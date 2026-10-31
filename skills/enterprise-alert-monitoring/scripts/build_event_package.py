#!/usr/bin/env python3
"""Build source-preserving event packages from saved mx_api_invoke returns; no network.

Channel contract (kept verbatim from the two enabled catalog entries):
- newsEventSearch    -> 已发生事件（事件大全），list path data.eventItemList
- futureEventSearch  -> 未来预期事件（未来行动事件），list path data.futureEventSearchItemList

The script only normalizes, deduplicates, fingerprints and re-binds returned
records; it never invents citations, URLs, risk grades or event facts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import build_news_package as news
import prepare_inputs as prepare

InputError = prepare.InputError
SUPPORTED_APIS = ("newsEventSearch", "futureEventSearch")
API_LABELS = {
    "newsEventSearch": "已发生事件（事件大全）",
    "futureEventSearch": "未来预期事件（未来行动事件）",
}
MATERIAL_KINDS = {"newsEventSearch": "event", "futureEventSearch": "future_event"}
KIND_LABELS = {"event": "已发生事件", "future_event": "未来预期事件"}
EVENT_LIST_KEYS = ("eventItemList", "futureEventSearchItemList")
EVENT_EXTRA_FIELDS = ("org_name", "org_code", "security_code", "first_tag", "second_tag",
                      "industry", "risk_level", "risk_flag", "info_code", "native_event_id", "happen_time")
RISK_FLAGS = {-1: "负面", 0: "中性", 1: "正面", -2: "无"}


def _pick(node, *keys):
    for key in keys:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _risk_label(node):
    label = _pick(node, "riskLevelName")
    if label:
        return label
    raw = node.get("riskLevel", node.get("risk"))
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, bool) or raw is None:
        return "未标注"
    return RISK_FLAGS.get(raw, "未标注")


def _first_company_code(node):
    beans = node.get("companyBeanList")
    if isinstance(beans, list) and beans and isinstance(beans[0], dict):
        return _pick(beans[0], "secuFullCode")
    return ""


def event_unit(node, api_id):
    """Normalize one returned record; missing title/digest yields None (fail closed)."""
    item = {name: news._field(node, name) for name in news.ALIASES}
    if not _pick(node, "eventTitle", "eventMessage") and not item["title"].strip():
        return None
    if not _pick(node, "eventDigest", "eventMessage") and not item["content"].strip():
        return None
    item["title"] = _pick(node, "eventTitle", "eventMessage") or item["title"]
    item["content"] = _pick(node, "eventDigest", "eventMessage") or item["content"]
    if not item["content"].strip() or not item["title"].strip():
        return None
    item["source"] = _pick(node, "medianame") or item["source"]
    item["material_kind"] = MATERIAL_KINDS[api_id]
    item["title_origin"] = "original"
    if item["url"]:
        prepare.validate_url(item["url"], "returned_event_url")
    item["org_name"] = _pick(node, "orgName", "originCompanyName")
    item["org_code"] = _pick(node, "orgCode")
    item["security_code"] = _pick(node, "securityCode") or _first_company_code(node)
    item["first_tag"] = _pick(node, "firstTagName", "eventType")
    item["second_tag"] = _pick(node, "secondaryTagName", "secondTagName")
    item["industry"] = _pick(node, "industryName", "eventIndustry")
    item["risk_level"] = _risk_label(node)
    raw_flag = node.get("riskLevel", node.get("risk"))
    item["risk_flag"] = "" if raw_flag is None else str(raw_flag).strip()
    item["info_code"] = _pick(node, "infoCode", "infocode")
    item["native_event_id"] = _pick(node, "eventId", "futureEventId")
    item["happen_time"] = _pick(node, "happenTime")
    return item


def extract_event_records(payload, api_id):
    """Read the two known list paths; unknown shapes fail closed with notes."""
    notes = []
    if not isinstance(payload, dict):
        raise InputError("event raw result must be a JSON object")
    if news.safe_value(payload).get("need_auth") is True or payload.get("error"):
        return [], ["search_not_successful"]
    code = payload.get("code")
    if code not in (0, 200):
        return [], [f"api_code_{code}"]
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}
    records = None
    for key in EVENT_LIST_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            records = value
            break
    if records is None:
        return [], ["event_list_not_found"]
    units, seen_native = [], set()
    for record in records:
        if not isinstance(record, dict):
            notes.append("non_object_record_skipped")
            continue
        native = _pick(record, "infoCode", "infocode") or _pick(record, "eventId", "futureEventId")
        unit = event_unit(record, api_id)
        if unit is None:
            notes.append("record_missing_title_or_digest")
            continue
        if native and native in seen_native:
            notes.append("duplicate_native_record_kept_once")
            continue
        if native:
            seen_native.add(native)
        units.append(unit)
    return units, notes


def _stable_event_id(item):
    original = {key: value for key, value in item.items() if key != "source_assessment"}
    encoded = json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "evt_" + hashlib.sha256(encoded).hexdigest()[:24]


def build_event_candidates(manifest, base_dir=None):
    started = time.perf_counter()
    if not isinstance(manifest, dict):
        raise InputError("manifest must be an object")
    name, code = prepare.validate_entity(manifest.get("entity"))
    context = prepare.context_projection(manifest.get("context"))
    searches = manifest.get("event_searches")
    if not isinstance(searches, list) or not searches:
        raise InputError("manifest.event_searches must be a nonempty list covering both event APIs")
    if {"blocks", "block_keys", "block_candidates", "searches"}.intersection(manifest):
        raise InputError("manifest must describe one shared event pool; news searches stay in their own manifest")
    base_dir = Path(base_dir or ".").resolve()
    entity = {"name": name, "confirmed": True}
    if code:
        entity["org_code"] = code
    bundle = {"schema_version": "1.0", "acquisition": "mx-api-invoke", "entity": entity, "context": context,
              "catalog": {}, "candidate_ids": [], "queries": [], "origins": {}}
    audit = {"schema_version": "1.0", "event_searches": [], "duplicate_records_reused": 0}
    initial_seen = set()
    for index, search in enumerate(searches):
        if not isinstance(search, dict):
            raise InputError("event search record must be an object")
        if {"block_keys", "blocks", "block_key"}.intersection(search):
            raise InputError("chapter-specific event routing is not supported")
        api_id = prepare.text(search.get("api_id"), "event_search.api_id")
        if api_id not in SUPPORTED_APIS:
            raise InputError(f"event_search.api_id must be one of {SUPPORTED_APIS}")
        query = prepare.text(search.get("query"), "event_search.query")
        kind = search.get("kind", "initial")
        if kind not in {"initial", "supplement"}:
            raise InputError("event_search.kind must be initial or supplement")
        if kind == "initial":
            if api_id in initial_seen:
                raise InputError(f"only one initial search is allowed for {api_id}")
            initial_seen.add(api_id)
        reason = prepare.text(search.get("reason", ""), "event_search.reason", empty=kind == "initial")
        status = search.get("status")
        if status not in {"success", "empty", "failed", "need_auth"}:
            raise InputError("event_search.status must be success, empty, failed or need_auth")
        raw_name = prepare.text(search.get("raw_result_path"), "event_search.raw_result_path")
        raw_path = Path(raw_name)
        raw_path = (base_dir / raw_path).resolve() if not raw_path.is_absolute() else raw_path.resolve()
        record = {"api_id": api_id, "api_label": API_LABELS[api_id], "query": query, "kind": kind,
                  "reason": reason, "status": status, "raw_result_path": str(raw_path),
                  "notes": [], "candidate_ids": []}
        if status == "success":
            units, record["notes"] = extract_event_records(news._read_result(raw_path), api_id)
            if not units and "event_list_not_found" in record["notes"]:
                record["status"] = "unsupported"
            elif not units:
                record["status"] = "empty"
            for item in units:
                source_id = _stable_event_id(item)
                item = {"id": source_id, **item, "source_assessment": prepare.assess_source(item)}
                if source_id in bundle["catalog"]:
                    audit["duplicate_records_reused"] += 1
                else:
                    bundle["catalog"][source_id] = item
                    bundle["origins"][source_id] = []
                    bundle["candidate_ids"].append(source_id)
                bundle["origins"][source_id].append({"search_index": index, "api_id": api_id, "query": query,
                                                     "kind": kind, "raw_result_path": str(raw_path)})
                if source_id not in record["candidate_ids"]:
                    record["candidate_ids"].append(source_id)
        entry = {"search_index": index, "api_id": api_id, "api_label": API_LABELS[api_id], "query": query,
                 "kind": kind, "reason": reason, "status": record["status"],
                 "raw_result_path": str(raw_path), "start_date": context["start_date"],
                 "end_date": context["end_date"], "returned_count": len(record["candidate_ids"])}
        if isinstance(search.get("elapsed_seconds"), (int, float)):
            entry["elapsed_seconds"] = search["elapsed_seconds"]
        bundle["queries"].append(entry)
        record["notes"] = list(dict.fromkeys(record["notes"]))
        audit["event_searches"].append(record)
    for api_id in SUPPORTED_APIS:
        if api_id not in initial_seen:
            raise InputError(f"manifest.event_searches must include one initial search for {api_id}")
    indexed = enumerate(bundle["candidate_ids"])
    bundle["candidate_ids"] = [source_id for _, source_id in sorted(
        indexed, key=lambda pair: prepare.item_sort_key({**bundle["catalog"][pair[1]], "_index": pair[0]}))]
    audit["candidate_sort_keys"] = ["authority_v2_priority", "published_at_desc", "original_index"]
    audit["candidate_count"] = len(bundle["catalog"])
    audit["kind_counts"] = {
        KIND_LABELS[kind]: sum(1 for item in bundle["catalog"].values() if item["material_kind"] == kind)
        for kind in ("event", "future_event")}
    audit["shared_candidate_ids"] = bundle["candidate_ids"]
    audit["elapsed_seconds"] = time.perf_counter() - started
    return bundle, audit


def compose_event_package(bundle, selection):
    started = time.perf_counter()
    if not isinstance(bundle, dict) or bundle.get("acquisition") != "mx-api-invoke":
        raise InputError("candidate bundle must originate from mx-api-invoke event searches")
    name, code = prepare.validate_entity(bundle.get("entity"))
    context = prepare.context_projection(bundle.get("context"))
    catalog = bundle.get("catalog")
    candidates = bundle.get("candidate_ids")
    if {"block_candidates", "blocks", "block_keys"}.intersection(bundle):
        raise InputError("candidate bundle must use one shared catalog, not chapter-specific routing")
    if (not isinstance(catalog, dict) or not isinstance(candidates, list)
            or any(not isinstance(i, str) or i not in catalog for i in candidates)
            or len(set(candidates)) != len(candidates) or set(candidates) != set(catalog)):
        raise InputError("candidate_ids must list each shared catalog ID exactly once")
    queries = bundle.get("queries")
    if not isinstance(queries, list) or any(not isinstance(q, dict) for q in queries):
        raise InputError("candidate queries must be one shared list")
    if not isinstance(selection, dict) or set(selection) - {"selected_ids"}:
        raise InputError("selection permits selected_ids only; no rewritten items or forged events")
    chosen = selection.get("selected_ids")
    if (not isinstance(chosen, list) or any(not isinstance(i, str) or i not in catalog for i in chosen)
            or len(set(chosen)) != len(chosen)):
        raise InputError("selection.selected_ids must be one list of unique existing event candidate IDs")
    entity = {"name": name, "confirmed": True}
    if code:
        entity["org_code"] = code
    items = []
    for source_id in chosen:
        item = catalog[source_id]
        if not isinstance(item, dict) or item.get("id") != source_id:
            raise InputError("candidate ID and record binding disagree")
        if _stable_event_id({k: v for k, v in item.items() if k != "id"}) != source_id:
            raise InputError("candidate content or provenance changed after build; rebuild from original return")
        allowed = {"id", *prepare.EVENT_ITEM_FIELDS}
        original = {k: v for k, v in item.items() if k in allowed}
        items.append({**original, "source_assessment": prepare.assess_source(original)})
    prepare.validate_event_items(items, "shared-events")
    package = {"acquisition": "mx-api-invoke", "entity": entity, "context": context,
               "event_queries": news.safe_value(queries), "items": items}
    audit = {"schema_version": "1.0", "candidate_count": len(catalog), "selected_ids": chosen,
             "selected_count": len(chosen), "excluded_candidate_ids": [i for i in candidates if i not in chosen],
             "kind_counts": {
                 KIND_LABELS[kind]: sum(1 for item in items if item["material_kind"] == kind)
                 for kind in ("event", "future_event")}}
    audit["elapsed_seconds"] = time.perf_counter() - started
    audit["selection_characters"] = len(json.dumps(selection, ensure_ascii=False))
    return package, audit


def candidate_event_index(bundle):
    lines = ["# 共享事件库候选索引", "",
             "全部章节共用本索引和同一事件池。条目分两类：已发生事件（事件大全）与未来预期事件（未来行动事件）。"
             "索引只用于选题；发酵判断与事实核验仍须阅读摘要与原文链接，接口风险标注不代表企业风险结论。", ""]
    for source_id in bundle["candidate_ids"]:
        item = bundle["catalog"][source_id]
        grade = prepare.assess_source(item)
        happen = f"｜预计 {item['happen_time']}" if item["happen_time"] else ""
        lines.append(
            f"- `{source_id}` | {KIND_LABELS[item['material_kind']]} | {item['title']} | {item['published_at']}"
            f"{happen} | {item['org_name']} | {item['second_tag'] or item['first_tag']} | 接口风险标注：{item['risk_level']}"
            f" | {grade['source_category_v2']} | 权威度：{grade['authority_v2']}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build one shared event candidate pool from saved mx_api_invoke returns")
    build.add_argument("--manifest", required=True)
    build.add_argument("--out", required=True)
    compose = commands.add_parser("compose", help="compose the shared event package from a selection")
    compose.add_argument("--bundle", required=True)
    compose.add_argument("--selection", required=True)
    compose.add_argument("--out", required=True)
    inspect = commands.add_parser("inspect", help="print full candidate records for given IDs")
    inspect.add_argument("--bundle", required=True)
    inspect.add_argument("--ids", nargs="+", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            path = Path(args.manifest).resolve()
            bundle, audit = build_event_candidates(json.loads(path.read_text(encoding="utf-8-sig")), path.parent)
            news._write_new(args.out, {"event_bundle.json": bundle,
                                       "candidate_event_index.md": candidate_event_index(bundle),
                                       "event_build_audit.json": audit},
                            [path, *(s["raw_result_path"] for s in audit["event_searches"])])
            print(json.dumps({"status": "event_candidates_built", "candidate_count": audit["candidate_count"],
                              "kind_counts": audit["kind_counts"], "out": str(Path(args.out).resolve()),
                              "elapsed_seconds": audit["elapsed_seconds"]}, ensure_ascii=False))
        else:
            bundle_path = Path(args.bundle).resolve()
            bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
            if args.command == "inspect":
                if any(i not in bundle["catalog"] for i in args.ids):
                    raise InputError("inspect requested unknown candidate IDs")
                print(json.dumps([bundle["catalog"][i] for i in args.ids], ensure_ascii=False, indent=2))
            else:
                selection_path = Path(args.selection).resolve()
                package, audit = compose_event_package(bundle, json.loads(selection_path.read_text(encoding="utf-8-sig")))
                news._write_new(args.out, {"event_package.json": package, "event_compose_audit.json": audit},
                                [bundle_path, selection_path])
                print(json.dumps({"status": "event_package_composed", "out": str(Path(args.out).resolve()),
                                  "selected_count": audit["selected_count"],
                                  "elapsed_seconds": audit["elapsed_seconds"]}, ensure_ascii=False))
        return 0
    except (InputError, OSError, ValueError, KeyError, TypeError) as exc:
        print("INPUT_ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
