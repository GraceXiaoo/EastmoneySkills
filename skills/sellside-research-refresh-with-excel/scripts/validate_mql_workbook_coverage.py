#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from openpyxl import load_workbook



VALID_DISPOSITIONS = {
    "mql_returned",
    "derived_from_mql",
    "model_forecast",
    "mx_ds_non_structured",
    "mql_unavailable",
    "not_applicable",
}
VALID_APPLICABILITY = {"required", "conditional", "not_applicable"}
MQL_FALLBACK_CATEGORIES = {"UNSUPPORTED", "NO_CANDIDATE_AFTER_SEARCH", "REMOTE_NO_DATA_AFTER_VALID_QUERY", "SERVICE_FAILURE_CONFIRMED"}
SERVICE_FAULT_TYPES = {"NETWORK_ERROR", "HTTP_5XX", "RATE_LIMIT", "AUTH_INVALID", "TOOL_UNAVAILABLE", "PARSE_FAILED"}
CHOICE_DOWNLOAD_URL = "https://choice.eastmoney.com/downloads"
UNIT_TO_YUAN = {"元": 1.0, "千元": 1_000.0, "万元": 10_000.0, "百万元": 1_000_000.0, "亿元": 100_000_000.0}
LAYOUT_RATIO_THRESHOLD = 3
LAYOUT_LONG_SIDE_THRESHOLD = 12
MQL_BLOCK_KEYWORDS = ("CrossSectionBlock", "TimeSeriesBlock", "ReportBlock", "EdbBlock")
MQL_BLOCK_START_RE = re.compile(r"^\s*(CrossSectionBlock|TimeSeriesBlock|ReportBlock|EdbBlock)\s*\(")
# Patterns that indicate natural-language contamination inside an MQL script/comment.
# These must never appear in a pure MQL Note or mql_script field.
MQL_CONTAMINATION_RES = [
    re.compile(r"[【】]"),                                  # 【说明】等全角方括号标记
    re.compile(r"(^|\n)\s*(注|备注|说明|提示|注意|警告)\s*[：:]"),  # 注：/备注：/说明：等开头行
    re.compile(r"安装\s*[Cc]hoice", re.IGNORECASE),       # 安装 Choice / 安装choice
    re.compile(r"加载项"),                                  # 加载项
    re.compile(r"刷新\s*本\s*锚点"),                        # 刷新本锚点
    re.compile(r"即可\s*复算|复算"),                        # 即可复算 / 复算
    re.compile(r"```"),                                     # Markdown 代码围栏
    re.compile(r"\[Threaded\s+comment\]", re.IGNORECASE),  # Threaded comment 标记
    re.compile(r"(^|\n)\s*Comment\s*:", re.IGNORECASE),   # Comment: 开头
]
# Valid MQL statement line prefixes (after stripping leading whitespace).
MQL_VALID_LINE_RE = re.compile(
    r"^\s*("
    r"(CrossSectionBlock|TimeSeriesBlock|ReportBlock|EdbBlock)\s*\("
    r"|SetCodes\s*\("
    r"|SetWindow\s*\("
    r"|OutputBlock\s*\("
    r"|\{[^}]*\}\s*[:=]"
    r"|\)"
    r"|[A-Za-z_][A-Za-z0-9_]*\s*="
    r")"
)


def validate_pure_mql(script: str, location: str) -> None:
    """Validate that *script* is pure executable MQL without natural-language contamination.

    Raises SystemExit via fail() on the first detected problem.
    """
    text = (script or "").strip()
    if not text:
        fail(f"{location}: MQL script is empty")
    # 1. First non-whitespace must begin a Block declaration.
    if not MQL_BLOCK_START_RE.match(text):
        fail(f"{location}: MQL script must start with one of {MQL_BLOCK_KEYWORDS}")
    # 2. Scan for explicit contamination markers anywhere in the text.
    for pattern in MQL_CONTAMINATION_RES:
        match = pattern.search(text)
        if match:
            fail(f"{location}: MQL script contains non-MQL text {match.group(0)!r}")
    # 3. Flag lines that are clearly natural-language prose rather than MQL.
    #    A line is suspicious if it contains Chinese sentence punctuation but
    #    none of the structural characters that appear in MQL statements.
    MQL_STRUCTURAL_CHARS = set("{}();=")
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if MQL_VALID_LINE_RE.match(line):
            continue
        has_structural = any(ch in line for ch in MQL_STRUCTURAL_CHARS)
        has_prose_punct = any(ch in line for ch in "。！？")
        if has_prose_punct and not has_structural:
            fail(f"{location}: line {lineno} looks like prose, not MQL: {line[:60]!r}")


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def rgb(value: object) -> str:
    raw = str(value or "").upper().replace("#", "")
    return raw[-6:] if len(raw) >= 6 else raw


def assert_standard_header(ws) -> None:
    # Skip sheets that don't use the standard table-header row format
    if ws.title in ("00_导读", "20_研报底稿", "90_执行日志"):
        return
    for cell in ws[1]:
        if cell.value is None:
            continue
        if rgb(cell.fill.fgColor.rgb) != "1F4E78":
            fail(f"{ws.title}!{cell.coordinate} header fill is not #1F4E78")
        color = cell.font.color.rgb if cell.font.color and cell.font.color.type == "rgb" else None
        if rgb(color) != "FFFFFF" or not cell.font.bold:
            fail(f"{ws.title}!{cell.coordinate} header must use bold white font")


def validate_coverage_requirements(audit: dict, by_key: dict[str, dict]) -> dict[str, dict]:
    rows = audit.get("coverage_requirements")
    if not isinstance(rows, list) or not rows:
        fail("audit must contain a non-empty coverage_requirements inventory")
    by_id: dict[str, dict] = {}
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            fail(f"coverage requirement {index} must be an object")
        coverage_id = str(item.get("coverage_id", "")).strip()
        if not coverage_id or coverage_id in by_id:
            fail(f"missing or duplicate coverage_id: {coverage_id!r}")
        category = str(item.get("category", "")).strip()
        disposition = str(item.get("disposition", "")).strip()
        label = str(item.get("item", "")).strip()
        if not label or not category or disposition not in VALID_DISPOSITIONS:
            fail(f"coverage requirement {coverage_id} lacks item/category/valid disposition")
        if item.get("data_kind", "structured") != "non_structured" and disposition == "mx_ds_non_structured":
            fail(f"structured item {coverage_id} cannot bypass MQL as mx_ds_non_structured")
        source_unit = str(item.get("source_unit", "")).strip()
        target_unit = str(item.get("target_unit", source_unit)).strip()
        if source_unit and target_unit and source_unit != target_unit:
            if source_unit not in UNIT_TO_YUAN or target_unit not in UNIT_TO_YUAN:
                fail(f"coverage requirement {coverage_id} uses an unsupported unit conversion")
            try:
                factor = float(item["scale_factor"])
            except (KeyError, TypeError, ValueError):
                fail(f"coverage requirement {coverage_id} lacks scale_factor")
            expected = UNIT_TO_YUAN[source_unit] / UNIT_TO_YUAN[target_unit]
            if abs(factor - expected) > max(1e-12, abs(expected) * 1e-9):
                fail(f"coverage requirement {coverage_id} has incorrect unit scale_factor")
            if not str(item.get("conversion_formula", "")).startswith("="):
                fail(f"coverage requirement {coverage_id} lacks an Excel conversion formula")
            if not str(item.get("presentation_range", "")).strip():
                fail(f"coverage requirement {coverage_id} lacks a converted presentation range")
        if disposition == "mql_returned":
            key = str(item.get("block_key", ""))
            field = str(item.get("returned_field", ""))
            if key not in by_key or field not in set(by_key[key].get("returned_items") or []):
                fail(f"coverage requirement {coverage_id} has invalid MQL block/field lineage")
        elif disposition == "derived_from_mql":
            formula = str(item.get("formula", "")).strip()
            inputs = item.get("input_coverage_ids")
            if not formula.startswith("=") or not isinstance(inputs, list) or not inputs:
                fail(f"derived requirement {coverage_id} needs an Excel formula and MQL-backed inputs")
        elif disposition == "mql_unavailable":
            attempts = item.get("mql_failure_evidence")
            fallback = str(item.get("fallback_locator", "")).strip()
            if not isinstance(attempts, list) or not attempts or not fallback:
                fail(f"MQL-unavailable requirement {coverage_id} needs actual discovery/execution evidence and fallback locator")
            category = item.get("mql_failure_category")
            if category not in MQL_FALLBACK_CATEGORIES:
                fail(f"fallback {coverage_id} needs a completed MQL no-data or confirmed service-fault category")
            if category == "SERVICE_FAILURE_CONFIRMED" and not any(
                isinstance(e, dict) and e.get("status") in {"FAILED", "TIMEOUT"}
                and e.get("failure_type") in SERVICE_FAULT_TYPES
                and e.get("tool_call_id") and e.get("evidence_locator") for e in attempts
            ):
                fail(f"fallback {coverage_id} requires a returned terminal service error; pending/abandoned calls do not qualify")
        elif disposition == "not_applicable" and not str(item.get("reason", "")).strip():
            fail(f"not-applicable requirement {coverage_id} needs a reason")
        by_id[coverage_id] = item

    for coverage_id, item in by_id.items():
        if item.get("disposition") != "derived_from_mql":
            continue
        for input_id in item["input_coverage_ids"]:
            source = by_id.get(str(input_id))
            if not source or source.get("disposition") not in {"mql_returned", "derived_from_mql"}:
                fail(f"derived requirement {coverage_id} has non-MQL-backed input {input_id}")

    scope = str(audit.get("scope", "")).strip()
    if not scope:
        fail("audit must declare a report scope")
    applicability = audit.get("category_applicability")
    if not isinstance(applicability, dict):
        fail("category_applicability must be an object")
    categories = {item["category"] for item in by_id.values()}
    if categories - set(applicability):
        fail("category_applicability must cover the categories used in this task")
    for category in sorted(applicability):
        rule = applicability.get(category)
        if not isinstance(rule, dict) or rule.get("status") not in VALID_APPLICABILITY:
            fail(f"category {category} lacks a valid applicability status")
        category_rows = [item for item in by_id.values() if item.get("category") == category]
        if rule["status"] == "required":
            if not category_rows or all(item.get("disposition") == "not_applicable" for item in category_rows):
                fail(f"required category {category} has no applicable coverage")
        elif rule["status"] == "not_applicable":
            if not str(rule.get("reason", "")).strip():
                fail(f"not-applicable category {category} needs a scope-specific reason")
            if any(item.get("disposition") != "not_applicable" for item in category_rows):
                fail(f"not-applicable category {category} must be explicitly represented by not_applicable coverage")
        elif not category_rows:
            fail(f"conditional category {category} needs coverage or an explicit not-applicable item")
    return by_id


def validate_sheet_coverage_ids(ws, coverage: dict[str, dict]) -> set[str]:
    headers = {str(cell.value): cell.column for cell in ws[1] if cell.value is not None}
    if "覆盖需求ID" not in headers:
        fail(f"{ws.title} lacks 覆盖需求ID")
    seen: set[str] = set()
    for row in range(2, ws.max_row + 1):
        if all(ws.cell(row, col).value is None for col in range(1, ws.max_column + 1)):
            continue
        coverage_id = str(ws.cell(row, headers["覆盖需求ID"]).value or "").strip()
        if coverage_id not in coverage:
            fail(f"{ws.title} row {row} has missing or unknown 覆盖需求ID {coverage_id!r}")
        if coverage_id in seen:
            fail(f"{ws.title} repeats 覆盖需求ID {coverage_id}")
        seen.add(coverage_id)
        item = coverage[coverage_id]
        if item.get("disposition") == "derived_from_mql":
            formula_cell = str(item.get("formula_cell", "")).strip()
            if not formula_cell or ws.title not in formula_cell:
                fail(f"derived requirement {coverage_id} lacks a formula_cell on {ws.title}")
            coordinate = formula_cell.split("!", 1)[-1]
            value = ws[coordinate].value
            if not isinstance(value, str) or not value.startswith("="):
                fail(f"derived requirement {coverage_id} is not an Excel formula at {formula_cell}")
    return seen


def main() -> None:
    if len(sys.argv) != 3:
        fail("usage: validate_mql_workbook_coverage.py workbook.xlsx mql_audit.json")
    book_path, audit_path = map(Path, sys.argv[1:])
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    blocks = audit.get("blocks") or []

    by_key: dict[str, dict] = {}
    for block in blocks:
        key = str(block.get("key", ""))
        if not key or key in by_key:
            fail(f"missing or duplicate block key: {key!r}")
        if block.get("status") != "SUCCESS" or not str(block.get("execution_id", "")).strip():
            fail(f"block {key} lacks a successful real execution id")
        script = str(block.get("mql_script", "")).strip()
        validate_pure_mql(script, f"block {key} mql_script")
        try:
            expected_rows = int(block["expected_rows"])
            expected_columns = int(block["expected_columns"])
            orientation = int(block["mql_orientation"])
            source_page_index = int(block["source_page_index"])
            source_order = int(block["source_order"])
            formula_columns = int(block["mql_formula_cols"])
            formula_rows = int(block["mql_formula_rows"])
            refresh_rows = int(block["refresh_rows"])
            refresh_columns = int(block["refresh_columns"])
        except (KeyError, TypeError, ValueError):
            fail(f"block {key} lacks source, formula, refresh-shape, or ordering metadata")
        if min(expected_rows, expected_columns, source_page_index, source_order, formula_columns, formula_rows, refresh_rows, refresh_columns) < 1 or orientation not in (0, 1):
            fail(f"block {key} has invalid source, formula, refresh-shape, or ordering metadata")
        if block.get("refresh_shape_evidence") not in {"observed_refresh", "provider_contract", "result_matrix"}:
            fail(f"block {key} lacks reliable refresh_shape_evidence")
        display_shape = (expected_columns + 1, expected_rows) if orientation == 1 else (expected_rows + 1, expected_columns)
        if (refresh_rows, refresh_columns) != display_shape or (formula_columns, formula_rows) != (expected_columns, expected_rows):
            fail(f"block {key} refresh shape differs from the complete result matrix")
        layout_class = str(block.get("layout_class", ""))
        if layout_class not in {"financial", "non_financial"}:
            fail(f"block {key} lacks valid layout_class")
        reference_orientation = block.get("reference_orientation")
        if reference_orientation is not None:
            if reference_orientation not in (0, 1) or orientation != int(reference_orientation):
                fail(f"block {key} does not follow the reference report orientation")
        elif expected_columns >= LAYOUT_LONG_SIDE_THRESHOLD and expected_columns >= expected_rows * LAYOUT_RATIO_THRESHOLD and orientation != 1:
            fail(f"block {key} is disproportionately wide and should be transposed")
        elif expected_rows >= LAYOUT_LONG_SIDE_THRESHOLD and expected_rows >= expected_columns * LAYOUT_RATIO_THRESHOLD and orientation != 0:
            fail(f"block {key} is already vertically oriented and should keep its original direction")
        required = set(block.get("required_items") or [])
        returned = set(block.get("returned_items") or [])
        omitted_rows = block.get("omitted_items") or []
        omitted = {x.get("item") if isinstance(x, dict) else x for x in omitted_rows}
        if required != returned | omitted or returned & omitted:
            fail(f"block {key} required/returned/omitted coverage is inconsistent")
        if not returned.issubset(set(block.get("columns", []))):
            fail(f"block {key} returned_items do not match actual result columns")
        by_key[key] = block

    coverage = validate_coverage_requirements(audit, by_key)

    wb = load_workbook(book_path, data_only=False)
    for sheet in ("10_研报快照", "20_研报底稿", "30_预测框架"):
        if sheet not in wb.sheetnames:
            fail(f"missing sheet {sheet}")

    for sheet in wb.worksheets:
        assert_standard_header(sheet)

    ws = wb["20_研报底稿"]
    guide = wb["00_导读"]
    guide_links = [cell.hyperlink.target for row in guide.iter_rows() for cell in row if cell.hyperlink]
    if CHOICE_DOWNLOAD_URL not in guide_links:
        fail("00_导读 lacks the Choice terminal download link")

    # Validate 20_研报底稿: collect =mql() anchors and verify format
    anchors = []
    spills = []
    for row in ws.iter_rows():
        for cell in row:
            value = cell.value
            if isinstance(value, str) and re.match(r"^=mql\(", value, flags=re.IGNORECASE):
                anchors.append(cell)
                # Formula must match =mql("#N",0|1) pattern
                match = re.fullmatch(r'=mql\("#(\d+)",([01])\)', value, flags=re.IGNORECASE)
                if not match:
                    fail(f"{ws.title}!{cell.coordinate} has invalid MQL formula: {value!r}")
                block_num = int(match.group(1))
                orientation = int(match.group(2))
                # Must have MQL script in cell comment
                if cell.comment is None:
                    fail(f"{ws.title}!{cell.coordinate} =mql() formula missing MQL script comment")
                note = cell.comment.text.strip()
                validate_pure_mql(note, f"{ws.title}!{cell.coordinate} Comment")
                # Find matching block from audit by checking script content
                matched_block = None
                for key, block in by_key.items():
                    if block.get("mql_script", "").strip() == note:
                        matched_block = block
                        break
                if matched_block is None:
                    fail(f"{ws.title}!{cell.coordinate} comment script not found in audit blocks")
                if orientation != int(matched_block["mql_orientation"]):
                    fail(f"{ws.title}!{cell.coordinate} formula orientation {orientation} differs from audit {matched_block['mql_orientation']}")
                # Check spill area is reserved (blank cells below)
                spill_rows = int(matched_block["refresh_rows"])
                spill_cols = int(matched_block["refresh_columns"])
                spill = (cell.row, cell.column, cell.row + spill_rows - 1, cell.column + spill_cols - 1)
                # Check no overlap with other spills
                for top, left, bottom, right, other in spills:
                    intersects = not (spill[2] < top or bottom < spill[0] or spill[3] < left or right < spill[1])
                    if intersects:
                        fail(f"{ws.title}!{cell.coordinate} spill overlaps {other}")
                spills.append((*spill, cell.coordinate))

    if len(anchors) != len(blocks):
        fail(f"MQL anchor count {len(anchors)} != successful block count {len(blocks)}")

    if ws.column_dimensions["B"].width < 48:
        fail("20_研报底稿 column B width is too narrow")

    facts = wb["10_研报快照"]
    fact_coverage_ids = validate_sheet_coverage_ids(facts, coverage)
    headers = {c.value: c.column for c in facts[1]}
    needed = ["来源类型", "MQL区块", "执行请求ID", "返回字段", "覆盖状态"]
    if any(h not in headers for h in needed):
        fail("fact sheet lacks field-level MQL lineage columns")
    for row in range(2, facts.max_row + 1):
        if facts.cell(row, headers["来源类型"]).value != "Choice 金融查数":
            continue
        key = str(facts.cell(row, headers["MQL区块"]).value or "")
        run_id = facts.cell(row, headers["执行请求ID"]).value
        returned_field = str(facts.cell(row, headers["返回字段"]).value or "")
        if key not in by_key or run_id != by_key[key]["execution_id"]:
            fail(f"fact row {row} has invalid block/execution lineage")
        field = returned_field.split(":", 1)[-1]
        if field not in by_key[key]["returned_items"]:
            fail(f"fact row {row} field {field!r} was not returned by block {key}")
        if facts.cell(row, headers["覆盖状态"]).value != "已返回":
            fail(f"fact row {row} is not marked returned")

    forecast = wb["30_预测框架"]
    forecast_coverage_ids = validate_sheet_coverage_ids(forecast, coverage)
    missing_workbook_rows = set(coverage) - fact_coverage_ids - forecast_coverage_ids
    if missing_workbook_rows:
        fail(
            "coverage requirements missing from facts/forecast workbook rows: "
            f"{sorted(missing_workbook_rows)}"
        )
    forecast_headers = {str(cell.value): cell.column for cell in forecast[1] if cell.value is not None}
    if "类型" not in forecast_headers:
        fail("forecast sheet lacks 类型 column")
    type_column = forecast_headers["类型"]
    coverage_column = forecast_headers["覆盖需求ID"]
    workbook_types = {
        str(forecast.cell(row, coverage_column).value): str(forecast.cell(row, type_column).value or "")
        for row in range(2, forecast.max_row + 1)
        if forecast.cell(row, coverage_column).value is not None
    }
    for coverage_id, item in coverage.items():
        if coverage_id not in workbook_types:
            continue
        value_type = workbook_types[coverage_id]
        if item.get("disposition") == "model_forecast" and "自主模型" not in value_type:
            fail(f"forecast coverage {coverage_id} must be labeled 自主模型")
        if item.get("category") == "consensus_forecast" and item.get("disposition") == "mql_returned" and "Choice一致预期" not in value_type:
            fail(f"forecast coverage {coverage_id} must be labeled Choice一致预期")
        if item.get("disposition") == "derived_from_mql" and "公式推导" not in value_type:
            fail(f"forecast coverage {coverage_id} must be labeled 公式推导")

    print("PASS: MQL workbook coverage validated")


if __name__ == "__main__":
    main()
