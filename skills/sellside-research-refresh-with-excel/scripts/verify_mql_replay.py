#!/usr/bin/env python3
"""Verify that every MQL script in the evidence package was re-executed
successfully and returned the same data matrix as the original execution.

This is a mandatory gate before Excel workbook generation: it prevents
fabricated or stale execution evidence from entering the deliverable.

Usage:
    python verify_mql_replay.py target_data_evidence.json mql_replay_records.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

BLOCK_START = re.compile(r"^\s*(CrossSectionBlock|TimeSeriesBlock|ReportBlock|EdbBlock)\s*\(")
FLOAT_TOLERANCE = 1e-6


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def normalize_script(script: str) -> str:
    """Normalize whitespace for stable script comparison."""
    return re.sub(r"\s+", " ", (script or "").strip())


def extract_matrix(response: dict[str, Any]) -> list[list[Any]]:
    """Extract [header_row, *data_rows] from an Execute_MQL response."""
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise ValueError("response is not a successful Execute_MQL result")
    blocks = response.get("result", {}).get("blocks", [])
    if len(blocks) != 1 or str(blocks[0].get("blockId")) != "1":
        raise ValueError("response must contain exactly one Block #1")
    block = blocks[0]
    columns = list(block.get("columns") or [])
    rows = block.get("rows") or []
    if not columns:
        raise ValueError("response block has no columns")
    matrix = [columns]
    for row in rows:
        matrix.append([row.get(col) for col in columns])
    return matrix


def cells_equal(a: Any, b: Any) -> bool:
    """Compare two cell values with float tolerance."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= FLOAT_TOLERANCE
    return a == b


def compare_matrices(
    original: list[list[Any]], replay: list[list[Any]], label: str
) -> list[str]:
    """Return a list of mismatch descriptions; empty list means identical."""
    diffs: list[str] = []
    if len(original) != len(replay):
        diffs.append(f"{label}: row count differs ({len(original)} vs {len(replay)})")
        return diffs
    if len(original[0]) != len(replay[0]):
        diffs.append(
            f"{label}: column count differs ({len(original[0])} vs {len(replay[0])})"
        )
        return diffs
    for r, (orig_row, replay_row) in enumerate(zip(original, replay)):
        for c, (orig_val, replay_val) in enumerate(zip(orig_row, replay_row)):
            if not cells_equal(orig_val, replay_val):
                diffs.append(
                    f"{label}: cell [{r},{c}] differs: "
                    f"{orig_val!r} vs {replay_val!r}"
                )
                if len(diffs) >= 10:
                    diffs.append("... (truncated, more mismatches exist)")
                    return diffs
    return diffs


def main() -> None:
    if len(sys.argv) != 3:
        fail("usage: verify_mql_replay.py target_data_evidence.json mql_replay_records.json")

    evidence_path, replay_path = map(Path, sys.argv[1:])
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    replay_doc = json.loads(replay_path.read_text(encoding="utf-8"))

    payload = evidence.get("writing_payload", {})
    original_records = payload.get("mql_execution_records") or []
    if not isinstance(original_records, list):
        fail("writing_payload.mql_execution_records must be a list")

    # If there are no MQL records (e.g., all coverage is model_forecast or
    # mx_ds), replay verification is trivially satisfied.
    if not original_records:
        receipt = {
            "status": "PASS",
            "checked": 0,
            "matched": 0,
            "mismatches": [],
            "note": "no mql_execution_records to verify",
        }
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return

    replay_records = replay_doc.get("records") or []
    if not isinstance(replay_records, list) or not replay_records:
        fail("mql_replay_records.json must contain a non-empty 'records' array")

    # Build a lookup from normalized script -> replay matrix
    replay_by_script: dict[str, list[list[Any]]] = {}
    replay_meta: dict[str, dict[str, str]] = {}
    for idx, rec in enumerate(replay_records, start=1):
        script = normalize_script(rec.get("request", {}).get("mql", ""))
        if not BLOCK_START.match(script):
            fail(f"replay record {idx}: request.mql does not start with a valid Block")
        if not rec.get("replay_tool_call_id"):
            fail(f"replay record {idx}: missing replay_tool_call_id")
        try:
            matrix = extract_matrix(rec.get("response", {}))
        except (ValueError, KeyError, TypeError) as exc:
            fail(f"replay record {idx}: cannot extract matrix — {exc}")
        replay_by_script[script] = matrix
        replay_meta[script] = {
            "replay_tool_call_id": str(rec["replay_tool_call_id"]),
        }

    results: list[dict[str, Any]] = []
    all_diffs: list[str] = []
    for idx, orig in enumerate(original_records, start=1):
        label = f"record[{idx}]"
        orig_script = normalize_script(
            orig.get("tool_execution", {}).get("request", {}).get("mql", "")
        )
        if not orig_script:
            fail(f"{label}: original record has no MQL script")
        replay_matrix = replay_by_script.get(orig_script)
        if replay_matrix is None:
            all_diffs.append(f"{label}: no replay found for script (first 80 chars: {orig_script[:80]!r})")
            results.append({"index": idx, "status": "NO_REPLAY", "script": orig_script[:80]})
            continue
        try:
            orig_matrix = extract_matrix(orig.get("tool_execution", {}).get("response", {}))
        except (ValueError, KeyError, TypeError) as exc:
            fail(f"{label}: cannot extract original matrix — {exc}")
        diffs = compare_matrices(orig_matrix, replay_matrix, label)
        if diffs:
            all_diffs.extend(diffs)
            results.append({
                "index": idx,
                "status": "MISMATCH",
                "script": orig_script[:80],
                "replay_tool_call_id": replay_meta[orig_script]["replay_tool_call_id"],
                "diffs": diffs[:3],
            })
        else:
            results.append({
                "index": idx,
                "status": "MATCH",
                "script": orig_script[:80],
                "replay_tool_call_id": replay_meta[orig_script]["replay_tool_call_id"],
                "rows": len(orig_matrix),
                "cols": len(orig_matrix[0]),
            })

    matched = sum(1 for r in results if r["status"] == "MATCH")
    status = "PASS" if not all_diffs else "FAIL"
    receipt = {
        "status": status,
        "checked": len(original_records),
        "matched": matched,
        "results": results,
        "mismatches": all_diffs,
        "replay_file": str(replay_path.resolve()),
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if all_diffs:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
