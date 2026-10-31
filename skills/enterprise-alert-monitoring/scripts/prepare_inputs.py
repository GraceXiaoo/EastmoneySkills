#!/usr/bin/env python3
"""Prepare one shared news prompt, then a synthesis of completed chapters; no network."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from resolve_time_range import subtract_calendar_months
from source_authority import assess_source, UNKNOWN_PRIORITY

NEWS_BLOCK_KEYS = (
    "monitoring-overview", "key-events", "related-environment",
)
BLOCK_KEYS = NEWS_BLOCK_KEYS  # Compatibility name for the three news-consuming blocks.
FOLLOWUP_BLOCK_KEYS = NEWS_BLOCK_KEYS + ("risk-fermentation",)
REPORT_BLOCK_KEYS = FOLLOWUP_BLOCK_KEYS + ("key-concerns",)
SHARED_ANALYSIS_KEY = "shared-analysis"
ANALYSIS_PLACEHOLDERS = {
    "monitoring-overview": "舆情概览内容", "key-events": "重点事件内容",
    "related-environment": "关联主体内容",
}
CONCERNS_PLACEHOLDERS = {**ANALYSIS_PLACEHOLDERS, "risk-fermentation": "风险发酵链路内容"}
KIND_LABELS = {"event": "已发生事件", "future_event": "未来预期事件"}
EVENT_PLACEHOLDER_NOTE = "接口风险标注（正面/中性/负面）是数据源对事件的情绪倾向分级，不代表企业风险等级或发酵结论，发酵判断须另行论证。"
PACKAGE_KIND_FIELD = {"mx-finance-search": "news_queries", "mx-api-invoke": "event_queries"}
DEFAULT_PROMPTS = Path(__file__).resolve().parents[1] / "references" / "analysis-prompts"
ITEM_FIELDS = ("title", "content", "source", "published_at", "url", "citation", "source_category", "authority_level", "information_type", "material_kind", "title_origin")
EVENT_ITEM_FIELDS = ("title", "content", "source", "published_at", "url", "citation", "source_category",
                     "authority_level", "information_type", "material_kind", "title_origin", "org_name",
                     "org_code", "security_code", "first_tag", "second_tag", "industry", "risk_level",
                     "risk_flag", "info_code", "native_event_id", "happen_time")
ITEM_FIELD_ALIASES = {"authority_level": "authorityLevel", "information_type": "informationType"}
STATUSES = {
    "unknown": "状态未核验", "planned": "计划阶段", "approved": "已披露获批",
    "received": "已披露到账", "ongoing": "事项持续", "clarified": "已披露澄清",
    "released": "已披露解除", "resolved": "已披露处置完成", "withdrawn": "已披露撤回",
}
FORBIDDEN = {"mql", "datasets", "generated_analysis", "analysis_results", "block_data_packages"}
ACQUISITIONS = ("mx-finance-search", "mx-api-invoke")
EVENT_ALLOWED_TOP = {"schema_version", "acquisition", "entity", "context", "event_queries", "items"}
EVENT_MATERIAL_KINDS = {"event", "future_event"}


class InputError(ValueError):
    pass


def text(value, where, *, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise InputError(f"{where}: expected {'a string' if empty else 'a nonempty string'}")
    return value


def iso(value, where, *, empty=False):
    value = text(value, where, empty=empty)
    if not value:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return dt.datetime.combine(dt.date.fromisoformat(value), dt.time())
        if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]", value):
            raise ValueError()
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError(f"{where}: expected an ISO date or datetime") from exc


def local_date(value, where):
    stamp = iso(value, where)
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(dt.timezone(dt.timedelta(hours=8)))
    return stamp.date().isoformat()


def context_projection(value):
    if not isinstance(value, dict):
        raise InputError("context: expected an object")
    as_of = text(value.get("data_as_of"), "context.data_as_of")
    cutoff = local_date(as_of, "context.data_as_of")
    end = value.get("end_date") or cutoff
    if not isinstance(end, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
        raise InputError("context.end_date: expected YYYY-MM-DD")
    iso(end, "context.end_date")
    start = value.get("start_date") or subtract_calendar_months(dt.date.fromisoformat(end), 3).isoformat()
    for key, date_value in (("start_date", start), ("end_date", end)):
        if not isinstance(date_value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
            raise InputError(f"context.{key}: expected YYYY-MM-DD")
        iso(date_value, f"context.{key}")
    if start > end or end > cutoff:
        raise InputError("context: start_date <= end_date <= data_as_of is required")
    return {"start_date": start, "end_date": end, "data_as_of": as_of,
            "scope": text(value.get("scope"), "context.scope")}


def validate_entity(entity):
    if not isinstance(entity, dict) or entity.get("confirmed") is not True:
        raise InputError("entity: an explicitly confirmed target is required; candidates cannot be auto-selected")
    name = text(entity.get("name"), "entity.name")
    code = entity.get("org_code", "")
    if code is None:
        code = ""
    if code != "" and (not isinstance(code, str) or not re.fullmatch(r"[0-9]{8,32}(?:\.FXR)?", code, re.IGNORECASE)):
        raise InputError("entity.org_code: if provided, retain the complete numeric string (8-32 digits, optional .FXR); no truncation or stock code")
    return name, code


def validate_url(value, where):
    value = text(value, where, empty=True)
    if not value:
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise InputError(f"{where}: expected an HTTP(S) source URL without credentials")
    if any(key.lower() in {"password", "api_key", "access_token", "authorization", "secret"}
           for key, _ in parse_qsl(parsed.query)):
        raise InputError(f"{where}: credential parameters must not enter source material")
    return value  # Syntax validation only; no claim that the link was fetched or verified.


def validate_items(items, where):
    if not isinstance(items, list):
        raise InputError(f"{where}.items: expected a list")
    output = []
    seen = set()
    for index, raw in enumerate(items):
        here = f"{where}.items[{index}]"
        if not isinstance(raw, dict) or FORBIDDEN.intersection(raw) or raw.get("acquisition", "mx-finance-search") != "mx-finance-search":
            raise InputError(f"{here}: invalid news item or forbidden business package")
        item_id = text(raw.get("id"), f"{here}.id")
        if item_id in seen:
            raise InputError(f"{here}: duplicate item id")
        seen.add(item_id)
        item = {"id": item_id, "_index": index, "_metadata_notes": []}
        for field in ITEM_FIELDS:
            value = raw.get(ITEM_FIELD_ALIASES.get(field, field), raw.get(field, "")) or ""
            item[field] = text(value, f"{here}.{field}", empty=field not in {"title", "content"})
        item["material_kind"] = item["material_kind"] or "article"
        item["title_origin"] = item["title_origin"] or "original"
        if item["material_kind"] not in {"article", "search_summary"} or item["title_origin"] not in {"original", "material_label"}:
            raise InputError(f"{here}: unsupported material kind or title origin")
        if item["material_kind"] == "article" and item["title_origin"] != "original":
            raise InputError(f"{here}: an article requires its original title")
        if not try_iso(item["published_at"]):
            item["_metadata_notes"].append("publication_date_missing_or_unparseable; raw_value_preserved")
        validate_url(item["url"], f"{here}.url")
        if not item["url"] and not item["citation"]:
            if not item["source"]:
                raise InputError(f"{here}: original URL, citation, or explicit original publisher is required")
            item["_metadata_notes"].append("textual_source_attribution_only; do_not_invent_url_or_citation")
        for field in ("source", "source_category", "authority_level", "information_type"):
            if not item[field]:
                item["_metadata_notes"].append(f"{field}_missing; no_replacement_invented")
        item["source_assessment"] = assess_source(item)
        if item["source_assessment"]["priority"] == UNKNOWN_PRIORITY:
            item["_metadata_notes"].append("source_authority_v2_unknown; raw_values_preserved")
        output.append(item)
    return output


def references(value, legal, where):
    if not isinstance(value, list) or not value or any(not isinstance(v, str) or v not in legal for v in value):
        raise InputError(f"{where}: a nonempty list of existing block-local item IDs is required")
    return list(dict.fromkeys(value))


def validate_event_items(items, where):
    """Event-library items come from mx_api_invoke returns; the material kind records
    which of the two catalog APIs produced the record (event / future_event)."""
    if not isinstance(items, list):
        raise InputError(f"{where}.items: expected a list")
    output = []
    seen = set()
    for index, raw in enumerate(items):
        here = f"{where}.items[{index}]"
        if not isinstance(raw, dict) or FORBIDDEN.intersection(raw):
            raise InputError(f"{here}: invalid event item or forbidden business package")
        item_id = text(raw.get("id"), f"{here}.id")
        if item_id in seen:
            raise InputError(f"{here}: duplicate item id")
        seen.add(item_id)
        item = {"id": item_id, "_index": index, "_metadata_notes": []}
        for field in EVENT_ITEM_FIELDS:
            value = raw.get(ITEM_FIELD_ALIASES.get(field, field), raw.get(field, "")) or ""
            item[field] = text(value, f"{here}.{field}", empty=True)
        if not item["title"].strip() or not item["content"].strip():
            raise InputError(f"{here}: event items require a title and digest")
        if item["material_kind"] not in EVENT_MATERIAL_KINDS:
            raise InputError(f"{here}: event items require material_kind event or future_event")
        if item["title_origin"] not in {"original", "material_label"}:
            raise InputError(f"{here}: unsupported title origin")
        if item["risk_flag"] and item["risk_level"] == "未标注":
            item["_metadata_notes"].append("risk_label_and_flag_disagree; raw_values_preserved")
        if not try_iso(item["published_at"]):
            item["_metadata_notes"].append("publication_date_missing_or_unparseable; raw_value_preserved")
        validate_url(item["url"], f"{here}.url")
        if not item["url"] and not item["citation"] and not item["info_code"]:
            if not item["source"]:
                raise InputError(f"{here}: original URL, citation, info code, or explicit original publisher is required")
            item["_metadata_notes"].append("textual_source_attribution_only; do_not_invent_url_or_citation")
        for field in EVENT_ITEM_FIELDS:
            if field not in {"title", "content"} and not item[field]:
                item["_metadata_notes"].append(f"{field}_missing; no_replacement_invented")
        item["source_assessment"] = assess_source(item)
        if item["source_assessment"]["priority"] == UNKNOWN_PRIORITY:
            item["_metadata_notes"].append("source_authority_v2_unknown; raw_values_preserved")
        output.append(item)
    return output


def claims_projection(raw, legal, where):
    if not isinstance(raw, dict) or FORBIDDEN.intersection(raw):
        raise InputError(f"{where}: expected a fact object")
    claim = {"text": text(raw.get("text"), f"{where}.text"),
             "source_ids": references(raw.get("source_ids"), legal, f"{where}.source_ids")}
    for field in ("fact_key", "amount", "currency", "unit", "as_of"):
        if field in raw:
            claim[field] = text(raw[field], f"{where}.{field}", empty=False)
    if "as_of" in claim:
        iso(claim["as_of"], f"{where}.as_of")
    claim["statement"] = raw.get("statement", "fact")
    if claim["statement"] not in {"fact", "plan"}:
        raise InputError(f"{where}.statement: expected fact or plan")
    return claim


def validate_events(events, items, where):
    if not isinstance(events, list):
        raise InputError(f"{where}.events: expected a list")
    legal = {item["id"] for item in items}
    result = []
    for index, raw in enumerate(events):
        here = f"{where}.events[{index}]"
        if not isinstance(raw, dict) or raw.get("verified") is not True or FORBIDDEN.intersection(raw):
            raise InputError(f"{here}: events require explicit model verification (verified=true)")
        event = {"subject": text(raw.get("subject"), f"{here}.subject"),
                 "event_key": text(raw.get("event_key"), f"{here}.event_key"),
                 "title": text(raw.get("title"), f"{here}.title"),
                 "source_ids": references(raw.get("source_ids"), legal, f"{here}.source_ids"),
                 "event_date": raw.get("event_date", ""),
                 "status_date": raw.get("status_date", ""),
                 "status": raw.get("status", "unknown"),
                 "statement": raw.get("statement", "fact"),
                 "claims": [], "developments": []}
        for field in ("event_date", "status_date"):
            iso(event[field], f"{here}.{field}", empty=True)
        if event["status"] not in STATUSES:
            raise InputError(f"{here}.status: unsupported explicit status")
        if event["statement"] not in {"fact", "plan"}:
            raise InputError(f"{here}.statement: expected fact or plan")
        supporting = set(event["source_ids"])
        raw_claims = raw.get("claims", [])
        if not isinstance(raw_claims, list):
            raise InputError(f"{here}.claims: expected a list")
        for claim_index, claim in enumerate(raw_claims):
            event["claims"].append(claims_projection(claim, supporting, f"{here}.claims[{claim_index}]"))
        developments = raw.get("developments", [])
        if not isinstance(developments, list):
            raise InputError(f"{here}.developments: expected a list")
        for dev_index, raw_dev in enumerate(developments):
            dev = claims_projection(raw_dev, supporting, f"{here}.developments[{dev_index}]")
            dev["date"] = text(raw_dev.get("date"), f"{here}.developments[{dev_index}].date", empty=True)
            iso(dev["date"], f"{here}.developments[{dev_index}].date", empty=True)
            dev["status"] = raw_dev.get("status", "unknown")
            if dev["status"] not in STATUSES:
                raise InputError(f"{here}.developments[{dev_index}].status: unsupported status")
            event["developments"].append(dev)
        relationship = raw.get("relationship", "")
        if relationship:
            event["relationship"] = text(relationship, f"{here}.relationship")
            event["relationship_source_ids"] = references(raw.get("relationship_source_ids"), supporting, f"{here}.relationship_source_ids")
        result.append(event)
    return result


def unique_facts(facts):
    output, positions = [], {}
    for fact in facts:
        marker = json.dumps({k: v for k, v in fact.items() if k != "source_ids"}, ensure_ascii=False, sort_keys=True)
        if marker in positions:
            existing = output[positions[marker]]
            existing["source_ids"] = list(dict.fromkeys(existing["source_ids"] + fact["source_ids"]))
        else:
            positions[marker] = len(output)
            output.append(dict(fact))
    return output


def merge_events(events):
    groups = {}
    for event in events:
        groups.setdefault((event["subject"], event["event_key"]), []).append(event)
    merged = []
    for (subject, key), members in groups.items():
        dates = list(dict.fromkeys(e["event_date"] for e in members if e["event_date"]))
        developments = unique_facts([d for e in members for d in e["developments"]])
        developments.sort(key=lambda d: (not bool(d["date"]), d["date"]))
        claims = unique_facts([c for e in members for c in e["claims"]])
        observations = [{"status": e["status"], "date": e["status_date"], "source_ids": e["source_ids"]}
                        for e in members if e["status"] != "unknown"]
        observations += [{"status": d["status"], "date": d["date"], "source_ids": d["source_ids"]}
                         for d in developments if d["status"] != "unknown"]
        observations = unique_facts(observations)
        fact_values = {}
        for claim in claims:
            if claim.get("fact_key"):
                fact_values.setdefault((claim["fact_key"], claim.get("as_of", "")), set()).add(
                    json.dumps({k: claim.get(k) for k in ("amount", "currency", "unit")}, sort_keys=True)
                    if "amount" in claim else claim["text"])
        conflicts = [k[0] for k, values in fact_values.items() if len(values) > 1]
        relationships = list(dict.fromkeys(e.get("relationship", "") for e in members if e.get("relationship")))
        relationship_evidence = unique_facts([
            {"text": e["relationship"], "source_ids": e["relationship_source_ids"]}
            for e in members if e.get("relationship")])
        merged.append({"subject": subject, "event_key": key, "titles": list(dict.fromkeys(e["title"] for e in members)),
                       "source_ids": list(dict.fromkeys(s for e in members for s in e["source_ids"])),
                       "event_dates": dates, "date_conflict": len(dates) > 1,
                       "claims": claims, "developments": developments, "status_observations": observations,
                       "statements": list(dict.fromkeys(e["statement"] for e in members)),
                       "fact_conflicts": conflicts, "relationships": relationships,
                       "relationship_evidence": relationship_evidence, "member_count": len(members)})
    return merged


def snapshot_events(events, context):
    cutoff = moment(context["data_as_of"], date_end=True)
    output = []
    exclusions = []
    for event in events:
        if event["event_date"] and moment(event["event_date"]) > cutoff and not is_plan(event):
            exclusions.append({"subject": event["subject"], "event_key": event["event_key"],
                               "future_event_removed": True, "reason": "future_occurrence_not_explicit_plan"})
            continue
        item = dict(event)
        future_devs = [d for d in event["developments"] if d["date"] and moment(d["date"]) > cutoff
                       and not is_plan(d)]
        future_claims = [c for c in event["claims"] if c.get("as_of") and moment(c["as_of"]) > cutoff
                         and not is_plan(c)]
        item["developments"] = [d for d in event["developments"] if d not in future_devs]
        item["claims"] = [c for c in event["claims"] if c not in future_claims]
        # A future completed status is not a fact in the historical snapshot.
        if event["status_date"] and moment(event["status_date"]) > cutoff:
            item["status"] = "unknown"
            item["status_date"] = ""
        output.append(item)
        if future_devs or future_claims:
            exclusions.append({"subject": event["subject"], "event_key": event["event_key"],
                               "future_fact_developments_removed": len(future_devs), "future_fact_claims_removed": len(future_claims)})
    return output, exclusions


def is_plan(fact):
    return (fact.get("statement") == "plan" or fact.get("status") == "planned") and fact.get("status") not in {
        "received", "clarified", "released", "resolved", "withdrawn"}


def try_iso(value):
    try:
        return iso(value, "publication", empty=True)
    except InputError:
        return None


def source_ref(item):
    return {field: item[field] for field in ("title", "source", "published_at", "url", "citation")}


def moment(value, *, date_end=False):
    stamp = iso(value, "date")
    if date_end and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        stamp = stamp.replace(hour=23, minute=59, second=59, microsecond=999999)
    return stamp.replace(tzinfo=dt.timezone(dt.timedelta(hours=8))) if stamp.tzinfo is None else stamp


def supported_fact(fact, by_id):
    out = {k: v for k, v in fact.items() if k not in {"source_ids", "fact_key"}}
    out["sources"] = [source_ref(by_id[source_id]) for source_id in fact["source_ids"]]
    if is_plan(fact):
        out["statement_note"] = "计划或未来节点，不表示截至时点已经发生或完成"
    return out


def event_business(event, by_id, context, entity_name):
    dates = [local_date(v, "event.event_date") for v in event["event_dates"]]
    start, end = context["start_date"], context["end_date"]
    progress = [local_date(d["date"], "development.date") for d in event["developments"] if d["date"] and not is_plan(d)]
    if event["date_conflict"]:
        period = "发生日期披露不一致，不能据此判定本期新增"
    elif not dates:
        period = "发生日期未核验，不能据发布时间判定本期新增"
    elif dates[0] < start:
        period = "历史事项，本期有已核验进展" if any(start <= d <= end for d in progress) else "历史事项；本期转载或披露不等于新增"
    elif start <= dates[0] <= end:
        period = "发生日期在监测期内；不自动判定其风险程度"
    else:
        period = "发生日期在监测期之外"
    if any(try_iso(by_id[s]["published_at"]) is None for s in event["source_ids"]):
        period += "；支持资讯的披露日期未核验，不能证明截至时点已知"
    cutoff = moment(context["data_as_of"], date_end=True)
    dated = [o for o in event["status_observations"] if o["date"] and moment(o["date"]) <= cutoff
             and all(try_iso(by_id[s]["published_at"]) is not None for s in o["source_ids"])]
    current = "unknown"
    if dated:
        latest = max(moment(o["date"]) for o in dated)
        latest_statuses = {o["status"] for o in dated if moment(o["date"]) == latest}
        if len(latest_statuses) == 1:
            current = next(iter(latest_statuses))
    out = {"subject": event["subject"], "titles": event["titles"], "event_dates": event["event_dates"],
           "attribution": "目标企业自身事项" if event["subject"] == entity_name else "其他主体事项，不自动归为目标企业自身风险",
           "relationships_disclosed": event["relationships"], "period_assessment": period,
           "relationship_evidence": [supported_fact(fact, by_id) for fact in event["relationship_evidence"]],
           "latest_dated_status": STATUSES[current],
           "status_observations": [supported_fact(o, by_id) for o in event["status_observations"]],
           "claims": [supported_fact(c, by_id) for c in event["claims"]],
           "developments": [supported_fact(d, by_id) for d in event["developments"]],
           "sources": [source_ref(by_id[s]) for s in event["source_ids"]]}
    if "plan" in event["statements"]:
        out["statement_note"] = "包含已公开的计划或未来节点；计划部分不表示截至时点已经发生或完成"
    if event["fact_conflicts"]:
        out["conflict_note"] = "同一事项存在不同金额或事实披露，分别保留，未求和；不能未经核验择一"
    if current == "clarified":
        out["status_note"] = "澄清是披露进展，不自动表示风险解除或事项已解决"
    if current in {"released", "resolved", "withdrawn"}:
        out["status_note"] = "解除、处置或撤回仅适用于原文明确的事项和范围，不覆盖其他风险"
    if current in {"planned", "approved"}:
        out["status_note"] = "计划或获批不等于资金到账"
    return out


def item_sort_key(item):
    stamp = try_iso(item["published_at"])
    if stamp is None:
        seconds = float("-inf")
    else:
        stamp = stamp.replace(tzinfo=dt.timezone(dt.timedelta(hours=8))) if stamp.tzinfo is None else stamp
        seconds = (stamp.astimezone(dt.timezone.utc) - dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)).total_seconds()
    return (assess_source(item)["priority"], -seconds, item["_index"])


def render_material(projection):
    context = projection["context"]
    parts = [f"监测期间：{context['start_date']} 至 {context['end_date']}（含两端）\n资讯截至：{context['data_as_of']}\n范围说明：{context['scope']}\n统计限于本次检索材料，不代表全量舆情；未提供材料不能证明无风险。"]
    for item in projection["items"]:
        summary = item["material_kind"] == "search_summary"
        heading = "检索返回汇总材料（保持整体，不等于独立新闻）" if summary else "资讯原始信源"
        title_label = "材料标签（非新闻原标题）" if item["title_origin"] == "material_label" else "标题"
        parts.append(heading + "\n" + "\n".join([
            f"材料ID（仅供词云标签绑定，不作来源引用、不写入报告）：{item['id']}",
            f"{title_label}：{item['title']}", f"来源机构：{item['source'] or '输入未提供'}", f"发布时间：{item['published_at'] or '原文未提供'}",
            "日期核验：可解析" if try_iso(item['published_at']) else "日期核验：未核验，不能证明截至时点已知，不用于历史截止判断",
            f"原文URL：{item['url'] or '输入未提供'}", f"原始引用：{item['citation'] or '输入未提供'}",
            f"来源类别原值：{item['source_category'] or '输入未提供'}", f"权威度原值：{item['authority_level'] or '输入未提供'}",
            f"来源分类（V2）：{item['source_assessment']['source_category_v2']}",
            f"权威度（V2）：{item['source_assessment']['authority_v2']}",
            f"资讯类型原值：{item['information_type'] or '输入未提供'}", f"正文：{item['content']}" ]))
    if projection["events"]:
        parts.append("已经显式核验并归并的事项（仅依赖上述原始信源）\n" + json.dumps(projection["events"], ensure_ascii=False, indent=2))
    if not projection["items"]:
        parts.append("本模块没有可用资讯材料；不能由此得出企业无风险的结论。")
    return "\n\n".join(parts)


def render_prompt(template, entity_name, news_text):
    template = text(template, "shared analysis template")
    placeholders = set(re.findall(r"\{\{([^{}]+)\}\}", template))
    if placeholders != {"企业名称", "资讯"}:
        raise InputError("prompt templates must contain exactly the two placeholder kinds {{企业名称}} and {{资讯}}")
    if any(template.count(token) != 1 for token in ("{{企业名称}}", "{{资讯}}")):
        raise InputError("the shared analysis template must contain {{企业名称}} and {{资讯}} exactly once each; do not repeat the shared context by chapter")
    # One substitution pass: braces in untrusted news/name must never become instructions to the renderer.
    return re.sub(r"\{\{(企业名称|资讯)\}\}", lambda m: entity_name if m.group(1) == "企业名称" else news_text, template)


def render_event_material(items, context, entity_name):
    """Render the shared event-library material once for the fermentation task."""
    parts = [
        f"事件库截至：{context['data_as_of']}",
        "以下条目来自事件库两个接口（事件大全＝已发生事件；未来行动事件＝未来预期事件）的原始返回，摘要与分类为接口原文，未改写。",
        EVENT_PLACEHOLDER_NOTE,
        f"主体归属核对：条目“事件主体”与目标企业（{entity_name}）不一致时，该条目为关键词相关主体事项，不能直接当作目标企业自身事件。",
        "未来预期事件的“预计发生时间”为粗粒度表述（可能仅有年份或半年），实际以公司公告为准；预计时间早于截至时点的条目已标注，须核对是否已经发生。",
    ]
    for item in items:
        future = item["material_kind"] == "future_event"
        lines = [
            f"事件条目ID（仅供内部绑定，不作来源引用、不写入报告）：{item['id']}",
            f"条目类型：{KIND_LABELS[item['material_kind']]}",
            f"标题：{item['title']}",
            f"事件主体：{item['org_name'] or '接口未提供'}",
            f"主体机构代码：{item['org_code'] or '接口未提供'}",
            f"证券代码：{item['security_code'] or '接口未提供'}",
            f"事件分类：{item['first_tag'] or '接口未提供'}／{item['second_tag'] or '接口未提供'}",
            f"行业：{item['industry'] or '接口未提供'}",
            f"接口风险标注：{item['risk_level']}",
            f"发布时间：{item['published_at'] or '接口未提供'}",
            "发布时间核验：可解析" if try_iso(item["published_at"]) else "发布时间核验：未核验，不能证明截至时点已知",
            f"原文URL：{item['url'] or '接口未提供'}",
            f"信息编码：{item['info_code'] or '接口未提供'}",
            f"来源机构：{item['source'] or '接口未提供'}",
            f"来源分类（V2）：{item['source_assessment']['source_category_v2']}",
            f"权威度（V2）：{item['source_assessment']['authority_v2']}",
            f"摘要原文：{item['content']}",
        ]
        if future:
            overdue = bool(item["happen_time"]) and _coarse_date(item["happen_time"]) is not None \
                and _coarse_date(item["happen_time"]) <= context["data_as_of"][:10]
            lines.append(f"预计发生时间：{item['happen_time'] or '接口未提供'}"
                         + ("（早于截至时点，须核对实际状态）" if overdue else ""))
        parts.append("事件库条目\n" + "\n".join(lines))
    if not items:
        parts.append("本次没有可用事件库材料；不能由此得出企业无风险或风险不会发酵的结论。")
    return "\n\n".join(parts)


def _coarse_date(value):
    """Coarse happen-time strings like 2026 / 2026-12 / 2026下半年 / 2026-12-31 to a comparable date."""
    match = re.match(r"^\s*(\d{4})(?:[-/](\d{1,2}))?(?:[-/](\d{1,2}))?", value)
    if not match:
        return None
    year, month, day = (int(part) if part else None for part in match.groups())
    month = month or 1
    if not 1 <= month <= 12:
        month = 1
    day = day or 1
    try:
        return dt.date(year, month, min(day, 28)).isoformat()
    except ValueError:
        return None


def prepare_event_material(event_payload, context, entity_name):
    """Validate the shared event package and render its material for the fermentation task."""
    if not isinstance(event_payload, dict) or event_payload.get("acquisition") != "mx-api-invoke":
        raise InputError("events must be one shared event package with acquisition='mx-api-invoke'")
    if FORBIDDEN.intersection(event_payload):
        raise InputError("MQL datasets and generated analysis are not accepted as events")
    if set(event_payload) - EVENT_ALLOWED_TOP:
        raise InputError("event packages accept acquisition, entity, context, event_queries and items only")
    package_entity = event_payload.get("entity")
    if not isinstance(package_entity, dict) or package_entity.get("confirmed") is not True:
        raise InputError("event package entity: an explicitly confirmed target is required")
    package_name, package_code = validate_entity(package_entity)
    if package_name != entity_name:
        raise InputError("event package entity must match the target entity of this run")
    if package_code and package_code != (event_payload.get("_run_org_code") or package_code):
        pass  # org_code equality with the run identity is enforced by the caller when both exist
    package_context = context_projection(event_payload.get("context"))
    if (package_context["start_date"], package_context["end_date"]) != (context["start_date"], context["end_date"]):
        raise InputError("event package context must share the same monitoring period as this run")
    queries = event_payload.get("event_queries")
    if not isinstance(queries, list):
        raise InputError("event package event_queries must be a list")
    items = validate_event_items(event_payload.get("items"), "shared-events")
    cutoff = moment(context["data_as_of"], date_end=True)
    dropped = [i for i in items if try_iso(i["published_at"]) is not None and moment(i["published_at"]) > cutoff]
    eligible = [i for i in items if i not in dropped]
    ordered = sorted(eligible, key=item_sort_key)
    material = render_event_material(ordered, context, entity_name)
    audit = {"acquisition": "mx-api-invoke", "event_queries": _query_audit(queries, "event_queries"),
             "kept_item_ids": [i["id"] for i in ordered],
             "excluded_post_cutoff_item_ids": [i["id"] for i in dropped],
             "kind_counts": {label: sum(1 for i in ordered if i["material_kind"] == kind)
                             for kind, label in KIND_LABELS.items()},
             "metadata_notes": {i["id"]: i["_metadata_notes"] for i in items if i["_metadata_notes"]},
             "source_assessments": {i["id"]: i["source_assessment"] for i in items},
             "sort_keys": ["authority_v2_priority", "published_at_desc", "original_index"]}
    return {"context": context, "items": [{"id": i["id"], **{f: i[f] for f in EVENT_ITEM_FIELDS},
                                           "source_assessment": i["source_assessment"]} for i in ordered],
            "material": material, "audit": audit}


def _query_audit(queries, where):
    audit = []
    for query in queries:
        if isinstance(query, str):
            audit.append(query)
        elif isinstance(query, dict):
            audit.append({f: query[f] for f in ("query", "api_id", "api_label", "purpose", "subject", "start_date",
                                               "end_date", "status", "returned_count", "raw_result_path", "kind",
                                               "reason") if f in query and isinstance(query[f], (str, int, bool))})
        else:
            raise InputError(f"{where}: each query must be a string or object")
    return audit


def render_fermentation_prompt(template, entity_name, event_material, analysis_results):
    """Replace each declared token once; inserted prose and material are never reparsed."""
    template = text(template, "risk-fermentation template")
    expected = {"企业名称", "事件库", *ANALYSIS_PLACEHOLDERS.values()}
    if set(re.findall(r"\{\{([^{}]+)\}\}", template)) != expected:
        raise InputError("risk-fermentation template must contain exactly the five placeholder kinds: 企业名称、事件库、舆情概览内容、重点事件内容、关联主体内容")
    if any(template.count("{{" + token + "}}") != 1 for token in expected):
        raise InputError("the risk-fermentation template must contain each of the five placeholders exactly once")
    values = {"企业名称": entity_name, "事件库": event_material,
              **{ANALYSIS_PLACEHOLDERS[key]: analysis_results[key] for key in NEWS_BLOCK_KEYS}}
    return re.sub(r"\{\{([^{}]+)\}\}", lambda match: values[match.group(1)], template)


def prepare_fermentation(payload, template):
    """Build the risk-fermentation task from three completed chapter bodies plus the shared event package."""
    if not isinstance(payload, dict) or set(payload) != {"entity", "analysis_results", "events"}:
        raise InputError("prepare-fermentation accepts exactly entity, analysis_results and events; the news pool never re-enters here")
    entity = payload.get("entity")
    if not isinstance(entity, dict) or set(entity) - {"name", "confirmed", "org_code"}:
        raise InputError("prepare-fermentation.entity accepts confirmed name and optional org_code only")
    entity_name, org_code = validate_entity(entity)
    original = payload.get("analysis_results")
    if not isinstance(original, dict) or set(original) != set(NEWS_BLOCK_KEYS):
        raise InputError("analysis_results must contain exactly the three preceding news chapter keys")
    normalized = {}
    for key in NEWS_BLOCK_KEYS:
        value = text(original[key], f"analysis_results.{key}", empty=True)
        normalized[key] = "" if value.strip() in {"", "暂无数据", "暂无数据。"} else value
    event_payload = payload.get("events")
    if not isinstance(event_payload, dict):
        raise InputError("events must be the composed shared event package (mx-api-invoke)")
    event_package_code = event_payload.get("entity", {}).get("org_code", "")
    if org_code and isinstance(event_package_code, str) and event_package_code and event_package_code != org_code:
        raise InputError("event package entity org_code disagrees with the run identity")
    context = context_projection(event_payload.get("context"))
    prepared_events = prepare_event_material(event_payload, context, entity_name)
    event_material = prepared_events["material"]
    prompt = render_fermentation_prompt(template, entity_name, event_material, normalized)
    kept = [key for key in NEWS_BLOCK_KEYS if normalized[key]]
    empty = [key for key in NEWS_BLOCK_KEYS if not normalized[key]]
    identity = {"name": entity_name, "confirmed": True}
    if org_code:
        identity["org_code"] = org_code
    prompt_inputs = {"企业名称": entity_name, "事件库": event_material,
                     **{ANALYSIS_PLACEHOLDERS[key]: normalized[key] for key in NEWS_BLOCK_KEYS}}
    block = {"key": "risk-fermentation", "status": "ready" if (kept or prepared_events["items"]) else "empty",
             "prompt_data": {"analysis_results": normalized, "prompt_inputs": prompt_inputs,
                             "active_blocks": kept, "empty_blocks": empty,
                             "events": prepared_events["items"]},
             "prompt": prompt, "prompt_length": len(prompt)}
    result = {"schema_version": "1.0", "entity": identity, "context": context, "blocks": [block]}
    audit = {"schema_version": "1.0", "key": "risk-fermentation", "entity_identity": identity,
             "input_kind": "completed_analysis_prose_plus_event_package",
             "report_order": list(NEWS_BLOCK_KEYS) + ["risk-fermentation"],
             "kept_keys": kept, "original_empty_keys": empty,
             "input_lengths": {key: len(original[key]) for key in NEWS_BLOCK_KEYS},
             **prepared_events["audit"], "prompt_length": len(prompt)}
    return result, audit


def prepare_block(block, template, context, entity_name):
    key = block["key"]
    items = validate_items(block.get("items"), key)
    queries = block.get("news_queries")
    if not isinstance(queries, list):
        raise InputError(f"{key}.news_queries: expected a list")
    validated_events = validate_events(block.get("events", []), items, key)
    snapshot, future_event_exclusions = snapshot_events(validated_events, context)
    events = merge_events(snapshot)
    cutoff = moment(context["data_as_of"], date_end=True)
    future_items = [i for i in items if try_iso(i["published_at"]) is not None and moment(i["published_at"]) > cutoff]
    eligible = [i for i in items if i not in future_items]
    ordered = sorted(eligible, key=item_sort_key)
    by_id = {item["id"]: item for item in items}

    def projection(selected):
        kept = {i["id"] for i in selected}
        return {"context": context, "items": [{"id": i["id"], **{f: i[f] for f in ITEM_FIELDS},
                                             "source_assessment": i["source_assessment"]} for i in selected],
                "events": [event_business(e, by_id, context, entity_name) for e in events if set(e["source_ids"]) <= kept]}

    business = projection(ordered)
    material = render_material(business)
    prompt = render_prompt(template, entity_name, material)
    kept = {i["id"] for i in ordered}
    query_audit = []
    for query in queries:
        if isinstance(query, str):
            query_audit.append(query)
        elif isinstance(query, dict):
            query_audit.append({f: query[f] for f in ("query", "purpose", "subject", "start_date", "end_date", "status", "returned_count", "raw_result_path", "kind", "reason") if f in query and isinstance(query[f], (str, int, bool))})
        else:
            raise InputError(f"{key}.news_queries: each query must be a string or object")
    audit = {"key": key, "news_queries": query_audit, "ordered_item_ids": [i["id"] for i in ordered],
             "kept_item_ids": [i["id"] for i in ordered], "dropped_item_ids": [i["id"] for i in future_items],
             "excluded_post_cutoff_item_ids": [i["id"] for i in future_items],
             "future_event_fact_exclusions": future_event_exclusions,
             "metadata_notes": {i["id"]: i["_metadata_notes"] for i in items if i["_metadata_notes"]},
             "source_assessments": {i["id"]: i["source_assessment"] for i in items},
             "sort_keys": ["authority_v2_priority", "published_at_desc", "original_index"],
             "prompt_length": len(prompt),
             "events": [{"subject": e["subject"], "event_key": e["event_key"], "source_ids": e["source_ids"],
                         "merged_records": e["member_count"], "fact_conflicts": e["fact_conflicts"],
                         "date_conflict": e["date_conflict"], "kept": set(e["source_ids"]) <= kept}
                        for e in events]}
    return {"key": key, "status": "ready" if ordered else "empty", "prompt_data": business,
            "news_text": material, "prompt": prompt, "prompt_length": len(prompt)}, audit


def prepare(payload, template):
    """Render the shared package once for a single analysis producing three chapters."""
    if not isinstance(payload, dict) or payload.get("acquisition") != "mx-finance-search":
        raise InputError("only acquisition='mx-finance-search' is accepted")
    if FORBIDDEN.intersection(payload):
        raise InputError("MQL datasets and generated analysis are not accepted as news")
    allowed = {"schema_version", "acquisition", "entity", "context", "news_queries", "items", "events"}
    if set(payload) - allowed:
        raise InputError("prepare accepts one shared news package only: acquisition, entity, context, news_queries, items and events; old blocks and chapter-specific packages are not accepted")
    entity_name, org_code = validate_entity(payload.get("entity"))
    context = context_projection(payload.get("context"))
    if not isinstance(template, str):
        raise InputError("prepare requires one shared-analysis template string; per-chapter template maps are not accepted")
    result = {"schema_version": "1.0", "entity": {"name": entity_name}, "context": context, "blocks": []}
    identity = {"name": entity_name, "confirmed": True}
    if org_code:
        identity["org_code"] = org_code
    audit = {"schema_version": "1.0", "acquisition": "mx-finance-search",
             "entity_identity": identity, "blocks": []}
    block = {"key": SHARED_ANALYSIS_KEY, "news_queries": payload.get("news_queries"),
             "items": payload.get("items"), "events": payload.get("events", [])}
    business, block_audit = prepare_block(block, template, context, entity_name)
    business["output_blocks"] = list(NEWS_BLOCK_KEYS)
    result["blocks"].append(business)
    audit["blocks"].append(block_audit)
    return result, audit


def render_concerns_prompt(template, entity_name, analysis_results):
    """Replace each declared token once; inserted completed prose is never reparsed."""
    template = text(template, "key-concerns template")
    expected = {"企业名称", *CONCERNS_PLACEHOLDERS.values()}
    if set(re.findall(r"\{\{([^{}]+)\}\}", template)) != expected:
        raise InputError("key-concerns template must contain exactly the five placeholder kinds: 企业名称、舆情概览内容、重点事件内容、关联主体内容、风险发酵链路内容")
    values = {"企业名称": entity_name, **{CONCERNS_PLACEHOLDERS[key]: analysis_results[key] for key in FOLLOWUP_BLOCK_KEYS}}
    return re.sub(r"\{\{([^{}]+)\}\}", lambda match: values[match.group(1)], template)


def prepare_key_concerns(payload, template):
    """Build the final synthesis from four completed prose strings, preserving each whole."""
    if not isinstance(payload, dict) or set(payload) != {"entity", "analysis_results"}:
        raise InputError("prepare-concerns accepts only entity and analysis_results; raw news, items, events, context and other packages are forbidden")
    entity = payload.get("entity")
    if not isinstance(entity, dict) or set(entity) - {"name", "confirmed", "org_code"}:
        raise InputError("prepare-concerns.entity accepts confirmed name and optional org_code only")
    entity_name, org_code = validate_entity(entity)
    original = payload.get("analysis_results")
    if not isinstance(original, dict) or set(original) != set(FOLLOWUP_BLOCK_KEYS):
        raise InputError("analysis_results must contain exactly the four preceding chapter keys; no key-concerns")
    normalized = {}
    for key in FOLLOWUP_BLOCK_KEYS:
        value = text(original[key], f"analysis_results.{key}", empty=True)
        normalized[key] = "" if value.strip() in {"", "暂无数据", "暂无数据。"} else value

    prompt = render_concerns_prompt(template, entity_name, normalized)
    kept = [key for key in FOLLOWUP_BLOCK_KEYS if normalized[key]]
    empty = [key for key in FOLLOWUP_BLOCK_KEYS if not normalized[key]]
    identity = {"name": entity_name, "confirmed": True}
    if org_code:
        identity["org_code"] = org_code
    prompt_inputs = {"企业名称": entity_name, **{CONCERNS_PLACEHOLDERS[key]: normalized[key] for key in FOLLOWUP_BLOCK_KEYS}}
    block = {"key": "key-concerns", "status": "ready" if kept else "empty",
             "prompt_data": {"analysis_results": normalized, "prompt_inputs": prompt_inputs,
                             "active_blocks": kept, "empty_blocks": empty},
             "prompt": prompt, "prompt_length": len(prompt)}
    result = {"schema_version": "1.0", "entity": identity, "blocks": [block]}
    audit = {"schema_version": "1.0", "key": "key-concerns", "entity_identity": identity,
             "input_kind": "completed_analysis_prose", "report_order": list(FOLLOWUP_BLOCK_KEYS),
             "kept_keys": kept,
             "original_empty_keys": [key for key in FOLLOWUP_BLOCK_KEYS if not normalized[key]],
             "input_lengths": {key: len(original[key]) for key in FOLLOWUP_BLOCK_KEYS},
             "prompt_length": len(prompt)}
    return result, audit


def candidate_result(payload):
    """Present supplied candidates only; even a single candidate is never auto-confirmed."""
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise InputError("resolve-candidates expects {candidates:[{name,org_code}, ...]}")
    candidates = []
    for index, candidate in enumerate(payload["candidates"]):
        if not isinstance(candidate, dict):
            raise InputError("candidate must be an object")
        name, code = validate_entity({"name": candidate.get("name"), "org_code": candidate.get("org_code"), "confirmed": True})
        candidate_view = {"name": name}
        if code:
            candidate_view["org_code"] = code
        candidates.append(candidate_view)
    return {"status": "no_candidate" if not candidates else "confirmation_required", "selected": None, "candidates": candidates}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="prepare one shared news prompt for all three preceding chapters")
    prep.add_argument("--input", required=True)
    prep.add_argument("--out", required=True, help="new directory for prepared_inputs.json and audit.json")
    prep.add_argument("--prompts-dir", default=str(DEFAULT_PROMPTS))
    concerns = commands.add_parser("prepare-concerns", help="prepare key-concerns from the three completed chapter bodies")
    concerns.add_argument("--input", required=True)
    concerns.add_argument("--out", required=True, help="new directory for prepared_inputs.json and audit.json")
    concerns.add_argument("--prompts-dir", default=str(DEFAULT_PROMPTS))
    candidates = commands.add_parser("resolve-candidates")
    candidates.add_argument("--input", required=True)
    fermentation = commands.add_parser("prepare-fermentation", help="prepare risk-fermentation from three chapter bodies plus the shared event package")
    fermentation.add_argument("--input", required=True)
    fermentation.add_argument("--out", required=True, help="new directory for prepared_inputs.json and audit.json")
    fermentation.add_argument("--prompts-dir", default=str(DEFAULT_PROMPTS))
    args = parser.parse_args(argv)
    try:
        input_path = Path(args.input).resolve()
        payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
        if args.command == "resolve-candidates":
            print(json.dumps(candidate_result(payload), ensure_ascii=False, indent=2))
            return 0
        prompts_dir = Path(args.prompts_dir)
        if args.command == "prepare-concerns":
            template = (prompts_dir / "key-concerns.md").read_text(encoding="utf-8-sig")
            prepared, audit = prepare_key_concerns(payload, template)
        elif args.command == "prepare-fermentation":
            template = (prompts_dir / "risk-fermentation.md").read_text(encoding="utf-8-sig")
            prepared, audit = prepare_fermentation(payload, template)
        else:
            template = (prompts_dir / "shared-analysis.md").read_text(encoding="utf-8-sig")
            prepared, audit = prepare(payload, template)
        out = Path(args.out).resolve()
        targets = [out / "prepared_inputs.json", out / "audit.json"]
        if any(target == input_path or target.exists() for target in targets):
            raise InputError("output must not overwrite the input or an existing prepared result")
        out.mkdir(parents=True, exist_ok=True)
        for target, data in zip(targets, (prepared, audit)):
            with target.open("x", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
        print(f"PREPARED_INPUTS={targets[0]}\nAUDIT={targets[1]}")
        return 0
    except (InputError, ValueError, OSError) as exc:
        print(f"prepare failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
