#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from build_writing_workbook import build
from validate_target_workbook import validate as validate_workbook


SKILL_NAME = "sellside-research-refresh-with-excel20"
SKILL_VERSION = "2.0.0"
REQUIRED_STAGE2_OUTPUTS = {
    "entity_mapping.json",
    "period_mapping.json",
    "coverage_requirements.json",
    "target_table_mapping.json",
    "information_rows.json",
}
TERMINAL_STRUCTURED_DISPOSITIONS = {
    "mql_returned",
    "derived_from_mql",
    "model_forecast",
    "mql_unavailable",
}
ALLOWED_SOURCE_ORIGINS = {"mql", "mx_ds", "model", "derived"}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path, media_type: str) -> dict[str, Any]:
    resolved = path.resolve()
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
        "media_type": media_type,
    }


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_confirmed_stage2(handoff_path: Path) -> dict[str, Any]:
    handoff = _load_json(handoff_path)
    if handoff.get("stage") != 2 or handoff.get("status") != "CONFIRMED":
        raise ValueError("stage-2 handoff must be CONFIRMED")
    outputs: dict[str, Path] = {}
    for artifact in handoff.get("outputs", []):
        path = Path(str(artifact.get("path", "")))
        if not path.is_file():
            raise ValueError(f"stage-2 output missing: {path}")
        if path.stat().st_size != artifact.get("size_bytes"):
            raise ValueError(f"stage-2 output size mismatch: {path}")
        if _sha256(path) != artifact.get("sha256"):
            raise ValueError(f"stage-2 output hash mismatch: {path}")
        outputs[path.name] = path
    missing = REQUIRED_STAGE2_OUTPUTS - set(outputs)
    if missing:
        raise ValueError(f"stage-2 handoff missing outputs: {sorted(missing)!r}")
    return {
        "handoff": handoff,
        "paths": outputs,
        "data": {name: _load_json(path) for name, path in outputs.items()},
    }


def validate_evidence_package(
    stage2: dict[str, Any],
    evidence_package: dict[str, Any],
) -> dict[str, Any]:
    if evidence_package.get("schema_version") != 1:
        raise ValueError("target evidence package schema_version must be 1")
    target = evidence_package.get("target_identity")
    payload = evidence_package.get("writing_payload")
    if not isinstance(target, dict) or not isinstance(payload, dict):
        raise ValueError("target_identity and writing_payload are required")

    entity_mapping = stage2["data"]["entity_mapping.json"]
    confirmed_target = entity_mapping.get("target_primary", {})
    for field, stage2_field in (
        ("entity_id", "entity_id"),
        ("entity_name", "name"),
        ("security_code", "code"),
    ):
        if str(target.get(field, "")) != str(confirmed_target.get(stage2_field, "")):
            raise ValueError(f"target identity differs from stage 2: {field}")
    meta = payload.get("workbook_meta", {})
    if meta.get("subject") != target["entity_name"]:
        raise ValueError("workbook subject differs from confirmed target")
    if meta.get("security_code") != target["security_code"]:
        raise ValueError("workbook security code differs from confirmed target")

    planned = stage2["data"]["coverage_requirements.json"]
    final = payload.get("coverage_requirements")
    if not isinstance(final, list):
        raise ValueError("writing_payload.coverage_requirements must be a list")
    planned_by_id = {str(item["coverage_id"]): item for item in planned}
    final_by_id = {str(item["coverage_id"]): item for item in final}
    if set(planned_by_id) != set(final_by_id):
        raise ValueError("final coverage IDs differ from stage 2")
    if len(final_by_id) != len(final):
        raise ValueError("duplicate final coverage ID")
    for coverage_id, source in planned_by_id.items():
        item = final_by_id[coverage_id]
        if item.get("item") != source.get("metric_name"):
            raise ValueError(f"coverage item changed after stage 2: {coverage_id}")
        if source.get("disposition") == "not_applicable":
            if item.get("disposition") != "not_applicable":
                raise ValueError(f"not-applicable coverage changed: {coverage_id}")
        elif item.get("disposition") not in TERMINAL_STRUCTURED_DISPOSITIONS:
            raise ValueError(f"coverage lacks terminal evidence: {coverage_id}")

    mapping_coverage = {
        str(coverage_id)
        for item in stage2["data"]["target_table_mapping.json"]
        for coverage_id in item.get("coverage_ids", [])
    }
    if mapping_coverage != set(planned_by_id):
        raise ValueError("target table mapping does not cover stage-2 requirements")

    sources = payload.get("source_registry")
    if not isinstance(sources, list) or not sources:
        raise ValueError("source_registry must be non-empty")
    source_by_id = {int(item["source_id"]): item for item in sources}
    if len(source_by_id) != len(sources):
        raise ValueError("duplicate source registry ID")
    for source in sources:
        if source.get("origin") not in ALLOWED_SOURCE_ORIGINS:
            raise ValueError("source-workbook evidence cannot enter target workbook")

    row_by_coverage: dict[str, dict[str, Any]] = {}
    for row in payload.get("fact_rows", []) + payload.get("forecast_rows", []):
        coverage_id = str(row.get("coverage_id", ""))
        if coverage_id in row_by_coverage:
            raise ValueError(f"duplicate workbook coverage row: {coverage_id}")
        row_by_coverage[coverage_id] = row
    if set(row_by_coverage) != set(final_by_id):
        raise ValueError("facts and forecasts do not cover every final requirement")
    for coverage_id, item in final_by_id.items():
        row = row_by_coverage[coverage_id]
        source = source_by_id.get(int(row["source_id"]))
        if source is None:
            raise ValueError(f"unknown source for coverage {coverage_id}")
        if item.get("disposition") == "mql_returned":
            if source.get("origin") != "mql" or row.get("source_type") != "Choice 金融查数":
                raise ValueError(f"MQL coverage lacks MQL lineage: {coverage_id}")

    expected_information = stage2["data"]["information_rows.json"]
    actual_information = payload.get("information_rows")
    if not isinstance(actual_information, list):
        raise ValueError("writing_payload.information_rows must be a list")
    expected_keys = {
        (
            str(row.get("title", "")),
            str(row.get("published_at", "")),
            str(row.get("url", "")),
        )
        for row in expected_information
    }
    actual_keys = {
        (
            str(row.get("title", "")),
            str(row.get("published_at", "")),
            str(row.get("locator", "")),
        )
        for row in actual_information
    }
    if actual_keys != expected_keys:
        raise ValueError("information evidence differs from confirmed stage 2 output")
    return payload


def _run_validator(command: list[str], receipt_path: Path) -> None:
    process = subprocess.run(command, capture_output=True, text=True)
    receipt = {
        "status": "PASS" if process.returncode == 0 else "FAIL",
        "command": command,
        "returncode": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise ValueError(
            f"validator failed: {Path(command[1]).name}: "
            f"{process.stdout}{process.stderr}"
        )


def build_stage3(
    stage2_handoff_path: Path,
    evidence_path: Path,
    output_dir: Path,
    replay_path: Path | None = None,
) -> dict[str, Any]:
    started_at = _now()
    stage2 = load_confirmed_stage2(stage2_handoff_path)
    evidence = _load_json(evidence_path)
    payload = validate_evidence_package(stage2, evidence)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Replay verification gate: if the evidence package contains MQL execution
    # records, every script must have been re-executed and returned identical
    # results.  This prevents fabricated or stale execution evidence.
    mql_records = payload.get("mql_execution_records") or []
    replay_receipt_path = output_dir / "mql_replay_receipt.json"
    if mql_records:
        if replay_path is None:
            raise ValueError(
                "mql_replay_records.json is required when evidence contains "
                f"{len(mql_records)} MQL execution record(s)"
            )
        if not replay_path.is_file():
            raise ValueError(f"replay file not found: {replay_path}")
        script_dir = Path(__file__).resolve().parent
        _run_validator(
            [
                sys.executable,
                str(script_dir / "verify_mql_replay.py"),
                str(evidence_path),
                str(replay_path),
            ],
            replay_receipt_path,
        )
    else:
        replay_receipt_path.write_text(
            json.dumps(
                {"status": "PASS", "checked": 0, "note": "no MQL records to verify"},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    workbook_path = output_dir / "B_新标的底稿.xlsx"
    audit_path = output_dir / "mql_audit.json"
    mql_receipt_path = output_dir / "mql_coverage_receipt.json"
    reference_receipt_path = output_dir / "reference_coverage_receipt.json"
    structure_receipt_path = output_dir / "workbook_structure_receipt.json"
    handoff_path = output_dir / "stage-3-handoff.json"

    audit = build(workbook_path, payload)
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    script_dir = Path(__file__).resolve().parent
    _run_validator(
        [
            sys.executable,
            str(script_dir / "validate_mql_workbook_coverage.py"),
            str(workbook_path),
            str(audit_path),
        ],
        mql_receipt_path,
    )
    _run_validator(
        [
            sys.executable,
            str(script_dir / "validate_reference_metric_coverage.py"),
            str(evidence_path),
            str(stage2["paths"]["target_table_mapping.json"]),
            str(audit_path),
        ],
        reference_receipt_path,
    )
    structure_receipt = validate_workbook(
        workbook_path,
        stage2["data"]["coverage_requirements.json"],
        stage2["data"]["information_rows.json"],
    )
    structure_receipt_path.write_text(
        json.dumps(structure_receipt, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    outputs = [
        _artifact(workbook_path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        _artifact(audit_path, "application/json"),
        _artifact(mql_receipt_path, "application/json"),
        _artifact(reference_receipt_path, "application/json"),
        _artifact(structure_receipt_path, "application/json"),
        _artifact(replay_receipt_path, "application/json"),
    ]
    inputs = [
        _artifact(stage2_handoff_path, "application/json"),
        _artifact(evidence_path, "application/json"),
    ]
    if replay_path is not None:
        inputs.append(_artifact(replay_path, "application/json"))
    input_hashes = {
        str(stage2_handoff_path.resolve()): _sha256(stage2_handoff_path),
        str(evidence_path.resolve()): _sha256(evidence_path),
    }
    if replay_path is not None:
        input_hashes[str(replay_path.resolve())] = _sha256(replay_path)
    handoff = {
        "schema_version": 1,
        "task_id": stage2["handoff"]["task_id"],
        "stage": 3,
        "status": "CONFIRMED",
        "producer": {
            "skill": SKILL_NAME,
            "version": SKILL_VERSION,
            "mode": "新标的Excel底稿",
        },
        "inputs": inputs,
        "outputs": outputs,
        "started_at": started_at,
        "completed_at": _now(),
        "validation": [
            {
                "name": "MQL replay verification",
                "status": "PASS",
                "receipt_path": str(replay_receipt_path.resolve()),
            },
            {
                "name": "MQL workbook coverage",
                "status": "PASS",
                "receipt_path": str(mql_receipt_path.resolve()),
            },
            {
                "name": "reference metric coverage",
                "status": "PASS",
                "receipt_path": str(reference_receipt_path.resolve()),
            },
            {
                "name": "target workbook structure and lineage",
                "status": "PASS",
                "receipt_path": str(structure_receipt_path.resolve()),
            },
        ],
        "limitations": [],
        "error": None,
        "resume": {
            "next_stage": 4,
            "requires_user_confirmation": False,
            "input_hashes": input_hashes,
        },
    }
    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return handoff


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage2_handoff", type=Path)
    parser.add_argument("target_evidence", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        help="mql_replay_records.json: re-execution results for every MQL script",
    )
    args = parser.parse_args()
    handoff = build_stage3(
        args.stage2_handoff,
        args.target_evidence,
        args.output_dir,
        replay_path=args.replay,
    )
    print(
        json.dumps(
            {
                "status": handoff["status"],
                "workbook": next(
                    item["path"]
                    for item in handoff["outputs"]
                    if item["path"].endswith(".xlsx")
                ),
                "handoff": str(
                    (args.output_dir / "stage-3-handoff.json").resolve()
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
