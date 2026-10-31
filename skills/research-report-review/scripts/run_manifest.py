"""Record and check resumable research-report workflow operations."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_fingerprints(paths: list[Path]) -> dict[str, str]:
    return {str(path.resolve()): file_fingerprint(path) for path in paths}


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "operations": {}}
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("operations"), dict):
        raise ValueError("manifest must contain schema_version=1 and an operations object")
    return value


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(path)


def operation_key(stage: str, object_id: str, operation: str) -> str:
    return f"{stage}:{object_id}:{operation}"


def record_operation(
    manifest_path: Path,
    stage: str,
    object_id: str,
    operation: str,
    *,
    inputs: list[Path] | None = None,
    status: str = "PASS",
    result_path: Path | None = None,
    execution_id: str = "",
) -> None:
    """Programmatically record an operation (best-effort, never raises).

    Pipeline scripts call this after a stage artifact is written so that
    ``run_manifest.json`` accumulates stage fingerprints, statuses and
    result paths. Failures are swallowed: manifest recording must never
    break the main build flow.
    """
    try:
        manifest = load_manifest(manifest_path)
        key = operation_key(stage, object_id, operation)
        manifest["operations"][key] = {
            "stage": stage,
            "object_id": object_id,
            "operation": operation,
            "status": status,
            "input_fingerprints": input_fingerprints(inputs or []),
            "result_path": str(result_path.resolve()) if result_path else "",
            "execution_id": execution_id or "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        save_manifest(manifest_path, manifest)
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check")
    record = subparsers.add_parser("record")
    budget = subparsers.add_parser("budget")
    for command in (check, record):
        command.add_argument("--stage", required=True)
        command.add_argument("--object-id", required=True)
        command.add_argument("--operation", required=True)
        command.add_argument("--input", action="append", type=Path, default=[])

    record.add_argument("--status", choices=("TODO", "IN_PROGRESS", "PASS", "BLOCKED"), required=True)
    record.add_argument("--result-path", type=Path)
    record.add_argument("--execution-id")
    budget.add_argument("--increment", type=int, default=1)
    budget.add_argument("--limit", type=int, default=100)
    budget.add_argument("--checkpoint-at", type=int, default=85)

    args = parser.parse_args()
    manifest = load_manifest(args.manifest)

    if args.command == "budget":
        if args.increment < 0 or args.limit <= 0 or not 0 < args.checkpoint_at < args.limit:
            raise ValueError("budget requires increment>=0 and 0<checkpoint-at<limit")
        execution_budget = manifest.setdefault(
            "execution_budget",
            {"limit": args.limit, "used": 0, "checkpoint_at": args.checkpoint_at},
        )
        execution_budget["limit"] = args.limit
        execution_budget["checkpoint_at"] = args.checkpoint_at
        execution_budget["used"] = int(execution_budget.get("used", 0)) + args.increment
        execution_budget["remaining"] = max(0, args.limit - execution_budget["used"])
        execution_budget["updated_at"] = datetime.now(timezone.utc).isoformat()
        action = "CHECKPOINT_AND_ASK" if execution_budget["used"] >= args.checkpoint_at else "CONTINUE"
        execution_budget["action"] = action
        save_manifest(args.manifest, manifest)
        print(json.dumps(execution_budget, ensure_ascii=False))
        raise SystemExit(2 if action == "CHECKPOINT_AND_ASK" else 0)

    key = operation_key(args.stage, args.object_id, args.operation)
    fingerprints = input_fingerprints(args.input)

    if args.command == "check":
        entry = manifest["operations"].get(key)
        reusable = bool(
            isinstance(entry, dict)
            and entry.get("status") == "PASS"
            and entry.get("input_fingerprints") == fingerprints
            and (not entry.get("result_path") or Path(entry["result_path"]).exists())
        )
        print(json.dumps({"operation_key": key, "reusable": reusable}, ensure_ascii=False))
        raise SystemExit(0 if reusable else 1)

    manifest["operations"][key] = {
        "stage": args.stage,
        "object_id": args.object_id,
        "operation": args.operation,
        "status": args.status,
        "input_fingerprints": fingerprints,
        "result_path": str(args.result_path.resolve()) if args.result_path else "",
        "execution_id": args.execution_id or "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_manifest(args.manifest, manifest)
    print(json.dumps({"operation_key": key, "status": args.status}, ensure_ascii=False))


if __name__ == "__main__":
    main()
