#!/usr/bin/env python3
"""Generate independent financial MQL and assemble runtime results into a workpaper contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .mql_contract import script_sha256
except ImportError:
    from mql_contract import script_sha256


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORE = ROOT / "reference" / "a_share_financial_timeseries_core.json"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def transform(entry: dict[str, Any], display_unit: str) -> tuple[str, float, str, str, str | None]:
    source_unit = str(entry.get("unit") or "")
    if source_unit == "元" and display_unit == "百万元":
        return "/ 1000000", 0.000001, "ABSOLUTE", "ABSOLUTE", "/ 1000000"
    if source_unit == "元" and display_unit == "亿元":
        return "/ 100000000", 0.00000001, "ABSOLUTE", "ABSOLUTE", "/ 100000000"
    if source_unit.startswith("小数") and display_unit == "%":
        return "* 100", 100, "DECIMAL_RATIO", "PERCENT", "* 100"
    if source_unit.startswith("%") and display_unit == "%":
        return "", 1, "PERCENT", "PERCENT", None
    semantics = "ABSOLUTE" if source_unit in {"元", "元/股", "次", "倍"} else str(entry.get("value_semantics") or "ABSOLUTE")
    if display_unit != source_unit:
        raise ValueError(f"unsupported unit conversion: {source_unit} -> {display_unit}")
    return "", 1, semantics, semantics, None


def generate(spec: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    metrics = spec.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("metrics must be a non-empty array")
    entries = catalog.get("entries", {})
    end_date = str(spec["end_date"])
    start_date = str(spec["start_date"])
    if end_date == "N()":
        raise ValueError('N() is not valid for "_s" reporting-period windows; use MRQ() or a fixed date')
    rendered_end = end_date if end_date == "MRQ()" else json.dumps(end_date, ensure_ascii=False)
    lines = [
        "TimeSeriesBlock(#1, {EM_DATE}, {EM_CODE});",
        f'SetCodes([{json.dumps(str(spec["security_code"]), ensure_ascii=False)}]);',
        "SetWindow(",
        f'    {{开始时间}} = {json.dumps(start_date, ensure_ascii=False)},',
        f'    {{结束时间}} = {rendered_end},',
        f'    {{周期}} = {json.dumps(str(spec.get("period", "年")), ensure_ascii=False)}',
        ");",
    ]
    fields: list[str] = []
    contracts: list[dict[str, Any]] = []
    for metric in metrics:
        field = str(metric.get("field") or "")
        if not field: raise ValueError("every metric requires field")
        if metric.get("kind", "DIRECT") == "DERIVED":
            operands = metric.get("operands", [])
            operand_expr=[]
            for key in operands:
                entry=entries.get(key)
                if not isinstance(entry,dict): raise ValueError(f"cache miss in formula {field}: {key}")
                target=str(metric.get("operand_display_unit") or metric.get("display_unit") or entry["unit"])
                suffix, *_ = transform(entry,target)
                value=f'{{{entry["indicator_path"]}}}()' + (" "+suffix if suffix else "")
                operand_expr.append(value)
            expression=str(metric["expression"]).format(*operand_expr)
            display_unit=str(metric["display_unit"]); scale=1; token=None
            source_semantics=display_semantics="PERCENT" if display_unit=="%" else "ABSOLUTE"
            source_unit=display_unit
        else:
            key = metric.get("cache_key"); entry = entries.get(key)
            if not isinstance(entry, dict): raise ValueError(f"cache miss: {key}")
            display_unit = str(metric.get("display_unit") or entry["unit"])
            suffix, scale, source_semantics, display_semantics, token = transform(entry, display_unit)
            expression = f'{{{entry["indicator_path"]}}}()' + (" " + suffix if suffix else "")
            source_unit = entry["unit"]
        lines.append(f"{{{field}}}: {expression};")
        fields.append(field)
        contract_source_unit = "%" if str(source_unit).startswith("%") else "小数" if str(source_unit).startswith("小数") else source_unit
        contracts.append({
            "field": field, "value_type": "NUMBER", "source_unit": contract_source_unit,
            "display_unit": display_unit, "scale_factor": scale,
            "source_semantics": source_semantics, "display_semantics": display_semantics,
            "script_transform_token": token,
        })
    lines.append("OutputBlock();")
    script = "\n".join(lines)
    source_fields = spec.get("source_fields")
    if source_fields is not None and fields != source_fields:
        raise ValueError("compiled output fields must exactly equal source_fields in order")
    output = {
        "mql_script": script,
        "block_selector": "#1",
        "script_sha256": script_sha256(script),
        "script_output_fields": fields,
        "unit_contracts": contracts,
        "indicator_time_shape": "time_series",
        "financial_query_mode": "FINANCIAL_TIME_SERIES",
    }
    if end_date == "MRQ()":
        output["query_end_date_dynamic"] = "MRQ()"
    # R05：报告期时序不套交易日历，也不写 {市场类型}；source 保留报告期事实，query 记录生成时窗口。
    output["window_policy"] = "SOURCE_FIXED"
    output["rolling_implemented"] = False
    output["query_start_date"] = start_date
    output["query_end_date"] = end_date
    return output


def runtime_matrix(runtime: dict[str, Any], execution_request: dict[str, Any] | None = None,
                   planned_script: str | None = None, tool_call_id: str | None = None) -> tuple[str, list[list[Any]]]:
    """Read an unchanged successful response and its paired actual request."""
    if runtime.get("ok") is not True or runtime.get("error"):
        raise ValueError("save the original successful MQL toolchain response")
    execution_id = str(runtime.get("traceparent") or tool_call_id or "")
    if not execution_id:
        raise ValueError("save a real response trace or paired tool call identifier")
    actual_request = execution_request or {}
    if planned_script is not None and actual_request.get("mql") != planned_script:
        raise ValueError("planned script differs from the saved executed request; re-execute changes")
    result = runtime.get("result") or {}
    blocks = result.get("blocks") or []
    if len(blocks) != 1:
        raise ValueError("save one independently executed Block per workpaper")
    block = blocks[0]
    schema = block.get("column_schema", [])
    hidden = {value["name"] for value in schema if value.get("hidden_key")}
    columns = [name for name in (block.get("columns") or [value.get("name") for value in schema]) if name not in hidden]
    rows = block.get("rows") or []
    if not columns or not rows:
        raise ValueError("MQL output block has no visible columns or rows")
    matrix = [list(columns)] + [[row.get(column) for column in columns] for row in rows]
    return execution_id, matrix


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--spec", type=Path, required=True)
    gen.add_argument("--output", type=Path, required=True)
    gen.add_argument("--core", type=Path, default=DEFAULT_CORE)
    assemble = sub.add_parser("assemble")
    assemble.add_argument("--plan", type=Path, required=True)
    assemble.add_argument("--runtime-result", type=Path, required=True)
    assemble.add_argument("--executed-request", type=Path, required=True, help="Saved request paired with the raw response")
    assemble.add_argument("--tool-call-id", help="Real paired tool call ID when the response has no execution or trace ID")
    assemble.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "generate":
        output = generate(read_json(args.spec), read_json(args.core))
    else:
        output = read_json(args.plan)
        paired = read_json(args.executed_request)
        execution_id, raw = runtime_matrix(read_json(args.runtime_result), paired, output["mql_script"], args.tool_call_id)
        orientation = int(output.get("mql_orientation", 1))
        last = raw if orientation == 0 else [list(row) for row in zip(*raw)]
        output.update({
            "execution_run_id": execution_id,
            "raw_result": raw,
            "last_result": last,
            "cached_table": last,
            "expected_rows": len(last),
            "expected_columns": len(last[0]),
            "result_origin": "MQL_TOOLCHAIN",
            "execution_status": "SUCCESS",
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
