#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公司一页纸 · 章节文字描述「资讯检索」归一化取数封装

取数通道：妙想 MCP 工具 `mx_finance_search`（**非 MQL**，供全报告 9 个章节的
**文字描述部分**取数）。

分工：
- **Agent（本会话）**：按场景注册表**分批并发**调用 `mx_finance_search`（11 个场景无依赖 →
  按 `SCENE_BATCHES` 每批 3–4 个并发提交，禁止逐个串行），将每次返回的条目结构化为
  `raw/{scene}.json`（字段见 `INGEST_SCHEMA`），供本脚本消费。
- **本脚本**：只做五件事（对应《资讯检索-取数规范.md》§6 第 1-3 步 + §7 拼接）：
  1) 按场景算时间窗（1 个月 / 6 个月，均由系统日现算，用于窗口兜底校验）；
  2) 读取 `raw/{scene}.json`（query 用场景模板，公司名称是唯一变量）；
  3) 窗口兜底校验 → 同源去重 → 时间倒序（无 showTime 的条目排最后）；
  4) 把 `chunk` 按顺序拼接为该场景的文字描述输入文本；
  5) 落盘为该章节的输入 JSON（单场景）或全场景 map（`--all`）。

不做的事：事件筛选（纯股价/交易/情绪类剔除）由 `reference/prompts/01-公司近况跟踪.md`
负责；章节 3-8 的**表格/图表**取数一律走 MQL（见 `mql_api.py`），本脚本不得替代。

mx_finance_search 不支持分页/类型参数/显式时间窗入参，只接受自然语言 query：
- 时间范围（近 1 个月 / 近半年）通过 query 语义表达，窗口兜底在本脚本按 `showTime` 完成；
- 来源类型（资讯/公告/研报）通过 query 语义表达，由 Agent 组装 query 时遵守场景模板。
"""
from __future__ import annotations

import argparse
import calendar
import datetime as _dt
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# ------------------------------------------------------------------ 场景注册表
# query 句式与《资讯检索-取数规范.md》§2 逐项一致（公司名称是唯一变量，
# 不得带代码或交易所后缀）。window 为时间窗档位，用于窗口兜底与展示。
SCENES: Dict[str, Dict[str, Any]] = {
    "1": {
        "name": "公司近况跟踪",
        "chapter": "1",
        "target": "近况文字段 + 催化事件时间表",
        "query": "【{company}】近况跟踪",
        "sources": "资讯、公告、研报披露的公司最近 1 个月的数据",
        "window": "1M",
        "fields": ["showTime", "chunk"],
    },
    "2": {
        "name": "核心推荐逻辑",
        "chapter": "2",
        "target": "短期逻辑 / 长期逻辑",
        "query": "【{company}】投资观点",
        "sources": "研报披露的公司最近半年的数据",
        "window": "6M",
        "fields": ["chunk"],
    },
    "3.1": {
        "name": "公司简介-发展历程",
        "chapter": "3",
        "target": "公司简介表「发展历程」格",
        "query": "【{company}】发展历程",
        "sources": "公告披露的公司最近半年的数据",
        "window": "6M",
        "fields": ["chunk"],
    },
    "3.2": {
        "name": "公司简介-股权结构",
        "chapter": "3",
        "target": "公司简介表「股权结构」格",
        "query": "【{company}】股权结构",
        "sources": "公告披露的公司最近半年的数据",
        "window": "6M",
        "fields": ["chunk"],
    },
    "4": {
        "name": "公司业务拆分",
        "chapter": "4",
        "target": "4.1 公司盈利方式",
        "query": "【{company}】分产品业务情况",
        "sources": "资讯披露的公司最近半年的数据",
        "window": "6M",
        "fields": ["chunk"],
    },
    "5.1": {
        "name": "主要客户情况",
        "chapter": "5",
        "target": "5.1 主要客户情况正文",
        "query": "【{company}】主要客户",
        "sources": "资讯、公告、研报披露的公司最近半年的数据",
        "window": "6M",
        "fields": ["chunk"],
    },
    "5.2": {
        "name": "主要供应商情况",
        "chapter": "5",
        "target": "5.2 主要供应商情况正文",
        "query": "【{company}】主要供应商",
        "sources": "资讯、公告、研报披露的公司最近半年的数据",
        "window": "6M",
        "fields": ["chunk"],
    },
    "6": {
        "name": "公司研发实力",
        "chapter": "6",
        "target": "研发实力正文（段落部分）",
        "query": "【{company}】研发实力与专利",
        "sources": "公告披露的公司最近半年的数据",
        "window": "6M",
        "fields": ["chunk"],
    },
    "7": {
        "name": "公司财务分析",
        "chapter": "7",
        "target": "7.1 财务健康状况评估",
        "query": "【{company}】财务数据和指标",
        "sources": "研报披露的公司最近半年的数据",
        "window": "6M",
        "fields": ["chunk"],
    },
    "8": {
        "name": "公司盈利预测与估值分析",
        "chapter": "8",
        "target": "8.2 估值分析",
        "query": "【{company}】估值",
        "sources": "研报披露的公司最近半年的数据",
        "window": "6M",
        "fields": ["chunk"],
    },
    "9": {
        "name": "公司风险提示",
        "chapter": "9",
        "target": "风险提示段落",
        "query": "【{company}】风险",
        "sources": "研报披露的公司最近半年的数据",
        "window": "6M",
        "fields": ["chunk"],
    },
}

SCENE_ORDER: List[str] = list(SCENES.keys())
"""固定归一化顺序（= `{{ZWSMSJ}}` 的 scene_order）：
1 → 2 → 3.1 → 3.2 → 4 → 5.1 → 5.2 → 6 → 7 → 8 → 9。"""

SCENE_BATCHES: List[List[str]] = [
    ["1", "2", "3.1", "3.2"],
    ["4", "5.1", "5.2", "6"],
    ["7", "8", "9"],
]
"""检索的**并发批次**（每批 3–4 个场景；批次内并发提交，批次间无依赖）。

11 个场景彼此无依赖（`query` 的唯一变量都是公司名称，窗口由系统日现算），
因此**不允许逐个串行**：按本表分 3 批（4+4+3）并发提交。
本表与《资讯检索-取数规范.md》§10.1 逐项对应，**改动须两处同步**。
注意：并发只改变检索的提交时序，不改变 `SCENE_ORDER` 的归一化顺序，
也不改变 `raw/{scene}.json` 落盘契约（并发返回须按 query 与场景键一一对应，禁止串号）。
"""

# 自洽校验：批次必须完整覆盖 SCENE_ORDER，且不重不漏（导入即校验）
assert [s for _b in SCENE_BATCHES for s in _b] == SCENE_ORDER, (
    "SCENE_BATCHES 必须与 SCENE_ORDER 一一对应（不重、不漏、顺序一致）")


def batch_of(scene: str) -> int:
    """场景所属并发批次号（从 1 开始）；不在批次表内返回 0。"""
    for i, batch in enumerate(SCENE_BATCHES, 1):
        if scene in batch:
            return i
    return 0


def format_batches() -> str:
    """打印用：并发批次划分（每批 3–4 个场景）。"""
    lines = []
    for i, batch in enumerate(SCENE_BATCHES, 1):
        lines.append(f"批次 {chr(64 + i)}（{len(batch)} 个场景，批次内并发提交）："
                     + "、".join(f"{s} {SCENES[s]['name']}" for s in batch))
    lines.append(f"共 {len(SCENE_BATCHES)} 批 / {len(SCENE_ORDER)} 个场景；"
                 f"批次之间无依赖，禁止逐个串行；归一化顺序仍为 {' → '.join(SCENE_ORDER)}。")
    return "\n".join(lines)

# ------------------------------------------------------------------ 时间窗口径

WINDOW_MONTHS = {"1M": 1, "6M": 6}


def months_window(months: int, today: Optional[_dt.date] = None) -> Tuple[str, str]:
    """系统日往前推 N 个自然月（规范 §4）。

    例：系统日 2026-09-23、N=1  -> ('2026-08-23 00:00:00', '2026-09-23 23:59:59')
        系统日 2026-09-23、N=6  -> ('2026-03-23 00:00:00', '2026-09-23 23:59:59')
    月末回退按目标月最后一天收敛：2026-03-31 回退 1 个月 -> '2026-02-28'
    """
    if months < 0:
        raise ValueError("months 不能为负")
    t = today or _dt.date.today()
    total = t.year * 12 + (t.month - 1) - months
    y, m0 = divmod(total, 12)
    m = m0 + 1
    d = min(t.day, calendar.monthrange(y, m)[1])
    start = _dt.datetime(y, m, d, 0, 0, 0)
    end = _dt.datetime(t.year, t.month, t.day, 23, 59, 59)
    return (start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"))


def scene_window(scene: str, today: Optional[_dt.date] = None) -> Tuple[str, str]:
    """按场景注册表的 window 档位算窗口（仅用于兜底校验与展示）。"""
    key = WINDOW_MONTHS[SCENES[scene]["window"]]
    return months_window(key, today)


def build_query(scene: str, company: str) -> str:
    """query 固定句式；公司名称是唯一变量（不得带代码或交易所后缀）。

    示例：`【宁德时代】近况跟踪`。时间范围与来源类型已含在句式语义中，
    由 mx_finance_search 按自然语言召回。
    """
    return SCENES[scene]["query"].format(company=company.strip())


# ------------------------------------------------------------------ raw 落盘契约
# Agent 每次调用 mx_finance_search 后，把返回条目结构化为 raw/{scene}.json：
#   {
#     "query": "【宁德时代】近况跟踪",          # 本次实际使用的 query
#     "company": "宁德时代",
#     "items": [
#       {
#         "showTime": "2026-09-23 12:25:22",   # 发布时间（来源：返回的「发布时间」）
#         "title":   "资讯标题",                # 返回的「标题」
#         "chunk":   "资讯正文摘要/关键事实",     # 返回的「摘要/正文片段」——文字描述唯一事实来源
#         "source":  "公告|研报|媒体名",          # 返回的「来源」或其类型
#         "link":    "https://...",              # 返回的「链接」（无链接可为空串）
#         "source_marker": "[source:1]"          # 返回的溯源标记（无则空串）
#       }, ...
#     ]
#   }
INGEST_SCHEMA = "raw/{scene}.json → {query, company, items:[{showTime, title, chunk, source, link, source_marker}]}"


def raw_path(raw_dir: str, scene: str) -> str:
    return os.path.join(raw_dir, f"{scene}.json")


def load_raw(raw_dir: str, scene: str) -> Dict[str, Any]:
    """读取 raw/{scene}.json；缺失或非法视为该场景取数失败（按 §9 降级）。"""
    p = raw_path(raw_dir, scene)
    if not os.path.isfile(p):
        raise FileNotFoundError(f"缺少原始结果文件：{p}")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError(f"原始结果文件结构非法（应为 {INGEST_SCHEMA}）：{p}")
    return data


# ------------------------------------------------------------------ 结果加工

def _in_window(show_time: str, start: str, end: str) -> bool:
    return bool(show_time) and start <= show_time <= end


def normalize(rows: List[Dict[str, Any]], start: str, end: str,
              with_meta: bool = False) -> List[Dict[str, Any]]:
    """规范 §6 第 1-3 步：窗口兜底 → 同源去重 → 时间倒序。

    严格两遍去重（顺序不可颠倒）：
    1) 窗口兜底：`showTime` 必须存在且落在 `[start, end]` 内，否则剔除
       （无 `showTime` 视为无法校验窗口，一并剔除）；`chunk` 为空亦剔除。
    2) 同 `title`（同源）只保留 `chunk` 最长的一条（保证同一篇资讯只贡献一次）。
    3) 第一遍存活结果按 `chunk` 完全一致再去重，保留首条（来源权威度最高者，
       即 items 中出现顺序最靠前的一条）。
    4) 按 `showTime` 倒序（最新在前）。

    输出默认只含 `showTime` / `chunk` 两个业务字段；`with_meta=True` 时额外保留
    title/source/link/source_marker 供溯源与人工核对。
    """
    # 第 1 步：窗口兜底 + 基础字段清洗
    stage1: List[Dict[str, Any]] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        show_time = str(r.get("showTime") or "").strip()
        chunk = str(r.get("chunk") or "").strip()
        if not chunk or not _in_window(show_time, start, end):
            continue
        item = {"showTime": show_time, "chunk": chunk}
        if with_meta:
            item["title"] = str(r.get("title") or "").strip()
            item["source"] = str(r.get("source") or "").strip()
            item["link"] = str(r.get("link") or "").strip()
            item["source_marker"] = str(r.get("source_marker") or "").strip()
        item["_title"] = str(r.get("title") or chunk)[:120]
        item["_order"] = len(stage1)
        stage1.append(item)

    # 第 2 步：同 title 保留 chunk 最长的一条
    by_title: Dict[str, Dict[str, Any]] = {}
    for it in stage1:
        prev = by_title.get(it["_title"])
        if prev is None or len(it["chunk"]) > len(prev["chunk"]):
            by_title[it["_title"]] = it

    # 第 3 步：完全相同 chunk 去重，保留出现顺序最靠前（items 顺序即召回权威序）
    by_chunk: Dict[str, Dict[str, Any]] = {}
    for it in by_title.values():
        dup = by_chunk.get(it["chunk"])
        if dup is None or it["_order"] < dup["_order"]:
            by_chunk[it["chunk"]] = it

    # 第 4 步：清理内部字段并按时间倒序
    deduped = []
    for it in by_chunk.values():
        it.pop("_title", None)
        it.pop("_order", None)
        if not with_meta:
            it.pop("title", None)
            it.pop("source", None)
            it.pop("link", None)
            it.pop("source_marker", None)
        deduped.append(it)
    deduped.sort(key=lambda x: x["showTime"], reverse=True)
    return deduped


def join_chunks(items: List[Dict[str, Any]], max_chars: int = 0) -> Tuple[str, int]:
    """规范 §7：把 `chunk` 按排序结果拼成该场景的文字描述输入文本。

    返回 (拼接文本, 拼接前字符总数)。`max_chars > 0` 时在 chunk 边界截断。
    """
    total = sum(len(i["chunk"]) for i in items)
    if max_chars and max_chars > 0:
        kept: List[str] = []
        used = 0
        for it in items:
            c = it["chunk"]
            if used + len(c) > max_chars and kept:
                break
            kept.append(c)
            used += len(c)
        return "\n".join(kept), total
    return "\n".join(i["chunk"] for i in items), total


def sources_from_items(items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """从带元数据的 items 提炼「溯源清单」，供 data.json 章节 `sources` 使用。

    每项只保留 title / time / source / link / source_marker；无链接时 link 留空，
    渲染层对无链接来源仅展示文本、不可点击。
    """
    out = []
    for it in items:
        s = {
            "title": it.get("title") or it.get("chunk", "")[:40],
            "time": it.get("showTime", ""),
            "source": it.get("source", ""),
            "link": it.get("link", ""),
            "source_marker": it.get("source_marker", ""),
        }
        out.append(s)
    return out


def ingest_scene(scene: str, company: str, raw: Dict[str, Any],
                 start: Optional[str] = None, end: Optional[str] = None,
                 with_meta: bool = False, max_chars: int = 0) -> Dict[str, Any]:
    """单场景一站加工：算窗口 → 读 raw → 加工 → 拼文本 → 返回该场景输入结构。"""
    if scene not in SCENES:
        raise KeyError(f"未知场景键：{scene}（可选：{', '.join(SCENE_ORDER)}）")
    if not start or not end:
        d_start, d_end = scene_window(scene)
        start = start or d_start
        end = end or d_end
    rows = raw.get("items") or []
    items = normalize(rows, start, end, with_meta=with_meta)
    text, total_chars = join_chunks(items, max_chars=max_chars)
    cfg = SCENES[scene]
    q = str(raw.get("query") or build_query(scene, company)).strip()
    return {
        "scene": scene,
        "scene_name": cfg["name"],
        "chapter": cfg["chapter"],
        "target": cfg["target"],
        "company": company,
        "query": q,
        "sources_desc": cfg["sources"],
        "window": {"start": start, "end": end},
        "window_months": WINDOW_MONTHS[cfg["window"]],
        "returned": len(rows),
        "kept": len(items),
        "chunk_chars": total_chars,
        "text": text,
        "items": items,
        "sources": sources_from_items(items) if with_meta else [],
    }


def ingest_all(company: str, raw_dir: str, scenes: Optional[List[str]] = None,
               with_meta: bool = False, max_chars: int = 0) -> Dict[str, Any]:
    """按固定顺序批量加工全场景 raw；单场景失败不阻塞其它场景（记录 error 字段）。"""
    keys = scenes or SCENE_ORDER
    out: Dict[str, Any] = {}
    failed: List[str] = []
    for sc in keys:
        try:
            raw = load_raw(raw_dir, sc)
            out[sc] = ingest_scene(sc, company, raw, with_meta=with_meta,
                                   max_chars=max_chars)
        except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as e:
            failed.append(sc)
            out[sc] = {
                "scene": sc, "scene_name": SCENES.get(sc, {}).get("name", ""),
                "company": company, "error": str(e), "text": "", "items": [],
            }
    return {
        "company": company,
        "as_of": _dt.date.today().strftime("%Y-%m-%d"),
        "scene_order": list(keys),
        "failed_scenes": failed,
        "scenes": out,
    }


# ------------------------------------------------------------------ CLI

def _print_scene_line(res: Dict[str, Any]) -> None:
    if res.get("error"):
        print(f"[FAIL] 场景 {res['scene']} {res.get('scene_name', '')}：{res['error']}")
    else:
        print(f"[OK]   场景 {res['scene']} {res.get('scene_name', '')}："
              f"窗口 {res['window']['start']} ~ {res['window']['end']}；"
              f"返回 {res['returned']} 条，去重后 {res['kept']} 条，"
              f"拼接 {res['chunk_chars']} 字")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="章节文字描述 · mx_finance_search 结果归一化（11 个场景）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="场景键：\n  " + "\n  ".join(
            f"{k:<5} 第{v['chapter']}章 {v['name']}（{v['target']}，窗口 {v['window']}）"
            for k, v in SCENES.items()) + "\n\n"
        "并发批次：\n  " + "\n  ".join(
            f"批次 {chr(64 + i)}（{len(b)} 个场景并发）：" + "、".join(b)
            for i, b in enumerate(SCENE_BATCHES, 1)) + "\n\n"
        "raw 目录约定：\\n  ".join([
            "",
            "Agent 按 SCENE_BATCHES 分批并发调用 mx_finance_search（每批 3–4 个场景），"
            f"将每次返回条目结构化为 raw/{{scene}}.json 保存（{INGEST_SCHEMA}）；"
            "并发返回须按 query 与场景键一一对应落盘，禁止串号。",
            "本脚本只做窗口兜底 / 去重 / 排序 / 拼接 / 落盘，不发起任何网络请求。"]))
    ap.add_argument("--company",
                    help="公司简称，如 宁德时代（不带代码与后缀）")
    ap.add_argument("--raw-dir",
                    help="mx_finance_search 原始结果目录（内含 1.json / 2.json / 3.1.json / … / 9.json）")
    ap.add_argument("--batches", action="store_true",
                    help="仅打印资讯检索的并发批次划分（每批 3–4 个场景）后退出，不需要 --company / --raw-dir")
    ap.add_argument("--scene", action="append", default=None,
                    help="场景键，可重复；省略且未指定 --all 时默认取场景 1")
    ap.add_argument("--all", action="store_true", help="加工全部 11 个场景")
    ap.add_argument("--start", help="覆盖窗口起（默认按场景档位现算 00:00:00，仅兜底用）")
    ap.add_argument("--end", help="覆盖窗口止（默认按场景档位现算 23:59:59，仅兜底用）")
    ap.add_argument("--max-chars", type=int, default=0,
                    help="拼接文本上限，0 = 不截断（默认，禁止默认丢数据）")
    ap.add_argument("--with-meta", action="store_true",
                    help="保留 title/source/link/source_marker 等辅助字段（溯源与核验用）")
    ap.add_argument("--out", help="输出 JSON 路径；省略则打印到 stdout")
    args = ap.parse_args(argv)

    if args.batches:
        print(format_batches())
        return 0
    if not args.company or not args.raw_dir:
        ap.error("--company 与 --raw-dir 均为必填（仅 --batches 可单独使用）")

    scenes = args.scene or (None if args.all else ["1"])
    if args.all and not args.scene:
        scenes = SCENE_ORDER

    # 校验 raw 目录场景文件是否存在（缺失 = 取数失败，按《资讯检索-取数规范.md》§9 降级）
    missing = [sc for sc in scenes if not os.path.isfile(raw_path(args.raw_dir, sc))]
    for sc in missing:
        print(f"[WARN] 缺少 {raw_path(args.raw_dir, sc)}，场景 {sc} 将按降级处理",
              file=sys.stderr)

    single = bool(scenes and len(scenes) == 1)
    try:
        if single:
            raw = load_raw(args.raw_dir, scenes[0])
            result = ingest_scene(scenes[0], args.company, raw,
                                  args.start, args.end,
                                  args.with_meta, args.max_chars)
        else:
            result = ingest_all(args.company, args.raw_dir, scenes,
                                args.with_meta, args.max_chars)
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        print("[降级] 按《资讯检索-取数规范.md》§9 处理：章节 1 先只渲染文字段、"
              "再退化为仅保留一级章标题；章节 3-8 文字描述回退到 MQL 数据生成；"
              "章节 2/9 只保留一级章标题。", file=sys.stderr)
        return 1

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)

    if single:
        _print_scene_line(result)
        if args.out:
            print(f"       -> {args.out}")
    else:
        for sc in result["scene_order"]:
            _print_scene_line(result["scenes"][sc])
        if args.out:
            print(f"       -> {args.out}（{len(result['scenes'])} 个场景）")
    if not args.out and not single:
        print(text)

    fail = result.get("error") if single else (result.get("failed_scenes") or [])
    if missing:
        return 1
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())