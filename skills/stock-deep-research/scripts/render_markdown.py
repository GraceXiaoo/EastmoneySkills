#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公司一页纸 · 会话正文渲染器（data.json → Markdown）

用途：按《输出契约与数据契约》§1「会话回复正文（硬约束）」把**同一份 `data.json`**
渲染成对话里要直接输出的报告正文 Markdown——章节 1-9 一级标题、正文段落、以及
章节 3 简介表 / 4.2 分板块表 / 6 研发趋势表 / 7.2 主要财务指标表 / 8.1 一致预测表。

为什么要有这个脚本：会话正文必须是"报告内容本身"，而不是执行过程、校验结果、
数据缺口或口径说明。靠模型手写正文容易走样（漏表、漏章、改了数字口径），
所以这里与 `build_report.py` **共用同一套渲染规则函数**（报告期降序、
4.2 / 7.2 各表独立剔除整列为空的报告期、8.1 固定行集原样输出），
保证对话正文与 HTML **同源同值**。

用法:
    python render_markdown.py --input data.json --out 会话正文.md
    python render_markdown.py --input data.json            # 直接打印到 stdout
    python render_markdown.py --input data.json --no-footer # 不输出页脚免责行
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_report as br  # noqa: E402  复用同一套口径函数，禁止在此重实现

CHAPTER_TITLES = br.CHAPTER_TITLES
FOOTER_TEXT = br.FOOTER_TEXT


# ----------------------------------------------------------------- 基础工具
def cell(v: Any) -> str:
    """单元格文本：None/空 → 空串；竖线转义，避免破坏 Markdown 表格。"""
    if v is None:
        return ""
    return str(v).replace("|", "\\|").replace("\n", " ").strip()


def md_table(header: Sequence[Any], rows: Sequence[Sequence[Any]],
             title: str = "", note: str = "") -> List[str]:
    """Markdown 表格：标题/表注作为独立行，空表返回 []。"""
    if not header:
        return []
    out: List[str] = []
    if title:
        out.append(f"**{title}**")
    out.append("| " + " | ".join(cell(h) for h in header) + " |")
    out.append("|" + "---|" * len(header))
    for r in rows:
        cells = list(r) + [""] * (len(header) - len(r))
        out.append("| " + " | ".join(cell(c) for c in cells[:len(header)]) + " |")
    if note:
        out.append(note)
    return out + [""]


def wide_rows(spec: Dict[str, Any]) -> List[List[Any]]:
    body: List[List[Any]] = []
    for r in spec.get("rows") or []:
        if isinstance(r, dict):
            body.append([r.get("name", "")] + list(r.get("values", [])))
        else:
            body.append(list(r))
    return body


def paras(texts: Sequence[Any]) -> List[str]:
    """段落列表 → Markdown 行（段间空行，否则相邻段落会被并成一段）。"""
    out: List[str] = []
    for t in texts:
        t = str(t).strip()
        if not t:
            continue
        out += [t, ""]
    return out


# ----------------------------------------------------------------- 各章渲染
def ch1(ch: Dict[str, Any]) -> List[str]:
    out: List[str] = paras(ch.get("texts") or [])
    cat = ch.get("catalyst") or {}
    rows = cat.get("rows") or []
    if rows:
        if str(rows[0][0]).strip() in ("时间", "日期"):
            out += md_table(rows[0], rows[1:], title=cat.get("title", ""), note=cat.get("note", ""))
        else:
            out += md_table(["时间", "事件", "预期影响"], rows,
                            title=cat.get("title", ""), note=cat.get("note", ""))
    return out


def ch2(ch: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key, label in (("short", "短期逻辑"), ("long", "长期逻辑")):
        subs = ch.get(key) or []
        if not subs:
            continue
        out.append(f"### {label}")
        out.append("")
        for s in subs:
            head = str(s.get("head", "")).rstrip("：:")
            out.append(f"**{head}**：{s.get('body', '')}")
        out.append("")
    return out


def ch3(ch: Dict[str, Any]) -> List[str]:
    rows = [r for r in (ch.get("rows") or []) if len(r) >= 2]
    return md_table(["项目", "内容"], [[r[0], r[1]] for r in rows]) if rows else []


def ch4(ch: Dict[str, Any]) -> List[str]:
    out: List[str] = paras(ch.get("texts") or [])
    seg = ch.get("segments") or {}
    rows = seg.get("rows") or []
    periods = seg.get("periods") or []
    if not rows or not periods:
        return out
    periods, idx = br.period_index(periods, desc=True)
    # 与 render_segment_table 同一判定：整列为空 → 该表不展示该报告期
    col_vals: List[List[Any]] = [[] for _ in periods]
    for s in rows:
        for _m, vals in (s.get("metrics") or {}).items():
            vals = list(vals)
            for k, i in enumerate(idx):
                col_vals[k].append(vals[i] if i < len(vals) else "")
    keep = [k for k in range(len(periods)) if any(not br.is_blank_cell(v) for v in col_vals[k])]
    if not keep:
        return out
    periods = [periods[k] for k in keep]
    idx = [idx[k] for k in keep]
    body: List[List[Any]] = []
    for s in rows:
        for mname, vals in (s.get("metrics") or {}).items():
            vals = list(vals)
            body.append([s.get("name", ""), mname] + [vals[i] if i < len(vals) else "" for i in idx])
    if body:
        out.append("### 4.2 分板块业务情况")
        out.append("")
        out += md_table(["业务板块", "财务指标"] + [str(p) for p in periods], body,
                        note=seg.get("note", ""))
    return out


def ch5(ch: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for key, label in (("customers", "5.1 主要客户情况"), ("suppliers", "5.2 主要供应商情况")):
        blk = ch.get(key) or {}
        if not blk or not (blk.get("items") or blk.get("summary")):
            continue
        out.append(f"### {label}")
        out.append("")
        if blk.get("text"):
            out += [str(blk["text"]).strip(), ""]
        items = blk.get("items") or []
        rows: List[List[Any]] = []
        if items and isinstance(items[0], dict):
            rows = [[i.get("name", ""), i.get("amount", ""), i.get("ratio", "")] for i in items]
        elif items:
            rows = [list(r) for r in items]
        rows += [list(r) for r in (blk.get("summary") or [])]
        if rows:
            out += md_table(["名称", "金额(亿元)", "占比(%)"], rows,
                            title=blk.get("title", ""))
    return out


def ch6(ch: Dict[str, Any]) -> List[str]:
    out: List[str] = paras(ch.get("texts") or [])
    cards = ch.get("cards") or []
    if cards:
        out.append("| " + " | ".join(cell((list(c) + [""])[0]) for c in cards) + " |")
        out.append("|" + "---|" * len(cards))
        out.append("| " + " | ".join(cell((list(c) + ["", "", ""])[1]) for c in cards) + " |")
        out.append("")
    trend = ch.get("trend") or {}
    if trend.get("periods"):
        rows = [
            ["研发支出(亿元)"] + [cell(v) for v in (trend.get("expend") or [])],
            ["研发费用率(%)"] + [cell(v) for v in (trend.get("ratio") or [])],
        ]
        out += md_table(["研发投入"] + [str(p) for p in trend["periods"]], rows,
                        title=trend.get("title", ""), note=trend.get("note", ""))
    return out


def ch7(ch: Dict[str, Any]) -> List[str]:
    out: List[str] = paras(ch.get("texts") or [])
    tbl = ch.get("table") or {}
    periods = tbl.get("periods") or []
    body = wide_rows(tbl)
    if periods and body:
        # 与 7.2 渲染同规则：降序 + 本表独立剔除整列为空的报告期
        periods, body = br.reorder_periods(periods, body, desc=True)
        periods, body = br.drop_all_empty_periods(periods, body)
        if periods:
            out.append("### 7.2 主要财务指标")
            out.append("")
            out += md_table(["财务指标"] + [str(p) for p in periods], body, note=tbl.get("note", ""))
    return out


def ch8(ch: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    cons = ch.get("consensus") or {}
    periods = cons.get("periods") or []
    body = wide_rows(cons)
    if periods and body:
        # 8.1 为固定行集：A→E 顺序保持传入顺序，行不得删减（口径同 render_wide_table）
        out.append("### 8.1 一致预测")
        out.append("")
        out += md_table(["预测指标"] + [str(p) for p in periods], body, note=cons.get("note", ""))
    texts = [str(t).strip() for t in (ch.get("texts") or []) if str(t).strip()]
    if texts:
        out.append("### 8.2 估值分析")
        out.append("")
        out += paras(texts)
    return out


def ch9(ch: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for r in ch.get("risks") or []:
        name = r.get("name", "")
        out.append(f"**{name}**：{r.get('desc', '')}**可观测指标**：{r.get('metric', '')}")
        out.append("")
    return out


RENDERERS = {"1": ch1, "2": ch2, "3": ch3, "4": ch4, "5": ch5,
             "6": ch6, "7": ch7, "8": ch8, "9": ch9}


def render(data: Dict[str, Any], footer: bool = True) -> str:
    company = data.get("company") or {}
    name, code = company.get("name", ""), company.get("secucode", "")
    lines: List[str] = [f"# {name}（{code}）公司一页纸", ""]
    meta = " ｜ ".join(x for x in [company.get("report_period", ""),
                                  f"取数时点：{company.get('as_of')}" if company.get("as_of") else "",
                                  "数据来源：Choice 金融终端（MQL）"] if x)
    if meta:
        lines += [meta, ""]
    chapters = data.get("chapters") or {}
    for num in "123456789":
        lines += [f"## {num} {CHAPTER_TITLES[num]}", ""]
        lines += RENDERERS[num](chapters.get(num) or {})
    if footer:
        lines += ["---", "", FOOTER_TEXT]
    # 折叠 3 个以上连续空行
    text = "\n".join(lines)
    while "\n\n\n\n" in text:
        text = text.replace("\n\n\n\n", "\n\n\n")
    return text.rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="公司一页纸 data.json → 会话正文 Markdown")
    ap.add_argument("--input", required=True, help="data.json 路径")
    ap.add_argument("--out", default=None, help="输出 .md 路径；不给则打印到 stdout")
    ap.add_argument("--no-footer", action="store_true", help="不输出页脚免责行")
    a = ap.parse_args()
    data = json.load(open(a.input, encoding="utf-8"))
    text = render(data, footer=not a.no_footer)
    if a.out:
        open(a.out, "w", encoding="utf-8", newline="").write(text)
        print(f"[OK] session body -> {a.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
