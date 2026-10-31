#!/usr/bin/env python3
"""Render static SVG charts for the alert report; no network, no JS runtime.

V20 format rules are baked in:
- 统一图表字号体系：所有图表以显示宽度 630px（HTML 640px/Word 620px 容器）为基准，
  通过 DISPLAY_W / viewBox 宽度反推 SVG 字号（DISPLAY_W ≈ 630），
  保证 HTML、Word 两渠道图表内标题/图例/轴/正文与文档正文(15px)排版一致且不缩放漂移。
- 图表字号档位（显示效果）：图表标题 13-15px、图例/轴 10.5-11.5px、图内正文 12-12.5px。
- volume：图例置于绘图区上方、间距充足不重叠；备注一律放图下说明（figcaption），SVG 内不再绘制。
- distribution：标题居中；图例字号与正文一致。
- chain：无右上角说明框；面板底框高度按内容行数自适应，所有节点框不越界。
- timeline：时间轴长宽自适应，事件盒/图例/刻度字号统一。
Four modes: volume / distribution / chain / timeline.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FONT_STACK = '"PingFang SC","Microsoft YaHei",sans-serif'
GRADE_COLORS = {"红": "#d64545", "黄": "#c9a13b", "蓝": "#4a7fd4", "灰": "#b8c0cc"}
# 图表统一显示基准宽度（HTML 640 / Word 620，取中间值保证两渠道误差 <4%）
DISPLAY_W = 630.0


class InputError(ValueError):
    pass


def _text_width(text, font_size):
    """CJK chars ~1em, ASCII ~0.55em; conservative estimate for badge sizing."""
    width = 0
    for ch in text:
        width += font_size if ord(ch) > 0x2E80 else font_size * 0.55
    return width


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _wrap(text, max_chars):
    """V21：按“CJK≈1 字、ASCII≈0.62 字”估算宽度，在不超过 max_chars 处断行；
    返回行列表（不删字，尾部行过长时截断并按 max_chars 保留）。"""
    lines, cur, w = [], "", 0.0
    text = str(text)
    for ch in text:
        cw = 1.0 if ord(ch) > 0x2E80 else 0.62
        if w + cw > max_chars and cur:
            lines.append(cur)
            cur, w = "", 0.0
        cur += ch
        w += cw
    if cur or not lines:
        lines.append(cur)
    return lines


def render_volume_chart(data, title="周度舆情声量（去重资讯篇数）"):
    """data: [{bucket, total, focus(optional), focus_name(optional)}] -> static bar+line SVG.
    V20: 图例置于绘图区上方、项间距 26 单位防重叠；SVG 内不绘制备注（并入图下说明）；
    字号按 630px 显示基准反推：标题 20（≈13px）、图例 17（≈11px）、轴/数值 16（≈10.5px）。"""
    if not isinstance(data, list) or not data or len(data) < 2:
        raise InputError("volume data needs at least 2 buckets")
    for i, row in enumerate(data):
        if not isinstance(row, dict) or "bucket" not in row or "total" not in row:
            raise InputError(f"volume row {i} needs bucket and total")
        if not isinstance(row["total"], int) or row["total"] < 0:
            raise InputError(f"volume row {i} total must be a nonnegative int")
        if "focus" in row and (not isinstance(row["focus"], int) or row["focus"] < 0):
            raise InputError(f"volume row {i} focus must be a nonnegative int")
    if len(data) > 14:
        raise InputError("volume data supports up to 14 weekly buckets")
    focus_name = data[0].get("focus_name", "其中回购类")
    has_focus = any("focus" in row for row in data)
    max_val = max(row["total"] for row in data)
    if has_focus:
        max_val = max(max_val, max(row.get("focus", 0) for row in data))
    W, H = 960, 360
    left, zero_y = 56, 224
    plot_w = W - left - 24
    scale = 160 / max_val if max_val else 1
    n = len(data)
    slot = plot_w / n
    bar_w = min(18, slot * 0.38)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {W} {H}"',
        'preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:auto" role="img" aria-labelledby="vct vcd">',
        f'<title id="vct">{_esc(title)}</title>',
        '<desc id="vcd">柱形为各周去重资讯篇数' + (f'，折线为{focus_name}篇数' if has_focus else '') + '。</desc>',
        f'<style>.t{{font:600 20px {FONT_STACK};fill:#1f2933}}.ax{{stroke:#8a94a6;stroke-width:1.5}}',
        f'.gd{{stroke:#e3e8f0;stroke-width:1}}.xl{{font:500 16px {FONT_STACK};fill:#5b6472}}',
        f'.yl{{font:500 16px {FONT_STACK};fill:#5b6472}}.vl{{font:600 16px {FONT_STACK};fill:#1f2933}}',
        f'.lg{{font:400 17px {FONT_STACK};fill:#3d4757}}</style>',
        f'<text x="16" y="26" class="t">{_esc(title)}</text>',
    ]
    for step in range(0, 5):
        gy = zero_y - step * 40
        parts.append(f'<line class="gd" x1="{left}" y1="{gy:.0f}" x2="{left+plot_w}" y2="{gy:.0f}"/>')
    points = []
    for i, row in enumerate(data):
        cx = left + slot * i + slot / 2
        bx = cx - bar_w / 2
        h = row["total"] * scale
        if row["total"] > 0:
            parts.append(f'<rect x="{bx:.1f}" y="{zero_y-h:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="#4a7fd4" rx="2.5"/>')
            parts.append(f'<text x="{cx:.0f}" y="{zero_y-h-6:.0f}" text-anchor="middle" class="vl">{row["total"]}</text>')
        if has_focus:
            fy = zero_y - row.get("focus", 0) * scale
            points.append(f"{cx:.0f},{fy:.0f}")
    if has_focus:
        parts.append(f'<path d="M {" L ".join(points)}" fill="none" stroke="#c9a13b" stroke-width="2.2" stroke-dasharray="7,4"/>')
        for i, row in enumerate(data):
            cx = left + slot * i + slot / 2
            fy = zero_y - row.get("focus", 0) * scale
            parts.append(f'<circle cx="{cx:.0f}" cy="{fy:.0f}" r="3.6" fill="#c9a13b"/>')
            if row.get("focus", 0) > 0:
                parts.append(f'<text x="{cx:.0f}" y="{fy-7:.0f}" text-anchor="middle" class="vl" fill="#8a6a1c">{row.get("focus", 0)}</text>')
    parts.append(f'<line class="ax" x1="{left}" y1="{zero_y}" x2="{left+plot_w}" y2="{zero_y}"/>')
    # V20: 图例置顶横向一行，项间距 26 单位（约 17px），不重叠
    legend_items = [("bar", "资讯篇数")]
    if has_focus:
        legend_items.append(("line", focus_name))
    total_lw = 0
    for kind, label in legend_items:
        total_lw += (36 if kind == "bar" else 46) + _text_width(label, 17) + 26
    lx = left + (plot_w - total_lw) / 2
    ly = 46
    for kind, label in legend_items:
        if kind == "bar":
            parts.append(f'<rect x="{lx:.0f}" y="{ly}" width="13" height="13" rx="2.5" fill="#4a7fd4"/>')
            parts.append(f'<text x="{lx+18:.0f}" y="{ly+11}" class="lg">{_esc(label)}</text>')
            lx += 36 + _text_width(label, 17) + 26
        else:
            parts.append(f'<line x1="{lx:.0f}" y1="{ly+6}" x2="{lx+13:.0f}" y2="{ly+6}" stroke="#c9a13b" stroke-width="2.5" stroke-dasharray="7,4"/>')
            parts.append(f'<text x="{lx+18:.0f}" y="{ly+11}" class="lg">{_esc(label)}</text>')
            lx += 46 + _text_width(label, 17) + 26
    # 横轴日期斜排45°（Word与HTML通用）；备注不入图（并入图下说明）
    xlab_y = zero_y + 14
    for i, row in enumerate(data):
        cx = left + slot * i + slot / 2
        parts.append(f'<text x="{cx:.0f}" y="{xlab_y}" text-anchor="end" class="xl" '
                     f'transform="rotate(-45 {cx:.0f} {xlab_y})">{_esc(row["bucket"])}</text>')
    axis_max = max_val if max_val else 1
    for step in range(0, 5):
        gy = zero_y - step * 40
        tick = axis_max * step / 4
        tick = int(tick) if abs(tick - round(tick)) < 1e-9 else round(tick, 1)
        parts.append(f'<text x="{left-8}" y="{gy+4:.0f}" text-anchor="end" class="yl">{tick}</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def render_distribution_chart(data, title="预警分布图", subtitle=None):
    """data: [{grade(红/黄/蓝/灰), label, count}] -> static donut SVG (counts, not percentages).
    V20: 标题居中（text-anchor=middle @ x=490）；字号沿用 V19（显示≈17px 标题/15px 图例，与正文一致）。"""
    if not isinstance(data, list) or not data:
        raise InputError("distribution data needs grade/label/count rows")
    total = 0
    for i, row in enumerate(data):
        if not isinstance(row, dict) or row.get("grade") not in GRADE_COLORS:
            raise InputError(f"distribution row {i}: grade must be one of {list(GRADE_COLORS)}")
        if not isinstance(row.get("count"), int) or row["count"] < 0:
            raise InputError(f"distribution row {i}: count must be a nonnegative int")
        if not str(row.get("label", "")).strip():
            raise InputError(f"distribution row {i}: label required")
        total += row["count"]
    cx, cy, r, stroke = 260, 300, 92, 42
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 980 612"',
        'preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:auto" role="img" aria-labelledby="dct dcd">',
        f'<title id="dct">{_esc(title)}</title>',
        '<desc id="dcd">环形图展示各预警等级的对象数量。</desc>',
        f'<style>.t{{font:600 26px {FONT_STACK};fill:#1f2933}}.lg{{font:400 24px {FONT_STACK};fill:#3d4757}}',
        f'.lgv{{font:700 24px {FONT_STACK};fill:#1f2933}}.ct{{font:700 28px {FONT_STACK};fill:#1f2933}}',
        f'.cs{{font:400 16px {FONT_STACK};fill:#5b6472}}.note{{font:400 16px {FONT_STACK};fill:#667}}</style>',
        f'<text x="490" y="46" text-anchor="middle" class="t">{_esc(title)}'
        + (f'（{_esc(subtitle)}）' if subtitle else '') + '</text>',
    ]
    import math as _math
    start_deg = -90.0  # 12点方向起始
    for row in data:
        frac = row["count"] / total if total else 0
        color = GRADE_COLORS[row["grade"]]
        if row["count"] > 0 and frac > 0:
            sweep = frac * 360.0
            end_deg = start_deg + sweep
            a0, a1 = _math.radians(start_deg), _math.radians(min(end_deg, start_deg + 359.99))
            x0, y0 = cx + r * _math.cos(a0), cy + r * _math.sin(a0)
            x1, y1 = cx + r * _math.cos(a1), cy + r * _math.sin(a1)
            large_arc = 1 if sweep > 180 else 0
            parts.append(f'<path d="M {x0:.2f} {y0:.2f} A {r} {r} 0 {large_arc} 1 {x1:.2f} {y1:.2f}" '
                         f'fill="none" stroke="{color}" stroke-width="{stroke}"/>')
            start_deg = end_deg
    parts.append(f'<text x="{cx}" y="{cy-4}" text-anchor="middle" class="ct">{total} 项</text>')
    parts.append(f'<text x="{cx}" y="{cy+30}" text-anchor="middle" class="cs">研判对象</text>')
    ly = 130
    meaning = {"红": "红色：正在发生，须立即处置", "黄": "黄色：有预期但证据不足", "蓝": "蓝色：持续观察", "灰": "不设预警（利好或已解除）"}
    for row in data:
        color = GRADE_COLORS[row["grade"]]
        label_w = _text_width(row["label"], 24)
        parts.append(f'<rect x="540" y="{ly}" width="18" height="18" rx="4" fill="{color}"/>')
        parts.append(f'<text x="568" y="{ly+14}" class="lg">{_esc(row["label"])}</text>')
        parts.append(f'<text x="{568 + label_w + 12:.0f}" y="{ly+14}" class="lgv">{row["count"]} 项</text>')
        parts.append(f'<text x="568" y="{ly+42}" class="note">{_esc(meaning[row["grade"]])}</text>')
        ly += 92
    parts.append(f'<text x="26" y="594" class="note">分级依据：发酵判断与证据链完整程度；数据截至报告当日</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def render_chain_chart(data):
    """data: {warning, sources[], mechanism{title,details[]}, trigger{...}, impact{...},
    nodes_future[], observations[], hedge} -> static chain SVG per report-format.md.

    V21: 无右上角说明框；面板背景拉伸至视口边缘（28..1180，左右留白≈2%），
    HTML 端非限宽显示（占满报告正文宽度），Word 620px 嵌入；
    字号面版标题26/列头24/正文22/小字21（HTML 全宽≈19/18/16px，Word≈13/12/11px）；
    所有框内文本按列宽自动换行（_wrap），面板与各框高度按换行后的行数自适应，
    杜绝文字重叠与越界；文本不删字（只做行内截断兜底）。"""
    required = ("warning", "sources", "mechanism", "trigger", "impact")
    if not isinstance(data, dict):
        raise InputError("chain data must be an object")
    for key in required:
        if key not in data:
            raise InputError(f"chain data missing key: {key}")
    warning = str(data["warning"])
    # 三列网格：内容 X=46/408/776；面板贴边 20..1178，列间留 38/52 空隙画箭头
    COL1_X, COL2_X, COL3_X = 46, 408, 776
    COL1_W, COL2_W, COL3_W = 314, 292, 380
    PANELS = ((14, 354), (396, 316), (756, 428))  # (x, width)：A 14..368 B 396..712 C 756..1184（左右留白≈1.2%)
    ROW1_Y = 92
    ARROW1, ARROW2 = (370, 394), (714, 754)        # 面板间隙内箭头起止 x
    NT_FS, NS_FS, SL_FS, SM_FS = 26, 22, 24, 21
    LINE_H = 36.0
    COL_PAD = 16
    max_chars = {COL1_X: int((COL1_W - 2 * COL_PAD - 16) / NS_FS),
                 COL2_X: int((COL2_W - 2 * COL_PAD - 16) / NS_FS),
                 COL3_X: int((COL3_W - 2 * COL_PAD - 16) / NS_FS)}
    # 标题字体更大（NT_FS），按标题字号单独收紧换行宽度，防止标题越出面板
    max_chars_nt = {COL1_X: int((COL1_W - 2 * COL_PAD - 16) / NT_FS),
                    COL2_X: int((COL2_W - 2 * COL_PAD - 16) / NT_FS),
                    COL3_X: int((COL3_W - 2 * COL_PAD - 16) / NT_FS)}

    src_title = _wrap(data.get("source_title", "核心源头事实"), max_chars_nt[COL1_X])[:2]
    src_lines = []
    for s in data["sources"][:4]:
        src_lines += _wrap(s, max_chars[COL1_X])
    mech = data["mechanism"]
    mech_title = _wrap(mech.get("title", "传导机制"), max_chars_nt[COL2_X])[:2]
    mech_lines = []
    for d in mech.get("details", [])[:4]:
        mech_lines += _wrap(d, max_chars[COL2_X])
    trig = data["trigger"]
    trig_lines = _wrap(trig.get("condition", ""), max_chars[COL2_X])[:2]
    impact = data["impact"]
    imp_lines = []
    for d in impact.get("details", [])[:3]:
        imp_lines += _wrap(d, max_chars[COL3_X])
    obs = [str(o) for o in data.get("observations", [])][:2]
    obs_reasons = [str(o) for o in data.get("obs_reasons", [])][:len(obs)]
    obs_blocks = [(_wrap(o, max_chars_nt[COL2_X]), _wrap(obs_reasons[i] if i < len(obs_reasons) else "", max_chars[COL2_X]))
                  for i, o in enumerate(obs)]
    nodes = [str(n) for n in data.get("nodes_future", [])][:2]
    node_blocks = [_wrap(n, max_chars[COL3_X]) for n in nodes]

    # —— 高度计算（全长随换行后行数自适应） ——
    h1 = 50 + 36 * len(src_title) + 14 + LINE_H * len(src_lines)
    h2 = 50 + 36 * len(mech_title) + 14 + LINE_H * len(mech_lines)
    h3 = 62 + 36 * max(0, len(imp_lines) - 1) + 36  # 标题基线62前留5px余量
    trig_h = 62 + LINE_H * max(0, len(trig_lines) - 1) + 34
    obs_h = 62 + max((LINE_H * (len(t) + len(r) - 1) for t, r in obs_blocks), default=LINE_H) + 34
    node_h = 62 + LINE_H * max(0, max((len(b) for b in node_blocks), default=1) - 1) + 34
    # 行距须大于同列框高 + 余量，否则上下框重叠（V21 自适应）
    ROW_STEP = max(128, int(obs_h) + 40, int(node_h) + 40)

    ROW2_Y = ROW1_Y + max(h1, h2, h3) + 28   # 第二行基线自适应（修复同列框重叠）
    LABEL_Y = ROW2_Y + trig_h + 30
    OBS1_Y = ROW2_Y + trig_h + 54
    bottoms = [ROW1_Y + h1, ROW1_Y + h2, ROW2_Y + trig_h, ROW1_Y + h3]
    bottoms.append(LABEL_Y + 8)
    for i in range(len(obs_blocks)):
        bottoms.append(OBS1_Y + i * ROW_STEP + obs_h)
    for i in range(len(node_blocks)):
        bottoms.append(ROW2_Y + i * ROW_STEP + node_h)
    panel_bottom = max(bottoms) + 30
    H = panel_bottom + 58
    panel_h = panel_bottom - 52

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 1200 {int(H)}"',
        'preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:auto" role="img" aria-labelledby="fct fcd">',
        f'<title id="fct">{_esc(warning)}｜本期风险发酵链路图</title>',
        '<desc id="fcd">主链路自源头事实经传导机制，在触发条件下形成自增强负反馈，指向潜在影响；支链列为待观察。节点均未越出面板边界。</desc>',
        '<defs>',
        '<marker id="vc-ar" viewBox="0 0 10 10" refX="9" refY="5" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L10,5 L0,10 z" fill="#d64545"/></marker>',
        '<marker id="vc-ob" viewBox="0 0 10 10" refX="9" refY="5" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L10,5 L0,10 z" fill="#c9a13b"/></marker>',
        '</defs>',
        f'<style>.fn{{fill:#f4f7fd;stroke:#8a94a6;stroke-width:1.5}}.fr{{fill:#fdeeee;stroke:#d64545;stroke-width:2}}',
        f'.fy{{fill:#fdf8e9;stroke:#c9a13b;stroke-width:1.8}}.fb{{fill:#fff;stroke:#c9a13b;stroke-width:1.5;stroke-dasharray:5,4}}',
        f'.nt{{font:700 {NT_FS}px {FONT_STACK};fill:#1f2933}}.ns{{font:400 {NS_FS}px {FONT_STACK};fill:#5b6472}}',
        f'.ce{{stroke:#d64545;stroke-width:2.6;fill:none;marker-end:url(#vc-ar)}}',
        f'.oe{{stroke:#c9a13b;stroke-width:2;fill:none;marker-end:url(#vc-ob)}}',
        f'.sl{{font:600 {SL_FS}px {FONT_STACK};fill:#3d4757}}</style>',
        f'<rect x="{PANELS[0][0]}" y="52" width="{PANELS[0][1]}" height="{panel_h:.0f}" rx="14" fill="#fafbfd" stroke="#e3e8f0"/>',
        f'<rect x="{PANELS[1][0]}" y="52" width="{PANELS[1][1]}" height="{panel_h:.0f}" rx="14" fill="#fafbfd" stroke="#e3e8f0"/>',
        f'<rect x="{PANELS[2][0]}" y="52" width="{PANELS[2][1]}" height="{panel_h:.0f}" rx="14" fill="#fafbfd" stroke="#e3e8f0"/>',
        f'<text x="{COL1_X}" y="44" class="sl">源头事实（已发生）</text>',
        f'<text x="{COL2_X}" y="44" class="sl">传导机制与触发条件</text>',
        f'<text x="{COL3_X}" y="44" class="sl">未来节点与潜在影响</text>',
        f'<path class="ce" d="M {ARROW1[0]} {int(ROW1_Y + max(h1, h2) / 2)} L {ARROW1[1]} {int(ROW1_Y + max(h1, h2) / 2)}"/>',
        f'<path class="ce" d="M {ARROW2[0]} {int(ROW1_Y + max(h2, h3) / 2)} L {ARROW2[1]} {int(ROW1_Y + max(h2, h3) / 2)}"/>',
    ]
    # 源头事实（列1，行1，红框）
    parts.append(f'<g transform="translate({COL1_X},{ROW1_Y})"><rect class="fn fr" width="{COL1_W}" height="{h1:.0f}" rx="10"/>')
    for i, ln in enumerate(src_title):
        parts.append(f'<text x="{COL_PAD}" y="{36 + i * LINE_H:.0f}" class="nt">{_esc(ln)}</text>')
    y = 36 + len(src_title) * LINE_H + 14
    for ln in src_lines:
        parts.append(f'<text x="{COL_PAD}" y="{y:.0f}" class="ns">{_esc(ln)}</text>')
        y += LINE_H
    parts.append('</g>')
    # 传导机制（列2，行1）
    parts.append(f'<g transform="translate({COL2_X},{ROW1_Y})"><rect class="fn" width="{COL2_W}" height="{h2:.0f}" rx="10"/>')
    for i, ln in enumerate(mech_title):
        parts.append(f'<text x="{COL_PAD}" y="{36 + i * LINE_H:.0f}" class="nt">{_esc(ln)}</text>')
    y = 36 + len(mech_title) * LINE_H + 14
    for ln in mech_lines:
        parts.append(f'<text x="{COL_PAD}" y="{y:.0f}" class="ns">{_esc(ln)}</text>')
        y += LINE_H
    parts.append('</g>')
    # 持续恶化条件（列2，行2）
    parts.append(f'<g transform="translate({COL2_X},{ROW2_Y})"><rect class="fn" width="{COL2_W}" height="{trig_h:.0f}" rx="10"/>')
    parts.append(f'<text x="{COL_PAD}" y="36" class="nt">持续恶化条件</text>')
    y = 62
    for ln in trig_lines:
        parts.append(f'<text x="{COL_PAD}" y="{y:.0f}" class="ns">{_esc(ln)}</text>')
        y += LINE_H
    parts.append('</g>')
    # 证据不足待观察（观察框，列2，自 ROW2 下方）
    for i, (t, r) in enumerate(obs_blocks):
        oy = OBS1_Y + i * ROW_STEP
        if i == 0:
            parts.append(f'<text x="{COL2_X}" y="{LABEL_Y}" class="sl" font-size="{SL_FS}">证据不足待观察</text>')
        parts.append(f'<g transform="translate({COL2_X},{oy})"><rect class="fb" width="{COL2_W}" height="{obs_h:.0f}" rx="10"/>')
        for j, ln in enumerate(t):
            parts.append(f'<text x="{COL_PAD}" y="{36 + j * LINE_H:.0f}" class="nt" fill="#7a5d10" font-size="{SM_FS}">{_esc(ln)}</text>')
        yy = 36 + len(t) * LINE_H + 12
        for ln in r:
            parts.append(f'<text x="{COL_PAD}" y="{yy:.0f}" class="ns">{_esc(ln)}</text>')
            yy += LINE_H
        parts.append('</g>')
    # 潜在影响（列3，行1，红框）
    parts.append(f'<g transform="translate({COL3_X},{ROW1_Y})"><rect class="fn fr" width="{COL3_W}" height="{h3:.0f}" rx="10"/>')
    parts.append(f'<text x="{COL_PAD}" y="36" class="nt">潜在影响（条件性）</text>')
    y = 62
    for ln in imp_lines:
        parts.append(f'<text x="{COL_PAD}" y="{y:.0f}" class="ns">{_esc(ln)}</text>')
        y += LINE_H
    parts.append('</g>')
    # 关键未来节点（列3，行2 起）
    for i, b in enumerate(node_blocks):
        ny = ROW2_Y + i * ROW_STEP
        parts.append(f'<g transform="translate({COL3_X},{ny})"><rect class="fn" width="{COL3_W}" height="{node_h:.0f}" rx="10"/>')
        parts.append(f'<text x="{COL_PAD}" y="36" class="nt" font-size="{SM_FS}">关键未来节点</text>')
        y = 62
        for ln in b:
            parts.append(f'<text x="{COL_PAD}" y="{y:.0f}" class="ns">{_esc(ln)}</text>')
            y += LINE_H
        parts.append('</g>')
    # 底部说明（置于同宽背景条内，随面板自适应，不悬空）
    hedge_lines = _wrap(data.get("hedge", "黄色预警按证据缺失降级观察"), 58)
    hy = panel_bottom + 2
    parts.append(f'<rect x="{PANELS[0][0]}" y="{hy}" width="{PANELS[2][0] + PANELS[2][1] - PANELS[0][0]}" height="44" rx="12" fill="#f7f9fc" stroke="#e3e8f0"/>')
    for ln in hedge_lines:
        parts.append(f'<text x="46" y="{hy + 29:.0f}" class="ns" font-size="{SM_FS}">{_esc(ln)}</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def render_timeline_chart(data):
    """data: {as_of, windows[[label,days]], events[{title, days, cert(红/黄/蓝), note, up(bool)}]} -> static timeline SVG.
    V20: 字号按 630px 显示基准反推（窗口/图内标题≈14px、说明≈12px）；事件盒加高至 66、
    行距 84，时间轴长宽按内容自适应（溢出时自动均衡上下两侧，容量不足才报错）。"""
    if not isinstance(data, dict) or "as_of" not in data:
        raise InputError("timeline data needs as_of and events")
    events = data.get("events")
    if not isinstance(events, list) or not events:
        raise InputError("timeline events must be a nonempty list")
    for i, ev in enumerate(events):
        if not isinstance(ev, dict) or not str(ev.get("title", "")).strip():
            raise InputError(f"timeline event {i} needs title")
        if ev.get("cert") not in ("红", "黄", "蓝"):
            raise InputError(f"timeline event {i} cert must be 红/黄/蓝")
        if not isinstance(ev.get("days"), (int, float)) or ev["days"] < 0:
            raise InputError(f"timeline event {i} days must be a nonnegative number")
    windows = data.get("windows", [["+7天", 7], ["+30天", 30], ["+90天", 90]])
    W = 1200
    AXIS_Y = 320
    UP_TOP, DOWN_BOTTOM = 104, 560
    BOX_H = 66
    UP_STEP = DOWN_STEP = 84
    H = DOWN_BOTTOM + 64
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {W} {H}"',
        'preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:auto" role="img" aria-labelledby="tct tcd">',
        '<title id="tct">未来事件时间轴</title>',
        '<desc id="tcd">以报告日为原点向右展开7/30/90天窗口，红黄蓝分级标注未来事件节点与确定性。</desc>',
        '<defs><marker id="tl-ar" viewBox="0 0 10 10" refX="9" refY="5" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L10,5 L0,10 z" fill="#8a94a6"/></marker></defs>',
        f'<style>.ax{{stroke:#8a94a6;stroke-width:2.5;marker-end:url(#tl-ar)}}.tk{{stroke:#b8c0cc;stroke-width:1.4}}',
        f'.wl{{font:600 27px {FONT_STACK};fill:#3d4757}}.dl{{font:500 23px {FONT_STACK};fill:#5b6472}}',
        f'.nr{{fill:#fdeeee;stroke:#d64545;stroke-width:2}}.ny{{fill:#fdf8e9;stroke:#c9a13b;stroke-width:1.8}}',
        f'.nb{{fill:#eef4fd;stroke:#4a7fd4;stroke-width:1.6}}',
        f'.nt{{font:700 27px {FONT_STACK};fill:#1f2933}}.ns{{font:400 22px {FONT_STACK};fill:#5b6472}}</style>',
        f'<line class="ax" x1="60" y1="{AXIS_Y}" x2="1150" y2="{AXIS_Y}"/>',
        f'<line class="tk" x1="120" y1="{AXIS_Y-12}" x2="120" y2="{AXIS_Y+12}"/>',
        f'<text x="116" y="{AXIS_Y+30}" text-anchor="end" class="dl" transform="rotate(-60 116 {AXIS_Y+30})">T0 = {_esc(str(data["as_of"]))}</text>',
    ]
    max_days = max(float(ev["days"]) for ev in events) if events else 90
    max_days = max(max_days, float(windows[-1][1]))
    span = 1080.0
    for label, days in windows:
        x = 60 + span * min(float(days) / max_days, 1.0)
        parts.append(f'<line class="tk" x1="{x:.0f}" y1="{AXIS_Y-12}" x2="{x:.0f}" y2="{AXIS_Y+12}"/>')
        parts.append(f'<text x="{x-4:.0f}" y="{AXIS_Y+30}" text-anchor="end" class="wl" '
                     f'transform="rotate(-60 {x-4:.0f} {AXIS_Y+30})">{_esc(label)}</text>')
    cert_fill = {"红": "nr", "黄": "ny", "蓝": "nb"}
    meaning = {"红": "红色：高确定性、高影响", "黄": "黄色：合同或单方预期", "蓝": "蓝色：公司排期类正面节点"}
    up_y_start = AXIS_Y - 16 - BOX_H
    down_y_start = AXIS_Y + 16
    up_rows, down_rows = [], []
    for ev in events:
        (up_rows if ev.get("up", False) else down_rows).append(ev)
    max_up_rows = (up_y_start - UP_TOP) // UP_STEP + 1
    max_down_rows = (DOWN_BOTTOM - down_y_start) // UP_STEP + 1
    if len(up_rows) > max_up_rows or len(down_rows) > max_down_rows:
        # 上下均衡：上溢下空则上侧溢出项移至下方，下溢上空同理
        while len(up_rows) > max_up_rows and len(down_rows) < max_down_rows:
            down_rows.append(up_rows.pop())
        while len(down_rows) > max_down_rows and len(up_rows) < max_up_rows:
            up_rows.append(down_rows.pop(0))
    if len(up_rows) > max_up_rows or len(down_rows) > max_down_rows:
        raise InputError("timeline events overflow: too many events; split or reduce")
    for ev in events:
        x = 60 + span * min(float(ev["days"]) / max_days, 1.0)
        above = ev in up_rows
        if above:
            row = up_rows.index(ev)
            y = up_y_start - row * UP_STEP
            parts.append(f'<line class="tk" x1="{x:.0f}" y1="{AXIS_Y}" x2="{x:.0f}" y2="{y+BOX_H}"/>')
        else:
            row = down_rows.index(ev)
            y = down_y_start + row * UP_STEP
            parts.append(f'<line class="tk" x1="{x:.0f}" y1="{AXIS_Y}" x2="{x:.0f}" y2="{y}"/>')
        box_x = min(max(170, x - 160), 830)
        parts.append(f'<g transform="translate({box_x:.0f},{y})"><rect class="{cert_fill[ev["cert"]]}" width="320" height="{BOX_H}" rx="9"/>')
        parts.append(f'<text x="14" y="31" class="nt">{_esc(str(ev["title"])[:11])}</text>')
        parts.append(f'<text x="14" y="58" class="ns">{_esc(str(ev.get("note", ""))[:13])}</text></g>')
    # 底部说明 + 顶部横向图例（间距充足）
    parts.append(f'<text x="60" y="{H-16}" class="dl">剩余天数 = 节点日 − {_esc(str(data["as_of"]))}｜{_esc(str(data.get("footnote", "预计时间为粗粒度标注，以公司公告为准")))}</text>')
    items = [("红", meaning["红"]), ("黄", meaning["黄"]), ("蓝", meaning["蓝"])]
    lx = 60
    for cert, text in items:
        tw = _text_width(text, 22)
        parts.append(f'<rect x="{lx:.0f}" y="24" width="14" height="14" rx="2.5" class="{cert_fill[cert]}"/>')
        parts.append(f'<text x="{lx+22:.0f}" y="36" class="ns" font-size="23">{_esc(text)}</text>')
        lx += tw + 22 + 60
    parts.append('</svg>')
    return "\n".join(parts)


MODES = {"volume": render_volume_chart, "distribution": render_distribution_chart,
         "chain": render_chain_chart, "timeline": render_timeline_chart}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=sorted(MODES))
    parser.add_argument("--data", required=True, help="JSON file with chart data")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(Path(args.data).read_text(encoding="utf-8-sig"))
        svg = MODES[args.mode](payload)
        out = Path(args.out).resolve()
        if out.exists():
            raise InputError("output must not overwrite an existing file")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(svg, encoding="utf-8")
        print(f"CHART={out} ({len(svg)} chars)")
        return 0
    except (InputError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f"chart failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())