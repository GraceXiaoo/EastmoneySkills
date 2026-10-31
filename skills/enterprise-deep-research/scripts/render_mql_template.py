#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render reusable MQL templates for enterprise-deep-research."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
VERIFICATION_FILE = ROOT / "references" / "data-sources" / "mql-verification.json"

SHAREHOLDER_MAIN_TEMPLATE = r'''ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\股东股权\股东明细\股东明细\主要股东|789604172179402});
SetReportFilter({发行人代码} == "{{ORG_CODE}}" AND {截止日期} == "{{END_DATE}}");
{股东名称}: REPORT_FIELD("股东名称");
{持有数量(股)}: REPORT_FIELD("持有数量/金额");
{持有比例(%)}: REPORT_FIELD("持有比例(%)");
{股东是否为发行人}: REPORT_FIELD("股东是否为发行人");
Sort({持有比例(%)}, "DESC");
Head(15);
OutputBlock();'''

CURVE_SAMPLES_TEMPLATE = r'''ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\发行人曲线\样本券对应关系\发行人曲线_样本券|873037266287012});
SetReportFilter(({原始发行人代码} == "{{ISSUER_CODE}}") AND ({定价日} == "{{TRADE_DATE}}"));
{样本券类型}: REPORT_FIELD("样本券类型");
{样本券代码}: REPORT_FIELD("样本券代码");
OutputBlock();'''

CURVE_VALUATION_TEMPLATE = r'''ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\发行人曲线\条件筛选-债券列表\发行人曲线_相似债_估值|025324135305196});
SetCodes({{SAMPLE_CODES}});
SetReportFilter(({交易日期} == "{{TRADE_DATE}}") AND ({通用类型1} == "{{SAMPLE_TYPES}}"));
{债券代码}: REPORT_FIELD("债券代码");
{样本类型编码}: REPORT_FIELD("样本类型编码");
{样本类型}: REPORT_FIELD("样本类型");
{定价日}: REPORT_FIELD("定价日");
{剩余期限(中债)}: REPORT_FIELD("剩余期限(中债)");
{中债估值(推荐)}: REPORT_FIELD("中债估值(推荐)");
{债券简称}: REPORT_FIELD("债券简称");
{债项评级}: REPORT_FIELD("债项评级");
{东财债券分类}: REPORT_FIELD("东财债券分类");
{东财债券分类编码}: REPORT_FIELD("东财债券分类编码");
{到期日}: REPORT_FIELD("到期日");
{发行日}: REPORT_FIELD("发行日");
{发行规模}: REPORT_FIELD("发行规模");
{债券余额}: REPORT_FIELD("债券余额");
{上一日成交收益率}: REPORT_FIELD("上一日成交收益率");
{募集方式}: REPORT_FIELD("募集方式");
{YY评级}: REPORT_FIELD("YY评级");
{YY行业}: REPORT_FIELD("YY行业");
{票面利率}: REPORT_FIELD("票面利率");
OutputBlock();'''

FINANCE_CHART_TEMPLATE = r'''ReportBlock(#1, {Choice报表\报表指标\服务端\妙想服务\对接API\F10_财务分析_主要财务指标|594237169895505});
SetCodes(["{{STOCK_CODE}}"]);
SetReportFilter(({报告期} >= "{{START_DATE}}") AND ({报告期} <= "{{END_DATE}}"));
{公司代码}: REPORT_FIELD("公司代码");
{证券代码(带后缀)}: REPORT_FIELD("证券代码(带后缀)");
{机构类型}: REPORT_FIELD("机构类型");
{币种}: REPORT_FIELD("币种");
{报告期}: REPORT_FIELD("报告期");
{报告期标签}: REPORT_FIELD("报告期标签");
{报告期类型}: REPORT_FIELD("报告期类型");
{营业总收入}: REPORT_FIELD("营业总收入");
{营业总收入同比增长}: REPORT_FIELD("营业总收入同比增长");
{归属净利润}: REPORT_FIELD("归属净利润");
{归属净利润同比增长}: REPORT_FIELD("归属净利润同比增长");
{资产负债率}: REPORT_FIELD("资产负债率");
{净资产收益率(加权)}: REPORT_FIELD("净资产收益率(加权)");
{每股经营现金流}: REPORT_FIELD("每股经营现金流");
OutputBlock();'''

ESG_LEVEL1_TEMPLATE = r'''ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\API专题报表函数\A股\F9\ESG\ESG-明细弹窗接口|545851408591004});
SetCodes(["{{STOCK_CODE}}"]);
SetReportFilter({更新日期} <= "{{END_DATE}}");
{证券代码带后缀}: REPORT_FIELD("证券代码带后缀");
{所属子项中文}: REPORT_FIELD("所属子项中文");
{一级指标名称}: REPORT_FIELD("一级指标名称");
{一级指标得分}: REPORT_FIELD("一级指标得分");
{更新日期}: REPORT_FIELD("更新日期");
OutputBlock();'''

ISSUANCE_TEMPLATE = r'''ReportBlock(#1, {Choice报表\报表指标\服务端\妙想服务\量化查数\债券\企业F9\发行一览\发行债券|RPT_CUSTOM_BOND_BS_SAMEISSUER});
SetReportFilter(({发行人代码} == "{{ORG_CODE}}") AND ({集团系} == "0") AND ({跨市场去重排序} == 1) AND ({到期日期} >= "{{SYSTEM_DATE}}") AND ({债券类型} <> "同业存单"));
{债券代码}: REPORT_FIELD("债券代码带后缀");
{债券简称}: REPORT_FIELD("债券简称");
{债券类型}: REPORT_FIELD("证券类别");
{债券余额}: REPORT_FIELD("当前余额(亿)");
{币种}: REPORT_FIELD("币种");
{发行日期}: REPORT_FIELD("发行日期");
{到期日期}: REPORT_FIELD("到期日期");
{剩余期限}: REPORT_FIELD("剩余期限");
{最新债项评级}: REPORT_FIELD("债券评级");
{最新主体评级}: REPORT_FIELD("主体评级");
{票面利率}: REPORT_FIELD("票面利率(发行参考利率)");
{所属集团}: REPORT_FIELD("所属集团");
OutputBlock();'''

CREDIT_FULL_TEMPLATE = '''ReportBlock(#1, {Choice报表\\报表指标\\Choice金融终端\\企业F9\\企业一页纸\\信用分析\\信用分析|088883350557610});
SetReportFilter(({公司代码} == "{{ORG_CODE}}") AND ({截止日期} == "{{END_DATE}}"));
{银行授信总额度}: REPORT_FIELD("银行授信总额度（亿元）");
{银行授信已使用额度}: REPORT_FIELD("银行授信已使用额度（亿元）");
{前十大授信银行}: REPORT_FIELD("前十大授信银行");
{授信机构数量}: REPORT_FIELD("授信机构数量");
{货币资金短期债务}: REPORT_FIELD("货币资金/短期债务\u0000");
{当前逾期本息}: REPORT_FIELD("当前逾期本息（万元）");
{对外担保余额占总资产比例}: REPORT_FIELD("对外担保余额占总资产比例");
{对外担保余额占净资产比例}: REPORT_FIELD("对外担保余额占净资产比例");
{变动方向}: REPORT_FIELD("变动方向");
{评级展望}: REPORT_FIELD("评级展望");
{最新主体评级}: REPORT_FIELD("最新主体评级");
{经营活动现金流净额带息债务}: REPORT_FIELD("经营活动产生的现金流量净额/带息债务");
{经营活动现金流净额流动负债}: REPORT_FIELD("经营活动产生的现金流量净额/流动负债");
{最新实质违约债券}: REPORT_FIELD("最新实质违约债券");
{展期债券只数}: REPORT_FIELD("展期债券只数");
{实质违约债券只数}: REPORT_FIELD("实质违约债券只数");
{前十大对外担保对象}: REPORT_FIELD("前十大对外担保对象");
{未使用授信额度有息债务}: REPORT_FIELD("未使用的授信额度/有息债务");
{报告期}: REPORT_FIELD("报告期");
OutputBlock();'''

SOLVENCY_STATISTICS_TEMPLATE = r'''ReportBlock(#1, {Choice报表\报表指标\服务端\妙想服务\细分场景\企业分析\企业融资偿债情况\偿债统计\企业融资偿债情况偿债统计|RPT_CUSTOM_BOND_ISSUEEND_IS_C});
SetReportFilter(({实体代码} == "{{ISSUER_CODE}}") AND ({起始日期} == "{{START_DATE}}") AND ({截止日期} == "{{END_DATE}}") AND ({周期} == 4) AND ({发行日期类型} == "2"));
{偿债总额}: REPORT_FIELD("偿债总额");
{偿债只数}: REPORT_FIELD("偿债只数");
OutputBlock();'''

SCI_TECH_PROFILE_TEMPLATE = r'''ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\表头\企业F9_机构基本信息|148758350698551});
SetReportFilter({公司代码} == "{{ORG_CODE}}");
{行业}: REPORT_FIELD("行业");
{省份}: REPORT_FIELD("省份");
{科创称号}: REPORT_FIELD("科创称号");
{科创领域}: REPORT_FIELD("科创领域");
OutputBlock();'''

JUDICIAL_PATHS = {
    "dishonest": "Choice报表\\报表指标\\Choice金融终端\\企业F9(发行人+工商企业)\\企业一页纸\\司法风险汇总信息\\失信被执行人汇总|081751076337787",
    "executed_main": "Choice报表\\报表指标\\Choice金融终端\\企业F9(发行人+工商企业)\\企业一页纸\\司法风险汇总信息\\被执行人汇总|006194229816016",
    "executed_backup": "Choice报表\\报表指标\\Choice金融终端\\企业F9\\企业一页纸\\司法风险汇总信息\\被执行人\\被执行人汇总|024220940284594",
    "restricted": "Choice报表\\报表指标\\Choice金融终端\\企业F9(发行人+工商企业)\\企业一页纸\\司法风险汇总信息\\限制高消费汇总|868338831875985",
    "termination": "Choice报表\\报表指标\\Choice金融终端\\企业F9(发行人+工商企业)\\企业一页纸\\司法风险汇总信息\\终本案件汇总|349894282139442",
}

JUDICIAL_FIELDS = {
    "dishonest": [("关系类型", "关系类型"), ("对象", "失信被执行人"), ("当前案件数", "当前案件数"), ("历史案件数", "历史案件数"), ("当前执行标的", "当前执行标的（万元）"), ("历史执行标的", "历史执行标的（万元）")],
    "executed": [("关系类型", "关系类型"), ("对象", "被执行人"), ("当前案件数", "当前案件数"), ("历史案件数", "历史案件数"), ("当前执行标的", "当前执行标的（万元）"), ("历史执行标的", "历史执行标的（万元）")],
    "restricted": [("关系类型", "关系类型"), ("对象", "限消令对象"), ("当前案件数", "当前案件数"), ("历史案件数", "历史案件数")],
    "termination": [("关系类型", "关系类型"), ("对象", "被执行人"), ("当前案件数", "当前案件数"), ("历史案件数", "历史案件数"), ("当前执行总金额", "当前执行总金额（万元）"), ("历史执行总金额", "历史执行总金额（万元）"), ("当前未履行总金额", "当前未履行总金额（万元）"), ("历史未履行总金额", "历史未履行总金额（万元）"), ("当前未履行比例", "当前未履行比例(%)"), ("历史未履行比例", "历史未履行比例(%)")],
}

VERIFIED_KEYS = {"org_info_all", "urban_filter", "issuer_filter", "basic_noid_cn", "industry_fixed", "shareholder_partial", "related_noid", "operation_product_fixed", "operation_region_fixed", "operation_other_entity_chart", "esg_scope", "esg_summary", "esg_detail_fixed", "finance_metrics", "curve_types", "patents", "rd_metric", "staff", "solvency_key", "solvency_debt", "credit_noid"}

MODULE_KEYS = {
    "企业类型": ["org_info_all", "esg_scope", "urban_filter", "issuer_filter"],
    "基本情况": ["basic_noid_cn"], "股东情况": ["shareholder_main", "shareholder_partial", "related_noid"], "所处行业": ["industry_fixed"],
    "经营状况": ["operation_product_fixed", "operation_region_fixed", "operation_other_entity_chart"], "ESG分析": ["esg_scope", "esg_summary", "esg_detail_fixed", "esg_level1"],
    "财务状况": ["finance_metrics", "finance_chart", "credit_full"], "财务状况（债券发行人）": ["finance_metrics", "finance_chart", "credit_full"], "发行概述": ["issuance_fixed"],
    "定价分析（债券发行人）": ["curve_types", "curve_samples", "curve_valuation", "curve_fullmarket"], "定价分析（城投）": ["region_compare", "urban_margin", "urban_issuer_spread"],
    "科创能力": ["sci_tech_profile", "patents", "rd_metric", "staff"], "偿债分析": ["solvency_key", "credit_full", "solvency_debt", "solvency_statistics", "shareholder_partial"], "信用分析": ["credit_full", "credit_noid"],
    "司法风险": ["judicial_dishonest", "judicial_executed_main", "judicial_executed_backup", "judicial_restricted", "judicial_termination"],
    "重点关注": [],
}

def _load_verified_records() -> Dict[str, Mapping[str, object]]:
    payload = json.loads(VERIFICATION_FILE.read_text(encoding="utf-8"))
    return {str(x["key"]): x for x in payload.get("queries", []) if x.get("key") in VERIFIED_KEYS and x.get("ok") is True and x.get("mql")}

def _quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

def _replace_values(text: str, samples: Iterable[str], value: str) -> str:
    for sample in samples:
        if _quoted(sample) in text and not value:
            raise ValueError("missing code parameter for template")
        text = text.replace(_quoted(sample), _quoted(value))
    return text

def _render_verified(key: str, args: argparse.Namespace) -> str:
    record = _load_verified_records().get(key)
    if not record: raise KeyError("template is not a successful verification record: %s" % key)
    mql = str(record["mql"]); org = args.org_code or ""; issuer = args.issuer_code or (org + ".FXR" if org else ""); stock = args.stock_code or ""
    org_samples = ["10002602", "10002264", "10083304", "10000069733", "10010954", "10426109"]; issuer_samples = ["10002602.FXR", "10002264.FXR", "10010954.FXR", "10000069733.FXR"]; stock_samples = ["600519.SH", "688630.SH"]
    if key == "esg_scope":
        if not stock and not issuer:
            raise ValueError("ESG scope requires a stock or issuer code")
        blocks = mql.split("CrossSectionBlock(#2", 1)
        mql = blocks[0] if stock else "CrossSectionBlock(#1" + blocks[1]
    # Replace both raw organization codes and suffixed issuer codes independently.
    mql = _replace_values(_replace_values(_replace_values(mql, org_samples, org), issuer_samples, issuer), stock_samples, stock)
    dates = {"2026-09-20": args.system_date or args.end_date or "", "2025-09-20": args.start_date or "", "2026-09-18": args.trade_date or args.system_date or args.end_date or "", "2023-01-01": args.period_start or args.start_date or "", "2025-12-31": args.report_date or ""}
    def replace_date(match: re.Match) -> str:
        value = dates[match.group()]
        if not value:
            raise ValueError("missing date parameter for template: %s" % match.group())
        return value
    return re.sub("|".join(re.escape(old) for old in dates), replace_date, mql)

def _fill(template: str, values: Mapping[str, str]) -> str:
    for name in re.findall(r"\{\{([A-Z_]+)\}\}", template):
        value = values.get(name, "")
        if not value:
            raise ValueError("missing template parameter: %s" % name)
        template = template.replace("{{%s}}" % name, value)
    return template

def _curve_valuation(args: argparse.Namespace) -> str:
    if args.samples_json and args.samples_file:
        raise ValueError("use only one of --samples-json and --samples-file")
    pairs = json.loads(Path(args.samples_file).read_text(encoding="utf-8-sig") if args.samples_file else (args.samples_json or "[]"))
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("--samples-json requires nonempty [[bond_code, sample_type], ...]")
    by_code = {}
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("each sample must be [bond_code, sample_type]")
        code, kind = pair
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9]+\.[A-Za-z0-9]+", code) or kind not in ("1", "2"):
            raise ValueError("invalid bond code or sample type")
        if code in by_code and by_code[code] != kind:
            raise ValueError("conflicting sample types for %s" % code)
        by_code[code] = kind
    codes = sorted(by_code)
    return _fill(CURVE_VALUATION_TEMPLATE, {
        "SAMPLE_CODES": json.dumps(codes, ensure_ascii=True),
        "SAMPLE_TYPES": ",".join(by_code[code] for code in codes),
        "TRADE_DATE": args.trade_date or "",
    })

def _judicial_template(kind: str, org_code: str, is_history: str) -> str:
    base = "executed" if kind in {"executed_main", "executed_backup"} else kind
    if kind not in JUDICIAL_PATHS or base not in JUDICIAL_FIELDS: raise KeyError("unknown judicial template: %s" % kind)
    lines = ["ReportBlock(#1, {%s});" % JUDICIAL_PATHS[kind], 'SetReportFilter(({公司代码} == "%s") AND ({是否历史信息} == "%s") AND IN({关系类型}, ["1", "2", "3", "4"]));' % (org_code, is_history)]
    lines.extend('{%s}: REPORT_FIELD("%s");' % pair for pair in JUDICIAL_FIELDS[base]); lines.append("OutputBlock();")
    return "\n".join(lines)

def render(key: str, args: argparse.Namespace) -> str:
    for name in ("start_date", "end_date", "system_date", "report_date", "period_start", "trade_date"):
        value = getattr(args, name, None)
        if value and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) or date.fromisoformat(value).isoformat() != value):
            raise ValueError("invalid ISO date: %s" % name)
    for name in ("org_code", "issuer_code", "stock_code"):
        value = getattr(args, name, None)
        if value and not re.fullmatch(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)?", value):
            raise ValueError("invalid code: %s" % name)
    if args.org_code and "." in args.org_code:
        raise ValueError("--org-code must not include a market suffix")
    if args.start_date and (args.end_date or args.system_date) and args.start_date > (args.end_date or args.system_date):
        raise ValueError("start date must not exceed end date")
    if args.is_history not in ("0", "1"):
        raise ValueError("--is-history must be 0 or 1")
    if key == "curve_samples":
        return _fill(CURVE_SAMPLES_TEMPLATE, {"ISSUER_CODE": args.issuer_code or (args.org_code + ".FXR" if args.org_code else ""), "TRADE_DATE": args.trade_date or ""})
    if key == "curve_valuation":
        return _curve_valuation(args)
    if key in {"finance_chart", "esg_level1"}:
        return _fill(FINANCE_CHART_TEMPLATE if key == "finance_chart" else ESG_LEVEL1_TEMPLATE, {"STOCK_CODE": args.stock_code or "", "START_DATE": args.start_date or "", "END_DATE": args.end_date or args.system_date or ""})
    if key in {"shareholder_main", "issuance_fixed", "credit_full", "sci_tech_profile"} or key.startswith("judicial_"):
        if not args.org_code:
            raise ValueError("--org-code is required")
    if key in {"shareholder_main", "issuance_fixed", "credit_full"} and not (args.end_date or args.system_date):
        raise ValueError("--end-date or --system-date is required")
    if key == "shareholder_main": return SHAREHOLDER_MAIN_TEMPLATE.replace("{{ORG_CODE}}", args.org_code or "").replace("{{END_DATE}}", args.end_date or args.system_date or "")
    if key == "issuance_fixed": return ISSUANCE_TEMPLATE.replace("{{ORG_CODE}}", args.org_code or "").replace("{{SYSTEM_DATE}}", args.system_date or args.end_date or "")
    if key == "credit_full": return CREDIT_FULL_TEMPLATE.replace("{{ORG_CODE}}", args.org_code or "").replace("{{END_DATE}}", args.end_date or args.system_date or "")
    if key == "solvency_statistics_diagnostic":
        return _fill(SOLVENCY_STATISTICS_TEMPLATE, {"ISSUER_CODE": args.issuer_code or (args.org_code + ".FXR" if args.org_code else ""), "START_DATE": args.start_date or "", "END_DATE": args.end_date or args.system_date or ""})
    if key == "sci_tech_profile": return SCI_TECH_PROFILE_TEMPLATE.replace("{{ORG_CODE}}", args.org_code or "")
    if key.startswith("judicial_"): return _judicial_template(key.removeprefix("judicial_"), args.org_code or "", args.is_history)
    if key in {"curve_fullmarket", "region_compare", "urban_margin", "urban_issuer_spread", "solvency_statistics"}: raise KeyError("template is not business-complete; consult module verification before execution: %s" % key)
    return _render_verified(key, args)

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--list", action="store_true"); p.add_argument("--module"); p.add_argument("--key"); p.add_argument("--org-code"); p.add_argument("--issuer-code"); p.add_argument("--stock-code"); p.add_argument("--start-date"); p.add_argument("--end-date"); p.add_argument("--system-date"); p.add_argument("--report-date"); p.add_argument("--period-start"); p.add_argument("--trade-date"); p.add_argument("--is-history", default="0"); p.add_argument("--samples-json"); p.add_argument("--samples-file"); p.add_argument("--json", action="store_true"); a = p.parse_args()
    if a.list: print("\n".join(sorted({k for v in MODULE_KEYS.values() for k in v}))); return 0
    if a.module:
        if a.module not in MODULE_KEYS: print("unknown module: %s" % a.module, file=sys.stderr); return 2
        print("\n".join(MODULE_KEYS[a.module])); return 0
    if not a.key: print("--key is required unless --list or --module is used", file=sys.stderr); return 2
    try: result = render(a.key, a)
    except (KeyError, ValueError, OSError) as exc: print(str(exc), file=sys.stderr); return 3
    print(json.dumps(result, ensure_ascii=True) if a.json else result); return 0

if __name__ == "__main__": raise SystemExit(main())
