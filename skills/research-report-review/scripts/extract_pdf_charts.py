#!/usr/bin/env python3
"""Render and crop PDF chart blocks returned by layoutV2."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader


TITLE_RE = re.compile(r"(图表?\s*\d+)\s*[：:]\s*([^\n;|]{2,80})")
SOURCE_RE = re.compile(r"((?:资料|数据)来源[：:].*?)(?:\n|$)")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--layout-json", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--top-pad", type=float, default=6.0)
    parser.add_argument("--bottom-pad", type=float, default=6.0)
    parser.add_argument("--side-pad", type=float, default=6.0)
    parser.add_argument("--include-tables", action="store_true", help="Also crop every layout table block")
    parser.add_argument("--neighbor-gap", type=float, default=2.0, help="Minimum gap from adjacent blocks in PDF points")
    return parser.parse_args()


def load_blocks(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    blocks = (payload.get("data") or {}).get("textBlocks")
    if isinstance(blocks, list):
        return blocks
    blocks = payload.get("textBlocks")
    if isinstance(blocks, list):
        return blocks
    blocks_by_page = (payload.get("layoutAnalysis") or {}).get("blocksByPage")
    if isinstance(blocks_by_page, dict):
        flattened: list[dict[str, Any]] = []
        for page_key, page_blocks in blocks_by_page.items():
            if not isinstance(page_blocks, list):
                continue
            for item in page_blocks:
                if isinstance(item, dict):
                    block = dict(item)
                    block.setdefault("page", int(page_key))
                    flattened.append(block)
        if flattened:
            return flattened
    images = payload.get("imageBlocks")
    if isinstance(images, list):
        return images
    raise ValueError("layout JSON must contain data.textBlocks, textBlocks, layoutAnalysis.blocksByPage, or imageBlocks")


def chart_blocks(blocks: list[dict[str, Any]], include_tables: bool = False) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for block in blocks:
        content = str(block.get("content") or "")
        is_chart = block.get("classType") == "image" or bool(TITLE_RE.search(content)) or (include_tables and block.get("classType") == "table")
        coords = [block.get(name) for name in ("minX", "maxX", "minY", "maxY")]
        if not is_chart or not all(isinstance(value, (int, float)) for value in coords):
            continue
        key = (block.get("page"), block.get("index"))
        if key not in seen:
            seen.add(key)
            selected.append(block)
    return selected


def vertical_limits(block: dict[str, Any], blocks: list[dict[str, Any]], gap: float) -> tuple[float | None, float | None]:
    """Return nearest lower/upper block boundaries that overlap horizontally."""
    page = block.get("page")
    min_x, max_x = float(block["minX"]), float(block["maxX"])
    min_y, max_y = float(block["minY"]), float(block["maxY"])
    lower: list[float] = []
    upper: list[float] = []
    for other in blocks:
        if other is block or other.get("page") != page:
            continue
        coords = [other.get(name) for name in ("minX", "maxX", "minY", "maxY")]
        if not all(isinstance(value, (int, float)) for value in coords):
            continue
        omin_x, omax_x, omin_y, omax_y = map(float, coords)
        overlap = min(max_x, omax_x) - max(min_x, omin_x)
        if overlap <= 0:
            continue
        if omax_y <= min_y:
            lower.append(omax_y + gap)
        elif omin_y >= max_y:
            upper.append(omin_y - gap)
    return (max(lower) if lower else None, min(upper) if upper else None)


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|;\r\n]+", "_", value).strip(" ._")
    return cleaned[:80] or "untitled"


def is_figure_block(block: dict[str, Any]) -> bool:
    """判断块是否为「图」（视觉图对象）。

    `classType=image` 一律为图；`classType=table` 仅当内容**开头**即图题（`图N：`/`图表N：`）
    时视为图版式图表。正文表格即使内部引用「图1」也只是数据表裁图，不占图号。
    """
    if block.get("classType") == "image":
        return True
    return bool(TITLE_RE.match(str(block.get("content") or "").strip()))


def chart_page_orders(blocks: list[dict[str, Any]]) -> list[int | None]:
    """按页内图序编号（每页从 1 重新计数），非图块返回 None。

    编号口径与 `prepare_workbook_phases.py` 一致；表格裁图不占用图号（见 ingestion_rules）。
    """
    counter: dict[int, int] = {}
    orders: list[int | None] = []
    for block in blocks:
        page = int(block["page"])
        if not is_figure_block(block):
            orders.append(None)
            continue
        counter[page] = counter.get(page, 0) + 1
        orders.append(counter[page])
    return orders


def parse_text(content: str, fallback: str) -> tuple[str, str, str, list[str]]:
    title_match = TITLE_RE.search(content)
    chart_no = title_match.group(1).replace(" ", "") if title_match else fallback
    title = title_match.group(2).strip() if title_match else "未识别标题"
    source_match = SOURCE_RE.search(content)
    source = source_match.group(1).strip() if source_match else ""
    serial: list[str] = []
    for line in content.splitlines():
        if line.count("|") < 2 or re.fullmatch(r"\s*\|?\s*:?-+.*", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] and cells[0] not in serial:
            serial.append(cells[0])
    return chart_no, title, source, serial[1:] if len(serial) > 1 else serial


def render_page(pdf: Path, page: int, dpi: int, cache: Path) -> Path:
    target = cache / f"page-{page}.png"
    if target.exists():
        return target
    executable = shutil.which("pdftoppm")
    if not executable:
        raise RuntimeError("pdftoppm is required to render PDF pages")
    prefix = cache / f"page-{page}"
    subprocess.run(
        [executable, "-png", "-r", str(dpi), "-f", str(page), "-l", str(page),
         "-singlefile", str(pdf), str(prefix)],
        check=True,
        capture_output=True,
        text=True,
    )
    if not target.exists():
        raise RuntimeError(f"page renderer did not create {target}")
    return target


def main() -> None:
    args = arguments()
    if args.dpi <= 0:
        raise ValueError("dpi must be positive")
    pdf = args.pdf.resolve()
    layout = args.layout_json.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = out_dir / ".pages"
    cache.mkdir(exist_ok=True)

    reader = PdfReader(str(pdf))
    all_blocks = load_blocks(layout)
    blocks = chart_blocks(all_blocks, args.include_tables)
    metadata: dict[str, Any] = {
        "source_pdf": pdf.name,
        "source_pdf_path": str(pdf),
        "layout_json": str(layout),
        "dpi": args.dpi,
        "chart_count": len(blocks),
        "charts": [],
    }

    for figure_order, block in zip(chart_page_orders(blocks), blocks):
        page_number = int(block["page"])
        if not 1 <= page_number <= len(reader.pages):
            raise ValueError(f"invalid chart page: {page_number}")
        pdf_page = reader.pages[page_number - 1]
        page_width = float(pdf_page.mediabox.width)
        page_height = float(pdf_page.mediabox.height)
        min_x, max_x = float(block["minX"]), float(block["maxX"])
        min_y, max_y = float(block["minY"]), float(block["maxY"])
        lower_limit, upper_limit = vertical_limits(block, all_blocks, args.neighbor_gap)
        expanded_min_y = max(0.0, min_y - args.bottom_pad)
        expanded_max_y = min(page_height, max_y + args.top_pad)
        if lower_limit is not None:
            expanded_min_y = max(expanded_min_y, lower_limit)
        if upper_limit is not None:
            expanded_max_y = min(expanded_max_y, upper_limit)
        left = max(0.0, min_x - args.side_pad)
        right = min(page_width, max_x + args.side_pad)
        top = page_height - expanded_max_y
        bottom = page_height - expanded_min_y
        if not (left < right and top < bottom):
            raise ValueError(f"invalid crop for page {page_number}, index {block.get('index')}")

        content = str(block.get("content") or "")
        block_index = int(block.get("index", 0))
        chart_no, title, source, serial = parse_text(content, "")
        if figure_order is None:
            # 非图块（数据表裁图）：不占图号，也不从正文引用中臆取图号
            chart_no, source, serial = "", "", []
            if block.get("classType") == "table":
                first_line = next((line.strip(" |") for line in content.splitlines() if line.strip(" |")), "")
                title = first_line[:80] or f"表格{block_index}"
            else:
                title = "未识别标题"
        elif block.get("classType") == "table" and title == "未识别标题":
            first_line = next((line.strip(" |") for line in content.splitlines() if line.strip(" |")), "")
            title = first_line[:80] or f"表格{block_index}"
        filename = f"p{page_number}-i{block_index}.png"
        page_png = render_page(pdf, page_number, args.dpi, cache)
        with Image.open(page_png) as image:
            scale_x = image.width / page_width
            scale_y = image.height / page_height
            crop = image.crop((round(left * scale_x), round(top * scale_y),
                               round(right * scale_x), round(bottom * scale_y)))
            crop.save(out_dir / filename)

        title_present = bool(TITLE_RE.search(content))
        source_present = bool(SOURCE_RE.search(content))
        metadata["charts"].append({
            "chart_id": f"p{page_number}-c{figure_order}" if figure_order is not None else "",
            "stable_object_key": f"p{page_number}-i{block_index}",
            "chart_no": chart_no,
            "title": title,
            "source": source,
            "page": page_number,
            "bbox_pt": {"minX": min_x, "maxX": max_x, "minY": min_y, "maxY": max_y},
            "crop_pt": {"top": top, "bottom": bottom, "left": left, "right": right},
            "snapshot_path": str((out_dir / filename).resolve()),
            "api_block_index": block.get("index"),
            "api_class_type": block.get("classType"),
            "serial": serial,
            "coordinate": {"x": "", "y": "", "time_series": None, "data_labels": None},
            "frequency": "待视觉复核",
            "structure_title_present": title_present,
            "structure_source_present": source_present,
            "header_footer_ok": False,
            "visual_check": "PENDING_REVIEW",
            "review_note": "查看截图后确认标题、footer、坐标轴、图例和图形主体完整性",
        })

    output = out_dir / "chart_metadata.json"
    output.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Created {len(blocks)} chart snapshots and {output}")


if __name__ == "__main__":
    main()
