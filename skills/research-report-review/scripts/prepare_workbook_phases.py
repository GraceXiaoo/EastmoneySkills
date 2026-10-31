#!/usr/bin/env python3
"""Normalize deterministic evidence fields before MQL planning or workbook merge."""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_manifest import record_operation  # noqa: E402

NUMERIC_TOKEN = re.compile(r"[-+]?\(?\d[\d,]*(?:\.\d+)?\)?%?")
PERIOD_TOKEN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?:[-/]?(?:Q[1-4]|H[12]))?[AEF]?(?!\d)", re.I)
SHORT_FY_TOKEN = re.compile(r"(?<![A-Z0-9])FY\s*(\d{2})([AEF])?", re.I)
FINANCIAL_NAME = re.compile(r"资产负债表|利润表|损益表|现金流量表|财务摘要|财务比率|每股指标", re.I)
# 主营构成/分部表：行轴为分部（合计 + 明细），需按「分类×分部×字段」单独验收，合计数据不得替代明细。
SEGMENT_TABLE_NAME = re.compile(r"主营构成|主营业务构成|业务构成|收入构成|分部|分行业|分地区|分产品|按产品|按地区|按行业", re.I)
TOTAL_SEGMENT_LABEL = re.compile(r"^\s*(?:合\s*计|总\s*计|小\s*计|总\s*额|合\s*并\s*数)\s*$")


class TableParser(HTMLParser):
    """Collect table rows as (text, rowspan, colspan) cells plus thead tracking."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[tuple[str, int, int]]] = []
        self.thead_marks: list[bool] = []
        self.in_thead = False
        self._row: list[tuple[str, int, int]] | None = None
        self._cell: list[str] | None = None
        self._span: tuple[int, int] = (1, 1)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag == "thead":
            self.in_thead = True
        elif tag in {"td", "th"} and self._row is not None:
            raw = dict(attrs)
            try:
                rowspan = int(raw.get("rowspan") or 1)
                colspan = int(raw.get("colspan") or 1)
            except (TypeError, ValueError):
                rowspan = colspan = 0
            if rowspan < 1 or colspan < 1:
                raise ValueError(
                    f'invalid span attribute rowspan={raw.get("rowspan")!r} colspan={raw.get("colspan")!r}: span must be a positive integer'
                )
            self._span = (rowspan, colspan)
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "thead":
            self.in_thead = False
        elif tag in {"td", "th"} and self._row is not None and self._cell is not None:
            text = " ".join("".join(self._cell).split())
            self._row.append((text, self._span[0], self._span[1]))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.thead_marks.append(self.in_thead)
                self.rows.append(self._row)
            self._row = None


def _grid_table(cells: list[list[tuple[str, int, int]]], thead_marks: list[bool]) -> tuple[list[str], list[list[str]], list[dict[str, Any]]]:
    """Place spanned cells on a strict rectangular grid; reject holes instead of shifting or padding."""
    occupied: dict[tuple[int, int], tuple[str, bool]] = {}
    width = 0
    for r, row in enumerate(cells):
        c = 0
        for text, rowspan, colspan in row:
            while (r, c) in occupied:
                c += 1
            for dr in range(rowspan):
                for dc in range(colspan):
                    occupied[(r + dr, c + dc)] = (text, dr > 0)
            width = max(width, c + colspan)
            c += colspan
    height = len(cells)
    for r in range(height):
        for c in range(width):
            if (r, c) not in occupied:
                raise ValueError(
                    f"table grid hole at row {r + 1} column {c + 1}: ambiguous or incomplete layout requires semantic review instead of shifting or padding"
                )
    if any(thead_marks):
        header_count = thead_marks.index(False) if False in thead_marks else height
    else:
        header_count = min(max((rowspan for _, rowspan, _ in cells[0]), default=1), height)
    headers: list[str] = []
    hierarchy: list[dict[str, Any]] = []
    for c in range(width):
        parts: list[str] = []
        for r in range(header_count):
            text, vertical = occupied[(r, c)]
            if text and not vertical and text not in parts:
                parts.append(text)
        headers.append(" / ".join(parts))
        if len(parts) >= 2:
            hierarchy.append({"parent": parts[0], "child": " / ".join(parts[1:])})
        elif len(parts) == 1:
            hierarchy.append({"parent": None, "child": parts[0]})
        else:
            hierarchy.append({"parent": None, "child": None})
    seen: dict[str, int] = {}
    for i, label in enumerate(headers):
        count = seen.get(label, 0) + 1
        seen[label] = count
        headers[i] = label if count == 1 else f"{label} ({count})"
    rows = [[occupied[(r, c)][0] for c in range(width)] for r in range(header_count, height)]
    return headers, rows, hierarchy


def find_text_blocks(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        blocks = value.get("textBlocks")
        if isinstance(blocks, list):
            return [item for item in blocks if isinstance(item, dict)]
        blocks_by_page = value.get("blocksByPage")
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
        for child in value.values():
            found = find_text_blocks(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_text_blocks(child)
            if found:
                return found
    return []


def markdown_table(content: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in content.splitlines():
        if line.count("|") < 2:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and not all(re.fullmatch(r":?-+:?", cell.replace(" ", "")) for cell in cells):
            rows.append(cells)
    return rows


def block_table_detail(block: dict[str, Any]) -> tuple[list[str], list[list[str]], list[dict[str, Any]]]:
    """同 block_table，但额外返回每列的父子表头配对（用于嵌套子表单独验收）。"""
    content = str(block.get("content") or "")
    html = str(block.get("tableContent") or "")
    if not html and "<table" in content.lower():
        html = content
    if html:
        parser = TableParser()
        parser.feed(html)
        if parser.rows:
            return _grid_table(parser.rows, parser.thead_marks)
    rows = markdown_table(content)
    if not rows:
        return [], [], []
    width = max(map(len, rows))
    rows = [(row + [""] * width)[:width] for row in rows]
    return rows[0], rows[1:], [{"parent": None, "child": header} for header in rows[0]]


def block_table(block: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    headers, rows, _ = block_table_detail(block)
    return headers, rows


def from_layout(args: argparse.Namespace) -> None:
    payload = json.loads(args.layout_json.read_text(encoding="utf-8"))
    blocks = find_text_blocks(payload)
    if not blocks:
        raise ValueError("layout JSON does not contain textBlocks")
    pages = sorted({int(block["page"]) for block in blocks if block.get("page") is not None})
    page_bounds: dict[int, tuple[float, float]] = {}
    for page in pages:
        current = [block for block in blocks if int(block.get("page", 0)) == page]
        page_bounds[page] = (
            max(float(block.get("maxX", 1) or 1) for block in current),
            max(float(block.get("maxY", 1) or 1) for block in current),
        )
    table_order: dict[int, int] = {}
    chart_order: dict[int, int] = {}
    snapshots: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []
    chart_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    visual_keys: dict[int, list[int]] = {}
    title_blocks: list[dict[str, Any]] = []
    for block in sorted(blocks, key=lambda item: (int(item.get("page", 0)), int(item.get("index", 0)))):
        page = int(block.get("page", 0))
        kind = block.get("classType")
        content = str(block.get("content") or "")
        coords = [block.get(name) for name in ("minX", "minY", "maxX", "maxY")]
        if not all(isinstance(value, (int, float)) for value in coords):
            continue
        block_index = int(block.get("index") or 0)
        width, height = page_bounds[page]
        bbox = [float(coords[0]) / width, float(coords[1]) / height, float(coords[2]) / width, float(coords[3]) / height]
        first_line = next((line.strip(" |") for line in content.splitlines() if line.strip(" |")), "")
        if kind == "table":
            table_order[page] = table_order.get(page, 0) + 1
            table_id = f"p{page}-t{table_order[page]}"
            headers, rows, hierarchy = block_table_detail(block)
            if not headers or not rows:
                raise ValueError(
                    f"{table_id}: table block has no parseable table content (tableContent/HTML/markdown); LAYOUT_SCHEMA_BLOCKED"
                )
            title = first_line or table_id
            chart_order[page] = chart_order.get(page, 0) + 1
            chart_id = f"p{page}-c{chart_order[page]}"
            charts.append({
                "chart_id": chart_id, "page": page, "api_block_index": block.get("index"),
                "api_class_type": kind, "bbox_pt": {"minX": coords[0], "minY": coords[1], "maxX": coords[2], "maxY": coords[3]},
                "title": title[:100], "visual_check": "PENDING_REVIEW",
                "parsed_table_ids": [table_id], "stable_object_key": f"p{page}-t{block_index}",
            })
            chart_by_key[(page, block_index)] = charts[-1]
            visual_keys.setdefault(page, []).append(block_index)
            snapshots.append({
                "table_id": table_id, "page": page, "table_name": title[:100], "bbox": bbox,
                "layout_group": f"p{page}", "lane": "UNREVIEWED", "reading_order": table_order[page],
                "headers": headers, "rows": rows, "parse_origin": "LAYOUT_TABLE_BLOCK",
                "header_hierarchy": hierarchy,
                "header_parse_origin": "NESTED_HEADER" if any(value.get("parent") for value in hierarchy) else "FLAT",
                "source_semantic_type": "OTHER", "source_status": "TODO", "visual_check": "PENDING_REVIEW",
                "is_visual_object": False, "paired_chart_id": chart_id,
            })
        elif kind == "image":
            chart_order[page] = chart_order.get(page, 0) + 1
            chart_id = f"p{page}-c{chart_order[page]}"
            charts.append({
                "chart_id": chart_id, "page": page, "api_block_index": block.get("index"),
                "api_class_type": kind, "bbox_pt": {"minX": coords[0], "minY": coords[1], "maxX": coords[2], "maxY": coords[3]},
                "title": first_line[:100] if first_line else "待识别图表",
                "visual_check": "PENDING_REVIEW", "parsed_table_ids": [],
                "stable_object_key": f"p{page}-i{block_index}",
            })
            chart_by_key[(page, block_index)] = charts[-1]
            visual_keys.setdefault(page, []).append(block_index)
        elif re.search(r"图表?\s*\d+[：:]", content):
            title_blocks.append({"page": page, "index": block_index, "title": first_line})
    for candidate in title_blocks:
        page_indices = visual_keys.get(candidate["page"], [])
        following = [index for index in page_indices if index > candidate["index"]]
        preceding = [index for index in page_indices if index < candidate["index"]]
        target = following[0] if following else (preceding[-1] if preceding else None)
        if target is not None:
            chart_by_key[(candidate["page"], target)]["title"] = candidate["title"][:100]
    guide = {
        "company_name": args.company_name, "security_code": args.security_code,
        "report_title": args.report_title, "report_date": args.report_date,
        "verification_date": args.verification_date, "pdf_page_count": max(pages),
        "census_table_count": len(snapshots), "visual_object_count": len(charts),
    }
    args.census_output.write_text(json.dumps({"schema_version": 1, "guide": guide, "excluded_tables": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.evidence_output.write_text(json.dumps({"schema_version": 1, "snapshots": snapshots, "chart_snapshots": charts, "chart_data": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created draft census/evidence: {len(snapshots)} tables, {len(charts)} chart candidates")


def unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def header_kind(value: Any) -> str:
    text = str(value).strip().upper()
    if re.search(r"(?:19|20)\d{2}A\b|\bFY\s*\d{2}\s*(?:A|实际)\b", text):
        return "ACTUAL"
    if re.search(r"(?:19|20)\d{2}[EF]\b|\bFY\s*\d{2}\s*(?:E|F|预测)\b", text):
        return "FORECAST"
    if re.search(r"(?:19|20)\d{2}.*实际|\bFY\s*\d{2}.*实际", text):
        return "ACTUAL"
    return "OTHER"


def periods(headers: list[Any], kinds: list[str]) -> list[str]:
    result: list[str] = []
    for header, kind in zip(headers, kinds):
        if kind != "ACTUAL":
            continue
        text = str(header).strip()
        match = PERIOD_TOKEN.search(text)
        short = SHORT_FY_TOKEN.search(text)
        if match:
            period = match.group(0).upper()
        elif short:
            year = 2000 + int(short.group(1))
            suffix = (short.group(2) or "A").upper()
            period = f"{year}{suffix}"
        else:
            period = text
        if period and period not in result:
            result.append(period)
    return result


def row_bboxes(bbox: list[float], count: int) -> list[list[float]]:
    x0, y0, x1, y1 = bbox
    height = (y1 - y0) / max(count, 1)
    result = []
    for i in range(count):
        top = y0 + i * height
        bottom = y1 if i == count - 1 else y0 + (i + 1) * height
        result.append([round(x0, 12), round(top, 12), round(x1, 12), round(bottom, 12)])
    return result


def normalize_table(source: dict[str, Any]) -> dict[str, Any]:
    table = dict(source)
    headers = [str(value) for value in table.get("headers", [])]
    if not headers:
        raise ValueError(f'{table.get("table_id", "unknown")}: headers are required')
    width = len(headers)
    rows: list[list[Any]] = []
    for source_row in table.get("rows", []):
        row = list(source_row) if isinstance(source_row, list) else [source_row]
        row = (row + [""] * width)[:width]
        if any(value not in (None, "") for value in row):
            rows.append(row)
    if not rows:
        raise ValueError(f'{table.get("table_id", "unknown")}: rows are required')
    kinds = table.get("header_kinds")
    if not isinstance(kinds, list) or len(kinds) != width:
        kinds = [header_kind(value) for value in headers]
    name = str(table.get("table_name", ""))
    latest_filing = bool(re.search(r"(?:^|[（(\s])LF(?:$|[）)\s])|最新财报|最近财报", name, re.I))
    if latest_filing:
        for index, header in enumerate(headers):
            if re.fullmatch(r"LF|最新财报|最近财报", str(header).strip(), re.I):
                kinds[index] = "ACTUAL"
    bbox = table.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError(f'{table.get("table_id", "unknown")}: normalized bbox is required')
    bbox = [float(value) for value in bbox]
    tokens = [[token for cell in row[1:] for token in NUMERIC_TOKEN.findall(str(cell))] for row in rows]

    table.update(
        headers=headers,
        rows=rows,
        header_kinds=kinds,
        source_row_labels=["" if row[0] is None else str(row[0]) for row in rows],
        source_numeric_tokens_by_row=tokens,
        row_numeric_token_counts=[len(value) for value in tokens],
        source_row_count=len(rows),
        source_numeric_token_count=sum(map(len, tokens)),
        extracted_numeric_token_count=sum(map(len, tokens)),
        bbox=bbox,
        source_periods=periods(headers, kinds),
    )
    if not isinstance(table.get("row_bboxes"), list) or len(table["row_bboxes"]) != len(rows):
        table["row_bboxes"] = row_bboxes(bbox, len(rows))
    table["row_bold"] = (list(table.get("row_bold", [])) + [False] * len(rows))[:len(rows)]

    financial = bool(FINANCIAL_NAME.search(name)) or table.get("source_semantic_type") in {"FINANCIAL_STATEMENT", "FINANCIAL_METRICS"}
    if financial:
        if table.get("source_semantic_type") not in {"FINANCIAL_STATEMENT", "FINANCIAL_METRICS"}:
            table["source_semantic_type"] = "FINANCIAL_METRICS"
        table["source_row_axis"] = "FINANCIAL_METRIC"
        table["source_column_axis"] = "REPORTING_PERIOD"
    else:
        if table.get("source_row_axis") not in {"ENTITY", "CATEGORY", "DATE", "SERIES", "METRIC"}:
            table["source_row_axis"] = "CATEGORY"
        if table.get("source_column_axis") not in {"ENTITY", "CATEGORY", "DATE", "SERIES", "METRIC"} or table.get("source_column_axis") == table["source_row_axis"]:
            table["source_column_axis"] = "METRIC"
    if not financial and SEGMENT_TABLE_NAME.search(name):
        roles = [
            {"segment": label, "role": "TOTAL" if TOTAL_SEGMENT_LABEL.match(label) else "DETAIL"}
            for label in unique(table["source_row_labels"])
        ]
        if any(item["role"] == "TOTAL" for item in roles) and any(item["role"] == "DETAIL" for item in roles):
            table["source_segments"] = roles
            table["segment_role_basis"] = "来源表名命中主营构成/分部关键词；行标签「合计/总计/小计/总额/合并数」判为 TOTAL，其余判为 DETAIL"
    candidates = table.get("queryable_fields")
    if not isinstance(candidates, list) or not candidates:
        candidates = table["source_row_labels"] if financial else headers[1:]
    table["queryable_fields"] = unique(candidates)
    table.setdefault("layout_contract_reason", "由来源表头、行标签与期间结构确定")
    table["source_period_basis"] = "LATEST_FILING" if latest_filing else table.get("source_period_basis", "REPORTED_PERIOD")
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("normalize-evidence")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--manifest", type=Path, default=None)
    command.add_argument("--object-id", default=None)
    layout = commands.add_parser("from-layout")
    layout.add_argument("--layout-json", type=Path, required=True)
    layout.add_argument("--census-output", type=Path, required=True)
    layout.add_argument("--evidence-output", type=Path, required=True)
    layout.add_argument("--company-name", default="待确认")
    layout.add_argument("--security-code", default="待确认")
    layout.add_argument("--report-title", default="待确认")
    layout.add_argument("--report-date", default="待确认")
    layout.add_argument("--verification-date", default="待确认")
    layout.add_argument("--manifest", type=Path, default=None)
    layout.add_argument("--object-id", default=None)
    args = parser.parse_args()
    if args.command == "from-layout":
        args.census_output.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_output.parent.mkdir(parents=True, exist_ok=True)
        from_layout(args)
        if args.manifest is not None:
            oid = args.object_id or args.census_output.parent.name
            record_operation(args.manifest, "1", oid, "census", inputs=[args.layout_json], result_path=args.census_output)
            record_operation(args.manifest, "2", oid, "evidence_skeleton", inputs=[args.layout_json], result_path=args.evidence_output)
        return
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list):
        raise ValueError("evidence.snapshots must be an array")
    payload["snapshots"] = [normalize_table(table) for table in snapshots]
    page_orders: dict[int, int] = {}
    for table in payload["snapshots"]:
        page = int(table.get("page", 0))
        page_orders[page] = page_orders.get(page, 0) + 1
        table["reading_order"] = page_orders[page]
    payload.setdefault("chart_snapshots", [])
    payload.setdefault("chart_data", [])
    chart_shapes: dict[str, str] = {}
    for chart in payload["chart_snapshots"]:
        if not isinstance(chart, dict) or not chart.get("chart_id"):
            continue
        coordinate = chart.get("coordinate") or {}
        chart_shapes[str(chart["chart_id"])] = "TIME_SERIES" if coordinate.get("time_series") is True else "CROSS_SECTION"
    for block in payload["chart_data"]:
        if isinstance(block, dict) and block.get("chart_id") in chart_shapes:
            block["source_temporal_shape"] = chart_shapes[str(block["chart_id"])]
    payload["schema_version"] = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    if args.manifest is not None:
        oid = args.object_id or args.output.parent.name
        record_operation(args.manifest, "2", oid, "evidence", inputs=[args.input], result_path=args.output)
    print(f"Normalized {len(snapshots)} snapshots: {args.output}")


if __name__ == "__main__":
    main()
