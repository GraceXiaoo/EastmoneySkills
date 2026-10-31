"""Validate audited research-report tables and build a refreshable Excel workbook."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage

from mql_contract import selected_block_name, validate_market_group, validate_refresh_contract


HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
SECTION_FILL = PatternFill("solid", fgColor="D9EAF7")
SPILL_FILL = PatternFill("solid", fgColor="F2F2F2")
DYNAMIC_FILL = PatternFill("solid", fgColor="EAF2F8")
YELLOW_FILL = PatternFill("solid", fgColor="FFF2CC")
WHITE_FONT = Font(color="FFFFFF", bold=True)
BOLD_FONT = Font(bold=True)
WRAP = Alignment(vertical="top", wrap_text=True)
NOWRAP = Alignment(vertical="top", wrap_text=False)
LEFT = Alignment(horizontal="left", vertical="top", wrap_text=False)
RIGHT = Alignment(horizontal="right", vertical="top", wrap_text=True)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
ALLOWED_EXCLUSIONS = {
    "DISCLAIMER",
    "ANALYST_OR_INSTITUTION_DISCLOSURE",
    "RATING_DEFINITION",
    "CONTACT_INFORMATION",
}
ALLOWED_HEADER_KINDS = {"ACTUAL", "FORECAST", "OTHER"}
NUMERIC_TOKEN = re.compile(r"[-+]?\(?\d[\d,]*(?:\.\d+)?\)?%?")
PERIOD_TOKEN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?:[-/]?(?:Q[1-4]|H[12]))?[AEF]?(?!\d)", re.IGNORECASE)
SHORT_FY_TOKEN = re.compile(r"(?<![A-Z0-9])FY\s*(\d{2})([AEF])?", re.IGNORECASE)
BLOCK_SELECTOR = re.compile(r"^#\d+$")
MQL_BLOCK_DEFINITION = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*Block\s*\(\s*#(\d+)", re.IGNORECASE)
DYNAMIC_END_MARKERS = {"N()", "MRQ()"}
DYNAMIC_END_PATTERN = re.compile(r"\{结束时间\}\s*=\s*(N\(\)|MRQ\(\))")
QUOTED_DYNAMIC_END_PATTERN = re.compile(r"\{结束时间\}\s*=\s*[\"'](?:N\(\)|MRQ\(\))[\"']")
DATA_SOURCES = {"MQL", "MX_DS_MCP"}
CHART_METHODS = {"LAYOUT_CONTENT_VERIFIED", "LAYOUT_CONTENT_CORRECTED", "EXTERNAL_VERIFIED", "VISUAL_ESTIMATE"}
CHART_CONFIDENCE = {"EXACT", "APPROXIMATE"}
CHART_MAPPING_STATUSES = {"FULL", "PARTIAL", "NO_MATCH", "NOT_APPLICABLE"}
MQL_RETRYABLE_FAILURES = {"SYNTAX_ERROR", "PARAMETER_ERROR", "DATE_ERROR", "ENTITY_CODE_ERROR", "SECTOR_UNIVERSE_ERROR", "PATH_ERROR"}
MQL_FALLBACK_FAILURES = {"UNSUPPORTED", "NO_CANDIDATE_AFTER_SEARCH", "REMOTE_NO_DATA_AFTER_VALID_QUERY", "SERVICE_FAILURE_CONFIRMED"}
QUERY_SHAPES = {"CROSS_SECTION", "TIME_SERIES", "REPORT_MATRIX"}
AXIS_TYPES = {"FINANCIAL_METRIC", "REPORTING_PERIOD", "DATE", "SERIES", "ENTITY", "METRIC", "CATEGORY"}
DATA_PATH_TYPES = {"INDICATOR", "REPORT"}
REPORT_FALLBACK_REASONS = {"NO_INDICATOR_CANDIDATE", "INDICATOR_EXECUTION_NO_DATA", "INDICATOR_COVERAGE_INCOMPLETE"}
SOURCE_SEMANTIC_TYPES = {"FINANCIAL_STATEMENT", "FINANCIAL_METRICS", "TIME_SERIES_CHART", "CROSS_SECTION_TABLE", "COMPARABLE_COMPANY_TABLE", "OTHER"}
OBSERVATION_FREQUENCIES = {"DAILY_TRADING", "DAILY_CALENDAR", "WEEKLY", "MONTHLY", "QUARTERLY", "ANNUAL", "IRREGULAR"}
FINANCIAL_SOURCE_TYPES = {"FINANCIAL_STATEMENT", "FINANCIAL_METRICS"}
FINANCIAL_QUERY_MODES = {"REPORT_FULL_TABLE", "NATIVE_MULTI_PERIOD", "FINANCIAL_TIME_SERIES", "PERIOD_BLOCK_MERGE", "REPORT_FALLBACK"}
FINANCIAL_TABLE_NAME = re.compile(
    r"资产负债表|利润表|损益表|现金流量表|财务摘要|财务比率|每股指标|"
    r"balance\s*sheet|income\s*statement|profit\s*(?:and|&)\s*loss|cash\s*flow|"
    r"financial\s*(?:summary|ratio)|per\s*share",
    re.IGNORECASE,
)
# R07：主营构成/分部表的分部维度。TOTAL=合计/总计行，DETAIL=明细分部行；合计数据不得替代明细。
SEGMENT_ROLES = {"TOTAL", "DETAIL"}


def segment_value_gaps(item: dict[str, Any], covered_segments: list[str], roles: dict[str, str]) -> list[str]:
    """返回「已覆盖明细分部 × 已覆盖数值字段」中无有效值的单元，阻止合计行替代明细覆盖。"""
    if not any(roles.get(str(segment)) == "DETAIL" for segment in covered_segments):
        return []
    last_result = item.get("last_result")
    if not isinstance(last_result, list) or len(last_result) < 2:
        return []
    value_types = {
        str(contract.get("field")): str(contract.get("value_type"))
        for contract in item.get("unit_contracts", [])
        if isinstance(contract, dict)
    }
    numeric_fields = [str(name) for name in item.get("covered_fields", []) if value_types.get(str(name)) == "NUMBER"]
    if not numeric_fields:
        return []
    columns = [str(value) for value in last_result[0]]
    rows_by_label = {str(row[0]): row for row in last_result[1:] if isinstance(row, list) and row}
    gaps: list[str] = []
    for segment in covered_segments:
        if roles.get(str(segment)) != "DETAIL":
            continue
        row = rows_by_label.get(str(segment))
        if row is None:
            continue
        for name in numeric_fields:
            if name not in columns:
                continue
            index = columns.index(name)
            value = row[index] if index < len(row) else None
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                gaps.append(f"{segment}×{name}")
    return gaps


def has_continuous_time_series_block(script: str) -> bool:
    return bool(re.search(r"\b(?:TimeSeries|Edb)Block\s*\(", script, re.IGNORECASE))


def is_edb_workpaper(item: dict[str, Any]) -> bool:
    return (
        item.get("execution_status") == "SUCCESS"
        and item.get("data_source", "MQL") == "MQL"
        and selected_block_name(str(item.get("mql_script") or ""), item.get("block_selector")).lower() == "edbblock"
    )


def dynamic_end_marker(item: dict[str, Any]) -> str | None:
    marker = item.get("query_end_date_dynamic")
    return marker if isinstance(marker, str) and marker in DYNAMIC_END_MARKERS else None


def is_dynamic_timeseries_workpaper(item: dict[str, Any]) -> bool:
    return (
        item.get("execution_status") == "SUCCESS"
        and item.get("data_source", "MQL") == "MQL"
        and dynamic_end_marker(item) is not None
    )


def validate_dynamic_end_marker(item: dict[str, Any], label: str) -> None:
    """Keep the declared dynamic end marker and the SetWindow script text in sync.

    A dynamic anchor refreshes beyond its generation-time shape, so the workpaper
    must declare query_end_date_dynamic and keep query_end_date as the resolved
    generation-time snapshot; scripts with an unquoted marker must not bypass the
    declaration, and quoted markers are runtime errors that must fail fast here.
    """
    script = str(item.get("mql_script") or "")
    marker = item.get("query_end_date_dynamic")
    script_marker = DYNAMIC_END_PATTERN.search(script)
    require(QUOTED_DYNAMIC_END_PATTERN.search(script) is None, f"{label} dynamic end markers N()/MRQ() must appear unquoted in SetWindow; quoted markers are rejected by the MQL runtime")
    if marker in (None, ""):
        require(script_marker is None, f"{label} script uses a dynamic end marker; declare query_end_date_dynamic and keep query_end_date as the generation-time snapshot")
        return
    require(marker in DYNAMIC_END_MARKERS, f"{label}.query_end_date_dynamic must be N() or MRQ()")
    require(item.get("execution_status") == "SUCCESS" and item.get("data_source", "MQL") == "MQL", f"{label}.query_end_date_dynamic requires a successful MQL workpaper")
    require(not is_edb_workpaper(item), f"{label} EDB anchors do not support dynamic end markers; keep a fixed end date")
    require(script_marker is not None and script_marker.group(1) == marker, f"{label}.query_end_date_dynamic must appear as the same unquoted marker in SetWindow")


MAX_WINDOW_POINTS = 1000


def validate_time_series_window(item: dict[str, Any], label: str) -> None:
    """R05：校验应用层窗口策略与位置数。

    LATEST_1000_TRADING_DAYS 交付「生成时最近 1000 交易日固定窗口」：query 窗口允许与 source
    原图区间不同（source 事实保留原值），但必须如实标注位置数与截断，且不得伪装成原生滚动。
    """
    script = str(item.get("mql_script") or "")
    preload = item.get("preload_period_count")
    if "{预加载周期}" in script or preload is not None:
        require(isinstance(preload, int) and not isinstance(preload, bool) and preload >= 0, f"{label}.preload_period_count must be a non-negative integer when the window uses preload")
    if item.get("window_policy", "SOURCE_FIXED") != "LATEST_1000_TRADING_DAYS":
        return
    require(isinstance(item.get("query_window_point_count"), int) and item["query_window_point_count"] >= 1, f"{label}.query_window_point_count is required for LATEST_1000_TRADING_DAYS")
    require(item.get("rolling_implemented") is False, f"{label} native rolling windows are not implemented; LATEST_1000_TRADING_DAYS must declare rolling_implemented=false")
    require(item["query_window_point_count"] + (preload or 0) <= MAX_WINDOW_POINTS, f"{label} official query points plus preload must not exceed {MAX_WINDOW_POINTS}")
    start = item.get("query_start_date")
    end = item.get("query_end_date")
    if start and end:
        require(str(start) <= str(end), f"{label}.query_start_date must not be after query_end_date")


def validate_service_fault(item: dict[str, Any], label: str) -> None:
    if item.get("mql_failure_category") != "SERVICE_FAILURE_CONFIRMED":
        return
    fault = item.get("mql_service_failure", {})
    require(isinstance(fault, dict) and fault.get("status") in {"FAILED", "TIMEOUT"}
            and fault.get("failure_type") in {"NETWORK_ERROR", "HTTP_5XX", "RATE_LIMIT", "AUTH_INVALID", "TOOL_UNAVAILABLE", "PARSE_FAILED"}
            and bool(fault.get("tool_call_id")) and bool(fault.get("evidence_locator")),
            f"{label} needs a returned terminal MQL service error; unfinished/abandoned calls cannot authorize fallback")


def validate_mql_fallback(item: dict[str, Any], label: str) -> None:
    require(item.get("fallback_from_mql") is True, f"{label}.fallback_from_mql must be true for numeric MX_DS_MCP fallback")
    category = item.get("mql_failure_category")
    require(category in MQL_FALLBACK_FAILURES, f"{label}.mql_failure_category must be an allowed terminal MQL failure, not a correctable routing error")
    require(isinstance(item.get("mql_failure_evidence"), str) and item["mql_failure_evidence"].strip(), f"{label}.mql_failure_evidence is required for numeric MX_DS_MCP fallback")
    validate_service_fault(item, label)


def normalize_data_source(value: Any, label: str) -> str:
    require(isinstance(value, str), f"{label}.data_source must be a string")
    normalized = value.strip().upper().replace("-", "_")
    require(normalized in DATA_SOURCES, f"{label}.data_source must be MQL, MX_DS_MCP, or mx-ds-mcp")
    return normalized


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="UTF-8 JSON input file")
    parser.add_argument("--output", type=Path, help="Output .xlsx path")
    parser.add_argument("--validate-only", action="store_true", help="Validate input and exit")
    arguments = parser.parse_args()
    if not arguments.validate_only and arguments.output is None:
        parser.error("--output is required unless --validate-only is used")
    return arguments


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_workpaper_status(item: dict[str, Any], label: str) -> tuple[str, str]:
    execution_status = item.get("execution_status")
    require(execution_status in {"SUCCESS", "TABLE_BLOCKED"}, f"{label}.execution_status must be SUCCESS or TABLE_BLOCKED")
    mapping_status = item.get("mapping_status")
    allowed = {"TABLE_BLOCKED"} if execution_status == "TABLE_BLOCKED" else {"FULL", "PARTIAL"}
    require(mapping_status in allowed, f"{label}.mapping_status must match execution_status")
    return execution_status, mapping_status


def apply_mql_orientation(matrix: list[list[Any]], orientation: int) -> list[list[Any]]:
    """Apply the Choice Excel add-in orientation semantics to a rectangular matrix."""
    require(orientation in {0, 1}, "mql_orientation must be 0 or 1")
    return matrix if orientation == 0 else [list(row) for row in zip(*matrix)]


def looks_like_technical_code(value: Any) -> bool:
    text = str(value).strip()
    return bool(re.fullmatch(r"[A-Za-z0-9_.:-]+", text)) and bool(re.search(r"\d|[._:-]", text))


PERIOD_COLUMN_KIND = "REPORTING_PERIOD"


def looks_like_period_label(value: Any) -> bool:
    """研报期间标签必须能被既有的期间记号识别（保留 LF 最新披露期特例）。

    期间标签（如 `2025A`）天然命中技术码正则，因此不适用行标签的可读性约束；
    这里用「必须是可识别的期间记号」作为等效强度的形状校验。
    """
    text = str(value).strip()
    if text == "LF":
        return True
    return bool(PERIOD_TOKEN.search(text) or SHORT_FY_TOKEN.search(text))


def split_display_label_map(label_map: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 kind 拆出「期间列映射」与「其余（行标签）映射」，各自保持声明顺序。"""
    period = [value for value in label_map if isinstance(value, dict) and value.get("kind") == PERIOD_COLUMN_KIND]
    rows = [value for value in label_map if not (isinstance(value, dict) and value.get("kind") == PERIOD_COLUMN_KIND)]
    return rows, period


def period_label_map_entries(item: dict[str, Any]) -> list[dict[str, Any]]:
    """读取一个 workpaper 的期间列映射条目，供校验与底稿元数据共用。"""
    label_map = item.get("display_label_map")
    if not isinstance(label_map, list):
        return []
    return split_display_label_map(label_map)[1]


def validate_bbox(value: Any, label: str) -> None:
    require(isinstance(value, list) and len(value) == 4, f"{label}.bbox must have four numbers")
    require(all(isinstance(number, (int, float)) for number in value), f"{label}.bbox must be numeric")
    x0, y0, x1, y1 = value
    require(0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1, f"{label}.bbox must be a normalized valid rectangle")


def bbox_inside(inner: list[float], outer: list[float]) -> bool:
    epsilon = 1e-9
    return (
        inner[0] + epsilon >= outer[0]
        and inner[1] + epsilon >= outer[1]
        and inner[2] <= outer[2] + epsilon
        and inner[3] <= outer[3] + epsilon
    )


def bbox_overlap_area(first: list[float], second: list[float]) -> float:
    width = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    height = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    return width * height


def extract_numeric_tokens(row: list[Any]) -> list[str]:
    tokens: list[str] = []
    for value in row[1:]:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            tokens.append(str(value))
        elif isinstance(value, str):
            tokens.extend(NUMERIC_TOKEN.findall(value))
    return tokens


def source_periods_from_headers(headers: list[Any], kinds: list[Any]) -> list[str]:
    """Extract unique periods from plain or metric-period headers."""
    periods: list[str] = []
    for header, kind in zip(headers, kinds):
        if kind != "ACTUAL":
            continue
        text = str(header).strip()
        match = PERIOD_TOKEN.search(text)
        short = SHORT_FY_TOKEN.search(text)
        if match:
            period = match.group(0).upper()
        elif short:
            period = f"{2000 + int(short.group(1))}{(short.group(2) or 'A').upper()}"
        else:
            period = text
        if period and period not in periods:
            periods.append(period)
    return periods


def validate_payload(payload: dict[str, Any]) -> None:
    guide = payload.get("guide")
    require(isinstance(guide, dict), "guide must be an object")
    required_guide = (
        "company_name", "security_code", "report_title", "report_date",
        "verification_date", "pdf_page_count", "census_table_count", "visual_object_count",
    )
    missing = [field for field in required_guide if guide.get(field) in (None, "")]
    require(not missing, f"guide is missing required fields: {', '.join(missing)}")
    require(isinstance(guide["pdf_page_count"], int) and guide["pdf_page_count"] > 0, "pdf_page_count must be a positive integer")
    require(isinstance(guide["census_table_count"], int) and guide["census_table_count"] >= 0, "census_table_count must be a non-negative integer")
    require(isinstance(guide["visual_object_count"], int) and guide["visual_object_count"] >= 0, "visual_object_count must be a non-negative integer")

    for field in ("snapshots", "chart_snapshots", "chart_data", "excluded_tables", "workpapers", "verification", "execution_log"):
        require(isinstance(payload.get(field), list), f"{field} must be an array")
    require(isinstance(payload.get("forecast"), dict), "forecast must be an object")
    snapshots = payload["snapshots"]
    excluded = payload["excluded_tables"]
    require(guide["census_table_count"] == len(snapshots) + len(excluded), "table census count must equal included plus excluded tables")

    all_ids: set[str] = set()
    snapshot_ids: list[str] = []
    for index, table in enumerate(snapshots):
        label = f"snapshots[{index}]"
        require(isinstance(table, dict), f"{label} must be an object")
        table_id = table.get("table_id")
        require(isinstance(table_id, str) and table_id.strip(), f"{label}.table_id is required")
        require(table_id not in all_ids, f"duplicate table_id: {table_id}")
        all_ids.add(table_id)
        snapshot_ids.append(table_id)
        require(isinstance(table.get("page"), int) and 1 <= table["page"] <= guide["pdf_page_count"], f"{label}.page is invalid")
        require(bool(table.get("table_name")), f"{label}.table_name is required")
        validate_bbox(table.get("bbox"), label)
        for field in ("layout_group", "lane"):
            require(bool(table.get(field)), f"{label}.{field} is required")
        require(isinstance(table.get("reading_order"), int) and table["reading_order"] > 0, f"{label}.reading_order must be positive")
        headers = table.get("headers")
        rows = table.get("rows")
        kinds = table.get("header_kinds")
        require(isinstance(headers, list) and headers, f"{label}.headers must be non-empty")
        require(isinstance(rows, list) and rows, f"{label}.rows must contain every non-empty data row")
        require(isinstance(kinds, list) and len(kinds) == len(headers), f"{label}.header_kinds must match headers")
        require(all(kind in ALLOWED_HEADER_KINDS for kind in kinds), f"{label}.header_kinds contains an invalid value")
        for row_index, row in enumerate(rows):
            require(isinstance(row, list) and len(row) == len(headers), f"{label}.rows[{row_index}] is not rectangular")
            require(any(value not in (None, "") for value in row), f"{label}.rows[{row_index}] is empty")
        row_bold = table.get("row_bold", [False] * len(rows))
        require(isinstance(row_bold, list) and len(row_bold) == len(rows), f"{label}.row_bold must match rows")
        require(all(isinstance(value, bool) for value in row_bold), f"{label}.row_bold must contain booleans")
        source_labels = table.get("source_row_labels")
        extracted_labels = [str(row[0]) if row[0] is not None else "" for row in rows]
        require(isinstance(source_labels, list) and source_labels == extracted_labels, f"{label}.source_row_labels does not match extracted row order")
        row_bboxes = table.get("row_bboxes")
        require(isinstance(row_bboxes, list) and len(row_bboxes) == len(rows), f"{label}.row_bboxes must cover every row")
        for row_index, row_bbox in enumerate(row_bboxes):
            validate_bbox(row_bbox, f"{label}.row_bboxes[{row_index}]")
            require(bbox_inside(row_bbox, table["bbox"]), f"{label}.row_bboxes[{row_index}] falls outside its table")
        computed_tokens_by_row = [extract_numeric_tokens(row) for row in rows]
        computed_row_tokens = [len(tokens) for tokens in computed_tokens_by_row]
        require(table.get("source_numeric_tokens_by_row") == computed_tokens_by_row, f"{label}.source_numeric_tokens_by_row does not match extracted values")
        require(table.get("row_numeric_token_counts") == computed_row_tokens, f"{label}.row_numeric_token_counts does not match extracted cells")
        require(table.get("source_row_count") == len(rows), f"{label}.source_row_count does not match extracted rows")
        source_tokens = table.get("source_numeric_token_count")
        extracted_tokens = table.get("extracted_numeric_token_count")
        require(isinstance(source_tokens, int) and source_tokens >= 0, f"{label}.source_numeric_token_count is invalid")
        require(source_tokens == extracted_tokens, f"{label} numeric-token count mismatch")
        require(extracted_tokens == sum(computed_row_tokens), f"{label}.extracted_numeric_token_count is not reproducible from rows")
        require(table.get("source_status") == "PASS", f"{label}.source_status must be PASS")
        require(table.get("visual_check") == "PASS", f"{label}.visual_check must be PASS")
        require(table.get("source_row_axis") in AXIS_TYPES, f"{label}.source_row_axis is required")
        require(table.get("source_column_axis") in AXIS_TYPES and table["source_column_axis"] != table["source_row_axis"], f"{label}.source_column_axis is required")
        source_semantic_type = table.get("source_semantic_type")
        require(source_semantic_type in SOURCE_SEMANTIC_TYPES, f"{label}.source_semantic_type is invalid")
        source_periods = table.get("source_periods")
        expected_source_periods = source_periods_from_headers(headers, kinds)
        require(isinstance(source_periods, list) and all(isinstance(value, str) and value.strip() for value in source_periods), f"{label}.source_periods must be an array")
        require(source_periods == expected_source_periods, f"{label}.source_periods must equal ACTUAL headers in source order")
        require(len(source_periods) == len(set(source_periods)), f"{label}.source_periods must be unique")
        structurally_financial = (
            source_semantic_type in FINANCIAL_SOURCE_TYPES
            or table.get("source_row_axis") == "FINANCIAL_METRIC"
            or bool(FINANCIAL_TABLE_NAME.search(str(table.get("table_name", ""))))
        )
        if structurally_financial:
            require(source_semantic_type in FINANCIAL_SOURCE_TYPES, f"{label} financial source cannot be downgraded to a non-financial semantic type")
            require(table.get("source_row_axis") == "FINANCIAL_METRIC" and table.get("source_column_axis") == "REPORTING_PERIOD", f"{label} financial source must use FINANCIAL_METRIC x REPORTING_PERIOD")
            require(bool(source_periods), f"{label} financial source must retain every ACTUAL reporting period or LF latest-filing period")
            if table.get("source_period_basis") == "LATEST_FILING":
                require(source_periods == ["LF"], f"{label} latest-filing source must use source_periods=['LF']")
        require(isinstance(table.get("layout_contract_reason"), str) and table["layout_contract_reason"].strip(), f"{label}.layout_contract_reason is required")
        require(isinstance(table.get("queryable_fields"), list) and table["queryable_fields"] and all(isinstance(value, str) and value.strip() for value in table["queryable_fields"]), f"{label}.queryable_fields must enumerate the source fields before query generation")
        require(len(set(table["queryable_fields"])) == len(table["queryable_fields"]), f"{label}.queryable_fields must be unique")
        require(isinstance(table.get("is_visual_object"), bool), f"{label}.is_visual_object must explicitly identify chart-like source tables")
        segments = table.get("source_segments")
        if segments is not None:
            require(isinstance(segments, list) and segments, f"{label}.source_segments must be a non-empty array")
            names = [item.get("segment") for item in segments]
            require(all(isinstance(name, str) and name.strip() for name in names), f"{label}.source_segments[].segment must be a non-empty string")
            require(len(names) == len(set(names)), f"{label}.source_segments must use unique segment labels")
            require(all(item.get("role") in SEGMENT_ROLES for item in segments), f"{label}.source_segments[].role must be one of {sorted(SEGMENT_ROLES)}")
            require(any(item["role"] == "TOTAL" for item in segments) and any(item["role"] == "DETAIL" for item in segments), f"{label}.source_segments must keep both a TOTAL and at least one DETAIL segment")
            require(table.get("source_row_axis") == "CATEGORY", f"{label} segment source must use a CATEGORY row axis")
            require(isinstance(table.get("segment_role_basis"), str) and table["segment_role_basis"].strip(), f"{label}.segment_role_basis must record how TOTAL/DETAIL roles were assigned")
        hierarchy = table.get("header_hierarchy")
        if hierarchy is not None:
            require(isinstance(hierarchy, list) and len(hierarchy) == len(headers), f"{label}.header_hierarchy must pair every header column")
            require(all(isinstance(item, dict) and "parent" in item and "child" in item for item in hierarchy), f"{label}.header_hierarchy entries must record parent and child labels")
        if table.get("header_parse_origin") == "NESTED_HEADER":
            require(isinstance(hierarchy, list) and len(hierarchy) == len(headers), f"{label}.header_hierarchy must record the parent/child pairing for every column of a nested header")
            require(all(value.get("child") for value in hierarchy if value.get("parent")), f"{label}.header_hierarchy must keep the child label beside every nested parent label")

    for first_index, first in enumerate(snapshots):
        for second in snapshots[first_index + 1:]:
            if first["page"] == second["page"] and first["layout_group"] == second["layout_group"]:
                require(bbox_overlap_area(first["bbox"], second["bbox"]) == 0, f'{first["table_id"]} and {second["table_id"]} overlap in one layout group')

    for index, table in enumerate(excluded):
        label = f"excluded_tables[{index}]"
        require(isinstance(table, dict), f"{label} must be an object")
        table_id = table.get("table_id")
        require(isinstance(table_id, str) and table_id.strip(), f"{label}.table_id is required")
        require(table_id not in all_ids, f"duplicate table_id: {table_id}")
        all_ids.add(table_id)
        require(isinstance(table.get("page"), int) and 1 <= table["page"] <= guide["pdf_page_count"], f"{label}.page is invalid")
        require(bool(table.get("table_name")), f"{label}.table_name is required")
        validate_bbox(table.get("bbox"), label)
        require(table.get("exclude_reason") in ALLOWED_EXCLUSIONS, f"{label}.exclude_reason is not allowed")

    chart_ids: set[str] = set()
    for index, chart in enumerate(payload["chart_snapshots"]):
        label = f"chart_snapshots[{index}]"
        require(isinstance(chart, dict), f"{label} must be an object")
        chart_id = chart.get("chart_id")
        require(isinstance(chart_id, str) and chart_id.strip(), f"{label}.chart_id is required")
        require(chart_id not in chart_ids, f"duplicate chart_id: {chart_id}")
        chart_ids.add(chart_id)
        require(isinstance(chart.get("page"), int) and 1 <= chart["page"] <= guide["pdf_page_count"], f"{label}.page is invalid")
        require(bool(chart.get("title")), f"{label}.title is required")
        bbox = chart.get("bbox_pt")
        require(isinstance(bbox, dict), f"{label}.bbox_pt must be an object")
        for field in ("minX", "maxX", "minY", "maxY"):
            require(isinstance(bbox.get(field), (int, float)), f"{label}.bbox_pt.{field} must be numeric")
        require(bbox["minX"] < bbox["maxX"] and bbox["minY"] < bbox["maxY"], f"{label}.bbox_pt must be a valid rectangle")
        crop = chart.get("crop_pt")
        require(isinstance(crop, dict), f"{label}.crop_pt must be an object")
        for field in ("top", "bottom", "left", "right"):
            require(isinstance(crop.get(field), (int, float)), f"{label}.crop_pt.{field} must be numeric")
        require(crop["left"] < crop["right"] and crop["top"] < crop["bottom"], f"{label}.crop_pt must be a valid rectangle")
        snapshot_path = chart.get("snapshot_path")
        require(isinstance(snapshot_path, str) and Path(snapshot_path).is_absolute(), f"{label}.snapshot_path must be absolute")
        require(Path(snapshot_path).is_file(), f"{label}.snapshot_path does not exist: {snapshot_path}")
        require(Path(snapshot_path).suffix.lower() in {".png", ".jpg", ".jpeg"}, f"{label}.snapshot_path must be PNG or JPEG")
        require(chart.get("header_footer_ok") is True, f"{label}.header_footer_ok must be true")
        require(chart.get("visual_check") == "PASS", f"{label}.visual_check must be PASS")
        require(isinstance(chart.get("serial", []), list), f"{label}.serial must be an array")
        coordinate = chart.get("coordinate", {})
        require(isinstance(coordinate, dict), f"{label}.coordinate must be an object")
        require(isinstance(coordinate.get("time_series"), bool), f"{label}.coordinate.time_series must explicitly identify continuous time-series charts")

    require(guide["visual_object_count"] == len(payload["chart_snapshots"]), "visual_object_count must equal chart_snapshots, including chart-like table blocks")

    paired_table_ids: set[str] = set()
    snapshot_by_id = {table["table_id"]: table for table in snapshots}
    chart_by_id = {chart["chart_id"]: chart for chart in payload["chart_snapshots"]}
    for index, chart in enumerate(payload["chart_snapshots"]):
        label = f"chart_snapshots[{index}]"
        parsed_table_ids = chart.get("parsed_table_ids", [])
        require(isinstance(parsed_table_ids, list), f"{label}.parsed_table_ids must be an array")
        for table_id in parsed_table_ids:
            require(table_id in snapshot_by_id, f"{label}.parsed_table_ids references an unknown snapshot: {table_id}")
            require(table_id not in paired_table_ids, f"snapshot {table_id} is paired with more than one chart")
            require(snapshot_by_id[table_id]["page"] == chart["page"], f"{label} and paired snapshot {table_id} must be on the same page")
            require(snapshot_by_id[table_id].get("parse_origin") == "LAYOUT_TABLE_BLOCK", f"paired snapshot {table_id}.parse_origin must be LAYOUT_TABLE_BLOCK")
            paired_table_ids.add(table_id)
    for table in snapshots:
        if table["is_visual_object"]:
            paired_chart_id = table.get("paired_chart_id")
            require(paired_chart_id in chart_by_id, f'{table["table_id"]}.paired_chart_id must reference a screenshot')
            require(table["table_id"] in chart_by_id[paired_chart_id].get("parsed_table_ids", []), f'{table["table_id"]} must be listed by its paired chart screenshot')
        else:
            require(table.get("paired_chart_id") in (None, ""), f'{table["table_id"]}.paired_chart_id is only allowed for visual objects')

    chart_data_ids: set[str] = set()
    chart_data_by_id: dict[str, dict[str, Any]] = {}
    for index, block in enumerate(payload["chart_data"]):
        label = f"chart_data[{index}]"
        require(isinstance(block, dict), f"{label} must be an object")
        require(block.get("chart_id") in chart_ids, f"{label}.chart_id does not reference chart_snapshots")
        require(not chart_by_id[block["chart_id"]].get("parsed_table_ids"), f"{label} cannot coexist with parsed_table_ids for the same chart")
        data_block_id = block.get("data_block_id")
        require(isinstance(data_block_id, str) and data_block_id.strip(), f"{label}.data_block_id is required")
        require(data_block_id not in chart_data_ids, f"duplicate data_block_id: {data_block_id}")
        chart_data_ids.add(data_block_id)
        chart_data_by_id[data_block_id] = block
        headers = block.get("headers")
        rows = block.get("rows")
        require(isinstance(headers, list) and headers and all(value not in (None, "") for value in headers), f"{label}.headers must be complete")
        require(isinstance(rows, list) and rows, f"{label}.rows must be non-empty")
        require(all(isinstance(row, list) and len(row) == len(headers) for row in rows), f"{label}.rows must be rectangular")
        method = block.get("extraction_method")
        confidence = block.get("confidence_status")
        require(method in CHART_METHODS, f"{label}.extraction_method is invalid")
        require(confidence in CHART_CONFIDENCE, f"{label}.confidence_status is invalid")
        require(not (method == "VISUAL_ESTIMATE" and confidence == "EXACT"), f"{label}.VISUAL_ESTIMATE cannot be EXACT")
        require(bool(block.get("source_note")), f"{label}.source_note is required")
        require(block.get("candidate_source") == "LAYOUT_IMAGE_CONTENT", f"{label}.candidate_source must be LAYOUT_IMAGE_CONTENT")
        require(block.get("visual_validation") == "PASS", f"{label}.visual_validation must be PASS")
        corrections = block.get("visual_corrections")
        require(isinstance(corrections, list), f"{label}.visual_corrections must be an array")
        if method == "LAYOUT_CONTENT_CORRECTED":
            require(bool(corrections), f"{label}.visual_corrections is required when content was corrected")
        if method == "LAYOUT_CONTENT_VERIFIED":
            require(not corrections, f"{label}.visual_corrections must be empty when content was verified unchanged")
        mapping_status = block.get("mql_mapping_status")
        require(mapping_status in CHART_MAPPING_STATUSES, f"{label}.mql_mapping_status is invalid")
        if mapping_status != "FULL":
            require(bool(block.get("mql_mapping_note")), f"{label}.mql_mapping_note is required unless mapping is FULL")
        omitted_metrics = block.get("omitted_metrics", [])
        require(isinstance(omitted_metrics, list) and all(isinstance(value, str) and value.strip() for value in omitted_metrics), f"{label}.omitted_metrics must be an array of source metric labels")
        if mapping_status == "PARTIAL":
            require(bool(omitted_metrics), f"{label}.omitted_metrics is required for PARTIAL mapping")
        expected_shape = "TIME_SERIES" if chart_by_id[block["chart_id"]]["coordinate"]["time_series"] else "CROSS_SECTION"
        require(block.get("source_temporal_shape") == expected_shape, f"{label}.source_temporal_shape must match chart coordinate semantics")

    execution_attempts = {
        item.get("attempt_id"): item for item in payload["execution_log"]
        if isinstance(item, dict) and isinstance(item.get("attempt_id"), str) and item.get("attempt_id").strip()
    }
    require(len(execution_attempts) == len([
        item for item in payload["execution_log"]
        if isinstance(item, dict) and isinstance(item.get("attempt_id"), str) and item.get("attempt_id").strip()
    ]), "execution_log.attempt_id must be unique")

    table_workpaper_ids: list[str] = []
    mapping_ids: set[str] = set()
    successful_chart_workpapers: dict[str, list[dict[str, Any]]] = {}
    successful_mql_run_ids: set[str] = set()
    comparable_workpaper_groups: dict[str, list[dict[str, Any]]] = {}
    script_hash_sources: dict[str, str] = {}
    for index, item in enumerate(payload["workpapers"]):
        label = f"workpapers[{index}]"
        require(isinstance(item, dict), f"{label} must be an object")
        source_type = item.get("source_type")
        require(source_type in {"TABLE", "CHART"}, f"{label}.source_type must be TABLE or CHART")
        source_id = item.get("source_id")
        require(isinstance(source_id, str) and source_id.strip(), f"{label}.source_id is required")
        item["source_type"] = source_type
        item["source_id"] = source_id
        mapping_id = item.get("mapping_id") or (f"table:{source_id}" if source_type == "TABLE" else None)
        require(isinstance(mapping_id, str) and mapping_id.strip(), f"{label}.mapping_id is required")
        require(mapping_id not in mapping_ids, f"duplicate mapping_id: {mapping_id}")
        mapping_ids.add(mapping_id)
        item["mapping_id"] = mapping_id
        if source_type == "TABLE":
            require(source_id in snapshot_ids, f"{label}.source_id does not reference snapshots")
            if source_id not in table_workpaper_ids:
                table_workpaper_ids.append(source_id)
            source_data_block_id = None
            snapshot = snapshot_by_id[source_id]
            # 财务来源 OTHER 锚点豁免：财务摘要等来源拆出的估值截面锚点（非财务形态轴）允许登记 OTHER；
            # 仅覆盖降级方向，OTHER→财务 的升级方向仍按原规则拒绝。
            financial_other_anchor = (
                snapshot["source_semantic_type"] in FINANCIAL_SOURCE_TYPES
                and item.get("source_semantic_type") == "OTHER"
                and (item.get("target_row_axis"), item.get("target_column_axis")) != ("FINANCIAL_METRIC", "REPORTING_PERIOD")
            )
            require(item.get("source_semantic_type") == snapshot["source_semantic_type"] or financial_other_anchor, f"{label}.source_semantic_type must inherit the source snapshot and cannot be downgraded")
        else:
            require(source_id in chart_ids, f"{label}.source_id does not reference chart_snapshots")
            source_data_block_id = item.get("source_data_block_id")
            require(source_data_block_id in chart_data_by_id, f"{label}.source_data_block_id does not reference chart_data")
            require(chart_data_by_id[source_data_block_id]["chart_id"] == source_id, f"{label}.source_data_block_id belongs to another chart")
            covered_metrics = item.get("covered_metrics")
            require(isinstance(covered_metrics, list) and covered_metrics and all(isinstance(value, str) and value.strip() for value in covered_metrics), f"{label}.covered_metrics must contain source metric labels")
            omitted_metrics = item.get("omitted_metrics", [])
            require(isinstance(omitted_metrics, list) and all(isinstance(value, str) and value.strip() for value in omitted_metrics), f"{label}.omitted_metrics must be an array")
        execution_status, mapping_status = validate_workpaper_status(item, label)
        if mapping_status == "PARTIAL":
            require(bool(item.get("mapping_note")), f"{label}.mapping_note is required for PARTIAL mappings")
            if source_type == "CHART":
                require(bool(item.get("omitted_metrics")), f"{label}.omitted_metrics is required for PARTIAL CHART mappings")
        require(isinstance(item.get("expected_rows"), int) and item["expected_rows"] > 0, f"{label}.expected_rows must be positive")
        require(isinstance(item.get("expected_columns"), int) and item["expected_columns"] > 0, f"{label}.expected_columns must be positive")
        data_source = normalize_data_source(item.get("data_source", "MQL"), label)
        item["data_source"] = data_source
        require(bool(item.get("query_interface")), f"{label}.query_interface is required")
        require(item.get("query_interface") != "PDF原文静态抽取", f"{label} cannot use PDF-only data as a Choice workpaper")
        script = item.get("mql_script")
        if execution_status == "TABLE_BLOCKED":
            require(data_source == "MQL", f"{label}.TABLE_BLOCKED is only valid for MQL workpapers")
            require(bool(item.get("block_reason")), f"{label}.block_reason is required for TABLE_BLOCKED")
            require(bool(item.get("mapping_note")), f"{label}.mapping_note is required for TABLE_BLOCKED")
            if source_type == "TABLE":
                snapshot = snapshot_by_id[source_id]
                source_periods = item.get("source_periods")
                omitted_periods = item.get("omitted_periods", [])
                require(isinstance(source_periods, list) and set(source_periods) <= set(snapshot["source_periods"]), f"{label}.source_periods must stay within the source ACTUAL periods even when blocked")
                require(item.get("covered_periods", []) == [], f"{label}.covered_periods must be empty when blocked")
                require(isinstance(omitted_periods, list) and all(isinstance(value, dict) for value in omitted_periods) and {value.get("period") for value in omitted_periods} == set(source_periods), f"{label}.omitted_periods must cover every period of this blocked anchor")
                require(all(
                    isinstance(value.get("reason"), str) and value["reason"].strip()
                    and isinstance(value.get("evidence_ids"), list) and value["evidence_ids"]
                    and all(evidence_id in execution_attempts for evidence_id in value["evidence_ids"])
                    for value in omitted_periods
                ), f"{label}.omitted_periods require execution attempt evidence when blocked")
            for forbidden in ("raw_result", "last_result", "cached_table", "result_origin", "execution_run_id"):
                require(item.get(forbidden) in (None, "", []), f"{label}.{forbidden} must be absent for TABLE_BLOCKED")
            continue
        if data_source == "MQL":
            require(isinstance(script, str) and script.strip(), f"{label}.mql_script is required for successful MQL workpapers")
            block_numbers = [int(value) for value in MQL_BLOCK_DEFINITION.findall(script)]
            require(block_numbers == list(range(1, len(block_numbers) + 1)), f"{label}.mql_script Block numbers must start at #1 and increase continuously")
        else:
            require(script in (None, ""), f"{label}.mql_script is not allowed for MX_DS_MCP")
        require(bool(item.get("result_as_of")), f"{label}.result_as_of is required")
        if data_source == "MQL":
            require(item.get("result_origin") == "MQL_TOOLCHAIN", f"{label}.result_origin must be MQL_TOOLCHAIN for MQL workpapers")
            require(isinstance(item.get("execution_run_id"), str) and item["execution_run_id"].strip(), f"{label}.execution_run_id is required for the current MQL_TOOLCHAIN run")
            successful_mql_run_ids.add(item["execution_run_id"])
            contract_errors = validate_refresh_contract(item, payload["execution_log"])
            require(not contract_errors, f"{label} refresh contract failed: " + "; ".join(f"{code}: {message}" for code, message in contract_errors))
            validate_dynamic_end_marker(item, label)
            script_hash = item.get("script_sha256")
            previous_source = script_hash_sources.get(script_hash)
            require(previous_source in (None, source_id), f"{label} reuses an identical MQL script from source {previous_source}; compile a source-specific script")
            script_hash_sources[script_hash] = source_id
            query_shape = item.get("query_shape")
            require(query_shape in QUERY_SHAPES, f"{label}.query_shape must describe the executed MQL result shape")
            data_path_type = item.get("data_path_type")
            require(data_path_type in DATA_PATH_TYPES, f"{label}.data_path_type must be INDICATOR or REPORT")
            require(item.get("source_semantic_type") in SOURCE_SEMANTIC_TYPES, f"{label}.source_semantic_type is invalid")
            effective_orientation = item.get("mql_orientation", 1)
            require(effective_orientation in {0, 1}, f"{label}.mql_orientation must be 0 or 1 when supplied")
            require(isinstance(item.get("orientation_reason"), str) and item["orientation_reason"].strip(), f"{label}.orientation_reason is required")
            raw_result = item.get("raw_result")
            require(isinstance(raw_result, list) and raw_result and all(isinstance(row, list) and row for row in raw_result), f"{label}.raw_result must be a non-empty matrix")
            raw_width = len(raw_result[0])
            require(all(len(row) == raw_width for row in raw_result), f"{label}.raw_result must be rectangular")
            oriented_result = apply_mql_orientation(raw_result, effective_orientation)
            require(oriented_result == item.get("last_result"), f"{label}.last_result must equal raw_result after applying mql_orientation")
        last_result = item.get("last_result")
        require(isinstance(last_result, list) and len(last_result) == item["expected_rows"], f"{label}.last_result must match expected_rows")
        require(all(isinstance(row, list) and len(row) == item["expected_columns"] for row in last_result), f"{label}.last_result must be rectangular and match expected_columns")
        require(any(value not in (None, "") for row in last_result for value in row), f"{label}.last_result cannot be empty")
        require(all(value not in (None, "") for value in last_result[0]), f"{label}.last_result header row must be complete")
        # 数值有效性：表头与行标签非空不代表有真实数据，数值区全空（全 NULL）必须拦截
        require(
            any(value is not None and not (isinstance(value, str) and not value.strip())
                for row in last_result[1:] for value in row[1:]),
            f"{label}.last_result data body must not be entirely blank (all-NULL values are rejected)",
        )
        if data_source == "MQL":
            target_row_axis = item.get("target_row_axis")
            target_column_axis = item.get("target_column_axis")
            require(target_row_axis in AXIS_TYPES, f"{label}.target_row_axis is invalid")
            require(target_column_axis in AXIS_TYPES and target_column_axis != target_row_axis, f"{label}.target_column_axis is invalid")
            row_axis_labels = item.get("row_axis_labels")
            column_axis_labels = item.get("column_axis_labels")
            require(isinstance(row_axis_labels, list) and row_axis_labels, f"{label}.row_axis_labels must be non-empty")
            require(isinstance(column_axis_labels, list) and column_axis_labels, f"{label}.column_axis_labels must be non-empty")
            require([str(row[0]) for row in last_result[1:]] == [str(value) for value in row_axis_labels], f"{label}.last_result first column must match row_axis_labels after orientation")
            label_map = item.get("display_label_map")
            require(isinstance(label_map, list) and label_map, f"{label}.display_label_map is required before MQL generation")
            require(all(isinstance(value, dict) and value.get("key") not in (None, "") and isinstance(value.get("display_name"), str) and value["display_name"].strip() and value.get("kind") for value in label_map), f"{label}.display_label_map entries require key, display_name, and kind")
            row_entries, period_entries = split_display_label_map(label_map)
            row_display_names = [value["display_name"].strip() for value in row_entries]
            period_keys = [str(value["key"]).strip() for value in period_entries]
            period_display_names = [value["display_name"].strip() for value in period_entries]
            require(len(row_display_names) == len(set(row_display_names)), f"{label}.display_label_map display names must be unique")
            require(all(not looks_like_technical_code(value) for value in row_display_names), f"{label}.display_label_map must contain readable names, not only technical codes")
            require(len(period_keys) == len(set(period_keys)), f"{label} reporting-period mapping keys must be unique")
            require(len(period_display_names) == len(set(period_display_names)), f"{label} reporting-period display names must be unique")
            require(not (set(period_display_names) & set(row_display_names)), f"{label} reporting-period labels must not reuse row display names")
            require(all(looks_like_period_label(value) for value in period_display_names), f"{label} reporting-period display names must be recognizable period labels, not free text")
            if period_entries:
                require(target_column_axis == "REPORTING_PERIOD", f"{label}.display_label_map REPORTING_PERIOD entries require target_column_axis=REPORTING_PERIOD")
                require(len(period_entries) == len(column_axis_labels), f"{label}.display_label_map must map exactly the result period columns declared in column_axis_labels")
                require(period_display_names == [str(value) for value in column_axis_labels], f"{label}.display_label_map reporting-period names must equal column_axis_labels in column order")
                require([str(value) for value in last_result[0][1:]] == period_keys, f"{label}.last_result period headers must equal the mapped result labels in column order")
            else:
                require([str(value) for value in last_result[0][1:]] == [str(value) for value in column_axis_labels], f"{label}.last_result header must match column_axis_labels after orientation; declare display_label_map REPORTING_PERIOD entries when the executed result labels differ from the report labels")
            if target_row_axis in {"ENTITY", "CATEGORY"}:
                display_field = item.get("entity_display_name_field")
                if display_field:
                    require(display_field in last_result[0], f"{label}.entity_display_name_field must be an output column")
                    display_index = last_result[0].index(display_field)
                    require([str(row[display_index]) for row in last_result[1:]] == row_display_names, f"{label} output display-name column must match display_label_map")
                else:
                    technical_keys = [str(row[0]) for row in last_result[1:]]
                    require([str(value.get("key")) for value in row_entries] == technical_keys, f"{label}.display_label_map keys must match the technical row keys when no display-name field is returned")
            elif target_row_axis in {"METRIC", "FINANCIAL_METRIC"}:
                require([str(value) for value in row_axis_labels] == row_display_names, f"{label} metric rows must use readable display names")
            elif target_column_axis == "SERIES":
                require([str(value) for value in column_axis_labels] == row_display_names, f"{label} series columns must use readable display names")
            financial_matrix = item["source_semantic_type"] in {"FINANCIAL_STATEMENT", "FINANCIAL_METRICS"}
            if financial_matrix:
                require(target_row_axis == "FINANCIAL_METRIC" and target_column_axis == "REPORTING_PERIOD", f"{label} financial multi-period output must use metrics as rows and reporting periods as columns")
                require(query_shape == "REPORT_MATRIX", f"{label} financial source must produce a multi-period REPORT_MATRIX even when standard indicators are used")
                financial_query_mode = item.get("financial_query_mode")
                require(financial_query_mode in FINANCIAL_QUERY_MODES, f"{label}.financial_query_mode must describe how all reporting periods were queried")
                require(isinstance(item.get("financial_query_mode_evidence"), str) and item["financial_query_mode_evidence"].strip(), f"{label}.financial_query_mode_evidence is required")
                if financial_query_mode == "FINANCIAL_TIME_SERIES":
                    require("TimeSeriesBlock" in script, f"{label} FINANCIAL_TIME_SERIES requires a candidate-confirmed TimeSeriesBlock")
                    require("SetWindow" in script, f"{label} FINANCIAL_TIME_SERIES requires SetWindow for the reporting-period range")
                    require(item.get("indicator_time_shape") == "time_series", f"{label}.indicator_time_shape must be time_series for FINANCIAL_TIME_SERIES")
                    require("{市场类型}" not in script, f"{label} financial reporting-period SetWindow must not specify a trading market")
                if financial_query_mode == "PERIOD_BLOCK_MERGE":
                    prior_attempt_ids = item.get("prior_multi_period_attempt_ids")
                    require(isinstance(prior_attempt_ids, list) and prior_attempt_ids and all(isinstance(value, str) and value in execution_attempts for value in prior_attempt_ids), f"{label}.prior_multi_period_attempt_ids must reference failed native multi-period or financial time-series attempts")
                    prior_attempts = [execution_attempts[value] for value in prior_attempt_ids]
                    require(all(attempt.get("financial_query_mode") in {"NATIVE_MULTI_PERIOD", "FINANCIAL_TIME_SERIES"} for attempt in prior_attempts), f"{label}.prior_multi_period_attempt_ids must reference higher-priority financial query modes")
                    require(all(attempt.get("status") in {"FAILED", "NO_CANDIDATE", "NO_DATA", "PARTIAL"} and attempt.get("failure_category") not in (None, "") for attempt in prior_attempts), f"{label}.prior_multi_period_attempt_ids require structured failure evidence")
                if item["data_path_type"] == "REPORT":
                    require(financial_query_mode in {"REPORT_FULL_TABLE", "REPORT_FALLBACK"}, f"{label} REPORT data path requires financial_query_mode=REPORT_FULL_TABLE or REPORT_FALLBACK")
                    if financial_query_mode == "REPORT_FULL_TABLE":
                        # 整表报表直取：只需说明整表口径，不要求指标失败证据链
                        require(isinstance(item.get("report_selection_reason"), str) and item["report_selection_reason"].strip(), f"{label}.report_selection_reason is required for REPORT_FULL_TABLE")
                    else:
                        require(item.get("report_fallback_reason") in REPORT_FALLBACK_REASONS, f"{label}.report_fallback_reason must prove why standard financial indicators could not be used")
                        attempt_ids = item.get("indicator_attempt_ids")
                        require(isinstance(attempt_ids, list) and attempt_ids and all(isinstance(value, str) and value.strip() for value in attempt_ids), f"{label}.indicator_attempt_ids must reference real indicator attempts")
                        attempts = [execution_attempts.get(value) for value in attempt_ids]
                        require(all(attempt is not None for attempt in attempts), f"{label}.indicator_attempt_ids must exist in execution_log")
                        require(all(attempt.get("source_id") == source_id and attempt.get("data_path_type") == "INDICATOR" for attempt in attempts), f"{label}.indicator_attempt_ids must reference INDICATOR attempts for the same source")
                        require(all(attempt.get("status") in {"FAILED", "NO_CANDIDATE", "NO_DATA", "PARTIAL"} and attempt.get("failure_category") not in (None, "") for attempt in attempts), f"{label}.indicator_attempt_ids must reference failed or incomplete attempts with failure categories")
                        require(isinstance(item.get("report_selection_reason"), str) and item["report_selection_reason"].strip(), f"{label}.report_selection_reason is required for financial REPORT fallback")
                else:
                    require(financial_query_mode not in {"REPORT_FALLBACK", "REPORT_FULL_TABLE"}, f"{label} {financial_query_mode} cannot be used with an INDICATOR data path")
            if item["data_path_type"] == "REPORT":
                require("ReportBlock" in script, f"{label}.data_path_type REPORT requires ReportBlock in mql_script")
            else:
                require("ReportBlock" not in script, f"{label}.data_path_type INDICATOR cannot use ReportBlock")
            # [冒烟放宽 2026-10-12 / R1] 凡真实执行通过的 MQL 脚本（含服务端妙想路径）均可用于可刷新底稿，
            # excel_refresh_compatible 与服务端路径门禁均已移除，唯一写入门禁是真实执行成功。
            # require("服务端\\妙想服务" not in script and "服务端/妙想服务" not in script, f"{label} server-only MiaoXiang paths cannot be placed in a locally refreshable workpaper")
            if source_type == "CHART" and chart_by_id[source_id]["coordinate"]["time_series"]:
                require(item["query_shape"] == "TIME_SERIES", f"{label} continuous-time chart requires TIME_SERIES query_shape")
                require(has_continuous_time_series_block(script), f"{label} continuous-time chart requires TimeSeriesBlock or EdbBlock; interval cross-sections cannot replace a series")
                require(target_row_axis == "DATE" and target_column_axis == "SERIES", f"{label} time-series chart output must use DATE rows and SERIES columns")
                for field in ("source_start_date", "source_end_date", "query_start_date", "query_end_date", "observation_frequency", "axis_tick_frequency", "frequency_evidence"):
                    require(item.get(field) not in (None, ""), f"{label}.{field} is required for time-series mapping")
                validate_time_series_window(item, label)
                if item.get("window_policy") != "LATEST_1000_TRADING_DAYS":
                    if dynamic_end_marker(item):
                        require(item["source_start_date"] == item["query_start_date"] and item["source_end_date"] == item["query_end_date"], f"{label} dynamic-window generation snapshot must equal the source chart range; query_end_date records the generation-time resolved date")
                    else:
                        require(item["source_start_date"] == item["query_start_date"] and item["source_end_date"] == item["query_end_date"], f"{label} query date range must cover the source chart range exactly")
                require(item["observation_frequency"] in OBSERVATION_FREQUENCIES, f"{label}.observation_frequency is invalid")
                require(isinstance(item.get("expected_min_points"), int) and item["expected_min_points"] >= 2, f"{label}.expected_min_points must be at least 2")
                require(isinstance(item.get("temporal_point_count"), int) and item["temporal_point_count"] >= item["expected_min_points"], f"{label}.temporal_point_count is below expected_min_points")
                require(item["temporal_point_count"] == len(row_axis_labels), f"{label}.temporal_point_count must match date rows")
                if item["observation_frequency"] == "DAILY_TRADING":
                    require(item["expected_min_points"] >= 100, f"{label} annual-like daily trading charts cannot be compressed to monthly endpoints")
        selector = item.get("block_selector")
        require(selector in (None, "") or (isinstance(selector, str) and BLOCK_SELECTOR.fullmatch(selector)), f"{label}.block_selector must look like #2")
        if data_source == "MQL" and selector:
            require(int(selector[1:]) in block_numbers, f"{label}.block_selector must reference a Block defined in mql_script")
        if data_source == "MQL" and item.get("financial_query_mode") == "FINANCIAL_TIME_SERIES":
            require(block_numbers == [1] and selector == "#1", f"{label} each financial statement must use an independent single #1 Block and anchor")
        if data_source == "MQL" and "mql_orientation" in item:
            require(selector not in (None, ""), f"{label}.block_selector is required when mql_orientation is explicitly supplied")
        if data_source == "MX_DS_MCP":
            require(selector in (None, ""), f"{label}.block_selector is not allowed for MX_DS_MCP")
            validate_mql_fallback(item, label)
        edb_time_series = (
            is_edb_workpaper(item)
            and item.get("query_shape") == "TIME_SERIES"
            and item.get("source_semantic_type") not in FINANCIAL_SOURCE_TYPES
        )
        # R06：删除「FULL 必须与快照行列数/表头/行标签完全相同」的一般规则。
        # 底稿按实际成功结果输出，形状只与自身 expected_* 及 cached_table 自洽；
        # 来源是否被完整覆盖改由来源级目标数据单元汇总验收（见下方 source coverage）。
        cached_table = item.get("cached_table")
        require(isinstance(cached_table, list) and len(cached_table) == item["expected_rows"], f"{label}.cached_table must match expected_rows")
        require(all(isinstance(row, list) and len(row) == item["expected_columns"] for row in cached_table), f"{label}.cached_table must match expected_columns")
        if source_type == "TABLE":
            # R06：锚点只声明自己本次取得的目标单元；真实缺失在来源汇总层统一计算。
            source_fields = item.get("source_fields")
            covered_fields = item.get("covered_fields")
            omitted_fields = item.get("omitted_fields", [])
            require(isinstance(source_fields, list) and source_fields and all(isinstance(value, str) and value.strip() for value in source_fields), f"{label}.source_fields must list this anchor's target source fields")
            require(len(set(source_fields)) == len(source_fields), f"{label}.source_fields must be unique")
            require(set(source_fields) <= set(snapshot["queryable_fields"]), f"{label}.source_fields must stay within the source snapshot queryable_fields")
            require(isinstance(covered_fields, list) and all(value in source_fields for value in covered_fields), f"{label}.covered_fields must be a subset of this anchor's source_fields")
            require(isinstance(omitted_fields, list) and all(isinstance(value, dict) and value.get("field") in source_fields and value.get("reason") for value in omitted_fields), f"{label}.omitted_fields must provide a reason for every omitted source field of this anchor")
            omitted_names = [value["field"] for value in omitted_fields]
            require(len(set(covered_fields)) == len(covered_fields) and len(set(omitted_names)) == len(omitted_names), f"{label} coverage fields must be unique")
            require(set(covered_fields).isdisjoint(omitted_names) and set(covered_fields) | set(omitted_names) == set(source_fields), f"{label} covered_fields and omitted_fields must partition this anchor's source_fields")
            if item.get("mapping_status") == "FULL":
                require(covered_fields == source_fields and not omitted_fields, f"{label} FULL mapping requires this anchor to cover all of its target source fields")
            if data_source == "MQL" and execution_status == "SUCCESS" and snapshot["source_semantic_type"] != "COMPARABLE_COMPANY_TABLE" and not edb_time_series:
                require(item.get("script_output_fields") == covered_fields, f"{label}.script_output_fields must exactly equal covered_fields in source order; unrelated outputs are forbidden")
            # R06：不再要求目标轴等于快照轴。底稿按实际成功结果输出，允许合约长表、品种矩阵、
            # 分市场表、分部表与多锚点；版式/表头/简称差异不得单独判 PARTIAL。财务来源的
            # FINANCIAL_METRIC × REPORTING_PERIOD 语义仍在下文强制保留。
            if edb_time_series:
                require(item["mapping_status"] == "PARTIAL", f"{label} EdbBlock fallback for a non-time-series source must be PARTIAL")
                require(item.get("target_row_axis") == "DATE" and item.get("target_column_axis") == "SERIES", f"{label} EdbBlock fallback must emit DATE x SERIES")
            source_periods = item.get("source_periods")
            covered_periods = item.get("covered_periods")
            omitted_periods = item.get("omitted_periods", [])
            require(isinstance(source_periods, list) and all(isinstance(value, str) and value.strip() for value in source_periods), f"{label}.source_periods must list this anchor's target ACTUAL periods")
            require(len(set(source_periods)) == len(source_periods), f"{label}.source_periods must be unique")
            require(set(source_periods) <= set(snapshot["source_periods"]), f"{label}.source_periods must stay within the source snapshot ACTUAL periods")
            require(isinstance(covered_periods, list) and all(value in source_periods for value in covered_periods), f"{label}.covered_periods must be a subset of this anchor's source_periods")
            require(isinstance(omitted_periods, list) and all(
                isinstance(value, dict)
                and value.get("period") in source_periods
                and isinstance(value.get("reason"), str) and value["reason"].strip()
                and isinstance(value.get("evidence_ids"), list) and value["evidence_ids"]
                and all(evidence_id in execution_attempts for evidence_id in value["evidence_ids"])
                for value in omitted_periods
            ), f"{label}.omitted_periods must provide reason and execution attempt evidence for every omitted period")
            omitted_period_names = [value["period"] for value in omitted_periods]
            require(len(set(covered_periods)) == len(covered_periods) and len(set(omitted_period_names)) == len(omitted_period_names), f"{label} period coverage values must be unique")
            require(set(covered_periods).isdisjoint(omitted_period_names) and set(covered_periods) | set(omitted_period_names) == set(source_periods), f"{label} covered_periods and omitted_periods must partition source_periods")
            if snapshot.get("source_segments"):
                source_segment_names = [str(value["segment"]) for value in snapshot["source_segments"]]
                segment_roles = {str(value["segment"]): str(value["role"]) for value in snapshot["source_segments"]}
                covered_segments = item.get("covered_segments")
                omitted_segments = item.get("omitted_segments", [])
                require(isinstance(covered_segments, list) and all(value in source_segment_names for value in covered_segments), f"{label}.covered_segments must list this anchor's covered source segments")
                require(isinstance(omitted_segments, list) and all(
                    isinstance(value, dict)
                    and value.get("segment") in source_segment_names
                    and isinstance(value.get("reason"), str) and value["reason"].strip()
                    and isinstance(value.get("evidence_ids"), list) and value["evidence_ids"]
                    and all(evidence_id in execution_attempts for evidence_id in value["evidence_ids"])
                    for value in omitted_segments
                ), f"{label}.omitted_segments must provide reason and execution attempt evidence for every omitted segment")
                omitted_segment_names = [value["segment"] for value in omitted_segments]
                require(len(set(covered_segments)) == len(covered_segments) and len(set(omitted_segment_names)) == len(omitted_segment_names), f"{label} segment coverage values must be unique")
                require(set(covered_segments).isdisjoint(omitted_segment_names) and set(covered_segments) | set(omitted_segment_names) == set(source_segment_names), f"{label} covered_segments and omitted_segments must partition source_segments")
                if item.get("mapping_status") == "FULL":
                    require(not omitted_segments, f"{label} FULL mapping forbids omitting any source segment")
                gaps = segment_value_gaps(item, covered_segments, segment_roles)
                require(not gaps, f"{label} covered detail segments lack valid values for covered numeric fields; a TOTAL row must not substitute DETAIL coverage: {sorted(gaps)}")
            if item["source_semantic_type"] in FINANCIAL_SOURCE_TYPES:
                require(item.get("target_row_axis") == "FINANCIAL_METRIC" and item.get("target_column_axis") == "REPORTING_PERIOD", f"{label} financial source cannot be emitted as an entity cross-section")
                require([str(value) for value in item.get("column_axis_labels", [])] == [str(value) for value in covered_periods], f"{label} financial result columns must equal covered_periods in order")
        if source_type == "TABLE" and item.get("source_semantic_type") == "COMPARABLE_COMPANY_TABLE":
            comparable_workpaper_groups.setdefault(source_id, []).append(item)
            singular_by_dimension = {"entities": "entity", "periods": "period", "metrics": "metric"}
            for dimension in ("entities", "periods", "metrics"):
                source_values = item.get(f"source_{dimension}")
                covered_values = item.get(f"covered_{dimension}")
                omitted_values = item.get(f"omitted_{dimension}", [])
                require(isinstance(source_values, list) and source_values, f"{label}.source_{dimension} is required")
                require(isinstance(covered_values, list) and set(covered_values) <= set(source_values), f"{label}.covered_{dimension} must be a subset")
                key = singular_by_dimension[dimension]
                require(isinstance(omitted_values, list) and all(isinstance(value, dict) and value.get(key) in source_values and value.get("reason") for value in omitted_values), f"{label}.omitted_{dimension} must include source value and reason")
                omitted_names = {value[key] for value in omitted_values}
                require(set(covered_values).isdisjoint(omitted_names) and set(covered_values) | omitted_names == set(source_values), f"{label} {dimension} coverage must partition the source")
        if data_source == "MQL":
            require(item["expected_rows"] == len(cached_table), f"{label}.MQL result rows must cover the complete cached table")
            require(item["expected_columns"] == len(cached_table[0]), f"{label}.MQL result columns must cover the complete cached table")
            require([str(value) for value in last_result[0]] == [str(value) for value in cached_table[0]], f"{label}.MQL result headers must exactly match cached_table headers")
            require([str(row[0]) for row in last_result[1:]] == [str(row[0]) for row in cached_table[1:]], f"{label}.MQL result row labels must exactly match cached_table row labels")
            for row_index, (actual_row, cached_row) in enumerate(zip(last_result, cached_table)):
                for column_index, (actual, cached) in enumerate(zip(actual_row, cached_row)):
                    same_numeric = (
                        isinstance(actual, (int, float)) and not isinstance(actual, bool)
                        and isinstance(cached, (int, float)) and not isinstance(cached, bool)
                        and actual == cached
                    )
                    require(
                        (type(actual) is type(cached) and actual == cached) or same_numeric,
                        f"{label}.last_result[{row_index}][{column_index}] must equal cached_table cell by cell with the same value type; static patching is forbidden",
                    )
        require(item.get("mql_orientation", 1) in {0, 1}, f"{label}.mql_orientation must be 0 or 1 when supplied")
        if source_type == "CHART" and data_source == "MQL":
            successful_chart_workpapers.setdefault(source_data_block_id, []).append(item)
    require(table_workpaper_ids == snapshot_ids, "TABLE workpaper groups must cover snapshots in the same order; one source may contain multiple anchors")

    # R06/R07：来源级覆盖汇总不变量。E=来源计划目标单元集（快照 queryable_fields / ACTUAL 期间 /
    # 分部 source_segments），S=∪各锚点有效单元，O=∪各锚点终止缺失单元；要求 S⊆E、O⊆E、S∩O=∅、S∪O=E。
    # 已在锚点 B 成功的字段不得写成锚点 A 的真实 omitted_fields（否则 S∩O 非空直接失败）。
    source_field_coverage: dict[str, dict[str, set[str]]] = {}
    source_period_coverage: dict[str, dict[str, set[str]]] = {}
    source_segment_coverage: dict[str, dict[str, set[str]]] = {}
    for item in payload["workpapers"]:
        if item.get("source_type") != "TABLE" or item.get("execution_status") not in {"SUCCESS", "TABLE_BLOCKED"}:
            continue
        source_id = item["source_id"]
        fields = source_field_coverage.setdefault(source_id, {"covered": set(), "omitted": set()})
        fields["covered"].update(str(value) for value in item.get("covered_fields", []))
        fields["omitted"].update(str(value.get("field")) for value in item.get("omitted_fields", []) if isinstance(value, dict) and value.get("field"))
        periods = source_period_coverage.setdefault(source_id, {"covered": set(), "omitted": set()})
        periods["covered"].update(str(value) for value in item.get("covered_periods", []))
        periods["omitted"].update(str(value.get("period")) for value in item.get("omitted_periods", []) if isinstance(value, dict) and value.get("period"))
        segments = source_segment_coverage.setdefault(source_id, {"covered": set(), "omitted": set()})
        segments["covered"].update(str(value) for value in item.get("covered_segments", []))
        segments["omitted"].update(str(value.get("segment")) for value in item.get("omitted_segments", []) if isinstance(value, dict) and value.get("segment"))
    for source_id in table_workpaper_ids:
        snapshot = snapshot_by_id[source_id]
        for noun, unit, target_values in (
            ("field", source_field_coverage, snapshot["queryable_fields"]),
            ("period", source_period_coverage, snapshot["source_periods"]),
            ("segment", source_segment_coverage, [value["segment"] for value in snapshot.get("source_segments", [])]),
        ):
            target = {str(value) for value in target_values}
            bucket = unit.get(source_id, {"covered": set(), "omitted": set()})
            covered, omitted = bucket["covered"], bucket["omitted"]
            require(covered <= target, f"source {source_id} covered {noun}s must stay within the source target units {sorted(covered - target)}")
            require(omitted <= target, f"source {source_id} omitted {noun}s must stay within the source target units {sorted(omitted - target)}")
            require(not (covered & omitted), f"source {source_id} already-covered {noun}s cannot also be recorded as omitted: {sorted(covered & omitted)}")
            require(covered | omitted == target, f"source {source_id} coverage must account for every source {noun}; unaccounted {sorted(target - covered - omitted)}")

    for source_id, items in comparable_workpaper_groups.items():
        source_entities = items[0].get("source_entities")
        market_errors = validate_market_group(items, source_entities if isinstance(source_entities, list) else None)
        require(not market_errors, f"cross-market source {source_id} failed: " + "; ".join(f"{code}: {message}" for code, message in market_errors))

    for data_block_id, block in chart_data_by_id.items():
        label = f"chart_data[{data_block_id}]"
        successful = successful_chart_workpapers.get(data_block_id, [])
        status = block["mql_mapping_status"]
        source_metrics = {str(row[0]) for row in block["rows"] if row and row[0] not in (None, "")}
        covered = {metric for item in successful for metric in item.get("covered_metrics", [])}
        omitted = set(block.get("omitted_metrics", []))
        require(covered <= source_metrics, f"{label} covered_metrics must use source row labels")
        require(omitted <= source_metrics, f"{label}.omitted_metrics must use source row labels")
        if status == "FULL":
            require(successful, f"{label} FULL mapping requires a successful CHART MQL workpaper")
            require(covered == source_metrics, f"{label} FULL mapping must cover every source metric")
        elif status == "PARTIAL":
            require(successful and covered, f"{label} PARTIAL mapping requires a successful CHART MQL workpaper")
            require(covered | omitted == source_metrics and not (covered & omitted), f"{label} PARTIAL covered and omitted metrics must partition source metrics")
        else:
            require(not successful, f"{label} {status} cannot have a successful CHART MQL workpaper")
            if status == "NO_MATCH":
                category = block.get("mql_failure_category")
                require(category in MQL_FALLBACK_FAILURES, f"{label}.mql_failure_category must be terminal; correctable MQL routing errors cannot end as NO_MATCH")
                validate_service_fault(block, label)
                require(isinstance(block.get("mql_failure_evidence"), str) and block["mql_failure_evidence"].strip(), f"{label}.mql_failure_evidence is required for NO_MATCH")

    successful_chart_blocks = set(successful_chart_workpapers)
    logged_mql_run_ids: set[str] = set()
    for index, item in enumerate(payload["execution_log"]):
        label = f"execution_log[{index}]"
        if item.get("data_source") == "MQL" and item.get("status") in {"OK", "SUCCESS"}:
            for field in ("metric", "source_block", "query_path", "execution_run_id", "queried_at", "raw_result_summary", "unit", "script_sha256"):
                require(item.get(field) not in (None, ""), f"{label}.{field} is required for successful MQL audit records")
            require(isinstance(item["source_block"], str) and BLOCK_SELECTOR.fullmatch(item["source_block"]), f"{label}.source_block must look like #2")
            require(item["execution_run_id"] not in logged_mql_run_ids, f"{label}.execution_run_id must be unique")
            logged_mql_run_ids.add(item["execution_run_id"])
            if item.get("source_data_block_id"):
                require(item["source_data_block_id"] in successful_chart_blocks, f"{label} records successful chart MQL without a matching workpaper")
    require(successful_mql_run_ids <= logged_mql_run_ids, "every successful MQL workpaper must have a complete execution_log record with the same execution_run_id")

    for index, item in enumerate(payload["verification"]):
        label = f"verification[{index}]"
        require(isinstance(item, dict), f"{label} must be an object")
        for field in ("metric", "period", "unit", "source_location"):
            require(item.get(field) not in (None, ""), f"{label}.{field} is required")
        report_value = item.get("report_value")
        choice_value = item.get("verified_value", item.get("choice_value"))
        if "verified_value" in item and "choice_value" in item:
            require(item["verified_value"] == item["choice_value"], f"{label}.verified_value must equal choice_value when both are supplied")
        difference = item.get("difference")
        source_block = item.get("source_block")
        data_source = normalize_data_source(item.get("data_source", "MQL"), label)
        item["data_source"] = data_source
        require(bool(item.get("query_interface")) or data_source == "MQL", f"{label}.query_interface is required for MX_DS_MCP")
        if data_source == "MX_DS_MCP":
            require(not item.get("query_script"), f"{label}.query_script is not allowed for MX_DS_MCP")
            require(source_block in (None, ""), f"{label}.source_block is not allowed for MX_DS_MCP")
            numeric_pair = all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (report_value, choice_value))
            if numeric_pair:
                validate_mql_fallback(item, label)
            if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (report_value, choice_value)):
                require(bool(item.get("report_excerpt")), f"{label}.report_excerpt is required for non-numeric MX_DS_MCP verification")
        require(source_block in (None, "") or (isinstance(source_block, str) and BLOCK_SELECTOR.fullmatch(source_block)), f"{label}.source_block must look like #2")
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (report_value, choice_value)):
            require(isinstance(difference, (int, float)) and not isinstance(difference, bool), f"{label}.difference is required for two numeric values")
            require(math.isclose(difference, choice_value - report_value, rel_tol=1e-9, abs_tol=1e-9), f"{label}.difference must equal choice_value - report_value")


def load_payload(input_path: Path) -> dict[str, Any]:
    with input_path.open("r", encoding="utf-8") as input_file:
        payload = json.load(input_file)
    require(isinstance(payload, dict), "JSON root must be an object")
    payload.setdefault("excluded_tables", [])
    payload.setdefault("chart_snapshots", [])
    payload.setdefault("chart_data", [])
    payload.setdefault("workpapers", [])
    payload.setdefault("verification", [])
    payload.setdefault("forecast", {})
    payload.setdefault("execution_log", [])
    validate_payload(payload)
    return payload


def style_header(worksheet: Any, row: int, column_count: int) -> None:
    for column in range(1, column_count + 1):
        cell = worksheet.cell(row=row, column=column)
        cell.fill = HEADER_FILL
        cell.font = WHITE_FONT
        cell.alignment = CENTER


def style_section(worksheet: Any, row: int, title: str, column_count: int) -> None:
    column_count = max(column_count, 8)
    worksheet.cell(row=row, column=1, value=title)
    if column_count > 1:
        worksheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=column_count)
    cell = worksheet.cell(row=row, column=1)
    cell.fill = SECTION_FILL
    cell.font = BOLD_FONT
    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    worksheet.row_dimensions[row].height = max(24, 18 * math.ceil(len(title) / 70))


def write_table(worksheet: Any, start_row: int, headers: list[str], rows: list[list[Any]], bold_rows: list[bool] | None = None) -> int:
    for column, header in enumerate(headers, start=1):
        worksheet.cell(row=start_row, column=column, value=header)
    style_header(worksheet, start_row, len(headers))
    for row_index, row_values in enumerate(rows, start=start_row + 1):
        for column, value in enumerate(row_values, start=1):
            cell = worksheet.cell(row=row_index, column=column, value=value)
            cell.alignment = RIGHT if isinstance(value, (int, float)) and not isinstance(value, bool) else WRAP
            if bold_rows and bold_rows[row_index - start_row - 1]:
                cell.font = BOLD_FONT
    return start_row + len(rows)


def format_snapshot_values(worksheet: Any, header_row: int, table: dict[str, Any]) -> None:
    """Keep values numeric and preserve the report's leading-minus convention."""
    for offset, source_row in enumerate(table["rows"], start=1):
        label = str(source_row[0])
        percent_row = "%" in label or label in {"绝对升幅", "相对指数", "净负债率"}
        for column, value in enumerate(source_row[1:], start=2):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            cell = worksheet.cell(header_row + offset, column)
            if percent_row:
                cell.number_format = '0.0\\%;-0.0\\%;0.0\\%'
            elif isinstance(value, int):
                cell.number_format = '#,##0;-#,##0;0'
            else:
                cell.number_format = '#,##0.00;-#,##0.00;0.00'
            cell.alignment = RIGHT


def set_widths(worksheet: Any, widths: dict[int, int]) -> None:
    for column, width in widths.items():
        worksheet.column_dimensions[get_column_letter(column)].width = width


def mql_formula(orientation: int | None = None, scalar: bool = False, selector: str | None = None) -> str:
    require(orientation in {None, 0, 1}, "orientation must be 0, 1, or omitted")
    if orientation is None:
        call = f'mql("{selector}")' if selector else "mql()"
    else:
        require(bool(selector), "selector is required when orientation is explicitly supplied")
        call = f'mql("{selector}",{orientation})'
    return f"=INDEX({call},2,1)" if scalar else f"={call}"


def build_guide_sheet(workbook: Workbook, guide: dict[str, Any], included: int, excluded: int, charts: int) -> None:
    worksheet = workbook.active
    worksheet.title = "00_导读"
    worksheet.sheet_view.showGridLines = False
    worksheet["A1"] = "研报底稿抽取"
    worksheet["A1"].font = Font(size=16, bold=True)
    details = [
        ("标的公司", guide["company_name"]), ("证券代码", guide["security_code"]),
        ("研报标题", guide["report_title"]), ("研报发布日期", guide["report_date"]),
        ("核验基准日", guide["verification_date"]), ("PDF 页数", guide["pdf_page_count"]),
        ("普查表格数", guide["census_table_count"]), ("纳入表格数", included),
        ("排除表格数", excluded), ("纳入图表数", charts),
        ("历史实际数据说明", guide.get("actual_summary", "仅历史实际数据纳入准确度评价。")),
        ("分析师预测说明", guide.get("forecast_summary", "预测值仅进行框架和自洽性分析。")),
        ("刷新说明", "20_研报底稿只保留 MQL 公式；安装 Choice Excel 加载项并刷新后显示结果。未安装加载项时请查看10_研报快照。"),
        ("备注", guide.get("notes", "")),
    ]
    write_table(worksheet, 3, ["项目", "内容"], [[key, value] for key, value in details])
    for row in worksheet.iter_rows(min_row=1, max_row=worksheet.max_row, min_col=1, max_col=2):
        for cell in row:
            cell.alignment = LEFT
    worksheet.freeze_panes = "A4"
    set_widths(worksheet, {1: 24, 2: 100})


def build_snapshot_sheet(workbook: Workbook, snapshots: list[dict[str, Any]], chart_snapshots: list[dict[str, Any]], chart_data: list[dict[str, Any]]) -> None:
    worksheet = workbook.create_sheet("10_研报快照")
    worksheet.sheet_view.showGridLines = False
    current_row = 1

    def write_snapshot_table(table: dict[str, Any], row: int, paired: bool = False) -> int:
        headers = [str(value) for value in table["headers"]]
        suffix = " | 同图解析表格" if paired else ""
        style_section(worksheet, row, f'{table["table_id"]} | {table["table_name"]}{suffix}', len(headers))
        row += 1
        metadata = (
            ("页码", table["page"]), ("单位", table.get("unit", "")), ("空间区域", json.dumps(table["bbox"])),
            ("版面位置", f'{table["layout_group"]} / {table["lane"]} / {table["reading_order"]}'),
            ("表格审计", f'行数 {table["source_row_count"]}；数值令牌 {table["source_numeric_token_count"]}；回读 {table["visual_check"]}'),
        )
        for label, value in metadata:
            worksheet.cell(row, 1, label).font = BOLD_FONT
            worksheet.cell(row, 1).alignment = LEFT
            worksheet.cell(row, 2, value).alignment = LEFT
            row += 1
        header_row = row
        row = write_table(worksheet, row, headers, table["rows"], table.get("row_bold")) + 2
        format_snapshot_values(worksheet, header_row, table)
        return row

    chart_data_by_chart: dict[str, list[dict[str, Any]]] = {}
    for block in chart_data:
        chart_data_by_chart.setdefault(block["chart_id"], []).append(block)
    snapshot_by_id = {table["table_id"]: table for table in snapshots}
    paired_ids = {table_id for chart in chart_snapshots for table_id in chart.get("parsed_table_ids", [])}

    def write_chart_group(chart: dict[str, Any], row: int) -> int:
        style_section(worksheet, row, f'{chart["chart_id"]} | {chart.get("chart_no", "")} | {chart["title"]}', 8)
        row += 1
        metadata = (
            ("页码", chart["page"]), ("资料来源", chart.get("source", "")),
            ("空间区域(pt)", json.dumps(chart["bbox_pt"], ensure_ascii=False)),
            ("序列", "、".join(str(value) for value in chart.get("serial", []))),
            ("频率", chart.get("frequency", "")),
            ("截图审计", f'标题/footer {chart["header_footer_ok"]}；视觉复核 {chart["visual_check"]}'),
        )
        for label, value in metadata:
            worksheet.cell(row, 1, label).font = BOLD_FONT
            worksheet.cell(row, 1).alignment = LEFT
            worksheet.cell(row, 2, value).alignment = LEFT
            row += 1
        snapshot_path = Path(chart["snapshot_path"])
        with PILImage.open(snapshot_path) as source_image:
            width, height = source_image.size
        scale = min(1.0, 720 / width, 520 / height)
        excel_image = XLImage(str(snapshot_path))
        excel_image.width = round(width * scale)
        excel_image.height = round(height * scale)
        anchor = f"A{row}"
        worksheet.add_image(excel_image, anchor)
        row += math.ceil(excel_image.height / 20) + 2
        for table_id in chart.get("parsed_table_ids", []):
            row = write_snapshot_table(snapshot_by_id[table_id], row, paired=True)
        for block in chart_data_by_chart.get(chart["chart_id"], []):
            headers = [str(value) for value in block["headers"]]
            style_section(worksheet, row, f'{block["data_block_id"]} | 图表双通道验收 | {block.get("title", chart["title"])}', len(headers))
            row += 1
            metadata = (
                ("单位", block.get("unit", "")), ("抽取方法", block["extraction_method"]),
                ("置信状态", block["confidence_status"]), ("候选来源", block["candidate_source"]),
                ("视觉验收", block["visual_validation"]), ("来源说明", block["source_note"]),
            )
            for label, value in metadata:
                worksheet.cell(row, 1, label).font = BOLD_FONT
                worksheet.cell(row, 1).alignment = LEFT
                worksheet.cell(row, 2, value).alignment = LEFT
                row += 1
            row = write_table(worksheet, row, headers, block["rows"]) + 2
        return row

    groups: list[tuple[tuple[int, int, int], str, dict[str, Any]]] = []
    for table in snapshots:
        if table["table_id"] not in paired_ids:
            groups.append(((table["page"], table.get("reading_order", 9999), 0), "TABLE", table))
    for chart in chart_snapshots:
        paired_orders = [snapshot_by_id[table_id].get("reading_order", 9999) for table_id in chart.get("parsed_table_ids", [])]
        order = min(paired_orders) if paired_orders else chart.get("api_block_index", 9999)
        groups.append(((chart["page"], order, 1), "CHART", chart))
    for _, group_type, item in sorted(groups, key=lambda value: value[0]):
        current_row = write_snapshot_table(item, current_row) if group_type == "TABLE" else write_chart_group(item, current_row)
    worksheet.freeze_panes = "A2"
    set_widths(worksheet, {1: 28, 2: 20, 3: 18, 4: 18, 5: 18, 6: 18, 7: 18, 8: 18})


def write_isolated_anchor_sheet(workbook: Workbook, sheet_name: str, section_label: str, source_id: str, source_title: str, source_page: Any, source_unit: str, item: dict[str, Any], anchor_label: str, note_text: str, extra_metadata: tuple[tuple[str, Any], ...] = ()) -> None:
    """Write an anchor whose refresh output may grow onto its own sheet; nothing sits below it."""
    sheet = workbook.create_sheet(sheet_name)
    style_section(sheet, 1, f'{source_id} | {section_label} | {source_title}', max(8, len(item["last_result"][0])))
    metadata = (
        ("来源ID", source_id), ("页码", source_page), ("单位", source_unit),
        ("映射状态", item.get("mapping_status", "")), ("映射说明", item.get("mapping_note", "")),
    ) + extra_metadata
    row = 2
    for label, value in metadata:
        sheet.cell(row, 1, label).font = BOLD_FONT
        sheet.cell(row, 1).alignment = LEFT
        sheet.cell(row, 2, value).alignment = LEFT
        row += 1
    sheet.cell(row, 1, anchor_label).font = BOLD_FONT
    row += 1
    anchor = sheet.cell(row, 1, mql_formula(item.get("mql_orientation"), False, item.get("block_selector")))
    anchor.comment = Comment(item["mql_script"], "research-report-review")
    anchor.fill = YELLOW_FILL
    anchor.font = BOLD_FONT
    sheet.cell(row, 2, note_text).alignment = NOWRAP
    sheet.freeze_panes = f"A{row + 1}"
    set_widths(sheet, {1: 28, 2: 90, 3: 18, 4: 18, 5: 18, 6: 18, 7: 18, 8: 18})


def build_workpaper_sheet(workbook: Workbook, snapshots: list[dict[str, Any]], workpapers: list[dict[str, Any]], chart_snapshots: list[dict[str, Any]]) -> None:
    worksheet = workbook.create_sheet("20_研报底稿")
    worksheet.sheet_view.showGridLines = False
    current_row = 1
    snapshot_by_id = {item["table_id"]: item for item in snapshots}
    chart_by_id = {item["chart_id"]: item for item in chart_snapshots}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in workpapers:
        source_type = item.get("source_type")
        source_id = item.get("source_id")
        grouped.setdefault((source_type, source_id), []).append(item)

    edb_sheet_index = 0
    ts_sheet_index = 0
    for (source_type, source_id), items in grouped.items():
        first = items[0]
        if source_type == "TABLE":
            source = snapshot_by_id[source_id]
            source_title = first.get("table_name", source["table_name"])
            source_page = source["page"]
            source_unit = source.get("unit", "")
        else:
            source = chart_by_id[source_id]
            source_title = first.get("table_name", source["title"])
            source_page = source["page"]
            source_unit = first.get("unit", "")
        successful_mql = [
            item for item in items
            if item.get("execution_status") == "SUCCESS"
            and item.get("data_source", "MQL") == "MQL"
            and not is_edb_workpaper(item)
        ]
        columns = max(8, max((len(item["last_result"][0]) for item in successful_mql), default=2))
        style_section(worksheet, current_row, f'{source_id} | {source_type} | {source_title}', columns)
        current_row += 1
        metadata = (
            ("来源ID", source_id), ("页码", source_page), ("单位", source_unit),
            ("可刷新锚点数", len(items)),
        )
        # 加载项按 MQL 返回值写列头，因此刷新后期间列显示的是取数原生标签；这里把
        # 「研报期间标签 ← 取数期间标签」的对应关系写入元数据行，使研报标签在底稿中可见。
        for period_entry in period_label_map_entries(first):
            metadata += (("期间标签映射", f'{period_entry["display_name"]} ← {period_entry["key"]}'),)
        for label, value in metadata:
            worksheet.cell(current_row, 1, label).font = BOLD_FONT
            worksheet.cell(current_row, 1).alignment = LEFT
            worksheet.cell(current_row, 2, value).alignment = LEFT
            current_row += 1
        for anchor_index, item in enumerate(items, start=1):
            anchor_label = item.get("anchor_label") or f'锚点{anchor_index} · {item["mapping_id"]}'
            worksheet.cell(current_row, 1, anchor_label).font = BOLD_FONT
            if is_edb_workpaper(item):
                edb_sheet_index += 1
                sheet_name = f"21_EDB_{edb_sheet_index:03d}"
                link = worksheet.cell(current_row, 2, f"打开独立 EDB 时序 Sheet：{sheet_name}")
                link.hyperlink = f"#'{sheet_name}'!A1"
                link.style = "Hyperlink"
                link.alignment = LEFT
                write_isolated_anchor_sheet(workbook, sheet_name, "EDB", source_id, source_title, source_page, source_unit, item, anchor_label, "安装Choice加载项并刷新后，EDB时序从下一行开始溢出；本Sheet下方不放置其他内容。")
                current_row += 2
                continue
            if is_dynamic_timeseries_workpaper(item):
                ts_sheet_index += 1
                sheet_name = f"22_TS_{ts_sheet_index:03d}"
                link = worksheet.cell(current_row, 2, f"打开独立动态时序 Sheet：{sheet_name}")
                link.hyperlink = f"#'{sheet_name}'!A1"
                link.style = "Hyperlink"
                link.alignment = LEFT
                write_isolated_anchor_sheet(workbook, sheet_name, "动态时序", source_id, source_title, source_page, source_unit, item, anchor_label, "安装Choice加载项并刷新后，时序从下一行开始溢出并自动延伸到最新；本Sheet下方不放置其他内容。", extra_metadata=(("动态结束时间", item["query_end_date_dynamic"]), ("生成时基线", f'截至 {item.get("query_end_date", "")}（取数时间 {item.get("result_as_of", "")}）')))
                current_row += 2
                continue
            worksheet.cell(current_row, 2, item.get("mapping_note", "")).alignment = LEFT
            current_row += 1
            if item.get("execution_status") == "SUCCESS" and item.get("data_source", "MQL") == "MQL":
                anchor = worksheet.cell(current_row, 1, mql_formula(item.get("mql_orientation"), False, item.get("block_selector")))
                anchor.comment = Comment(item["mql_script"], "research-report-review")
                anchor.fill = YELLOW_FILL
                anchor.font = BOLD_FONT
                worksheet.cell(current_row, 2, "安装Choice加载项并刷新后，本锚点结果将从下一行开始显示；生成文件不预填静态结果。").alignment = NOWRAP
                current_row += len(item["last_result"]) + 3
            else:
                worksheet.cell(current_row, 1, "状态").font = BOLD_FONT
                worksheet.cell(current_row, 2, item.get("execution_status") or item.get("mapping_status") or "未完成")
                worksheet.cell(current_row + 1, 1, "原因").font = BOLD_FONT
                worksheet.cell(current_row + 1, 2, item.get("block_reason") or item.get("mapping_note") or "")
                current_row += 3
        current_row += 1
    worksheet.freeze_panes = "A2"
    set_widths(worksheet, {1: 28, 2: 20, 3: 18, 4: 18, 5: 18, 6: 18, 7: 18, 8: 18})


def build_forecast_sheet(workbook: Workbook, forecast: dict[str, Any]) -> None:
    worksheet = workbook.create_sheet("30_预测框架")
    current_row = 1
    sections = [
        ("盈利预测驱动", ["驱动环节", "预测值或方向", "调整幅度", "原文依据", "可验证时点"], forecast.get("drivers", []), ("driver", "forecast", "change", "evidence", "verify_at")),
        ("估值参数与依据", ["估值方法", "核心参数", "参数变化", "锚定物或依据", "评价"], forecast.get("valuation", []), ("method", "parameter", "change", "anchor", "assessment")),
        ("相对市场预期", ["指标", "财年", "分析师预测", "一致预期", "偏离度", "说明"], forecast.get("consensus", []), ("metric", "period", "analyst_value", "consensus_value", "deviation", "note")),
        ("核心假设与可证伪点", ["假设", "观察指标", "预期方向或区间", "可验证时点", "可能证伪情形", "研报位置"], forecast.get("assumptions", []), ("assumption", "observation", "expected", "verify_at", "falsifier", "source_location")),
    ]
    for title, headers, items, fields in sections[:1]:
        style_section(worksheet, current_row, title, len(headers)); current_row += 1
        current_row = write_table(worksheet, current_row, headers, [[item.get(field, "") for field in fields] for item in items]) + 2
    style_section(worksheet, current_row, "目标价与上行空间复核", 6); current_row += 1
    check = forecast.get("target_price_check", {})
    method = str(check.get("method", "PE")).upper()
    metric_header, multiple_header = ("预测 BPS", "目标 PB") if method == "PB" else ("预测 EPS", "目标 PE")
    current_row = write_table(worksheet, current_row, ["检验项", metric_header, multiple_header, "基准股价", "研报列示", "还原结果"], [["目标价", "", "", "", "", ""], ["上行空间", "", "", "", "", ""]])
    target_row, upside_row = current_row - 1, current_row
    for column, key in ((2, "eps"), (3, "pe"), (4, "base_price"), (5, "target_price_reported")):
        worksheet.cell(target_row, column, check.get(key, ""))
    worksheet.cell(target_row, 6, f"=B{target_row}*C{target_row}")
    worksheet.cell(upside_row, 4, f"=D{target_row}")
    worksheet.cell(upside_row, 5, check.get("upside_reported", ""))
    worksheet.cell(upside_row, 6, f'=IF(OR(F{target_row}="",D{upside_row}=""),NA(),F{target_row}/D{upside_row}-1)')
    worksheet.cell(upside_row, 5).number_format = worksheet.cell(upside_row, 6).number_format = "0.0%"
    current_row += 2
    for title, headers, items, fields in sections[1:]:
        style_section(worksheet, current_row, title, len(headers)); current_row += 1
        current_row = write_table(worksheet, current_row, headers, [[item.get(field, "") for field in fields] for item in items]) + 2
    worksheet.freeze_panes = "A2"
    set_widths(worksheet, {1: 24, 2: 18, 3: 18, 4: 30, 5: 24, 6: 28})


def build_log_sheet(workbook: Workbook, execution_log: list[dict[str, Any]]) -> None:
    worksheet = workbook.create_sheet("90_执行日志")
    headers = ["指标", "数据源", "查询接口", "原始 Block/记录编号", "执行编号", "取数时间", "完整指标路径/检索条件", "状态", "返回形状/摘要", "原始值", "单位", "原始链接", "信息", "脚本SHA-256"]
    rows = [[item.get("metric", ""), item.get("data_source", "MQL"), item.get("query_interface", "MQL_TOOLCHAIN"), item.get("source_block", item.get("source_record_id", "")), item.get("execution_run_id", ""), item.get("queried_at", ""), item.get("query_path", item.get("indicator_path", item.get("query_conditions", ""))), item.get("status", ""), item.get("raw_result_summary", ""), item.get("raw_value", ""), item.get("unit", ""), item.get("raw_source_url", ""), item.get("message", ""), item.get("script_sha256", "")] for item in execution_log]
    last_row = write_table(worksheet, 1, headers, rows)
    for index, item in enumerate(execution_log, start=2):
        raw_source_url = item.get("raw_source_url", "")
        if raw_source_url:
            link_cell = worksheet.cell(index, 12)
            link_cell.hyperlink = raw_source_url
            link_cell.style = "Hyperlink"
    worksheet.freeze_panes = "A2"; worksheet.auto_filter.ref = f"A1:N{max(last_row, 1)}"
    set_widths(worksheet, {1: 24, 2: 15, 3: 26, 4: 20, 5: 24, 6: 23, 7: 70, 8: 14, 9: 24, 10: 18, 11: 12, 12: 52, 13: 36, 14: 66})
    worksheet.sheet_state = "hidden"


def build_workbook(payload: dict[str, Any], output_path: Path) -> None:
    workbook = Workbook()
    build_guide_sheet(workbook, payload["guide"], len(payload["snapshots"]), len(payload["excluded_tables"]), len(payload["chart_snapshots"]))
    build_snapshot_sheet(workbook, payload["snapshots"], payload["chart_snapshots"], payload["chart_data"])
    build_workpaper_sheet(workbook, payload["snapshots"], payload["workpapers"], payload["chart_snapshots"])
    build_forecast_sheet(workbook, payload["forecast"])
    build_log_sheet(workbook, payload["execution_log"])
    for worksheet in workbook.worksheets:
        worksheet.sheet_view.showGridLines = False
        worksheet.sheet_properties.pageSetUpPr.fitToPage = True
        worksheet.page_setup.paperSize = worksheet.PAPERSIZE_A4
        worksheet.page_setup.orientation = "landscape" if worksheet.max_column > 6 else "portrait"
        worksheet.page_setup.fitToWidth = 1
        worksheet.page_setup.fitToHeight = 0
        worksheet.sheet_properties.pageSetUpPr.autoPageBreaks = False
        worksheet.page_margins.left = 0.25
        worksheet.page_margins.right = 0.25
        worksheet.page_margins.top = 0.4
        worksheet.page_margins.bottom = 0.4
        for row in worksheet.iter_rows():
            for cell in row:
                if cell.value is not None:
                    if cell.alignment.wrap_text is not False:
                        cell.alignment = RIGHT if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool) else WRAP
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    _repair_worksheet_r_namespace(output_path)  # [冒烟放宽 2026-10-12] 修复 openpyxl 批注 legacyDrawing 漏写 xmlns:r


def _repair_worksheet_r_namespace(output_path: Path) -> None:
    """openpyxl 部分版本在含批注的 worksheet 上写入 legacyDrawing r:id，却未在根元素声明 xmlns:r，
    导致 XML 解析报 unbound prefix。本函数对所有 worksheet XML 补全缺失的 xmlns:r 声明。"""
    import re, zipfile, shutil, os
    R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    changed = False
    with zipfile.ZipFile(output_path, "r") as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if re.match(r"xl/worksheets/sheet\d+\.xml$", item.filename):
                text = data.decode("utf-8")
                m = re.match(r"<worksheet([^>]*)>", text)
                if m and "xmlns:r=" not in m.group(1) and "r:" in text:
                    text = text.replace("<worksheet", f'<worksheet xmlns:r="{R_NS}"', 1)
                    data = text.encode("utf-8")
                    changed = True
            zout.writestr(item, data)
    if changed:
        shutil.move(str(tmp), str(output_path))
    elif tmp.exists():
        os.remove(tmp)


def main() -> None:
    arguments = parse_arguments()
    payload = load_payload(arguments.input)
    if arguments.validate_only:
        print(f'Validation passed: {len(payload["snapshots"])} included tables, {len(payload["excluded_tables"])} excluded tables, {len(payload["chart_snapshots"])} charts, {len(payload["chart_data"])} chart data blocks.')
        return
    build_workbook(payload, arguments.output)


if __name__ == "__main__":
    main()
