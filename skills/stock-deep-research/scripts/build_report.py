#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公司一页纸 · 报告组装渲染器

把 S1 取数结果 + S2 章节文本（data.json）渲染成一份自包含 HTML 报告：
- 版式、表格、4 类图表（业务拆分宽表 / 集中度 Treemap / 研发四方块+双轴图 / 财务与预测宽表）
  全部内联，无外部依赖（不引用 CDN），可离线打开、可直接打印。
- 缺失数据一律留空或整段不渲染，绝不生成占位符（零幻觉约束）。
- 4.2 / 7.2 两张宽表额外执行「整列为空的报告期不展示」（每表独立判定，两表列集合可不同；口径见 reference/MQL-取数规程.md §11.2 第 4 条，机读实现在 drop_all_empty_periods）。

用法:
    python build_report.py --input data.json --out "胜宏科技(300476.SZ)股票研究_20260921.html"
"""
from __future__ import annotations

import argparse
import html
import json
import re
from typing import Any, Dict, List, Sequence

MAIN = "#ED7D31"
DEEP = "#44546A"
LINE_BLUE = "#8FAADC"
GRID = "#E3E3E3"
OTHER_GRAY = "#D9D9D9"
FOOTER_TEXT = "本文由【AI研究员】模块自动生成，更详细的信息请登录Choice金融终端"

CHAPTER_TITLES = {
    "1": "公司近况跟踪",
    "2": "核心推荐逻辑",
    "3": "公司简介",
    "4": "公司业务拆分",
    "5": "公司产销链分析",
    "6": "公司研发实力",
    "7": "公司财务分析",
    "8": "公司盈利预测与估值分析",
    "9": "公司风险提示",
}


# ----------------------------------------------------------------- 基础工具
def esc(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def is_num(v: Any) -> bool:
    s = str(v).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "--"):
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def source_line() -> str:
    return '<div class="src">资料来源：Choice 金融终端</div>'


def src_chip(scene_key: str) -> str:
    """资讯来源溯源锚点（hover 显示来源浮层、click 打开来源链接）。

    scene_key 对应 data.json 章节键（"1".."9"），实际来源清单由渲染器
    汇总该章 `sources` 字段后写入 `#srcdata`，前端按 data-src 读取。
    """
    return (f'<span class="src-chip" data-src="{esc(scene_key)}" '
            f'title="悬停查看资讯来源，点击打开来源链接">来源</span>')


def collect_srcdata(chapters: Dict[str, Any]) -> str:
    """汇总各章节 `sources` 溯源清单，返回可嵌入 HTML 的 JSON 文本。

    只收集非空来源；无来源的章节不输出（前端对空章节不渲染浮层）。
    """
    out: Dict[str, List[Any]] = {}
    for num in "123456789":
        ch = chapters.get(num) or {}
        srcs = ch.get("sources") or []
        items = [s for s in srcs if isinstance(s, dict) and (s.get("title") or s.get("link"))]
        if items:
            out[num] = items
    if not out:
        return "{}"
    # 转义 </script> 防止破坏脚本块
    return json.dumps(out, ensure_ascii=False).replace("</", "<\\/")


def table_title(t: str) -> str:
    return f'<div class="tbl-title">{esc(t)}</div>' if t else ""


# ---------------------------------------------------- 报告期排序（表格统一降序）
def period_key(p: Any) -> tuple:
    """把 '2025-12-31' / '2025A' / '2026E' / '2026H1' 归一化为可比较的 (年,月,日)。"""
    s = str(p).strip()
    m = re.match(r"(\d{4})\D*(\d{1,2})?\D*(\d{1,2})?", s)
    if not m:
        return (0, 0, 0)
    y = int(m.group(1))
    mo = int(m.group(2)) if m.group(2) else 12
    d = int(m.group(3)) if m.group(3) else 31
    if mo > 12:
        mo, d = 12, 31
    up = s.upper()
    if "H1" in up or "Q1" in up or "Q2" in up:
        mo, d = 6, 30
    elif "H2" in up or "Q3" in up or "Q4" in up:
        mo, d = 12, 31
    return (y, mo, d)


def period_index(periods: Sequence[Any], desc: bool = True) -> tuple:
    """返回 (排序后的报告期列表, 原索引顺序)；desc=False 时保持传入顺序。

    渲染层只做列序保护，不做取数后的报告期裁剪或去重；报告期集合应已在
    MQL 阶段通过传参/筛选条件一次表达完成。
    """
    plist = [str(p) for p in periods]
    if not desc:
        return plist, list(range(len(plist)))
    keys = [period_key(p) for p in plist]
    idx = sorted(range(len(plist)), key=lambda i: (keys[i], i), reverse=True)
    return [plist[i] for i in idx], idx


def reorder_periods(periods: Sequence[Any], rows: Sequence[Sequence[Any]],
                    desc: bool = True) -> tuple:
    """报告期从左到右=最新在最左（降序）；rows 的数值列同步重排。"""
    new_periods, idx = period_index(periods, desc)
    new_rows = []
    for r in rows:
        cells = list(r)
        vals = cells[1:] if len(cells) > 1 else []
        new_rows.append([cells[0]] + [vals[i] if i < len(vals) else "" for i in idx])
    return new_periods, new_rows


# ------------------------------- 4.2 / 7.2 空报告期列剔除（v2.7.2，口径变更点）
# 权威定义：reference/MQL-取数规程.md §11.2 第 4 条；版式规则：reference/报告版式与图表规范.md §4.2 / §7.2。
# 规则：4.2 与 7.2 **各自独立**判断——某报告期在该表内没有任何有效数据（整列皆空）
#      → 该表不展示这个报告期（整列删除）。两表最终列集合**允许不一致**。
#      仅个别单元格为空仍保留该列（单元格留空，沿用既定规则）。
EMPTY_CELL_TOKENS = {"", "-", "--", "—", "–", "n/a", "na", "null", "none", "nan"}
"""视为"空单元格"的字面量（strip + 小写后比较）。0 / 0.00 是数据，不算空。"""


def is_blank_cell(v: Any) -> bool:
    """单元格是否为空（None / 空串 / 纯空白 / 占位符字面量）。"""
    if v is None:
        return True
    return str(v).strip().lower() in EMPTY_CELL_TOKENS


def drop_all_empty_periods(periods: Sequence[Any],
                           rows: Sequence[Sequence[Any]]) -> tuple:
    """剔除"整列为空"的报告期列：rows 首列为行名，其后与 periods 一一对应。

    返回 (保留的报告期列表, 同步裁剪后的 rows)。全部列都为空时返回 ([], 仅含行名的 rows)。
    """
    plist = [str(p) for p in periods]
    names = [list(r)[0] if r else "" for r in rows]
    cols = [[list(r)[i + 1] if len(r) > i + 1 else "" for r in rows] for i in range(len(plist))]
    keep = [i for i in range(len(plist)) if any(not is_blank_cell(c) for c in cols[i])]
    out_rows = [[names[k]] + [cols[i][k] for i in keep] for k in range(len(rows))]
    return [plist[i] for i in keep], out_rows


def render_table(header: Sequence[str], rows: Sequence[Sequence[Any]],
                 title: str = "", note: str = "", right_from: int = 1) -> str:
    """通用表格：表头灰底、数字右对齐、空值留空。"""
    if not rows and not header:
        return ""
    out = [table_title(title)]
    if note:
        out.append(f'<div class="tbl-note">{esc(note)}</div>')
    out.append('<table>')
    if header:
        out.append("<thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in header) + "</tr></thead>")
    out.append("<tbody>")
    for r in rows:
        tds = []
        for i, c in enumerate(r):
            cls = ' class="num"' if (i >= right_from and is_num(c)) else ""
            tds.append(f"<td{cls}>{esc(c)}</td>")
        out.append("<tr>" + "".join(tds) + "</tr>")
    out.append("</tbody></table>")
    out.append(source_line())
    return "".join(out)


def render_wide_table(spec: Dict[str, Any], desc: bool = True,
                      first_header: str = "财务指标",
                      drop_empty_periods: bool = False) -> str:
    """宽表：首列为行名，其余为各报告期数值。

    表格报告期一律从左到右降序（最新报告期在最左）；8.1 一致预测为 3A+3E 的
    时间递进表，调用时传 desc=False 保持 A→E 顺序。

    drop_empty_periods=True（7.2 主要财务指标）：降序后**剔除整列为空的报告期**
    （本表独立判定，与 4.2 表列集合允许不一致，见 reference/MQL-取数规程.md §11.2
    第 4 条）；剔除后已无任何报告期列 → 返回 ""（整表不渲染，调用方连小节标题一并省略）。
    """
    periods = spec.get("periods") or []
    rows = spec.get("rows") or []
    body: List[List[Any]] = []
    for r in rows:
        if isinstance(r, dict):
            body.append([r.get("name", "")] + list(r.get("values", [])))
        else:
            body.append(list(r))
    if periods and body:
        header_periods, body = reorder_periods(periods, body, desc=desc)
        if drop_empty_periods:
            header_periods, body = drop_all_empty_periods(header_periods, body)
            if not header_periods:
                return ""
    else:
        header_periods = list(periods)
    return render_table([first_header] + list(header_periods), body,
                        title=spec.get("title", ""), note=spec.get("note", ""))


def render_segment_table(spec: Dict[str, Any]) -> str:
    """4.2 分板块业务情况：板块跨行（rowspan）× [收入/占比/毛利率] × 报告期。

    报告期集合应已由 MQL 一次取出；这里只做两件事：① 从左到右降序（最新报告期在最左）；
    ② 剔除**整列为空**的报告期列（本表独立判定，与 7.2 表列集合允许不一致，
    见 reference/MQL-取数规程.md §11.2 第 4 条）。剔除后已无报告期列 → 返回 ""（整表不渲染）。
    """
    periods = spec.get("periods") or []
    rows = spec.get("rows") or []
    if not rows:
        return ""
    periods, idx = period_index(periods, desc=True)
    # 先按"列"汇总全部指标值 → 判定整列是否为空 → 剔除空列（列序保持降序）
    col_vals: List[List[Any]] = [[] for _ in periods]
    for _seg in rows:
        for _mname, _vals in (_seg.get("metrics") or {}).items():
            _vals = list(_vals)
            for _k, _i in enumerate(idx):
                col_vals[_k].append(_vals[_i] if _i < len(_vals) else "")
    _keep = [_k for _k in range(len(periods)) if any(not is_blank_cell(v) for v in col_vals[_k])]
    if not _keep:
        return ""
    periods = [periods[_k] for _k in _keep]
    idx = [idx[_k] for _k in _keep]
    header = ["业务板块", "财务指标"] + [str(p) for p in periods]
    body = ['<table><thead><tr>' + "".join(f"<th>{esc(h)}</th>" for h in header) + "</tr></thead><tbody>"]
    for seg in rows:
        metrics = seg.get("metrics") or {}
        mlist = list(metrics.items())
        if not mlist:
            continue
        span = len(mlist)
        for idx_m, (mname, vals) in enumerate(mlist):
            vals = list(vals)
            pick = [vals[i] if i < len(vals) else "" for i in idx]
            tr = ["<tr>"]
            if idx_m == 0:
                tr.append(f'<td class="seg" rowspan="{span}">{esc(seg.get("name", ""))}</td>')
            tr.append(f"<td>{esc(mname)}</td>")
            for v in pick + [""] * (len(periods) - len(pick)):
                tr.append(f'<td class="num">{esc(v)}</td>')
            tr.append("</tr>")
            body.append("".join(tr))
    body.append("</tbody></table>")
    return table_title(spec.get("title", "")) + "".join(body) + source_line()


# ----------------------------------------------------------------- Treemap
def _squarify(values: List[float], x: float, y: float, dx: float, dy: float) -> List[List[float]]:
    values = [v for v in values if v > 0]
    if not values:
        return []
    total = sum(values)
    scaled = [v * dx * dy / total for v in values]

    def worst(row: List[float], length: float) -> float:
        s = sum(row)
        rmax, rmin = max(row), min(row)
        return max(length * length * rmax / (s * s), (s * s) / (length * length * rmin))

    rects: List[List[float]] = []

    def layout_row(row: List[float], x: float, y: float, dx: float, dy: float, vertical: bool):
        s = sum(row)
        if vertical:
            w = s / dy if dy else 0
            yy = y
            for r in row:
                h = r / w if w else 0
                rects.append([x, yy, w, h])
                yy += h
            return x + w, y, max(dx - w, 0), dy
        h = s / dx if dx else 0
        xx = x
        for r in row:
            w = r / h if h else 0
            rects.append([xx, y, w, h])
            xx += w
        return x, y + h, dx, max(dy - h, 0)

    remaining = list(scaled)
    cx, cy, cdx, cdy = x, y, dx, dy
    row: List[float] = []
    while remaining:
        v = remaining[0]
        vertical = cdx >= cdy
        length = cdy if vertical else cdx
        if not row or worst(row + [v], length) <= worst(row, length):
            row.append(v)
            remaining.pop(0)
        else:
            cx, cy, cdx, cdy = layout_row(row, cx, cy, cdx, cdy, vertical)
            row = []
    if row:
        layout_row(row, cx, cy, cdx, cdy, cdx >= cdy)
    return rects


def treemap_svg(items: List[Dict[str, Any]], width: int = 420, height: int = 260) -> str:
    """items: [{'name':..,'ratio':float}]，占比降序；'其他' 用浅灰。"""
    if not items:
        return ""
    vals = [float(i.get("ratio") or 0) for i in items]
    rects = _squarify(vals, 0, 0, width, height)
    if not rects:
        return ""
    top = max(vals) or 1.0
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
             f'role="img" style="display:block">']
    for item, (x, y, w, h) in zip(items, rects):
        name = str(item.get("name", ""))
        ratio = float(item.get("ratio") or 0)
        if "其他" in name:
            fill = OTHER_GRAY
        else:
            k = 0.35 + 0.65 * (ratio / top) if top else 1
            fill = f"rgba(237,125,49,{k:.2f})"
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w - 2, 0):.1f}" '
                     f'height="{max(h - 2, 0):.1f}" fill="{fill}" stroke="#FFFFFF" stroke-width="1.5"/>')
        if w > 58 and h > 26:
            txt = "#FFFFFF" if "其他" not in name and ratio / top > 0.55 else "#333333"
            short = name if len(name) <= 8 else name[:7] + "…"
            parts.append(f'<text x="{x + w / 2:.1f}" y="{y + h / 2 - 2:.1f}" text-anchor="middle" '
                         f'font-size="11" fill="{txt}">{esc(short)}</text>')
            parts.append(f'<text x="{x + w / 2:.1f}" y="{y + h / 2 + 12:.1f}" text-anchor="middle" '
                         f'font-size="11" fill="{txt}">{ratio:.2f}%</text>')
    parts.append("</svg>")
    return "".join(parts)


# ----------------------------------------------------------------- 双轴图
def dual_axis_svg(periods: List[str], bars: List[Any], line: List[Any],
                  unit_bar: str = "亿元", unit_line: str = "%",
                  width: int = 560, height: int = 250) -> str:
    if not periods or not bars:
        return ""
    nums = [float(v) for v in bars if is_num(v)]
    if not nums:
        return ""
    pad_l, pad_r, pad_t, pad_b = 46, 46, 18, 42
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b
    vmax = max(nums) * 1.15 or 1
    lvals = [float(v) for v in line if is_num(v)]
    lmax = (max(lvals) * 1.3 if lvals else 1) or 1
    n = len(periods)
    slot = iw / n
    bw = min(slot * 0.5, 46)
    p = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" style="display:block">']
    for i in range(5):
        yy = pad_t + ih * i / 4
        p.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{pad_l + iw}" y2="{yy:.1f}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
    pts = []
    for i, per in enumerate(periods):
        cx = pad_l + slot * i + slot / 2
        if i < len(bars) and is_num(bars[i]):
            v = float(bars[i])
            bh = ih * v / vmax
            p.append(f'<rect x="{cx - bw / 2:.1f}" y="{pad_t + ih - bh:.1f}" width="{bw:.1f}" '
                     f'height="{bh:.1f}" fill="{LINE_BLUE}"/>')
            p.append(f'<text x="{cx:.1f}" y="{pad_t + ih - bh - 4:.1f}" text-anchor="middle" '
                     f'font-size="10" fill="#666">{v:.2f}</text>')
        if i < len(line) and is_num(line[i]):
            lv = float(line[i])
            pts.append((cx, pad_t + ih - ih * lv / lmax, lv))
        p.append(f'<text x="{cx:.1f}" y="{pad_t + ih + 16:.1f}" text-anchor="middle" '
                 f'font-size="10" fill="#666">{esc(per)}</text>')
    if len(pts) >= 2:
        p.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>' %
                 (MAIN, " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)))
    for x, y, lv in pts:
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{MAIN}"/>')
        p.append(f'<text x="{x:.1f}" y="{y - 6:.1f}" text-anchor="middle" font-size="10" '
                 f'fill="{MAIN}">{lv:.2f}</text>')
    p.append(f'<text x="{pad_l - 6}" y="{pad_t - 6}" text-anchor="end" font-size="10" fill="#888">'
             f'{esc(unit_bar)}</text>')
    p.append(f'<text x="{width - pad_r + 6}" y="{pad_t - 6}" font-size="10" fill="#888">'
             f'{esc(unit_line)}</text>')
    p.append("</svg>")
    return "".join(p)


# ----------------------------------------------------------------- 章节渲染
def chapter_head(num: str) -> str:
    return f'<h2 class="ch"><span class="no">{num}</span>{esc(CHAPTER_TITLES[num])}</h2>'


def sec_block(ch: Dict[str, Any], scene_key: str = "") -> str:
    """章节内文字段：支持 "**短语**：" / "**短语**，" 开头，全角空格缩进。

    scene_key 非空且该章存在 `sources` 时，每段末尾追加溯源锚点
    （hover+click 溯源，见 collect_srcdata / 内联 JS）。
    """
    texts = ch.get("texts") or ([ch["text"]] if ch.get("text") else [])
    use_src = bool(scene_key) and bool(ch.get("sources"))
    out = []
    for t in texts:
        t = str(t).strip()
        if not t:
            continue
        # 只把段首的 **加粗短语** 渲染为 .lead，其余正文保持常规字重
        m = re.match(r"^\*\*(.+?)\*\*(.*)$", t, flags=re.S)
        if m:
            body = ('<span class="lead">' + esc(m.group(1)) + "</span>"
                    + esc(m.group(2)))
        else:
            body = esc(t)
        if use_src:
            body += src_chip(scene_key)
        out.append(f'<p class="body">{body}</p>')
    return "".join(out)


def render_chapter(num: str, ch: Dict[str, Any]) -> str:
    out = [f'<section class="chapter">{chapter_head(num)}']
    if not ch:
        out.append("</section>")
        return "".join(out)
    if num == "1":
        out.append(sec_block(ch, "1"))
        cat = ch.get("catalyst") or {}
        if cat.get("rows"):
            if ch.get("sources"):
                out.append('<div class="src-row">' + src_chip("1") + "</div>")
            rows = cat["rows"]
            if rows and str(rows[0][0]).strip() in ("时间", "日期"):
                out.append(render_table(rows[0], rows[1:], title=cat.get("title", ""),
                                        note=cat.get("note", ""), right_from=99))
            else:
                out.append(render_table(["时间", "事件", "预期影响"], rows,
                                        title=cat.get("title", ""), note=cat.get("note", ""),
                                        right_from=99))
    elif num == "2":
        use_src = bool(ch.get("sources"))
        for key, label in (("short", "短期逻辑"), ("long", "长期逻辑")):
            subs = ch.get(key) or []
            if not subs:
                continue
            out.append(f'<div class="h3">{label}</div>')
            for s in subs:
                head = str(s.get("head", "")).rstrip("：:")
                tail = src_chip("2") if use_src else ""
                out.append(f'<p class="sub"><span class="lead">{esc(head)}：</span>'
                           f'　　{esc(s.get("body", ""))}{tail}</p>')
    elif num == "3":
        rows = ch.get("rows") or []
        if rows:
            body = "".join(f'<tr><td class="lbl">{esc(r[0])}</td><td>{esc(r[1])}</td></tr>'
                           for r in rows if len(r) >= 2)
            out.append(f'<table class="plain"><tbody>{body}</tbody></table>')
            if ch.get("sources"):
                out.append('<div class="src-row">' + src_chip("3") + "</div>")
    elif num == "4":
        out.append('<div class="h3">4.1 公司盈利方式</div>')
        out.append(sec_block(ch, "4"))
        seg = ch.get("segments") or {}
        if seg.get("rows"):
            seg_html = render_segment_table(seg)
            # 整列为空的报告期不展示；剔完已无报告期列 → 表与小节标题一并省略
            if seg_html:
                out.append('<div class="h3">4.2 分板块业务情况</div>')
                out.append(seg_html)
    elif num == "5":
        for key, label in (("customers", "5.1 主要客户情况"), ("suppliers", "5.2 主要供应商情况")):
            blk = ch.get(key) or {}
            if not blk or not (blk.get("items") or blk.get("summary")):
                continue
            out.append(f'<div class="h3">{label}</div>')
            if blk.get("text"):
                tail = src_chip("5") if ch.get("sources") else ""
                out.append(f'<p class="body">{esc(blk["text"])}{tail}</p>')
            items = blk.get("items") or []
            if items:
                head = ["名称", "金额(亿元)", "占比(%)"]
                if items and isinstance(items[0], dict):
                    tm = [{"name": i.get("name", ""), "ratio": i.get("ratio") or 0} for i in items]
                    rows = [[i.get("name", ""), i.get("amount", ""), i.get("ratio", "")] for i in items]
                else:
                    tm = [{"name": r[0], "ratio": float(str(r[2]).replace("%", "") or 0)} for r in items]
                    rows = [list(r) for r in items]
                out.append('<div class="tm-wrap"><div class="tm">' + treemap_svg(tm) + "</div>")
                out.append('<div class="tm-detail">' + render_table(head, rows + list(blk.get("summary") or []),
                                                                    title=blk.get("title", "")) + "</div></div>")
    elif num == "6":
        out.append(sec_block(ch, "6"))
        cards = ch.get("cards") or []
        trend = ch.get("trend") or {}
        if cards or trend.get("periods"):
            out.append('<div class="rd-wrap">')
            if cards:
                out.append('<div class="cards">')
                for c in cards:
                    label, value, unit = (list(c) + ["", ""])[:3]
                    out.append(f'<div class="card"><div class="cv">{esc(value)}</div>'
                               f'<div class="cu">{esc(unit)}</div>'
                               f'<div class="cl">{esc(label)}</div></div>')
                out.append("</div>")
            if trend.get("periods"):
                out.append('<div class="chart">' + table_title(trend.get("title", "研发投入趋势")) +
                           dual_axis_svg(list(trend["periods"]), list(trend.get("expend") or []),
                                         list(trend.get("ratio") or [])) + source_line() + "</div>")
            out.append("</div>")
    elif num == "7":
        out.append('<div class="h3">7.1 财务健康状况评估</div>')
        out.append(sec_block(ch, "7"))
        tbl = ch.get("table") or {}
        if tbl.get("rows"):
            # 7.2 与 4.2 独立判定：整列为空的报告期不展示（两表列集合允许不一致）
            tbl_html = render_wide_table(tbl, drop_empty_periods=True)
            if tbl_html:
                out.append('<div class="h3">7.2 主要财务指标</div>')
                out.append(tbl_html)
    elif num == "8":
        cons = ch.get("consensus") or {}
        if cons.get("rows"):
            out.append('<div class="h3">8.1 一致预测</div>')
            # 8.1 表的指标行是**固定表结构**（沪深京 10 行 / 港股 9 行，行名与行序逐字，
            # 不得少返回），由 data.json 的 rows 原样渲染；某期缺值 → 单元格留空、整行保留。
            # 固定行集的机读定义：mql_api.TABLE_8_1_ROWS / validate_report.CONSENSUS_ROWS_8_1。
            out.append(render_wide_table(cons, desc=False, first_header="预测指标"))
        if ch.get("texts"):
            out.append('<div class="h3">8.2 估值分析</div>')
            out.append(sec_block(ch, "8"))
    elif num == "9":
        risks = ch.get("risks") or []
        tail = src_chip("9") if ch.get("sources") else ""
        for r in risks:
            name = r.get("name", "")
            out.append(f'<p class="body"><span class="lead">{esc(name)}：</span>'
                       f'{esc(r.get("desc", ""))}　<span class="lead">可观测指标：</span>'
                       f'{esc(r.get("metric", ""))}{tail}</p>')
    out.append("</section>")
    return "".join(out)


# ----------------------------------------------------------------- 样式
CSS = """
* { box-sizing: border-box; }
body { margin:0; background:#F5F6F8; color:#222;
       font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB",Arial,sans-serif; }
.page { max-width:1040px; margin:28px auto 60px; background:#FFFFFF; padding:44px 52px 72px;
        box-shadow:0 2px 14px rgba(0,0,0,.08); }
h1 { text-align:center; font-size:24px; color:#333; margin:0 0 6px; letter-spacing:.5px; }
.meta { text-align:center; font-size:12px; color:#888; margin-bottom:6px; }
.rule { height:3px; background:%(main)s; width:78px; margin:14px auto 30px; border-radius:2px; }
h2.ch { font-size:17px; color:%(deep)s; margin:34px 0 12px; padding-left:10px;
        border-left:5px solid %(main)s; line-height:1.2; }
h2.ch .no { display:inline-block; min-width:22px; color:%(main)s; font-weight:700; margin-right:6px; }
.h3 { font-size:14px; font-weight:700; color:%(deep)s; margin:16px 0 8px; }
p.body { font-size:13.5px; line-height:1.9; margin:8px 0; text-align:justify; }
p.sub { font-size:13.5px; line-height:1.9; margin:6px 0; text-align:justify; }
.lead { font-weight:700; color:#1F1F1F; }
table { width:100%%; border-collapse:collapse; margin:6px 0 4px; font-size:12.5px; }
th { background:#F2F2F2; color:#333; font-weight:700; text-align:left; padding:7px 9px;
     border:1px solid #E0E0E0; white-space:nowrap; }
td { padding:6px 9px; border:1px solid #E8E8E8; vertical-align:top; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
td.seg { font-weight:700; background:#FBFBFB; }
table.plain td { border:none; border-bottom:1px dashed #EDEDED; padding:8px 4px; font-size:13.5px; }
table.plain td.lbl { width:96px; font-weight:700; color:%(deep)s; }
.tbl-title { font-size:13px; font-weight:700; color:#333; margin:14px 0 4px; }
.tbl-note { font-size:11.5px; color:#999; margin-bottom:4px; }
.src { font-size:11.5px; color:#999; font-style:italic; margin:2px 0 12px; }
.tm-wrap, .rd-wrap { display:flex; gap:18px; align-items:flex-start; flex-wrap:wrap; }
.tm { flex:1 1 340px; min-width:300px; }
.tm-detail { flex:1 1 380px; }
.cards { display:flex; gap:12px; flex-wrap:wrap; flex:1 1 300px; }
.card { flex:1 1 120px; border:1px solid #EEE; border-top:3px solid %(main)s; border-radius:6px;
        padding:12px 10px; text-align:center; background:#FDFDFD; }
.card .cv { font-size:19px; font-weight:700; color:%(main)s; }
.card .cu { font-size:11px; color:#999; }
.card .cl { font-size:12px; color:#555; margin-top:4px; }
.chart { flex:1 1 460px; }
.footer { position:fixed; bottom:0; left:0; right:0; text-align:center; font-size:11px;
          color:#999; background:rgba(255,255,255,.94); padding:6px 0; border-top:1px solid #EEE; }
@media print {
  body { background:#FFF; }
  .page { box-shadow:none; margin:0; max-width:none; padding:0 8mm 16mm; }
  .chapter, table, .tm-wrap, .rd-wrap { page-break-inside:avoid; }
  .footer { position:fixed; }
}

/* ---------- hover+click 资讯溯源 ---------- */
.src-row { margin:2px 0 8px; }
.src-chip { display:inline-block; margin-left:6px; padding:0 8px; font-size:11px;
            color:#7A5200; border:1px solid #E8C37A; border-radius:9px;
            background:#FFF7E6; cursor:pointer; vertical-align:1px;
            user-select:none; white-space:nowrap; line-height:1.7; }
.src-chip:hover { background:#FFE9B8; border-color:#D9A95C; }
.src-panel { position:fixed; z-index:999; width:380px; max-width:92vw;
             max-height:55vh; overflow:auto; background:#FFFDF7;
             border:1px solid #E4D5AE; border-radius:6px;
             box-shadow:0 4px 14px rgba(0,0,0,.14); padding:8px 10px;
             font-size:12px; text-align:left; }
.src-panel-title { font-size:12px; font-weight:700; color:#7A5200; margin:0 0 6px; }
.src-item { display:block; font-size:12px; color:#1F4E9C; text-decoration:none;
            padding:4px 2px; border-bottom:1px dashed #EDE3C8; line-height:1.5; }
.src-item:last-child { border-bottom:none; }
.src-item:hover { color:#B3541E; text-decoration:underline; }
.src-item .tm { color:#999; margin-left:4px; }
""" % {"main": MAIN, "deep": DEEP}


TRACE_JS = """
<script>
(function () {
  "use strict";
  var SRC = {};
  try { SRC = JSON.parse(document.getElementById('srcdata').textContent || '{}') || {}; }
  catch (e) { SRC = {}; }
  var panel = null, timer = null;
  function hide() { if (panel) { panel.remove(); panel = null; } }
  function show(el) {
    hide();
    var key = el.getAttribute('data-src');
    var list = (SRC[key] || []).filter(function (s) { return s && (s.title || s.link); });
    if (!list.length) return;
    panel = document.createElement('div');
    panel.className = 'src-panel';
    var h = document.createElement('div');
    h.className = 'src-panel-title';
    h.textContent = '资讯来源（第 ' + key + ' 章）——悬停查看，点击来源可跳转原文';
    panel.appendChild(h);
    list.forEach(function (s, i) {
      var a = document.createElement('a');
      a.className = 'src-item';
      var label = (i + 1) + '. ' + (s.title || '（无标题条目）');
      if (s.time) label += '　' + s.time;
      if (s.source) label += '　[' + s.source + ']';
      if (s.source_marker) label += '　' + s.source_marker;
      a.textContent = label;
      if (s.link) { a.href = s.link; a.target = '_blank'; a.rel = 'noopener noreferrer'; }
      panel.appendChild(a);
    });
    document.body.appendChild(panel);
    var r = el.getBoundingClientRect();
    var left = Math.max(4, Math.min(r.left, window.innerWidth - 420));
    var top = r.bottom + 8;
    if (top + panel.offsetHeight > window.innerHeight - 8) {
      top = Math.max(4, r.top - panel.offsetHeight - 8);
    }
    panel.style.left = left + 'px';
    panel.style.top = top + 'px';
  }
  document.addEventListener('mouseover', function (e) {
    var t = e.target && e.target.closest ? e.target.closest('.src-chip') : null;
    if (!t) return;
    clearTimeout(timer);
    show(t);
  });
  document.addEventListener('mouseout', function (e) {
    var t = e.target && e.target.closest ? e.target.closest('.src-chip, .src-panel') : null;
    if (!t) return;
    timer = setTimeout(hide, 300);
  });
  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest ? e.target.closest('.src-chip') : null;
    if (!t) return;
    var key = t.getAttribute('data-src');
    var linked = (SRC[key] || []).filter(function (s) { return s && s.link; });
    if (linked.length) { window.open(linked[0].link, '_blank'); }
    else { show(t); }
    e.preventDefault();
  });
})();
</script>
"""


def build(data: Dict[str, Any]) -> str:
    co = data.get("company") or {}
    name = co.get("name", "")
    code = co.get("secucode", "")
    title = f"{name}({code}) 股票研究" if name or code else "公司一页纸"
    metas = [m for m in [code, co.get("report_period"), f"数据截止日：{co.get('as_of', '')}"
                         if co.get("as_of") else ""] if m]
    chapters = data.get("chapters") or {}
    body = "".join(render_chapter(n, chapters.get(n) or {}) for n in "123456789")
    srcdata_block = ('<script type="application/json" id="srcdata">'
                     + collect_srcdata(chapters) + "</script>\n" + TRACE_JS)
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{esc(title)}</title><style>{CSS}</style></head>
<body><div class="page">
<h1>{esc(title)}</h1>
<div class="meta">{esc(" · ".join(metas))}</div>
<div class="rule"></div>
{body}
</div>
<div class="footer">{esc(FOOTER_TEXT)}</div>
{srcdata_block}
</body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="公司一页纸 HTML 渲染器")
    ap.add_argument("--input", required=True, help="data.json 路径")
    ap.add_argument("--out", required=True, help="输出 HTML 路径")
    args = ap.parse_args()
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(build(data))
    print(f"[OK] rendered -> {args.out}")


if __name__ == "__main__":
    main()
