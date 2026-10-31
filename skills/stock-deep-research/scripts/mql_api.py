#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公司一页纸 · MQL 取数封装（参考实现）

取数通道：MQL（妙想查询语言），统一由 mcp-mql-tools 一个服务提供
- 检索：mcp-mql-tools 的 Get_MQL_Reference / Search_Business_Knowledge / Search_Context
- 执行：mcp-mql-tools 的 Execute_MQL（不再需要单独的 runtime 服务）

本文件只做两件事：
1) 按章节把 MQL 脚本拼装成可执行文本（降低手写语法错误的概率）；
2) 对 MQL 返回结果做口径加工（单位换算 / 汇率折算 / "其他"客户供应商二次计算）。

重要约定
- **零检索快车道**：`PINNED_REPORTS` 收录了 2026-10-01 实测跑通的 F9 报表完整路径（含 |metricId）
  与字段中文名。命中时**直接使用**，无需 Search_Business_Knowledge / Search_Context；
  仅保留 Get_MQL_Reference 做版本校验。详见 reference/MQL-报表路径固化表.md。
- 固化表未收录的对象，走完整检索流程（Get_MQL_Reference -> Search_Business_Knowledge
  -> Search_Context -> Execute_MQL）；"未实测基线路径"不落在本文件中，只在
  reference/沪深京-分章节MQL清单.md / reference/港股-分章节MQL清单.md 内作为检索词提示。
- MQL 报表字段一律用中文返回列名（reportFields[].column_name_cn）；
  旧妙想 MCP 通道的 OPERATE_INCOME / REPORT_DATE 等物理字段代码在 MQL 中无效。
- 路径一律单反斜杠（Python 字符串中写作 "\\\\" 或使用 r"" 原始串）。
- 报告期集合口径（4.2 / 7.2「最新报告期 + 近 5 个年报期」、8.1 历史年）见
  MQL-取数规程 §11：通过传参一次表达，**不做本地二次筛选去重**；
  对应工具函数：period_param_array / annual_window_filter / history_annual_periods。
- 4.2 / 7.2 成表时的「整列为空的报告期不展示」属**展示层**，实现在
  scripts/build_report.py 的 drop_all_empty_periods()（每表独立判定，两表列集合可不同），
  不在本文件内，且**不改报告期窗口口径**（规程 §11.2 第 4 条）。
- **8.1 一致预测表的指标行是固定表结构**：行名与行序由 `TABLE_8_1_ROWS`
  （沪深京 10 行 / 港股 9 行）机读固化，**一行都不得少返回**；某期无值即单元格留空、
  整行照常渲染，不得删行。行名/行序的权威副本**共 9 处**（清单见
  reference/报告版式与图表规范.md §8.1），任一处改动必须全部同步。
- **取数脚本一次成型**：`build_script()`（CLI：`--script <批次名>`）按批次一次产出整段可执行 MQL——
  **Block 编号由脚本自动连续分配（1..N，声明即分配，不可跳号/重号）**，
  每类报表的加载列传参**顺序固定**（见 `report_params()` / `PARAM_ORDER_HINT`），
  生成结果可再用 `check_mql_script()`（CLI：`--check`）自检，
  从源头消除"编号跳号 + 参数乱序"引起的语法返工。详见 reference/取数脚本一次成型.md。
"""
from __future__ import annotations
import datetime as _dt
import csv
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

# ------------------------------------------------------------------ 口径工具

def five_year_window(today: Optional[_dt.date] = None) -> tuple[str, str]:
    """近5年滑动窗口：例今天2026-06-12 -> ('2021-06-13', '2026-06-12')"""
    t = today or _dt.date.today()
    return (str(t.replace(year=t.year - 5) + _dt.timedelta(days=1)), str(t))


def q4_expr(n: int) -> str:
    """第 n 个年报的报告期动态函数字面量（MQL 内使用，含转义双引号）。

    q4_expr(1) -> 'GetReportDate(1, \\"Q4\\")'   最近 1 个年报
    q4_expr(2) -> 'GetReportDate(2, \\"Q4\\")'   2 年前年报
    """
    return f'GetReportDate({n}, \\"Q4\\")'


MQ_MRQ = '最新一期(MRQ)'
"""最新报告期（含中报/季报）的选项原文，来自候选 parameters[].options。"""


# -------- 报告期集合口径（MQL-取数规程 §11，2026-09-22 用户确认）--------
# 结论：4.2 / 7.2 的「最新报告期 + 近 5 个年报期」通过传参一次表达，
#       执行后【不做】本地二次筛选或去重。8.1 历史年（A）= 最近 3 个已披露年报期。

N_ANNUAL = 5           # 4.2 / 7.2 表：近 5 个年报期
N_HISTORY_A = 3        # 8.1 表：3 个历史年（A）= 最近 3 个已披露年报期


def period_param_values(with_latest: bool = True, n_annual: int = N_ANNUAL) -> List[str]:
    """报告期参数的多值列表（MQL 数组字面量元素，形态 B 用）。

    仅当候选 parameters[].options 已声明这些取值原文时才可使用；
    返回的字符串已含 MQL 内层转义双引号，可直接拼进 {"报告期"} = [...]。
    """
    vals = [f'"{q4_expr(i)}"' for i in range(1, n_annual + 1)]
    if with_latest:
        vals.insert(0, f'"{MQ_MRQ}"')
    return vals


def period_param_array(with_latest: bool = True, n_annual: int = N_ANNUAL) -> str:
    """形态 B：`{"报告期"} = ["最新一期(MRQ)", "GetReportDate(1, \\"Q4\\")", ...]`"""
    return "[" + ", ".join(period_param_values(with_latest, n_annual)) + "]"


def annual_window_filter(date_col_cn: str, latest_flag_col_cn: Optional[str] = None,
                         today: Optional[_dt.date] = None) -> str:
    """形态 A：`SetReportFilter` 条件 ——「（报告期窗口）OR（最新报告期标志 == "1"）」。

    date_col_cn        : 报告期加载列中文名（reportFilterColumns[].column_name_cn）
    latest_flag_col_cn : 最新报告期标志加载列中文名；None 表示该候选没有该列，
                         此时退化为「窗口内年报」（最新报告期另取一次做并集，不做行级去重）
    """
    start, end = five_year_window(today)
    win = f'({mql_ref(date_col_cn)} >= "{start}" AND {mql_ref(date_col_cn)} <= "{end}")'
    if not latest_flag_col_cn:
        return win
    return f'({win} OR {mql_ref(latest_flag_col_cn)} == "1")'


def mql_ref(name_cn: str) -> str:
    """中文列名 -> MQL 花括号引用（参数名/加载列名）。"""
    return "{" + name_cn + "}"


def history_annual_periods(n_annual: int = N_HISTORY_A) -> List[str]:
    """8.1 历史年（A）的报告期取值：最近 n 个已披露年报期（默认近 3 个）。"""
    return [f'"{q4_expr(i)}"' for i in range(1, n_annual + 1)]


def mql_str(s: str) -> str:
    """转成 MQL 双引号字符串（内部双引号转义）。"""
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def set_codes(codes: Sequence[str]) -> str:
    return "SetCodes([" + ", ".join(mql_str(c) for c in codes) + "]);"


# ------------------------------------------------------------------ 脚本拼装

class Block:
    """一个 MQL Block 的语句累加器；str(block) 得到完整脚本片段。"""

    def __init__(self, kind: str, block_id: int, decl: str) -> None:
        self.kind = kind
        self.id = block_id
        self.decl = decl
        self._lines: List[str] = []
        self._output = False

    def add(self, line: str) -> "Block":
        if line and not line.endswith(";"):
            line += ";"
        self._lines.append(line)
        return self

    def output(self) -> "Block":
        self._output = True
        return self

    def render(self) -> str:
        out = [self.decl] + self._lines
        if self._output:
            out.append("OutputBlock();")
        return "\n".join(out)


def report_block(block_id: int, report_path: str) -> Block:
    """ReportBlock：读报表明细；report_path 为带 |指标ID 后缀的完整报表路径。"""
    return Block("ReportBlock", block_id, f"ReportBlock(#{block_id}, {{{report_path}}});")


def cross_section(block_id: int) -> Block:
    """CrossSectionBlock：每代码一个值（单点指标）。"""
    return Block("CrossSectionBlock", block_id, f"CrossSectionBlock(#{block_id}, {{EM_CODE}});")


def time_series(block_id: int) -> Block:
    """TimeSeriesBlock：时序指标。"""
    return Block("TimeSeriesBlock", block_id,
                 f"TimeSeriesBlock(#{block_id}, {{EM_DATE}}, {{EM_CODE}});")


def set_report_filter(*conditions: str) -> str:
    """SetReportFilter：只能用加载列中文名；等值条件用 ==。"""
    return "SetReportFilter(" + "\n    AND ".join(conditions) + ");"


def filter_rows(*conditions: str) -> str:
    """FILTER_ROWS：一条完整筛选，条件内部用括号组织逻辑。"""
    return "FILTER_ROWS(" + " AND ".join(f"({c})" for c in conditions) + ");"


def set_window(start: str, end: str, period: str, market: Optional[str] = None) -> str:
    """SetWindow。period: 日/周/月/年；报告期时序指标(_s) 只能用 季/年 且不写 market。"""
    parts = [f'{{开始时间}} = {mql_str(start)}',
             f'{{结束时间}} = {mql_str(end)}',
             f'{{周期}} = {mql_str(period)}']
    if market:
        parts.append(f'{{市场类型}} = {mql_str(market)}')
    return "SetWindow(\n    " + ",\n    ".join(parts) + "\n);"


def field(name_cn: str, out_name: Optional[str] = None) -> str:
    """报表返回列 -> 输出列；name_cn 必须是 reportFields 里的中文列名。"""
    return f"{{{out_name or name_cn}}}: REPORT_FIELD({mql_str(name_cn)});"


def indicator(path: str, out_name: str, params: Optional[Dict[str, str]] = None) -> str:
    """普通指标调用 -> 输出列。params 的 value 需已包含 MQL 引号/花括号或为数值字面量。

    indicator(p, "涨跌幅", {"交易日期": '"2026-08-20"'})
    """
    if not params:
        return f"{{{out_name}}}: {{{path}}}();"
    kv = ",\n    ".join(f"{{{k}}} = {v}" for k, v in params.items())
    return f"{{{out_name}}}: {{{path}}}(\n    {kv}\n);"


# ------------------------------------------------------------------ 结果加工

def fmt_yi(amount: Any, rate: float = 1.0) -> str:
    """金额 -> 人民币亿元，保留2位小数；None/非法值返回空串（零幻觉：不造数）"""
    try:
        v = float(amount)
    except (TypeError, ValueError):
        return ""
    return f"{v * rate / 1e8:.2f}"


def pct2(v: Any) -> str:
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return ""


def others_amount(first_amount: float, first_ratio: float, top5_amount_sum: float) -> float:
    """其他客户/供应商金额 = 第一名金额*100/第一名占比 - sum(前五名金额)"""
    return first_amount * 100 / first_ratio - top5_amount_sum


def others_ratio(top5_ratio_sum: float) -> float:
    """其他客户/供应商占比 = 100 - sum(前五名占比)"""
    return 100 - top5_ratio_sum


def report_date_str(d: Any) -> str:
    """'2025-12-31 00:00:00' -> '2025-12-31'"""
    return str(d)[:10] if d else ""


def _read_result_file(path: str) -> List[Dict[str, Any]]:
    """读取 Execute_MQL 大结果集落盘文件。支持 JSON/JSONL/CSV。"""
    if not path:
        return []
    lower = path.lower()
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        if lower.endswith(".jsonl"):
            return [json.loads(line) for line in f if line.strip()]
        if lower.endswith(".csv"):
            return list(csv.DictReader(f))
        payload = json.load(f)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        rows = payload.get("rows")
        if isinstance(rows, list):
            return rows
        data = payload.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            return data["rows"]
    return []


def read_block_result(result: Dict[str, Any], block_id: int) -> List[Dict[str, Any]]:
    """从 Execute_MQL 返回中取某个 Block 的行。

    - 常规：results[].rows
    - 大结果集：Block 落盘，优先读取 result_file.path，避免把无内联 rows 误判为无数据
    """
    for blk in (result.get("results") or []):
        if blk.get("blockId") == block_id:
            rows = blk.get("rows")
            if rows:
                return rows
            rf = blk.get("result_file") or blk.get("resultFile") or {}
            if isinstance(rf, dict) and rf.get("path"):
                return _read_result_file(rf["path"])
            if isinstance(rf, str):
                return _read_result_file(rf)
            return []
    return []


# ------------------------------------------------------------------ 固化路径（零检索直取）
# ✅ 2026-10-01 由 Search_Context 实测返回 + Execute_MQL 跑通验证。
#    命中时直接使用，**无需**再调 Search_Business_Knowledge / Search_Context。
#    详见 reference/MQL-报表路径固化表.md。
#
# 结构：市场 -> 逻辑名 -> {"path": 完整引用(含|metricId), "fields": {展示名: 中文列名}, "flags": 加载列}

PINNED_REPORTS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "沪深京": {
        "公司介绍": {
            "path": r"Choice报表\报表指标\服务端\妙想服务\量化查数\A股\F9\公司一页纸\公司简介\沪深F9_基础资料_公司介绍|233401653044996",
            "fields": {
                "证券代码": "证券代码(带后缀)",
                "证券简称": "证券简称",
                "公司简介": "公司简介",
                "主营业务": "主营产品/主营业务",
                "实际控制人": "实际控制人",
                "董事长": "董事长",
                "总经理": "总经理",
                "上市日期": "上市日期",
                "上市状态": "上市状态",
                "最新年报报告期": "最新年报报告期",
                "第一大股东": "第一大股东",
                "第一大股东持股比例": "第一大股东持股比例",
            },
            # 加载列（reportFilterColumns）为空 → 无需 SetReportFilter，只 SetCodes。
            # 2026-10-03 实测：reportFields 含 公司简介/主营产品/实际控制人/上市状态/最新年报报告期 等 47 列。
            "note": "上市状态非正常上市 → 0 前置终止；`最新年报报告期` 用于确定批次 3 的报告期基准。",
        },
        "高级管理人员": {
            "path": r"Choice报表\报表指标\服务端\妙想服务\量化查数\A股\F9\公司一页纸\公司简介\沪深F9_公司基本资料_高级管理人员|298190295923428",
            "fields": {
                "姓名": "姓名",
                "职务": "职务",
                "任职起始日": "任职起始日",
                "最高学历": "最高学历",
                "简历": "简历",
            },
            # 该报表语义即"高级管理人员(现任)"，无需再用在职状态字段过滤。
            # 2026-10-03 实测：reportFields = 姓名/职务/任职起始日/最高学历/简历/性别/出生日期/国籍/任职终止日/证券代码(带后缀)。
            "note": "返回列已实测采集（2026-10-03 Search_Context）；加载列为空 → 无需 SetReportFilter。",
        },
        "主营构成": {
            "path": r"Choice报表\报表指标\Choice金融终端\A股F9\公司一页纸\公司业务拆分\主营标准化平台_主表|834360480555928",
            "fields": {
                "项目名称": "项目名称",
                "统计维度名称": "统计维度名称",
                "层级": "层级",
                "数据值": "数据值",
                "是否为百分比": "是否为百分比",
                "数据类型": "数据类型",
                "报告期": "报告期",
                "报告期类型编码": "报告期类型编码",
                "是否最新报告期": "是否最新报告期",
                "证券简称": "证券简称",
                "币种(中文)": "币种(中文)",
                "展示顺序": "展示顺序",
                "分组": "分组",
            },
            # 2026-10-03 实测：加载列 = 报告期类型编码(001年报/002中报/003一季报/004三季报)、
            # 数据类型(指标数值/结构百分比)、是否最新报告期(1是/0否)、报告期(date)。
            # 报告期窗口按规程 §11：近 5 年年报 OR 最新报告期，一次表达。
            "params": [
                {"kind": "union", "annual_col": "报告期类型编码", "annual_value": "001",
                 "date_col": "报告期", "latest_col": "是否最新报告期",
                 "desc": "报告期 = 近 5 年窗口内年报 OR 最新报告期（规程 §11）"},
            ],
        },
        "客户供应商": {
            "path": r"Choice报表\报表指标\Choice金融终端\A股F9\公司一页纸\公司产销链分析\主要客户情况和主要供应商情况|464277271454376",
            "fields": {
                "客户类型": "客户类型",
                "金额": "金额",
                "占比": "占全部营业收入比例 ",
                "名次": "名次",
                "排名": "排名",
                "报告期": "报告期",
                "报告期名称": "报告期名称",
                "证券简称": "证券简称",
            },
            # ⚠️ 2026-10-03 实测修正（二）：本报表实际加载列 = 是否最新报告期(1是/0否, string)、
            # 报表日期(date, yyyy-MM-dd)、报告期类型编码(1一季报/5中报/3三季报/6年报, string)。
            # 但服务端"报表数据量预估"强制要求 filter 含 REPORT_TYPE_CODE|IS_MAXREPORTDATE **且** TYPE，
            # 而 客户类型(客户/供应商) 是返回列、不能写入 SetReportFilter（执行器 metadata 阶段校验拒绝）
            # → 该报表当前在执行器侧不可执行（服务端预估器与元数据不一致），章节 5 降级为仅保留一级章标题。
            # 待服务端修复后：恢复 TYPE 过滤或放开 客户类型 作加载列，即可一次取回 5.1+5.2。
            "params": [
                {"kind": "eq", "col": "报表日期", "from": "report_date", "optional": True,
                 "desc": "报表日期（最近一个已披露年报期，如 2025-12-31）；未提供时省略该条件"},
            ],
        },
        "研发支出": {
            # ⚠️ 2026-10-03 实测：三个别名（量化查数 / Choice金融终端 / API专题报表函数）在执行器
            # "报表数据量预估"阶段均报 remote_rejected"报表名称不能为空"（服务端预估库缺报表名），
            # 该报表暂不可执行 → 已从 SCRIPTS 批次中移除。章节 6 的研发支出/研发费用率
            # 改用「财务摘要报告期」返回列 `研发支出`（同 MQL 通道）供数。
            "path": r"Choice报表\报表指标\服务端\妙想服务\量化查数\A股\F9\公司一页纸\公司研发实力\沪深F9_财务附注_研发支出|372228366512753",
            "fields": {
                "转换后科目名称": "转换后科目名称",
                "项目金额": "项目金额",
                "报告期": "报告期",
                "报告年度": "报告年度",
                "报告期类型编码": "报告期类型编码",
                "证券简称": "证券简称",
            },
            # 2026-10-03 实测：加载列 = 报告期(date)、报告期类型编码(1一季报/5中报/3三季报/6年报)。
            "params": [
                {"kind": "annual", "col": "报告期类型编码", "value": "6", "date_col": "报告期",
                 "desc": "近 5 年窗口内年报（报告期类型编码=6）"},
            ],
        },
        "员工构成": {
            "path": r"Choice报表\报表指标\服务端\妙想服务\量化查数\A股\F9\公司一页纸\公司研发实力\沪深F9_基础资料_员工构成|440316368767118",
            "fields": {
                "研发人员": "研发人员",
                "职工总数": "职工总数",
                "技术人员": "技术人员",
                "博士": "博士",
                "硕士": "硕士",
                "本科": "本科",
                "专科": "专科",
                "中专及以下": "中专及以下",
                "人均创收": "人均创收",
                "人均创利": "人均创利",
                "报告期": "报告期",
                "证券简称": "证券简称",
            },
            # 2026-10-03 实测：加载列 = 报告期(date)。
            "params": [
                {"kind": "window", "col": "报告期",
                 "desc": "近 5 年窗口内报告期"},
            ],
        },
        "专利信息": {
            "path": r"Choice报表\报表指标\Choice金融终端\A股F9\公司一页纸\公司研发实力\公司一页纸_上市公司专利信息|453514830402110",
            "fields": {
                "专利合计": "报告期末累计拥有专利合计数量",
                "发明专利": "报告期末累计拥有发明专利数量",
                "实用新型专利": "报告期末累计拥有实用新型专利数量",
                "外观设计专利": "报告期末累计拥有外观设计专利数量",
                "国际专利": "报告期末累计拥有国际专利数量",
                "截止日期": "截止日期",
            },
            # 2026-10-03 实测：该路径仅 1 个加载列 系统日期(date)；不做过滤，直接 SetCodes 取全量后取最新行。
        },
        "财务摘要报告期": {
            "path": r"Choice报表\报表指标\服务端\妙想服务\量化查数\A股\F9\财务摘要报告期|709806706862950",
            "fields": {
                "证券代码": "证券代码",
                "报告期": "报告日期",
                "是否最新报告期": "是否最新报告期",
                "营业总收入": "营业总收入",
                "归属于母公司股东的净利润": "归属于母公司股东的净利润",
                "扣除非经常性损益后归属于母公司股东的净利润": "扣除非经常性损益后归属于母公司股东的净利润",
                "销售毛利率": "销售毛利率",
                "销售净利率": "销售净利率",
                "ROE(加权)": "ROE(加权)",
                "经营活动产生的现金流量净额": "经营活动产生的现金流量净额",
                "资产负债率": "资产负债率",
                "EPS(基本)": "EPS(基本)",
                "研发支出": "研发支出",
            },
            # 2026-10-03 实测：reportStandardCodeSupported=false → 禁止 SetCodes/GetSectors，
            # 证券范围改由返回列 `证券代码` 本地 FILTER_ROWS 过滤（local_scope）。
            # 加载列枚举：报告期类型编码(1一季报/5中报/3三季报/6年报/8其它/7最新)、
            # 合并类型(1合并报表/2调整/3母公司/4母公司调整)、是否最新(1_是)、报表合并类型编码(1业绩快报/2普通报表/3盈利预测)。
            "local_scope": {"field": "证券代码"},
            "params": [
                # 2026-10-03 实测：该报表 reportStandardCodeSupported=false 且服务端
                # "报表数据量预估"要求 ORG_CODE|SECUCODE 至少其一 → 用加载列 公司代码(ORG_CODE)
                # 远端过滤（取值来自 公司介绍.机构代码，按标的传入 --org-code）。
                {"kind": "eq", "col": "公司代码", "from": "org_code", "optional": True,
                 "desc": "机构代码（来自 公司介绍.机构代码，如 300476.SZ → 10329296）；未提供时省略"},
                {"kind": "union", "annual_col": "报告期类型编码", "annual_value": "6",
                 "date_col": "报告期", "latest_col": "是否最新",
                 "desc": "报告期 = 近 5 年窗口内年报 OR 最新报告期（规程 §11）"},
                {"kind": "eq", "col": "合并类型", "value": "1",
                 "desc": "合并报表"},
                {"kind": "eq", "col": "报表合并类型编码", "value": "2",
                 "desc": "普通报表"},
            ],
        },
        "一致预测": {
            "path": r"Choice报表\报表指标\服务端\妙想服务\量化查数\A股\F9\公司一页纸\公司盈利预测\股票F9_盈利预测_一致预测|145968192392335",
            "fields": {
                "证券代码": "证券代码(带后缀)",
                "证券名称": "证券名称",
                "年份": "年份",
                "EPS": "EPS(摊薄)(元)",
                "营业总收入": "营业总收入(元)",
                "营业收入增长率": "营业收入增长率(%)",
                "归母净利润": "归母净利润(元)",
                "归母净利润增长率": "归母净利润增长率(%)",
                "PE": "PE",
                "PEG": "PEG",
                "ROA": "ROA(%)",
                "ROE": "ROE(摊薄)(%)",
                "基准股本": "基准股本(元)",
            },
            "flags": {"评级综合值周期": [30, 90, 180]},
            "params": [
                {"kind": "eq", "col": "评级综合值周期", "from": "rating_cycle", "optional": True,
                 "desc": "加载列枚举 30 / 90 / 180；默认不写该条件（返回三档，成表前须归一到同一档位），传 --rating-cycle 90 可远端只取一档"},
            ],
        },
    },
    "港股": {
        "公司简况": {
            "path": r"Choice报表\报表指标\Choice金融终端\港股F9\公司一页纸\公司简介\港股F9_资料_公司简况|922975114034125",
            "fields": {
                "公司名称": "公司名称",
                "公司业务": "公司业务",
                "成立日期": "成立日期",
                "董事长": "董事长",
                "员工人数": "员工人数",
                "所属港交所行业": "所属港交所行业",
                "上市状态": "上市状态",
            },
            # 加载列为空（reportFilterColumns 为空数组）→ 无需 SetReportFilter。
        },
        "董事会与高管": {
            "path": r"Choice报表\报表指标\Choice金融终端\港股F9\公司一页纸\公司简介\港股F9_董事会与高管|478933104602547",
            "fields": {
                "人员姓名": "人员姓名",
                "职务名称": "职务名称",
                "任职状态": "任职状态",
            },
            "flags": {"任职状态": [], "职务类型": []},
            # 加载列顺序固定为「任职状态 → 职务类型」；两者枚举值尚未采集 → 暂不自动生成
            # SetReportFilter，待补录进本注册表后由 --script 自动带上。
            "fields_unverified": True,
            "note": "`任职状态` / `职务类型` 的枚举值尚未采集（固化表 §4.1 待补项）；过滤“现任”须先用一次 Search_Context 拿枚举并补录。",
        },
        "主营构成": {
            "path": r"Choice报表\报表指标\Choice金融终端\港股F9\公司一页纸\公司业务拆分\港股F9_主营构成_汇总|251228110707503",
            "fields": {
                "标准产品名称": "标准产品名称",
                "主营业务收入": "主营业务收入",
                "收入构成": "收入构成",
                "毛利率": "毛利率",
                "标准报告期": "标准报告期",
                "中文币种": "中文币种",
            },
            "flags": {
                "分布类型": ["1", "2"],
                "报告期类型编码": ["1", "2", "3", "4", "5"],
                "数据类型": ["1", "3"],
                "是否最新报告期": ["1", "0"],
            },
            # 参数顺序固定：分布类型 → 数据类型 →（报告期窗口并最新）→ 标准报表日期
            "params": [
                {"kind": "eq", "col": "分布类型", "value": "1",
                 "desc": "1：产品（板块维度取按产品）"},
                {"kind": "eq", "col": "数据类型", "value": "1",
                 "desc": "1：普通报表"},
                {"kind": "union", "annual_col": "报告期类型编码", "annual_value": "4",
                 "date_col": "标准报表日期", "latest_col": "是否最新报告期",
                 "desc": "报告期 = 近 5 年窗口内年报 OR 最新报告期（一次表达，不做本地二次筛选，规程 §11）"},
            ],
        },
        "财务分析摘要": {
            "path": r"Choice报表\报表指标\Choice金融终端\港股F9\公司一页纸\公司财务分析\港股F9_财务分析_财务分析摘要|068207929498612",
            "fields": {
                "报表日期": "报表日期",
                "销售毛利率": "销售毛利率(%)",
                "销售净利率": "销售净利率(%)",
                "净资产收益率平均": "净资产收益率(平均)(%)",
                "资产负债率": "资产负债率(%)",
                "归属母公司净利润TTM": "归属母公司净利润(TTM)(元)",
                "经营活动现金流量净额TTM": "经营活动产生的现金流量净额(TTM)(元)",
                "原始币种": "原始币种",
            },
            "note": "比率类六项（毛利率/净利率/ROE/资产负债率/归母净利润TTM/经营现金流TTM）一律优先取本表一次取全。",
        },
        "利润表GSD": {
            "path": r"Choice报表\报表指标\Choice金融终端\港股F9\公司一页纸\公司财务分析\港股F9_利润表GSD|196772091948400",
            "fields": {
                "报告期": "报告期",
                "科目编码": "科目编码",
                "科目名称": "科目名称(调整)",
                "科目值": "科目值",
                "币种": "币种",
            },
            "flags": {
                "报告期类型编码": ["001", "002", "003", "004", "005", "999"],
                "报表类型编码": ["1", "2", "3", "4"],
                "上市标识编码": ["1", "0"],
                "是否最新报告期": ["1", "0"],
            },
            "note": "加载列枚举已采集，但该表的报告期窗口写法未实测 → 暂不自动生成 SetReportFilter；需要时按规程 §11 形态 A 手写并回写本注册表。",
        },
        "现金流量表GSD": {
            "path": r"Choice报表\报表指标\Choice金融终端\港股F9\公司一页纸\公司财务分析\港股F9_现金流量表GSD|410958025816791",
            "fields": {
                "报告期": "报告期",
                "科目编码": "科目编码",
                "科目名称": "科目名称(调整)",
                "科目值": "科目值",
                "币种": "币种",
            },
            "flags": {
                "报告期类型编码": ["001", "002", "003", "004", "005", "999"],
                "报表类型编码": ["1", "2", "3", "4"],
                "上市标识编码": ["1", "0"],
                "是否最新报告期": ["1", "0"],
            },
            "note": "同「利润表GSD」：加载列枚举已采集，报告期窗口写法未实测 → 暂不自动生成 SetReportFilter。",
        },
        "一致预测": {
            "path": r"Choice报表\报表指标\Choice金融终端\港股F9\公司一页纸\公司盈利预测\港美股F9_盈利预测_一致预测|598262128582362",
            "fields": {
                "证券名称": "证券名称",
                "预测年度": "预测年度",
                "年度标志": "年度标志",
                "EPS": "EPS(稀释)",
                "营业收入": "营业收入",
                "营业收入增长率": "营业收入增长率",
                "归母净利润": "归母净利润",
                "归母净利润增长率": "归母净利润增长率",
                "PE": "PE",
                "PEG": "PEG",
                "ROA": "ROA",
                "ROE": "ROE(摊薄)",
            },
            "flags": {"评级综合周期": []},
            "params": [
                {"kind": "in", "col": "评级综合周期", "values": [999, 180],
                 "desc": "取最新档与 180 日档（固化表 §2.4 实测写法）"},
            ],
        },
    },
}


def pinned_report(market: str, name: str) -> Dict[str, Any]:
    """取固化报表条目；未收录返回 {}，调用方据此回退标准检索。"""
    return (PINNED_REPORTS.get(market) or {}).get(name) or {}


# ============================================================
# 8.1 一致预测表：固定指标行（机读定义，行名/行序不得少改）
# ============================================================
# `key` 指向 PINNED_REPORTS[<市场>]["一致预测"]["fields"] 的逻辑键（该键再映射到报表中文返回列）；
# `key_hk` 为港股同义列的键（港股无「营业总收入」列名，用「营业收入」）；缺省时沿用 `key`。
# `transform` 为展示单位换算口径。⚠️ 行名/行序的权威副本**共 9 处**：
#   reference/报告版式与图表规范.md §8.1（清单与行↔列映射）/ MQL-报表路径固化表.md §1.7 /
#   沪深京·港股分章节MQL清单.md §8.1 / prompts/08 / 章节示例对照表.md /
#   reference/输出契约与数据契约.md §1（v2.6.0 起，原 SKILL.md Output Contract 已拆至该文件）/
#   本常量 / validate_report.py 的 CONSENSUS_ROWS_8_1 —— 任一处改动必须全部同步。
TABLE_8_1_ROWS: List[Dict[str, str]] = [
    {"label": "营业总收入(亿元)",   "key": "营业总收入",     "key_hk": "营业收入",     "transform": "÷ 1e8"},
    {"label": "营业总收入增长率(%)", "key": "营业收入增长率", "key_hk": "营业收入增长率", "transform": "原值"},
    {"label": "归母净利润(亿元)",   "key": "归母净利润",     "key_hk": "归母净利润",   "transform": "÷ 1e8"},
    {"label": "归母净利润增长率(%)", "key": "归母净利润增长率", "key_hk": "归母净利润增长率", "transform": "原值"},
    {"label": "EPS(稀释)",         "key": "EPS",           "key_hk": "EPS",         "transform": "原值"},
    {"label": "基准股本(百万股)",   "key": "基准股本",       "key_hk": "",           "transform": "÷ 1e6"},
    {"label": "ROE(摊薄)(%)",      "key": "ROE",           "key_hk": "ROE",         "transform": "原值"},
    {"label": "ROA(%)",            "key": "ROA",           "key_hk": "ROA",         "transform": "原值"},
    {"label": "PE",               "key": "PE",            "key_hk": "PE",          "transform": "原值"},
    {"label": "PEG",              "key": "PEG",           "key_hk": "PEG",         "transform": "原值"},
]
"""8.1 表格指标行（沪深京，10 行）——行名与行序逐字固定，**一行都不得少返回**。"""


def table_8_1_rows(market: str = "沪深京") -> List[Dict[str, str]]:
    """8.1 一致预测表的固定指标行（沪深京 10 行 / 港股 9 行）。

    港股：去掉「基准股本(百万股)」（港股一致预测报表无该列），并把 `key` 换成 `key_hk`
    （港股同义列名为「营业收入」，无「营业总收入」）。
    """
    if market == "港股":
        out = []
        for r in TABLE_8_1_ROWS:
            if not r["key_hk"]:            # 港股无该行数据源 → 整行不渲染
                continue
            out.append({**r, "key": r["key_hk"]})
        return out
    return [dict(r) for r in TABLE_8_1_ROWS]


def table_8_1_missing_keys(market: str = "沪深京") -> List[str]:
    """自查：8.1 各指标行在固化表 fields 中是否都有对应取数列；返回缺失行名（空 = 齐全）。"""
    fmap = pinned_report(market, "一致预测").get("fields") or {}
    return [r["label"] for r in table_8_1_rows(market) if r["key"] not in fmap]


# ============================================================
# 「取数脚本一次成型」：Block 编号连续 + 加载列参数顺序固定
# ============================================================
# 设计目标：把「手写 MQL Block」这件事彻底交给脚本，消除两类高频返工——
#   ① Block 编号跳号 / 重号（规程 §7.9：编号唯一递增，只能引用更小编号）；
#   ② 加载列 SetReportFilter 条件顺序随手写（同一事实出现多种顺序，易漏参、易错引号）。
# 用法：build_script(market, 脚本名, code) → 整段可执行 MQL，可直接交给 Execute_MQL。
#       生成后可用 check_mql_script(text) 自检；CLI 见 --script / --check / --params。
# ⚠️ 脚本名（批次名）与 reference/MQL-取数规程.md §8 的批次编排对应，**改动须两处同步**。

PARAM_ORDER_HINT = (
    "SetReportFilter 的条件顺序**固定**为加载列在 PINNED_REPORTS[...]['params'] 中的声明顺序"
    "（打印见 report_params() / param_order()）；AND 语义与顺序无关，固定顺序只为消除返工、便于逐字比对。"
    "证券范围一律由 SetCodes 表达，不重复写进 SetReportFilter。"
)


def report_params(market: str, name: str) -> List[Dict[str, Any]]:
    """取某报表的加载列传参声明（**顺序即固定写序**）；未声明返回 []。"""
    return list(pinned_report(market, name).get("params") or [])


def param_order(market: str, name: str) -> List[str]:
    """某报表加载列的固定顺序（列中文名列表），供打印 / 比对。"""
    out: List[str] = []
    for p in report_params(market, name):
        if p.get("kind") == "union":
            out.extend([p["annual_col"], p["date_col"], p["latest_col"]])
        else:
            out.append(p["col"])
    return out


def _lit(v: Any) -> str:
    """MQL 字面量：int / float 原样（不加引号）；字符串加双引号并转义内部引号。"""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    return mql_str(str(v))


def _filter_condition(spec: Dict[str, Any], ctx: Dict[str, Any]) -> tuple:
    """把一条参数声明渲染为单个筛选条件；返回 (条件文本或 None, 提示文本)。"""
    kind = spec.get("kind", "eq")
    if kind == "union":
        start, end = five_year_window()
        col = mql_ref(spec["annual_col"])
        dcol = mql_ref(spec["date_col"])
        cond = (f'(({col} == {_lit(spec["annual_value"])}'
                f' AND {dcol} >= "{start}" AND {dcol} <= "{end}")'
                f' OR {mql_ref(spec["latest_col"])} == "1")')
        return cond, ""
    if kind == "annual":
        # 近 5 年窗口内年报：{类型列} == 枚举 AND {日期列} 在窗口内（无"最新报告期"标志列时用）
        start, end = five_year_window()
        col = mql_ref(spec["col"])
        dcol = mql_ref(spec["date_col"])
        cond = (f'({col} == {_lit(spec["value"])}'
                f' AND {dcol} >= "{start}" AND {dcol} <= "{end}")')
        return cond, ""
    if kind == "window":
        # 近 5 年窗口：{日期列} 在窗口内（无类型枚举、无最新标志列时用）
        start, end = five_year_window()
        col = mql_ref(spec["col"])
        cond = f'({col} >= "{start}" AND {col} <= "{end}")'
        return cond, ""
    if kind == "in":
        vals = ", ".join(_lit(v) for v in spec["values"])
        return f'IN({mql_ref(spec["col"])}, [{vals}])', ""
    # kind == "eq"
    key = spec.get("from")
    if key:
        val = ctx.get(key)
        if val in (None, ""):
            tag = "未提供" if spec.get("optional") else "缺少必填参数"
            return None, f'{tag} {key}：已省略 `{mql_ref(spec["col"])}` 条件'
    else:
        val = spec.get("value")
    return f'{mql_ref(spec["col"])} == {_lit(val)}', ""


class MqlScript:
    """多 Block MQL 脚本累加器：**Block 编号由本类连续分配（1..N）**。

    调用方不再手写 `#1` / `#2`，从根上消除跳号、重号与"引用更大编号"的返工。
    """

    def __init__(self) -> None:
        self._blocks: List[Block] = []
        self.notes: List[str] = []

    @property
    def next_block_id(self) -> int:
        return len(self._blocks) + 1

    def note(self, text: str) -> None:
        self.notes.append(text)

    def add_report(self, market: str, name: str, code: str, *,
                   params: Optional[Dict[str, Any]] = None,
                   only_fields: Optional[Sequence[str]] = None,
                   fields_override: Optional[Sequence[str]] = None,
                   report_date: Optional[str] = None,
                   rating_cycle: Any = None,
                   type_value: Optional[str] = None,
                   block_id: Optional[int] = None) -> int:
        """追加一个 ReportBlock，返回分配到的 Block 编号。

        - 加载列条件按 `report_params()` 的声明顺序输出到**同一个** `SetReportFilter`；
        - 未取到值的可选条件自动省略，并记入 `self.notes`（不猜值、不留空条件）；
        - `fields_override` 用于该报表返回列尚未采集时（`fields_pending`）显式提供输出列。
        """
        item = pinned_report(market, name)
        if not item:
            raise KeyError(f"固化表未收录 {market}/{name}，请回退标准检索流程")
        fmap = item.get("fields") or {}
        want = list(fields_override) if fields_override else (
            list(only_fields) if only_fields else list(fmap))
        if not want:
            raise KeyError(
                f"{market}/{name} 的返回列中文名尚未采集（fields_pending），"
                f"无法生成合法 MQL（规程 §7.9 要求每个 Block 至少一个输出列）。"
                f"请先用 --fields 显式提供，或回退一次 Search_Context 取 reportFields 后补录 "
                f"PINNED_REPORTS 与 reference/MQL-报表路径固化表.md §4.1。")
        if fields_override is None:
            for k in want:
                if k not in fmap:
                    raise KeyError(f"字段 {k} 不在固化表 {market}/{name} 的返回列中")

        bid = block_id or self.next_block_id
        b = report_block(bid, item["path"])
        # reportStandardCodeSupported=false 的报表禁止 SetCodes/GetSectors（规程 §7.8）：
        # 证券范围改由返回列本地 FILTER_ROWS 过滤（item["local_scope"]）。
        local_scope = item.get("local_scope")
        if local_scope:
            scope_fld = local_scope.get("field", "证券代码")
            if scope_fld not in fmap:
                raise KeyError(f"local_scope 字段 {scope_fld} 不在固化表 {market}/{name} 的返回列中")
        else:
            b.add(set_codes([code]))

        ctx: Dict[str, Any] = {"code": code, "report_date": report_date,
                               "rating_cycle": rating_cycle, "type": type_value}
        ctx.update(params or {})
        conds: List[str] = []
        for spec in report_params(market, name):
            cond, tip = _filter_condition(spec, ctx)
            if cond is None:
                if tip:
                    self.note(f"[{name}] {tip}")
                continue
            conds.append(cond)
        if conds:
            b.add(set_report_filter(*conds))

        for k in want:
            b.add(field(fmap[k], k) if fields_override is None else
                  f"{{{k}}}: REPORT_FIELD({mql_str(k)});")

        if local_scope:
            code0 = str(code).split(".")[0]
            b.add(filter_rows(f'STARTS_WITH({{{scope_fld}}}, "{code0}")'))

        if item.get("note"):
            self.note(f"[{name}] {item['note']}")
        self._blocks.append(b.output())
        return bid

    def render(self) -> str:
        return "\n\n".join(b.render() for b in self._blocks)

    def block_ids(self) -> List[int]:
        return [b.id for b in self._blocks]


# 脚本名（批次名）→ 有序的报表清单；`params` 为**必须显式给定**的加载列取值。
# 与 reference/MQL-取数规程.md §8「本 skill 的取数批次编排」对应，**改动须两处同步**。
SCRIPTS: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "沪深京": {
        "批次1": [
            {"report": "公司介绍"},
            {"report": "高级管理人员"},
        ],
        "批次2": [
            {"report": "主营构成"},
            # 研发支出报表：2026-10-03 服务端预估接口不可用（remote_rejected），已移除；
            # 研发支出数据由「财务摘要报告期」的 `研发支出` 返回列承担。
            {"report": "员工构成"},
            {"report": "专利信息"},
            {"report": "财务摘要报告期"},
            {"report": "一致预测"},
        ],
        "批次3": [
            # 2026-10-03 实测修正：该报表无 TYPE 加载列，客户/供应商由返回列 `客户类型`
            # 本地区分 → 单 Block 取全量，取数后按 客户类型 拆 5.1/5.2。
            {"report": "客户供应商"},
        ],
        "章节3": [{"report": "公司介绍"}, {"report": "高级管理人员"}],
        "章节4": [{"report": "主营构成"}],
        "章节5": [
            {"report": "客户供应商"},
        ],
        "章节6": [{"report": "员工构成"}, {"report": "专利信息"}],
        "章节7": [{"report": "财务摘要报告期"}],
        "章节8": [{"report": "一致预测"}],
    },
    "港股": {
        "批次1": [
            {"report": "公司简况"},
            {"report": "董事会与高管"},
        ],
        "批次2": [
            {"report": "主营构成"},
            {"report": "财务分析摘要"},
            {"report": "利润表GSD"},
            {"report": "现金流量表GSD"},
            {"report": "一致预测"},
        ],
        "章节3": [{"report": "公司简况"}, {"report": "董事会与高管"}],
        "章节4": [{"report": "主营构成"}],
        "章节7": [{"report": "财务分析摘要"}, {"report": "利润表GSD"}, {"report": "现金流量表GSD"}],
        "章节8": [{"report": "一致预测"}],
    },
}
SCRIPTS["沪深京"]["全量"] = (SCRIPTS["沪深京"]["批次1"] + SCRIPTS["沪深京"]["批次2"]
                            + SCRIPTS["沪深京"]["批次3"])
SCRIPTS["港股"]["全量"] = SCRIPTS["港股"]["批次1"] + SCRIPTS["港股"]["批次2"]


def script_names(market: Optional[str] = None) -> List[str]:
    """可用的脚本名（批次名）列表。"""
    markets = [market] if market else list(SCRIPTS)
    out: List[str] = []
    for mk in markets:
        out.extend(f"{mk}/{n}" for n in SCRIPTS.get(mk, {}))
    return out


def build_script(market: str, name: str, code: str, *,
                 report_date: Optional[str] = None,
                 rating_cycle: Any = None,
                 org_code: Optional[str] = None,
                 fields_override: Optional[Sequence[str]] = None) -> tuple:
    """一次成型：按脚本名（批次名）生成整段可执行 MQL。

    返回 `(脚本文本, 提示列表, 跳过的报表列表)`：
    - Block 编号自动连续（1..N）；
    - 加载列条件顺序固定；
    - 返回列尚未采集的报表**不猜测、不生成非法 Block**，直接跳过并记录原因。
    """
    entries = (SCRIPTS.get(market) or {}).get(name)
    if entries is None:
        raise KeyError(f"未知脚本名 {market}/{name}（可选：{'、'.join(SCRIPTS.get(market, {}))}）")
    reps = {e["report"] for e in entries}
    if fields_override and len(reps) > 1:
        raise ValueError(
            f"--fields 只适用于「单报表」脚本（本次 {'、'.join(sorted(reps))} 含多种报表，"
            f"字段集各不相同）。请改为逐报表生成，或把返回列中文名补录进 PINNED_REPORTS + "
            f"reference/MQL-报表路径固化表.md §4.1。")
    sc = MqlScript()
    skipped: List[str] = []
    for e in entries:
        rep = e["report"]
        item = pinned_report(market, rep)
        if not item:
            sc.note(f"[{rep}] 固化表未收录 → 已跳过，请回退标准检索流程（规程 §2B）")
            skipped.append(rep)
            continue
        fmap = item.get("fields") or {}
        fo = list(fields_override) if fields_override else None
        if not fmap and fo is None:
            sc.note(f"[{rep}] 返回列中文名未采集（fields_pending）→ 已跳过；"
                    f"补录 PINNED_REPORTS 后自动纳入，或本次用 --fields 显式提供")
            skipped.append(rep)
            continue
        extra = dict(e.get("params") or {})
        if org_code:
            extra.setdefault("org_code", org_code)
        sc.add_report(market, rep, code, params=extra or None,
                      fields_override=fo, report_date=report_date,
                      rating_cycle=rating_cycle,
                      type_value=(e.get("params") or {}).get("type"))
    return sc.render(), sc.notes, skipped


def check_mql_script(text: str) -> List[str]:
    """MQL 脚本自检：Block 编号连续性 / 每个 Block 有输出列 / OutputBlock 配对 /
    路径单反斜杠 / 括号配平。返回问题清单（空 = 通过）。"""
    problems: List[str] = []
    decls = re.findall(r"(?m)^\s*[A-Za-z]+Block\(\s*#(\d+)\s*,", text)
    ids = [int(x) for x in decls]
    expect = list(range(1, len(ids) + 1))
    if not ids:
        problems.append("未找到任何 Block 声明（形如 `XxxBlock(#1, {...});`）")
    elif ids != expect:
        problems.append(f"Block 编号不连续：{ids}（应为 {expect}）")

    for i, seg in enumerate(re.split(r"(?m)^\s*[A-Za-z]+Block\(\s*#\d+\s*,", text)[1:], 1):
        head = seg.split("OutputBlock()")[0]
        if not re.search(r"REPORT_FIELD\(|\}\s*\(\s*\)\s*;", head):
            problems.append(f"Block #{i} 没有任何输出列（规程 §7.9：每个 Block 至少一个输出列）")

    n_out = len(re.findall(r"(?m)^\s*OutputBlock\(\s*\)\s*;", text))
    if ids and n_out != len(ids):
        problems.append(f"OutputBlock() 数量 {n_out} 与 Block 数量 {len(ids)} 不一致")

    if "\\\\" in text:
        problems.append("出现双反斜杠 `\\\\`（规程 §7.1：路径内部只能有一个实际反斜杠）")
    for op, cl in (("(", ")"), ("{", "}")):
        if text.count(op) != text.count(cl):
            problems.append(f"`{op}` 与 `{cl}` 数量不匹配（{text.count(op)} vs {text.count(cl)}）")
    return problems


def pinned_mql(market: str, name: str, secucode: str, block_id: int = 1,
               only_fields: Optional[Sequence[str]] = None, *,
               report_date: Optional[str] = None, rating_cycle: Any = None,
               type_value: Optional[str] = None,
               fields_override: Optional[Sequence[str]] = None) -> str:
    """零检索直取：按固化表拼装可直接交给 Execute_MQL 的 MQL（单 Block）。

    pinned_mql("沪深京", "一致预测", "300476.SZ")
    pinned_mql("沪深京", "客户供应商", "300476.SZ", type_value="客户", report_date="2025-12-31")

    与多 Block 脚本**同源**：统一走 `MqlScript`，Block 编号由脚本分配、
    加载列条件按固定顺序一次写出，避免手写与本函数产出不一致。
    """
    sc = MqlScript()
    sc.add_report(market, name, secucode, only_fields=only_fields,
                  fields_override=fields_override, block_id=block_id,
                  report_date=report_date, rating_cycle=rating_cycle,
                  type_value=type_value)
    return sc.render()


# ============================================================
# CLI：查询/导出「报表路径固化表」（零检索直取的机器可读入口）
# ============================================================
def _cli(argv=None):
    """用法：
      # —— 查询「报表路径固化表」（零检索直取的机器可读入口）——
      python scripts/mql_api.py --list                              # 列出全部已固化报表
      python scripts/mql_api.py --list --market 港股               # 只看某市场
      python scripts/mql_api.py --report 一致预测 --code 300476.SZ  # 含 8.1 表格 10 行指标↔返回列映射
      python scripts/mql_api.py --report 一致预测 --code 300476.SZ --params   # 只看加载列的固定顺序
      python scripts/mql_api.py --report 一致预测 --code 300476.SZ --mql      # 单 Block 可执行 MQL
      python scripts/mql_api.py --dump                              # 导出固化表 JSON

      # —— 取数脚本一次成型（Block 编号连续 + 参数顺序固定）——
      python scripts/mql_api.py --scripts                            # 列出全部脚本（批次）名
      python scripts/mql_api.py --script 批次2 --code 300476.SZ      # 整段可执行 MQL（多 Block，编号自动连续）
      python scripts/mql_api.py --script 批次3 --code 300476.SZ --report-date 2025-12-31
      python scripts/mql_api.py --script 批次3 --code 300476.SZ --fields "客户名称,销售额,占比"
      python scripts/mql_api.py --script 批次2 --code 300476.SZ --out mql_batch2.txt
      python scripts/mql_api.py --check mql_batch2.txt               # 自检已有脚本（编号/输出列/配对/反斜杠/括号）
    """
    import argparse, json, sys

    ap = argparse.ArgumentParser(
        prog="mql_api.py", add_help=True,
        description="MQL 取数辅助：拼装 MQL + 加工返回数据；"
                    "--list/--report/--script 查询固化表并一次成型生成可执行 MQL（零检索直取）",
    )
    ap.add_argument("--list", action="store_true", help="列出全部已固化报表")
    ap.add_argument("--market", default=None, help="市场过滤：沪深京 / 港股")
    ap.add_argument("--report", default=None, help="逻辑报表名（如 一致预测 / 公司简况 / 主营构成）")
    ap.add_argument("--code", default=None, help="SECUCODE（带交易所后缀，如 300476.SZ / 09992.HK）")
    ap.add_argument("--mql", action="store_true", help="直接输出可执行 MQL 脚本（单 Block）")
    ap.add_argument("--params", action="store_true",
                    help="配合 --report：只打印该报表加载列的固定顺序与说明")
    ap.add_argument("--scripts", action="store_true",
                    help="列出全部脚本名（批次名），可搭配 --market")
    ap.add_argument("--script", default=None,
                    help="脚本名（批次名），如 批次1 / 批次2 / 批次3 / 章节8 / 全量")
    ap.add_argument("--report-date", default=None,
                    help="报告期取值（如 2025-12-31）；仅「客户供应商」等需要钉住报告期的报表使用")
    ap.add_argument("--rating-cycle", default=None,
                    help="一致预测的「评级综合值周期 / 评级综合周期」取值；不给则该条件不写")
    ap.add_argument("--org-code", default=None,
                    help="机构代码（来自 公司介绍.机构代码）；供「财务摘要报告期」等 "
                         "reportStandardCodeSupported=false 报表的公司代码(ORG_CODE)加载列使用")
    ap.add_argument("--type", default=None, help="加载列 TYPE 的取值（客户 / 供应商）")
    ap.add_argument("--fields", default=None,
                    help="显式指定 Block 的输出列（返回列中文名，逗号分隔，**替换**原字段表）；"
                         "仅适用于单报表场景（--report，或脚本内只含一种报表）")
    ap.add_argument("--check", default=None,
                    help="自检一个 MQL 脚本文件（传 - 表示读 stdin）：Block 编号 / 输出列 / OutputBlock / 反斜杠 / 括号")
    ap.add_argument("--out", default=None, help="把生成的 MQL 写入文件（默认打印到 stdout）")
    ap.add_argument("--dump", action="store_true", help="导出固化表完整 JSON")
    args = ap.parse_args(argv)

    def _emit(text: str, notes, skipped=()) -> int:
        for n in notes or []:
            print(f"[提示] {n}", file=sys.stderr)
        if skipped:
            print(f"[跳过] 以下报表返回列未采集，已从脚本中剔除：{'、'.join(skipped)}", file=sys.stderr)
        problems = check_mql_script(text) if text.strip() else []
        for p in problems:
            print(f"[自检][FAIL] {p}", file=sys.stderr)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as f:
                f.write(text if text.endswith("\n") else text + "\n")
            print(f"[OK] 已写入 {args.out}")
        else:
            print(text)
        return 1 if problems else 0

    if args.dump:
        print(json.dumps(PINNED_REPORTS, ensure_ascii=False, indent=2))
        return 0

    if args.list:
        markets = [args.market] if args.market else list(PINNED_REPORTS.keys())
        for mk in markets:
            reps = PINNED_REPORTS.get(mk)
            if reps is None:
                print(f"[{mk}] 无此市场（可选：{list(PINNED_REPORTS.keys())}）")
                continue
            ready = [n for n, s in reps.items() if (s.get("fields") or {})]
            pending = [n for n, s in reps.items() if not (s.get("fields") or {})]
            print(f"[{mk}] {len(reps)} 个已固化报表（可用 {len(ready)} / 待补返回列 {len(pending)}）：")
            for name, spec in reps.items():
                tag = "" if (spec.get("fields") or {}) else "  ⚠️ 返回列未采集"
                print(f"  - {name}{tag}")
                print(f"      {spec['path']}")
                order = param_order(mk, name)
                if order:
                    print(f"      加载列固定顺序：{' → '.join(order)}")
                elif spec.get("flags"):
                    print(f"      加载列：{list(spec['flags'].keys())}")
        return 0

    if args.check is not None:
        if args.check == "-":
            raw = sys.stdin.read()
        else:
            try:
                raw = open(args.check, encoding="utf-8").read()
            except OSError as e:
                print(f"错误：无法读取 {args.check}（{e}）")
                return 2
        problems = check_mql_script(raw)
        for p in problems:
            print(f"[自检][FAIL] {p}")
        if not problems:
            print(f"[自检][PASS] Block 编号连续、每块有输出列、OutputBlock 配对、路径单反斜杠、括号配平")
        return 1 if problems else 0

    if args.scripts:
        markets = [args.market] if args.market else list(SCRIPTS)
        for mk in markets:
            names = list(SCRIPTS.get(mk, {}))
            print(f"[{mk}] {len(names)} 个脚本：{'、'.join(names)}")
            for n in names:
                reps = " → ".join(e["report"] for e in SCRIPTS[mk][n])
                print(f"  - {n}：{reps}")
        return 0

    if args.script:
        if not args.code:
            print("错误：--script 必须搭配 --code（SECUCODE 带后缀）")
            return 2
        mk = args.market or _guess_market(args.code)
        fields_override = None
        if args.fields:
            fields_override = [f.strip() for f in args.fields.split(",") if f.strip()]
        try:
            text, notes, skipped = build_script(
                mk, args.script, args.code,
                report_date=args.report_date, rating_cycle=args.rating_cycle,
                org_code=args.org_code, fields_override=fields_override)
        except KeyError as e:
            print(f"错误：{e}")
            return 2
        except ValueError as e:
            print(f"错误：{e}")
            return 2
        if args.type:
            print(f"[提示] --type={args.type} 对多 Block 脚本无效："
                  f"批次内各 Block 的 TYPE 已由脚本注册表按块给定（见 --scripts）", file=sys.stderr)
        print(f"# 市场：{mk} ｜ 脚本：{args.script} ｜ SECUCODE：{args.code}", file=sys.stderr)
        print(f"# {PARAM_ORDER_HINT}", file=sys.stderr)
        return _emit(text, notes, skipped)

    if args.report:
        if not args.code and not args.params:
            print("错误：--report 必须搭配 --code（SECUCODE 带后缀）")
            return 2
        if not args.code:
            print("错误：--report --params 仍需 --code 以推断市场")
            return 2
        mk = args.market or _guess_market(args.code)
        spec = pinned_report(mk, args.report)
        if not spec:
            print(f"错误：固化表未收录 {mk}/{args.report}（可选：{'、'.join(PINNED_REPORTS.get(mk, {}))}）")
            return 2
        if args.params:
            order = param_order(mk, args.report)
            print(f"市场：{mk} ｜ 报表：{args.report}")
            print(f"加载列固定顺序（SetReportFilter 按此顺序书写）：{' → '.join(order) or '（无加载列）'}")
            for p in report_params(mk, args.report):
                print(f"  - {p.get('kind', 'eq')} {p.get('col') or p.get('annual_col', '')}：{p.get('desc', '')}")
            if not order:
                print("  （该报表加载列为空 → 只写 SetCodes，不写 SetReportFilter）")
            return 0
        if args.mql:
            fo = None
            if args.fields:
                fo = [f.strip() for f in args.fields.split(",") if f.strip()]
            try:
                text = pinned_mql(mk, args.report, args.code,
                                  report_date=args.report_date,
                                  rating_cycle=args.rating_cycle,
                                  type_value=args.type,
                                  fields_override=fo)
            except KeyError as e:
                print(f"错误：{e}")
                return 2
            return _emit(text, [])
        print(f"市场：{mk}")
        print(f"路径：{spec['path']}")
        print(f"加载列：{list((spec.get('flags') or {}).keys()) or '（无）'}")
        print(f"加载列固定顺序：{' → '.join(param_order(mk, args.report)) or '（无加载列）'}")
        print("字段：")
        for k, v in (spec.get("fields") or {}).items():
            print(f"  {k} -> {v}")
        if spec.get("fields_pending"):
            print("  ⚠️ 返回列中文名未采集（fields_pending），生成前请用 --fields 显式提供")
        if spec.get("note"):
            print(f"  说明：{spec['note']}")
        if args.report == "一致预测":
            rows = table_8_1_rows(mk)
            print(f"8.1 一致预测表格指标行（{len(rows)} 行，行名/行序逐字固定，"
                  f"一行都不得少返回）：")
            for i, r in enumerate(rows, 1):
                src = (spec.get("fields") or {}).get(r["key"], "（固化表无对应取数列）")
                print(f"  {i:>2}. {r['label']}  <- {src}  [{r['transform']}]")
            miss = table_8_1_missing_keys(mk)
            if miss:
                print(f"  ⚠️ 固化表缺取数列的行：{'、'.join(miss)}")
        return 0

    ap.print_help()
    return 0


def _guess_market(code: str) -> str:
    """按 SECUCODE 后缀推断市场（沪深京 / 港股）。"""
    suf = code.rsplit(".", 1)[-1].upper() if "." in code else ""
    return "港股" if suf == "HK" else "沪深京"


if __name__ == "__main__":
    import sys as _sys
    raise SystemExit(_cli(_sys.argv[1:]))
