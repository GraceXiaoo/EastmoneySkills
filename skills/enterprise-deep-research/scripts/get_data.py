#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enterprise-deep-research 本地数据兜底脚本
========================================

本脚本只做本地结构化数据获取与 JSON 落盘，不调用企业一页纸服务端报告生成接口。
MQL MCP 不可用、单个 MQL 数据集报错或缺关键字段时，可用本脚本通过 Choice REST
接口兜底取数，再由本地 prompt 生成报告正文。

用法:
  python scripts/get_data.py resolve --name "<企业全称>"
  python scripts/get_data.py fetch --org <完整机构代码> [--out <目录>]
  python scripts/get_data.py fetch --org <完整机构代码> --analysis-results <JSON文件>

fetch 输出会保留全局 datasets 作为调试底稿，同时生成 selected_blocks 与
block_data_packages。生成正文时只能使用对应板块的材料与必要业务元数据，
sources 等内部审计字段不传给 prompt，不得把全局 datasets 混合传入 prompt。

重点关注的 block_data_package 是例外：它只接收前 14 个板块已经生成的分析正文，
不接收 MQL/Python 原始数据，也不发起新的 MQL 或资讯查询。

退出码:
  0 = 成功（至少一个数据集成功返回）
  1 = 参数错误
  2 = 网络或业务失败
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional


BASE_API = "https://datacenter-choice.eastmoney.com/api/data/v1/get"
BASE_CHOICE = "https://datacenter-choice.eastmoney.com/choice/api/data/v1/get"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

HTTP_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_RETRIES = 10
ESG_ORG_NAME = "中诚信绿金"

PROMPT_FILES = {
    "基本情况": "references/analysis-prompts/basic-info.md",
    "股东情况": "references/analysis-prompts/shareholder.md",
    "所处行业": "references/analysis-prompts/industry.md",
    "经营状况": "references/analysis-prompts/operation.md",
    "ESG分析": "references/analysis-prompts/esg.md",
    "财务状况": "references/analysis-prompts/financial-general.md",
    "财务状况（债券发行人）": "references/analysis-prompts/financial-bond-issuer.md",
    "发行概述": "references/analysis-prompts/issuance-overview.md",
    "定价分析（债券发行人）": "references/analysis-prompts/pricing-bond-issuer.md",
    "定价分析（城投）": "references/analysis-prompts/pricing-urban-investment.md",
    "科创能力": "references/analysis-prompts/sci-tech-capability.md",
    "偿债分析": "references/analysis-prompts/solvency.md",
    "信用分析": "references/analysis-prompts/credit-analysis.md",
    "司法风险": "references/analysis-prompts/judicial-risk.md",
    "重点关注": "references/analysis-prompts/key-concerns.md",
}

# 重点关注固定接收前面的 14 个板块。即使某个板块因企业类型路由未被选择，
# 也必须在交接包中保留该槽位，并传入空字符串。
PREVIOUS_ANALYSIS_BLOCKS = [
    "基本情况",
    "股东情况",
    "所处行业",
    "经营状况",
    "ESG分析",
    "财务状况",
    "财务状况（债券发行人）",
    "发行概述",
    "定价分析（债券发行人）",
    "定价分析（城投）",
    "科创能力",
    "偿债分析",
    "信用分析",
    "司法风险",
]

# key-concerns.md 当前使用的占位符名称。基本情况占位槽位虽然暂未出现在
# 用户原文 prompt 中，仍保留在 prompt_inputs 和 analysis_results 中，避免丢失
# 前 14 个板块的固定位置；渲染时只替换 prompt 中实际存在的占位符。
KEY_CONCERNS_PROMPT_INPUTS = {
    "基本情况": "基本情况内容",
    "股东情况": "股东股权内容",
    "所处行业": "所处行业内容",
    "经营状况": "经营状况内容",
    "ESG分析": "ESG分析内容",
    "财务状况": "财务状况内容",
    "财务状况（债券发行人）": "财务状况（债券发行人）内容",
    "发行概述": "发行概述内容",
    "定价分析（债券发行人）": "定价分析（债券发行人）内容",
    "定价分析（城投）": "定价分析（城投）内容",
    "科创能力": "科创能力分析",
    "偿债分析": "偿债分析内容",
    "信用分析": "信用分析内容",
    "司法风险": "司法风险内容",
}

BASIC_INFO_FIELDS = [
    "COMPETITOR",
    "FOUND_DATE",
    "GBGI_INDUSTRY",
    "IS_LFP",
    "IS_LISCOM",
    "MAIN_ORG_NAME",
    "ORG_CODE",
    "ORG_NAME",
    "ORG_CODE_FXR",
    "ORG_FORM_TOTAL",
    "ORG_PROFILE",
    "PROVINCE_NAME",
    "REG_CAPITAL",
    "REG_ADDRESS",
    "SCOPE",
    "SJKZR",
    "SOCIAL_CREDIT_CODE",
    "STOCKGLANCE_NEW",
    "TOP1_HOLDER_ST",
]

INDUSTRY_FIELDS = [
    "GBGI_INDUSTRY",
    "PROVINCE_NAME",
]

ESG_ANALYSIS_FIELDS = [
    "ESG_RATING",
    "ESGRATING_MID",
    "ESG_SCORE",
    "ESG_AVG",
    "ESGSCORE_MID",
    "ESG_INDNO",
    "ESG_INDNOZF",
    "ESG_NO",
    "ESG_STDSCORE",
    "ESG_INDAVGSCORE",
    "INDUSTRY_NAME",
    "INDUSTRY_NUM",
    "UPDATEDATE",
    "E_SCORE",
    "E_RATING",
    "S_SCORE",
    "S_RATING",
    "G_SCORE",
    "G_RATING",
    "ESG_MANAGE_SCORE",
    "ESG_RA_SCORE",
    "ESG_ORG",
]

SCI_TECH_FIELDS = [
    "ORG_CODE",
    "ORG_NAME",
    "TAG_CODE",
    "TAG_NAME",
    "TECH_FIELD",
    "TECH_TITLE",
]

SCI_TECH_PROPERTY_SUMMARY_FIELDS = [
    "ORG_CODE",
    "SECURITY_NAME_ABBR",
    "END_DATE",
    "商标",
    "专利",
    "著作权",
    "软件著作权",
    "域名",
]

SCI_TECH_PROPERTY_YEARLY_FIELDS = [
    "ORG_CODE",
    "SECURITY_NAME_ABBR",
    "年份",
    "商标",
    "专利",
    "著作权",
    "软件著作权",
    "域名",
]

SCI_TECH_PATENT_FIELDS = [
    "ORG_CODE",
    "SECURITY_NAME_ABBR",
    "END_DATE",
    "SYSDATE_DATE",
    "TOTAL_ACCUM_NUM",
    "INVENT_ACCUM_NUM",
    "UTILITY_ACCUM_NUM",
    "DESIGN_ACCUM_NUM",
    "INTL_ACCUM_NUM",
    "BANKNAME",
    "DERIVE_SECURITY_CODE",
]

SCI_TECH_TRADEMARK_FIELDS = [
    "ORG_CODE",
    "SECURITY_NAME_ABBR",
    "类别",
    "数量",
    "END_DATE",
]

SCI_TECH_RD_EXP_FIELDS = [
    "ORG_CODE",
    "SECUCODE",
    "SECURITY_NAME_ABBR",
    "REPORT_DATE",
    "REPORT_YEAR",
    "STD_ITEM_CODE",
    "STD_ITEM_NAMENEW",
    "CURRENT_AMT",
    "REPORT_TYPE",
    "REPORT_TYPE_CODE",
    "TYPE",
    "TYPE_CODE",
]

SCI_TECH_RD_EMP_FIELDS = [
    "SECUCODE",
    "SECURITY_CODE",
    "SECURITY_NAME_ABBR",
    "REPORT_DATE",
    "NOTICE_DATE",
    "RESEARCH_NUM",
    "TOTAL_NUM",
    "TECHNOLOGY_NUM",
    "DOCTOR_NUM",
    "MASTER_NUM",
    "GRADUATE_NUM",
    "ADMINISTRATOR_NUM",
    "PRODUCT_NUM",
    "SALE_NUM",
    "FINANCE_NUM",
    "OTHER_NUM",
    "RETIRE_NUM",
    "CORE_NUM",
]

SCI_TECH_TITLE_FIELDS = [
    "是否高新技术企业",
    "所属概念板块",
    "TAG_NAME",
    "TECH_TITLE",
    "IS_ZJTX",
    "IS_DJSQY",
]

SCI_TECH_INDUSTRY_FIELDS = [
    "ORG_CODE",
    "ORG_NAME",
    "GBGI_INDUSTRY",
    "PROVINCE_NAME",
]

CREDIT_BASIC_FIELDS = [
    "ORG_CODE",
    "ORG_NAME",
    "RATING",
    "RATING_EXPECT",
    "DIRECTION",
    "RATING_ORG_NAME",
    "RATING_DATE",
    "SJKZR",
    "TOP1_HOLDER_ST",
    "TAG_CODE",
    "TAG_NAME",
]

CREDIT_ANALYSIS_FIELDS = [
    "BANKCT_AMOUNT",
    "BANKCT_COUNT",
    "BANKCT_NAME",
    "BANKCT_USE_AMOUNT",
    "CASHTOSTDEBT",
    "DEFAULT_PRICE",
    "DIRECTION",
    "GUARANTAMT_ASSETS_RATIO",
    "GUARANTAMT_EQUITY_RATIO",
    "GUARANT_AMT",
    "ISSUERRATECWS",
    "ISSUERRATEFWS",
    "ISSUERRATES",
    "JYXJECDX",
    "JYXJECLD",
    "NEWEST_DEFAULT",
    "ORG_CODE",
    "ORG_CODE_FXR",
    "PROLONG_NUM",
    "RATING",
    "RATING_EXPECT",
    "REAL_DEFAULT_NUM",
    "REPORT_DATE",
    "TOP10_GUARANTEED",
    "UCD_RATIO",
]

SOLVENCY_FINANCIAL_KEY_METRICS_FIELDS = [
    "CASHII",
    "CURRENT_RATIO",
    "DEBT_ASSET_RATIO",
    "EBITZTFNEW",
    "INTSTCOVRATE",
    "NETPROFIT",
    "OCFTOINTEREST",
    "ORG_CODE",
    "REPORT_DATE",
    "SPEED_RATIO",
    "TOTAL_ASSETS",
    "TOTAL_CURRENT_LIAB",
    "TOTAL_NONCURRENT_LIAB",
    "YYZB",
]

SOLVENCY_CREDIT_ANALYSIS_FIELDS = [
    "BANKCT_AMOUNT",
    "BANKCT_COUNT",
    "BANKCT_NAME",
    "BANKCT_USE_AMOUNT",
    "CASHTOSTDEBT",
    "DEFAULT_PRICE",
    "GUARANTAMT_ASSETS_RATIO",
    "GUARANTAMT_EQUITY_RATIO",
    "ISSUERRATECWS",
    "ISSUERRATEFWS",
    "ISSUERRATES",
    "JYXJECDX",
    "JYXJECLD",
    "NEWEST_DEFAULT",
    "ORG_CODE",
    "PROLONG_NUM",
    "REAL_DEFAULT_NUM",
    "REPORT_DATE",
    "TOP10_GUARANTEED",
    "UCD_RATIO",
]

SOLVENCY_LIABILITY_STRUCTURE_FIELDS = [
    "ACCOUNTS_PAYABLE",
    "BOND_PAYABLE",
    "CD_NOTE_PAYABLE",
    "LONG_LOAN",
    "ORG_CODE",
    "OTHER_CURRENT_LIAB",
    "OTHER_LIAB",
    "REPORT_DATE",
    "SHORT_LOAN",
    "TYPE_CODE",
]

SOLVENCY_SHAREHOLDER_FIELDS = [
    "SJKZR",
    "TOP1_HOLDER_ST",
]

# MQL 财务摘要报表的 reportFields（Python REST JSON 解包后的字段键）。
# 不同市场接口的原始载荷分别位于 FIN_INDICATOR1 / FIN_SUMMARY，见
# normalize_financial_summary_rows()。
FINANCIAL_SUMMARY_FIELDS = [
    "ORG_CODE",
    "REPORT_DATE",
    "TYPE_CODE",
    "DATE_TYPE_CODE",
    "DATE_TYPE_NEW",
    "IS_NEWEST",
    "CURRENCY_ORIG",
    "OPERATE_INCOME",
    "OPERATE_INCOME_A",
    "OPERATE_COST",
    "OPERATE_PROFIT",
    "NETPROFIT",
    "PARENT_NETPROFIT",
    "DEDU_PARENT_PROFIT",
    "NRPL",
    "CURRENT_ASSETS",
    "CURRENT_ASSET_NON",
    "FIXED_ASSET",
    "CURRENT_LIAB",
    "NONCURRENT_LIAB",
    "LONG_EQUITY_INVEST",
    "CAPITAL_RESERVE",
    "NETCASH_OPERATE",
    "NETCASH_INVEST",
    "NETCASH_FINANCE",
    "CASH_NETADD",
    "END_CASH",
    "DEBT_ASSET_RATIO",
    "AVERAGE_ROE",
    "DILUTED_ROE",
    "DEDUCT_WEIGHT_ROE",
    "JROA",
    "BASIC_EPS",
    "BVPS_ORIG",
    "BVPS_DILUTED",
    "OCFPS",
    "CFPS",
    "PER_OPERATE_INCOME",
    "FIXED_LONGASSET_CASH",
    "INVEST_PAY_CASH",
    "ACCEPT_INVEST_CASH",
    "AMORTIZE_PROVISION",
    "EBIT",
    "EBITDA",
    "EBIT_ZSR",
    "EBITDA_ZSR",
]

ISSUANCE_OVERVIEW_FIELDS = [
    "SECUCODE",
    "BOND_NAME_ABBR",
    "SECURITY_TYPE",
    "CURRENT_BALANCE",
    "CURRENCY",
    "ISSUE_DATE",
    "EXPIRE_DATE",
    "REMAIN_DAY",
    "BOND_RATING",
    "CREDIT_RATING",
    "FXCKLL",
    "CREDIT_SUBJECT_NAME",
    "GROUP_NAME",
]

URBAN_INVESTMENT_BOND_FILTER_FIELDS = [
    "ORG_CODE",
    "FILTER_CONTENT",
    "FILTER_TYPE_CODE",
    "INTERBANK_DEPO",
]

URBAN_INVESTMENT_BOND_FILTER_MQL_PATH = (
    "Choice报表\\报表指标\\Choice金融终端\\企业F9\\企业一页纸\\"
    "信用债发行企业一页纸专项数据\\发行人发行债券类型|"
    "RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER"
)

# This is the same underlying report as the urban-investment check, but it
# serves a different decision path. The issuer route uses 发行人代码 in MQL;
# it must not reuse the urban route's 信用主体代码 filter.
BOND_ISSUER_FILTER_FIELDS = [
    "ORG_CODE",
    "FILTER_CONTENT",
]

BOND_ISSUER_ALLOWED_TYPES = [
    "短期融资券",
    "超短期融资券",
    "中期票据",
    "集合票据",
    "项目收益票据",
    "定向工具(PPN)",
    "一般公司债",
    "项目收益专项债",
    "私募公司债",
    "一般企业债",
    "项目收益债",
    "中小企业集合债",
]

BOND_ISSUER_FILTER_MQL_PATH = URBAN_INVESTMENT_BOND_FILTER_MQL_PATH

ISSUER_CURVE_FIELDS = [
    "期限(年)",
    "利率(%)",
    "数据日期",
    "统计时间",
    "经纪商成交(笔)",
    "CFETS成交量(万)",
    "交易所成交量(万)",
    "成交天数",
    "平均偏离(BP)",
    "最大负偏(BP)",
    "负偏日期",
    "最大正偏(BP)",
    "正偏日期",
    "平均利差",
    "最大利差",
    "最大利差日期",
    "最小利差",
    "最小利差日期",
]

ISSUER_BOND_TYPE_FIELDS = [
    "SECUCODE",
    "ORG_CODE",
    "ISSUE_SECUCODE_YS",
    "BOND_NAME_ABBR",
    "BOND_NAME",
    "RAISEWAY",
    "SAMPLE_CODE",
    "SAMPLE_TYPE",
    "EXPIRE_DATE",
    "ORG_CODE_YS",
    "SECUCODE_YS",
    "EMBOND_3LEVEL_CODE",
    "EMBOND_3LEVEL",
]

MARKET_CONTEXT_FIELDS = [
    "DR007",
    "R007",
    "DR007_R007_SPREAD",
    "OMO_7D_NET_INJECTION",
    "MLF_6M_OPERATION",
    "MLF_1Y_MATURITY",
    "WEEK_NET_INJECTION",
    "MONTH_NET_INJECTION",
    "DATA_DATE",
]

URBAN_REGION_COMPARE_FIELDS = [
    "区域经济",
    "GDP(亿)",
    "人均GDP(元)",
    "区域财政",
    "一般公共预算收入(亿)",
    "财政自给率(%)",
    "政府性基金收入(亿)",
    "上市公司数量",
    "区域债务",
    "负债率(%)",
    "债务率(宽口径,全辖,%)",
    "区域城投债券余额增速(%)",
    "城投短期有息债务占比(%)",
    "区域高收益债务占比(%)",
    "区域土地",
    "常住人口(万人)",
    "二手房均价(元)",
    "城投债最高收益率(%)",
    "国有资本经营收入对区域债务覆盖率(%)",
    "区域经济地位",
    "GDP占比(%)",
    "国家级园区数",
    "区域债务地位",
    "发债规模占比(%)",
    "END_DATE",
    "AREA_CODE",
    "AREA_NAME",
    "全国排名",
]

URBAN_MARGIN_ANALYSIS_FIELDS = [
    "交易日期",
    "地区利差(BP)",
    "区域名称",
    "区域代码",
    "AREA_TYPE",
    "AREA_CODE",
]

URBAN_ISSUER_MARGIN_FIELDS = [
    "交易日期",
    "主体利差(BP)",
    "发行人名称",
    "发行人代码",
    "最新交易日",
    "有效日期",
]

# Legacy shared bond subset retained for the still-unconfigured pricing and
# solvency routes. Issuance overview uses its own dedicated field whitelist.
BOND_FIELDS = [
    "BOND_NAME_ABBR",
    "SECURITY_TYPE",
    "ISSUE_SCALE",
    "CURRENT_BALANCE",
    "ISSUE_DATE",
    "EXPIRE_DATE",
    "REMAIN_DAY",
    "FXCKLL",
    "CREDIT_RATING",
    "BOND_RATING",
    "GUARANTEE",
    "IS_ABS",
]


def _request_json(url: str, timeout: int = HTTP_TIMEOUT_SECONDS) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Referer": "https://data.eastmoney.com/",
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw_bytes = resp.read()
        encodings = [resp.headers.get_content_charset(), "utf-8", "gb18030"]
        raw = ""
        for encoding in encodings:
            if not encoding:
                continue
            try:
                raw = raw_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if not raw:
            raw = raw_bytes.decode("utf-8", "replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("接口返回格式异常")
    return data


def http_get_json(url: str) -> Dict[str, Any]:
    last_error: Optional[BaseException] = None
    for attempt in range(1, MAX_TIMEOUT_RETRIES + 1):
        try:
            return _request_json(url)
        except TimeoutError as exc:
            last_error = exc
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if "timed out" not in message and "timeout" not in message:
                raise
            last_error = exc
        if attempt < MAX_TIMEOUT_RETRIES:
            time.sleep(min(2 * attempt, 10))
    raise RuntimeError("接口超时重试超过10次，已中断调用: %r" % last_error)


def api(
    base: str,
    report_name: str,
    filter_str: str,
    columns: Optional[str] = None,
    sort_columns: Optional[str] = None,
    sort_types: Optional[str] = None,
    page: Any = 1,
    page_size: Any = None,
    source: Optional[str] = None,
    client: str = "SW",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {"reportName": report_name, "client": client}
    if filter_str:
        params["filter"] = filter_str
    if columns:
        params["columns"] = columns
    if sort_columns:
        params["sortColumns"] = sort_columns
        params["sortTypes"] = sort_types if sort_types is not None else "-1"
    params["pageNumber"] = page
    if page_size is not None:
        params["pageSize"] = page_size
    if source:
        params["source"] = source
    if extra:
        params.update(extra)
    url = base + "?" + urllib.parse.urlencode(params)
    data = http_get_json(url)
    result = data.get("result") or {}
    rows = result.get("data") or []
    return {
        "rows": rows if isinstance(rows, list) else [],
        "count": result.get("count", len(rows) if isinstance(rows, list) else 0),
        "raw": data,
        "url": url,
    }


def api_any(
    report_name: str,
    filter_str: str,
    prefer: str = "api",
    columns: Optional[str] = None,
    sort_columns: Optional[str] = None,
    sort_types: Optional[str] = None,
    page: Any = 1,
    page_size: Any = None,
    source: Optional[str] = None,
    client: str = "SW",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    bases = (BASE_CHOICE, BASE_API) if prefer == "choice" else (BASE_API, BASE_CHOICE)
    last_error = ""
    first_empty: Optional[Dict[str, Any]] = None
    for base in bases:
        try:
            result = api(
                base,
                report_name,
                filter_str,
                columns=columns,
                sort_columns=sort_columns,
                sort_types=sort_types,
                page=page,
                page_size=page_size,
                source=source,
                client=client,
                extra=extra,
            )
            result["_base"] = base
            if result["rows"]:
                return result
            if first_empty is None:
                first_empty = result
            last_error = "empty rows"
        except Exception as exc:  # noqa: BLE001
            last_error = "%s: %s" % (type(exc).__name__, exc)
    return first_empty or {"rows": [], "count": 0, "_error": last_error}


def norm_date(value: Any) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(value))
    if not match:
        return None
    return "%s-%02d-%02d" % (match.group(1), int(match.group(2)), int(match.group(3)))


def parse_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_json_payload(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def normalize_financial_summary_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unpack FIN_INDICATOR1/FIN_SUMMARY for the financial-general prompt."""
    normalized: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue

        item = {
            field: row.get(field)
            for field in FINANCIAL_SUMMARY_FIELDS
            if field in row
        }
        metrics: Dict[str, Any] = {}
        for payload_key in ("FIN_INDICATOR1", "FIN_SUMMARY"):
            payload = parse_json_payload(row.get(payload_key))
            if isinstance(payload, dict):
                metrics.update(payload)
            elif payload is not None:
                metrics[payload_key] = payload

        if metrics:
            item["metrics"] = metrics
        else:
            # Preserve the raw payload only when the local fallback cannot
            # decode it, so the caller can diagnose the source response.
            for payload_key in ("FIN_INDICATOR1", "FIN_SUMMARY"):
                if row.get(payload_key) not in (None, ""):
                    item[payload_key] = row.get(payload_key)

        normalized.append(item)
    return normalized


def has_non_empty_value(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def extract_analysis_content(value: Any) -> str:
    """Read only generated analysis text, never raw datasets."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "\n".join(
            extract_analysis_content(item)
            for item in value
        ).strip()
    if isinstance(value, dict):
        for key in ("content", "analysis", "summary", "text", "result", "正文"):
            if key in value:
                return extract_analysis_content(value.get(key))
        return ""
    return str(value).strip()


def usable_analysis_content(value: Any) -> str:
    """Keep inline citations; treat no-data chapter results as empty slots."""
    content = extract_analysis_content(value)
    text_without_legacy_citations = re.sub(r"【#[^\r\n】]*#】", "", content).strip()
    if text_without_legacy_citations in ("", "暂无数据"):
        return ""
    return content


def normalize_analysis_handoff(
    analysis_results: Any,
    selected_blocks: Iterable[str],
) -> Dict[str, Dict[str, Any]]:
    """Build the fixed 14-slot handoff used by the key-concerns prompt.

    The caller may provide either:
      {"股东情况": "分析正文"}
    or:
      {
          "analysis_results": {"股东情况": {"content": "..."}}
      }

    Only blocks selected by the enterprise route are allowed to carry content.
    Inline citations are preserved; local audit metadata is not forwarded.
    """
    selected = set(selected_blocks or [])
    payload = analysis_results
    if isinstance(payload, dict) and isinstance(payload.get("analysis_results"), dict):
        payload = payload.get("analysis_results")

    if not isinstance(payload, dict):
        payload = {}

    normalized: Dict[str, Dict[str, Any]] = {}
    for block in PREVIOUS_ANALYSIS_BLOCKS:
        if block not in selected:
            normalized[block] = {"content": ""}
            continue

        normalized[block] = {"content": usable_analysis_content(payload.get(block))}
    return normalized


def one(rows: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for row in rows:
        return row
    return None


def detect_market(stock_glance: Any) -> str:
    text = str(stock_glance or "")
    match = re.search(r"(\d{6}|\d{5})", text)
    if not match:
        return "org"
    code = match.group(1)
    if re.fullmatch(r"\d{6}", code):
        if code[:2] in ("60", "68", "00", "30", "43"):
            return "sh"
        return "hk"
    if re.fullmatch(r"\d{5}", code):
        return "hk"
    return "sh"


def split_tag_codes(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        codes: List[str] = []
        for item in value:
            codes.extend(split_tag_codes(item))
        return codes
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,;；|/、，\s]+", text) if part.strip()]


def has_tag_prefix(tag_codes: Iterable[str], prefix: str) -> bool:
    return any(str(code).strip().startswith(prefix) for code in tag_codes)


def is_meaningful_filter_content(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.upper() not in {"NULL", "NONE", "-", "—", "--"}


def split_bond_filter_contents(value: Any) -> List[str]:
    """Split one FILTER_CONTENT value without weakening exact type matching."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        output: List[str] = []
        for item in value:
            output.extend(split_bond_filter_contents(item))
        return output

    text = str(value).strip()
    if not text or text.upper() in {"NULL", "NONE", "-", "—", "--"}:
        return []
    return [
        item.strip()
        for item in re.split(r"[,，;；|/、\n\r]+", text)
        if item.strip()
    ]


def filter_bond_issuer_special_rows(
    rows: Iterable[Dict[str, Any]],
    org_code: str,
    today: dt.date,
) -> List[Dict[str, Any]]:
    """Apply the issuer-specific filter and retain active, meaningful rows.

    The REST request applies the complete date condition before aggregation.
    Recheck explicit dates if supplied; hidden dates must not be inferred.
    """
    today_text = today.isoformat()
    filtered: List[Dict[str, Any]] = []
    for row in rows or []:
        row_org_code = str(
            row.get("ORG_CODE")
            or row.get("ISSUE_CODE")
            or row.get("发行人代码")
            or ""
        ).strip()
        if row_org_code and row_org_code != org_code:
            continue

        group_value = str(row.get("IS_GROUP") or row.get("集团系") or "").strip()
        if group_value and group_value not in {"0", "0.0"}:
            continue

        filter_type = str(row.get("FILTER_TYPE_CODE", row.get("筛选类型编码", ""))).strip()
        if filter_type and filter_type not in {"1", "1.0"}:
            continue

        interbank_depo = str(row.get("INTERBANK_DEPO", row.get("是否剔除同业存单", ""))).strip()
        if interbank_depo and interbank_depo not in {"1", "1.0"}:
            continue

        content = row.get("FILTER_CONTENT")
        if content in (None, ""):
            content = row.get("筛选内容")
        if not is_meaningful_filter_content(content):
            continue

        raw_expire_date = str(
            row.get("EXPIRE_DATE")
            or row.get("到期日期")
            or ""
        ).strip()
        if raw_expire_date.upper() not in {"", "NULL", "NONE"}:
            expire_date = norm_date(raw_expire_date)
            if not expire_date:
                raise ValueError("发债人专项到期日期无法解析: %s" % raw_expire_date)
            if expire_date <= today_text:
                continue

        filtered.append(row)
    return filtered


def bond_filter_whitelist_rows(
    rows: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return rows whose FILTER_CONTENT contains an exact allowed bond type."""
    allowed = set(BOND_ISSUER_ALLOWED_TYPES)
    matched: List[Dict[str, Any]] = []
    for row in rows or []:
        content = row.get("FILTER_CONTENT")
        if content in (None, ""):
            content = row.get("筛选内容")
        tokens = split_bond_filter_contents(content)
        if any(token in allowed for token in tokens):
            matched.append(row)
    return matched


def classify_enterprise_type(
    rows: Iterable[Dict[str, Any]],
    urban_investment_bond_filter: Optional[Dict[str, Any]] = None,
    bond_issuer_special_filter: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data = list(rows or [])
    tag_codes: List[str] = []
    secucode_bjn_values: List[str] = []
    for row in data:
        tag_codes.extend(split_tag_codes(row.get("TAG_CODE")))
        value = str(row.get("SECUCODE_BJN") or "").strip()
        if value:
            secucode_bjn_values.append(value)

    urban_tag_match = has_tag_prefix(tag_codes, "003005")
    urban_bond_filter_rows = list(
        (urban_investment_bond_filter or {}).get("rows", [])
    )
    urban_bond_filter_rows = [
        row for row in urban_bond_filter_rows
        if is_meaningful_filter_content(
            row.get("FILTER_CONTENT") or row.get("筛选内容")
        )
    ]
    urban_bond_filter_match = bool(urban_bond_filter_rows)
    is_urban_investment = urban_tag_match and urban_bond_filter_match
    is_sci_tech = (not is_urban_investment) and has_tag_prefix(tag_codes, "003002")
    bond_excluded = has_tag_prefix(tag_codes, "003001") or has_tag_prefix(tag_codes, "003005")

    bond_issuer_special_rows = filter_bond_issuer_special_rows(
        (bond_issuer_special_filter or {}).get("rows", []),
        str((bond_issuer_special_filter or {}).get("org_code") or "").strip(),
        dt.date.fromisoformat(
            str((bond_issuer_special_filter or {}).get("as_of_date") or dt.date.today())
        ),
    ) if bond_issuer_special_filter else []
    bond_issuer_whitelist_rows = bond_filter_whitelist_rows(
        bond_issuer_special_rows
    )
    generic_bond_issuer_match = (
        (not is_urban_investment)
        and bool(secucode_bjn_values)
        and not bond_excluded
    )
    special_result = bond_issuer_special_filter or {}
    special_failed = (
        not special_result
        or special_result.get("status") == "failed"
        or bool(special_result.get("fallback_reason"))
    )

    # The extra issuer report is conditional: one allowed bond type makes the
    # special rule applicable; if every returned type is outside the whitelist,
    # the report is ignored and the established generic rule decides.
    bond_issuer_special_applicable = bool(bond_issuer_whitelist_rows)
    if generic_bond_issuer_match and special_failed:
        is_bond_issuer = None
    elif bond_issuer_special_applicable:
        is_bond_issuer = generic_bond_issuer_match and bool(
            bond_issuer_whitelist_rows
        )
    else:
        is_bond_issuer = generic_bond_issuer_match

    return {
        "status": "failed" if is_bond_issuer is None else ("ok" if data else "empty"),
        "judgement_path": "Python REST fallback",
        "fallback_from": "MQL",
        "source_dataset": "RPT_COP_ORG_INFO",
        "tag_codes": tag_codes,
        "secucode_bjn_values": secucode_bjn_values,
        "urban_tag_match": urban_tag_match,
        "urban_bond_filter_match": urban_bond_filter_match,
        "urban_bond_filter_rows": len(urban_bond_filter_rows),
        "is_urban_investment": is_urban_investment,
        "is_sci_tech": is_sci_tech,
        "is_bond_issuer": is_bond_issuer,
        "generic_bond_issuer_match": generic_bond_issuer_match,
        "bond_issuer_special_rows": len(bond_issuer_special_rows),
        "bond_issuer_special_whitelist_rows": len(bond_issuer_whitelist_rows),
        "bond_issuer_special_applicable": bond_issuer_special_applicable,
        "bond_issuer_special_status": "failed" if special_failed else special_result.get("status", "ok"),
        "bond_issuer_special_match": bool(bond_issuer_whitelist_rows),
        "bond_issuer_special_allowed_types": BOND_ISSUER_ALLOWED_TYPES,
        "rules": {
            "urban_investment": (
                "TAG_CODE startswith 003005 AND "
                "发行人发行债券类型 returns meaningful FILTER_CONTENT "
                "after 信用主体代码=current_org, 筛选类型编码=1, "
                "是否剔除同业存单=1, 到期日期>=system_date"
            ),
            "sci_tech": "non-urban TAG_CODE startswith 003002",
            "bond_issuer": (
                "non-urban SECUCODE_BJN non-empty and TAG_CODE not startswith "
                "003001 or 003005; when the issuer-special report has at least "
                "one allowed FILTER_CONTENT, the allowed row must also exist; "
                "when all returned bond types are outside the whitelist, skip "
                "the special rule and use the generic condition"
            ),
            "esg": "RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS ESG_SCORE non-empty",
        },
    }


def normalize_org_code(org_code: str) -> str:
    """Preserve the complete issuer identifier returned by entity resolution."""
    match = re.fullmatch(r"([0-9]+)(?:\.FXR)?", (org_code or "").strip(), re.IGNORECASE)
    if not match:
        raise ValueError("机构代码须为完整数字代码或发行人 .FXR 代码")
    return match.group(1)


def collect_esg_secucodes(org_code: str, rows: Iterable[Dict[str, Any]]) -> List[str]:
    fields = (
        "SECUCODE_PRI",
        "SECUCODE_AS",
        "SECUCODE_HKS",
        "SECUCODE_USS",
        "SECUCODE_BS",
        "SECUCODE_ND",
        "SECUCODE_BJN",
        "SECUCODE_BJW",
        "SECUCODE_BJNZ",
        "SECUCODE_BJNZ_ISSUER",
        "SECUCODE_FD",
    )
    candidates: List[str] = []
    if org_code:
        candidates.append("%s.FXR" % normalize_org_code(org_code))
    for row in rows or []:
        for field in fields:
            raw = str(row.get(field) or "").strip()
            if not raw:
                continue
            for item in re.split(r"[,;；|/、，\s]+", raw):
                code = item.strip()
                if code:
                    candidates.append(code)

    seen = set()
    ordered: List[str] = []
    for code in candidates:
        key = code.upper()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(code)
    return ordered


def normalize_esg_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize common REST aliases into the logical ESG field names."""
    out = dict(row or {})
    aliases = {
        "ESGRATING_MID": ("ESGRATING_MID", "ESG_RATING_MID"),
        "ESG_AVG": ("ESG_AVG", "ESG_SCORE_AVG", "ESG_INDAVGSCORE"),
        "ESGSCORE_MID": ("ESGSCORE_MID", "ESG_SCORE_MID"),
        "ESG_INDNOZF": ("ESG_INDNOZF", "ESG_SCORE_RN"),
        "ESG_NO": ("ESG_NO", "ESG_SCORE_RN"),
        "INDUSTRY_NAME": ("INDUSTRY_NAME", "INDUSTRY"),
    }
    for actual_name, candidates in aliases.items():
        if has_non_empty_value(out.get(actual_name)):
            continue
        for candidate in candidates:
            if has_non_empty_value(out.get(candidate)):
                out[actual_name] = out.get(candidate)
                break
    return out


def normalize_basic_info_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Align REST-only aliases with the confirmed MQL field names."""
    out = dict(row or {})
    if not has_non_empty_value(out.get("ORG_FORM_TOTAL")) and has_non_empty_value(
        out.get("ORG_FORM_1LEVEL")
    ):
        out["ORG_FORM_TOTAL"] = out.get("ORG_FORM_1LEVEL")
    return out


def fetch_esg_scope(org_code: str, basic_rows: Iterable[Dict[str, Any]], today: dt.date) -> Dict[str, Any]:
    columns = (
        "SECUCODE,SECURITY_CODE,SNAME,@ORG_CODE;@ORG_CODE,ORG_NAME,USCC,"
        "INDUSTRY,INDUSTRY_CODE,INDUSTRY_TYPE,INDUSTRY_TYPE_CODE,ESG_ORG,"
        "UPDATEDATE,ESG_RATING,ESGRATING_MID,ESG_SCORE,ESG_AVG,"
        "ESGSCORE_MID,ESG_INDNO,ESG_INDNOZF,ESG_NO,ESG_STDSCORE,"
        "INDUSTRY_NAME,INDUSTRY_NUM,ESG_INDAVGSCORE,"
        "E_AVGSCORE,E_RANKING,E_RATING,E_SCORE,S_AVGSCORE,S_RANKING,S_RATING,S_SCORE,"
        "G_AVGSCORE,G_RANKING,G_RATING,G_SCORE,"
        "ESG_MANAGE_SCORE,ESG_RA_SCORE,"
        "SOURCE_TYPE,SECUCODE2,ESG_RATING_T"
    )
    candidates = collect_esg_secucodes(org_code, basic_rows)
    attempts: List[Dict[str, Any]] = []
    valid_rows: List[Dict[str, Any]] = []
    for secucode in candidates:
        filter_str = (
            '(SECUCODE="%s");(ORG_CODE="")(UPDATEDATE>=\'1900-01-01\')'
            "(UPDATEDATE<='%s')(INDUSTRY_TYPE_CODE=\"0203\")(ESG_ORG=\"%s\")"
        ) % (secucode, today.isoformat(), ESG_ORG_NAME)
        try:
            result = api_any(
                "RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS",
                filter_str,
                prefer="choice",
                columns=columns,
                sort_columns="UPDATEDATE",
                sort_types="-1",
                page=1,
                page_size=200,
                source="choice",
            )
            rows = result.get("rows", [])
            normalized_rows = [normalize_esg_row(row) for row in rows]
            detail_updatedates: List[str] = []
            for detail_row in normalized_rows:
                updatedate = norm_date(detail_row.get("UPDATEDATE")) or str(detail_row.get("UPDATEDATE") or "").strip()
                if updatedate and updatedate not in detail_updatedates:
                    detail_updatedates.append(updatedate)
            valid_candidate_rows = [
                detail_row
                for detail_row in normalized_rows
                if has_non_empty_value(detail_row.get("ESG_SCORE"))
            ]
            has_score = bool(valid_candidate_rows)
            attempts.append({
                "secucode": secucode,
                "esg_org": ESG_ORG_NAME,
                "rows": len(rows),
                "has_esg_score": has_score,
                "detail_updatedates": sorted(detail_updatedates, reverse=True),
                "error": result.get("_error", ""),
            })
            if has_score:
                for valid_row in valid_candidate_rows:
                    copied = dict(valid_row)
                    copied["_query_secucode"] = secucode
                    copied["_esg_scope_field"] = "ESG_SCORE"
                    valid_rows.append(copied)
        except Exception as exc:  # noqa: BLE001
            attempts.append({"secucode": secucode, "esg_org": ESG_ORG_NAME, "rows": 0, "has_esg_score": False, "error": repr(exc)})

    valid_rows.sort(key=lambda row: str(row.get("UPDATEDATE") or ""), reverse=True)
    latest = valid_rows[0] if valid_rows else None
    all_updatedates: List[str] = []
    for attempt in attempts:
        for updatedate in attempt.get("detail_updatedates", []):
            if updatedate and updatedate not in all_updatedates:
                all_updatedates.append(updatedate)
    return {
        "report": "RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS",
        "candidates": candidates,
        "esg_org": ESG_ORG_NAME,
        "attempts": attempts,
        "is_esg_scope": latest is not None,
        "latest": latest,
        "valid_rows": valid_rows[:3],
        "detail_updatedates": sorted(all_updatedates, reverse=True),
    }


def fetch_basic_info(org_code: str) -> Dict[str, Any]:
    columns = (
        "ORG_CODE,ORG_NAME,SOCIAL_CREDIT_CODE,FOUND_DATE,REG_ADDRESS,"
        "REG_CAPITAL,ORG_FORM_1LEVEL,GBGI_INDUSTRY,SCOPE,ORG_PROFILE,"
        "COMPETITOR,IS_LISCOM,STOCKGLANCE_NEW,SJKZR,TOP1_HOLDER_ST,"
        "IS_LFP,MAIN_ORG_NAME,IS_ST,IS_ZJTX,IS_DJSQY,PROVINCE_NAME,"
        "PROVINCE_CODE,ORG_INNER_CODE,TAG_CODE,TAG_NAME,SECUCODE_BJN,"
        "TECH_FIELD,TECH_TITLE,"
        "SECUCODE_BJNZ,SECUCODE_BJNZ_ISSUER,SECUCODE_PRI,SECUCODE_AS,"
        "SECUCODE_HKS,SECUCODE_USS,SECUCODE_BS,SECUCODE_ND,SECUCODE_BJW,"
        "SECUCODE_FD,RATING,RATING_EXPECT,DIRECTION,RATING_ORG_CODE,"
        "RATING_ORG_NAME,RATING_DATE,RATING_TYPE,RATING_CLASSIF_TYPE"
    )
    result = api_any(
        "RPT_COP_ORG_INFO",
        '(ORG_CODE="%s")' % org_code,
        columns=columns,
        sort_columns="ORG_CODE",
        sort_types="1",
        page=1,
        page_size=10,
        source="CHOICE",
    )
    rows = [normalize_basic_info_row(row) for row in result.get("rows", [])]
    return {"rows": rows, "count": result.get("count", len(rows))}


def fetch_shareholders(org_code: str, today: dt.date) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "latest_report_date": None,
        "top_holders": [],
        "holder_equity": [],
        "related_transactions": [],
        "related_window": "",
        "errors": {},
    }

    try:
        r = api_any(
            "RPT_BOND_GQJG_ISHOLDER",
            '(ISSUE_CODE="%s")(IS_SHOW=1)' % org_code,
            columns="ISSUE_CODE,END_DATE,END_DATE_ORIG",
            sort_columns="END_DATE",
            sort_types="-1",
            page=1,
            page_size=1,
        )
        row = one(r.get("rows", []))
        if row:
            out["latest_report_date"] = norm_date(row.get("END_DATE_ORIG") or row.get("END_DATE"))
    except Exception as exc:  # noqa: BLE001
        out["errors"]["latest_report_date"] = repr(exc)

    try:
        report_date = out.get("latest_report_date")
        if report_date:
            r = api_any(
                "RPT_BOND_GQJG_ISHOLDER",
                '(ISSUE_CODE="%s")(END_DATE=\'%s\')(IS_SHOW=1)' % (org_code, report_date),
                columns="ALL",
                page=1,
                page_size=200,
            )
            rows = []
            for item in r.get("rows", []):
                try:
                    rank = int(item.get("RANK"))
                except (TypeError, ValueError):
                    continue
                if 1 <= rank <= 10 or rank == 9999:
                    rows.append(item)
            out["top_holders"] = rows
    except Exception as exc:  # noqa: BLE001
        out["errors"]["top_holders"] = repr(exc)

    try:
        r = api_any(
            "RPT_CUSTOM_ORG_SHAREHOLDER_EQUITY",
            '(ORG_CODE="%s")(END_DATE=\'%s\')' % (org_code, today.isoformat()),
            source="CHOICE",
            sort_columns="REPORT_DATE",
            sort_types="-1",
            page=1,
            page_size=20,
        )
        if not r.get("rows"):
            r = api_any(
                "RPT_CUSTOM_ORG_SHAREHOLDER_EQUITY",
                '(ORG_CODE="%s")(REPORT_DATE<=\'%s\')' % (org_code, today.isoformat()),
                source="CHOICE",
                sort_columns="REPORT_DATE",
                sort_types="-1",
                page=1,
                page_size=20,
            )
        out["holder_equity"] = r.get("rows", [])
    except Exception as exc:  # noqa: BLE001
        out["errors"]["holder_equity"] = repr(exc)

    try:
        window_end = dt.date.fromisoformat(out["latest_report_date"]) if out.get("latest_report_date") else today
        start = window_end - dt.timedelta(days=365)
        out["related_window"] = "%s~%s" % (start.isoformat(), window_end.isoformat())
        r = api_any(
            "RPT_RELATED_TRANSACTION",
            '(ORG_CODE="%s")(NOTICE_DATE>=\'%s\')(NOTICE_DATE<=\'%s\')'
            % (org_code, start.isoformat(), window_end.isoformat()),
            columns="ALL",
            source="choice",
            sort_columns="NOTICE_DATE",
            sort_types="-1",
            page=1,
            page_size=50,
        )
        out["related_transactions"] = r.get("rows", [])
    except Exception as exc:  # noqa: BLE001
        out["errors"]["related_transactions"] = repr(exc)

    return out


def fetch_financial_summary(
    org_code: str, market: str, today: dt.date,
    *, history_start: Optional[dt.date] = None,
) -> Dict[str, Any]:
    # Include six completed calendar years initially; chart selection uses
    # actual annual periods and keeps the extra year until YoY is computed.
    start_date = min(history_start or today, dt.date(today.year - 6, 1, 1)).isoformat()
    end_date = today.isoformat()
    if market == "hk":
        filter_str = (
            '(ORG_CODE="%s")(TYPE_CODE in ("2"))(DATE_TYPE_NEW in ("1"))'
            "(((REPORT_DATE>='%s')(REPORT_DATE<='%s')"
            '(DATE_TYPE_CODE in ("1","5","3","6","8")))(|IS_NEWEST="1"))'
        ) % (org_code, start_date, end_date)
        r = api_any(
            "RPT_HKORGF9_FIN_SUMMARY",
            filter_str,
            columns="FIN_SUMMARY",
            source="CHOICE",
            page="",
            page_size="",
            sort_columns="REPORT_DATE,TYPE_CODE,DATE_TYPE_NEW",
            sort_types="-1,-1,1",
        )
        return {"market": "hk", "report": "RPT_HKORGF9_FIN_SUMMARY", "rows": r.get("rows", [])}

    if market == "us":
        filter_str = (
            '(ORG_CODE="%s")(TYPE_CODE in ("2"))(DATE_TYPE_NEW in ("1"))'
            "(((REPORT_DATE>='%s')(REPORT_DATE<='%s')"
            '(DATE_TYPE_CODE in ("1","5","3","6","8")))(|IS_NEWEST="1"))'
        ) % (org_code, start_date, end_date)
        r = api_any(
            "RPT_USORGF9_FIN_SUMMARY",
            filter_str,
            columns="FIN_SUMMARY",
            source="CHOICE",
            page="",
            page_size="",
            sort_columns="REPORT_DATE,TYPE_CODE,DATE_TYPE_NEW",
            sort_types="-1,-1,1",
        )
        return {"market": "us", "report": "RPT_USORGF9_FIN_SUMMARY", "rows": r.get("rows", [])}

    filter_str = (
        '(ORG_CODE="%s")(TYPE_CODE in ("1","2","3"))(DATE_TYPE_NEW in ("1"))'
        "(((REPORT_DATE>='%s')(REPORT_DATE<='%s')"
        '(DATE_TYPE_CODE in ("5","6")))(|IS_NEWEST="1"))'
    ) % (org_code, start_date, end_date)
    r = api_any(
        "RPT_CUSTOM_ORGF9_FIN_SUMMARY",
        filter_str,
        columns="FIN_INDICATOR1",
        page=1,
        page_size=100,
        sort_columns="STD_REPORT_DATE",
        sort_types="-1",
        source="choice",
    )
    return {"market": "sh", "report": "RPT_CUSTOM_ORGF9_FIN_SUMMARY", "rows": r.get("rows", [])}


def fetch_operation(
    org_code: str, market: str = "sh", today: Optional[dt.date] = None,
) -> Dict[str, Any]:
    """Query the same market and preserve the product-first fallback rule."""
    org_code = normalize_org_code(org_code)
    today = today or dt.date.today()
    if market not in ("sh", "us", "org"):
        raise RuntimeError("当前市场的主营构成 REST 模板尚未验证，不能套用已验证函数")
    start = dt.date(today.year - 5, 1, 1).isoformat()
    for type_code, type_name, label in (("2", "product", "产品"), ("3", "region", "地区")):
        report = (
            "RPT_HSF9_FN_MAINOPBUSINESS_NORMAL" if market == "sh"
            else (
                "RPT_ORGF9_FN_MAINOPBUSINESS" if market == "org"
                else ("RPT_USF9_INFO_PRODUCTSTRUCTURE" if type_name == "product"
                      else "RPT_USF9_INFO_AREASTRUCTURE")
            )
        )
        if market == "org":
            filter_str = (
                '(ORG_CODE="%s")(REPORT_DATE>=\'%s\')(REPORT_DATE<=\'%s\')'
                '(BELONG_TYPE="%s")(IS_MAXREPORTDATE="1")(METHOD_CODE="0")'
            ) % (org_code, start, today.isoformat(), label)
        else:
            filter_str = '(ORG_CODE="%s")(REPORT_DATE>=\'%s\')(REPORT_DATE<=\'%s\')' % (
                org_code, start, today.isoformat(),
            )
        if market == "sh":
            filter_str += '(Type="%s")' % label
        rows: List[Dict[str, Any]] = []
        page = 1
        while True:
            response = api_any(
                report, filter_str, prefer="choice", columns="ALL",
                sort_columns="REPORT_DATE", sort_types="-1",
                page=page, page_size=200, source="choice",
            )
            raw = response.get("raw") or {}
            code = raw.get("code")
            if response.get("_error") or code not in (None, 0, "0", 9201, "9201"):
                raise RuntimeError(str(response.get("_error") or raw.get("message") or code))
            if raw.get("success") is False and code not in (9201, "9201"):
                raise RuntimeError(str(raw.get("message") or "REST request failed"))
            batch = response.get("rows", [])
            if any(str(row.get("ORG_CODE", "")) != org_code for row in batch):
                raise RuntimeError("主营构成返回主体不匹配")
            rows.extend(batch)
            if len(rows) >= response.get("count", len(rows)):
                break
            if not batch:
                raise RuntimeError("主营构成分页未完整")
            page += 1
        if market == "org":
            rows = [
                row for row in rows
                if str(row.get("STD_CLASSIFY_CODE") or "") != "999"
                and str(row.get("ACT_REPORT_NAME") or "") != "合计"
            ]
        has_data = any(
            any(has_non_empty_value(row.get(field)) for field in (
                "MAIN_BUSINESS_INCOME", "MAIN_BUSINESS_COST", "MAIN_BUSINESS_RPOFIT",
            ))
            for row in rows
        )
        if has_data or type_name == "region":
            return {
                "report": report, "type_code": type_code, "type_name": type_name,
                "rows": rows, "count": len(rows), "filter": filter_str,
                "status": "ok" if rows else "empty",
                "fallback_reason": "",
                "notes": "" if type_name == "product" else "产品无有效数据，切换地区口径",
            }
    raise RuntimeError("No composition query executed")


def filter_issuance_overview_rows(rows: Iterable[Dict[str, Any]], today: dt.date) -> List[Dict[str, Any]]:
    today_text = today.isoformat()
    filtered: List[Dict[str, Any]] = []
    for row in rows or []:
        rn = row.get("SECUCODE_RN")
        if rn not in (None, "", 1, "1"):
            continue
        expire_date = norm_date(row.get("EXPIRE_DATE"))
        if expire_date and expire_date < today_text:
            continue
        security_type = str(row.get("SECURITY_TYPE") or "")
        bond_name = str(row.get("BOND_NAME_ABBR") or "")
        if "同业存单" in security_type or "同业存单" in bond_name:
            continue
        filtered.append(row)
    return filtered


def fetch_bonds(org_code: str) -> Dict[str, Any]:
    r = api_any(
        "RPT_CUSTOM_BOND_BS_SAMEISSUER",
        '(SECUCODE_RN=1)(ISSUE_CODE="%s")(IS_GROUP="0")(INTERBANK_DEPO="1")' % org_code,
        prefer="choice",
        columns="ALL",
        sort_columns="ISSUE_DATE",
        sort_types="-1",
        page=1,
        page_size=100,
        source="choice",
    )
    return {"rows": r.get("rows", []), "count": r.get("count", 0)}


def filter_urban_investment_bond_rows(
    rows: Iterable[Dict[str, Any]],
    org_code: str,
    today: dt.date,
) -> List[Dict[str, Any]]:
    """Keep meaningful rows from the verified specialized issuer-type report.

    The REST endpoint reliably returns the issuer code and filter content, but
    may omit the hidden filter columns. Therefore missing hidden columns must
    not reject a row. If a valid EXPIRE_DATE is actually returned, apply the
    local date bound; otherwise do not invent a date mapping.
    """
    today_text = today.isoformat()
    filtered: List[Dict[str, Any]] = []
    for row in rows or []:
        row_org_code = str(row.get("ORG_CODE") or row.get("ISSUE_CODE") or "").strip()
        if row_org_code and row_org_code != org_code:
            continue

        filter_type = str(row.get("FILTER_TYPE_CODE") or "").strip()
        if filter_type and filter_type not in {"1", "1.0"}:
            continue
        interbank_depo = str(row.get("INTERBANK_DEPO") or "").strip()
        if interbank_depo and interbank_depo not in {"1", "1.0"}:
            continue

        content = str(
            row.get("FILTER_CONTENT") or row.get("筛选内容") or ""
        ).strip()
        if not content or content.upper() in {"NULL", "NONE", "-", "—", "--"}:
            continue

        raw_expire_date = str(row.get("EXPIRE_DATE") or "").strip()
        if raw_expire_date.upper() not in {"", "NULL", "NONE"}:
            expire_date = norm_date(raw_expire_date)
            if expire_date and expire_date < today_text:
                continue
        filtered.append(row)
    return filtered


def fetch_urban_investment_bond_filter(
    org_code: str,
    today: dt.date,
) -> Dict[str, Any]:
    """Fetch the additional non-empty bond-filter condition for urban entities."""
    fixed_filter = (
        '(ORG_CODE="%s")(FILTER_TYPE_CODE="1")'
        '(INTERBANK_DEPO="1")'
    ) % org_code
    response = api_any(
        "RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER",
        fixed_filter,
        prefer="choice",
        columns=",".join(URBAN_INVESTMENT_BOND_FILTER_FIELDS),
        sort_columns="",
        sort_types="",
        page=1,
        page_size=200,
        source="choice",
    )
    rows = filter_urban_investment_bond_rows(
        response.get("rows", []),
        org_code,
        today,
    )
    return {
        "report": "RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER",
        "mql_report_path": URBAN_INVESTMENT_BOND_FILTER_MQL_PATH,
        "rows": rows,
        "count": len(rows),
        "as_of_date": today.isoformat(),
        "filter": fixed_filter,
        "filter_semantics": {
            "org_code": org_code,
            "filter_type_code": "1",
            "interbank_depo": "1",
            "expire_date": "apply_locally_only_if_returned",
        },
        "raw_count": len(response.get("rows", [])),
        "fallback_reason": response.get("_error", "") if not rows else "",
    }


def fetch_bond_issuer_special_filter(
    org_code: str,
    today: dt.date,
) -> Dict[str, Any]:
    """Fetch the issuer-specific bond-type rule used by bond classification.

    This deliberately has its own dataset and metadata even though the REST
    report name is shared with the urban-investment check. The issuer rule is
    keyed by the report's issuer-code field (ORG_CODE/发行人代码), whereas the
    urban rule is keyed by 信用主体代码 in MQL.
    """
    fixed_filter = (
        '(ORG_CODE="%s")(IS_GROUP="0")(FILTER_TYPE_CODE="1")'
        '(INTERBANK_DEPO="1")((EXPIRE_DATE>\'%s\')(|EXPIRE_DATE="NULL"))'
    ) % (org_code, today.isoformat())
    errors: List[str] = []
    for base in (BASE_CHOICE, BASE_API):
        try:
            response = api(
                base,
                "RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER",
                fixed_filter,
                columns=",".join(BOND_ISSUER_FILTER_FIELDS),
                page=1,
                page_size=200,
                source="CHOICE",
            )
        except Exception as exc:  # noqa: BLE001
            if "接口超时重试超过10次" in str(exc):
                raise
            errors.append(str(exc))
            continue
        raw = response.get("raw", {})
        if raw.get("success") is True or str(raw.get("code")) == "9201":
            break
        errors.append("%s: %s" % (raw.get("code"), raw.get("message")))
    else:
        raise RuntimeError("发债人专项查询失败: " + "; ".join(errors))
    raw_rows = response.get("rows", [])
    rows = filter_bond_issuer_special_rows(
        raw_rows,
        org_code,
        today,
    )
    whitelist_rows = bond_filter_whitelist_rows(rows)
    return {
        "report": "RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER",
        "mql_report_path": BOND_ISSUER_FILTER_MQL_PATH,
        "status": "ok" if rows else "empty",
        "org_code": org_code,
        "rows": rows,
        "whitelist_rows": whitelist_rows,
        "count": len(rows),
        "whitelist_count": len(whitelist_rows),
        "as_of_date": today.isoformat(),
        "filter": fixed_filter,
        "filter_semantics": {
            "issuer_code": org_code,
            "is_group": "0",
            "filter_type_code": "1",
            "interbank_depo": "1",
            "expire_date": "> system_date OR NULL; filtered by REST before aggregation",
            "allowed_types": BOND_ISSUER_ALLOWED_TYPES,
        },
        "raw_count": len(raw_rows),
        "fallback_reason": response.get("_error", "") if not rows else "",
    }


def shift_years(value: dt.date, years: int) -> dt.date:
    """Shift a date by calendar years without failing on February 29."""
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, month=2, day=28)


def empty_solvency_dataset(
    report: str,
    fields: List[str],
    reason: str,
    filter_str: str = "",
    **metadata: Any,
) -> Dict[str, Any]:
    """Return an explicit empty fallback without guessing an unverified endpoint."""
    data: Dict[str, Any] = {
        "report": report,
        "rows": [],
        "count": 0,
        "fields": fields,
        "filter": filter_str,
        "fallback_reason": reason,
    }
    data.update(metadata)
    return data


def fetch_solvency_table(
    report: str, org_code: str, fields: List[str],
) -> Dict[str, Any]:
    """Fetch a verified, bounded one-page table without mixing block fields."""
    org_code = normalize_org_code(org_code)
    filter_str = '(ORG_CODE="%s")' % org_code
    response = api_any(
        report, filter_str, prefer="choice", columns="ALL",
        page=1, page_size=200, source="choice",
    )
    raw = response.get("raw") or {}
    code = raw.get("code")
    error = response.get("_error", "")
    if code not in (None, 0, "0", 9201, "9201"):
        error = "%s: %s" % (code, raw.get("message", "REST request failed"))
    if raw.get("success") is False and code not in (9201, "9201"):
        error = error or str(raw.get("message") or "REST request failed")
    raw_rows = response.get("rows", [])
    if any(str(row.get("ORG_CODE", "")) != org_code for row in raw_rows):
        error = "REST 返回主体与请求机构代码不匹配"
    if response.get("count", len(raw_rows)) > len(raw_rows):
        error = "REST 返回分页未完整，不能作为完整数据集"
    if error:
        return empty_solvency_dataset(report, fields, error, filter_str, status="failed")
    rows = subset_rows(raw_rows, fields)
    return {
        "report": report, "rows": rows, "count": len(rows),
        "fields": fields, "filter": filter_str,
        "status": "ok" if rows else "empty", "fallback_reason": "",
    }


def fetch_solvency_financial_key_metrics(org_code: str) -> Dict[str, Any]:
    return fetch_solvency_table(
        "RPT_CUSTOM_AIONEPAPER_FINANCE", org_code,
        SOLVENCY_FINANCIAL_KEY_METRICS_FIELDS,
    )


def normalize_credit_analysis_rows(
    rows: Iterable[Dict[str, Any]],
    org_code: str,
) -> List[Dict[str, Any]]:
    """Normalize the verified credit-analysis REST aliases for local prompts.

    The MQL credit-analysis report exposes rating fields by their runtime display
    names, while RPT_CUSTOM_ORG_CREDITANALYSIS returns the corresponding
    issuer-analysis aliases. Keep the raw aliases and add the local canonical
    names so both MQL and REST-fallback packages have the same shape.
    """
    normalized: List[Dict[str, Any]] = []
    alias_map = {
        "ISSUERRATES": "RATING",
        "ISSUERRATEFWS": "RATING_EXPECT",
        "ISSUERRATECWS": "DIRECTION",
    }
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        for source, target in alias_map.items():
            if not has_non_empty_value(item.get(target)) and source in item:
                item[target] = item.get(source)
        if not has_non_empty_value(item.get("ORG_CODE")):
            item["ORG_CODE"] = org_code
        if (
            not has_non_empty_value(item.get("ORG_CODE_FXR"))
            and has_non_empty_value(item.get("ORG_CODE"))
        ):
            item["ORG_CODE_FXR"] = "%s.FXR" % item["ORG_CODE"]
        normalized.append(item)
    return normalized


def fetch_credit_analysis(org_code: str, today: dt.date) -> Dict[str, Any]:
    """Fetch the dedicated credit-analysis table for the local fallback."""
    filter_str = '(ORG_CODE="%s")(END_DATE<=\'%s\')' % (
        org_code,
        today.isoformat(),
    )
    response = api_any(
        "RPT_CUSTOM_ORG_CREDITANALYSIS",
        filter_str,
        prefer="choice",
        columns="ALL",
        sort_columns="REPORT_DATE",
        sort_types="-1",
        page=1,
        page_size=200,
        source="choice",
    )
    raw = response.get("raw") or {}
    code = raw.get("code")
    if response.get("_error") or code not in (None, 0, "0", 9201, "9201"):
        raise RuntimeError(str(response.get("_error") or raw.get("message") or code))
    if raw.get("success") is False and code not in (9201, "9201"):
        raise RuntimeError(str(raw.get("message") or "REST request failed"))
    rows = normalize_credit_analysis_rows(response.get("rows", []), org_code)
    return {
        "report": "RPT_CUSTOM_ORG_CREDITANALYSIS",
        "rows": rows,
        "count": len(rows),
        "fields": CREDIT_ANALYSIS_FIELDS,
        "filter": filter_str,
        "as_of_date": today.isoformat(),
        "status": "ok" if rows else "empty",
        "fallback_reason": (
            ""
            if rows
            else ""
        ),
    }


def fetch_solvency_credit_analysis(org_code: str) -> Dict[str, Any]:
    result = fetch_credit_analysis(org_code, dt.date.today())
    result["rows"] = subset_rows(result.get("rows", []), SOLVENCY_CREDIT_ANALYSIS_FIELDS)
    result["fields"] = SOLVENCY_CREDIT_ANALYSIS_FIELDS
    return result


def fetch_solvency_liability_structure(org_code: str) -> Dict[str, Any]:
    return fetch_solvency_table(
        "RPT_CUSTOM_AIONEPAPER_DEBT", org_code,
        SOLVENCY_LIABILITY_STRUCTURE_FIELDS,
    )


def fetch_solvency_issue_end_statistics(org_code: str, today: dt.date) -> Dict[str, Any]:
    window_start = shift_years(today, -2)
    window_end = shift_years(today, 1)
    excluded_bond_types = [
        "利率债",
        "同业存单",
        "可转债",
        "资产支持债券",
        "可交换债券",
        "境外债",
    ]
    return empty_solvency_dataset(
        "RPT_CUSTOM_BOND_ISSUEEND_IS_C",
        [],
        "MQL 已发现季度参数，但执行时到期年份日期解析失败，且未暴露六类债券排除参数及发行额；完整同口径 REST 尚未验证。",
        'ORG_CODE="%s"; 日期=%s至%s；按季度；债券类型排除=%s'
        % (
            org_code,
            window_start.isoformat(),
            window_end.isoformat(),
            "、".join(excluded_bond_types),
        ),
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        frequency="quarter",
        exclude_bond_types=excluded_bond_types,
        fields_status="元数据已发现，季度日期解析及债券排除口径待验证",
    )


def fetch_issuance_overview(org_code: str, today: dt.date) -> Dict[str, Any]:
    r = api_any(
        "RPT_CUSTOM_BOND_BS_SAMEISSUER",
        '(SECUCODE_RN=1)(ISSUE_CODE="%s")(IS_GROUP="0")(EXPIRE_DATE>=\'%s\')' % (org_code, today.isoformat()),
        prefer="choice",
        columns="SECUCODE,BOND_NAME_ABBR,SECURITY_TYPE,CURRENT_BALANCE,CURRENCY,ISSUE_DATE,EXPIRE_DATE,REMAIN_DAY,BOND_RATING,CREDIT_RATING,FXCKLL,CREDIT_SUBJECT_NAME,GROUP_NAME,SECUCODE_RN",
        sort_columns="ISSUE_DATE",
        sort_types="-1",
        page=1,
        page_size=100,
        source="choice",
    )
    rows = filter_issuance_overview_rows(r.get("rows", []), today)
    query_error = r.get("_error")
    status = "failed" if query_error else ("ok" if rows else "empty")
    return {
        "report": "RPT_CUSTOM_BOND_BS_SAMEISSUER",
        "rows": rows,
        "count": len(rows),
        "status": status,
        # None means the query failed; it must not be treated as an empty
        # active-bond result when deciding whether to remove report sections.
        "has_active_bonds": None if query_error else bool(rows),
        "as_of_date": today.isoformat(),
        "filter_semantics": {
            "deduplicate_cross_market": "SECUCODE_RN=1",
            "unmatured_only": "EXPIRE_DATE >= system_date",
            "exclude_interbank_deposit": "SECURITY_TYPE/BOND_NAME_ABBR excludes 同业存单; INTERBANK_DEPO value not assumed",
            "issuer_scope": "IS_GROUP=0",
        },
        "fallback_reason": query_error or "",
    }


def fetch_issuer_curve(org_code: str, today: dt.date) -> Dict[str, Any]:
    """Do not call the fit endpoint without verified sample-point inputs."""
    return {
        "report": "RPT_BOND_ISSUERCURVE",
        "rows": [],
        "count": 0,
        "status": "failed",
        "org_code": org_code,
        "as_of_date": today.isoformat(),
        "fallback_reason": "拟合需要样本期限、收益率、类型序列；样本关系及全市场补点链路尚未通过，禁止直接按 ORG_CODE 调用拟合函数。",
    }


def summarize_issuer_bond_types(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep one representative row per three-level bond type."""
    options: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        key = str(row.get("EMBOND_3LEVEL_CODE") or row.get("EMBOND_3LEVEL") or "").strip()
        if not key:
            continue
        options.setdefault(key, row)
    return list(options.values())


def fetch_issuer_bond_types(org_code: str, today: dt.date) -> Dict[str, Any]:
    r = api_any(
        "RPT_BOND_ISSUERCURVE_LIKEBOND",
        '(ORG_CODE="%s")' % org_code,
        prefer="choice",
        columns=",".join(ISSUER_BOND_TYPE_FIELDS),
        sort_columns="EMBOND_3LEVEL_CODE,EXPIRE_DATE",
        sort_types="1,-1",
        page=1,
        page_size=200,
        source="choice",
    )
    rows = subset_rows(r.get("rows", []), ISSUER_BOND_TYPE_FIELDS)
    return {
        "report": "RPT_BOND_ISSUERCURVE_LIKEBOND",
        "rows": rows,
        "type_options": summarize_issuer_bond_types(rows),
        "count": len(rows),
        "as_of_date": today.isoformat(),
        "filter": '(ORG_CODE="%s")' % org_code,
        "fallback_reason": r.get("_error", "") if not rows else "",
    }


def empty_market_context(today: dt.date) -> Dict[str, Any]:
    """No unverified REST endpoint may fabricate macro market numbers."""
    return {
        "report": "MQL Search_Context pending: pricing_market_context",
        "rows": [],
        "count": 0,
        "as_of_date": today.isoformat(),
        "fields": MARKET_CONTEXT_FIELDS,
        "fallback_reason": "未确认可用的本地 REST 市场数据报表；禁止补造 DR007、R007、OMO 或 MLF 数值",
    }


def _row_date(row: Dict[str, Any]) -> Optional[str]:
    # StartDate/EndDate bound the query; TDATE is the outstanding-bond cutoff.
    for key in ("交易日期", "TRADE_DATE", "END_DATE", "DATA_DATE", "DATE"):
        value = norm_date(row.get(key))
        if value:
            return value
    return None


def _row_has_margin_value(row: Dict[str, Any]) -> bool:
    for key in ("地区利差(BP)", "主体利差(BP)", "MARGIN", "MARGIN_BP", "SPREAD", "SPREAD_BP"):
        value = row.get(key)
        if value not in (None, ""):
            return True
    return False


def keep_monthly_last_valid(rows: Iterable[Dict[str, Any]], today: dt.date) -> List[Dict[str, Any]]:
    start = shift_years(today, -1)
    dated_rows = []
    for row in rows or []:
        row_date = _row_date(row)
        if not row_date or row_date < start.isoformat() or row_date > today.isoformat():
            continue
        if not _row_has_margin_value(row):
            continue
        dated_rows.append((row_date, row))
    if not dated_rows:
        return []
    monthly: Dict[str, Any] = {}
    for row_date, row in dated_rows:
        month = row_date[:7]
        if month not in monthly or row_date > monthly[month][0]:
            monthly[month] = (row_date, row)
    selected = [item[1] for item in sorted(monthly.values(), key=lambda item: item[0])]
    latest = max(dated_rows, key=lambda item: item[0])[1]
    if latest not in selected:
        selected.append(latest)
    return selected


def fetch_urban_region_compare(org_code: str, today: dt.date, province_name: str = "") -> Dict[str, Any]:
    r = api_any(
        "RPT_CUSTOM_DEBTREMOVE_REGION_COMPARE",
        "(END_DATE<='%s')" % today.isoformat(),
        prefer="choice",
        columns="ALL",
        sort_columns="END_DATE",
        sort_types="-1",
        page=1,
        page_size=200,
        source="choice",
    )
    rows = r.get("rows", [])
    if province_name:
        province_rows = [
            row for row in rows
            if str(row.get("AREA_NAME") or row.get("区域名称") or "").strip() == province_name.strip()
        ]
        if province_rows:
            rows = province_rows
    return {
        "report": "RPT_CUSTOM_DEBTREMOVE_REGION_COMPARE",
        "rows": rows,
        "count": len(rows),
        "as_of_date": today.isoformat(),
        "province_name": province_name,
        "fallback_reason": r.get("_error", "") if not rows else "",
    }


def fetch_urban_margin_analysis_ts(org_code: str, today: dt.date) -> Dict[str, Any]:
    return {
        "report": "RPT_CUSTOM_DEBTREMOVE_MARGIN_ANALYSIS_TS",
        "rows": [],
        "count": 0,
        "as_of_date": today.isoformat(),
        "window": "%s~%s" % ((today - dt.timedelta(days=366)).isoformat(), today.isoformat()),
        "fallback_reason": "AREA_TYPE 与 AREA_CODE 的实际枚举和值尚未由 Search_Context 核对，禁止猜测区域利差筛选条件",
    }


def fetch_urban_issuer_margin(
    org_code: str, today: dt.date, bond_cutoff_date: Optional[dt.date] = None,
) -> Dict[str, Any]:
    start = shift_years(today, -1)
    filter_str = '(ORG_CODE="%s")(StartDate=\'%s\')(EndDate=\'%s\')' % (
        org_code, start.isoformat(), today.isoformat(),
    )
    if bond_cutoff_date is not None:
        filter_str += "(TDATE='%s')" % bond_cutoff_date.isoformat()
    r = api_any(
        "RPT_BOND_ISMARGIN_ORGM",
        filter_str,
        prefer="choice",
        columns="ALL",
        sort_columns="",
        sort_types="",
        page=1,
        page_size=200,
        source="choice",
    )
    raw_rows = r.get("rows", [])
    query_error = r.get("_error", "")
    rows = keep_monthly_last_valid(raw_rows, today) if not query_error else []
    if raw_rows and not rows and not query_error:
        query_error = "主体利差返回记录中没有近12个月内日期和利差均有效的数据，禁止使用未过滤的原始记录"
    return {
        "report": "RPT_BOND_ISMARGIN_ORGM",
        "rows": rows,
        "count": len(rows),
        "status": "failed" if query_error else ("ok" if rows else "empty"),
        "as_of_date": today.isoformat(),
        "filter": filter_str,
        "window": "%s~%s" % (start.isoformat(), today.isoformat()),
        "bond_cutoff_date": bond_cutoff_date.isoformat() if bond_cutoff_date is not None else None,
        "fallback_reason": query_error,
    }


def _first_value(row: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if has_non_empty_value(value):
            return value
    return None


def fetch_sci_tech_rd_exp_emp(org_code: str, secucode: str = "") -> Dict[str, Any]:
    """Best-effort REST fallback for the user-confirmed RPT_ENT_RD_EXP_EMP source."""
    attempts: List[Dict[str, Any]] = []
    filters = ['(ORG_CODE="%s")' % org_code]
    if secucode:
        filters.append('(SECUCODE="%s")' % secucode)

    for filter_str in filters:
        try:
            result = api_any(
                "RPT_ENT_RD_EXP_EMP",
                filter_str,
                prefer="choice",
                columns=None,
                sort_columns="REPORT_DATE",
                sort_types="-1",
                page=1,
                page_size=500,
                source="choice",
            )
            rows = result.get("rows", [])
            attempts.append({"filter": filter_str, "rows": len(rows), "error": result.get("_error", "")})
            if rows:
                normalized: List[Dict[str, Any]] = []
                for row in rows:
                    item = dict(row)
                    item.setdefault("REPORT_DATE", _first_value(row, "REPORT_DATE", "报告期", "报告日期"))
                    item.setdefault("CURRENT_AMT", _first_value(row, "CURRENT_AMT", "项目金额", "研发投入合计", "研发费用"))
                    item.setdefault("RESEARCH_NUM", _first_value(row, "RESEARCH_NUM", "研发人员", "研发人员人数"))
                    item.setdefault("TOTAL_NUM", _first_value(row, "TOTAL_NUM", "职工总数", "员工总数"))
                    item.setdefault("STD_ITEM_NAMENEW", _first_value(row, "STD_ITEM_NAMENEW", "转换后科目名称", "项目"))
                    normalized.append(item)
                return {
                    "report": "RPT_ENT_RD_EXP_EMP",
                    "rows": normalized,
                    "count": len(normalized),
                    "attempts": attempts,
                    "fallback_reason": "",
                }
        except Exception as exc:  # noqa: BLE001
            attempts.append({"filter": filter_str, "rows": 0, "error": repr(exc)})

    return {
        "report": "RPT_ENT_RD_EXP_EMP",
        "rows": [],
        "count": 0,
        "attempts": attempts,
        "fallback_reason": "RPT_ENT_RD_EXP_EMP REST 兜底未返回研发费用与人员数据；不猜测其它函数名",
    }


def empty_sci_tech_dataset(report: str, reason: str) -> Dict[str, Any]:
    return {
        "report": report,
        "rows": [],
        "count": 0,
        "fallback_reason": reason,
    }


JUDICIAL_REPORTS = (
    {
        "key": "dishonest",
        "report": "RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTIONSINFO",
        "date_field": "PUBLISH_DATE",
        "fields": [
            "ORG_NAME",
            "ORG_CODE",
            "TYPE",
            "NUMBER_SUM",
            "NUMBER_SUM_HISTORY",
            "AMOUNT_SUM",
            "AMOUNT_SUM_HISTORY",
        ],
    },
    {
        "key": "executed",
        "report": "RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTEDPERSONS",
        "date_field": "CASE_DATE",
        "fields": [
            "ORG_NAME",
            "ORG_CODE",
            "TYPE",
            "NUMBER_SUM",
            "NUMBER_SUM_HISTORY",
            "AMOUNT_SUM",
            "AMOUNT_SUM_HISTORY",
        ],
    },
    {
        "key": "restricted",
        "report": "RPT_CUSTOM_ENT_JUDICIAL_SUM_RESTRICTEDCONSUMER",
        "date_field": "RELEASE_DATE",
        "fields": [
            "ORG_NAME",
            "ORG_CODE",
            "TYPE",
            "NUMBER_SUM",
            "NUMBER_SUM_HISTORY",
        ],
    },
    {
        "key": "termination",
        "report": "RPT_CUSTOM_ENT_JUDICIAL_SUM_TERMINATIONCASE",
        "date_field": "TERMINATE_DATE",
        "fields": [
            "ORG_NAME",
            "ORG_CODE",
            "TYPE",
            "NUMBER_SUM",
            "NUMBER_SUM_HISTORY",
            "AMOUNT_SUM",
            "AMOUNT_SUM_HISTORY",
            "FAIL_PERFORM_AMOUNT_SUM",
            "FAIL_PERFORM_AMOUNT_SUM_HISTORY",
            "PERFORM_AMOUNT_RATIO",
            "PERFORM_AMOUNT_RATIO_HISTORY",
        ],
    },
)

JUDICIAL_RELATION_TYPES = {
    "1": "本公司",
    "2": "实控人",
    "3": "主要股东",
    "4": "参股控股子公司",
}

JUDICIAL_ASSOCIATE_TYPES = ("实控人", "主要股东", "参股控股子公司")

JUDICIAL_METRICS = {
    "dishonest": (
        ("案件数", "NUMBER_SUM"),
        ("涉案总金额(万元)", "AMOUNT_SUM"),
    ),
    "executed": (
        ("案件数", "NUMBER_SUM"),
        ("执行总金额(万元)", "AMOUNT_SUM"),
    ),
    "restricted": (
        ("案件数", "NUMBER_SUM"),
    ),
    "termination": (
        ("案件数", "NUMBER_SUM"),
        ("执行总金额(万元)", "AMOUNT_SUM"),
        ("未履行总金额(万元)", "FAIL_PERFORM_AMOUNT_SUM"),
        ("未履行比例(%)", "PERFORM_AMOUNT_RATIO"),
    ),
}

JUDICIAL_DATASET_LABELS = {
    "dishonest": "失信被执行人",
    "executed": "被执行人",
    "restricted": "限制高消费",
    "termination": "终本案件",
}


def _first_present(row: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in row and has_non_empty_value(row.get(key)):
            return row.get(key)
    return None


def _canonical_judicial_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize REST aliases while keeping the MQL-facing logical fields."""
    item = dict(row)
    aliases = {
        "ORG_NAME": ("ORG_NAME", "公司名称", "企业名称"),
        "ORG_CODE": ("ORG_CODE", "公司代码", "企业代码"),
        "TYPE": ("TYPE", "关系类型"),
        "NUMBER_SUM": ("NUMBER_SUM", "当前案件数", "案件数"),
        "NUMBER_SUM_HISTORY": (
            "NUMBER_SUM_HISTORY",
            "NUMBER_SUM_ HISTORY",
            "历史案件数",
        ),
        "AMOUNT_SUM": (
            "AMOUNT_SUM",
            "AMOUNT _SUM",
            "当前执行标的（万元）",
            "当前执行标的(万元)",
            "当前执行总金额（万元）",
            "当前执行总金额(万元)",
            "涉案总金额（万元）",
            "涉案总金额(万元)",
            "执行总金额（万元）",
            "执行总金额(万元)",
        ),
        "AMOUNT_SUM_HISTORY": (
            "AMOUNT_SUM_HISTORY",
            "AMOUNT _SUM_HISTORY",
            "AMOUNT_SUM_ HISTORY",
            "历史执行标的（万元）",
            "历史执行标的(万元)",
            "历史执行总金额（万元）",
            "历史执行总金额(万元)",
            "历史涉案总金额（万元）",
            "历史涉案总金额(万元)",
            "历史执行金额（万元）",
            "历史执行金额(万元)",
        ),
        "FAIL_PERFORM_AMOUNT_SUM": (
            "FAIL_PERFORM_AMOUNT_SUM",
            "FAIL_PERFORM_AMOUNT _SUM",
            "当前未履行总金额（万元）",
            "当前未履行总金额(万元)",
        ),
        "FAIL_PERFORM_AMOUNT_SUM_HISTORY": (
            "FAIL_PERFORM_AMOUNT_SUM_HISTORY",
            "FAIL_PERFORM_AMOUNT _SUM_HISTORY",
            "FAIL_PERFORM_AMOUNT_SUM_ HISTORY",
            "历史未履行总金额（万元）",
            "历史未履行总金额(万元)",
        ),
        "PERFORM_AMOUNT_RATIO": (
            "PERFORM_AMOUNT_RATIO",
            "当前未履行比例（%）",
            "当前未履行比例(%)",
            "未履行比例（%）",
            "未履行比例(%)",
        ),
        "PERFORM_AMOUNT_RATIO_HISTORY": (
            "PERFORM_AMOUNT_RATIO_HISTORY",
            "PERFORM_AMOUNT_RATIO_ HISTORY",
            "历史未履行比例（%）",
            "历史未履行比例(%)",
        ),
    }
    for canonical, candidates in aliases.items():
        if not has_non_empty_value(item.get(canonical)):
            value = _first_present(item, candidates)
            if value is not None:
                item[canonical] = value
    return item


def _empty_judicial_period() -> Dict[str, Any]:
    metrics = {
        JUDICIAL_DATASET_LABELS[key]: {
            metric: None
            for metric, _ in JUDICIAL_METRICS[key]
        }
        for key in JUDICIAL_METRICS
    }
    return {
        "本公司": {label: dict(values) for label, values in metrics.items()},
        "关联方": {
            relation: {
                label: dict(values)
                for label, values in metrics.items()
            }
            for relation in JUDICIAL_ASSOCIATE_TYPES
        },
    }


def _period_value(row: Dict[str, Any], field: str, period: str) -> Any:
    if period == "history":
        history_field = "%s_HISTORY" % field
        value = row.get(history_field)
        if has_non_empty_value(value):
            return value
    return row.get(field)


def _combine_judicial_values(values: Iterable[Any], ratio: bool = False) -> Any:
    present = [value for value in values if has_non_empty_value(value)]
    if not present:
        return None
    if ratio:
        return present[0]
    if len(present) == 1:
        return present[0]
    numbers = [parse_number(value) for value in present]
    if all(number is not None for number in numbers):
        return sum(numbers)
    return present[0]


def _summarize_judicial_rows(
    rows: Iterable[Dict[str, Any]],
    report_key: str,
    period: str,
) -> Dict[str, Any]:
    summary = _empty_judicial_period()
    values: Dict[str, Dict[str, Dict[str, List[Any]]]] = {}
    for row in rows or []:
        relation_type = str(row.get("TYPE") or "").strip()
        relation = JUDICIAL_RELATION_TYPES.get(relation_type)
        if not relation:
            continue
        target = summary["本公司"] if relation == "本公司" else summary["关联方"][relation]
        relation_values = values.setdefault(relation, {})
        for metric, field in JUDICIAL_METRICS[report_key]:
            metric_values = relation_values.setdefault(metric, [])
            metric_values.append(
                _period_value(row, field, period)
            )
            target[JUDICIAL_DATASET_LABELS[report_key]][metric] = _combine_judicial_values(
                metric_values,
                ratio=field == "PERFORM_AMOUNT_RATIO",
            )
    return summary


def _judicial_filter(
    org_code: str,
    is_history: str,
    relation_type: str,
) -> str:
    # The judicial report APIs are reliable with one TYPE value per request;
    # do not rely on IN or an omitted TYPE filter to retrieve all relations.
    return (
        '(ORG_CODE="%s")(TYPE="%s")(IS_HISTORY="%s")'
        % (org_code, relation_type, is_history)
    )


def _count_judicial_rows(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    if isinstance(value.get("total_rows"), int):
        return value["total_rows"]
    if isinstance(value.get("rows"), list):
        return len(value["rows"])
    if isinstance(value.get("datasets"), dict):
        return sum(_count_judicial_rows(item) for item in value["datasets"].values())
    if isinstance(value.get("periods"), dict):
        return sum(_count_judicial_rows(item) for item in value["periods"].values())
    return 0


def fetch_judicial(
    org_code: str,
    today: dt.date,
) -> Dict[str, Any]:
    """Fetch only the four user-specified judicial summary reports.

    Each report is queried once for current records and once for historical
    records. No holding-ratio, date-window, supplementary-table, punishment,
    or equity-freeze query is added here.
    """
    out: Dict[str, Any] = {
        "report": "judicial_four_summary_reports",
        "org_code": org_code,
        "as_of_date": today.isoformat(),
        "relationship_types": dict(JUDICIAL_RELATION_TYPES),
        "query_scope": {
            "current": 'IS_HISTORY="0"',
            "history": 'IS_HISTORY="1"',
            "type": 'TYPE="1"/"2"/"3"/"4" queried separately',
            "holding_ratio_filter": False,
            "date_filter": False,
        },
        "current": _empty_judicial_period(),
        "history": _empty_judicial_period(),
        "datasets": {},
        "errors": {},
        "total_rows": 0,
    }

    for spec in JUDICIAL_REPORTS:
        key = spec["key"]
        report = spec["report"]
        fields = list(spec["fields"])
        dataset: Dict[str, Any] = {
            "report": report,
            "date_field": spec["date_field"],
            "fields": fields,
            "periods": {},
        }
        for period, is_history in (("current", "0"), ("history", "1")):
            filter_str = (
                'TYPE=1/2/3/4 each queried separately; IS_HISTORY="%s"'
                % is_history
            )
            period_result: Dict[str, Any] = {
                "filter": filter_str,
                "rows": [],
                "count": 0,
                "summary": _empty_judicial_period(),
            }
            try:
                rows = []
                errors = []
                for relation_type in ("1", "2", "3", "4"):
                    response = api_any(
                        report,
                        _judicial_filter(org_code, is_history, relation_type),
                        prefer="choice",
                        columns=",".join(fields),
                        page=1,
                        page_size=200,
                        source="choice",
                    )
                    if response.get("_error"):
                        errors.append(
                            "TYPE=%s: %s" % (relation_type, response["_error"])
                        )
                    rows.extend(
                        _canonical_judicial_row(row)
                        for row in response.get("rows", [])
                        if isinstance(row, dict)
                    )
                if errors and not rows:
                    period_result["error"] = "; ".join(errors)
                rows = subset_rows(rows, fields)
                unique_rows = []
                seen_rows = set()
                for row in rows:
                    row_key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
                    if row_key not in seen_rows:
                        seen_rows.add(row_key)
                        unique_rows.append(row)
                rows = unique_rows
                period_result["rows"] = rows
                period_result["count"] = len(rows)
                period_result["summary"] = _summarize_judicial_rows(
                    rows,
                    key,
                    period,
                )
                if period_result.get("error"):
                    out["errors"]["%s_%s" % (key, period)] = period_result["error"]
            except Exception as exc:  # noqa: BLE001
                period_result["error"] = repr(exc)
                out["errors"]["%s_%s" % (key, period)] = repr(exc)
            dataset["periods"][period] = period_result
            out["total_rows"] += period_result["count"]

            summary = period_result["summary"]
            dataset_label = JUDICIAL_DATASET_LABELS[key]
            out[period]["本公司"][dataset_label].update(
                summary["本公司"][dataset_label]
            )
            for relation in JUDICIAL_ASSOCIATE_TYPES:
                out[period]["关联方"][relation][dataset_label].update(
                    summary["关联方"][relation][dataset_label]
                )

        out["datasets"][key] = dataset

    out["status"] = "ok" if out["total_rows"] else "empty"
    return out


def make_source(source_id: int, dataset: str, path: str, status: str, rows: int, notes: str = "", placeholder: str = "{{数据}}") -> Dict[str, Any]:
    source = {
        "source_id": source_id,
        "placeholder": placeholder,
        "dataset": dataset,
        "path": path,
        "status": status,
        "rows": rows,
        "notes": notes,
    }
    if path == "Python REST":
        source["path"] = "Python REST fallback"
        source["fallback_from"] = "MQL"
        if status in ("ok", "empty"):
            source["status"] = "fallback"
            source["fallback_result_status"] = status
    return source


def route_blocks(flags: Dict[str, Any]) -> List[str]:
    if flags.get("status") == "failed" or (
        "is_bond_issuer" in flags and flags["is_bond_issuer"] is None
    ):
        raise RuntimeError("企业类型判定未完成，停止报告生成；请检查发债人专项数据源。")
    blocks = ["基本情况", "股东情况", "所处行业", "经营状况"]
    if flags.get("is_esg_scope"):
        blocks.append("ESG分析")

    # A successful issuance query with no active rows means that all bonds
    # are matured (or there is no in-scope bond). In either case, the
    # issuance-overview and solvency chapters have no usable bond data. Keep
    # the chapters when the query failed, so a transport failure is not
    # silently converted into a business conclusion.
    has_active_bonds = flags.get("has_active_bonds")
    lifecycle_blocks = ["发行概述", "偿债分析"] if has_active_bonds is not False else []

    if flags.get("is_urban_investment"):
        blocks.extend(["财务状况（债券发行人）", *lifecycle_blocks[:1], "定价分析（城投）", *lifecycle_blocks[1:]])
    else:
        if flags.get("is_sci_tech"):
            blocks.append("科创能力")
        if flags.get("is_bond_issuer"):
            blocks.extend(["财务状况（债券发行人）", *lifecycle_blocks[:1], "定价分析（债券发行人）", *lifecycle_blocks[1:]])
        else:
            blocks.append("财务状况")

    blocks.extend(["信用分析", "司法风险", "重点关注"])
    return blocks


def subset_rows(rows: Iterable[Dict[str, Any]], fields: Iterable[str]) -> List[Dict[str, Any]]:
    field_list = list(fields)
    clean_rows: List[Dict[str, Any]] = []
    for row in rows or []:
        clean_rows.append({field: row.get(field) for field in field_list if field in row})
    return clean_rows


def dedupe_rows(rows: Iterable[Dict[str, Any]], fields: Iterable[str]) -> List[Dict[str, Any]]:
    """Remove duplicate records returned by overlapping entity probes."""
    field_list = list(fields)
    output: List[Dict[str, Any]] = []
    seen = set()
    for row in rows or []:
        item = {field: row.get(field) for field in field_list if field in row}
        try:
            marker = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError):
            marker = repr(sorted(item.items()))
        if marker in seen:
            continue
        seen.add(marker)
        output.append(item)
    return output


SHAREHOLDER_EQUITY_FIELDS = [
    "HOLDER_NAME_DOWN",
    "HOLDER_NAME_UP",
    "HOLDER_RATIO_ DOWN",
    "HOLDER_RATIO_UP",
    "ORG_CODE",
    "REPORT_DATE",
    "SJKZR",
    "TOP1_HOLDER_ST",
]

SHAREHOLDER_TOP_HOLDER_FIELDS = [
    "RANK",
    "HOLDER_NAME",
    "HOLD_NUM",
    "HOLD_RATIO",
    "HOLDER_IS_ISSUER",
]

SHAREHOLDER_CHART_FIELDS = [
    "HOLDER_NAME",
    "HOLD_NUM",
    "HOLD_RATIO",
    "HOLDER_IS_ISSUER",
]

RELATED_TRANSACTION_FIELDS = [
    "NOTICE_DATE",
    "RELATED_PARTY",
    "TRADE_WAY",
    "RELATED_RELATION",
    "IS_CONTROL",
    "TRADE_AMT",
    "CURRENCY",
    "TRADE_PROFILE",
]


def normalize_shareholder_equity_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Align the REST alias with the confirmed MQL column name."""
    normalized: List[Dict[str, Any]] = []
    for row in rows or []:
        item = dict(row)
        if (
            "HOLDER_RATIO_ DOWN" not in item
            and "HOLDER_RATIO_DOWN" in item
        ):
            item["HOLDER_RATIO_ DOWN"] = item.get("HOLDER_RATIO_DOWN")
        normalized.append(item)
    return normalized


def shareholder_equity_package(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return subset_rows(normalize_shareholder_equity_rows(rows), SHAREHOLDER_EQUITY_FIELDS)


def shareholder_top_holder_package(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Project top holders and move the source-provided aggregate to the end."""
    ranked = []
    aggregate = None
    for row in rows or []:
        item = dict(row)
        issuer_flag = next(
            (
                item.get(key)
                for key in (
                    "HOLDER_IS_ISSUER",
                    "IS_ISSUER",
                    "股东是否为发行人",
                )
                if item.get(key) not in (None, "")
            ),
            None,
        )
        item["HOLDER_IS_ISSUER"] = "是" if str(issuer_flag) == "1" else (issuer_flag or "-")
        rank_value = parse_number(row.get("RANK"))
        if rank_value is None or rank_value != int(rank_value):
            continue
        rank = int(rank_value)
        if 1 <= rank <= 10:
            ranked.append((rank, item))
        elif rank == 9999:
            aggregate = item
    ranked.sort(key=lambda item: item[0])
    output = [dict(row) for _, row in ranked]
    if aggregate is not None:
        aggregate["HOLDER_NAME"] = "合计"
        aggregate["HOLDER_IS_ISSUER"] = "-"
        output.append(aggregate)
    return subset_rows(output, SHAREHOLDER_CHART_FIELDS)


def related_transaction_package(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return subset_rows(rows, RELATED_TRANSACTION_FIELDS)


def solvency_shareholder_package(shareholder_data: Dict[str, Any]) -> Dict[str, Any]:
    raw_rows = shareholder_data.get("holder_equity")
    if raw_rows is None:
        raw_rows = shareholder_data.get("rows", [])
    rows = subset_rows(
        normalize_shareholder_equity_rows(
            raw_rows
        ),
        SOLVENCY_SHAREHOLDER_FIELDS,
    )
    return {
        "latest_report_date": shareholder_data.get("latest_report_date"),
        "rows": rows,
        "fields": SOLVENCY_SHAREHOLDER_FIELDS,
        "fallback_reason": (
            "仅保留股东情况数据中的实控人 SJKZR 和第一大股东 TOP1_HOLDER_ST"
            if rows
            else "股东情况数据为空，偿债分析不复制其它股东或关联交易字段"
        ),
    }


def get_source(result: Dict[str, Any], source_ids: Dict[str, int], key: str, block: str) -> Dict[str, Any]:
    source_id = source_ids.get(key)
    for source in result.get("sources", []):
        if source.get("source_id") == source_id:
            copied = dict(source)
            copied["block"] = block
            return copied
    return {
        "source_id": source_id or 0,
        "block": block,
        "path": "Python REST fallback",
        "dataset": key,
        "status": "failed",
        "rows": 0,
        "notes": "source not found",
    }


def make_dataset(
    result: Dict[str, Any],
    key: str,
    dataset_name: str,
    fields: List[str],
    filter_str: str,
    data: Any,
) -> Dict[str, Any]:
    return {
        "dataset_key": key,
        "dataset": dataset_name,
        "query_path": "Python REST fallback",
        "fallback_from": "MQL",
        "fields": fields,
        "filter": filter_str,
        "data": data,
        "error": result.get("errors", {}).get(key, ""),
    }


def make_local_analysis_dataset(
    key: str,
    dataset_name: str,
    fields: List[str],
    filter_str: str,
    data: Any,
) -> Dict[str, Any]:
    """Create a non-MQL handoff dataset for already generated analysis text."""
    return {
        "dataset_key": key,
        "dataset": dataset_name,
        "query_path": "local analysis handoff",
        "fields": fields,
        "filter": filter_str,
        "data": data,
        "error": "",
    }


PROMPT_INTERNAL_KEYS = {
    "dataset_key",
    "dataset",
    "report",
    "mql_report",
    "mql_report_path",
    "fields",
    "filter",
    "filter_semantics",
    "query_path",
    "fallback_from",
    "fallback_reason",
    "error",
    "source",
    "sources",
    "status",
    "path",
    "prompt_file",
    "block_name",
}


def prompt_data_projection(value: Any) -> Any:
    """Remove implementation metadata before data reaches a block prompt."""
    if isinstance(value, dict):
        return {
            key: prompt_data_projection(item)
            for key, item in value.items()
            if key not in PROMPT_INTERNAL_KEYS
        }
    if isinstance(value, list):
        return [prompt_data_projection(item) for item in value]
    return value


def build_key_concerns_context(
    result: Dict[str, Any],
    analysis_results: Any = None,
) -> Dict[str, Any]:
    """Build the only input allowed for the key-concerns prompt.

    This function reads no raw dataset for analysis. It only uses the basic
    entity name as prompt metadata, receives generated block analyses, and
    preserves the fixed 14-slot route shape.
    """
    selected_blocks = result.get("selected_blocks", [])
    if analysis_results is None:
        analysis_results = result.get("analysis_results", {})
    normalized = normalize_analysis_handoff(analysis_results, selected_blocks)
    content_by_block = {
        block: normalized[block]["content"]
        for block in PREVIOUS_ANALYSIS_BLOCKS
    }
    prompt_inputs = {
        "企业名称": (
            one(result.get("datasets", {}).get("basic_info", {}).get("rows", []))
            or {}
        ).get("ORG_NAME")
        or result.get("org_name")
        or ""
    }
    for block, placeholder in KEY_CONCERNS_PROMPT_INPUTS.items():
        prompt_inputs[placeholder] = content_by_block[block]

    active_blocks = [
        block
        for block in PREVIOUS_ANALYSIS_BLOCKS
        if content_by_block[block]
    ]
    empty_blocks = [
        block
        for block in PREVIOUS_ANALYSIS_BLOCKS
        if not content_by_block[block]
    ]
    return {
        "analysis_results": content_by_block,
        "prompt_inputs": prompt_inputs,
        "active_blocks": active_blocks,
        "empty_blocks": empty_blocks,
        "selected_previous_blocks": [
            block
            for block in PREVIOUS_ANALYSIS_BLOCKS
            if block in set(selected_blocks)
        ],
        "input_rule": (
            "仅使用前 14 个板块已经生成的分析正文；"
            "未被企业类型路由选择或没有生成正文的板块传入空字符串；"
            "不读取、不传入任何原始 MQL/Python 数据表，不发起新的 MQL 或资讯查询。"
        ),
    }


def block_dataset_specs(
    result: Dict[str, Any],
    block: str,
    analysis_results: Any = None,
) -> List[Dict[str, Any]]:
    org_code = str(result.get("org_code") or "")
    datasets = result.get("datasets", {})
    basic_rows = datasets.get("basic_info", {}).get("rows", [])
    shareholder_data = datasets.get("shareholders", {})
    operation_data = datasets.get("operation", {})
    financial_rows = datasets.get("financial_summary", {}).get("rows", [])
    credit_rows = datasets.get("credit_analysis", {}).get("rows", [])
    bond_rows = datasets.get("bonds", {}).get("rows", [])
    issuance_rows = datasets.get("issuance_overview", {}).get("rows", [])
    issuer_curve_data = datasets.get("pricing_issuer_curve", {})
    issuer_bond_type_data = datasets.get("pricing_issuer_bond_types", {})
    market_context_data = datasets.get("pricing_market_context", {})
    urban_region_data = datasets.get("pricing_urban_region_compare", {})
    urban_margin_data = datasets.get("pricing_urban_margin_analysis_ts", {})
    urban_issuer_margin_data = datasets.get("pricing_urban_issuer_margin", {})
    sci_tech_profile_data = datasets.get("sci_tech_profile", {})
    sci_tech_property_summary_data = datasets.get("sci_tech_property_summary", {})
    sci_tech_property_yearly_data = datasets.get("sci_tech_property_yearly", {})
    sci_tech_patent_data = datasets.get("sci_tech_patent_distribution", {})
    sci_tech_trademark_data = datasets.get("sci_tech_trademark_distribution", {})
    sci_tech_rd_data = datasets.get("sci_tech_rd_exp_emp", {})
    sci_tech_titles_data = datasets.get("sci_tech_titles", {})
    sci_tech_industry_data = datasets.get("sci_tech_industry", {})
    solvency_financial_key_metrics_data = datasets.get("solvency_financial_key_metrics", {})
    solvency_credit_analysis_data = datasets.get("solvency_credit_analysis", {})
    solvency_liability_structure_data = datasets.get("solvency_liability_structure", {})
    solvency_issue_end_data = datasets.get("solvency_issue_end_statistics", {})
    solvency_shareholder_data = datasets.get("solvency_shareholder", {})
    credit_analysis_data = datasets.get("credit_analysis", {})

    basic_filter = '(ORG_CODE="%s")' % org_code
    financial_report = datasets.get("financial_summary", {}).get("report", "financial_summary")
    market = datasets.get("financial_summary", {}).get("market", "")
    financial_data = normalize_financial_summary_rows(financial_rows)

    if block == "基本情况":
        return [make_dataset(result, "basic_info", "RPT_COP_ORG_INFO", BASIC_INFO_FIELDS, basic_filter, subset_rows(basic_rows, BASIC_INFO_FIELDS))]
    if block == "股东情况":
        related_window = shareholder_data.get("related_window", "")
        related_start, related_end = ("", "")
        if "~" in related_window:
            related_start, related_end = related_window.split("~", 1)
        return [
            make_dataset(
                result,
                "shareholders_top_holders",
                "RPT_BOND_GQJG_ISHOLDER",
                SHAREHOLDER_TOP_HOLDER_FIELDS,
                '(ISSUE_CODE="%s")(END_DATE="%s")(IS_SHOW=1)；结果整理保留 RANK=1..10 或 RANK=9999' % (
                    org_code,
                    shareholder_data.get("latest_report_date") or "最新报告期",
                ),
                {
                    "report_date": shareholder_data.get("latest_report_date"),
                    "rows": shareholder_top_holder_package(
                        shareholder_data.get("top_holders", []),
                    ),
                },
            ),
            make_dataset(
                result,
                "shareholders_equity",
                "RPT_CUSTOM_ORG_SHAREHOLDER_EQUITY",
                SHAREHOLDER_EQUITY_FIELDS,
                '(ORG_CODE="%s")(END_DATE<=当前日期；最新报告期)' % org_code,
                shareholder_equity_package(shareholder_data.get("holder_equity", [])),
            ),
            make_dataset(
                result,
                "related_transactions",
                "RPT_RELATED_TRANSACTION",
                RELATED_TRANSACTION_FIELDS,
                '(ORG_CODE="%s")(NOTICE_DATE在%s至%s)' % (
                    org_code,
                    related_start,
                    related_end,
                ),
                related_transaction_package(shareholder_data.get("related_transactions", [])),
            ),
        ]
    if block == "所处行业":
        return [make_dataset(result, "basic_info", "RPT_COP_ORG_INFO", INDUSTRY_FIELDS, basic_filter, subset_rows(basic_rows, INDUSTRY_FIELDS))]
    if block == "经营状况":
        if operation_data.get("report") == "RPT_ORGF9_FN_MAINOPBUSINESS":
            operation_fields = [
                "ACT_REPORT_NAME", "BELONG_TYPE", "BELONG_TYPE_CODE", "CURRENCY",
                "CURRENCY_CN", "GROSS_RPOFIT_RATIO", "IS_MAXREPORTDATE",
                "MAIN_BUSINESS_COST", "MAIN_BUSINESS_INCOME", "MAIN_BUSINESS_RPOFIT",
                "MBC_RATIO", "MBI_RATIO", "MBR_RATIO", "METHOD_CODE", "METHOD_TYPE",
                "ORG_CODE", "ORG_NAME", "REPORT_CODE", "REPORT_DATE", "REPORT_TYPE",
                "REPORT_YEAR", "SECUCODE", "STD_CLASSIFY_CODE", "STD_REPORT_NAME",
            ]
        else:
            operation_fields = [
                "ACT_REPORT_NAME", "BELONG_TYPE_CODE", "CURRENCY", "CURRENCY_CH",
                "GROSS_RPOFIT_RATIO", "IS_MAXREPORTDATE", "MAIN_BUSINESS_COST",
                "MAIN_BUSINESS_INCOME", "MAIN_BUSINESS_RPOFIT", "MBC_RATIO",
                "MBI_RATIO", "MBR_RATIO", "METHOD_CODE", "METHOD_TYPE", "ORG_CODE",
                "ORG_NAME", "REPORT_CODE", "REPORT_DATE", "REPORT_TYPE", "REPORT_YEAR",
                "SECURITY_CODE", "SECURITY_INNER_CODE", "SECURITY_NAME_ABBR",
                "STD_CLASSIFY_CODE", "STD_REPORT_NAME", "Type",
            ]
        return [
            make_dataset(
                result,
                "operation",
                operation_data.get("report", "RPT_USF9_INFO_PRODUCTSTRUCTURE"),
                operation_fields,
                "ORG_CODE=%s；Type=%s；产品优先，产品为空切换地区"
                % (org_code, operation_data.get("type_code", "")),
                {
                    "type_code": operation_data.get("type_code"),
                    "type_name": operation_data.get("type_name"),
                    "fallback_reason": operation_data.get("fallback_reason", ""),
                    "rows": subset_rows(operation_data.get("rows", []), operation_fields),
                },
            )
        ]
    if block == "ESG分析":
        esg_scope = datasets.get("esg_scope", {})
        latest = esg_scope.get("latest") or {}
        summary = {
            field: latest.get(field)
            for field in ESG_ANALYSIS_FIELDS
            if field in latest
        }
        detail_dates = {
            "UPDATEDATE": esg_scope.get("detail_updatedates", [])
        }
        return [
            make_dataset(
                result,
                "esg_scope_summary",
                "RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS / ESG评级汇总+评级构成",
                ESG_ANALYSIS_FIELDS,
                'ESG_ORG="%s"; latest UPDATEDATE' % ESG_ORG_NAME,
                {"summary": summary},
            ),
            make_dataset(
                result,
                "esg_scope_updatedates",
                "RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS / ESG明细 UPDATEDATE",
                ["UPDATEDATE"],
                'ESG_ORG="%s"; UPDATEDATE deduplicated' % ESG_ORG_NAME,
                detail_dates,
            ),
        ]
    if block == "财务状况":
        return [
            make_dataset(
                result,
                "financial_summary",
                financial_report,
                FINANCIAL_SUMMARY_FIELDS,
                "market=%s; org_code=%s; report_type=ordinary; consolidated=true"
                % (market, org_code),
                financial_data,
            ),
            make_dataset(
                result,
                "credit_analysis",
                "Choice报表\\报表指标\\Choice金融终端\\企业F9\\智能发行人\\信用分析\\信用分析",
                CREDIT_ANALYSIS_FIELDS,
                '(ORG_CODE="%s")' % org_code,
                subset_rows(credit_rows, CREDIT_ANALYSIS_FIELDS),
            ),
        ]
    if block == "财务状况（债券发行人）":
        return [
            make_dataset(
                result,
                "financial_summary",
                financial_report,
                FINANCIAL_SUMMARY_FIELDS,
                "market=%s; org_code=%s; report_type=ordinary; consolidated=true"
                % (market, org_code),
                financial_data,
            ),
            make_dataset(
                result,
                "credit_analysis",
                "Choice报表\\报表指标\\Choice金融终端\\企业F9\\智能发行人\\信用分析\\信用分析",
                CREDIT_ANALYSIS_FIELDS,
                '(ORG_CODE="%s")' % org_code,
                subset_rows(credit_rows, CREDIT_ANALYSIS_FIELDS),
            ),
        ]
    if block == "发行概述":
        issuance_data = datasets.get("issuance_overview", {})
        return [make_dataset(
            result,
            "issuance_overview",
            issuance_data.get("report", "RPT_CUSTOM_BOND_BS_SAMEISSUER"),
            ISSUANCE_OVERVIEW_FIELDS,
            issuance_data.get(
                "filter",
                '(SECUCODE_RN=1)(ISSUE_CODE="%s")(IS_GROUP="0")(EXPIRE_DATE>=系统日)' % org_code,
            ),
            {
                "as_of_date": issuance_data.get("as_of_date", ""),
                "filter_semantics": issuance_data.get("filter_semantics", {}),
                "rows": subset_rows(issuance_rows, ISSUANCE_OVERVIEW_FIELDS),
            },
        )]
    if block == "定价分析（债券发行人）":
        return [
            make_dataset(
                result,
                "pricing_issuer_curve",
                issuer_curve_data.get("report", "RPT_BOND_ISSUERCURVE"),
                ISSUER_CURVE_FIELDS,
                issuer_curve_data.get("filter", '(ORG_CODE="%s")' % org_code),
                {
                    "as_of_date": issuer_curve_data.get("as_of_date", ""),
                    "rows": issuer_curve_data.get("rows", []),
                },
            ),
            make_dataset(
                result,
                "pricing_issuer_bond_types",
                issuer_bond_type_data.get("report", "RPT_BOND_ISSUERCURVE_LIKEBOND"),
                ISSUER_BOND_TYPE_FIELDS,
                issuer_bond_type_data.get("filter", '(ORG_CODE="%s")' % org_code),
                {
                    "as_of_date": issuer_bond_type_data.get("as_of_date", ""),
                    "rows": issuer_bond_type_data.get("rows", []),
                    "type_options": issuer_bond_type_data.get("type_options", []),
                },
            ),
            make_dataset(
                result,
                "pricing_market_context",
                market_context_data.get("report", "MQL Search_Context pending: pricing_market_context"),
                MARKET_CONTEXT_FIELDS,
                "同板块独立 MQL 市场数据查询；系统日及最新可用数据日",
                {
                    "as_of_date": market_context_data.get("as_of_date", ""),
                    "rows": market_context_data.get("rows", []),
                    "fallback_reason": market_context_data.get("fallback_reason", ""),
                },
            ),
        ]
    if block == "定价分析（城投）":
        return [
            make_dataset(
                result,
                "pricing_urban_region_compare",
                urban_region_data.get("report", "RPT_CUSTOM_DEBTREMOVE_REGION_COMPARE"),
                URBAN_REGION_COMPARE_FIELDS,
                urban_region_data.get("filter", "发行人所在省；END_DATE<=系统日；最新有效日期"),
                {
                    "as_of_date": urban_region_data.get("as_of_date", ""),
                    "province_name": urban_region_data.get("province_name", ""),
                    "rows": urban_region_data.get("rows", []),
                },
            ),
            make_dataset(
                result,
                "pricing_urban_margin_analysis_ts",
                urban_margin_data.get("report", "RPT_CUSTOM_DEBTREMOVE_MARGIN_ANALYSIS_TS"),
                URBAN_MARGIN_ANALYSIS_FIELDS,
                urban_margin_data.get("filter", "AREA_TYPE/AREA_CODE待Search_Context核对；近12个月每月最后有效日+最新有效日"),
                {
                    "as_of_date": urban_margin_data.get("as_of_date", ""),
                    "window": urban_margin_data.get("window", ""),
                    "rows": urban_margin_data.get("rows", []),
                },
            ),
            make_dataset(
                result,
                "pricing_urban_issuer_margin",
                urban_issuer_margin_data.get("report", "RPT_BOND_ISMARGIN_ORGM"),
                URBAN_ISSUER_MARGIN_FIELDS,
                urban_issuer_margin_data.get("filter", '(ORG_CODE="%s"); 最新交易日+近12个月每月最后有效日' % org_code),
                {
                    "as_of_date": urban_issuer_margin_data.get("as_of_date", ""),
                    "window": urban_issuer_margin_data.get("window", ""),
                    "rows": urban_issuer_margin_data.get("rows", []),
                },
            ),
        ]
    if block == "科创能力":
        return [
            make_dataset(
                result,
                "sci_tech_profile",
                sci_tech_profile_data.get("report", "企业F9_机构基本信息"),
                SCI_TECH_FIELDS,
                sci_tech_profile_data.get("filter", basic_filter),
                subset_rows(sci_tech_profile_data.get("rows", basic_rows), SCI_TECH_FIELDS),
            ),
            make_dataset(
                result,
                "sci_tech_property_summary",
                sci_tech_property_summary_data.get("report", "企业产权-数量统计"),
                SCI_TECH_PROPERTY_SUMMARY_FIELDS,
                sci_tech_property_summary_data.get("filter", basic_filter),
                {
                    "rows": sci_tech_property_summary_data.get("rows", []),
                    "fallback_reason": sci_tech_property_summary_data.get("fallback_reason", ""),
                },
            ),
            make_dataset(
                result,
                "sci_tech_property_yearly",
                sci_tech_property_yearly_data.get("report", "企业产权-年度变化图"),
                SCI_TECH_PROPERTY_YEARLY_FIELDS,
                sci_tech_property_yearly_data.get("filter", basic_filter),
                {
                    "rows": sci_tech_property_yearly_data.get("rows", []),
                    "fallback_reason": sci_tech_property_yearly_data.get("fallback_reason", ""),
                },
            ),
            make_dataset(
                result,
                "sci_tech_patent_distribution",
                sci_tech_patent_data.get(
                    "report",
                    "Choice报表\\报表指标\\Choice金融终端\\A股F9\\公司一页纸\\公司研发实力\\公司一页纸_上市公司专利信息",
                ),
                SCI_TECH_PATENT_FIELDS,
                sci_tech_patent_data.get("filter", basic_filter),
                {
                    "rows": subset_rows(sci_tech_patent_data.get("rows", []), SCI_TECH_PATENT_FIELDS),
                    "fallback_reason": sci_tech_patent_data.get("fallback_reason", ""),
                },
            ),
            make_dataset(
                result,
                "sci_tech_trademark_distribution",
                sci_tech_trademark_data.get("report", "企业产权-商标分布图"),
                SCI_TECH_TRADEMARK_FIELDS,
                sci_tech_trademark_data.get("filter", basic_filter),
                {
                    "rows": sci_tech_trademark_data.get("rows", []),
                    "fallback_reason": sci_tech_trademark_data.get("fallback_reason", ""),
                },
            ),
            make_dataset(
                result,
                "sci_tech_rd_exp_emp",
                sci_tech_rd_data.get(
                    "report",
                    "RPT_ENT_RD_EXP_EMP; Choice报表\\报表指标\\Choice金融终端\\A股F9\\公司一页纸\\公司研发实力\\沪深F9_财务附注_研发支出; "
                    "Choice报表\\报表指标\\Choice金融终端\\A股F9\\公司基本资料\\员工构成\\沪深F9_基础资料_员工构成",
                ),
                SCI_TECH_RD_EXP_FIELDS + SCI_TECH_RD_EMP_FIELDS,
                sci_tech_rd_data.get("filter", basic_filter),
                {
                    "expense_rows": subset_rows(sci_tech_rd_data.get("expense_rows", []), SCI_TECH_RD_EXP_FIELDS),
                    "employee_rows": subset_rows(sci_tech_rd_data.get("employee_rows", []), SCI_TECH_RD_EMP_FIELDS),
                    "rows": subset_rows(sci_tech_rd_data.get("rows", []), SCI_TECH_RD_EXP_FIELDS + SCI_TECH_RD_EMP_FIELDS),
                    "fallback_reason": sci_tech_rd_data.get("fallback_reason", ""),
                },
            ),
            make_dataset(
                result,
                "sci_tech_titles",
                sci_tech_titles_data.get("report", "企业F9机构基本信息 + 科创称号指标"),
                SCI_TECH_TITLE_FIELDS,
                sci_tech_titles_data.get("filter", basic_filter),
                {
                    "rows": sci_tech_titles_data.get("rows", []),
                    "fallback_reason": sci_tech_titles_data.get("fallback_reason", ""),
                },
            ),
            make_dataset(
                result,
                "sci_tech_industry",
                sci_tech_industry_data.get("report", "企业F9基本信息"),
                SCI_TECH_INDUSTRY_FIELDS,
                sci_tech_industry_data.get("filter", basic_filter),
                {
                    "rows": subset_rows(sci_tech_industry_data.get("rows", basic_rows), SCI_TECH_INDUSTRY_FIELDS),
                    "fallback_reason": sci_tech_industry_data.get("fallback_reason", ""),
                },
            ),
        ]
    if block == "偿债分析":
        return [
            make_dataset(
                result,
                "solvency_financial_key_metrics",
                solvency_financial_key_metrics_data.get(
                    "report",
                    "/Choice金融终端/企业F9/企业一页纸/财务关键指标",
                ),
                SOLVENCY_FINANCIAL_KEY_METRICS_FIELDS,
                solvency_financial_key_metrics_data.get(
                    "filter",
                    '(ORG_CODE="%s")' % org_code,
                ),
                {
                    "rows": subset_rows(
                        solvency_financial_key_metrics_data.get("rows", []),
                        SOLVENCY_FINANCIAL_KEY_METRICS_FIELDS,
                    ),
                    "fallback_reason": solvency_financial_key_metrics_data.get(
                        "fallback_reason",
                        "",
                    ),
                },
            ),
            make_dataset(
                result,
                "solvency_credit_analysis",
                solvency_credit_analysis_data.get(
                    "report",
                    "/Choice金融终端/企业F9/企业一页纸/信用分析",
                ),
                SOLVENCY_CREDIT_ANALYSIS_FIELDS,
                solvency_credit_analysis_data.get(
                    "filter",
                    '(ORG_CODE="%s")' % org_code,
                ),
                {
                    "rows": subset_rows(
                        solvency_credit_analysis_data.get("rows", []),
                        SOLVENCY_CREDIT_ANALYSIS_FIELDS,
                    ),
                    "fallback_reason": solvency_credit_analysis_data.get(
                        "fallback_reason",
                        "",
                    ),
                },
            ),
            make_dataset(
                result,
                "solvency_liability_structure",
                solvency_liability_structure_data.get(
                    "report",
                    "/Choice金融终端/企业F9/企业一页纸/负债结构",
                ),
                SOLVENCY_LIABILITY_STRUCTURE_FIELDS,
                solvency_liability_structure_data.get(
                    "filter",
                    '(ORG_CODE="%s")' % org_code,
                ),
                {
                    "rows": subset_rows(
                        solvency_liability_structure_data.get("rows", []),
                        SOLVENCY_LIABILITY_STRUCTURE_FIELDS,
                    ),
                    "fallback_reason": solvency_liability_structure_data.get(
                        "fallback_reason",
                        "",
                    ),
                },
            ),
            make_dataset(
                result,
                "solvency_issue_end_statistics",
                solvency_issue_end_data.get(
                    "report",
                    "RPT_CUSTOM_BOND_ISSUEEND_IS_C",
                ),
                solvency_issue_end_data.get("fields", []),
                solvency_issue_end_data.get(
                    "filter",
                    'ORG_CODE="%s"; 当前日前两年至后一年；按季度；排除指定债券类型'
                    % org_code,
                ),
                {
                    "window_start": solvency_issue_end_data.get("window_start", ""),
                    "window_end": solvency_issue_end_data.get("window_end", ""),
                    "frequency": solvency_issue_end_data.get("frequency", "quarter"),
                    "exclude_bond_types": solvency_issue_end_data.get(
                        "exclude_bond_types",
                        [],
                    ),
                    "fields_status": solvency_issue_end_data.get(
                        "fields_status",
                        "待 Search_Context 核对",
                    ),
                    "rows": solvency_issue_end_data.get("rows", []),
                    "fallback_reason": solvency_issue_end_data.get(
                        "fallback_reason",
                        "",
                    ),
                },
            ),
            make_dataset(
                result,
                "solvency_shareholder",
                "股东情况/股东股权",
                SOLVENCY_SHAREHOLDER_FIELDS,
                solvency_shareholder_data.get(
                    "filter",
                    '(ORG_CODE="%s")(仅保留 SJKZR、TOP1_HOLDER_ST)' % org_code,
                ),
                solvency_shareholder_package(
                    solvency_shareholder_data
                    if solvency_shareholder_data
                    else shareholder_data
                ),
            ),
        ]
    if block == "信用分析":
        return [
            make_dataset(
                result,
                "credit_analysis",
                credit_analysis_data.get(
                    "report",
                    "RPT_CUSTOM_ORG_CREDITANALYSIS",
                ),
                CREDIT_ANALYSIS_FIELDS,
                credit_analysis_data.get(
                    "filter",
                    '(ORG_CODE="%s")(END_DATE<=系统日)' % org_code,
                ),
                {
                    "as_of_date": credit_analysis_data.get("as_of_date", ""),
                    "rows": subset_rows(
                        credit_analysis_data.get("rows", []),
                        CREDIT_ANALYSIS_FIELDS,
                    ),
                    "fallback_reason": credit_analysis_data.get(
                        "fallback_reason",
                        "",
                    ),
                },
            )
        ]
    if block == "司法风险":
        return [make_dataset(
            result,
            "judicial",
            "judicial_four_summary_reports",
            [
                "RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTIONSINFO",
                "RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTEDPERSONS",
                "RPT_CUSTOM_ENT_JUDICIAL_SUM_RESTRICTEDCONSUMER",
                "RPT_CUSTOM_ENT_JUDICIAL_SUM_TERMINATIONCASE",
            ],
            '(ORG_CODE="%s"); TYPE values "1","2","3","4" queried separately; '
            '当前记录 IS_HISTORY="0" + 历史信息 IS_HISTORY="1"；不加持股比例和日期过滤'
            % org_code,
            datasets.get("judicial", {}),
        )]
    if block == "重点关注":
        context = build_key_concerns_context(result, analysis_results)
        return [make_local_analysis_dataset(
            "key_concerns_context",
            "generated_block_analysis_results",
            [
                "analysis_results",
                "prompt_inputs",
                "active_blocks",
                "empty_blocks",
            ],
            "only_previous_14_generated_analyses; unselected_blocks_are_empty",
            context,
        )]
    return []


def build_block_data_packages(
    result: Dict[str, Any],
    source_ids: Dict[str, int],
    analysis_results: Any = None,
) -> List[Dict[str, Any]]:
    packages: List[Dict[str, Any]] = []
    flags = result.get("enterprise_type_flags", {})
    basic_row = one(result.get("datasets", {}).get("basic_info", {}).get("rows", [])) or {}
    entity = {
        "org_code": result.get("org_code"),
        "org_name": basic_row.get("ORG_NAME") or "",
    }

    for block in result.get("selected_blocks", []):
        datasets = block_dataset_specs(result, block, analysis_results)
        source_keys = []
        for dataset in datasets:
            key = dataset.get("dataset_key")
            if key and key not in source_keys:
                source_keys.append(key)
        if block == "重点关注":
            sources = []
        else:
            sources = [
                get_source(result, source_ids, key, block)
                for key in source_keys
                if key in source_ids
            ]
        package_flags = {
            "is_esg_scope": bool(flags.get("is_esg_scope")),
            "is_urban_investment": bool(flags.get("is_urban_investment")),
            "is_sci_tech": bool(flags.get("is_sci_tech")),
            "is_bond_issuer": bool(flags.get("is_bond_issuer")),
        }
        if block == "重点关注":
            # The handoff prompt must not receive route flags as analysis input.
            package_flags = {}
        packages.append({
            "block_name": block,
            "prompt_file": PROMPT_FILES.get(block, ""),
            "entity": entity,
            "route_flags_allowed": package_flags,
            "datasets": datasets,
            # Prompt input is deliberately data-only. Keep report names,
            # fields, filters, and fallback state in the audit package above.
            "prompt_data": [
                prompt_data_projection(dataset.get("data"))
                for dataset in datasets
            ],
            "sources": sources,
            "package_rule": (
                "仅供当前 block_name 对应 prompt 使用；不得与其他板块数据包混传；"
                "prompt 只接收 prompt_data 中的可读业务数据；dataset、fields、filter、query_path、sources 和本地编号仅供内部审计，不传入 prompt；"
                "保留材料的有效原始引用，成文时紧跟对应句子，不集中放在段末。"
                if block != "重点关注"
                else "仅传入前 14 个板块已生成分析正文及其有效原始引用；"
                "引用紧跟对应句子，不集中放在段末；不得传入原始数据、本地审计编号、类型标记或错误信息。"
            ),
        })
    return packages


def load_analysis_results(path: str) -> Any:
    """Load generated block analyses for the optional local handoff test path."""
    with open(path, "r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if isinstance(payload, dict) and "analysis_results" in payload:
        return payload
    return payload


def fetch(
    org_code: str,
    out_dir: Optional[str] = None,
    analysis_results_path: Optional[str] = None,
) -> int:
    try:
        org_code = normalize_org_code(org_code)
    except ValueError as exc:
        print("%s: %s" % (exc, org_code), file=sys.stderr)
        return 1

    today = dt.date.today()
    result: Dict[str, Any] = {
        "org_code": org_code,
        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
        "runtime": "local_python_rest_fallback",
        "judgement_path": "Python REST fallback",
        "note": "本数据底稿由 enterprise-deep-research 本地兜底脚本生成，未调用服务端一页纸报告生成接口。",
        "datasets": {},
        "sources": [],
        "errors": {},
    }

    analysis_results: Any = {}
    if analysis_results_path:
        try:
            analysis_results = load_analysis_results(analysis_results_path)
            result["analysis_results_input"] = os.path.abspath(analysis_results_path)
        except Exception as exc:  # noqa: BLE001
            result["analysis_results_input"] = os.path.abspath(analysis_results_path)
            result["errors"]["analysis_results"] = repr(exc)
    # Keep the optional handoff input available for a later local rebuild of
    # block_data_packages; this contains generated text only, never raw tables.
    result["analysis_results"] = analysis_results

    source_id = 1
    source_ids: Dict[str, int] = {}

    try:
        basic = fetch_basic_info(org_code)
        result["datasets"]["basic_info"] = basic
        result["sources"].append(make_source(source_id, "RPT_COP_ORG_INFO", "Python REST", "ok" if basic["rows"] else "empty", len(basic["rows"])))
        source_ids["basic_info"] = source_id
        source_id += 1
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["basic_info"] = {"rows": []}
        result["errors"]["basic_info"] = repr(exc)
        result["sources"].append(make_source(source_id, "RPT_COP_ORG_INFO", "Python REST", "failed", 0, repr(exc)))
        source_ids["basic_info"] = source_id
        source_id += 1

    result["datasets"]["sci_tech_profile"] = {
        "report": "企业F9_机构基本信息",
        "rows": subset_rows(result["datasets"].get("basic_info", {}).get("rows", []), SCI_TECH_FIELDS),
        "filter": '(ORG_CODE="%s")' % org_code,
    }
    source_ids["sci_tech_profile"] = source_ids.get("basic_info", 0)

    basic_row = one(result["datasets"].get("basic_info", {}).get("rows", [])) or {}
    stock_secucode = str(
        basic_row.get("SECUCODE_AS")
        or basic_row.get("SECUCODE_PRI")
        or basic_row.get("SECUCODE_BJN")
        or ""
    ).strip()

    sci_tech_industry_rows = subset_rows(
        result["datasets"].get("basic_info", {}).get("rows", []),
        SCI_TECH_INDUSTRY_FIELDS,
    )
    result["datasets"]["sci_tech_industry"] = {
        "report": "企业F9基本信息",
        "rows": sci_tech_industry_rows,
        "filter": '(ORG_CODE="%s")' % org_code,
        "fallback_reason": "",
    }
    result["sources"].append(make_source(
        source_id,
        "企业F9基本信息",
        "Python REST",
        "ok" if sci_tech_industry_rows else "empty",
        len(sci_tech_industry_rows),
        "科创能力板块行业字段；由 basic_info 裁剪",
    ))
    source_ids["sci_tech_industry"] = source_id
    source_id += 1

    sci_tech_title_rows = subset_rows(
        result["datasets"].get("basic_info", {}).get("rows", []),
        SCI_TECH_TITLE_FIELDS,
    )
    result["datasets"]["sci_tech_titles"] = {
        "report": "企业F9机构基本信息 + 科创称号指标",
        "rows": sci_tech_title_rows,
        "filter": '(ORG_CODE="%s")' % org_code,
        "fallback_reason": "普通指标是否高新技术企业/所属概念板块在 Python 兜底中不补造，仅保留机构基本信息实际字段",
    }
    result["sources"].append(make_source(
        source_id,
        "企业F9机构基本信息 + 科创称号指标",
        "Python REST",
        "fallback" if sci_tech_title_rows else "empty",
        len(sci_tech_title_rows),
        result["datasets"]["sci_tech_titles"]["fallback_reason"],
    ))
    source_ids["sci_tech_titles"] = source_id
    source_id += 1

    for key, report, reason in (
        (
            "sci_tech_property_summary",
            "企业产权-数量统计",
            "企业产权数量统计的 REST 函数名尚未由 MQL 上下文核对，不猜测函数名",
        ),
        (
            "sci_tech_property_yearly",
            "企业产权-年度变化图",
            "企业产权年度变化的 REST 函数名尚未由 MQL 上下文核对，不猜测函数名",
        ),
        (
            "sci_tech_patent_distribution",
            "Choice报表\\报表指标\\Choice金融终端\\A股F9\\公司一页纸\\公司研发实力\\公司一页纸_上市公司专利信息",
            "专利分布报表的 REST 函数名尚未由 MQL 上下文核对，不猜测函数名",
        ),
        (
            "sci_tech_trademark_distribution",
            "企业产权-商标分布图",
            "企业产权商标分布的 REST 函数名尚未由 MQL 上下文核对，不猜测函数名",
        ),
    ):
        result["datasets"][key] = empty_sci_tech_dataset(report, reason)
        result["datasets"][key]["filter"] = '(ORG_CODE="%s")' % org_code
        result["sources"].append(make_source(source_id, report, "Python REST", "empty", 0, reason))
        source_ids[key] = source_id
        source_id += 1

    try:
        rd_data = fetch_sci_tech_rd_exp_emp(org_code, stock_secucode)
        result["datasets"]["sci_tech_rd_exp_emp"] = {
            **rd_data,
            "filter": '(ORG_CODE="%s")(SECUCODE="%s")' % (org_code, stock_secucode),
            "expense_rows": rd_data.get("rows", []),
            "employee_rows": rd_data.get("rows", []),
        }
        result["sources"].append(make_source(
            source_id,
            "RPT_ENT_RD_EXP_EMP",
            "Python REST",
            "ok" if rd_data.get("rows") else "empty",
            len(rd_data.get("rows", [])),
            rd_data.get("fallback_reason", "研发费用与人员兜底尝试"),
        ))
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["sci_tech_rd_exp_emp"] = empty_sci_tech_dataset(
            "RPT_ENT_RD_EXP_EMP",
            repr(exc),
        )
        result["sources"].append(make_source(source_id, "RPT_ENT_RD_EXP_EMP", "Python REST", "failed", 0, repr(exc)))
    source_ids["sci_tech_rd_exp_emp"] = source_id
    source_id += 1

    try:
        credit_analysis = fetch_credit_analysis(org_code, today)
        result["datasets"]["credit_analysis"] = credit_analysis
        credit_rows = credit_analysis.get("rows", [])
        result["sources"].append(make_source(
            source_id,
            "RPT_CUSTOM_ORG_CREDITANALYSIS",
            "Python REST",
            "ok" if credit_rows else "empty",
            len(credit_rows),
            "信用分析板块专属兜底；END_DATE<=%s；报告期按 REPORT_DATE 倒序"
            % today.isoformat(),
        ))
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["credit_analysis"] = {
            "report": "RPT_CUSTOM_ORG_CREDITANALYSIS",
            "rows": [],
            "fields": CREDIT_ANALYSIS_FIELDS,
            "filter": '(ORG_CODE="%s")(END_DATE<=\'%s\')'
            % (org_code, today.isoformat()),
            "as_of_date": today.isoformat(),
            "fallback_reason": repr(exc),
        }
        result["errors"]["credit_analysis"] = repr(exc)
        result["sources"].append(make_source(
            source_id,
            "RPT_CUSTOM_ORG_CREDITANALYSIS",
            "Python REST",
            "failed",
            0,
            repr(exc),
        ))
    source_ids["credit_analysis"] = source_id
    source_id += 1

    solvency_fallback_specs = (
        (
            "solvency_financial_key_metrics",
            fetch_solvency_financial_key_metrics,
            "/Choice金融终端/企业F9/企业一页纸/财务关键指标",
        ),
        (
            "solvency_credit_analysis",
            fetch_solvency_credit_analysis,
            "/Choice金融终端/企业F9/企业一页纸/信用分析",
        ),
        (
            "solvency_liability_structure",
            fetch_solvency_liability_structure,
            "/Choice金融终端/企业F9/企业一页纸/负债结构",
        ),
    )
    for dataset_key, fetcher, dataset_name in solvency_fallback_specs:
        try:
            solvency_data = fetcher(org_code)
            result["datasets"][dataset_key] = solvency_data
            rows = solvency_data.get("rows", [])
            result["sources"].append(make_source(
                source_id,
                dataset_name,
                "Python REST",
                solvency_data.get("status", "ok" if rows else "empty"),
                len(rows),
                solvency_data.get("fallback_reason", "偿债分析独立数据集；MQL 失败后的本地兜底"),
            ))
        except Exception as exc:  # noqa: BLE001
            result["datasets"][dataset_key] = {
                "report": dataset_name,
                "rows": [],
                "fields": [],
                "fallback_reason": repr(exc),
            }
            result["errors"][dataset_key] = repr(exc)
            result["sources"].append(make_source(
                source_id,
                dataset_name,
                "Python REST",
                "failed",
                0,
                repr(exc),
            ))
        source_ids[dataset_key] = source_id
        source_id += 1

    try:
        solvency_issue_end = fetch_solvency_issue_end_statistics(org_code, today)
        result["datasets"]["solvency_issue_end_statistics"] = solvency_issue_end
        result["sources"].append(make_source(
            source_id,
            "RPT_CUSTOM_BOND_ISSUEEND_IS_C",
            "Python REST",
            "ok" if solvency_issue_end.get("rows") else "empty",
            len(solvency_issue_end.get("rows", [])),
            solvency_issue_end.get("fallback_reason", "偿债分析发行与到期独立数据集"),
        ))
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["solvency_issue_end_statistics"] = {
            "report": "RPT_CUSTOM_BOND_ISSUEEND_IS_C",
            "rows": [],
            "fields": [],
            "fallback_reason": repr(exc),
        }
        result["errors"]["solvency_issue_end_statistics"] = repr(exc)
        result["sources"].append(make_source(
            source_id,
            "RPT_CUSTOM_BOND_ISSUEEND_IS_C",
            "Python REST",
            "failed",
            0,
            repr(exc),
        ))
    source_ids["solvency_issue_end_statistics"] = source_id
    source_id += 1

    try:
        urban_investment_bond_filter = fetch_urban_investment_bond_filter(
            org_code,
            today,
        )
        result["datasets"]["urban_investment_bond_filter"] = urban_investment_bond_filter
        result["sources"].append(make_source(
            source_id,
            "RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER",
            "Python REST",
            "ok" if urban_investment_bond_filter["rows"] else "empty",
            len(urban_investment_bond_filter["rows"]),
            (
                "城投新增判定条件；信用主体代码=当前企业；"
                "筛选类型编码=1；是否剔除同业存单=1；到期日期>=系统日；"
                "有效筛选内容不为占位符；"
                "raw_count=%s"
            ) % urban_investment_bond_filter.get("raw_count", 0),
        ))
    except Exception as exc:  # noqa: BLE001
        urban_investment_bond_filter = {
            "report": "RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER",
            "rows": [],
            "count": 0,
            "filter": (
                '(ORG_CODE="%s")(FILTER_TYPE_CODE="1")'
                '(INTERBANK_DEPO="1")'
            ) % org_code,
            "mql_report_path": URBAN_INVESTMENT_BOND_FILTER_MQL_PATH,
            "fallback_reason": repr(exc),
        }
        result["datasets"]["urban_investment_bond_filter"] = urban_investment_bond_filter
        result["errors"]["urban_investment_bond_filter"] = repr(exc)
        result["sources"].append(make_source(
            source_id,
            "RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER",
            "Python REST",
            "failed",
            0,
            repr(exc),
        ))
    source_ids["urban_investment_bond_filter"] = source_id
    source_id += 1

    try:
        bond_issuer_special_filter = fetch_bond_issuer_special_filter(
            org_code,
            today,
        )
        result["datasets"]["bond_issuer_special_filter"] = bond_issuer_special_filter
        result["sources"].append(make_source(
            source_id,
            "RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER",
            "Python REST",
            "ok" if bond_issuer_special_filter.get("rows") else "empty",
            len(bond_issuer_special_filter.get("rows", [])),
            (
                "发债人专项判定；发行人代码=%s；集团系=0；筛选类型编码=1；"
                "是否剔除同业存单=1；到期日期>%s或为空（接口过滤）；"
                "白名单命中=%s；raw_count=%s"
            ) % (
                org_code,
                today.isoformat(),
                bond_issuer_special_filter.get("whitelist_count", 0),
                bond_issuer_special_filter.get("raw_count", 0),
            ),
        ))
    except Exception as exc:  # noqa: BLE001
        bond_issuer_special_filter = {
            "report": "RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER",
            "status": "failed",
            "mql_report_path": BOND_ISSUER_FILTER_MQL_PATH,
            "org_code": org_code,
            "rows": [],
            "whitelist_rows": [],
            "count": 0,
            "whitelist_count": 0,
            "as_of_date": today.isoformat(),
            "filter": (
                '(ORG_CODE="%s")(IS_GROUP="0")(FILTER_TYPE_CODE="1")'
                '(INTERBANK_DEPO="1")((EXPIRE_DATE>\'%s\')(|EXPIRE_DATE="NULL"))'
            ) % (org_code, today.isoformat()),
            "fallback_reason": repr(exc),
        }
        result["datasets"]["bond_issuer_special_filter"] = bond_issuer_special_filter
        result["errors"]["bond_issuer_special_filter"] = repr(exc)
        result["sources"].append(make_source(
            source_id,
            "RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER",
            "Python REST",
            "failed",
            0,
            repr(exc),
        ))
    source_ids["bond_issuer_special_filter"] = source_id
    source_id += 1

    stock_glance = ""
    basic_row = one(result["datasets"].get("basic_info", {}).get("rows", []))
    province_name = ""
    if basic_row:
        stock_glance = str(basic_row.get("STOCKGLANCE_NEW") or "")
        province_name = str(basic_row.get("PROVINCE_NAME") or "")
    result["enterprise_type_flags"] = classify_enterprise_type(
        result["datasets"].get("basic_info", {}).get("rows", []),
        result["datasets"].get("urban_investment_bond_filter", {}),
        result["datasets"].get("bond_issuer_special_filter", {}),
    )
    market = detect_market(stock_glance)

    try:
        esg_scope = fetch_esg_scope(org_code, result["datasets"].get("basic_info", {}).get("rows", []), today)
        result["datasets"]["esg_scope"] = esg_scope
        result["enterprise_type_flags"]["is_esg_scope"] = bool(esg_scope.get("is_esg_scope"))
        result["sources"].append(make_source(
            source_id,
            esg_scope.get("report", "RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS"),
            "Python REST",
            "ok" if esg_scope.get("is_esg_scope") else "empty",
            1 if esg_scope.get("is_esg_scope") else 0,
            "ESG_SCORE non-empty" if esg_scope.get("is_esg_scope") else "no non-empty ESG_SCORE",
        ))
        source_ids["esg_scope"] = source_id
        source_ids["esg_scope_summary"] = source_id
        source_ids["esg_scope_updatedates"] = source_id + 1
        result["sources"].append(make_source(
            source_id + 1,
            esg_scope.get("report", "RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS"),
            "Python REST",
            "ok" if esg_scope.get("detail_updatedates") else "empty",
            len(esg_scope.get("detail_updatedates", [])),
            "ESG明细 UPDATEDATE 去重",
        ))
        source_id += 1
        source_id += 1
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["esg_scope"] = {"is_esg_scope": False, "errors": repr(exc)}
        result["enterprise_type_flags"]["is_esg_scope"] = False
        result["errors"]["esg_scope"] = repr(exc)
        result["sources"].append(make_source(source_id, "RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS", "Python REST", "failed", 0, repr(exc)))
        source_ids["esg_scope"] = source_id
        source_ids["esg_scope_summary"] = source_id
        source_ids["esg_scope_updatedates"] = source_id
        source_id += 1

    try:
        shareholders = fetch_shareholders(org_code, today)
        result["datasets"]["shareholders"] = shareholders
        row_count = (
            len(shareholders.get("holder_equity", []))
            + len(shareholders.get("related_transactions", []))
        )
        result["sources"].append(make_source(
            source_id,
            "RPT_BOND_GQJG_ISHOLDER",
            "Python REST",
            "ok" if shareholders.get("top_holders") else "empty",
            len(shareholders.get("top_holders", [])),
                "图表保留 RANK 1 至 10 及接口返回的 RANK 9999 合计行",
        ))
        source_ids["shareholders_top_holders"] = source_id
        source_ids["shareholders_equity"] = source_id + 1
        source_ids["related_transactions"] = source_id + 2
        result["sources"].append(make_source(
            source_id + 1,
            "RPT_CUSTOM_ORG_SHAREHOLDER_EQUITY",
            "Python REST",
            "ok" if shareholders.get("holder_equity") else "empty",
            len(shareholders.get("holder_equity", [])),
            "股东股权结果已裁剪为确认的 MQL 字段",
        ))
        result["sources"].append(make_source(
            source_id + 2,
            "RPT_RELATED_TRANSACTION",
            "Python REST",
            "ok" if shareholders.get("related_transactions") else "empty",
            len(shareholders.get("related_transactions", [])),
            "关联交易仅保留八个板块字段",
        ))
        source_id += 3
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["shareholders"] = {}
        result["errors"]["shareholders"] = repr(exc)
        result["sources"].append(make_source(
            source_id,
            "RPT_BOND_GQJG_ISHOLDER",
            "Python REST",
            "failed",
            0,
            repr(exc),
        ))
        source_ids["shareholders_top_holders"] = source_id
        source_ids["shareholders_equity"] = source_id + 1
        result["sources"].append(make_source(
            source_id + 1,
            "RPT_CUSTOM_ORG_SHAREHOLDER_EQUITY",
            "Python REST",
            "failed",
            0,
            repr(exc),
        ))
        result["sources"].append(make_source(
            source_id + 2,
            "RPT_RELATED_TRANSACTION",
            "Python REST",
            "failed",
            0,
            repr(exc),
        ))
        source_ids["related_transactions"] = source_id + 2
        source_id += 3

    shareholder_data = result["datasets"].get("shareholders", {})
    solvency_shareholder = {
        "report": "股东情况/股东股权",
        "filter": '(ORG_CODE="%s")(仅保留 SJKZR、TOP1_HOLDER_ST)' % org_code,
        "latest_report_date": shareholder_data.get("latest_report_date"),
        "rows": subset_rows(
            normalize_shareholder_equity_rows(
                shareholder_data.get("holder_equity", [])
            ),
            SOLVENCY_SHAREHOLDER_FIELDS,
        ),
        "fields": SOLVENCY_SHAREHOLDER_FIELDS,
        "fallback_reason": (
            "仅保留股东情况数据中的实控人 SJKZR 和第一大股东 TOP1_HOLDER_ST"
            if shareholder_data.get("holder_equity")
            else "股东情况数据为空，偿债分析不复制其它股东或关联交易字段"
        ),
    }
    result["datasets"]["solvency_shareholder"] = solvency_shareholder
    result["sources"].append(make_source(
        source_id,
        "RPT_CUSTOM_ORG_SHAREHOLDER_EQUITY",
        "Python REST",
        "ok" if solvency_shareholder["rows"] else "empty",
        len(solvency_shareholder["rows"]),
        "偿债分析独立股东数据集；仅保留 SJKZR、TOP1_HOLDER_ST",
    ))
    source_ids["solvency_shareholder"] = source_id
    source_id += 1

    try:
        operation = fetch_operation(org_code, market, today)
        result["datasets"]["operation"] = operation
        operation_rows = operation.get("rows", [])
        operation_status = "ok" if operation_rows else "empty"
        operation_note = (
            "Type=%s (%s)" % (
                operation.get("type_code", ""),
                operation.get("type_name", ""),
            )
        )
        if operation.get("fallback_reason"):
            operation_note += "; " + operation["fallback_reason"]
        result["sources"].append(make_source(
            source_id,
            operation.get("report", "RPT_ORGF9_FN_MAINOPBUSINESS"),
            "Python REST",
            operation_status,
            len(operation_rows),
            operation_note,
        ))
        source_ids["operation"] = source_id
        source_id += 1
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["operation"] = {"rows": []}
        result["errors"]["operation"] = repr(exc)
        result["sources"].append(make_source(
            source_id,
            "RPT_USF9_INFO_PRODUCTSTRUCTURE / RPT_USF9_INFO_AREASTRUCTURE",
            "Python REST",
            "failed",
            0,
            repr(exc),
        ))
        source_ids["operation"] = source_id
        source_id += 1

    try:
        financial = fetch_financial_summary(org_code, market, today)
        result["datasets"]["financial_summary"] = financial
        result["sources"].append(make_source(source_id, financial["report"], "Python REST", "ok" if financial["rows"] else "empty", len(financial["rows"]), "market=%s" % financial["market"]))
        source_ids["financial_summary"] = source_id
        source_id += 1
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["financial_summary"] = {"rows": []}
        result["errors"]["financial_summary"] = repr(exc)
        result["sources"].append(make_source(source_id, "financial_summary", "Python REST", "failed", 0, repr(exc)))
        source_ids["financial_summary"] = source_id
        source_id += 1

    try:
        bonds = fetch_bonds(org_code)
        result["datasets"]["bonds"] = bonds
        result["sources"].append(make_source(source_id, "RPT_CUSTOM_BOND_BS_SAMEISSUER", "Python REST", "ok" if bonds["rows"] else "empty", len(bonds["rows"])))
        source_ids["bonds"] = source_id
        source_id += 1
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["bonds"] = {"rows": []}
        result["errors"]["bonds"] = repr(exc)
        result["sources"].append(make_source(source_id, "RPT_CUSTOM_BOND_BS_SAMEISSUER", "Python REST", "failed", 0, repr(exc)))
        source_ids["bonds"] = source_id
        source_id += 1

    try:
        issuance_overview = fetch_issuance_overview(org_code, today)
        issuance_overview["filter"] = (
            '(SECUCODE_RN=1)(ISSUE_CODE="%s")(IS_GROUP="0")(EXPIRE_DATE>=\'%s\')'
            % (org_code, today.isoformat())
        )
        result["datasets"]["issuance_overview"] = issuance_overview
        result["enterprise_type_flags"]["has_active_bonds"] = issuance_overview.get("has_active_bonds")
        result["sources"].append(make_source(
            source_id,
            "RPT_CUSTOM_BOND_BS_SAMEISSUER",
            "Python REST",
            issuance_overview.get("status", "ok" if issuance_overview["rows"] else "empty"),
            len(issuance_overview["rows"]),
            "发行概述独立数据包；去重跨市场债、仅未到期、排除同业存单、系统日=%s；存续状态=%s"
            % (today.isoformat(), issuance_overview.get("status", "unknown")),
        ))
        source_ids["issuance_overview"] = source_id
        source_id += 1
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["issuance_overview"] = {"rows": []}
        result["enterprise_type_flags"]["has_active_bonds"] = None
        result["errors"]["issuance_overview"] = repr(exc)
        result["sources"].append(make_source(
            source_id,
            "RPT_CUSTOM_BOND_BS_SAMEISSUER",
            "Python REST",
            "failed",
            0,
            repr(exc),
        ))
        source_ids["issuance_overview"] = source_id
        source_id += 1

    try:
        issuer_curve = fetch_issuer_curve(org_code, today)
        issuer_curve["filter"] = "未执行拟合：样本期限、收益率及类型序列尚未就绪"
        result["datasets"]["pricing_issuer_curve"] = issuer_curve
        result["sources"].append(make_source(
            source_id,
            "RPT_BOND_ISSUERCURVE",
            "Python REST",
            issuer_curve.get("status", "ok" if issuer_curve["rows"] else "empty"),
            len(issuer_curve["rows"]),
            issuer_curve.get("fallback_reason", "发行人收益率/行情兜底尝试"),
        ))
        source_ids["pricing_issuer_curve"] = source_id
        source_id += 1
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["pricing_issuer_curve"] = {"rows": []}
        result["errors"]["pricing_issuer_curve"] = repr(exc)
        result["sources"].append(make_source(source_id, "RPT_BOND_ISSUERCURVE", "Python REST", "failed", 0, repr(exc)))
        source_ids["pricing_issuer_curve"] = source_id
        source_id += 1

    try:
        issuer_bond_types = fetch_issuer_bond_types(org_code, today)
        result["datasets"]["pricing_issuer_bond_types"] = issuer_bond_types
        result["sources"].append(make_source(
            source_id,
            "RPT_BOND_ISSUERCURVE_LIKEBOND",
            "Python REST",
            "ok" if issuer_bond_types["rows"] else "empty",
            len(issuer_bond_types["rows"]),
            "发行人债券类型样本；按 EMBOND_3LEVEL_CODE 去重生成 type_options",
        ))
        source_ids["pricing_issuer_bond_types"] = source_id
        source_id += 1
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["pricing_issuer_bond_types"] = {"rows": [], "type_options": []}
        result["errors"]["pricing_issuer_bond_types"] = repr(exc)
        result["sources"].append(make_source(source_id, "RPT_BOND_ISSUERCURVE_LIKEBOND", "Python REST", "failed", 0, repr(exc)))
        source_ids["pricing_issuer_bond_types"] = source_id
        source_id += 1

    market_context = empty_market_context(today)
    result["datasets"]["pricing_market_context"] = market_context
    result["errors"]["pricing_market_context"] = market_context["fallback_reason"]
    result["sources"].append(make_source(
        source_id,
        market_context["report"],
        "Python REST",
        "empty",
        0,
        market_context["fallback_reason"],
    ))
    source_ids["pricing_market_context"] = source_id
    source_id += 1

    try:
        urban_region = fetch_urban_region_compare(org_code, today, province_name)
        urban_region["filter"] = "发行人所在省=%s；END_DATE<=%s；取最新有效日期" % (province_name, today.isoformat())
        result["datasets"]["pricing_urban_region_compare"] = urban_region
        result["sources"].append(make_source(
            source_id,
            "RPT_CUSTOM_DEBTREMOVE_REGION_COMPARE",
            "Python REST",
            "ok" if urban_region["rows"] else "empty",
            len(urban_region["rows"]),
            urban_region.get("fallback_reason", "区域对比兜底尝试"),
        ))
        source_ids["pricing_urban_region_compare"] = source_id
        source_id += 1
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["pricing_urban_region_compare"] = {"rows": []}
        result["errors"]["pricing_urban_region_compare"] = repr(exc)
        result["sources"].append(make_source(source_id, "RPT_CUSTOM_DEBTREMOVE_REGION_COMPARE", "Python REST", "failed", 0, repr(exc)))
        source_ids["pricing_urban_region_compare"] = source_id
        source_id += 1

    try:
        urban_margin = fetch_urban_margin_analysis_ts(org_code, today)
        result["datasets"]["pricing_urban_margin_analysis_ts"] = urban_margin
        result["sources"].append(make_source(
            source_id,
            "RPT_CUSTOM_DEBTREMOVE_MARGIN_ANALYSIS_TS",
            "Python REST",
            "ok" if urban_margin["rows"] else "empty",
            len(urban_margin["rows"]),
            urban_margin.get("fallback_reason", "区域利差时间序列兜底尝试"),
        ))
        source_ids["pricing_urban_margin_analysis_ts"] = source_id
        source_id += 1
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["pricing_urban_margin_analysis_ts"] = {"rows": []}
        result["errors"]["pricing_urban_margin_analysis_ts"] = repr(exc)
        result["sources"].append(make_source(source_id, "RPT_CUSTOM_DEBTREMOVE_MARGIN_ANALYSIS_TS", "Python REST", "failed", 0, repr(exc)))
        source_ids["pricing_urban_margin_analysis_ts"] = source_id
        source_id += 1

    try:
        urban_issuer_margin = fetch_urban_issuer_margin(org_code, today)
        urban_issuer_margin["filter"] = '(ORG_CODE="%s"); 最新交易日+近12个月每月最后有效日' % org_code
        result["datasets"]["pricing_urban_issuer_margin"] = urban_issuer_margin
        result["sources"].append(make_source(
            source_id,
            "RPT_BOND_ISMARGIN_ORGM",
            "Python REST",
            "ok" if urban_issuer_margin["rows"] else "empty",
            len(urban_issuer_margin["rows"]),
            urban_issuer_margin.get("fallback_reason", "主体利差兜底尝试"),
        ))
        source_ids["pricing_urban_issuer_margin"] = source_id
        source_id += 1
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["pricing_urban_issuer_margin"] = {"rows": []}
        result["errors"]["pricing_urban_issuer_margin"] = repr(exc)
        result["sources"].append(make_source(source_id, "RPT_BOND_ISMARGIN_ORGM", "Python REST", "failed", 0, repr(exc)))
        source_ids["pricing_urban_issuer_margin"] = source_id
        source_id += 1

    try:
        judicial = fetch_judicial(org_code, today)
        result["datasets"]["judicial"] = judicial
        row_count = _count_judicial_rows(judicial)
        result["sources"].append(make_source(
            source_id,
            "judicial_four_summary_reports",
            "Python REST",
            "ok" if row_count else "empty",
            row_count,
            "仅四张指定司法汇总表；分别查询当前记录 IS_HISTORY=0 与历史信息 IS_HISTORY=1；按 TYPE 拆分本公司和关联方",
        ))
        source_ids["judicial"] = source_id
        source_id += 1
    except Exception as exc:  # noqa: BLE001
        result["datasets"]["judicial"] = {}
        result["errors"]["judicial"] = repr(exc)
        result["sources"].append(make_source(
            source_id,
            "judicial_four_summary_reports",
            "Python REST",
            "failed",
            0,
            repr(exc),
        ))
        source_ids["judicial"] = source_id
        source_id += 1

    result["selected_blocks"] = route_blocks(result.get("enterprise_type_flags", {}))
    result["block_data_packages"] = build_block_data_packages(
        result,
        source_ids,
        analysis_results,
    )

    out_dir = out_dir or os.getcwd()
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "enterprise_deep_research_local_data_%s_%s.json" % (org_code, today.strftime("%Y%m%d")))
    with open(json_path, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)

    print("JSON_PATH=%s" % os.path.abspath(json_path))
    print("ORG_CODE=%s" % org_code)
    print("BASIC_ROWS=%d" % len(result["datasets"].get("basic_info", {}).get("rows", [])))
    flags = result.get("enterprise_type_flags", {})
    print("IS_ESG_SCOPE=%s" % flags.get("is_esg_scope"))
    print("IS_URBAN_INVESTMENT=%s" % flags.get("is_urban_investment"))
    print("IS_SCI_TECH=%s" % flags.get("is_sci_tech"))
    print("IS_BOND_ISSUER=%s" % flags.get("is_bond_issuer"))
    print("TOP_HOLDERS_ROWS=%d" % len(result["datasets"].get("shareholders", {}).get("top_holders", [])))
    print("FINANCIAL_ROWS=%d" % len(result["datasets"].get("financial_summary", {}).get("rows", [])))
    print("BOND_ROWS=%d" % len(result["datasets"].get("bonds", {}).get("rows", [])))
    judicial_rows = _count_judicial_rows(result["datasets"].get("judicial", {}))
    print("JUDICIAL_ROWS=%d" % judicial_rows)
    if result["errors"]:
        print("PARTIAL_ERRORS=%s" % json.dumps(result["errors"], ensure_ascii=False))

    total_rows = 0
    for source in result["sources"]:
        total_rows += int(source.get("rows") or 0)
    return 0 if total_rows > 0 else 2


def resolve(name: str) -> int:
    token = "D43BF722C8E33BDC906FB84D85E326E8"
    candidates: List[Dict[str, Any]] = []
    for typ in ("14", "1"):
        try:
            query = urllib.parse.urlencode({"input": name, "type": typ, "token": token, "count": "20"})
            url = "https://searchapi.eastmoney.com/api/suggest/get?" + query
            data = http_get_json(url)
            table = (data.get("QuotationCodeTable") or {}).get("Data") or []
            for item in table:
                row = {"mkt_type": typ}
                if isinstance(item, dict):
                    row.update({str(k): v for k, v in item.items()})
                candidates.append(row)
        except Exception as exc:  # noqa: BLE001
            print("resolve type=%s error: %s" % (typ, exc), file=sys.stderr)

    if not candidates:
        print("RESOLVE=NO_CANDIDATE")
        return 1

    print("RESOLVE=CANDIDATES")
    for index, candidate in enumerate(candidates, 1):
        org = ""
        for key, value in candidate.items():
            if "org" in key.lower() and value:
                org = str(value)
                break
        print("[%d] Name=%s Code=%s OrgCode=%s Extra=%s" % (
            index,
            candidate.get("Name") or candidate.get("name") or "",
            candidate.get("Code") or candidate.get("code") or "",
            org,
            json.dumps({k: v for k, v in candidate.items() if k not in ("Name", "name", "Code", "code")}, ensure_ascii=False)[:300],
        ))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="enterprise-deep-research 本地数据兜底脚本")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_resolve = sub.add_parser("resolve", help="按企业名称解析机构代码候选")
    p_resolve.add_argument("--name", required=True, help="企业名称")

    p_fetch = sub.add_parser("fetch", help="按完整机构代码抓取通用结构化数据")
    p_fetch.add_argument("--org", required=True, help="完整数字机构代码，可带 .FXR 后缀；须先核对企业实体")
    p_fetch.add_argument("--out", default=None, help="输出目录（默认当前目录）")
    p_fetch.add_argument(
        "--analysis-results",
        default=None,
        help="可选：前 14 个板块已生成分析结果的 JSON 文件，仅用于组装重点关注输入",
    )

    args = parser.parse_args()
    if args.cmd == "resolve":
        return resolve(args.name)
    if args.cmd == "fetch":
        return fetch(args.org, args.out, args.analysis_results)
    return 1


if __name__ == "__main__":
    sys.exit(main())
