#!/usr/bin/env python3
"""Render a source-bound event-type word cloud from one selected mx news package.

No search, inferred event verification, semantic labeling, or report prose is used.
Frequency is the number of unique verified target-company events bearing a tag.
"""
from __future__ import annotations

import argparse
import base64
import collections
import hashlib
import html
import io
import json
import math
import os
import re
import struct
import sys
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

from prepare_inputs import (FORBIDDEN, InputError, context_projection, local_date,
                            moment, try_iso, validate_entity, validate_items,
                            validate_url)

DEFAULT_STYLE = Path(__file__).resolve().parents[1] / "assets" / "wordcloud-style.json"
PNG_NAME = "public_opinion_wordcloud.png"
SVG_NAME = "public_opinion_wordcloud.svg"
HTML_NAME = "public_opinion_wordcloud.html"
MANIFEST_NAME = "wordcloud_manifest.json"
FONT_ENV = "ENTERPRISE_WORDCLOUD_FONT"
SCOPE_NOTE = ("词频为本次已核验且具有监测期内原始资讯支持的目标企业独立事项数；"
              "同一事项同一类型只计一次，不代表全网舆情总量。一个事项可有多个标签，"
              "各标签词频不可相加作为事项总数。字号仅表示词频，颜色为装饰，不表示情感或严重程度。")


def require_object(value, keys, where):
    if not isinstance(value, dict) or set(value) - set(keys):
        raise InputError(f"{where}: expected an object containing only {', '.join(keys)}")


def nonempty(value, where):
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{where}: expected a nonempty string")
    return value.strip()


def prepare_labels(package, labels):
    """Validate provenance, merge stable event IDs, then count unique events per tag."""
    require_object(package, ("schema_version", "acquisition", "entity", "context", "news_queries", "items", "events"), "news package")
    if package.get("acquisition") != "mx-finance-search" or FORBIDDEN.intersection(package):
        raise InputError("news package: only the selected mx-finance-search original-material package is accepted")
    target, code = validate_entity(package.get("entity"))
    context = context_projection(package.get("context"))
    items = validate_items(package.get("items"), "wordcloud")
    by_id = {item["id"]: item for item in items}
    require_object(labels, ("events",), "labels")
    if not isinstance(labels.get("events"), list):
        raise InputError("labels.events: expected a list")
    merged = {}
    for index, raw in enumerate(labels["events"]):
        here = f"labels.events[{index}]"
        require_object(raw, ("event_id", "subject", "labels", "source_ids", "verified"), here)
        if raw.get("verified") is not True:
            raise InputError(f"{here}: upstream event verification (verified=true) is required")
        event_id = nonempty(raw.get("event_id"), f"{here}.event_id")
        if nonempty(raw.get("subject"), f"{here}.subject") != target:
            raise InputError(f"{here}.subject: must equal the confirmed target enterprise name")
        tags = raw.get("labels")
        if not isinstance(tags, list) or not tags:
            raise InputError(f"{here}.labels: expected nonempty brief event-type labels")
        normalized = []
        for tag in tags:
            tag = nonempty(tag, f"{here}.labels[]")
            if not 2 <= len(tag) <= 24 or re.search(r"[\s\n\r:：。！？!?，,;；<>]", tag) or not re.search(r"[A-Za-z\u3400-\u9fff]", tag):
                raise InputError(f"{here}.labels[]: use a brief event-type phrase of 2–24 characters, not a sentence, number, or URL")
            normalized.append(tag)
        refs = raw.get("source_ids")
        if not isinstance(refs, list) or not refs or any(not isinstance(s, str) or s not in by_id for s in refs):
            raise InputError(f"{here}.source_ids: require existing IDs from the final selected news pool")
        refs = list(dict.fromkeys(refs))
        eligible = []
        for source_id in refs:
            item = by_id[source_id]
            if try_iso(item["published_at"]) is None:
                raise InputError(f"{here}: publication date is unverified for {source_id}; do not assign it to a monitoring period")
            if moment(item["published_at"]) > moment(context["data_as_of"], date_end=True):
                raise InputError(f"{here}: source {source_id} was published after data_as_of")
            if not validate_url(item["url"], f"{here}.{source_id}.url"):
                raise InputError(f"{here}: source {source_id} needs its actual HTTP(S) original URL for figure provenance")
            date = local_date(item["published_at"], f"{here}.{source_id}.published_at")
            if item["material_kind"] == "article" and context["start_date"] <= date <= context["end_date"]:
                eligible.append(source_id)
        if not eligible:
            raise InputError(f"{here}: at least one original article disclosed within the monitoring period and by data_as_of is required; summaries or older disclosures alone cannot establish a period event")
        event = merged.setdefault(event_id, {"event_id": event_id, "subject": target, "labels": set(), "source_ids": set(), "period_source_ids": set()})
        event["labels"].update(normalized)
        event["source_ids"].update(refs)
        event["period_source_ids"].update(eligible)
    events = [{**event, "labels": sorted(event["labels"]), "source_ids": sorted(event["source_ids"]),
               "period_source_ids": sorted(event["period_source_ids"])} for _, event in sorted(merged.items())]
    indexed = collections.defaultdict(list)
    for event in events:
        for tag in event["labels"]:
            indexed[tag].append(event["event_id"])
    sources = {source_id: {"id": source_id, **{key: item[key] for key in ("title", "source", "published_at", "url", "citation", "material_kind")}}
               for source_id, item in sorted(by_id.items()) if any(source_id in e["source_ids"] for e in events)}
    labels_out = []
    by_event = {event["event_id"]: event for event in events}
    for tag, event_ids in sorted(indexed.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        source_ids = sorted({s for e in event_ids for s in by_event[e]["source_ids"]})
        labels_out.append({"label": tag, "frequency": len(event_ids), "event_ids": event_ids,
                           "source_ids": source_ids, "sources": [sources[s] for s in source_ids]})
    identity = {"name": target, "confirmed": True}
    if code:
        identity["org_code"] = code
    return {"schema_version": "1.0", "status": "ready" if events else "empty", "acquisition": "mx-finance-search",
            "entity": identity, "context": context, "scope_note": SCOPE_NOTE,
            "unique_event_count": len(events), "label_count": len(labels_out), "events": events,
            "labels": labels_out, "sources": list(sources.values()), "image": None, "interactive": None}


def load_style(path=DEFAULT_STYLE):
    style = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    keys = {"width", "height", "background", "palette", "min_font_size", "max_font_size", "padding", "margin", "seed", "growth_factor", "max_layout_attempts",
            "hover_scale", "hover_font_weight", "hover_brightness", "transition_ms"}
    if not isinstance(style, dict) or set(style) != keys:
        raise InputError("style: expected the documented style-only keys from assets/wordcloud-style.json")
    for key in keys - {"background", "palette", "growth_factor", "hover_scale", "hover_brightness"}:
        if isinstance(style[key], bool) or not isinstance(style[key], int) or (key != "seed" and style[key] < 1):
            raise InputError(f"style.{key}: expected a positive integer")
    if min(style["width"], style["height"]) <= style["margin"] * 2 or style["max_font_size"] < style["min_font_size"]:
        raise InputError("style: invalid canvas margins or font-size range")
    if not isinstance(style["growth_factor"], (int, float)) or not 1 < style["growth_factor"] <= 3:
        raise InputError("style.growth_factor: expected a value greater than 1 and at most 3")
    for key, low, high in (("hover_scale", 1, 2), ("hover_brightness", 0, 1)):
        if isinstance(style[key], bool) or not isinstance(style[key], (int, float)) or not low < style[key] <= high:
            raise InputError(f"style.{key}: expected a value greater than {low} and at most {high}")
    if not 500 <= style["hover_font_weight"] <= 900 or style["hover_font_weight"] % 100:
        raise InputError("style.hover_font_weight: use a bold weight from 500 to 900 in increments of 100")
    if not isinstance(style["palette"], list) or not style["palette"]:
        raise InputError("style.palette: expected a nonempty list of colors")
    try:
        for color in [style["background"], *style["palette"]]:
            ImageColor.getrgb(color)
    except (TypeError, ValueError) as exc:
        raise InputError("style: invalid image color") from exc
    return style


def build_svg(manifest, style):
    """One layout, with a script-free top paint layer for per-word emphasis.

    Transparent base rectangles remain stationary while the pointer/focus selects
    a word. A sibling CSS selector reveals its duplicate in the final layer, so
    expanded text is never painted underneath a later base word.
    """
    if not manifest["labels"]:
        return None
    esc = lambda value: html.escape(str(value), quote=True)
    num = lambda value: format(value, ".8g")
    width, height = manifest["image"]["width"], manifest["image"]["height"]
    layout = manifest["rendering"]["layout"]
    family = json.dumps(manifest["rendering"]["font_family"], ensure_ascii=False)
    family += ', "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif'
    css = [
        "svg.enterprise-wordcloud { display:block; width:100%; height:auto; overflow:visible; }",
        "svg.enterprise-wordcloud .wc-word { outline:none; cursor:default; }",
        "svg.enterprise-wordcloud .wc-hit { pointer-events:all; }",
        "svg.enterprise-wordcloud .wc-word text { font-weight:400; pointer-events:none; }",
        "svg.enterprise-wordcloud .wc-word:focus-visible .wc-hit { stroke:#53758c; stroke-width:2; stroke-dasharray:5 4; }",
        "svg.enterprise-wordcloud .wc-word:hover text, svg.enterprise-wordcloud .wc-word:focus-within text { opacity:0; }",
        "svg.enterprise-wordcloud .wc-hover-layer { pointer-events:none; }",
        f"svg.enterprise-wordcloud .wc-highlight {{ opacity:0; transition:opacity {style['transition_ms']}ms ease; }}",
        f"svg.enterprise-wordcloud .wc-hover-visual {{ transform:scale(1); transform-origin:0px 0px; transition:transform {style['transition_ms']}ms ease; }}",
        f"svg.enterprise-wordcloud .wc-highlight text {{ font-weight:{style['hover_font_weight']}; filter:brightness({style['hover_brightness']}); }}",
    ]
    words, highlights = [], []
    for index, word in enumerate(layout):
        left, top, right, bottom = word["bounds"]
        cx, cy = (left + right) / 2, (top + bottom) / 2
        x, y = word["baseline_xy"][0] - cx, word["baseline_xy"][1] - cy
        label, frequency = esc(word["label"]), word["frequency"]
        description = esc(f"{word['label']}，{frequency}项独立事项")
        text = (f'<text x="{num(x)}" y="{num(y)}" font-size="{word["font_size"]}" '
                f'fill="{esc(word["color"])}" textLength="{word["width"]}" '
                f'lengthAdjust="spacingAndGlyphs">{label}</text>')
        words.append(
            f'<g class="wc-word wc-word-{index}" transform="translate({num(cx)} {num(cy)})" '
            f'tabindex="0" role="img" aria-label="{description}" data-label="{label}" data-frequency="{frequency}">'
            f'<title>{description}</title>'
            f'<rect class="wc-hit" x="{num(-word["width"] / 2)}" y="{num(-word["height"] / 2)}" '
            f'width="{word["width"]}" height="{word["height"]}" fill="transparent"/>'
            f'<g class="wc-visual">{text}</g></g>')
        highlights.append(f'<g class="wc-highlight wc-hover-{index}" transform="translate({num(cx)} {num(cy)})">'
                          f'<g class="wc-hover-visual">{text}</g></g>')
        trigger = (f"svg.enterprise-wordcloud .wc-word-{index}:hover ~ .wc-hover-layer .wc-hover-{index}, "
                   f"svg.enterprise-wordcloud .wc-word-{index}:focus-within ~ .wc-hover-layer .wc-hover-{index}")
        css.extend([f"{trigger} {{ opacity:1; }}",
                    f"{trigger.replace(', ', ' .wc-hover-visual, ')} .wc-hover-visual {{ transform:scale({style['hover_scale']}); }}"])
    css.append("@media (prefers-reduced-motion: reduce) { svg.enterprise-wordcloud .wc-highlight, svg.enterprise-wordcloud .wc-hover-visual { transition:none; } }")
    title = esc(f"{manifest['entity']['name']}舆情词云")
    css_text = "\n".join(css)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="enterprise-wordcloud" '
            f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'font-family="{esc(family)}" role="group" aria-label="{title}">'
            f'<title>{title}</title><desc>{esc(manifest["scope_note"])}</desc>'
            f'<style>{css_text}</style>'
            f'<rect width="{width}" height="{height}" fill="{esc(style["background"])}" pointer-events="none"/>'
            + "".join(words) + '<g class="wc-hover-layer" aria-hidden="true" pointer-events="none">'
            + "".join(highlights) + '</g></svg>')


def build_html(manifest, svg):
    """Self-contained local preview; report integration reuses the same inline SVG."""
    if svg is None:
        return None
    esc = lambda value: html.escape(str(value), quote=True)
    entity = esc(manifest["entity"]["name"])
    context = manifest["context"]
    source_badges = []
    for index, source in enumerate(manifest["sources"], 1):
        # URLs were validated against the selected original material in prepare_labels.
        source_badges.append(
            '<details class="source-badge"><summary aria-label="查看来源' + str(index) + '">'
            '<span aria-hidden="true">↗</span> 来源' + str(index) + '</summary>'
            '<div class="source-popup"><a href="' + esc(source["url"]) + '" target="_blank" rel="noopener noreferrer">'
            + esc(source["title"]) + '</a><span>' + esc(source["source"]) + ' · '
            + esc(source["published_at"]) + '</span></div></details>')
    return ('''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>''' + entity + ''' · 舆情词云交互预览</title><style>
*{box-sizing:border-box}body{margin:0;background:#f5f7fa;color:#293b48;font-family:"Microsoft YaHei","PingFang SC",sans-serif;line-height:1.7}
main{max-width:1100px;margin:36px auto;background:#fff;padding:32px 40px;border-radius:12px}
h1{font-size:23px;margin:0 0 8px}p{margin:8px 0}.meta,.note{font-size:13px;color:#647787}
figure{margin:24px 0 14px}figcaption{font-weight:600}.chart{padding:14px 0}.hint{font-size:13px;color:#647787}
.sources{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}.source-badge{display:inline-block;position:relative;font-size:12px}
.source-badge summary{list-style:none;color:#476f93;border:1px solid #dbe4ec;border-radius:14px;padding:1px 9px;cursor:pointer}
.source-badge summary::-webkit-details-marker{display:none}.source-badge summary:focus-visible{outline:2px solid #53758c;outline-offset:2px}
.source-badge .source-popup{display:none;position:absolute;z-index:3;bottom:100%;left:0;width:min(320px,75vw);padding:12px;background:#fff;box-shadow:0 3px 18px #263b502a;border:1px solid #dbe4ec;border-radius:8px}
.source-badge[open] .source-popup,.source-badge:hover .source-popup,.source-badge:focus-within .source-popup{display:block}
.source-badge:hover::details-content,.source-badge:focus-within::details-content{content-visibility:visible}
.source-popup a{color:#366d9c;overflow-wrap:anywhere}.source-popup span{display:block;color:#647787;margin-top:5px}
@media(max-width:640px){main{margin:0;padding:22px 18px;border-radius:0}h1{font-size:20px}}
</style></head><body><main><h1>''' + entity + ''' · 舆情词云</h1>
<p class="meta">监测期：''' + esc(context["start_date"]) + ' 至 ' + esc(context["end_date"])
            + '；资讯截止：' + esc(context["data_as_of"]) + '''</p>
<figure><figcaption>舆情词云</figcaption><div class="chart">''' + svg + '''</div></figure>
<p class="hint">将鼠标移到词语上，或使用 Tab 键选择词语，可放大、加粗并突出显示。</p>
<p class="note">''' + esc(manifest["scope_note"]) + '''</p><div class="sources" aria-label="词云来源">'''
            + "".join(source_badges) + '</div></main></body></html>')


def font_cmaps(path):
    """Read SFNT/TTC Unicode cmaps with stdlib; no font download or extra library."""
    data = Path(path).read_bytes()
    u16 = lambda offset: struct.unpack_from(">H", data, offset)[0]
    u32 = lambda offset: struct.unpack_from(">I", data, offset)[0]
    base = u32(12) if data[:4] == b"ttcf" else 0  # Pillow's default collection face is 0.
    tables = u16(base + 4)
    cmap = None
    for i in range(tables):
        offset = base + 12 + 16 * i
        if data[offset:offset + 4] == b"cmap":
            cmap = u32(offset + 8)
            break
    if cmap is None:
        raise InputError("font has no usable Unicode cmap")
    cmaps = []
    for i in range(u16(cmap + 2)):
        entry = cmap + 4 + 8 * i
        platform, encoding = u16(entry), u16(entry + 2)
        if platform != 0 and (platform != 3 or encoding not in (1, 10)):
            continue
        offset = cmap + u32(entry + 4)
        fmt = u16(offset)
        if fmt in (4, 12, 13):
            cmaps.append((offset, fmt))
    def supports(cp):
        for offset, fmt in cmaps:
            if fmt in (12, 13):
                lo, hi = 0, u32(offset + 12) - 1
                while lo <= hi:
                    mid = (lo + hi) // 2
                    row = offset + 16 + mid * 12
                    first, last, glyph = u32(row), u32(row + 4), u32(row + 8)
                    if cp < first:
                        hi = mid - 1
                    elif cp > last:
                        lo = mid + 1
                    else:
                        return glyph + (cp - first if fmt == 12 else 0) != 0
            elif cp <= 0xFFFF:
                count = u16(offset + 6) // 2
                ends = offset + 14
                starts = ends + count * 2 + 2
                deltas = starts + count * 2
                ranges = deltas + count * 2
                for i in range(count):
                    end = u16(ends + i * 2)
                    if cp > end:
                        continue
                    start = u16(starts + i * 2)
                    if cp < start:
                        break
                    delta = u16(deltas + i * 2)
                    distance = u16(ranges + i * 2)
                    glyph = ((cp + delta) & 0xFFFF) if distance == 0 else u16(ranges + i * 2 + distance + (cp - start) * 2)
                    return glyph != 0
        return False
    return supports


def resolve_font(font_path, text):
    explicit = font_path or os.environ.get(FONT_ENV)
    candidates = [explicit] if explicit else [
        "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/NotoSansSC-VF.ttf", "C:/Windows/Fonts/simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "/usr/share/fonts/truetype/arphic/uming.ttc",
    ]
    missing = []
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            supports = font_cmaps(candidate)
            absent = sorted({char for char in text if not char.isspace() and not supports(ord(char))})
            if absent:
                missing = absent
                continue
            ImageFont.truetype(str(candidate), 24)
            return str(Path(candidate).resolve())
        except (OSError, ValueError, struct.error, InputError):
            continue
    detail = f" Missing glyphs: {''.join(missing[:12])}." if missing else ""
    raise InputError(f"No readable CJK font covers every label.{detail} Supply --font /path/to/CJK.ttf (or .ttc/.otf), or set {FONT_ENV}; install/provide a properly licensed local CJK font. No substitute glyph image was rendered.")


def overlaps(a, b, padding=0):
    return a[0] < b[2] + padding and a[2] + padding > b[0] and a[1] < b[3] + padding and a[3] + padding > b[1]


def render(manifest, style, font_path=None):
    """Return a new JSON-safe manifest and exact PNG bytes, or no PNG for no events."""
    result = json.loads(json.dumps(manifest, ensure_ascii=False))
    result["interactive"] = None
    if not result["labels"]:
        return result, None
    font_path = resolve_font(font_path, "".join(row["label"] for row in result["labels"]))
    frequencies = [row["frequency"] for row in result["labels"]]
    low, high = min(frequencies), max(frequencies)
    fonts, words = {}, []
    for row in result["labels"]:
        ratio = math.sqrt((row["frequency"] - low) / (high - low)) if high > low else 0.5
        size = round(style["min_font_size"] + ratio * (style["max_font_size"] - style["min_font_size"]))
        font = fonts.setdefault(size, ImageFont.truetype(font_path, size))
        bbox = font.getbbox(row["label"])
        width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        color_index = int.from_bytes(hashlib.sha256(f"{style['seed']}:{row['label']}".encode()).digest()[:8], "big") % len(style["palette"])
        words.append({"label": row["label"], "frequency": row["frequency"], "font_size": size,
                      "color": style["palette"][color_index], "text_bbox": list(bbox), "width": width, "height": height})
    words.sort(key=lambda row: (-row["frequency"], -row["width"] * row["height"], row["label"]))
    width, height = style["width"], style["height"]
    padded_area = sum((word["width"] + style["padding"]) * (word["height"] + style["padding"]) for word in words)
    factor = max(1.0, math.sqrt(padded_area / (width * height * 0.42)),
                 max(word["width"] + 2 * style["margin"] for word in words) / width,
                 max(word["height"] + 2 * style["margin"] for word in words) / height)
    width, height = math.ceil(width * factor), math.ceil(height * factor)
    placed = None
    for attempt in range(style["max_layout_attempts"]):
        positioned = []
        margin, padding = style["margin"], style["padding"]
        count = max(5000, math.ceil(width * height / 100))
        # Golden-angle spiral visits a deterministic, even set of horizontal positions.
        for word in words:
            found = None
            for i in range(count):
                angle = i * 2.399963229728653 + (style["seed"] % 360) * math.pi / 180
                radius = 0 if i == 0 else 0.5 * width * math.sqrt(i / count)
                x = round(width / 2 + radius * math.cos(angle) - word["width"] / 2)
                y = round(height / 2 + radius * (height / width) * math.sin(angle) - word["height"] / 2)
                rect = (x, y, x + word["width"], y + word["height"])
                if rect[0] < margin or rect[1] < margin or rect[2] > width - margin or rect[3] > height - margin:
                    continue
                if not any(overlaps(rect, other["bounds"], padding) for other in positioned):
                    found = {**word, "bounds": list(rect), "rotation": 0,
                             "draw_xy": [x - word["text_bbox"][0], y - word["text_bbox"][1]],
                             "baseline_xy": [x - word["text_bbox"][0], y - word["text_bbox"][1] + fonts[word["font_size"]].getmetrics()[0]]}
                    break
            if found is None:
                break
            positioned.append(found)
        if len(positioned) == len(words):
            placed = positioned
            break
        width, height = math.ceil(width * style["growth_factor"]), math.ceil(height * style["growth_factor"])
    if placed is None:
        raise InputError("Cannot place all event-type labels with the supplied style. Increase canvas dimensions or reduce style font sizes/padding; no labels were dropped and no figure was written.")
    image = Image.new("RGB", (width, height), style["background"])
    drawing = ImageDraw.Draw(image)
    for word in placed:
        drawing.text(tuple(word["draw_xy"]), word["label"], font=fonts[word["font_size"]], fill=word["color"])
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    png = buffer.getvalue()
    result["image"] = {"filename": PNG_NAME, "mime_type": "image/png", "width": width, "height": height,
                       "sha256": hashlib.sha256(png).hexdigest(), "byte_length": len(png),
                       "data_uri": "data:image/png;base64," + base64.b64encode(png).decode("ascii")}
    result["rendering"] = {"font_path": font_path, "font_face_index": 0,
                           "font_family": fonts[placed[0]["font_size"]].getname()[0], "seed": style["seed"],
                           "style": style, "layout": placed, "all_labels_placed": True}
    svg = build_svg(result, style)
    result["interactive"] = {"filename": SVG_NAME, "mime_type": "image/svg+xml", "svg": svg,
                             "sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
                             "html_filename": HTML_NAME, "embedding": "inline_svg", "uses_scripts": False,
                             "hover": {"scale": style["hover_scale"], "font_weight": style["hover_font_weight"],
                                       "brightness": style["hover_brightness"], "transition_ms": style["transition_ms"]}}
    return result, png


def write_outputs(manifest, png, out, input_paths=()):
    out = Path(out).resolve()
    if out.exists():
        raise InputError("--out must be a new directory; existing results and inputs are never overwritten")
    targets = [out / MANIFEST_NAME] + ([out / PNG_NAME, out / SVG_NAME, out / HTML_NAME] if png is not None else [])
    if any(target == Path(p).resolve() for target in targets for p in input_paths):
        raise InputError("output must not overwrite an input")
    out.mkdir(parents=True, exist_ok=False)
    if png is not None:
        with (out / PNG_NAME).open("xb") as stream:
            stream.write(png)
        with (out / SVG_NAME).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(manifest["interactive"]["svg"])
        with (out / HTML_NAME).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(build_html(manifest, manifest["interactive"]["svg"]))
    with (out / MANIFEST_NAME).open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return targets


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--news-package", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--out", required=True, help="new output directory")
    parser.add_argument("--font", help=f"local licensed CJK font; alternative environment variable: {FONT_ENV}")
    parser.add_argument("--style", default=str(DEFAULT_STYLE))
    args = parser.parse_args(argv)
    try:
        if Path(args.out).exists():
            raise InputError("--out must be a new directory")
        package = json.loads(Path(args.news_package).read_text(encoding="utf-8-sig"))
        labels = json.loads(Path(args.labels).read_text(encoding="utf-8-sig"))
        manifest = prepare_labels(package, labels)
        manifest, png = render(manifest, load_style(args.style), args.font)
        write_outputs(manifest, png, args.out, (args.news_package, args.labels, args.style))
        print(json.dumps({"status": manifest["status"], "unique_event_count": manifest["unique_event_count"],
                          "label_count": manifest["label_count"], "manifest": str(Path(args.out) / MANIFEST_NAME),
                          "image": str(Path(args.out) / PNG_NAME) if png else None,
                          "svg": str(Path(args.out) / SVG_NAME) if png else None,
                          "html": str(Path(args.out) / HTML_NAME) if png else None}, ensure_ascii=False))
        return 0
    except (InputError, OSError, ValueError, struct.error) as exc:
        print(f"wordcloud failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
