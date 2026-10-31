#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


EXPECTED_SHEETS = [
    "00_导读",
    "10_研报快照",
    "20_研报底稿",
    "30_预测框架",
    "90_执行日志",
]
FORBIDDEN_LINEAGE_MARKERS = ("A_原始底稿", "source_workbook", "原始研报数值")


def _headers(sheet: Any) -> dict[str, int]:
    return {
        str(cell.value): cell.column
        for cell in sheet[1]
        if cell.value is not None
    }


def _coverage_ids(sheet: Any) -> set[str]:
    headers = _headers(sheet)
    column = headers.get("覆盖需求ID")
    if column is None:
        raise ValueError(f"{sheet.title} missing 覆盖需求ID")
    return {
        str(sheet.cell(row, column).value)
        for row in range(2, sheet.max_row + 1)
        if sheet.cell(row, column).value not in (None, "")
    }


def validate(
    workbook_path: Path,
    coverage_requirements: list[dict[str, Any]],
    information_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    workbook = load_workbook(workbook_path, data_only=False)
    if workbook.sheetnames != EXPECTED_SHEETS:
        raise ValueError(
            f"workbook sheets differ from contract: {workbook.sheetnames!r}"
        )

    expected_coverage = {
        str(item["coverage_id"]) for item in coverage_requirements
    }
    workbook_coverage = (
        _coverage_ids(workbook["10_研报快照"])
        | _coverage_ids(workbook["30_预测框架"])
    )
    if workbook_coverage != expected_coverage:
        raise ValueError(
            "workbook coverage differs from stage 2; "
            f"missing={sorted(expected_coverage - workbook_coverage)!r}, "
            f"extra={sorted(workbook_coverage - expected_coverage)!r}"
        )

    # Validate 10_研报快照 (static snapshot)
    facts = workbook["10_研报快照"]
    fact_headers = _headers(facts)
    for required in ("来源/接口", "原始定位", "来源类型", "MQL区块", "执行请求ID"):
        if required not in fact_headers:
            raise ValueError(f"10_研报快照 missing {required}")
    for row in range(2, facts.max_row + 1):
        lineage = " ".join(
            str(facts.cell(row, fact_headers[field]).value or "")
            for field in ("来源/接口", "原始定位", "来源类型")
        )
        if any(marker in lineage for marker in FORBIDDEN_LINEAGE_MARKERS):
            raise ValueError(f"fact row {row} contains source-workbook lineage")
        if facts.cell(row, fact_headers["来源类型"]).value == "Choice 金融查数":
            if not facts.cell(row, fact_headers["MQL区块"]).value:
                raise ValueError(f"fact row {row} lacks MQL block lineage")
            if not facts.cell(row, fact_headers["执行请求ID"]).value:
                raise ValueError(f"fact row {row} lacks execution lineage")

    # Validate 20_研报底稿: must contain =mql() formulas, not static text
    mql_sheet = workbook["20_研报底稿"]
    mql_formula_count = 0
    for row in mql_sheet.iter_rows():
        for cell in row:
            if cell.value is not None and isinstance(cell.value, str) and cell.value.startswith("=mql("):
                mql_formula_count += 1
                if cell.comment is None:
                    raise ValueError(f"20_研报底稿 {cell.coordinate}: =mql() formula missing MQL script comment")
    if mql_formula_count == 0:
        raise ValueError("20_研报底稿 contains no =mql() formula anchors")

    # Validate 90_执行日志 is hidden and contains info sources
    log_sheet = workbook["90_执行日志"]
    if log_sheet.sheet_state != "hidden":
        raise ValueError("90_执行日志 must be hidden")

    external_links = getattr(workbook, "_external_links", [])
    if external_links:
        raise ValueError("workbook contains external workbook links")

    return {
        "status": "PASS",
        "workbook": str(workbook_path.resolve()),
        "sheet_names": workbook.sheetnames,
        "coverage_count": len(workbook_coverage),
        "mql_formula_count": mql_formula_count,
        "external_link_count": 0,
        "source_workbook_lineage_count": 0,
    }


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: validate_target_workbook.py "
            "workbook.xlsx coverage_requirements.json information_rows.json"
        )
    coverage = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    information = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    receipt = validate(Path(sys.argv[1]), coverage, information)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
