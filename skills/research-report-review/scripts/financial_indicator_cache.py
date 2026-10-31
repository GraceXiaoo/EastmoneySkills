"""Read and update the local catalog of verified financial indicator metadata.

The cache stores reusable paths and parameter schemas, never company values or query results.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0.0"
DEFAULT_CACHE = Path(__file__).resolve().parent.parent / "output" / "financial_indicator_catalog.json"
DEFAULT_SEED = Path(__file__).resolve().parent.parent / "reference" / "financial_indicator_seed.json"
DEFAULT_CORE = Path(__file__).resolve().parent.parent / "reference" / "a_share_financial_timeseries_core.json"


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "runtime_compatibility_version": "", "entries": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION or not isinstance(payload.get("entries"), dict):
        raise ValueError("financial indicator cache schema is incompatible")
    return payload


def save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_core(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION or not isinstance(payload.get("entries"), dict):
        raise ValueError("core financial time-series catalog schema is incompatible")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("get", "upsert", "invalidate", "list", "plan"))
    parser.add_argument("--reason", help="Reason for invalidating a stale path")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--key", help="Stable semantic key, e.g. balance_sheet.total_assets")
    parser.add_argument("--runtime-version", default="")
    parser.add_argument("--entry-json", help="Verified metadata object for upsert")
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--core", type=Path, default=DEFAULT_CORE)
    parser.add_argument("--families", help="Comma-separated statement families for first-run bulk discovery")
    parser.add_argument("--statement-variant", choices=("非单季度", "单季度"), default="非单季度")
    parser.add_argument("--batch-size", type=int, default=12)
    args = parser.parse_args()
    payload = load(args.cache)
    core = load_core(args.core)
    core_version = core.get("runtime_compatibility_version", "")
    core_compatible = not core_version or bool(args.runtime_version and args.runtime_version == core_version)
    if args.runtime_version and payload.get("runtime_compatibility_version") not in ("", args.runtime_version):
        raise ValueError("cache runtime version differs; refresh indicator metadata before reuse")
    if args.action == "list":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if args.action == "plan":
        if not args.families:
            parser.error("--families is required for plan")
        if not 1 <= args.batch_size <= 15:
            parser.error("--batch-size must be between 1 and 15")
        seed = json.loads(args.seed.read_text(encoding="utf-8"))
        requested = [value.strip() for value in args.families.split(",") if value.strip()]
        metrics: list[dict[str, str]] = []
        for family in requested:
            if family not in seed.get("families", {}):
                raise ValueError(f"unknown seed family: {family}")
            for name in seed["families"][family]:
                suffix = "_单季" if args.statement_variant == "单季度" and family in {"INCOME_STATEMENT", "CASH_FLOW"} else ""
                key = f"{family.lower()}.{name}{suffix}"
                metrics.append({"key": key, "family": family, "canonical_name": name, "statement_variant": args.statement_variant})
        hits: list[dict[str, Any]] = []
        missing: list[dict[str, str]] = []
        core_pending: list[dict[str, str]] = []
        for item in metrics:
            key = item["key"]
            if payload["entries"].get(key, {}).get("invalidated"):
                missing.append(item)
                continue
            if key in payload["entries"]:
                hits.append({**item, "cache_source": "runtime", "entry": payload["entries"][key]})
            elif key in core["entries"] and core_compatible:
                hits.append({**item, "cache_source": "bundled_core", "entry": core["entries"][key]})
            else:
                missing.append(item)
                if key in core["entries"]:
                    core_pending.append(item)
        batches = [missing[index:index + args.batch_size] for index in range(0, len(missing), args.batch_size)]
        print(json.dumps({
            "cache_hits": hits,
            "missing": missing,
            "core_candidates_needing_runtime_confirmation": core_pending,
            "core_runtime_compatibility_version": core_version,
            "statement_variant": args.statement_variant,
            "discovery_batches": batches,
        }, ensure_ascii=False, indent=2))
        return
    if not args.key:
        parser.error("--key is required")
    if args.action == "get":
        entry = payload["entries"].get(args.key)
        if entry and entry.get("invalidated"):
            print("null")
            return
        source = "runtime"
        if entry is None and core_compatible:
            entry = core["entries"].get(args.key)
            source = "bundled_core"
        if entry is not None:
            entry = {**entry, "_cache_source": source}
        print(json.dumps(entry, ensure_ascii=False))
        return
    if args.action == "invalidate":
        if not args.reason:
            parser.error("--reason is required for invalidate")
        previous = payload["entries"].get(args.key, core["entries"].get(args.key, {}))
        payload["entries"][args.key] = {**previous, "invalidated": True,
                                      "invalidation_reason": args.reason}
        payload["runtime_compatibility_version"] = args.runtime_version
        save(args.cache, payload)
        return
    if not args.entry_json:
        parser.error("--entry-json is required for upsert")
    entry = json.loads(args.entry_json)
    required = ("canonical_name", "statement_family", "indicator_path", "parameter_schema", "unit", "period_semantics", "evidence_run_id")
    missing = [field for field in required if entry.get(field) in (None, "")]
    if missing:
        raise ValueError(f"cache entry missing fields: {', '.join(missing)}")
    entry.pop("values", None)
    entry.pop("raw_result", None)
    entry.pop("invalidated", None)
    entry.pop("invalidation_reason", None)
    entry["verified_at"] = datetime.now(timezone.utc).isoformat()
    payload["runtime_compatibility_version"] = args.runtime_version
    payload["entries"][args.key] = entry
    save(args.cache, payload)
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
