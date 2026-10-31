"""
产业深度分析报告 - MQL 数据查询脚本

数据获取由 Agent 通过 Execute_MQL 完成，本脚本提供：
1. MQL 报表路径常量与脚本生成（build_* 函数）
2. 数据格式化（format_* 函数）

MQL 报表路径映射（参考值，实际执行以 Search_Context 返回的 indicatorPath 为准）：

产业搜索（唯一可用路径；旧路径 564217624877789 不支持「产业类型」加载列过滤）:
  {Choice报表\\报表指标\\Choice金融终端\\产业链\\产业深度分析AI一页纸\\产业深度分析\\产业链首页_企业搜索|329428787766940}

市场主题结构:
  {Choice报表\\报表指标\\Choice金融终端\\产业链\\产业深度分析AI一页纸\\产业深度分析\\公司一页纸_产业深度分析_市场主题图谱|010679682450425}

标准产业中游:
  {Choice报表\\报表指标\\Choice金融终端\\产业链\\产业深度分析AI一页纸\\产业深度分析\\公司一页纸_产业深度分析_标准产业图谱(中游)|196487813508749}

标准产业上下游:
  {Choice报表\\报表指标\\Choice金融终端\\产业链\\产业深度分析AI一页纸\\产业深度分析\\公司一页纸_产业深度分析_标准产业图谱(上下游)|617118297459170}

指数基本信息:
  {Choice报表\\报表指标\\Choice金融终端\\指数F9\\一页纸\\指数基本信息|292749174710315}

指数业绩表现(周频):
  {Choice报表\\报表指标\\Choice金融终端\\指数F9\\一页纸\\指数F9_估值通道_周频|505321336674530}

成分股详情(综合):
  {Choice报表\\报表指标\\Choice金融终端\\指数F9\\一页纸\\指数F9_成分数据_成分股详情(综合)|676193052396478}
"""

import json
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "output"

# ---- MQL 报表路径常量 ----

# 产业搜索：必须用本路径（可用「产业类型」做 SetReportFilter 加载列过滤）。
# 旧路径 ...\A股专题\产业链\产业链首页_企业搜索|564217624877789 的加载列只有
# 「公司名称/证券简称」，写 SetReportFilter({产业类型}) 会报 MQL_PLAN_ERROR。
REPORT_CHAIN_SEARCH = (
    "{Choice报表\\报表指标\\Choice金融终端\\产业链\\"
    "产业深度分析AI一页纸\\产业深度分析\\产业链首页_企业搜索|329428787766940}"
)

REPORT_THEME_CHAIN_MAP = (
    "{Choice报表\\报表指标\\Choice金融终端\\产业链\\"
    "产业深度分析AI一页纸\\产业深度分析\\"
    "公司一页纸_产业深度分析_市场主题图谱|010679682450425}"
)

REPORT_STANDARD_CHAIN_MID = (
    "{Choice报表\\报表指标\\Choice金融终端\\产业链\\"
    "产业深度分析AI一页纸\\产业深度分析\\"
    "公司一页纸_产业深度分析_标准产业图谱(中游)|196487813508749}"
)

REPORT_STANDARD_CHAIN_REL = (
    "{Choice报表\\报表指标\\Choice金融终端\\产业链\\"
    "产业深度分析AI一页纸\\产业深度分析\\"
    "公司一页纸_产业深度分析_标准产业图谱(上下游)|617118297459170}"
)

REPORT_INDEX_PROFILE = (
    "{Choice报表\\报表指标\\Choice金融终端\\指数F9\\"
    "一页纸\\指数基本信息|292749174710315}"
)

REPORT_INDEX_VALUATION = (
    "{Choice报表\\报表指标\\Choice金融终端\\指数F9\\"
    "一页纸\\指数F9_估值通道_周频|505321336674530}"
)

REPORT_INDEX_CONSTITUENT = (
    "{Choice报表\\报表指标\\Choice金融终端\\指数F9\\"
    "一页纸\\指数F9_成分数据_成分股详情(综合)|676193052396478}"
)

# 指数成分行业分布：2026-10-02 实测 6 组参数均返回 0 行，当前不可用；
# 默认走兜底——从 REPORT_INDEX_CONSTITUENT 的「行业」字段聚合（见 SKILL 的 mql-recipes）。
REPORT_INDEX_COMP_INDUSTRY = (
    "{Choice报表\\报表指标\\Choice金融终端\\指数F9\\"
    "成分数据\\成分行业\\指数F9成分行业|828709189779714}"
)


def build_search_mql(topic: str, chain_type: str = "市场主题") -> str:
    """生成产业搜索 MQL 脚本。

    Args:
        topic: 产业关键词（如 "AI"、"新能源汽车"）
        chain_type: 产业类型（"市场主题" 或 "标准产业"）

    Returns:
        完整的 MQL 脚本字符串
    """
    return f"""ReportBlock(#1, {REPORT_CHAIN_SEARCH});
SetReportFilter(
    {{产业类型}} == "{chain_type}"
);
{{产业代码}}: REPORT_FIELD("产业代码");
{{产业名称}}: REPORT_FIELD("产业名称");
{{产品所属路径}}: REPORT_FIELD("产品所属路径(首页)");
FILTER_ROWS(LIKE({{产业名称}}, "{topic}"));"""


def build_structure_mql(type_code: str, chain_type: str) -> list[tuple[str, str]]:
    """生成产业结构查询 MQL 脚本列表。

    Returns:
        [(描述, MQL脚本), ...]
    """
    scripts = []

    if chain_type == "市场主题":
        scripts.append(("市场主题结构", f"""ReportBlock(#1, {REPORT_THEME_CHAIN_MAP});
SetReportFilter({{产业代码}} == "{type_code}");
{{产业位置}}: REPORT_FIELD("产业位置");
{{一级节点名称}}: REPORT_FIELD("一级节点名称");
{{二级节点名称}}: REPORT_FIELD("二级节点名称");
{{二级节点公司}}: REPORT_FIELD("二级节点公司");
{{三级节点名称}}: REPORT_FIELD("三级节点名称");
{{三级节点公司}}: REPORT_FIELD("三级节点公司");
{{四级节点名称}}: REPORT_FIELD("四级节点名称");
{{产业代码}}: REPORT_FIELD("产业代码");
{{产业名称}}: REPORT_FIELD("产业名称");"""))

    if chain_type == "标准产业":
        scripts.append(("标准产业中游", f"""ReportBlock(#1, {REPORT_STANDARD_CHAIN_MID});
SetReportFilter({{标准产业代码}} == "{type_code}");
{{细分产品名称}}: REPORT_FIELD("细分产品名称");
{{产品下公司}}: REPORT_FIELD("产品下公司");
{{标准产业代码}}: REPORT_FIELD("标准产业代码");
{{标准产业名称}}: REPORT_FIELD("标准产业名称");"""))

        scripts.append(("标准产业上下游", f"""ReportBlock(#1, {REPORT_STANDARD_CHAIN_REL});
SetReportFilter({{产业代码}} == "{type_code}");
{{产业位置}}: REPORT_FIELD("产业位置");
{{产业节点名称}}: REPORT_FIELD("产业节点名称");
{{产业节点下公司}}: REPORT_FIELD("产业节点下公司");
{{细分产品名称}}: REPORT_FIELD("细分产品名称");
{{节点关系}}: REPORT_FIELD("节点关系");
{{归类节点名称}}: REPORT_FIELD("归类节点名称");"""))

    return scripts


def build_index_profile_mql(type_code: str) -> str:
    """生成指数基本信息 MQL 脚本。

    产业指数代码规则：
    - 产业整体: {type_code}.EI
    - 上游: {type_code_base + 1}.EI
    - 中游: {type_code_base + 2}.EI
    - 下游: {type_code_base + 3}.EI
    """
    base = int(type_code)
    codes = [
        f"{type_code}.EI",
        f"{base + 1}.EI",
        f"{base + 2}.EI",
        f"{base + 3}.EI",
    ]
    codes_str = ",".join(f'"{c}"' for c in codes)

    return f"""ReportBlock(#1, {REPORT_INDEX_PROFILE});
SetCodes([{codes_str}]);
{{指数代码}}: REPORT_FIELD("指数代码");
{{指数名称}}: REPORT_FIELD("指数名称");
{{指数简称}}: REPORT_FIELD("指数简称");
{{指数简介}}: REPORT_FIELD("指数简介");
{{成分股数量}}: REPORT_FIELD("成分股数量");
{{加权方式}}: REPORT_FIELD("加权方式");
{{发布机构}}: REPORT_FIELD("发布机构");"""


def build_index_valuation_mql(type_code: str) -> str:
    """生成指数业绩表现（周频估值）MQL 脚本。"""
    base = int(type_code)
    codes = [
        f"{type_code}.EI",
        f"{base + 1}.EI",
        f"{base + 2}.EI",
        f"{base + 3}.EI",
    ]
    codes_str = ",".join(f'"{c}"' for c in codes)

    return f"""ReportBlock(#1, {REPORT_INDEX_VALUATION});
SetCodes([{codes_str}]);
{{证券代码}}: REPORT_FIELD("证券代码(带后缀)");
{{周交易日}}: REPORT_FIELD("周交易日");
{{收盘价}}: REPORT_FIELD("收盘价");
{{市盈率}}: REPORT_FIELD("市盈率(TTM)");
{{市净率}}: REPORT_FIELD("市净率(MRQ)");
{{市销率}}: REPORT_FIELD("市销率(TTM)");"""


def build_constituent_mql(type_code: str) -> str:
    """生成成分股详情 MQL 脚本。"""
    base = int(type_code)
    codes = [
        f"{type_code}.EI",
        f"{base + 1}.EI",
        f"{base + 2}.EI",
        f"{base + 3}.EI",
    ]
    codes_str = ",".join(f'"{c}"' for c in codes)

    return f"""ReportBlock(#1, {REPORT_INDEX_CONSTITUENT});
SetCodes([{codes_str}]);
SetReportFilter({{交易日期}} >= "{{{{最新成分交易日}}}}");
{{指数代码}}: REPORT_FIELD("指数代码");
{{证券代码}}: REPORT_FIELD("证券代码");
{{证券简称}}: REPORT_FIELD("证券简称");
{{总市值}}: REPORT_FIELD("总市值(亿元)");
{{权重}}: REPORT_FIELD("权重");
{{涨跌幅}}: REPORT_FIELD("涨跌幅");
{{行业}}: REPORT_FIELD("行业");
{{交易日期}}: REPORT_FIELD("交易日期");"""


def format_search_results(records: list[dict]) -> dict:
    """格式化产业搜索结果。"""
    market_themes = [r for r in records if r.get("chain_type") == "市场主题"]
    standard_chains = [r for r in records if r.get("chain_type") == "标准产业"]
    return {
        "market_themes": market_themes,
        "standard_chains": standard_chains,
        "total": len(market_themes) + len(standard_chains),
    }


def format_structure_data(data: dict) -> str:
    """格式化产业结构数据为可读文本。"""
    parts = []
    for direction, key in [("上游", "upstream"), ("中游", "midstream"), ("下游", "downstream")]:
        nodes = data.get(key, [])
        if nodes:
            parts.append(f"## {direction}")
            for node in nodes:
                name = node.get("node_name", node.get("一级节点名称", ""))
                companies = node.get("companies", node.get("二级节点公司", ""))
                parts.append(f"- **{name}**: {companies}")
    return "\n".join(parts)


def format_performance_data(records: list[dict]) -> str:
    """格式化指数表现数据为 Markdown 表格。"""
    if not records:
        return "无数据"

    headers = ["产业环节", "指数代码", "交易日", "收盘价", "PE(TTM)", "PB(MRQ)", "PS(TTM)"]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join([":---"] * len(headers)) + " |"]

    for rec in sorted(records, key=lambda x: x.get("TRADE_DATE", ""), reverse=True):
        row = [
            rec.get("segment", ""),
            rec.get("secucode", ""),
            rec.get("trade_date", ""),
            str(rec.get("close_price", "")),
            str(rec.get("pe_ttm", "")),
            str(rec.get("pb_mrq", "")),
            str(rec.get("ps_ttm", "")),
        ]
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def format_constituent_data(records: list[dict], top_n: int = 10) -> str:
    """格式化成分股数据为可读文本。"""
    if not records:
        return "无数据"

    total_mv = sum(r.get("total_mv", 0) or 0 for r in records)
    sorted_records = sorted(records, key=lambda x: x.get("total_mv", 0) or 0, reverse=True)

    lines = [f"共{len(records)}只成分股，总市值{total_mv:.2f}亿元。"]
    lines.append(f"\n前{top_n}大市值股：")

    for i, rec in enumerate(sorted_records[:top_n], 1):
        name = rec.get("security_name", "")
        code = rec.get("security_code", "")
        mv = rec.get("total_mv", 0)
        industry = rec.get("sw_industry", rec.get("行业", ""))
        lines.append(f"{i}. {name}({code}) 市值{mv:.0f}亿 所属行业：{industry}")

    return "\n".join(lines)


if __name__ == "__main__":
    # CLI 模式：输出 MQL 脚本供 Agent 执行
    import argparse

    parser = argparse.ArgumentParser(description="MQL 脚本生成工具")
    parser.add_argument("--action", type=str, required=True,
                        choices=["mql_search", "mql_structure", "mql_index_profile",
                                 "mql_index_valuation", "mql_constituent", "all_mql"],
                        help="生成哪种 MQL 脚本")
    parser.add_argument("--topic", type=str, help="产业关键词")
    parser.add_argument("--type_code", type=str, help="产业代码")
    parser.add_argument("--chain_type", type=str, default="市场主题", help="产业链类型")

    args = parser.parse_args()

    if args.action == "mql_search":
        if not args.topic:
            print("ERROR: 需要 --topic 参数", file=sys.stderr)
            sys.exit(1)
        print("=== 市场主题搜索 ===")
        print(build_search_mql(args.topic, "市场主题"))
        print("\n=== 标准产业搜索 ===")
        print(build_search_mql(args.topic, "标准产业"))

    elif args.action == "mql_structure":
        if not args.type_code:
            print("ERROR: 需要 --type_code 参数", file=sys.stderr)
            sys.exit(1)
        for desc, mql in build_structure_mql(args.type_code, args.chain_type):
            print(f"=== {desc} ===")
            print(mql)
            print()

    elif args.action == "mql_index_profile":
        if not args.type_code:
            print("ERROR: 需要 --type_code 参数", file=sys.stderr)
            sys.exit(1)
        print(build_index_profile_mql(args.type_code))

    elif args.action == "mql_index_valuation":
        if not args.type_code:
            print("ERROR: 需要 --type_code 参数", file=sys.stderr)
            sys.exit(1)
        print(build_index_valuation_mql(args.type_code))

    elif args.action == "mql_constituent":
        if not args.type_code:
            print("ERROR: 需要 --type_code 参数", file=sys.stderr)
            sys.exit(1)
        print(build_constituent_mql(args.type_code))

    elif args.action == "all_mql":
        if not args.type_code or not args.topic:
            print("ERROR: 需要 --type_code 和 --topic 参数", file=sys.stderr)
            sys.exit(1)
        print("=== 1. 产业搜索（市场主题） ===")
        print(build_search_mql(args.topic, "市场主题"))
        print("\n=== 2. 产业搜索（标准产业） ===")
        print(build_search_mql(args.topic, "标准产业"))
        print(f"\n=== 3. 产业结构（{args.chain_type}） ===")
        for desc, mql in build_structure_mql(args.type_code, args.chain_type):
            print(f"\n--- {desc} ---")
            print(mql)
        print("\n=== 4. 指数基本信息 ===")
        print(build_index_profile_mql(args.type_code))
        print("\n=== 5. 指数业绩表现（周频估值） ===")
        print(build_index_valuation_mql(args.type_code))
        print("\n=== 6. 成分股详情（综合） ===")
        print(build_constituent_mql(args.type_code))

    else:
        print("ERROR: 未知 action", file=sys.stderr)
        sys.exit(1)