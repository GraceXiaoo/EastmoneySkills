"""Merge audited phase JSON files into the sole workbook input JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_manifest import record_operation  # noqa: E402


OWNERS = {
    "census": {"guide", "excluded_tables"},
    "evidence": {"snapshots", "chart_snapshots", "chart_data"},
    "queries": {"workpapers", "verification", "execution_log", "blocked_items"},
    "forecast": {"forecast"},
}
REQUIRED = {"guide", "snapshots", "chart_snapshots", "chart_data", "excluded_tables", "workpapers", "verification", "execution_log", "forecast"}
PHASE_SCHEMA_VERSION = 1
LEGACY_PHASE_SCHEMA = "LEGACY"
PUBLIC_FIELDS = {"schema_version"}
LEGACY_FULL_DOWNGRADE_REASON = "LEGACY_SCHEMA_FULL_NOT_REVERIFIED"
LEGACY_WORKPAPER_NOTE = "迁移自旧 schema：原 FULL 结论未按新语义重验，降级为 PARTIAL。"
LEGACY_CHART_NOTE = "迁移自旧 schema：原 FULL 映射结论未按新语义重验，降级为 PARTIAL。"


def _downgrade_legacy_full(fragment: dict[str, Any], label: str, artifact: str) -> list[dict[str, Any]]:
    """旧 schema 的 FULL 结论不得继承为新语义 FULL：降级并留重验记录。

    可无歧义推导的说明字段（`mapping_note` / `mql_mapping_note`）自动填充；新语义要求但旧工件
    未提供且无法推导的证据字段（`omitted_metrics`）不得编造，直接阻断合并并要求人工重验。
    """
    records: list[dict[str, Any]] = []
    if label == "queries":
        for index, item in enumerate(fragment.get("workpapers", [])):
            if not isinstance(item, dict) or item.get("mapping_status") != "FULL":
                continue
            if item.get("source_type") == "CHART" and not item.get("omitted_metrics"):
                raise ValueError(
                    f"workpapers[{index}] is a legacy FULL chart mapping without omitted_metrics; "
                    "evidence cannot be derived, re-verify it under the current schema first"
                )
            item["mapping_status"] = "PARTIAL"
            item.setdefault("mapping_note", LEGACY_WORKPAPER_NOTE)
            records.append(
                {
                    "phase": label,
                    "artifact": artifact,
                    "object_id": item.get("mapping_id") or item.get("source_id"),
                    "field": "mapping_status",
                    "from": "FULL",
                    "to": "PARTIAL",
                    "reason": LEGACY_FULL_DOWNGRADE_REASON,
                }
            )
    if label == "evidence":
        for index, item in enumerate(fragment.get("chart_data", [])):
            if not isinstance(item, dict) or item.get("mql_mapping_status") != "FULL":
                continue
            if not item.get("omitted_metrics"):
                raise ValueError(
                    f"chart_data[{index}] is a legacy FULL mapping without omitted_metrics; "
                    "evidence cannot be derived, re-verify it under the current schema first"
                )
            item["mql_mapping_status"] = "PARTIAL"
            item.setdefault("mql_mapping_note", LEGACY_CHART_NOTE)
            records.append(
                {
                    "phase": label,
                    "artifact": artifact,
                    "object_id": item.get("chart_block_id") or item.get("chart_id"),
                    "field": "mql_mapping_status",
                    "from": "FULL",
                    "to": "PARTIAL",
                    "reason": LEGACY_FULL_DOWNGRADE_REASON,
                }
            )
    return records


def read_artifact(path: Path, label: str) -> tuple[dict[str, Any], str]:
    """Read one phase artifact, returning its mergeable fields and declared schema version."""
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    declared = value.get("schema_version", LEGACY_PHASE_SCHEMA)
    if declared not in (LEGACY_PHASE_SCHEMA, PHASE_SCHEMA_VERSION):
        raise ValueError(
            f"{label} declares unsupported schema_version {declared!r}; "
            f"expected {LEGACY_PHASE_SCHEMA!r} (artifact written before versioning) or {PHASE_SCHEMA_VERSION}"
        )
    unexpected = set(value) - OWNERS[label] - PUBLIC_FIELDS
    if unexpected:
        raise ValueError(f"{label} contains fields owned by another phase: {sorted(unexpected)}")
    fragment = {key: item for key, item in value.items() if key not in PUBLIC_FIELDS}
    return fragment, declared


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--forecast", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--object-id", default=None)
    args = parser.parse_args()

    payload: dict[str, Any] = {}
    migration_log: list[dict[str, Any]] = []
    for label in ("census", "evidence", "queries", "forecast"):
        fragment, declared = read_artifact(getattr(args, label), label)
        overlap = set(payload) & set(fragment)
        if overlap:
            raise ValueError(f"duplicate root fields: {sorted(overlap)}")
        payload.update(fragment)
        if declared != PHASE_SCHEMA_VERSION:
            migration_log.append(
                {
                    "phase": label,
                    "artifact": getattr(args, label).name,
                    "from_version": declared,
                    "to_version": PHASE_SCHEMA_VERSION,
                    "migration": "explicit_upgrade_legacy_artifact",
                }
            )
            migration_log.extend(
                _downgrade_legacy_full(fragment, label, getattr(args, label).name)
            )
    missing = REQUIRED - set(payload)
    if missing:
        raise ValueError(f"missing workbook fields: {sorted(missing)}")
    payload.setdefault("blocked_items", [])
    payload["schema_version"] = PHASE_SCHEMA_VERSION
    payload["migration_log"] = migration_log

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(args.output)
    if args.manifest is not None:
        oid = args.object_id or args.output.parent.name
        record_operation(
            args.manifest, "5", oid, "merge",
            inputs=[args.census, args.evidence, args.queries, args.forecast],
            result_path=args.output,
        )
    print(f"Merged workbook input: {args.output}")


if __name__ == "__main__":
    main()
