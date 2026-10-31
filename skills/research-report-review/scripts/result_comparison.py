#!/usr/bin/env python3
"""统一容差分级、口径候选与倒挤重建的验证层。

规则单一真源：reference/tolerance_rules.json（分级有序、无重叠、无未覆盖，每类型单一声明单位）。
本模块只做机械定级与候选，不据误差大小认定研报定义。
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = ROOT / "reference" / "tolerance_rules.json"

# 前置一致性检查维度（对齐方案①：先查定义/币种/单位/期间/股数时点/调整类型，再算差异）
PRECONDITION_FIELDS = ("definition_id", "currency", "unit_basis", "period", "share_basis_date", "adjustment_type")

# 单位基准归一化：小数与百分数不混用
UNIT_ALIASES = {
    "fraction": "FRACTION", "小数": "FRACTION", "小数无单位": "FRACTION",
    "percent": "PERCENT", "%": "PERCENT", "百分数": "PERCENT", "百分点": "PERCENT",
}

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_SAFE_EXPRESSION = re.compile(r"^[0-9eE+\-*/().\s]+$")


def load_rules(path: Path = DEFAULT_RULES) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("metric_types"), dict) or not isinstance(payload.get("grades"), dict):
        raise ValueError(f"{path} tolerance rules schema is incompatible")
    return payload


def canonical_unit(value: str | None) -> str:
    text = str(value or "").strip()
    return UNIT_ALIASES.get(text.lower(), text.upper())


def check_preconditions(mql_meta: dict[str, Any], report_meta: dict[str, Any],
                        fields: tuple[str, ...] = PRECONDITION_FIELDS) -> list[str]:
    """先比较定义/币种/单位/期间/股数时点/调整类型，返回不一致的维度名（空列表=可继续比对）。"""
    mismatches: list[str] = []
    for field in fields:
        left, right = mql_meta.get(field), report_meta.get(field)
        if field == "unit_basis":
            if canonical_unit(left) != canonical_unit(right):
                mismatches.append(field)
        elif left != right:
            mismatches.append(field)
    return mismatches


def normalize_to_unit(value: float, unit_basis: str | None, target_unit: str | None) -> float:
    basis, target = canonical_unit(unit_basis), canonical_unit(target_unit)
    if basis == "FRACTION" and target == "PERCENT":
        return value * 100.0
    if basis == "PERCENT" and target == "FRACTION":
        return value / 100.0
    return value


def _apply_ladder(ladder: list[dict[str, Any]], value: float, flags: dict[str, bool]) -> str:
    for step in ladder[:-1]:
        if any(not flags.get(name, False) for name in step.get("requires", [])):
            continue
        if value <= step["max"]:
            return step["grade"]
    return ladder[-1]["grade"]


def classify(metric_type: str, mql_value: float, report_value: float, *, rules: dict[str, Any] | None = None,
             unit_basis: str = "as_declared", direction_consistent: bool = True) -> dict[str, Any]:
    """单一定级：每个 entry 恰好命中一个等级，单位由 metric_type 唯一声明。"""
    rules = rules or load_rules()
    spec = rules["metric_types"].get(metric_type)
    if spec is None:
        raise ValueError(f"unknown metric type: {metric_type}")
    if spec["normalize"] == "fraction_to_percent" and canonical_unit(unit_basis) == "FRACTION":
        mql_value = normalize_to_unit(mql_value, "fraction", "percent")
    if spec["unit"] == "relative_percent":
        base = abs(report_value)
        error = 0.0 if base == 0 else abs(mql_value - report_value) / base * 100.0
    else:
        error = abs(mql_value - report_value)
    error = round(error, 9)  # 抹去二进制浮点噪声，保证边界判定在十进制意义上唯一
    grade_id = _apply_ladder(spec["ladder"], error, {"direction_consistent": direction_consistent})
    meta = rules["grades"][grade_id]
    return {"metric_type": metric_type, "grade": grade_id, "label": meta["label"], "status": meta["status"],
            "unit": spec["unit"], "error_in_unit": round(error, 6), "attribution": meta["attribution"]}


def candidates(metric_type: str, report_value: float, options: dict[str, float], *, rules: dict[str, Any] | None = None,
               unit_basis: str = "as_declared", direction_consistent: bool = True) -> dict[str, Any]:
    """多口径比较：最接近者只产生候选，不证明研报定义（方案④）。"""
    ranking = []
    for name, value in options.items():
        result = classify(metric_type, value, report_value, rules=rules, unit_basis=unit_basis,
                          direction_consistent=direction_consistent)
        ranking.append({"candidate": name, "value": value, "grade": result["grade"],
                        "status": result["status"], "error_in_unit": result["error_in_unit"]})
    ranking.sort(key=lambda item: (item["status"] == "FAIL", item["error_in_unit"]))
    return {"report_value": report_value, "metric_type": metric_type, "ranking": ranking,
            "candidate_count": sum(item["status"] != "FAIL" for item in ranking),
            "closest": next((item for item in ranking if item["status"] != "FAIL"), None),
            "definition_proven": False,
            "note": "最接近口径仅为候选；须先通过定义/币种/单位/期间/股数时点/调整类型前置检查，再由人工确认研报定义"}


def verify_backsolve(formula: str, operands: dict[str, float], expected: float, *,
                     rules: dict[str, Any] | None = None, metric_type: str = "MONEY") -> dict[str, Any]:
    """倒挤重建：保存明确公式与完整输入，并检出重复使用同一输入（避免重复扣减，方案⑤）。"""
    if any(not _SAFE_EXPRESSION.match(str(value)) for value in operands.values()):
        raise ValueError("back-solve operands must be numeric")
    try:
        expression = formula.format(**operands)
    except (KeyError, IndexError, ValueError) as exc:
        raise ValueError(f"formula placeholders do not match operands: {exc}")
    if not _SAFE_EXPRESSION.match(expression):
        raise ValueError("formula must contain only numbers and +-*/() when substituted")
    computed = eval(expression, {"__builtins__": {}}, {})  # noqa: S307 - 表达式已限定为纯算术
    repeats = sorted(name for name, count in Counter(_PLACEHOLDER.findall(formula)).items() if count > 1)
    result = classify(metric_type, computed, expected, rules=rules)
    return {"formula": formula, "operands": dict(operands), "expression": expression,
            "computed": computed, "expected": expected, "difference": computed - expected,
            "grade": result["grade"], "status": result["status"], "unit": result["unit"],
            "error_in_unit": result["error_in_unit"],
            "repeated_operands": repeats, "duplicate_deduction_risk": bool(repeats),
            "attribution": result["attribution"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("describe",), help="校验规则文件可加载并输出分级摘要")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args()
    rules = load_rules(args.rules)
    summary = {
        "schema_version": rules.get("schema_version"),
        "grades": [grade for grade, _ in sorted(rules["grades"].items(), key=lambda item: item[1]["order"])],
        "metric_types": {name: {"unit": spec["unit"], "ladder": [step["grade"] for step in spec["ladder"]]}
                         for name, spec in rules["metric_types"].items()},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
