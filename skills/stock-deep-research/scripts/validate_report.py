#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公司一页纸 · 交付前质量校验（对应 reference/输出契约与数据契约.md §1 与 reference/合规与降级.md）

对已渲染的报告（HTML 或 Markdown）执行自动扫描：
- P0：占位符 / 空状态词 / 降级文本超限 / 合规禁用词 / 评级与目标价 / 章节齐全 /
      8.1 一致预测表指标行齐全（沪深京 10 行、港股 9 行）/ 单位口径 / 交付后记
- P1：资料来源行、页脚、SECUCODE 后缀规范、4.2/7.2 报告期列数上限与"整列为空"的报告期列（空列应在渲染前剔除）

退出码：0 = 无 P0 失败（可有 P1 警告）；1 = 存在 P0 失败，禁止交付。

用法:
    python validate_report.py --file "胜宏科技(300476.SZ)股票研究_20260921.html"
"""
from __future__ import annotations

import argparse
import html as _html
import re
import sys
from typing import Dict, List, Tuple

CHAPTERS = {
    "1": "公司近况跟踪", "2": "核心推荐逻辑", "3": "公司简介", "4": "公司业务拆分",
    "5": "公司产销链分析", "6": "公司研发实力", "7": "公司财务分析",
    "8": "公司盈利预测与估值分析", "9": "公司风险提示",
}

BANNED = ["套现", "抛售", "圈钱", "暴雷", "爆雷", "跑路", "出逃", "垃圾股", "坐庄", "操纵"]
PLACEHOLDER = re.compile(r"(?:X+%|XX+|约X|若干[X个]?)")
NULLWORD = re.compile(r"(?:null|NULL|缺失|暂无|未披露|数据待补|无数据)")
DEGRADE = re.compile(r"\[输入数据未提供该项数据\]")
RATING = re.compile(r"(?:目标价|目标市值|目标PE|建议买入|建议卖出|买入评级|卖出评级|"
                    r"增持评级|减持评级|强烈推荐|维持增持|维持买入|给予[^。；\n]{0,4}评级)")
PRICE_TALK = re.compile(r"(?:股价[^。；\n]{0,12}(?:上涨|下跌|走强|走弱)|利好股价|"
                        r"提振[^。；\n]{0,4}情绪|有望上涨)")
BAD_UNIT = re.compile(r"\d+(?:\.\d+)?\s*(?:万元|百万元|千万元|百万美元)")
POSTAMBLE = re.compile(r"数据缺口|口径声明|未包装|未补数|交付说明")
SECUCODE_OK = re.compile(r"\d{4,6}\.(?:SZ|SH|BJ|HK)\b")
BARE_CODE = re.compile(r"(?<![\d.\-])(\d{6})(?![\d\-%]|\.\d)(?!\s*(?:件|人|亿|万|股|吨|台|项|只))")
SRC_LINE = "资料来源"

# 8.1 一致预测表的固定指标行（行名与行序不得少改）。
# ⚠️ 行名/行序的权威副本共 9 处（清单见 reference/报告版式与图表规范.md §8.1），
#    机读副本另见 scripts/mql_api.py 的 TABLE_8_1_ROWS；任一处改动必须全部同步。
CONSENSUS_TABLE_MARK = "一致盈利预测数据"
CONSENSUS_ROWS_8_1 = [
    "营业总收入(亿元)", "营业总收入增长率(%)", "归母净利润(亿元)", "归母净利润增长率(%)",
    "EPS(稀释)", "基准股本(百万股)", "ROE(摊薄)(%)", "ROA(%)", "PE", "PEG",
]
CONSENSUS_ROW_HK_ONLY_MISSING = "基准股本(百万股)"   # 港股无该数据源 → 该行不渲染


def to_text(path: str) -> str:
    raw = open(path, "r", encoding="utf-8").read()
    if path.lower().endswith((".html", ".htm")):
        raw = re.sub(r"(?is)<(style|script)\b.*?</\1>", " ", raw)
        raw = re.sub(r"(?is)</(td|th|tr|p|div|h\d|li|table)>", " ", raw)
        raw = re.sub(r"(?s)<[^>]+>", " ", raw)
        raw = _html.unescape(raw)
    return re.sub(r"[ \t\u00a0]+", " ", raw)


def table_period_groups(path: str) -> List[List[str]]:
    """提取每张表表头里的报告期（YYYY-MM-DD），用于校验列顺序。

    注意：标签可能带附加属性（如 <thead data-...>），正则须容忍属性。
    """
    raw = open(path, "r", encoding="utf-8").read()
    if path.lower().endswith((".html", ".htm")):
        blocks = re.findall(r"(?is)<thead[^>]*>(.*?)</thead\s*>", raw)
    else:
        blocks = [ln for ln in raw.splitlines() if ln.lstrip().startswith("|")]
    groups = []
    for b in blocks:
        ds = re.findall(r"(\d{4}-\d{2}-\d{2})", b)
        if len(ds) >= 2:
            groups.append(ds)
    return groups


def table_period_columns(path: str) -> List[Tuple[List[str], List[List[str]]]]:
    """提取每张含报告期表头的表的 (报告期列表, 每个报告期列的数据单元格列表)。

    报告期列恒为**每行末尾 N 格**（4.2：业务板块|财务指标|periods…；7.2：指标|periods…），
    因此按"行尾 N 格"对齐即可，无需处理 4.2 的 rowspan。
    仅支持 HTML；Markdown 分支返回 []（该分支不做空列校验）。
    与 table_period_groups 一致，仅处理表头含 >= 2 个 YYYY-MM-DD 的表。
    """
    if not path.lower().endswith((".html", ".htm")):
        return []
    raw = open(path, "r", encoding="utf-8").read()
    out: List[Tuple[List[str], List[List[str]]]] = []
    for tb in re.findall(r"(?is)<table\b[^>]*>(.*?)</table\s*>", raw):
        head = re.search(r"(?is)<thead[^>]*>(.*?)</thead\s*>", tb)
        if not head:
            continue
        dates = re.findall(r"(\d{4}-\d{2}-\d{2})", head.group(1))
        if len(dates) < 2:
            continue
        body = re.search(r"(?is)<tbody[^>]*>(.*?)</tbody\s*>", tb)
        if not body:
            continue
        cols: List[List[str]] = [[] for _ in dates]
        for tr in re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr\s*>", body.group(1)):
            cells = [_html.unescape(re.sub(r"(?s)<[^>]+>", "", c)).strip()
                     for c in re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]\s*>", tr)]
            if len(cells) < len(dates):
                continue
            for i in range(len(dates)):
                cols[i].append(cells[len(cells) - len(dates) + i])
        out.append((dates, cols))
    return out


def html_table_count(path: str) -> int:
    raw = open(path, "r", encoding="utf-8").read()
    if not path.lower().endswith((".html", ".htm")):
        return sum(1 for ln in raw.splitlines() if ln.lstrip().startswith("|"))
    return len(re.findall(r"(?is)<table\b", raw))


def excerpts(text: str, pattern: re.Pattern, limit: int = 3) -> List[str]:
    out = []
    for m in pattern.finditer(text):
        s = max(m.start() - 18, 0)
        out.append("…" + text[s:m.end() + 18].replace("\n", " ").strip() + "…")
        if len(out) >= limit:
            break
    return out


def check(text: str, path: str) -> Tuple[List[Tuple[str, str, bool, List[str]]], Dict[str, int]]:
    results: List[Tuple[str, str, bool, List[str]]] = []
    stats: Dict[str, int] = {}

    ph = excerpts(text, PLACEHOLDER)
    results.append(("P0", "无占位符（XX / X% / 约X / 若干）", not ph, ph))

    nw = excerpts(text, NULLWORD)
    results.append(("P0", "无空状态描述（null/缺失/暂无/未披露）", not nw, nw))

    deg = DEGRADE.findall(text)
    stats["degrade_count"] = len(deg)
    results.append(("P0", f"降级文本 ≤2 处（实际 {len(deg)}）", len(deg) <= 2, []))

    hit = [w for w in BANNED if w in text]
    results.append(("P0", "合规禁用词 0 命中", not hit, hit))

    rt = excerpts(text, RATING)
    results.append(("P0", "无目标价 / 评级 / 买卖建议", not rt, rt))

    pt = excerpts(text, PRICE_TALK)
    results.append(("P0", '无"股价上涨/利好股价/提振情绪"类表述', not pt, pt))

    missing = [f"{k} {v}" for k, v in CHAPTERS.items()
               if not re.search(rf"(?:^|\s){k}\s*{v}", text) and not re.search(rf"[#\s]{k}\s*{v}", text)]
    results.append(("P0", "章节 1-9 一级标题齐全", not missing,
                    ["缺失：" + "、".join(missing)] if missing else []))

    intro_labels = ["主营业务", "发展历程", "股权结构", "管理层"]
    intro_missing = [label for label in intro_labels if label not in text]
    results.append(("P0", "公司简介表四项齐全", not intro_missing,
                    ["缺失：" + "、".join(intro_missing)] if intro_missing else []))

    risk_count = text.count("可观测指标")
    results.append(("P0", "风险提示含 3-5 个可观测指标", 3 <= risk_count <= 5,
                    [f"实际 {risk_count} 个"] if not (3 <= risk_count <= 5) else []))

    bu = excerpts(text, BAD_UNIT)
    results.append(("P0", "金额单位为人民币亿元口径", not bu, bu))

    pm = excerpts(text, POSTAMBLE)
    results.append(("P0", "无交付后记（数据缺口/口径声明/未包装/未补数/交付说明）", not pm, pm))

    bare = [c for c in dict.fromkeys(BARE_CODE.findall(text)) if not re.search(rf"{c}\.(SZ|SH|BJ|HK)", text)]
    results.append(("P0", "SECUCODE 全文带交易所后缀", not bare,
                    [f"无后缀代码：{', '.join(bare)}"] if bare else []))

    # 8.1 一致预测表：指标行必须齐全（沪深京 10 行 / 港股 9 行）。
    # 表未渲染（无一致预测数据，按降级只写"市场暂未形成明确一致预期"）时跳过，不误判。
    is_hk = bool(re.search(r"\d{4,6}\.HK\b", text))
    expect_8_1 = [r for r in CONSENSUS_ROWS_8_1
                  if not (is_hk and r == CONSENSUS_ROW_HK_ONLY_MISSING)]
    if CONSENSUS_TABLE_MARK in text:
        miss_8_1 = [r for r in expect_8_1 if r not in text]
        results.append(("P0", f"8.1 一致预测表指标行齐全（{'港股 9 行' if is_hk else '沪深京 10 行'}，不得少返回）",
                        not miss_8_1, ["缺失行：" + "、".join(miss_8_1)] if miss_8_1 else []))
    else:
        results.append(("P1", "8.1 一致预测表指标行齐全（未渲染一致预测表，跳过）", True, []))

    n_src = text.count(SRC_LINE)
    table_count = html_table_count(path)
    results.append(("P1", f"图表资料来源行覆盖表格（资料来源 {n_src} 处 / 表格 {table_count} 张）",
                    n_src >= max(1, table_count - 1), []))

    raw_html = open(path, "r", encoding="utf-8").read() if path.lower().endswith((".html", ".htm")) else ""
    srcdata_ok = 'id="srcdata"' in raw_html and 'class="src-chip"' in raw_html
    results.append(("P1", "资讯溯源（hover+click）数据块存在（srcdata + src-chip）",
                    srcdata_ok, ["报告缺少 #srcdata 或 .src-chip，资讯来源无法溯源"] if not srcdata_ok else []))

    groups = table_period_groups(path)
    bad_order = [" / ".join(g) for g in groups if g != sorted(g, reverse=True)]
    results.append(("P1", "表格报告期列降序（最新报告期在最左）", not bad_order,
                    [f"非降序：{b}" for b in bad_order]))
    # 4.2 / 7.2 报告期：候选窗口 = 最新报告期 + 近 5 个年报期（最多 6 列）；
    # 成表时每张表**各自独立**剔除"整列为空"的报告期，因此列数可以少于 5，
    # 两表的报告期列集合也允许不一致——此处不再校验"两表一致"，也不设列数下限。
    over = [" / ".join(g) for g in groups if len(g) > 6]
    results.append(("P1", "4.2/7.2 报告期列数 ≤ 6（候选窗口上限）", not over,
                    [f"超上限：{s}" for s in over]))
    results.append(("P1", "4.2/7.2 各表报告期列（整列为空的期已剔除，两表允许不一致）", True,
                    [f"{len(g)} 列：{' / '.join(g)}" for g in groups] or ["未发现含报告期的表格"]))
    empty_cols = []
    for periods, cols in table_period_columns(path):
        for i, p in enumerate(periods):
            vals = cols[i] if i < len(cols) else []
            if not any(v for v in vals):
                empty_cols.append(f"{p}（{len(vals)} 行全空）")
    results.append(("P1", '4.2/7.2 无"整列为空"的报告期列（空列应在渲染前剔除）',
                    not empty_cols, ["空列：" + "、".join(empty_cols)] if empty_cols else []))
    duplicated = [" / ".join(g) for g in groups if len(g) != len(set(g))]
    results.append(("P1", "表格报告期列无重复", not duplicated,
                    [f"重复报告期：{s}" for s in duplicated]))
    results.append(("P1", "页脚免责声明存在", "AI研究员" in text and "Choice" in text, []))
    results.append(("P1", "报告大标题含公司名与代码",
                    bool(re.search(r"\S+\(\S*\d{4,6}\.(?:SZ|SH|BJ|HK)\)\s*股票研究", text)), []))
    return results, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="公司一页纸交付校验")
    ap.add_argument("--file", required=True, help="待校验的 HTML / Markdown 报告")
    ap.add_argument("--json", help="可选：把结果写入 JSON 文件")
    args = ap.parse_args()

    text = to_text(args.file)
    results, stats = check(text, args.file)

    p0_fail = [r for r in results if r[0] == "P0" and not r[2]]
    p1_fail = [r for r in results if r[0] == "P1" and not r[2]]

    print(f"== 公司一页纸交付校验 :: {args.file} ==")
    for level, name, ok, detail in results:
        mark = "PASS" if ok else ("FAIL" if level == "P0" else "WARN")
        print(f"[{level}][{mark}] {name}")
        for d in detail:
            print(f"        · {d}")
    print(f"-- 汇总：P0 失败 {len(p0_fail)} 项 / P1 警告 {len(p1_fail)} 项 / "
          f"降级文本 {stats.get('degrade_count', 0)} 处")

    if args.json:
        import json
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([{"level": l, "item": n, "pass": o, "detail": d} for l, n, o, d in results],
                      f, ensure_ascii=False, indent=2)

    if p0_fail:
        print("结论：不合格，禁止交付。请退回对应章节重写后重新渲染。")
        return 1
    print("结论：P0 全部通过，允许交付" + ("（请修复 P1 警告项）" if p1_fail else "。"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
