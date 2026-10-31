#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate policy-comparison run directory deliverables."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]


def validate_run_dir(run_dir: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    files_found: list[str] = []

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        errors.append("missing manifest.json")
    else:
        files_found.append("manifest.json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"manifest.json invalid JSON: {exc}")
            manifest = {}
        if manifest.get("status") not in ("running", "completed", "failed"):
            warnings.append("manifest status unexpected")

    required = [
        "mcp_trace.json",
        "search_raw.json",
        "conferences.json",
        "comparison_result.md",
        "quality_review.md",
        "timing.json",
    ]
    for name in required:
        p = run_dir / name
        if p.is_file():
            files_found.append(name)
        else:
            errors.append(f"missing {name}")

    reports_dir = run_dir / "reports"
    if not reports_dir.is_dir():
        errors.append("missing reports/ directory")
    else:
        docx_files = list(reports_dir.glob("*.docx"))
        if not docx_files:
            errors.append("reports/ has no docx files")
        else:
            files_found.extend(f"reports/{f.name}" for f in docx_files)

    comparison = run_dir / "comparison_result.md"
    if comparison.is_file():
        text = comparison.read_text(encoding="utf-8")
        if len(text.strip()) < 200:
            warnings.append("comparison_result.md too short")
        if "|" not in text:
            warnings.append("comparison_result.md may lack markdown table")

    ok = len(errors) == 0
    return {
        "ok": ok,
        "run_dir": str(run_dir),
        "files_found": files_found,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate policy-comparison deliverables")
    parser.add_argument(
        "--date",
        required=True,
        help="Run date YYYY-MM-DD (resolves skills/policy-comparison/output/{date})",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Override run directory path",
    )
    args = parser.parse_args()

    if args.run_dir:
        run_dir = Path(args.run_dir)
    else:
        run_dir = SKILL_ROOT / "output" / args.date

    result = validate_run_dir(run_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
