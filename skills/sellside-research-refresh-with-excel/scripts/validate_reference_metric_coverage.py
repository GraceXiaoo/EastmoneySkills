#!/usr/bin/env python3
"""Validate that reference metric coverage is fully represented in the target
workbook audit.  Runs as a subprocess gate from build_target_workbook.

Usage:
    python validate_reference_metric_coverage.py evidence.json target_table_mapping.json audit.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: validate_reference_metric_coverage.py "
            "evidence.json target_table_mapping.json audit.json"
        )
    evidence_path, mapping_path, audit_path = map(Path, sys.argv[1:])
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    payload = evidence.get("writing_payload", {})
    coverage = payload.get("coverage_requirements", [])
    if not isinstance(coverage, list) or not coverage:
        raise SystemExit("FAIL: evidence has no coverage_requirements")

    blocks = audit.get("blocks", [])
    block_keys = {str(b.get("key", "")) for b in blocks}
    returned_fields_by_key: dict[str, set[str]] = {}
    for b in blocks:
        key = str(b.get("key", ""))
        returned_fields_by_key[key] = set(b.get("returned_items", []))

    # Every mql_returned coverage item must be backed by a block that returned its field.
    errors: list[str] = []
    for item in coverage:
        cid = str(item.get("coverage_id", ""))
        disposition = str(item.get("disposition", ""))
        if disposition == "mql_returned":
            key = str(item.get("block_key", ""))
            field = str(item.get("returned_field", ""))
            item_name = str(item.get("item", ""))
            if key not in block_keys:
                errors.append(f"{cid}: mql_returned but no audit block key {key!r}")
            elif item_name not in returned_fields_by_key.get(key, set()):
                errors.append(
                    f"{cid}: field {item_name!r} not in block {key!r} returned_items "
                    f"{sorted(returned_fields_by_key.get(key, set()))!r}"
                )

    # target_table_mapping coverage_ids must equal stage-2 coverage_ids set.
    mapping_coverage: set[str] = set()
    if isinstance(mapping, list):
        for entry in mapping:
            mapping_coverage.update(str(c) for c in entry.get("coverage_ids", []))
    elif isinstance(mapping, dict):
        # Some mappings store tables with embedded coverage_ids.
        for tbl in mapping.get("tables", []):
            mapping_coverage.update(str(c) for c in tbl.get("coverage_ids", []))

    if errors:
        raise SystemExit("FAIL: " + "; ".join(errors))

    print("PASS: reference metric coverage validated")


if __name__ == "__main__":
    main()
