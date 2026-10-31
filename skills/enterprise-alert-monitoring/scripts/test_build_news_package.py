#!/usr/bin/env python3
"""Offline behavioral fixtures for raw-news handoff. No network or credentials."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

import build_news_package as b
import prepare_inputs as p


TEMPLATE = "分析{{企业名称}}，依序输出舆情概览、重点事件、关联主体。只使用以下共享原始资讯：\n{{资讯}}"


def record(**extra):
    result = {
        "title": "虚拟企业项目公告",
        "content": "虚拟企业披露项目已获批，尚未说明资金到账。\n保留原始换行。",
        "source": "虚拟公告机构",
        "published_at": "2026-10-10T09:00:00+08:00",
        "url": "https://example.invalid/notice/001",
        "citation": "[source:original-marker-A]",
        "source_category": "公告",
        "authority_level": "L1",
        "information_type": "NOTICE",
    }
    result.update(extra)
    return result


def manifest(searches):
    return {
        "entity": {"name": "虚拟企业股份有限公司", "confirmed": True},
        "context": {
            "start_date": "2026-09-14", "end_date": "2026-10-14",
            "data_as_of": "2026-10-14T16:00:00+08:00",
            "scope": "企业自身及资讯明确涉及的关联事项",
        },
        "searches": searches,
    }


def search(path, *, query="虚拟企业综合资讯", status="success", kind="initial", reason=""):
    return {"query": query, "raw_result_path": path, "status": status,
            "kind": kind, "reason": reason}


def selection(ids=None, events=None):
    return {"selected_ids": [] if ids is None else ids,
            "events": [] if events is None else events}


def event(item_ids, **extra):
    result = {"verified": True, "subject": "虚拟企业股份有限公司",
              "event_key": "project-001", "title": "项目获批",
              "source_ids": item_ids, "event_date": "2026-10-09",
              "status": "approved", "status_date": "2026-10-10",
              "claims": [{"text": "项目已获批", "source_ids": item_ids}],
              "developments": []}
    result.update(extra)
    return result


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def write_raw(self, name, value):
        target = self.base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return name

    def build(self, rows, *, value=None):
        name = self.write_raw("raw/sample.json", value if value is not None else {"items": rows})
        return b.build_candidates(manifest([search(name)]), self.base)

    def test_original_fields_and_multiline_content_are_preserved(self):
        source = record(content="第一行。\n\n第二行含 {{企业名称}} 和中文🙂。", title=" 原始完整标题 ")
        original = copy.deepcopy(source)
        bundle, _ = self.build([source])
        self.assertEqual(source, original)
        self.assertEqual(len(bundle["catalog"]), 1)
        item = next(iter(bundle["catalog"].values()))
        for field in source:
            self.assertEqual(item[field], source[field], field)
        self.assertTrue(item["id"])
        self.assertEqual(bundle["candidate_ids"], [item["id"]])
        self.assertIsInstance(bundle["queries"], list)
        self.assertNotIn("block_candidates", bundle)

    def test_stable_id_and_only_exact_duplicates_are_removed(self):
        a = record()
        bundle, _ = self.build([a, copy.deepcopy(a)])
        self.assertEqual(len(bundle["catalog"]), 1)
        first_id = next(iter(bundle["catalog"]))
        rebuilt, _ = self.build([copy.deepcopy(a)])
        self.assertEqual(next(iter(rebuilt["catalog"])), first_id)
        changed, _ = self.build([
            a,
            record(content=a["content"] + "\n新增进展。"),
            record(citation="[source:original-marker-B]"),
            record(published_at="2026-10-11T09:00:00+08:00"),
        ])
        self.assertEqual(len(changed["catalog"]), 4)

    def test_one_initial_and_reasoned_supplement_share_one_deduplicated_pool(self):
        original = record()
        progress = record(title="虚拟企业补充进展", content="已公开项目后续进展。",
                          url="https://example.invalid/progress", published_at="2026-10-11")
        initial = self.write_raw("raw/initial.json", {"items": [original]})
        supplement = self.write_raw("raw/supplement.json", {"items": [original, progress]})
        reason = "原始返回未包含已明确披露的项目后续进展"
        bundle, audit = b.build_candidates(manifest([
            search(initial, query="虚拟企业监测期综合资讯"),
            search(supplement, query="虚拟企业项目进展", kind="supplement", reason=reason),
        ]), self.base)
        self.assertEqual(len(bundle["catalog"]), 2)
        self.assertEqual(len(bundle["candidate_ids"]), 2)
        self.assertEqual(set(bundle["candidate_ids"]), set(bundle["catalog"]))
        self.assertEqual([q["kind"] for q in bundle["queries"]], ["initial", "supplement"])
        self.assertEqual(bundle["queries"][1]["reason"], reason)
        self.assertEqual(audit["duplicate_records_reused"], 1)
        repeated_id = next(i for i, row in bundle["catalog"].items() if row["title"] == original["title"])
        self.assertEqual([origin["search_index"] for origin in bundle["origins"][repeated_id]], [0, 1])
        package, _ = b.compose_package(bundle, selection(bundle["candidate_ids"]))
        self.assertEqual(len(package["news_queries"]), 2)
        self.assertEqual(package["news_queries"][1]["reason"], reason)
        self.assertEqual(len(package["items"]), 2)

    def test_manifest_requires_initial_and_supplements_require_actual_gap_reason(self):
        name = self.write_raw("raw/search-policy.json", {"items": [record()]})
        cases = [[], [search(name, kind="supplement", reason="缺少进展")],
                 [search(name), search(name)],
                 [search(name), search(name, kind="supplement")],
                 [search(name), search(name, kind="supplement", reason="   ")],
                 [search(name), search(name, kind="other", reason="缺少进展")]]
        for searches in cases:
            with self.subTest(searches=searches), self.assertRaises(ValueError):
                b.build_candidates(manifest(searches), self.base)

    def test_aliases_preserve_raw_values_and_notice_derives_v2_without_database_promotion(self):
        source = record(authority_level="L3", authorityLevel="权威度：高",
                        information_type="NEWS", informationType="NOTICE", source_category="")
        bundle, _ = self.build([source])
        item = next(iter(bundle["catalog"].values()))
        self.assertEqual(item["authority_level"], "权威度：高")
        self.assertEqual(item["information_type"], "NOTICE")
        self.assertEqual(item["source_category"], "")
        self.assertEqual(item["source_assessment"]["source_category_v2"], "公司公告或官方网站等")
        self.assertEqual(item["source_assessment"]["authority_v2"], "较高")
        self.assertEqual(item["source_assessment"]["priority"], 1)
        self.assertEqual(item["source_assessment"]["basis"], "original_information_type_NOTICE")

    def test_missing_citation_and_authority_are_not_generated(self):
        source = record(citation="", authority_level="", source_category="", information_type="")
        bundle, _ = self.build([source])
        item = next(iter(bundle["catalog"].values()))
        for field in ("citation", "authority_level", "source_category", "information_type"):
            self.assertEqual(item[field], "")
        self.assertEqual(item["source_assessment"]["authority_v2"], "未知")
        self.assertNotEqual(item["id"], item["citation"])
        item_id = item["id"]
        package, _ = b.compose_package(bundle, selection([item_id]))
        prepared, _ = p.prepare(package, TEMPLATE)
        result_item = prepared["blocks"][0]["prompt_data"]["items"][0]
        self.assertEqual(result_item["url"], source["url"])
        self.assertEqual(result_item["citation"], "")

    def test_missing_date_is_preserved_instead_of_query_date(self):
        bundle, _ = self.build([record(published_at="日期不详")])
        item = next(iter(bundle["catalog"].values()))
        self.assertEqual(item["published_at"], "日期不详")
        package, _ = b.compose_package(bundle, selection([item["id"]]))
        prepared, audit = p.prepare(package, TEMPLATE)
        self.assertEqual(prepared["blocks"][0]["prompt_data"]["items"][0]["published_at"], "日期不详")
        self.assertTrue(audit["blocks"][0]["metadata_notes"])

    def test_explicit_aggregate_remains_one_unsplit_material(self):
        answer = "一、已获批事项。[source:aggregate-A]\n二、仍待核实事项。[source:aggregate-B]"
        units, notes = b.extract_units({"data": {"llmSearchResponse": answer}}, query="虚拟企业资讯")
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["content"], answer)
        self.assertEqual(units[0]["material_kind"], "search_summary")
        self.assertEqual(units[0]["title_origin"], "material_label")
        self.assertEqual(units[0].get("published_at", ""), "")
        self.assertEqual(units[0].get("authority_level", ""), "")

    def test_unknown_json_and_empty_business_return_are_not_news(self):
        cases = [
            {"unrecognized": {"rows": [{"a": "不是新闻"}]}},
            {"content": '{"unknown":"不是新闻"}', "raw": {"unknown": "不是新闻"}},
            {"query": "企业资讯", "content": "", "raw": None, "output_path": None},
            {"data": {"items": [{"title": "仅有标题", "url": "https://example.invalid/a"}]}},
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                units, notes = b.extract_units(raw, query="虚拟企业资讯")
                self.assertEqual(units, [])

    def test_forbidden_acquisition_or_analysis_cannot_be_relabelled_as_news(self):
        for raw in ({"items": [record(acquisition="mql")]},
                    {"generated_analysis": "已有模型分析", "items": [record()]}):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    b.extract_units(raw, query="虚拟企业资讯")
        units, _ = b.extract_units({"acquisition": "mx-finance-search", "items": [
            record(acquisition="mx-finance-search")
        ]}, query="虚拟企业资讯")
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["content"], record()["content"])
        self.assertEqual(units[0]["citation"], record()["citation"])

    def test_live_response_shape_date_url_and_code_are_mapped_conservatively(self):
        # Business shape observed in the real mx return; all contents below are fictional.
        article = {"code": "VIRTUAL_ANNOUNCEMENT_001_3", "title": "虚构原始公告",
                   "content": "虚构公司说明获批事项，暂无到账信息。\n第二行保持不变。",
                   "date": "2026-10-10 09:00:00", "jumpUrl": "https://example.invalid/raw.pdf",
                   "authorityLevel": "L1-3", "informationType": "NOTICE",
                   "recallIndex": "fictional_recall_index;", "rankScore": "Infinity",
                   "indexAttention": False, "attachType": "pdf"}
        raw = {"query": "虚构原始问句", "content": json.dumps({"data": [article]}, ensure_ascii=False),
               "raw": {"code": 200, "status": 0, "data": {
                   "protocolType": "SEARCH_NEWS", "refSeq": None,
                   "llmSearchResponse": {"data": [article], "code": 0, "status": 0}}}}
        bundle, _ = self.build([], value=raw)
        self.assertEqual(len(bundle["catalog"]), 1)
        item = next(iter(bundle["catalog"].values()))
        self.assertEqual(item["title"], article["title"])
        self.assertEqual(item["content"], article["content"])
        self.assertEqual(item["published_at"], article["date"])
        self.assertEqual(item["url"], article["jumpUrl"])
        self.assertEqual(item["authority_level"], "L1-3")
        self.assertEqual(item["information_type"], "NOTICE")
        self.assertEqual(item["citation"], "")
        self.assertEqual(item["source"], "")
        self.assertEqual(item["source_category"], "")
        self.assertEqual(item["source_assessment"]["authority_v2"], "较高")
        self.assertNotIn(article["code"], json.dumps(item, ensure_ascii=False))
        self.assertNotIn(article["recallIndex"], json.dumps(item, ensure_ascii=False))
        self.assertIsNotNone(p.try_iso(item["published_at"]))
        package, _ = b.compose_package(bundle, selection([item["id"]]))
        prepared, _ = p.prepare(package, TEMPLATE)
        final_item = prepared["blocks"][0]["prompt_data"]["items"][0]
        self.assertEqual(final_item["published_at"], article["date"])
        self.assertEqual(final_item["url"], article["jumpUrl"])
        self.assertEqual(final_item["citation"], "")
        self.assertEqual(final_item["source_assessment"]["authority_v2"], "较高")

    def test_shared_candidates_are_sorted_by_five_classes_then_date_stably(self):
        rows = [record(title="社区最新", source_category="community", authority_level="L1", published_at="2026-10-14"),
                record(title="公告旧文", source_category="announcement", authority_level="最高", published_at="2026-10-01"),
                record(title="研报", source_category="research", authority_level="L1", published_at="2026-10-13"),
                record(title="官网新文", source_category="official", authority_level="极低", published_at="2026-10-12"),
                record(title="同日公告", source_category="公告", authority_level="最高", published_at="2026-10-12"),
                record(title="互联网", source_category="internet", authority_level="L1", published_at="2026-10-13"),
                record(title="专业数据库", source_category="专业数据库数据", authority_level="极低", published_at="2026-09-14"),
                record(title="未知", source_category="media", information_type="NEWS", authority_level="L1", published_at="2026-10-14")]
        bundle, audit = self.build(rows)
        expected = ["专业数据库", "官网新文", "同日公告", "公告旧文", "研报", "互联网", "社区最新", "未知"]
        self.assertEqual([bundle["catalog"][source_id]["title"] for source_id in bundle["candidate_ids"]], expected)
        self.assertEqual([row["title"] for row in bundle["catalog"].values()], [row["title"] for row in rows])
        self.assertEqual(audit["candidate_sort_keys"], ["authority_v2_priority", "published_at_desc", "original_index"])
        index = b.candidate_index(bundle)
        self.assertEqual(sorted(expected, key=index.index), expected)
        for source_id in bundle["candidate_ids"]:
            self.assertEqual(index.count("`" + source_id + "`"), 1)
        self.assertNotIn("## key-events", index)
        self.assertNotIn("## related-environment", index)
        for grade in ("最高", "较高", "中等", "较低", "极低", "未知"):
            self.assertIn("权威度：" + grade, index)

    def test_derived_assessment_cannot_change_identity_or_promote_compose_and_prepare(self):
        source = record(source_category="social_media", authority_level="L1-3", information_type="WECHAT")
        bundle, _ = self.build([source])
        original_id = next(iter(bundle["catalog"]))
        original_record = copy.deepcopy(bundle["catalog"][original_id])
        forged = {"source_category_v2": "专业数据库数据", "authority_v2": "最高", "priority": 0, "basis": "forged"}
        rebuilt, _ = self.build([{**source, "source_assessment": forged}])
        self.assertEqual(list(rebuilt["catalog"]), [original_id])
        self.assertEqual(rebuilt["catalog"][original_id]["source_assessment"]["authority_v2"], "极低")
        changed = copy.deepcopy(bundle)
        changed["catalog"][original_id]["source_assessment"] = forged
        chosen = selection([original_id])
        package, _ = b.compose_package(changed, chosen)
        composed_record = package["items"][0]
        self.assertEqual(composed_record["id"], original_id)
        self.assertEqual(composed_record["source_assessment"]["authority_v2"], "极低")
        self.assertIn("权威度：极低", b.candidate_index(changed))
        self.assertNotIn("权威度：最高", b.candidate_index(changed))
        for field in p.ITEM_FIELDS:
            self.assertEqual(composed_record[field], original_record[field], field)
        composed_record["source_assessment"] = forged
        prepared, _ = p.prepare(package, TEMPLATE)
        final_record = prepared["blocks"][0]["prompt_data"]["items"][0]
        self.assertEqual(final_record["source_assessment"]["authority_v2"], "极低")
        self.assertEqual(final_record["source_category"], "social_media")
        self.assertEqual(final_record["authority_level"], "L1-3")

    def test_aggregate_source_hints_do_not_assign_every_underlying_fact_a_grade(self):
        raw = {"summary": "汇总多条原始信息。[source:summary-A]",
               "source_category": "", "source": "新华社", "information_type": "NOTICE",
               "authority_level": "L1", "url": "https://www.sse.com.cn/news/summary"}
        bundle, _ = self.build([], value=raw)
        item = next(iter(bundle["catalog"].values()))
        self.assertEqual(item["material_kind"], "search_summary")
        self.assertEqual(item["source_assessment"]["authority_v2"], "未知")
        self.assertEqual(item["source_assessment"]["priority"], 5)
        self.assertEqual(item["authority_level"], "L1")

    def test_explicit_empty_and_failed_searches_keep_query_status(self):
        raw_name = self.write_raw("raw/empty.json", {"query": "查询", "content": "", "raw": None})
        plan = manifest([
            search(raw_name, status="empty"),
            search(raw_name, status="failed", kind="supplement", reason="综合检索为空，核查目标事件"),
            search(raw_name, status="need_auth", kind="supplement", reason="上次补查失败，重试同一事实缺口"),
        ])
        bundle, _ = b.build_candidates(plan, self.base)
        self.assertEqual(bundle["catalog"], {})
        self.assertEqual([q["status"] for q in bundle["queries"]], ["empty", "failed", "need_auth"])
        package, _ = b.compose_package(bundle, selection())
        prepared, audit = p.prepare(package, TEMPLATE)
        self.assertEqual(len(prepared["blocks"]), 1)
        self.assertEqual(prepared["blocks"][0]["status"], "empty")
        self.assertEqual([q["status"] for q in audit["blocks"][0]["news_queries"]], ["empty", "failed", "need_auth"])

    def test_single_shared_package_produces_one_prompt_with_three_output_chapters(self):
        bundle, _ = self.build([record()])
        item_id = next(iter(bundle["catalog"]))
        chosen = selection([item_id])
        before = copy.deepcopy(bundle)
        package, audit = b.compose_package(bundle, chosen)
        self.assertEqual(bundle, before)
        self.assertEqual(set(package), {"acquisition", "entity", "context", "news_queries", "items", "events"})
        self.assertEqual(package["items"][0]["content"], record()["content"])
        self.assertEqual(package["items"][0]["citation"], record()["citation"])
        self.assertEqual(len(package["news_queries"]), 1)
        self.assertIn(item_id, json.dumps(audit, ensure_ascii=False))
        prepared, prepared_audit = p.prepare(package, TEMPLATE)
        self.assertEqual(len(prepared["blocks"]), 1)
        self.assertEqual(len(prepared_audit["blocks"]), 1)
        shared = prepared["blocks"][0]
        self.assertEqual(shared["key"], "shared-analysis")
        self.assertEqual(shared["status"], "ready")
        self.assertEqual(shared["output_blocks"], list(p.NEWS_BLOCK_KEYS))
        self.assertEqual(shared["prompt"].count(record()["content"]), 1)
        self.assertEqual(len(shared["prompt_data"]["items"]), 1)

    def test_old_chapter_routing_and_selections_are_rejected(self):
        raw_name = self.write_raw("raw/unsupported-route.json", {"items": [record()]})
        bundle, _ = self.build([record()])
        item_id = next(iter(bundle["catalog"]))
        for old_field in ("block_keys", "blocks", "block_candidates"):
            with self.subTest(field=old_field):
                old_manifest = manifest([search(raw_name)])
                old_manifest[old_field] = ["key-events"]
                with self.assertRaises(ValueError):
                    b.build_candidates(old_manifest, self.base)
                old_bundle = copy.deepcopy(bundle)
                old_bundle[old_field] = {"key-events": [item_id]}
                with self.assertRaises(ValueError):
                    b.compose_package(old_bundle, selection([item_id]))
        for old_field in ("block_key", "block_keys", "blocks"):
            with self.subTest(search_field=old_field):
                old_search = search(raw_name)
                old_search[old_field] = ["key-events"]
                with self.assertRaises(ValueError):
                    b.build_candidates(manifest([old_search]), self.base)
                old_queries = copy.deepcopy(bundle)
                old_queries["queries"][0][old_field] = ["key-events"]
                with self.assertRaises(ValueError):
                    b.compose_package(old_queries, selection())
        for chapter in (*p.NEWS_BLOCK_KEYS, "risk-impact", "key-concerns", "follow-up"):
            with self.subTest(chapter=chapter):
                with self.assertRaises(ValueError):
                    b.compose_package(bundle, {"selected_ids": {chapter: [item_id]}, "events": []})
                with self.assertRaises(ValueError):
                    b.compose_package(bundle, {"selected_ids": [item_id], "events": {chapter: [event([item_id])]}})

    def test_unknown_selection_and_unselected_event_sources_are_rejected(self):
        bundle, _ = self.build([record(), record(url="https://example.invalid/002", title="第二条公告")])
        item_ids = list(bundle["catalog"])
        with self.assertRaises(ValueError):
            b.compose_package(bundle, selection(["made-up-id"]))
        chosen = selection([item_ids[0]], [event([item_ids[1]])])
        with self.assertRaises(ValueError):
            b.compose_package(bundle, chosen)

    def test_duplicate_selection_and_inconsistent_shared_candidate_ids_are_rejected(self):
        bundle, _ = self.build([record()])
        item_id = next(iter(bundle["catalog"]))
        with self.assertRaises(ValueError):
            b.compose_package(bundle, selection([item_id, item_id]))
        for ids in ([], [item_id, item_id], ["made-up-id"]):
            broken = {**bundle, "candidate_ids": ids}
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                b.compose_package(broken, selection())

    def test_selection_cannot_supply_rewritten_items_or_unverified_events(self):
        bundle, _ = self.build([record()])
        item_id = next(iter(bundle["catalog"]))
        chosen = {**selection([item_id]), "items": [record(content="模型重写全文")]}
        with self.assertRaises(ValueError):
            b.compose_package(bundle, chosen)
        with self.assertRaises(ValueError):
            b.compose_package(bundle, selection([item_id], [event([item_id], verified=False)]))

    def test_changed_catalog_content_cannot_reuse_original_stable_id(self):
        bundle, _ = self.build([record()])
        item_id = next(iter(bundle["catalog"]))
        chosen = selection([item_id])
        original_package, audit = b.compose_package(bundle, chosen)
        changed = copy.deepcopy(bundle)
        changed["catalog"][item_id]["content"] += "\n未经原始返回支持的新增文字。"
        with self.assertRaises(ValueError):
            b.compose_package(changed, chosen)
        valid_package, _ = b.compose_package(bundle, chosen)
        self.assertEqual(valid_package, original_package)
        self.assertEqual(bundle["catalog"][item_id]["content"], record()["content"])
        self.assertEqual(audit["model_supplied_item_content_characters"], 0)
        self.assertGreater(audit["selection_characters"], 0)
        self.assertEqual(audit["catalog_content_characters"], len(record()["content"]))

    def test_optional_verified_event_preserves_source_bindings_through_prepare(self):
        bundle, _ = self.build([record()])
        item_id = next(iter(bundle["catalog"]))
        chosen = selection([item_id], [event([item_id])])
        package, _ = b.compose_package(bundle, chosen)
        prepared, _ = p.prepare(package, TEMPLATE)
        analyzed = prepared["blocks"][0]["prompt_data"]["events"][0]
        self.assertEqual(analyzed["latest_dated_status"], "已披露获批")
        self.assertEqual(analyzed["claims"][0]["sources"][0]["url"], record()["url"])
        self.assertEqual(analyzed["claims"][0]["sources"][0]["citation"], record()["citation"])
        self.assertNotIn("source_ids", analyzed["claims"][0])
        no_events, _ = b.compose_package(bundle, selection([item_id]))
        self.assertEqual(no_events["events"], [])

    def test_long_sources_preserved_and_future_material_excluded_without_catalog_mutation(self):
        future = record(title="截至后才披露", published_at="2026-10-14T17:00:00+08:00")
        long_record = record(title="长篇全文", content="完整长正文。" * 5000, url="https://example.invalid/long")
        small = record(title="尾部小条", published_at="2026-10-09", url="https://example.invalid/small")
        bundle, _ = self.build([future, long_record, small])
        before = copy.deepcopy(bundle)
        chosen = selection(list(bundle["catalog"]))
        package, _ = b.compose_package(bundle, chosen)
        prepared, audit = p.prepare(package, TEMPLATE)
        self.assertEqual(bundle, before)
        self.assertEqual(len(bundle["catalog"]), 3)
        block = prepared["blocks"][0]
        self.assertEqual(block["status"], "ready")
        self.assertEqual([entry["title"] for entry in block["prompt_data"]["items"]], ["长篇全文", "尾部小条"])
        self.assertIn(long_record["content"], block["prompt"])
        self.assertIn(small["content"], block["prompt"])
        self.assertNotIn("截至后才披露", block["prompt"])
        self.assertEqual(len(audit["blocks"][0]["excluded_post_cutoff_item_ids"]), 1)
        self.assertEqual(len(audit["blocks"][0]["dropped_item_ids"]), 1)
        self.assertEqual(next(i for i in bundle["catalog"].values() if i["title"] == "长篇全文")["content"], long_record["content"])

    def test_unknown_request_metadata_does_not_enter_bundle_or_package(self):
        secret = "VIRTUAL_CREDENTIAL_SENTINEL_DO_NOT_COPY"
        raw = {"items": [record()], "headers": {"Authorization": secret}, "apiKey": secret,
               "request": {"password": secret}, "trace": {"token": secret}}
        name = self.write_raw("raw/metadata.json", raw)
        plan = manifest([search(name)])
        plan["headers"] = {"Authorization": secret}
        plan["searches"][0]["request_headers"] = {"Authorization": secret}
        bundle, audit = b.build_candidates(plan, self.base)
        self.assertNotIn(secret, json.dumps([bundle, audit], ensure_ascii=False))
        package, composed_audit = b.compose_package(bundle, selection(list(bundle["catalog"])))
        prepared, prepared_audit = p.prepare(package, TEMPLATE)
        self.assertNotIn(secret, json.dumps([package, composed_audit, prepared, prepared_audit], ensure_ascii=False))

    def test_credential_source_url_is_not_exposed_in_generated_material(self):
        secret = "VIRTUAL_URL_SECRET_DO_NOT_COPY"
        name = self.write_raw("raw/bad-url.json", {"items": [record(url="https://example.invalid/news?access_token=" + secret)]})
        try:
            bundle, audit = b.build_candidates(manifest([search(name)]), self.base)
        except ValueError as exc:
            self.assertNotIn(secret, str(exc))
        else:
            self.assertNotIn(secret, json.dumps([bundle, audit], ensure_ascii=False))
            self.assertEqual(bundle["catalog"], {})

    def test_manifest_relative_paths_and_cli_no_overwrite(self):
        raw_name = self.write_raw("nested/raw.json", {"items": [record()]})
        manifest_path = self.base / "manifest.json"
        manifest_path.write_text(json.dumps(manifest([search(raw_name)]), ensure_ascii=False), encoding="utf-8")
        original_input = manifest_path.read_bytes()
        output_dir = self.base / "built"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            first = b.main(["build", "--manifest", str(manifest_path), "--out", str(output_dir)])
        self.assertEqual(first, 0)
        files = {file.name: file.read_bytes() for file in output_dir.iterdir() if file.is_file()}
        self.assertTrue(files)
        self.assertTrue(any("虚拟企业项目公告" in data.decode("utf-8") for data in files.values()))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            second = b.main(["build", "--manifest", str(manifest_path), "--out", str(output_dir)])
        self.assertEqual(second, 2)
        self.assertEqual(files, {file.name: file.read_bytes() for file in output_dir.iterdir() if file.is_file()})
        self.assertEqual(manifest_path.read_bytes(), original_input)


if __name__ == "__main__":
    unittest.main(verbosity=2)
