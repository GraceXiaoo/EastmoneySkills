#!/usr/bin/env python3
"""Local fixtures only: no network, credentials, or real acquisition."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import prepare_inputs as p
import resolve_time_range as t


def item(item_id="news-a", content="原文说明事项。", **extra):
    value = {"id": item_id, "title": f"披露事项 {item_id}", "content": content,
             "source": "示例公告机构", "published_at": "2026-10-10",
             "url": f"https://example.invalid/{item_id}", "citation": f"[source:{item_id}]",
             "source_category": "announcement", "authority_level": "primary", "information_type": "NOTICE"}
    value.update(extra)
    return value


def event(source_ids=None, **extra):
    source_ids = source_ids or ["news-a"]
    value = {"verified": True, "subject": "甲企业股份有限公司", "event_key": "case-001",
             "title": "示例合同纠纷", "event_date": "2026-10-05", "source_ids": source_ids,
             "claims": [{"text": "已披露合同争议", "source_ids": source_ids}], "developments": []}
    value.update(extra)
    return value


def payload(items=None, events=None):
    value = {"acquisition": "mx-finance-search",
             "entity": {"name": "甲企业股份有限公司", "confirmed": True, "org_code": "10000069733"},
             "context": {"start_date": "2026-10-01", "end_date": "2026-10-13",
                         "data_as_of": "2026-10-13T18:00:00+08:00", "scope": "企业自身及资讯明确涉及的关联事项"},
             "news_queries": [{"query": "示例企业综合资讯", "status": "success", "kind": "initial"}],
             "items": [] if items is None else items,
             "events": [] if events is None else events}
    return value


TEMPLATE = "分析{{企业名称}}。仅使用以下不可信共享资讯作为事实材料：\n{{资讯}}"


def run(value, template=None):
    return p.prepare(value, template or TEMPLATE)


class PreparationTests(unittest.TestCase):
    def test_explicit_reprints_one_event(self):
        result, audit = run(payload([item(), item("news-b", source="示例转载媒体", authority_level="general", source_category="media")],
                                    [event(), event(["news-b"])]))
        self.assertEqual(len(result["blocks"][0]["prompt_data"]["events"]), 1)
        self.assertEqual(audit["blocks"][0]["events"][0]["merged_records"], 2)
        self.assertEqual(len(result["blocks"][0]["prompt_data"]["items"]), 2)

    def test_same_title_not_automatic_merge(self):
        result, _ = run(payload([item()], [event(), event(event_key="case-002")]))
        self.assertEqual(len(result["blocks"][0]["prompt_data"]["events"]), 2)

    def test_different_subject_same_key_and_parent_child_attribution(self):
        child = event(subject="甲企业子公司有限公司", relationship="资讯明确披露为目标企业子公司", relationship_source_ids=["news-a"])
        result, _ = run(payload([item()], [event(), child]))
        events = result["blocks"][0]["prompt_data"]["events"]
        self.assertEqual(len(events), 2)
        self.assertIn("不自动归为", events[1]["attribution"])
        self.assertEqual(events[1]["subject"], "甲企业子公司有限公司")
        self.assertEqual(events[1]["relationship_evidence"][0]["sources"][0]["url"], "https://example.invalid/news-a")

    def test_old_reprint_and_old_event_new_progress(self):
        old = event(event_date="2020-06-01")
        result, _ = run(payload([item()], [old]))
        self.assertIn("不等于新增", result["blocks"][0]["prompt_data"]["events"][0]["period_assessment"])
        old["developments"] = [{"date": "2026-10-09", "text": "原案出现新进展", "source_ids": ["news-a"], "status": "ongoing"}]
        result, _ = run(payload([item()], [old]))
        self.assertIn("本期有已核验进展", result["blocks"][0]["prompt_data"]["events"][0]["period_assessment"])
        result, _ = run(payload([item()], [event(event_date="")]))
        self.assertIn("不能据发布时间", result["blocks"][0]["prompt_data"]["events"][0]["period_assessment"])

    def test_planned_approved_received_explicit_progress(self):
        for status, expected in (("planned", "计划阶段"), ("approved", "已披露获批"), ("received", "已披露到账")):
            result, _ = run(payload([item()], [event(status=status, status_date="2026-10-10")]))
            business = result["blocks"][0]["prompt_data"]["events"][0]
            self.assertEqual(business["latest_dated_status"], expected)
            if status != "received":
                self.assertIn("不等于资金到账", business["status_note"])

    def test_clarification_and_release_not_global_resolution(self):
        for status in ("clarified", "released", "resolved", "withdrawn"):
            result, _ = run(payload([item()], [event(status=status, status_date="2026-10-10")]))
            note = result["blocks"][0]["prompt_data"]["events"][0]["status_note"]
            self.assertTrue("不自动" in note or "不覆盖" in note)

    def test_status_conflicts_and_cutoff(self):
        result, _ = run(payload([item()], [event(status="approved", status_date="2026-10-10"), event(status="received", status_date="2026-10-10")]))
        self.assertEqual(result["blocks"][0]["prompt_data"]["events"][0]["latest_dated_status"], "状态未核验")
        result, _ = run(payload([item()], [event(status="received", status_date="2026-10-13T19:00:00+08:00")]))
        self.assertEqual(result["blocks"][0]["prompt_data"]["events"][0]["latest_dated_status"], "状态未核验")

    def test_amount_conflict_retained_never_summed(self):
        first = event(claims=[{"text": "披露金额100万元", "source_ids": ["news-a"], "fact_key": "claim_amount", "amount": "100", "currency": "CNY", "unit": "万元"}])
        second = event(["news-b"], claims=[{"text": "另有披露金额120万元", "source_ids": ["news-b"], "fact_key": "claim_amount", "amount": "120", "currency": "CNY", "unit": "万元"}])
        result, audit = run(payload([item(), item("news-b")], [first, second]))
        business = result["blocks"][0]["prompt_data"]["events"][0]
        self.assertEqual({c["amount"] for c in business["claims"]}, {"100", "120"})
        self.assertIn("未求和", business["conflict_note"])
        self.assertEqual(audit["blocks"][0]["events"][0]["fact_conflicts"], ["claim_amount"])

    def test_empty_is_not_no_risk_and_default_calendar_month_window(self):
        value = payload()
        del value["context"]["start_date"]
        del value["context"]["end_date"]
        result, _ = run(value)
        self.assertEqual(result["context"]["start_date"], "2026-07-13")
        self.assertEqual(len(result["blocks"]), 1)
        self.assertTrue(all(b["status"] == "empty" for b in result["blocks"]))
        self.assertIn("不能由此", result["blocks"][0]["news_text"])

    def test_complete_code_confirmation_and_candidates(self):
        for mutation in ({"org_code": "600519"}, {"org_code": 10000069733}, {"confirmed": False}):
            value = payload()
            value["entity"].update(mutation)
            with self.assertRaises(p.InputError):
                run(value)
        candidates = p.candidate_result({"candidates": [{"name": "甲", "org_code": "10000069733"}, {"name": "乙", "org_code": "10002602"}]})
        self.assertIsNone(candidates["selected"])
        self.assertEqual(candidates["status"], "confirmation_required")

    def test_confirmed_name_only_and_full_fxr_identity(self):
        value = payload()
        del value["entity"]["org_code"]
        result, audit = run(value)
        self.assertEqual(result["entity"]["name"], "甲企业股份有限公司")
        self.assertNotIn("org_code", audit["entity_identity"])
        value["entity"]["org_code"] = "10000069733.FXR"
        _, audit = run(value)
        self.assertEqual(audit["entity_identity"]["org_code"], "10000069733.FXR")

    def test_sources_forbidden_packages_and_fixed_keys(self):
        for mutation in ({"acquisition": "MQL-MCP"}, {"generated_analysis": "旧分析"}, {"datasets": {}}):
            value = payload()
            value.update(mutation)
            with self.assertRaises(p.InputError):
                run(value)
        value = payload([item(acquisition="MQL-MCP")])
        with self.assertRaises(p.InputError):
            run(value)

    def test_news_preparation_rejects_old_section_packages_and_separate_templates(self):
        for unsupported_key in (*p.NEWS_BLOCK_KEYS, "key-concerns", "follow-up"):
            with self.subTest(key=unsupported_key):
                value = payload([item()])
                value["blocks"] = [{"key": unsupported_key, "items": [item()], "events": []}]
                with self.assertRaises(p.InputError):
                    run(value)
        with self.assertRaises(p.InputError):
            run(payload(), {key: TEMPLATE for key in p.NEWS_BLOCK_KEYS})

    def test_no_dangling_references_and_shared_source_binding(self):
        for e in (event(["invented"]), event(claims=[{"text": "伪造引用", "source_ids": ["invented"]}]), event(verified=False)):
            with self.assertRaises(p.InputError):
                run(payload([item()], [e]))
        result, _ = run(payload([item(), item("shared-source")], [event(["shared-source"])]))
        self.assertEqual(result["blocks"][0]["prompt_data"]["events"][0]["sources"][0]["url"],
                         "https://example.invalid/shared-source")

    def test_credentials_queries_identity_fields_isolated_and_braces_literal(self):
        value = payload([item(content="原文包含 {{企业名称}} 和 {{资讯}} 字样。", credentials={"api_key": "DO_NOT_LEAK"})], [event()])
        value["context"]["query"] = "INTERNAL_QUERY"
        value["news_queries"] = [{"query": "INTERNAL_QUERY", "password": "DO_NOT_LEAK"}]
        result, audit = run(value)
        business_text = result["blocks"][0]["prompt"]
        for forbidden in ("INTERNAL_QUERY", "DO_NOT_LEAK", "10000069733", '"source_ids"', '"event_key"'):
            self.assertNotIn(forbidden, business_text)
        self.assertIn("{{企业名称}} 和 {{资讯}}", business_text)
        self.assertNotIn("DO_NOT_LEAK", json.dumps(audit))
        self.assertIn("[source:news-a]", business_text)
        self.assertIn("https://example.invalid/news-a", business_text)

    def test_wordcloud_binding_keeps_material_id_with_original_source(self):
        source = item("wordcloud-source", content="公司披露本期项目进展。")
        result, audit = run(payload([source]))
        block = result["blocks"][0]
        bound = block["prompt_data"]["items"][0]
        self.assertEqual(bound["id"], source["id"])
        self.assertEqual(bound["url"], source["url"])
        self.assertEqual(bound["citation"], source["citation"])
        self.assertIn("材料ID（仅供词云标签绑定，不作来源引用、不写入报告）：wordcloud-source", block["news_text"])
        self.assertEqual(audit["blocks"][0]["kept_item_ids"], [source["id"]])

    def test_stable_source_authority_and_time_sorting(self):
        values = [item("media-new", authority_level="general", source_category="authoritative_media", published_at="2026-10-13"),
                  item("official-old", authority_level="L1", published_at="2026-10-01"), item("official-new", authority_level="极低", published_at="2026-10-12"),
                  item("tie", authority_level="最高", published_at="2026-10-12")]
        _, audit = run(payload(values))
        self.assertEqual(audit["blocks"][0]["kept_item_ids"], ["official-new", "tie", "official-old", "media-new"])

    def test_five_source_classes_override_raw_authority_codes(self):
        values = [item("community", source_category="其它社区或自媒体消息", authority_level="L1", published_at="2026-10-13"),
                  item("internet", source_category="互联网检索资讯", authority_level="权威度：最高", published_at="2026-10-12"),
                  item("research", source_category="研报或权威新闻媒体等", authority_level="L1-3", published_at="2026-10-11"),
                  item("notice", source_category="公司公告或官方网站等", authority_level="极低", published_at="2026-10-10"),
                  item("database", source_category="专业数据库数据", authority_level="未知原始等级", published_at="2026-10-01"),
                  item("unknown", source_category="media", information_type="NEWS", authority_level="L1", published_at="2026-10-13")]
        result, audit = run(payload(values))
        self.assertEqual(audit["blocks"][0]["kept_item_ids"], ["database", "notice", "research", "internet", "community", "unknown"])
        records = result["blocks"][0]["prompt_data"]["items"]
        self.assertEqual([row["source_assessment"]["authority_v2"] for row in records], ["最高", "较高", "中等", "较低", "极低", "未知"])
        self.assertEqual([row["source_assessment"]["priority"] for row in records], list(range(6)))
        original = {row["title"]: row for row in values}
        for row in records:
            self.assertEqual(row["source_category"], original[row["title"]]["source_category"])
            self.assertEqual(row["authority_level"], original[row["title"]]["authority_level"])

    def test_source_priority_and_no_database_promotion_from_mx_channel(self):
        values = [item("notice", source="数据库检索返回的公告", source_category="", information_type="NOTICE", published_at="2026-10-13"),
                  item("report", source_category="research", information_type="REPORT", published_at="2026-10-12"),
                  item("law", source_category="", information_type="LAW", published_at="2026-10-11"),
                  item("bond", source_category="BOND", information_type="BOND", published_at="2026-10-10"),
                  item("database", source_category="专业数据库数据", authority_level="未知等级", published_at="2026-10-01")]
        result, audit = run(payload(values))
        self.assertEqual(audit["blocks"][0]["kept_item_ids"], ["database", "notice", "report", "law", "bond"])
        self.assertEqual(audit["blocks"][0]["sort_keys"], ["authority_v2_priority", "published_at_desc", "original_index"])
        self.assertEqual(result["blocks"][0]["prompt_data"]["items"][0]["source_category"], "专业数据库数据")
        notice = next(row for row in result["blocks"][0]["prompt_data"]["items"] if row["title"] == "披露事项 notice")
        self.assertEqual(notice["source_category"], "")
        self.assertEqual(notice["source_assessment"]["authority_v2"], "较高")
        self.assertEqual(audit["acquisition"], "mx-finance-search")
        with self.assertRaises(p.InputError):
            run(payload([item(source_category="专业数据库数据", acquisition="mql")]))

    def test_source_class_aliases_and_explicit_category_precedence(self):
        cases = (("professional_database", "最高"), ("announcement", "较高"), ("official", "较高"),
                 ("官方网站", "较高"), ("research", "中等"), ("authoritative_media", "中等"),
                 ("internet", "较低"), ("web", "较低"), ("community", "极低"), ("social_media", "极低"))
        for category, expected in cases:
            with self.subTest(category=category):
                value = item(source_category=category, information_type="NOTICE", source="新华社", url="https://www.sse.com.cn/disclosure/a")
                self.assertEqual(p.assess_source(value)["authority_v2"], expected)

    def test_missing_and_ambiguous_metadata_never_uses_raw_authority(self):
        for category in ("", "media", "news", "其它信源", "未知标签"):
            for raw_authority in ("L1", "L1-3", "L2", "L3", "高", "低", "primary", "权威度：最高", ""):
                with self.subTest(category=category, raw_authority=raw_authority):
                    value = item(source_category=category, authority_level=raw_authority, information_type="", source="未知原始机构")
                    grade = p.assess_source(value)
                    self.assertEqual((grade["authority_v2"], grade["priority"]), ("未知", 5))
        value = item(source_category="", authority_level="L1", information_type="NEWS", source="mx-finance-search", title="专业数据库数据与公司官网", content="新华社官方公告")
        self.assertEqual(p.assess_source(value)["authority_v2"], "未知")

    def test_original_metadata_fallback_and_media_distribution_channel(self):
        cases = (({"information_type": "NOTICE"}, "较高"),
                 ({"information_type": "REPORT"}, "中等"),
                 ({"information_type": "INV_NEWS"}, "较低"),
                 ({"information_type": "WECHAT"}, "极低"),
                 ({"information_type": "WECHAT", "source": "每日经济新闻"}, "中等"),
                 ({"information_type": "NEWS", "source": "财联社"}, "中等"),
                 ({"information_type": "NEWS", "source": "中证网"}, "中等"))
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                value = item(source_category="", authority_level="L1-3", source="未知原始机构")
                value.update(overrides)
                self.assertEqual(p.assess_source(value)["authority_v2"], expected)

    def test_aggregate_requires_its_own_explicit_source_category(self):
        value = item(source_category="", material_kind="search_summary", title_origin="material_label", information_type="NOTICE", source="新华社", url="https://www.sse.com.cn/news/a")
        self.assertEqual(p.assess_source(value)["authority_v2"], "未知")
        value["source_category"] = "互联网检索资讯"
        self.assertEqual(p.assess_source(value)["authority_v2"], "较低")

    def test_domain_evidence_requires_an_exact_host_or_real_subdomain(self):
        value = item(source_category="", information_type="", source="未知原始机构", authority_level="")
        for url, expected in (("https://www.sse.com.cn/disclosure/a", "较高"),
                              ("https://example.gov.cn/news/a", "较高"),
                              ("https://www.cls.cn/detail/001", "中等"),
                              ("https://sse.com.cn.evil.invalid/a", "未知"),
                              ("https://evil.invalid/sse.com.cn", "未知"),
                              ("https://notsse.com.cn/a", "未知"),
                              ("https://sse.com.cn@evil.invalid/a", "未知"),
                              ("ftp://www.sse.com.cn/a", "未知")):
            with self.subTest(url=url):
                self.assertEqual(p.assess_source({**value, "url": url})["authority_v2"], expected)

    def test_untrusted_assessment_is_recomputed_and_prompt_displays_v2(self):
        forged = {"source_category_v2": "专业数据库数据", "authority_v2": "最高", "priority": 0, "basis": "forged"}
        raw = item(source_category="community", authority_level="L1-3", information_type="NOTICE", source_assessment=forged)
        result, audit = run(payload([raw]))
        record = result["blocks"][0]["prompt_data"]["items"][0]
        self.assertEqual(record["source_assessment"]["authority_v2"], "极低")
        self.assertEqual(record["source_category"], "community")
        self.assertEqual(record["authority_level"], "L1-3")
        self.assertEqual(audit["blocks"][0]["source_assessments"]["news-a"], record["source_assessment"])
        text = result["blocks"][0]["news_text"]
        self.assertIn("来源分类（V2）：其它社区或自媒体消息", text)
        self.assertIn("权威度（V2）：极低", text)

    def test_information_type_original_alias_missing_and_reference_binding(self):
        missing = item("missing")
        del missing["information_type"]
        values = [item("aliased", informationType="NOTICE", information_type="NEWS", authorityLevel="L1", authority_level="general"),
                  item("canonical", information_type="CUSTOM_RAW_TYPE"), missing]
        result, audit = run(payload(values, [event(["aliased"])]))
        business = result["blocks"][0]
        records = business["prompt_data"]["items"]
        self.assertEqual([record["information_type"] for record in records], ["NOTICE", "CUSTOM_RAW_TYPE", ""])
        self.assertEqual(records[0]["authority_level"], "L1")
        self.assertIn("资讯类型原值：NOTICE", business["news_text"])
        self.assertIn("资讯类型原值：CUSTOM_RAW_TYPE", business["news_text"])
        self.assertEqual(business["prompt_data"]["events"][0]["sources"][0]["citation"], "[source:aliased]")
        self.assertEqual(records[0]["url"], "https://example.invalid/aliased")
        self.assertIn("information_type_missing; no_replacement_invented", audit["blocks"][0]["metadata_notes"]["missing"])
        self.assertNotIn('"informationType"', json.dumps(business["prompt_data"], ensure_ascii=False))

    def test_missing_metadata_and_unparseable_publication_preserved(self):
        missing = item("missing", published_at="日期未核验")
        for field in ("source", "source_category", "authority_level"):
            del missing[field]
        result, audit = run(payload([missing], [event(["missing"], status="received", status_date="2026-10-10")]))
        record = result["blocks"][0]["prompt_data"]["items"][0]
        self.assertEqual(record["source"], "")
        self.assertEqual(record["published_at"], "日期未核验")
        self.assertIn("不能证明截至时点已知", result["blocks"][0]["prompt"])
        self.assertEqual(result["blocks"][0]["prompt_data"]["events"][0]["latest_dated_status"], "状态未核验")
        self.assertIn("missing", audit["blocks"][0]["metadata_notes"])

    def test_textual_publisher_without_url_or_citation(self):
        result, audit = run(payload([item(url="", citation="", source="真实原始机构名称")]))
        record = result["blocks"][0]["prompt_data"]["items"][0]
        self.assertEqual(record["url"], "")
        self.assertEqual(record["citation"], "")
        self.assertEqual(record["content"], "原文说明事项。")
        self.assertIn("textual_source_attribution_only", " ".join(audit["blocks"][0]["metadata_notes"]["news-a"]))
        with self.assertRaises(p.InputError):
            run(payload([item(url="", citation="", source="")]))

    def test_post_cutoff_items_and_events_removed_as_whole_sources(self):
        result, audit = run(payload([item(), item("future", content="截至之后才公开的事实", published_at="2026-10-14")],
                                    [event(["news-a", "future"])]))
        business = result["blocks"][0]
        self.assertNotIn("截至之后才公开的事实", business["prompt"])
        self.assertEqual(business["prompt_data"]["events"], [])
        self.assertEqual(audit["blocks"][0]["excluded_post_cutoff_item_ids"], ["future"])

    def test_future_completed_progress_excluded_but_disclosed_plan_retained(self):
        e = event(developments=[
            {"date": "2026-10-15", "text": "未来才完成到账", "status": "received", "source_ids": ["news-a"]},
            {"date": "2026-10-15", "text": "公开材料中的未来计划节点", "status": "planned", "statement": "plan", "source_ids": ["news-a"]}])
        result, audit = run(payload([item()], [e]))
        prompt = result["blocks"][0]["prompt"]
        self.assertNotIn("未来才完成到账", prompt)
        self.assertIn("未来计划节点", prompt)
        self.assertIn("不表示截至时点已经发生或完成", prompt)
        self.assertEqual(audit["blocks"][0]["future_event_fact_exclusions"][0]["future_fact_developments_removed"], 1)

    def test_future_completed_event_excluded_and_plan_event_retained(self):
        completed = event(event_date="2026-10-15", status="received", status_date="2026-10-15", title="未来已发生到账事项")
        plan = event(event_key="future-plan", event_date="2026-10-15", status="planned", statement="plan", title="已公开未来计划事项")
        result, audit = run(payload([item()], [completed, plan]))
        business = result["blocks"][0]
        self.assertEqual(len(business["prompt_data"]["events"]), 1)
        self.assertNotIn("未来已发生到账事项", business["prompt"])
        self.assertIn("已公开未来计划事项", business["prompt"])
        self.assertIn("计划部分不表示截至时点已经发生或完成", business["prompt"])
        self.assertTrue(audit["blocks"][0]["future_event_fact_exclusions"][0]["future_event_removed"])

    def test_long_news_body_is_preserved_completely(self):
        content = "完整正文开头\n" + "文" * 50000 + "\n完整正文结尾"
        value = payload([item(content=content)])
        result, audit = run(value)
        self.assertIn("权威度（V2）：较高", result["blocks"][0]["prompt"])
        self.assertEqual(result["blocks"][0]["prompt_length"], len(result["blocks"][0]["prompt"]))
        self.assertEqual(result["blocks"][0]["prompt_data"]["items"][0]["content"], content)
        self.assertIn(content, result["blocks"][0]["prompt"])
        self.assertEqual(audit["blocks"][0]["kept_item_ids"], ["news-a"])
        self.assertEqual(audit["blocks"][0]["prompt_length"], len(result["blocks"][0]["prompt"]))

    def test_long_first_source_keeps_later_sources_and_complete_event(self):
        value = payload([item(content="大" * 20000), item("news-b", content="小", published_at="2026-10-09")], [event(["news-a", "news-b"])])
        result, audit = run(value)
        business = result["blocks"][0]
        self.assertEqual([record["content"] for record in business["prompt_data"]["items"]], ["大" * 20000, "小"])
        self.assertEqual(len(business["prompt_data"]["events"]), 1)
        self.assertEqual(len(business["prompt_data"]["events"][0]["sources"]), 2)
        self.assertEqual(audit["blocks"][0]["kept_item_ids"], ["news-a", "news-b"])
        self.assertTrue(audit["blocks"][0]["events"][0]["kept"])

    def test_long_news_does_not_restore_post_cutoff_support_or_its_event(self):
        value = payload([item(content="大" * 20000), item("news-b", content="截止后才公开", published_at="2026-10-14")], [event(["news-a", "news-b"])])
        result, audit = run(value)
        self.assertEqual(result["blocks"][0]["prompt_data"]["items"][0]["content"], "大" * 20000)
        self.assertEqual(result["blocks"][0]["prompt_data"]["events"], [])
        self.assertNotIn("截止后才公开", result["blocks"][0]["prompt"])
        self.assertEqual(audit["blocks"][0]["excluded_post_cutoff_item_ids"], ["news-b"])

    def test_long_fixed_template_is_rendered_and_unknown_placeholder_fails(self):
        template = "固定规则" * 10000 + "{{企业名称}}{{资讯}}"
        result, _ = run(payload([item()]), template)
        self.assertTrue(result["blocks"][0]["prompt"].startswith("固定规则" * 10000))
        self.assertIn("原文说明事项。", result["blocks"][0]["prompt"])
        with self.assertRaises(p.InputError):
            run(payload(), "{{数据}}{{资讯}}")

    def test_one_shared_material_is_rendered_once_for_three_outputs(self):
        content = "唯一共享正文_20261015_DO_NOT_REPEAT"
        result, audit = run(payload([item(content=content)]))
        self.assertEqual(len(result["blocks"]), 1)
        block = result["blocks"][0]
        self.assertEqual(block["key"], "shared-analysis")
        self.assertEqual(block["output_blocks"], list(p.NEWS_BLOCK_KEYS))
        self.assertEqual(block["prompt"].count(content), 1)
        self.assertEqual(len(block["prompt_data"]["items"]), 1)
        self.assertEqual(len(audit["blocks"]), 1)

    def test_shared_template_rejects_repeated_context_placeholders(self):
        for repeated in ("{{企业名称}}", "{{资讯}}"):
            with self.subTest(repeated=repeated), self.assertRaises(p.InputError):
                run(payload([item()]), TEMPLATE + repeated)

    def test_cli_no_input_or_result_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="alert-prepare-test-") as directory:
            root = Path(directory)
            source = root / "input.json"
            original = json.dumps(payload([item()]), ensure_ascii=False)
            source.write_text(original, encoding="utf-8")
            prompts = root / "prompts"
            prompts.mkdir()
            (prompts / "shared-analysis.md").write_text(TEMPLATE, encoding="utf-8")
            argv = ["prepare", "--input", str(source), "--out", str(root / "out"), "--prompts-dir", str(prompts)]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(p.main(argv), 0)
                self.assertEqual(p.main(argv), 2)
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            result = json.loads((root / "out" / "prepared_inputs.json").read_text(encoding="utf-8"))
            self.assertEqual(result["entity"], {"name": "甲企业股份有限公司"})


class TimeRangeTests(unittest.TestCase):
    CLOCK = "2026-10-13T18:00:00+08:00"

    def assert_period(self, query, start, end, *, as_of=CLOCK, cutoff=None, defaulted=False):
        result = t.resolve_time_range(query, as_of)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["context"], {"start_date": start, "end_date": end,
                                          "data_as_of": cutoff or as_of})
        self.assertEqual(result["time_range"]["defaulted"], defaulted)
        self.assertEqual(result["time_range"]["timezone"], "Asia/Shanghai")
        for value in result["context"].values():
            self.assertIn(value, result["query_constraint"])
        return result

    def test_three_user_examples(self):
        self.assert_period("贵州茅台近半年的预警监测报告", "2026-04-13", "2026-10-13")
        self.assert_period("江淮汽车这周的预警监测分析", "2026-10-12", "2026-10-13")
        self.assert_period("江淮汽车预警监测", "2026-07-13", "2026-10-13", defaulted=True)

    def test_current_week_monday_and_previous_complete_week(self):
        self.assert_period("甲企业本周预警", "2026-10-12", "2026-10-12", as_of="2026-10-12")
        self.assert_period("甲企业上周预警", "2026-10-05", "2026-10-11", cutoff="2026-10-11")

    def test_rolling_week_and_thirty_days_are_not_calendar_month(self):
        self.assert_period("甲企业近一周预警", "2026-10-07", "2026-10-13")
        self.assert_period("甲企业近30天预警", "2026-09-14", "2026-10-13")
        self.assert_period("甲企业近一个月预警", "2026-09-13", "2026-10-13")

    def test_month_end_and_leap_year_calendar_arithmetic(self):
        self.assert_period("甲企业预警", "2023-12-31", "2024-03-31", as_of="2024-03-31", defaulted=True)
        self.assert_period("甲企业预警", "2024-12-31", "2025-03-31", as_of="2025-03-31", defaulted=True)
        self.assert_period("甲企业近一年预警", "2023-02-28", "2024-02-29", as_of="2024-02-29")

    def test_cross_year_and_full_previous_year(self):
        self.assert_period("甲企业近2个月预警", "2025-11-05", "2026-01-05", as_of="2026-01-05")
        self.assert_period("甲企业今年预警", "2026-01-01", "2026-01-05", as_of="2026-01-05")
        self.assert_period("甲企业去年预警", "2025-01-01", "2025-12-31", as_of="2026-01-05", cutoff="2025-12-31")

    def test_current_and_previous_natural_month(self):
        self.assert_period("甲企业本月预警", "2026-10-01", "2026-10-13")
        self.assert_period("甲企业上月预警", "2026-09-01", "2026-09-30", cutoff="2026-09-30")

    def test_explicit_historical_period_has_end_date_cutoff(self):
        result = self.assert_period("甲企业2025-01-01至2025-03-31预警", "2025-01-01", "2025-03-31", cutoff="2025-03-31")
        self.assertFalse(result["time_range"]["defaulted"])

    def test_conflicting_invalid_and_future_periods_have_no_context(self):
        for query in ("甲企业近半年及本月预警", "甲企业2026-02-30至2026-03-01预警",
                      "甲企业2026-10-13至2026-10-01预警", "甲企业2026-10-01至2026-12-31预警",
                      "甲企业近0天预警", "甲企业2026-01-01至2026-02-01和2026-03-01至2026-04-01预警"):
            result = t.resolve_time_range(query, self.CLOCK)
            self.assertEqual(result["status"], "clarification_required", query)
            self.assertNotIn("context", result)
            self.assertNotIn("query_constraint", result)

    def test_unsupported_explicit_period_never_falls_back_to_default(self):
        for query in ("甲企业上季度预警", "甲企业2025年第二季度预警", "甲企业过去几个月预警",
                      "甲企业截至2026-09-30预警", "甲企业近半个月预警", "甲企业去年9月预警",
                      "甲企业去年九月预警", "甲企业本月15日预警", "甲企业近5个交易日预警",
                      "甲企业近5个工作日预警", "甲企业这周三预警", "江淮汽车明天预警监测",
                      "江淮汽车后天预警监测", "江淮汽车下星期预警监测", "江淮汽车半年以来的预警监测",
                      "江淮汽车半年来的预警监测"):
            result = t.resolve_time_range(query, self.CLOCK)
            self.assertEqual(result["status"], "unsupported", query)
            self.assertNotIn("context", result)

    def test_broad_recent_defaults_but_explicit_period_takes_precedence(self):
        for query in ("甲企业近期预警", "甲企业最近预警", "甲企业这段时间预警"):
            result = self.assert_period(query, "2026-07-13", "2026-10-13", defaulted=True)
            self.assertIn("宽泛时间词", result["time_range"]["basis"])
        self.assert_period("甲企业近期近半年预警", "2026-04-13", "2026-10-13")
        self.assert_period("甲企业最近本月预警", "2026-10-01", "2026-10-13")
        self.assert_period("甲企业本年预警", "2026-01-01", "2026-10-13")

    def test_explicit_clock_timezone_conversion_and_missing_offset(self):
        self.assert_period("甲企业本周预警", "2026-10-12", "2026-10-13",
                           as_of="2026-10-12T17:00:00Z", cutoff="2026-10-13T01:00:00+08:00")
        for clock in ("", "2026-10-13T18:00:00", "2026-13-13"):
            with self.assertRaises(ValueError):
                t.resolve_time_range("甲企业预警", clock)

    def test_prepare_default_matches_resolver_and_explicit_period_is_preserved(self):
        value = payload()
        del value["context"]["start_date"]
        del value["context"]["end_date"]
        prepared, _ = run(value)
        resolved = t.resolve_time_range("甲企业预警", self.CLOCK)
        self.assertEqual({k: prepared["context"][k] for k in resolved["context"]}, resolved["context"])
        value["context"].update(start_date="2026-04-13", end_date="2026-10-13")
        prepared, _ = run(value)
        self.assertEqual(prepared["context"]["start_date"], "2026-04-13")
        self.assertEqual(prepared["context"]["end_date"], "2026-10-13")
        value["context"].update(start_date="2025-01-01", end_date="2025-03-31", data_as_of="2025-03-31")
        prepared, _ = run(value)
        self.assertEqual(prepared["context"]["start_date"], "2025-01-01")
        self.assertEqual(prepared["context"]["end_date"], "2025-03-31")

    def test_prepare_fallback_calendar_month_end(self):
        value = payload()
        value["context"] = {"data_as_of": "2024-03-31", "scope": "本地测试范围"}
        prepared, _ = run(value)
        self.assertEqual(prepared["context"]["start_date"], "2023-12-31")
        self.assertEqual(prepared["context"]["end_date"], "2024-03-31")

    def test_three_user_examples_produce_concise_news_queries(self):
        for user_query, subject, start in (("贵州茅台近半年的预警监测报告", "贵州茅台酒股份有限公司", "2026-04-13"),
                                           ("江淮汽车这周的预警监测分析", "安徽江淮汽车集团股份有限公司", "2026-10-12"),
                                           ("江淮汽车预警监测", "安徽江淮汽车集团股份有限公司", "2026-07-13")):
            resolution = t.resolve_time_range(user_query, self.CLOCK)
            self.assertEqual(t.build_news_query(subject, resolution),
                             f"请检索{subject}在{start}至2026-10-13期间公开的资讯、公司公告和重要新闻。")

    def test_supplement_query_names_only_the_specific_matter(self):
        resolution = t.resolve_time_range("江淮汽车预警监测", self.CLOCK)
        self.assertEqual(t.build_news_query("安徽江淮汽车集团股份有限公司", resolution, focus="重大诉讼进展"),
                         "请检索安徽江淮汽车集团股份有限公司在2026-07-13至2026-10-13期间公开的重大诉讼进展相关资讯、公司公告和重要新闻。")
        # The cutoff stays in context for post-retrieval filtering, not in the query.
        self.assertEqual(resolution["context"]["data_as_of"], self.CLOCK)
        del resolution["query_constraint"]
        self.assertIn("期间公开的资讯、公司公告和重要新闻。", t.build_news_query("甲企业全称", resolution))

    def test_news_query_rejects_unresolved_or_invalid_context(self):
        for resolution in (t.resolve_time_range("甲企业上季度预警", self.CLOCK),
                           t.resolve_time_range("甲企业近半年及本月预警", self.CLOCK)):
            with self.assertRaises(ValueError):
                t.build_news_query("甲企业全称", resolution)
        valid = t.resolve_time_range("甲企业预警", self.CLOCK)
        for updates in ({"start_date": "2026-10-14"}, {"end_date": "2026-07-01"},
                        {"start_date": "2026-02-30"}, {"start_date": "2026-9-13"},
                        {"end_date": "2026-10-14"}, {"data_as_of": "2026-10-01"},
                        {"data_as_of": "2026-10-13T18:00:00"}, {"data_as_of": None}):
            resolution = {**valid, "context": {**valid["context"], **updates}}
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                t.build_news_query("甲企业全称", resolution)
        for subject, focus in (("", None), (None, None), ("甲企业全称", ""), ("甲企业全称", 3)):
            with self.subTest(subject=subject, focus=focus), self.assertRaises(ValueError):
                t.build_news_query(subject, valid, focus=focus)

    def test_cli_resolved_and_unresolved_status(self):
        for query, expected_code, expected_status in (("甲企业预警", 0, "resolved"), ("甲企业上季度预警", 2, "unsupported")):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(t.main(["--query", query, "--as-of", self.CLOCK]), expected_code)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], expected_status)


if __name__ == "__main__":
    unittest.main(verbosity=2)
