#!/usr/bin/env python3
"""Deterministic MQL refresh-contract parsing and validation helpers."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

BLOCK_DEFINITION = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*Block\s*\(\s*#(\d+)", re.I)
BLOCK_DECLARATION = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*Block)\s*\(\s*#(\d+)", re.I)
OUTPUT_ALIAS = re.compile(r"(?ms)^\s*\{([^{}\r\n]+)\}\s*:\s*(.+?);\s*$")
SET_CODES = re.compile(r"\bSetCodes\s*\(\s*\[(.*?)\]\s*\)\s*;", re.I | re.S)
QUOTED_VALUE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
TECHNICAL_HEADERS = {
    "EM_DATE", "EM_CODE", "EM_NAME", "DATE", "CODE", "NAME",
    "日期", "证券代码", "代码",
}
# 声明式报告期结构键：target_column_axis=REPORTING_PERIOD 时，脚本公开声明的
# 「报告期」列只承担期间轴定位，计入 raw_result 表头与 REPORTING_PERIOD 映射 key，
# 但不计入 script_output_fields / covered_fields / unit_contracts 的业务别名比对。
PERIOD_STRUCT_KEYS = {"报告期"}
VALUE_TYPES = {"NUMBER", "IDENTIFIER", "TEXT"}
VALUE_SEMANTICS = {
    "ABSOLUTE", "DECIMAL_RATIO", "PERCENT", "INDEX_BASE_100",
    "PRICE", "COUNT", "DATE", "IDENTIFIER", "TEXT",
}


def normalize_script(script: str) -> str:
    return script.replace("\r\n", "\n").replace("\r", "\n").strip()


def script_sha256(script: str) -> str:
    return hashlib.sha256(normalize_script(script).encode("utf-8")).hexdigest()


def block_numbers(script: str) -> list[int]:
    return [int(value) for value in BLOCK_DEFINITION.findall(script)]


def selected_block_name(script: str, selector: str | None) -> str:
    definitions = BLOCK_DECLARATION.findall(script)
    if not definitions:
        return ""
    number = int(selector[1:]) if isinstance(selector, str) and re.fullmatch(r"#\d+", selector) else int(definitions[-1][1])
    return next((name for name, block_number in definitions if int(block_number) == number), "")


def block_text(script: str, selector: str | None) -> str:
    definitions = list(BLOCK_DEFINITION.finditer(script))
    if not definitions:
        return ""
    number = int(selector[1:]) if isinstance(selector, str) and re.fullmatch(r"#\d+", selector) else definitions[-1].group(1)
    number = int(number)
    for index, match in enumerate(definitions):
        if int(match.group(1)) == number:
            end = definitions[index + 1].start() if index + 1 < len(definitions) else len(script)
            return script[match.start():end]
    return ""


def output_definitions(script: str, selector: str | None) -> list[tuple[str, str]]:
    return [(alias.strip(), expression.strip()) for alias, expression in OUTPUT_ALIAS.findall(block_text(script, selector))]


def output_aliases(script: str, selector: str | None) -> list[str]:
    return [alias for alias, _ in output_definitions(script, selector)]


def set_codes(script: str, selector: str | None) -> list[str]:
    match = SET_CODES.search(block_text(script, selector))
    return [value.encode("utf-8").decode("unicode_escape") for value in QUOTED_VALUE.findall(match.group(1))] if match else []


def runtime_output_headers(raw_result: Any, aliases: list[str] | None = None, structural_keys: set[str] | None = None) -> list[str]:
    """返回 raw_result 表头中属于业务列的部分。

    仅当表头命中 `TECHNICAL_HEADERS`（引擎自动注入的技术键）**且未**在本次 Block 中显式声明为输出别名时才剔除。
    显式声明的列（即使名为「证券代码」「日期」）属于业务列，必须保留，否则会被误判为 RUNTIME_HEADERS 不匹配。
    `structural_keys` 中的已声明结构键（如声明式报告期列）同样剔除：它们承担轴定位，不是业务输出。
    """
    if not isinstance(raw_result, list) or not raw_result or not isinstance(raw_result[0], list):
        return []
    declared = {str(alias).strip() for alias in (aliases or [])}
    structural = {str(key).strip() for key in (structural_keys or set())}
    headers: list[str] = []
    for value in raw_result[0]:
        text = str(value).strip()
        if text in structural and text in declared:
            continue
        if text.upper() in TECHNICAL_HEADERS and text not in declared:
            continue
        headers.append(text)
    return headers


def _numeric_equal(left: Any, right: Any) -> bool:
    return (
        isinstance(left, (int, float)) and not isinstance(left, bool)
        and isinstance(right, (int, float)) and not isinstance(right, bool)
        and math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-15)
    )


def validate_refresh_contract(item: dict[str, Any], execution_log: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return (code, message) errors for one successful MQL workpaper."""
    errors: list[tuple[str, str]] = []
    script = item.get("mql_script")
    if not isinstance(script, str) or not script.strip():
        return [("REFRESH_SCRIPT", "mql_script must be the exact successfully executed refresh script")]
    selector = item.get("block_selector")
    digest = script_sha256(script)
    if item.get("script_sha256") != digest:
        errors.append(("SCRIPT_HASH", f"script_sha256 must equal {digest}"))
    run_id = item.get("execution_run_id")
    matching_logs = [entry for entry in execution_log if isinstance(entry, dict) and entry.get("execution_run_id") == run_id]
    if len(matching_logs) != 1:
        errors.append(("EXECUTION_LOG_LINK", "execution_run_id must match exactly one execution_log entry"))
    elif matching_logs[0].get("script_sha256") != digest:
        errors.append(("EXECUTED_SCRIPT_HASH", "execution_log script_sha256 must match the Excel comment script"))

    aliases = output_aliases(script, selector)
    period_structural = item.get("target_column_axis") == "REPORTING_PERIOD"
    business_aliases = [alias for alias in aliases if not (period_structural and alias in PERIOD_STRUCT_KEYS)]
    if not business_aliases:
        errors.append(("OUTPUT_FIELDS", "selected Block must define at least one output alias"))
    if item.get("script_output_fields") != business_aliases:
        errors.append(("OUTPUT_FIELDS", f"script_output_fields must equal selected Block aliases {business_aliases!r}"))
    headers = runtime_output_headers(item.get("raw_result"), aliases, PERIOD_STRUCT_KEYS if period_structural else None)
    if headers != business_aliases:
        errors.append(("RUNTIME_HEADERS", f"raw_result output headers {headers!r} must equal selected Block aliases {business_aliases!r}"))

    definitions = dict(output_definitions(script, selector))
    contracts = item.get("unit_contracts")
    if not isinstance(contracts, list):
        errors.append(("UNIT_CONTRACTS", "unit_contracts must cover every selected Block output"))
        contracts = []
    by_field = {value.get("field"): value for value in contracts if isinstance(value, dict) and value.get("field")}
    if set(by_field) != set(business_aliases):
        errors.append(("UNIT_CONTRACTS", "unit_contract fields must exactly match selected Block output aliases"))
    for alias in business_aliases:
        contract = by_field.get(alias)
        if not isinstance(contract, dict):
            continue
        value_type = contract.get("value_type")
        if value_type not in VALUE_TYPES:
            errors.append(("UNIT_VALUE_TYPE", f"{alias}: value_type must be NUMBER, IDENTIFIER, or TEXT"))
            continue
        if value_type != "NUMBER":
            continue
        source_unit = contract.get("source_unit")
        display_unit = contract.get("display_unit")
        scale = contract.get("scale_factor")
        source_semantics = contract.get("source_semantics")
        display_semantics = contract.get("display_semantics")
        if not isinstance(source_unit, str) or not isinstance(display_unit, str):
            errors.append(("UNIT_NAMES", f"{alias}: numeric outputs require source_unit and display_unit"))
        if not isinstance(scale, (int, float)) or isinstance(scale, bool) or scale <= 0:
            errors.append(("UNIT_SCALE", f"{alias}: scale_factor must be a positive number"))
            continue
        if source_semantics not in VALUE_SEMANTICS or display_semantics not in VALUE_SEMANTICS:
            errors.append(("UNIT_SEMANTICS", f"{alias}: source_semantics and display_semantics must be explicit"))
        requires_transform = not _numeric_equal(scale, 1) or source_unit != display_unit or source_semantics != display_semantics
        token = contract.get("script_transform_token")
        if requires_transform and (not isinstance(token, str) or not token.strip() or token not in definitions.get(alias, "")):
            errors.append(("UNIT_TRANSFORM", f"{alias}: conversion must appear in the selected Block expression via script_transform_token"))
        if not requires_transform and token not in (None, "") and token not in definitions.get(alias, ""):
            errors.append(("UNIT_TRANSFORM", f"{alias}: declared script_transform_token is absent from the selected Block expression"))
    return errors


def validate_market_group(items: list[dict[str, Any]], source_entities: list[str] | None = None) -> list[tuple[str, str]]:
    """Validate uniform cross-market output schemas across workpapers for one source."""
    if not items:
        return []
    errors: list[tuple[str, str]] = []
    schemas = [item.get("market_schema") for item in items]
    if any(not isinstance(schema, list) or not schema for schema in schemas):
        return [("MARKET_SCHEMA", "every cross-market workpaper requires a non-empty market_schema")]
    canonical = schemas[0]
    if any(schema != canonical for schema in schemas[1:]):
        errors.append(("MARKET_SCHEMA", "all market segments for one source must use the same ordered market_schema"))
    entities: list[str] = []
    codes: list[str] = []
    markets: set[str] = set()
    for item in items:
        segment = item.get("market_segment")
        if not isinstance(segment, dict):
            errors.append(("MARKET_SEGMENT", "each cross-market workpaper requires market_segment"))
            continue
        market = segment.get("market")
        segment_entities = segment.get("entities")
        segment_codes = segment.get("codes")
        currency = segment.get("currency")
        if not isinstance(market, str) or not market or market in markets:
            errors.append(("MARKET_SEGMENT", "market must be non-empty and unique within a source"))
        else:
            markets.add(market)
        if not isinstance(currency, str) or not currency:
            errors.append(("MARKET_CURRENCY", "each market segment requires currency metadata"))
        if not isinstance(segment_entities, list) or not segment_entities or not isinstance(segment_codes, list) or len(segment_entities) != len(segment_codes):
            errors.append(("MARKET_ENTITIES", "market_segment entities and codes must be non-empty aligned arrays"))
            continue
        if set_codes(str(item.get("mql_script") or ""), item.get("block_selector")) != segment_codes:
            errors.append(("MARKET_CODES", "market_segment codes must equal SetCodes in the selected Block"))
        if item.get("script_output_fields") != canonical:
            errors.append(("MARKET_SCHEMA", "selected Block output aliases must equal the common market_schema"))
        entities.extend(segment_entities)
        codes.extend(segment_codes)
    if len(entities) != len(set(entities)) or len(codes) != len(set(codes)):
        errors.append(("MARKET_PARTITION", "market segments must not duplicate entities or codes"))
    if source_entities is not None:
        if set(entities) != set(source_entities):
            errors.append(("MARKET_PARTITION", "market segments must cover source_entities exactly"))
        output_orders = [item.get("market_output_order") for item in items]
        if any(order != source_entities for order in output_orders):
            errors.append(("MARKET_ORDER", "every segment must preserve the common market_output_order from the report"))
    return errors
