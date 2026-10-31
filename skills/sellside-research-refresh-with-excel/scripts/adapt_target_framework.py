"""Adapt an extracted research framework to a target entity and period."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


ENTITY_ROLES = {
    "PRIMARY",
    "SUBSIDIARY_OR_BUSINESS",
    "COMPARABLE",
    "INDUSTRY_OR_SECTOR",
    "INDEX_OR_BENCHMARK",
    "MACRO",
    "EXTERNAL_EVENT_PARTY",
}
ENTITY_ACTIONS = {"REPLACE", "PRESERVE", "OMIT", "REVIEW_REQUIRED"}
ANNUAL_PERIOD = re.compile(r"^(?P<year>\d{4})(?P<kind>[AFE])$", re.I)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AdaptationError(ValueError):
    """Raised when adaptation inputs violate their contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdaptationError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AdaptationError(f"JSON root must be an object: {path}")
    return payload


def validate_framework(framework: dict[str, Any]) -> None:
    if framework.get("schema_version") != 1:
        raise AdaptationError("metric framework schema_version must be 1")
    completeness = framework.get("completeness")
    if not isinstance(completeness, dict) or completeness.get("status") != "PASS":
        raise AdaptationError("metric framework completeness must be PASS")
    if not isinstance(framework.get("objects"), list):
        raise AdaptationError("metric framework objects must be an array")
    if not isinstance(framework.get("metrics"), list):
        raise AdaptationError("metric framework metrics must be an array")


def load_confirmed_framework(handoff_path: Path) -> tuple[dict[str, Any], Path]:
    handoff = load_json(handoff_path)
    if handoff.get("stage") != 1 or handoff.get("status") != "CONFIRMED":
        raise AdaptationError("stage-1 handoff must be CONFIRMED")
    producer = handoff.get("producer")
    if (
        not isinstance(producer, dict)
        or producer.get("skill") != "sellside-research-refresh-with-excel20"
        or producer.get("version") != "2.0.0"
    ):
        raise AdaptationError("stage-1 handoff producer must be 2.0.0")
    validation = handoff.get("validation")
    if not isinstance(validation, list) or any(
        not isinstance(item, dict) or item.get("status") != "PASS"
        for item in validation
    ):
        raise AdaptationError("stage-1 handoff validations must all be PASS")
    outputs = handoff.get("outputs")
    if not isinstance(outputs, list):
        raise AdaptationError("stage-1 handoff outputs must be an array")
    framework_artifacts = [
        item
        for item in outputs
        if isinstance(item, dict)
        and Path(str(item.get("path", ""))).name == "metric_framework.json"
    ]
    if len(framework_artifacts) != 1:
        raise AdaptationError("stage-1 handoff must contain one metric_framework.json")
    artifact_item = framework_artifacts[0]
    framework_path = Path(str(artifact_item["path"]))
    if not framework_path.is_absolute() or not framework_path.is_file():
        raise AdaptationError("stage-1 metric framework path must be an existing absolute file")
    if artifact_item.get("size_bytes") != framework_path.stat().st_size:
        raise AdaptationError("stage-1 metric framework size mismatch")
    if str(artifact_item.get("sha256", "")).lower() != sha256_file(framework_path):
        raise AdaptationError("stage-1 metric framework hash mismatch")
    framework = load_json(framework_path)
    validate_framework(framework)
    return framework, framework_path.resolve()


def blocker(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def normalize_entity_request(
    request: dict[str, Any], blockers: list[dict[str, Any]]
) -> dict[str, Any]:
    entities = request.get("source_entities")
    if not isinstance(entities, list):
        blockers.append(blocker("SOURCE_ENTITIES_REQUIRED", "source_entities must be an array"))
        entities = []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(entities, start=1):
        if not isinstance(item, dict):
            blockers.append(
                blocker("INVALID_ENTITY", f"source_entities[{index}] must be an object")
            )
            continue
        entity_id = str(item.get("entity_id", "")).strip()
        name = str(item.get("name", "")).strip()
        role = str(item.get("role", "")).upper()
        if not entity_id or not name or role not in ENTITY_ROLES:
            blockers.append(
                blocker(
                    "INVALID_ENTITY",
                    f"source_entities[{index}] requires entity_id, name and a valid role",
                )
            )
            continue
        normalized.append(
            {
                "entity_id": entity_id,
                "name": name,
                "role": role,
                "code": str(item.get("code", "")).strip(),
            }
        )

    primaries = [item for item in normalized if item["role"] == "PRIMARY"]
    if len(primaries) != 1:
        blockers.append(
            blocker(
                "PRIMARY_ENTITY_AMBIGUOUS",
                "Exactly one source PRIMARY entity is required",
                count=len(primaries),
            )
        )

    target = request.get("target_entity")
    if not isinstance(target, dict):
        blockers.append(blocker("TARGET_ENTITY_REQUIRED", "target_entity must be an object"))
        target = {}
    target_id = str(target.get("entity_id", "")).strip()
    target_name = str(target.get("name", "")).strip()
    if not target_id or not target_name:
        blockers.append(
            blocker(
                "TARGET_ENTITY_INCOMPLETE",
                "target_entity requires stable entity_id and name",
            )
        )

    overrides = request.get("entity_overrides", {})
    if not isinstance(overrides, dict):
        blockers.append(blocker("INVALID_ENTITY_OVERRIDES", "entity_overrides must be an object"))
        overrides = {}

    mappings: list[dict[str, Any]] = []
    for item in normalized:
        override = overrides.get(item["entity_id"], {})
        if not isinstance(override, dict):
            blockers.append(
                blocker(
                    "INVALID_ENTITY_OVERRIDE",
                    f"Override for {item['entity_id']} must be an object",
                )
            )
            override = {}
        if item["role"] == "PRIMARY":
            action = "REPLACE"
            mapped_id = target_id
            mapped_name = target_name
        else:
            default_action = (
                "REVIEW_REQUIRED"
                if item["role"] == "SUBSIDIARY_OR_BUSINESS"
                else "PRESERVE"
            )
            action = str(override.get("action", default_action)).upper()
            if action not in ENTITY_ACTIONS:
                blockers.append(
                    blocker(
                        "INVALID_ENTITY_ACTION",
                        f"Invalid action for {item['entity_id']}: {action}",
                    )
                )
                action = default_action
            mapped_id = str(override.get("target_entity_id", item["entity_id"])).strip()
            mapped_name = str(override.get("target_name", item["name"])).strip()
            if action == "REPLACE" and (not mapped_id or not mapped_name):
                blockers.append(
                    blocker(
                        "REPLACEMENT_ENTITY_INCOMPLETE",
                        f"Replacement for {item['entity_id']} requires target entity fields",
                    )
                )
        if action == "REVIEW_REQUIRED":
            blockers.append(
                blocker(
                    "ENTITY_REVIEW_REQUIRED",
                    f"Entity {item['name']} requires an explicit preserve, replace or omit action",
                    entity_id=item["entity_id"],
                )
            )
        mappings.append(
            {
                "source_entity_id": item["entity_id"],
                "source_name": item["name"],
                "role": item["role"],
                "action": action,
                "target_entity_id": mapped_id if action != "OMIT" else "",
                "target_name": mapped_name if action != "OMIT" else "",
                "reason": str(override.get("reason", "")).strip(),
            }
        )

    return {
        "source_primary": primaries[0] if len(primaries) == 1 else None,
        "target_primary": {
            "entity_id": target_id,
            "name": target_name,
            "code": str(target.get("code", "")).strip(),
        },
        "mappings": mappings,
    }


def all_periods(framework: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for metric in framework["metrics"]:
        periods = metric.get("periods", [])
        if isinstance(periods, list):
            for period in periods:
                text = str(period).strip()
                if text and text not in result:
                    result.append(text)
    return result


def map_periods(
    framework: dict[str, Any],
    request: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    periods = all_periods(framework)
    target_anchor = str(request.get("target_actual_anchor", "")).upper().strip()
    target_match = ANNUAL_PERIOD.fullmatch(target_anchor)
    if target_match is None or target_match.group("kind").upper() != "A":
        blockers.append(
            blocker(
                "TARGET_ACTUAL_ANCHOR_INVALID",
                "target_actual_anchor must use YYYYA format",
                value=target_anchor,
            )
        )

    actual_years = sorted(
        {
            int(match.group("year"))
            for period in periods
            if (match := ANNUAL_PERIOD.fullmatch(period.upper()))
            and match.group("kind").upper() == "A"
        }
    )
    source_anchor = f"{actual_years[-1]}A" if actual_years else ""
    if not actual_years:
        blockers.append(
            blocker(
                "SOURCE_ACTUAL_ANCHOR_MISSING",
                "No annual actual period is available to anchor automatic mapping",
            )
        )
    target_year = int(target_match.group("year")) if target_match else None
    year_shift = target_year - actual_years[-1] if target_year is not None and actual_years else None

    explicit = request.get("explicit_period_mappings", {})
    if not isinstance(explicit, dict):
        blockers.append(
            blocker("INVALID_PERIOD_MAPPINGS", "explicit_period_mappings must be an object")
        )
        explicit = {}

    mappings: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for period in periods:
        explicit_target = explicit.get(period)
        if explicit_target:
            mapped = str(explicit_target).strip()
            mappings.append(
                {
                    "source_period": period,
                    "target_period": mapped,
                    "method": "EXPLICIT",
                    "semantics_preserved": True,
                }
            )
            continue
        annual = ANNUAL_PERIOD.fullmatch(period.upper())
        if annual and year_shift is not None:
            mapped = f"{int(annual.group('year')) + year_shift}{annual.group('kind').upper()}"
            mappings.append(
                {
                    "source_period": period,
                    "target_period": mapped,
                    "method": "ANNUAL_SHIFT",
                    "semantics_preserved": True,
                }
            )
            continue
        unresolved.append(period)
        blockers.append(
            blocker(
                "PERIOD_MAPPING_REQUIRED",
                f"Explicit mapping is required for non-annual period {period}",
                source_period=period,
            )
        )

    data_cutoff = str(request.get("data_cutoff", "")).strip()
    try:
        cutoff = date.fromisoformat(data_cutoff)
    except ValueError:
        cutoff = None
        blockers.append(
            blocker("DATA_CUTOFF_INVALID", "data_cutoff must use YYYY-MM-DD format")
        )
    if cutoff is not None:
        for item in mappings:
            mapped = item["target_period"]
            if ISO_DATE.fullmatch(mapped):
                mapped_date = date.fromisoformat(mapped)
                if mapped_date > cutoff:
                    blockers.append(
                        blocker(
                            "PERIOD_AFTER_CUTOFF",
                            f"Mapped actual date {mapped} is after data cutoff {data_cutoff}",
                            source_period=item["source_period"],
                        )
                    )

    return {
        "source_actual_anchor": source_anchor,
        "target_actual_anchor": target_anchor,
        "year_shift": year_shift,
        "data_cutoff": data_cutoff,
        "mappings": mappings,
        "unresolved": unresolved,
    }


def period_lookup(period_mapping: dict[str, Any]) -> dict[str, str]:
    return {
        item["source_period"]: item["target_period"]
        for item in period_mapping["mappings"]
    }


def coverage_id(framework_id: str, target_entity_id: str, periods: list[str]) -> str:
    token = f"{framework_id}|{target_entity_id}|{'|'.join(periods)}".encode("utf-8")
    return f"cov-{hashlib.sha256(token).hexdigest()[:16]}"


def report_priority(metric: dict[str, Any]) -> str:
    if metric.get("object_type") == "FORECAST":
        return "CORE"
    if metric.get("status") in {"SUCCESS", "FAILED"}:
        return "CORE"
    return "SUPPORTING"


def build_coverage(
    framework: dict[str, Any],
    entity_mapping: dict[str, Any],
    period_mapping: dict[str, Any],
) -> list[dict[str, Any]]:
    lookup = period_lookup(period_mapping)
    target_id = entity_mapping["target_primary"]["entity_id"]
    rows: list[dict[str, Any]] = []
    for metric in framework["metrics"]:
        source_periods = [str(item) for item in metric.get("periods", [])]
        target_periods = [lookup.get(item, "") for item in source_periods]
        disposition = (
            "not_applicable"
            if metric.get("status") == "NOT_APPLICABLE"
            else "planned_mql"
        )
        rows.append(
            {
                "coverage_id": coverage_id(
                    str(metric["framework_id"]), target_id, target_periods
                ),
                "framework_id": metric["framework_id"],
                "object_id": metric["object_id"],
                "metric_name": metric["metric_name"],
                "target_entity_id": target_id,
                "target_entity_name": entity_mapping["target_primary"]["name"],
                "source_periods": source_periods,
                "target_periods": target_periods,
                "frequency": metric.get("frequency", "UNSPECIFIED"),
                "actual_forecast": metric.get("actual_forecast", "UNSPECIFIED"),
                "unit": metric.get("unit", ""),
                "indicator_path_hint": metric.get("indicator_path", ""),
                "disposition": disposition,
                "reason": (
                    metric.get("mapping_note", "")
                    if disposition == "not_applicable"
                    else ""
                ),
                "report_priority": report_priority(metric),
                "source_location": metric.get("source_location", ""),
            }
        )
    return rows


def build_table_mapping(
    framework: dict[str, Any], coverage: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_object: dict[str, list[dict[str, Any]]] = {}
    for item in coverage:
        by_object.setdefault(item["object_id"], []).append(item)
    rows: list[dict[str, Any]] = []
    for item in framework["objects"]:
        related = by_object.get(item["object_id"], [])
        all_not_applicable = bool(related) and all(
            row["disposition"] == "not_applicable" for row in related
        )
        action = "omit_with_reason" if all_not_applicable else "adapt"
        rows.append(
            {
                "source_object_id": item["object_id"],
                "target_object_id": f"target-{item['object_id']}",
                "object_type": item["object_type"],
                "source_title": item["title"],
                "target_title": item["title"],
                "action": action,
                "coverage_ids": [row["coverage_id"] for row in related],
                "reason": (
                    "All source metrics are explicitly not applicable to the target"
                    if all_not_applicable
                    else "Adapt source structure using target facts"
                ),
            }
        )
    return rows


def normalize_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", "", text)


def normalize_url(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    parts = urlsplit(text)
    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            parts.path.rstrip("/"),
            parts.query,
            "",
        )
    )


def build_information_rows(
    request: dict[str, Any],
    entity_mapping: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    raw = request.get("information_items", [])
    if not isinstance(raw, list):
        blockers.append(blocker("INVALID_INFORMATION_ITEMS", "information_items must be an array"))
        return []
    target_id = entity_mapping["target_primary"]["entity_id"]
    cutoff_text = str(request.get("data_cutoff", "")).strip()
    try:
        cutoff = date.fromisoformat(cutoff_text)
    except ValueError:
        cutoff = None
    by_key: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            blockers.append(
                blocker("INVALID_INFORMATION_ITEM", f"information_items[{index}] must be an object")
            )
            continue
        title = str(item.get("title", "")).strip()
        published_at = str(item.get("published_at", "")).strip()
        url = normalize_url(str(item.get("url", "")))
        if not title or not published_at or not str(item.get("source_id", "")).strip():
            blockers.append(
                blocker(
                    "INFORMATION_ITEM_INCOMPLETE",
                    f"information_items[{index}] requires title, published_at and source_id",
                )
            )
            continue
        try:
            published_date = date.fromisoformat(published_at)
        except ValueError:
            blockers.append(
                blocker(
                    "INFORMATION_DATE_INVALID",
                    f"information_items[{index}].published_at must use YYYY-MM-DD",
                )
            )
            continue
        if cutoff is not None and published_date > cutoff:
            blockers.append(
                blocker(
                    "INFORMATION_AFTER_CUTOFF",
                    f"information_items[{index}] is after data cutoff {cutoff_text}",
                )
            )
            continue
        key_material = "|".join(
            (target_id, normalize_title(title), published_at, url)
        )
        dedup_key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
        row = {
            "dedup_key": dedup_key,
            "target_entity_id": target_id,
            "title": title,
            "source_organization": str(item.get("source_organization", "")).strip(),
            "published_at": published_at,
            "url": url,
            "summary": str(item.get("summary", "")).strip(),
            "report_location": str(item.get("report_location", "")).strip(),
            "source_id": str(item.get("source_id", "")).strip(),
        }
        existing = by_key.get(dedup_key)
        if existing is not None and existing != row:
            blockers.append(
                blocker(
                    "INFORMATION_DEDUP_CONFLICT",
                    f"Conflicting information rows share dedup key {dedup_key}",
                    dedup_key=dedup_key,
                )
            )
            continue
        by_key[dedup_key] = row
    return list(by_key.values())


def adapt_framework(
    framework: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    validate_framework(framework)
    blockers: list[dict[str, Any]] = []
    entity_mapping = normalize_entity_request(request, blockers)
    period_mapping = map_periods(framework, request, blockers)
    coverage = build_coverage(framework, entity_mapping, period_mapping)
    target_mapping = build_table_mapping(framework, coverage)
    information = build_information_rows(request, entity_mapping, blockers)

    missing_period_coverage = [
        row["coverage_id"]
        for row in coverage
        if row["source_periods"] and any(not value for value in row["target_periods"])
    ]
    if missing_period_coverage:
        blockers.append(
            blocker(
                "COVERAGE_PERIOD_UNRESOLVED",
                "Coverage rows contain unresolved target periods",
                coverage_ids=missing_period_coverage,
            )
        )

    return {
        "schema_version": 1,
        "status": "BLOCKED" if blockers else "PASS",
        "blockers": blockers,
        "source_framework": {
            "task_id": framework["source_handoff"]["task_id"],
            "workbook_sha256": framework["source_workbook"]["sha256"],
        },
        "entity_mapping": entity_mapping,
        "period_mapping": period_mapping,
        "coverage_requirements": coverage,
        "target_table_mapping": target_mapping,
        "information_rows": information,
        "summary": {
            "entities": len(entity_mapping["mappings"]),
            "periods": len(period_mapping["mappings"]),
            "coverage": len(coverage),
            "objects": len(target_mapping),
            "information_rows": len(information),
            "dispositions": dict(Counter(item["disposition"] for item in coverage)),
        },
    }


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "media_type": "application/json",
    }


def write_outputs(
    bundle: dict[str, Any],
    stage1_handoff_path: Path,
    framework_path: Path,
    request_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "entity_mapping.json": bundle["entity_mapping"],
        "period_mapping.json": bundle["period_mapping"],
        "coverage_requirements.json": bundle["coverage_requirements"],
        "target_table_mapping.json": bundle["target_table_mapping"],
        "information_rows.json": bundle["information_rows"],
    }
    paths: list[Path] = []
    for name, payload in outputs.items():
        path = output_dir / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths.append(path)

    handoff_path = output_dir / "stage-2-handoff.json"
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    handoff = {
        "schema_version": 1,
        "task_id": bundle["source_framework"]["task_id"],
        "stage": 2,
        "status": (
            "BLOCKED" if bundle["status"] == "BLOCKED" else "CONFIRMED"
        ),
        "producer": {
            "skill": "sellside-research-refresh-with-excel20",
            "version": "2.0.0",
            "mode": "目标适配与取数计划",
        },
        "inputs": [
            artifact(stage1_handoff_path),
            artifact(framework_path),
            artifact(request_path),
        ],
        "outputs": [artifact(path) for path in paths],
        "started_at": timestamp,
        "completed_at": timestamp,
        "validation": [
            {
                "name": "target adaptation gates",
                "status": "FAIL" if bundle["blockers"] else "PASS",
            }
        ],
        "limitations": [],
        "error": (
            {
                "category": "ADAPTATION_BLOCKED",
                "message": "Entity, period or information mapping requires resolution",
                "blockers": bundle["blockers"],
            }
            if bundle["blockers"]
            else None
        ),
        "resume": {
            "next_stage": 2 if bundle["blockers"] else 3,
            "requires_user_confirmation": False,
            "input_hashes": {
                str(framework_path.resolve()): sha256_file(framework_path),
                str(stage1_handoff_path.resolve()): sha256_file(stage1_handoff_path),
                str(request_path.resolve()): sha256_file(request_path),
            },
        },
    }
    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return handoff


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage1_handoff", type=Path)
    parser.add_argument("request", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    framework, framework_path = load_confirmed_framework(args.stage1_handoff)
    request = load_json(args.request)
    bundle = adapt_framework(framework, request)
    handoff = write_outputs(
        bundle,
        args.stage1_handoff,
        framework_path,
        args.request,
        args.output_dir,
    )
    print(
        json.dumps(
            {
                "status": bundle["status"],
                "handoff": str((args.output_dir / "stage-2-handoff.json").resolve()),
                "coverage": len(bundle["coverage_requirements"]),
                "blockers": len(bundle["blockers"]),
            },
            ensure_ascii=False,
        )
    )
    return 2 if handoff["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
