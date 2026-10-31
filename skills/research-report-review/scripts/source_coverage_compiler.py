#!/usr/bin/env python3
"""Compile every source row to a direct indicator, derived formula, or evidenced omission."""
from __future__ import annotations

import argparse, json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORE = ROOT / "reference" / "a_share_financial_timeseries_core.json"
DEFAULT_FORMULAS = ROOT / "reference" / "derived_metric_formulas.json"

def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError(f"{path} must contain an object")
    return value

def normalize(value: str) -> str:
    """语义安全归一化：仅处理大小写、全半角括号/百分号与空白，不删任何业务修饰词。"""
    return "".join(str(value).replace("（", "(").replace("）", ")").replace("％", "%").split()).lower()


def normalized_map(values: dict[str, Any]) -> dict[str, Any]:
    return {normalize(key): value for key, value in values.items()}

def direct_display_unit(field: str, entry: dict[str, Any], table_unit: str | None, field_units: dict[str, str]) -> str:
    if field in field_units: return field_units[field]
    unit=str(entry.get("unit") or "")
    if unit == "元" and table_unit in {"万元", "百万元", "亿元"}: return str(table_unit)
    if unit.startswith("%") or (unit.startswith("小数") and "%" in field): return "%"
    return unit

# 处理状态分类：直接把结果归入「直接取数 / 同口径派生 / 近似参考 / 待定义 / 真实无数据 / 报表兜底」
FIRM_DISPOSITIONS = {"DIRECT", "DERIVED", "REPORT_FIELD"}
COVERED_DISPOSITIONS = FIRM_DISPOSITIONS | {"APPROXIMATE"}


def compile_fields(source_fields: list[str], core: dict[str, Any], rules: dict[str, Any], display_unit: str | None = None, field_units: dict[str, str] | None = None) -> dict[str, Any]:
    entries = core.get("entries", {})
    # 四条查表路径统一走同一 normalize，避免全半角/空白差异在不同入口表现不一致
    aliases = normalized_map(rules.get("aliases", {}))
    formulas = normalized_map(rules.get("formulas", {}))
    dispositions = normalized_map(rules.get("dispositions", {}))
    by_name = {normalize(v.get("canonical_name", "")): k for k, v in entries.items()}
    by_alias = {}
    for key, entry in entries.items():
        for alias in entry.get("aliases", []) or []:
            by_alias.setdefault(normalize(alias), key)
    metrics, unresolved = [], []
    field_dispositions: dict[str, str] = {}
    field_units = field_units or {}
    for field in source_fields:
        name = normalize(field)
        key = aliases.get(name) or by_name.get(name) or by_alias.get(name)
        if key in entries:
            metrics.append({"field": field, "kind": "DIRECT", "cache_key": key, "display_unit": direct_display_unit(field, entries[key], display_unit, field_units)})
            field_dispositions[field] = "DIRECT"
            continue
        formula = formulas.get(name)
        if formula and all(k in entries for k in formula.get("operands", [])):
            metrics.append({"field": field, "kind": "DERIVED", **formula})
            field_dispositions[field] = "DERIVED"
            continue
        disposition = dispositions.get(name)
        if disposition:
            kind = disposition.get("kind", "")
            if kind in COVERED_DISPOSITIONS:
                metrics.append({"field": field, "kind": kind, **{k: v for k, v in disposition.items() if k != "kind"}})
                field_dispositions[field] = kind
            else:
                reason = disposition.get("reason") or kind or "UNDEFINED_DISPOSITION"
                unresolved.append({"field": field, "reason": reason, "required_action": "MQL_TOOLCHAIN"})
                field_dispositions[field] = kind or "PENDING_DEFINITION"
            continue
        unresolved.append({"field": field, "reason": "NO_DIRECT_ALIAS_OR_FORMULA", "required_action": "MQL_TOOLCHAIN"})
        field_dispositions[field] = "PENDING_DEFINITION"
    needs_review = any(value not in FIRM_DISPOSITIONS for value in field_dispositions.values())
    return {"source_fields": source_fields, "metrics": metrics, "unresolved_fields": unresolved,
            "coverage_status": "PARTIAL" if unresolved or needs_review else "FULL",
            "covered_fields": [m["field"] for m in metrics],
            "field_dispositions": field_dispositions}

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True, help="JSON object with source_fields")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--core", type=Path, default=DEFAULT_CORE)
    p.add_argument("--formulas", type=Path, default=DEFAULT_FORMULAS)
    a=p.parse_args(); spec=load(a.source)
    result=compile_fields(spec["source_fields"], load(a.core), load(a.formulas), spec.get("display_unit"), spec.get("field_units"))
    result.update({k:v for k,v in spec.items() if k not in result})
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if result["unresolved_fields"]: raise SystemExit(2)
if __name__ == "__main__": main()
