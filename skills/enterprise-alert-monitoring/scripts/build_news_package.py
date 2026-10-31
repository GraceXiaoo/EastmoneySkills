#!/usr/bin/env python3
"""Build source-preserving news packages from saved search results; no network."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import prepare_inputs as prepare

InputError = prepare.InputError
ALIASES = {
    "title": ("title", "newsTitle", "articleTitle", "标题"),
    "content": ("content", "body", "text", "newsContent", "正文"),
    "source": ("source", "sourceName", "publisher", "mediaName", "来源机构", "来源"),
    "published_at": ("published_at", "publishedAt", "publishTime", "releaseTime", "date", "发布时间"),
    "url": ("url", "sourceUrl", "articleUrl", "jumpUrl", "link", "原文URL", "URL"),
    "citation": ("citation", "citation_marker", "referenceMarker", "原始引用", "引用"),
    "source_category": ("source_category", "sourceCategory", "来源分类", "来源类别", "来源类别原值"),
    "authority_level": ("authorityLevel", "authority_level", "权威度", "权威度原值"),
    "information_type": ("informationType", "information_type", "资讯类型", "资讯类型原值"),
}
CONTAINERS = ("raw", "data", "result", "items", "articles", "news", "newsList", "results", "documents")
SUMMARY_KEYS = ("llmSearchResponse", "searchResponse", "answer", "summary")
MARKERS = re.compile(r"\[source:[^\]\r\n]+\]")
SECRET_KEYS = {"api_key", "apikey", "em_api_key", "password", "token", "access_token", "refresh_token",
               "authorization", "headers", "user_info", "userinfo", "toolcontext", "credentials", "secret"}


def safe_value(value):
    """Keep business responses, excluding authentication/context objects at any depth."""
    if isinstance(value, dict):
        return {k: safe_value(v) for k, v in value.items() if str(k).lower() not in SECRET_KEYS}
    if isinstance(value, list):
        return [safe_value(v) for v in value]
    return value


def _field(node, name):
    for alias in ALIASES[name]:
        if alias in node:
            value = node[alias]
            return value if isinstance(value, str) else ""
    return ""


def _unit(node, *, summary=False, query=""):
    item = {name: _field(node, name) for name in ALIASES}
    if not item["content"].strip():
        return None
    if not summary and not item["title"].strip():
        return None
    item["material_kind"] = "search_summary" if summary else "article"
    item["title_origin"] = "original"
    if summary and not item["title"].strip():
        item["title"] = "检索汇总材料" + ("：" + query if query else "")
        item["title_origin"] = "material_label"
    # Only copy markers that actually occur in the returned text; never synthesize source IDs.
    if not item["citation"]:
        item["citation"] = "\n".join(dict.fromkeys(MARKERS.findall(item["content"])))
    if item["url"]:
        prepare.validate_url(item["url"], "returned_source_url")
    return item


def _text_units(value, query):
    """Accept JSON text or the explicitly labelled title/metadata/body text profile."""
    stripped = value.strip()
    if not stripped:
        return [], ["empty_return"]
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        decoded = None
    if decoded is not None:
        if isinstance(decoded, (dict, list)):
            return extract_units(decoded, query=query)
        return [], ["unsupported_json_scalar"]
    if stripped.startswith(("{", "[")) and not stripped.startswith("[source:"):
        return [], ["unparseable_json_return; no_model_rewrite_requested"]
    labels = {alias: field for field, aliases in ALIASES.items() for alias in aliases}
    pieces = re.split(r"(?m)^资讯原始信源\s*$", value)
    parsed = []
    for piece in pieces:
        match = re.search(r"(?m)^正文[：:]", piece)
        if not match:
            continue
        metadata = {}
        for line in piece[:match.start()].splitlines():
            pair = re.match(r"^([^：:]+)[：:](.*)$", line)
            if pair and pair.group(1).strip() in labels:
                metadata[labels[pair.group(1).strip()]] = pair.group(2).strip()
        metadata["content"] = piece[match.end():].rstrip("\r\n")
        article = _unit(metadata)
        if article:
            parsed.append(article)
    if parsed:
        return parsed, ["labelled_text_profile"]
    # Plain saved content stays one summary unit, not one fabricated article per paragraph.
    summary = _unit({"content": value}, summary=True, query=query)
    return [summary], ["plain_text_summary; provenance_must_be_checked"]


def extract_units(value, query=""):
    """Extract known article containers or explicit summary text; unknown dicts fail closed."""
    value = safe_value(value)
    if isinstance(value, str):
        return _text_units(value, query)
    if isinstance(value, list):
        units, notes = [], []
        for child in value:
            found, child_notes = extract_units(child, query=query)
            units.extend(found)
            notes.extend(child_notes)
        return units, list(dict.fromkeys(notes))
    if not isinstance(value, dict):
        return [], ["empty_return" if value is None else "unsupported_return_shape"]
    if prepare.FORBIDDEN.intersection(value) or value.get("acquisition", "mx-finance-search") != "mx-finance-search":
        raise InputError("foreign business packages cannot be relabelled as search news")
    if value.get("need_auth") is True or value.get("error"):
        return [], ["search_not_successful"]
    article = _unit(value)
    if article:
        return [article], []
    nested, notes = [], []
    for key in CONTAINERS:
        if isinstance(value.get(key), (dict, list)):
            found, child_notes = extract_units(value[key], query=query)
            nested.extend(found)
            notes.extend(child_notes)
    if nested:
        return nested, list(dict.fromkeys(notes))
    for key in SUMMARY_KEYS:
        candidate = value.get(key)
        if isinstance(candidate, (dict, list)):
            found, child_notes = extract_units(candidate, query=query)
            if found:
                return found, child_notes
        elif isinstance(candidate, str) and candidate.strip():
            try:
                decoded = json.loads(candidate)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, (dict, list)):
                return extract_units(decoded, query=query)
            item = _unit({**value, "content": candidate}, summary=True, query=query)
            return [item], ["explicit_search_summary; do_not_split_into_news"]
    # A capture wrapper can contain saved content after raw extraction failed/was unavailable.
    if isinstance(value.get("content"), str) and value["content"].strip():
        return _text_units(value["content"], query)
    return [], list(dict.fromkeys(notes + ["empty_return" if value.get("raw", 1) is None else "unsupported_return_shape"]))


def _stable_id(item):
    # Derived classification must not change original-material identity.
    original = {key: value for key, value in item.items() if key != "source_assessment"}
    encoded = json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "news_" + hashlib.sha256(encoded).hexdigest()[:24]


def _read_result(path):
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise InputError("raw result file is not valid JSON") from exc
    return text


def build_candidates(manifest, base_dir=None):
    started = time.perf_counter()
    if not isinstance(manifest, dict):
        raise InputError("manifest must be an object")
    name, code = prepare.validate_entity(manifest.get("entity"))
    context = prepare.context_projection(manifest.get("context"))
    searches = manifest.get("searches")
    if not isinstance(searches, list) or not searches:
        raise InputError("manifest.searches must be a nonempty list with one initial search")
    if {"blocks", "block_candidates", "block_keys"}.intersection(manifest):
        raise InputError("manifest must describe one shared news pool, not chapter-specific routing")
    base_dir = Path(base_dir or ".").resolve()
    entity = {"name": name, "confirmed": True}
    if code:
        entity["org_code"] = code
    bundle = {"schema_version": "1.0", "acquisition": "mx-finance-search", "entity": entity, "context": context,
              "catalog": {}, "candidate_ids": [], "queries": [], "origins": {}}
    audit = {"schema_version": "1.0", "searches": [], "duplicate_records_reused": 0}
    for index, search in enumerate(searches):
        if not isinstance(search, dict):
            raise InputError("search record must be an object")
        if {"block_keys", "blocks", "block_key"}.intersection(search):
            raise InputError("search.block_keys and chapter-specific routing are retired; use one shared search")
        query = prepare.text(search.get("query"), "search.query")
        kind = search.get("kind", "initial" if index == 0 else "supplement")
        if kind != ("initial" if index == 0 else "supplement"):
            raise InputError("only the first search may be initial; later searches must supplement an actual material gap")
        reason = prepare.text(search.get("reason", ""), "search.reason", empty=kind == "initial")
        status = search.get("status")
        if status not in {"success", "empty", "failed", "need_auth"}:
            raise InputError("search.status must be success, empty, failed or need_auth")
        raw_name = prepare.text(search.get("raw_result_path"), "search.raw_result_path")
        raw_path = Path(raw_name)
        raw_path = (base_dir / raw_path).resolve() if not raw_path.is_absolute() else raw_path.resolve()
        record = {"query": query, "kind": kind, "reason": reason, "status": status, "raw_result_path": str(raw_path),
                  "notes": [], "candidate_ids": []}
        if status == "success":
            units, record["notes"] = extract_units(_read_result(raw_path), query=query)
            if not units:
                record["status"] = "empty" if "empty_return" in record["notes"] else "unsupported"
            for item in units:
                source_id = _stable_id(item)
                item = {"id": source_id, **item, "source_assessment": prepare.assess_source(item)}
                if source_id in bundle["catalog"]:
                    audit["duplicate_records_reused"] += 1
                else:
                    bundle["catalog"][source_id] = item
                    bundle["origins"][source_id] = []
                    bundle["candidate_ids"].append(source_id)
                if not any(item.get(f) for f in ("source", "url", "citation")):
                    record["notes"].append("candidate_requires_original_source_binding")
                bundle["origins"][source_id].append({"search_index": index, "query": query, "kind": kind,
                                                      "raw_result_path": str(raw_path)})
                if source_id not in record["candidate_ids"]:
                    record["candidate_ids"].append(source_id)
        entry = {"search_index": index, "query": query, "kind": kind, "reason": reason,
                 "status": record["status"], "raw_result_path": str(raw_path),
                 "start_date": context["start_date"], "end_date": context["end_date"],
                 "returned_count": len(record["candidate_ids"])}
        if isinstance(search.get("elapsed_seconds"), (int, float)):
            entry["elapsed_seconds"] = search["elapsed_seconds"]
        bundle["queries"].append(entry)
        record["notes"] = list(dict.fromkeys(record["notes"]))
        audit["searches"].append(record)
    indexed = enumerate(bundle["candidate_ids"])
    bundle["candidate_ids"] = [source_id for _, source_id in sorted(
        indexed, key=lambda pair: prepare.item_sort_key({**bundle["catalog"][pair[1]], "_index": pair[0]}))]
    audit["candidate_sort_keys"] = ["authority_v2_priority", "published_at_desc", "original_index"]
    audit["candidate_count"] = len(bundle["catalog"])
    audit["shared_candidate_ids"] = bundle["candidate_ids"]
    audit["elapsed_seconds"] = time.perf_counter() - started
    return bundle, audit


def compose_package(bundle, selection):
    started = time.perf_counter()
    if not isinstance(bundle, dict) or bundle.get("acquisition") != "mx-finance-search":
        raise InputError("candidate bundle must originate from mx-finance-search")
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
    if any({"block_keys", "blocks", "block_key"}.intersection(q) for q in queries):
        raise InputError("candidate queries must not route by chapter")
    if not isinstance(selection, dict) or set(selection) - {"selected_ids", "events"}:
        raise InputError("selection permits selected_ids and optional events only; no rewritten items")
    chosen = selection.get("selected_ids")
    if (not isinstance(chosen, list) or any(not isinstance(i, str) or i not in catalog for i in chosen)
            or len(set(chosen)) != len(chosen)):
        raise InputError("selection.selected_ids must be one list of unique existing shared candidate IDs")
    events = selection.get("events", [])
    if not isinstance(events, list):
        raise InputError("selection.events must be one list of explicitly verified shared events")
    entity = {"name": name, "confirmed": True}
    if code:
        entity["org_code"] = code
    items = []
    for source_id in chosen:
        item = catalog[source_id]
        if not isinstance(item, dict) or item.get("id") != source_id:
            raise InputError("candidate ID and record binding disagree")
        if _stable_id({k: v for k, v in item.items() if k != "id"}) != source_id:
            raise InputError("candidate content or provenance changed after build; rebuild from original return")
        allowed = {"id", *prepare.ITEM_FIELDS}
        original = {k: v for k, v in item.items() if k in allowed}
        items.append({**original, "source_assessment": prepare.assess_source(original)})
    valid_items = prepare.validate_items(items, "shared-news")
    # Semantic verified=true must come from the reviewer; all references must belong to the shared selection.
    prepare.validate_events(events, valid_items, "shared-news")
    package = {"acquisition": "mx-finance-search", "entity": entity, "context": context,
               "news_queries": safe_value(queries), "items": items, "events": safe_value(events)}
    audit = {"schema_version": "1.0", "candidate_count": len(catalog), "selected_ids": chosen,
             "selected_count": len(chosen), "excluded_candidate_ids": [i for i in candidates if i not in chosen],
             "event_count": len(events)}
    audit["elapsed_seconds"] = time.perf_counter() - started
    audit["model_supplied_item_content_characters"] = 0
    audit["selection_characters"] = len(json.dumps(selection, ensure_ascii=False))
    audit["catalog_content_characters"] = sum(len(item["content"]) for item in catalog.values())
    return package, audit


def candidate_index(bundle):
    lines = ["# 共享资讯候选索引", "", "全部章节共用本索引和同一资讯池。此索引用于选题；事实核验须读取对应原文，不能只凭标题推定事项或关系。", ""]
    for source_id in bundle["candidate_ids"]:
        item = bundle["catalog"][source_id]
        grade = prepare.assess_source(item)
        lines.append(f"- `{source_id}` | {item['title']} | {item['published_at']} | {item['source']} | {item['material_kind']} | {grade['source_category_v2']} | 权威度：{grade['authority_v2']}")
    lines.append("")
    return "\n".join(lines)


def _write_new(out, files, inputs):
    out = Path(out).resolve()
    targets = [out / name for name in files]
    input_paths = {Path(p).resolve() for p in inputs}
    if any(p.exists() or p in input_paths for p in targets):
        raise InputError("outputs must not overwrite existing artifacts or input files")
    out.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        encoded = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        (out / name).write_text(encoded, encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--manifest", required=True)
    build.add_argument("--out", required=True)
    compose = commands.add_parser("compose")
    compose.add_argument("--bundle", required=True)
    compose.add_argument("--selection", required=True)
    compose.add_argument("--out", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--bundle", required=True)
    inspect.add_argument("--ids", nargs="+", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            path = Path(args.manifest).resolve()
            bundle, audit = build_candidates(json.loads(path.read_text(encoding="utf-8-sig")), path.parent)
            _write_new(args.out, {"candidate_bundle.json": bundle, "candidate_index.md": candidate_index(bundle),
                                  "build_audit.json": audit}, [path, *(s["raw_result_path"] for s in audit["searches"])])
            print(json.dumps({"status": "candidates_built", "candidate_count": audit["candidate_count"],
                              "out": str(Path(args.out).resolve()), "elapsed_seconds": audit["elapsed_seconds"]}, ensure_ascii=False))
        else:
            bundle_path = Path(args.bundle).resolve()
            bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
            if args.command == "inspect":
                if any(i not in bundle["catalog"] for i in args.ids):
                    raise InputError("inspect requested unknown candidate IDs")
                print(json.dumps([bundle["catalog"][i] for i in args.ids], ensure_ascii=False, indent=2))
            else:
                selection_path = Path(args.selection).resolve()
                package, audit = compose_package(bundle, json.loads(selection_path.read_text(encoding="utf-8-sig")))
                _write_new(args.out, {"news_package.json": package, "compose_audit.json": audit}, [bundle_path, selection_path])
                print(json.dumps({"status": "package_composed", "out": str(Path(args.out).resolve()),
                                  "elapsed_seconds": audit["elapsed_seconds"]}, ensure_ascii=False))
        return 0
    except (InputError, OSError, ValueError, KeyError, TypeError) as exc:
        print("INPUT_ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
