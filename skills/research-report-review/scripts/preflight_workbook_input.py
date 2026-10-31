#!/usr/bin/env python3
"""Collect workbook-input mechanical errors before the fail-fast final validator."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from mql_contract import validate_market_group, validate_refresh_contract

PERIOD_TOKEN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?:[-/]?(?:Q[1-4]|H[12]))?[AEF]?(?!\d)", re.I)
SHORT_FY_TOKEN = re.compile(r"(?<![A-Z0-9])FY\s*(\d{2})([AEF])?", re.I)
MQL_BLOCK_DEFINITION = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*Block\s*\(\s*#(\d+)", re.I)


def periods(headers: list[Any], kinds: list[Any]) -> list[str]:
    result: list[str] = []
    for header, kind in zip(headers, kinds):
        if kind != "ACTUAL":
            continue
        text = str(header).strip()
        match = PERIOD_TOKEN.search(text)
        short = SHORT_FY_TOKEN.search(text)
        if match:
            value = match.group(0).upper()
        elif short:
            value = f"{2000 + int(short.group(1))}{(short.group(2) or 'A').upper()}"
        else:
            value = text
        if value and value not in result:
            result.append(value)
    return result


def transpose(matrix: list[list[Any]]) -> list[list[Any]]:
    if not matrix or not all(isinstance(row, list) for row in matrix):
        return []
    widths = {len(row) for row in matrix}
    if len(widths) != 1:
        return []
    return [list(row) for row in zip(*matrix)]


def inside(inner: Any, outer: Any) -> bool:
    if not (isinstance(inner, list) and len(inner) == 4 and isinstance(outer, list) and len(outer) == 4):
        return False
    if not all(isinstance(value, (int, float)) for value in inner + outer):
        return False
    epsilon = 1e-9
    return (
        inner[0] + epsilon >= outer[0]
        and inner[1] + epsilon >= outer[1]
        and inner[2] <= outer[2] + epsilon
        and inner[3] <= outer[3] + epsilon
    )


def collect(payload: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []

    def add(path: str, code: str, message: str) -> None:
        errors.append({"path": path, "code": code, "message": message})

    guide = payload.get("guide") if isinstance(payload.get("guide"), dict) else {}
    snapshots = payload.get("snapshots") if isinstance(payload.get("snapshots"), list) else []
    excluded = payload.get("excluded_tables") if isinstance(payload.get("excluded_tables"), list) else []
    if guide.get("census_table_count") != len(snapshots) + len(excluded):
        add("guide.census_table_count", "CENSUS_COUNT", "must equal included plus excluded tables")

    for index, table in enumerate(snapshots):
        path = f"snapshots[{index}]"
        if not isinstance(table, dict):
            add(path, "TYPE", "must be an object")
            continue
        headers = table.get("headers") if isinstance(table.get("headers"), list) else []
        kinds = table.get("header_kinds") if isinstance(table.get("header_kinds"), list) else []
        rows = table.get("rows") if isinstance(table.get("rows"), list) else []
        if not headers:
            add(path + ".headers", "EMPTY_HEADERS", "must be non-empty")
        if len(kinds) != len(headers):
            add(path + ".header_kinds", "HEADER_KIND_COUNT", "must match headers")
        for row_index, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != len(headers):
                add(f"{path}.rows[{row_index}]", "NON_RECTANGULAR", "row width must match headers")
        expected_periods = periods(headers, kinds)
        if table.get("source_periods") != expected_periods:
            add(path + ".source_periods", "SOURCE_PERIODS", f"expected {expected_periods!r}")
        row_boxes = table.get("row_bboxes") if isinstance(table.get("row_bboxes"), list) else []
        if len(row_boxes) != len(rows):
            add(path + ".row_bboxes", "ROW_BBOX_COUNT", "must cover every row")
        else:
            for row_index, row_box in enumerate(row_boxes):
                if not inside(row_box, table.get("bbox")):
                    add(f"{path}.row_bboxes[{row_index}]", "ROW_BBOX_OUTSIDE", "must remain inside table bbox")

    chart_shapes: dict[str, str] = {}
    for chart in payload.get("chart_snapshots", []):
        if isinstance(chart, dict) and chart.get("chart_id"):
            coordinate = chart.get("coordinate") or {}
            chart_shapes[str(chart["chart_id"])] = "TIME_SERIES" if coordinate.get("time_series") is True else "CROSS_SECTION"
    for index, block in enumerate(payload.get("chart_data", [])):
        if not isinstance(block, dict):
            continue
        expected = chart_shapes.get(str(block.get("chart_id")))
        if expected and block.get("source_temporal_shape") != expected:
            add(f"chart_data[{index}].source_temporal_shape", "TEMPORAL_SHAPE", f"expected {expected}")

    comparable_groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    execution_log = payload.get("execution_log", []) if isinstance(payload.get("execution_log"), list) else []
    snapshot_by_id = {str(value.get("table_id")): value for value in snapshots if isinstance(value, dict) and value.get("table_id")}
    for index, item in enumerate(payload.get("workpapers", [])):
        path = f"workpapers[{index}]"
        if not isinstance(item, dict) or item.get("data_source") != "MQL" or item.get("execution_status") != "SUCCESS":
            continue
        raw = item.get("raw_result")
        orientation = item.get("mql_orientation", 1)
        if orientation not in (0, 1):
            add(path + ".mql_orientation", "ORIENTATION", "must be 0 or 1")
            continue
        oriented = raw if orientation == 0 else transpose(raw)
        if oriented != item.get("last_result"):
            add(path + ".last_result", "ORIENTED_RESULT", "must equal raw_result after applying effective orientation")
        if item.get("cached_table") != item.get("last_result"):
            add(path + ".cached_table", "CACHE_MISMATCH", "must equal last_result")
        script = str(item.get("mql_script") or "")
        block_numbers = [int(value) for value in MQL_BLOCK_DEFINITION.findall(script)]
        if not block_numbers:
            add(path + ".mql_script", "MQL_BLOCKS", "must define at least Block #1")
        elif block_numbers != list(range(1, len(block_numbers) + 1)):
            add(path + ".mql_script", "MQL_BLOCK_SEQUENCE", "Block definitions must start at #1 and increase continuously without duplicates")
        selector = item.get("block_selector")
        if isinstance(selector, str) and selector.startswith("#") and selector[1:].isdigit() and block_numbers:
            if int(selector[1:]) not in block_numbers:
                add(path + ".block_selector", "MQL_BLOCK_SELECTOR", "selected Block is not defined in mql_script")
        if item.get("financial_query_mode") == "FINANCIAL_TIME_SERIES":
            if "TimeSeriesBlock" not in script or "SetWindow" not in script:
                add(path + ".mql_script", "FINANCIAL_WINDOW", "financial time series requires TimeSeriesBlock + SetWindow")
            if block_numbers != [1] or item.get("block_selector") != "#1":
                add(path + ".block_selector", "FINANCIAL_INDEPENDENT_ANCHOR", "each financial statement must use its own single #1 Block and anchor")
            if item.get("indicator_time_shape") != "time_series":
                add(path + ".indicator_time_shape", "TIME_SHAPE", "expected time_series")
            if "{市场类型}" in script:
                add(path + ".mql_script", "FINANCIAL_MARKET", "financial reporting-period windows must not specify a trading market")
        if isinstance(oriented, list) and oriented:
            if item.get("expected_rows") != len(oriented):
                add(path + ".expected_rows", "EXPECTED_ROWS", f"expected {len(oriented)}")
            width = len(oriented[0]) if isinstance(oriented[0], list) else 0
            if item.get("expected_columns") != width:
                add(path + ".expected_columns", "EXPECTED_COLUMNS", f"expected {width}")
        for code, message in validate_refresh_contract(item, execution_log):
            add(path, code, message)
        if item.get("source_semantic_type") == "COMPARABLE_COMPANY_TABLE":
            comparable_groups.setdefault(str(item.get("source_id")), []).append((index, item))

    for source_id, indexed_items in comparable_groups.items():
        source = snapshot_by_id.get(source_id, {})
        source_entities = indexed_items[0][1].get("source_entities")
        if not isinstance(source_entities, list):
            source_entities = source.get("source_entities") if isinstance(source.get("source_entities"), list) else None
        for code, message in validate_market_group([item for _, item in indexed_items], source_entities):
            add(f"workpapers[source_id={source_id}]", code, message)
    return errors


def collect_with_final_validation(payload: dict[str, Any], final_validator=None) -> list[dict[str, str]]:
    """Run mechanical checks and the exact validator used by workbook construction."""
    errors = collect(payload)
    if errors:
        return errors
    if final_validator is None:
        from build_workbook import validate_payload as final_validator
    try:
        final_validator(payload)
    except (ValueError, KeyError, TypeError) as error:
        errors.append({"path": "$", "code": "FINAL_VALIDATOR", "message": str(error)})
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, help="Optional JSON error report")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text("utf-8"))
    errors = collect_with_final_validation(payload)
    result = {"status": "PASS" if not errors else "FAIL", "error_count": len(errors), "errors": errors}
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, "utf-8")
    print(rendered, end="")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
