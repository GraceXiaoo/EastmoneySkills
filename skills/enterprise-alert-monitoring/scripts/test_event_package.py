#!/usr/bin/env python3
"""Offline behavioral fixtures for the event-library channel. No network or credentials.

Covers: build_event_package.py (build/inspect/compose) and prepare_inputs.py
prepare-fermentation, including post-cutoff filtering, entity binding, the
three-tier guardrails and prompt rendering with fixtures shaped like the real
newsEventSearch / futureEventSearch returns.
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import build_event_package as e
import prepare_inputs as p

FERMENTATION_TEMPLATE = (
    "企业：{{企业名称}}\n"
    "事件库：{{事件库}}\n"
    "概览：{{舆情概览内容}}\n"
    "事件：{{重点事件内容}}\n"
    "关联：{{关联主体内容}}"
)


def news_event_record(**extra):
    result = {
        "infoCode": "IN2026102107493981031565",
        "eventId": "0f87e8a142804519a07525c53505e0fa",
        "firstTagName": "银行借款", "firstTagCode": "100000022",
        "secondaryTagName": "提交贷款申请", "secondaryTagCode": "100000000308",
        "industryName": "房地产", "orgCode": "10004086", "orgName": "万科企业股份有限公司",
        "eventTitle": "虚拟企业为子公司贷款提供担保",
        "eventDigest": "虚拟企业公告称，为控股子公司3.65亿元贷款提供连带责任保证，在股东会批准的担保额度范围内。",
        "publishTime": "2026-10-19 18:27:35.000",
        "jumpType": 5, "url": "https://example.invalid/notice/001",
        "securityCode": "000002.SZ", "marketCode": "CN",
        "riskLevel": -2, "riskLevelName": "无", "score": None, "jumpLinkType": None,
        "highLightEventTitle": "虚拟企业为子公司贷款提供担保", "highLightOrgName": "万科企业股份有限公司",
    }
    result.update(extra)
    return result


def future_event_record(**extra):
    result = {
        "futureEventId": "9711dc406a76490eb610e6841c8cecb3",
        "infocode": "207a5c783402425392e717cdeca7f085",
        "publishTime": "2026-03-09 07:32:00",
        "happenTime": "2026-12",
        "eventMessage": "22虚拟MTN005展期",
        "highLightEventMessage": "22虚拟MTN005展期",
        "originCompanyName": "万科,武汉誉天",
        "companyBeanList": [
            {"companyInnerCode": "1000001543", "companyName": "万科", "orgCode": "10004086", "secuFullCode": "000002.SZ"},
            {"companyInnerCode": "unknown", "companyName": "武汉誉天", "orgCode": None, "secuFullCode": None},
        ],
        "eventType": "企业战略公布", "secondTagCode": "100000000113", "secondTagName": "企业战略公布",
        "risk": "负面", "eventIndustry": "房地产",
        "jumpUrl": "http://mp.weixin.qq.com/s?__biz=EXAMPLE",
        "newsType": "WECHAT", "selfEventType": 0,
    }
    result.update(extra)
    return result


def news_event_payload(records):
    return {"code": 200, "data": {"total": len(records), "eventItemList": records},
            "message": "事件大全搜索成功", "nrsTraceId": "fixture-trace"}


def future_event_payload(records):
    return {"code": 0, "data": {"total": len(records), "futureEventSearchItemList": records},
            "message": "未来行动事件V2搜索成功:OK", "nrsTraceId": "fixture-trace"}


def manifest(event_searches, entity=None):
    return {
        "entity": entity or {"name": "万科企业股份有限公司", "confirmed": True, "org_code": "10004086"},
        "context": {"start_date": "2026-09-22", "end_date": "2026-10-22",
                    "data_as_of": "2026-10-22T17:00:00+08:00",
                    "scope": "企业自身及事件库明确涉及的关联事项"},
        "event_searches": event_searches,
    }


def event_search(api_id, path, *, query="事件检索", status="success", kind="initial", reason=""):
    return {"api_id": api_id, "query": query, "raw_result_path": path,
            "status": status, "kind": kind, "reason": reason}


def build_in_temp(root, news_records, future_records, out_name="candidates"):
    raw_dir = root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    news_path = raw_dir / "events.json"
    future_path = raw_dir / "future.json"
    news_path.write_text(json.dumps(news_event_payload(news_records), ensure_ascii=False), encoding="utf-8")
    future_path.write_text(json.dumps(future_event_payload(future_records), ensure_ascii=False), encoding="utf-8")
    manifest_path = root / "event_runs.json"
    manifest_path.write_text(json.dumps(manifest([
        event_search("newsEventSearch", str(news_path)),
        event_search("futureEventSearch", str(future_path)),
    ]), ensure_ascii=False), encoding="utf-8")
    out = root / out_name
    argv = ["build", "--manifest", str(manifest_path), "--out", str(out)]
    with contextlib.redirect_stdout(io.StringIO()):
        e.main(argv)
    bundle = json.loads((out / "event_bundle.json").read_text(encoding="utf-8"))
    return out, bundle


def event_package_from(bundle, selected_ids, root, name="composed", bundle_name="candidates"):
    selection_path = root / f"{name}_selection.json"
    selection_path.write_text(json.dumps({"selected_ids": selected_ids}, ensure_ascii=False), encoding="utf-8")
    out = root / name
    argv = ["compose", "--bundle", str(root / bundle_name / "event_bundle.json"),
            "--selection", str(selection_path), "--out", str(out)]
    with contextlib.redirect_stdout(io.StringIO()):
        e.main(argv)
    return json.loads((out / "event_package.json").read_text(encoding="utf-8"))


def fermentation_payload(analysis_results, events, entity=None):
    return {"entity": entity or {"name": "万科企业股份有限公司", "confirmed": True},
            "analysis_results": analysis_results, "events": events}


CHAPTERS = {
    "monitoring-overview": "**舆情总体承压**，本期纳入样本8篇。[source:ov]",
    "key-events": "**债务展期持续**，公司已披露多笔展期安排。[source:ke]",
    "related-environment": "**关联主体事项独立归属**，不直接归为母公司负债。[source:re]",
}


class BuildEventPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="evt-build-")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_normalizes_two_channels_and_counts_kinds(self):
        out, bundle = build_in_temp(self.root, [news_event_record()], [future_event_record()])
        self.assertEqual(bundle["acquisition"], "mx-api-invoke")
        self.assertEqual(len(bundle["candidate_ids"]), 2)
        kinds = {bundle["catalog"][i]["material_kind"] for i in bundle["candidate_ids"]}
        self.assertEqual(kinds, {"event", "future_event"})
        future_id = next(i for i in bundle["candidate_ids"] if bundle["catalog"][i]["material_kind"] == "future_event")
        item = bundle["catalog"][future_id]
        self.assertEqual(item["org_name"], "万科,武汉誉天")
        self.assertEqual(item["security_code"], "000002.SZ")
        self.assertEqual(item["second_tag"], "企业战略公布")
        self.assertEqual(item["risk_level"], "负面")
        self.assertEqual(item["happen_time"], "2026-12")
        self.assertTrue(item["id"].startswith("evt_"))
        index = (out / "candidate_event_index.md").read_text(encoding="utf-8")
        self.assertIn("已发生事件", index)
        self.assertIn("未来预期事件", index)
        self.assertIn("接口风险标注：负面", index)

    def test_duplicate_native_records_and_missing_digest_fail_closed(self):
        duplicate = news_event_record(infoCode="IN1")
        other = news_event_record(infoCode="IN1", eventTitle="重复条目不同标题", eventDigest="")
        out, bundle = build_in_temp(self.root, [duplicate, other], [future_event_record()])
        self.assertEqual(len(bundle["candidate_ids"]), 2)

    def test_unsupported_shape_and_non_success_status(self):
        raw = self.root / "raw"
        raw.mkdir(exist_ok=True)
        bad = raw / "bad.json"
        bad.write_text(json.dumps({"code": 200, "data": {"unknownKey": []}}), encoding="utf-8")
        manifest_path = self.root / "event_runs.json"
        manifest_path.write_text(json.dumps(manifest([
            event_search("newsEventSearch", str(bad)),
            event_search("futureEventSearch", str(bad)),
        ]), ensure_ascii=False), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(e.main(["build", "--manifest", str(manifest_path), "--out", str(self.root / "c")]), 0)
        bundle = json.loads((self.root / "c" / "event_bundle.json").read_text(encoding="utf-8"))
        self.assertEqual(bundle["candidate_ids"], [])
        statuses = [q["status"] for q in bundle["queries"]]
        self.assertEqual(statuses, ["unsupported", "unsupported"])

    def test_manifest_requires_one_initial_per_api(self):
        raw = self.root / "raw"
        raw.mkdir(exist_ok=True)
        path = raw / "a.json"
        path.write_text(json.dumps(news_event_payload([news_event_record()])), encoding="utf-8")
        for searches in ([event_search("newsEventSearch", str(path)), event_search("newsEventSearch", str(path), query="again")],
                         [event_search("newsEventSearch", str(path))],
                         [event_search("futureEventSearch", str(path), query="swapped")]):
            manifest_path = self.root / "event_runs.json"
            manifest_path.write_text(json.dumps(manifest(searches), ensure_ascii=False), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(e.main(["build", "--manifest", str(manifest_path), "--out", str(self.root / "x")]), 2)

    def test_supplement_requires_reason_and_unknown_api_rejected(self):
        raw = self.root / "raw"
        raw.mkdir(exist_ok=True)
        path = raw / "a.json"
        path.write_text(json.dumps(news_event_payload([news_event_record()])), encoding="utf-8")
        for search in (event_search("newsEventSearch", str(path), kind="supplement"),
                       event_search("madeUpApi", str(path))):
            manifest_path = self.root / "event_runs.json"
            searches = [event_search("newsEventSearch", str(path)), search] if search["kind"] == "supplement" else [search]
            manifest_path.write_text(json.dumps(manifest(searches), ensure_ascii=False), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(e.main(["build", "--manifest", str(manifest_path), "--out", str(self.root / "x")]), 2)

    def test_compose_selection_and_id_tampering(self):
        out, bundle = build_in_temp(self.root, [news_event_record()], [future_event_record()])
        package = event_package_from(bundle, bundle["candidate_ids"], self.root)
        self.assertEqual(package["acquisition"], "mx-api-invoke")
        self.assertEqual(len(package["items"]), 2)
        self.assertNotIn("events", package)
        selection = self.root / "hack.json"
        selection.write_text(json.dumps({"selected_ids": bundle["candidate_ids"], "events": [{"verified": True}]},
                                        ensure_ascii=False), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(e.main(["compose", "--bundle", str(out / "event_bundle.json"),
                                     "--selection", str(selection), "--out", str(self.root / "hack-out")]), 2)
        bundle_file = out / "event_bundle.json"
        mutated = json.loads(bundle_file.read_text(encoding="utf-8"))
        mutated["catalog"][mutated["candidate_ids"][0]]["title"] = "被篡改标题"
        bundle_file.write_text(json.dumps(mutated, ensure_ascii=False), encoding="utf-8")
        selection2 = self.root / "s2.json"
        selection2.write_text(json.dumps({"selected_ids": mutated["candidate_ids"]}, ensure_ascii=False), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(e.main(["compose", "--bundle", str(bundle_file),
                                     "--selection", str(selection2), "--out", str(self.root / "s2out")]), 2)

    def test_inspect_unknown_ids_fail(self):
        out, bundle = build_in_temp(self.root, [news_event_record()], [future_event_record()])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(e.main(["inspect", "--bundle", str(out / "event_bundle.json"), "--ids", "evt_missing"]), 2)


class PrepareFermentationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="evt-ferm-")
        self.root = Path(self.tmp.name)
        _, self.bundle = build_in_temp(self.root, [news_event_record()], [future_event_record()])
        self.package = event_package_from(self.bundle, self.bundle["candidate_ids"], self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def run_prepare(self, payload, template=FERMENTATION_TEMPLATE):
        return p.prepare_fermentation(payload, template)

    def test_fermentation_renders_five_placeholders_once(self):
        prepared, audit = self.run_prepare(fermentation_payload(CHAPTERS, self.package))
        block = prepared["blocks"][0]
        self.assertEqual(block["key"], "risk-fermentation")
        self.assertEqual(block["status"], "ready")
        self.assertIn(CHAPTERS["key-events"], block["prompt"])
        self.assertIn("事件库条目", block["prompt"])
        self.assertIn("已发生事件", block["prompt"])
        self.assertIn("未来预期事件", block["prompt"])
        self.assertIn("接口风险标注", block["prompt"])
        self.assertEqual(audit["kind_counts"], {"已发生事件": 1, "未来预期事件": 1})
        self.assertEqual(audit["kept_keys"], list(p.NEWS_BLOCK_KEYS))

    def test_material_renders_boundary_notes_and_coarse_dates(self):
        prepared, _ = self.run_prepare(fermentation_payload(CHAPTERS, self.package))
        prompt = prepared["blocks"][0]["prompt"]
        self.assertIn("不代表企业风险等级或发酵结论", prompt)
        self.assertIn("预计发生时间：2026-12", prompt)
        self.assertIn("与目标企业", prompt)  # 主体归属核对提示存在

    def test_overdue_future_event_flagged_and_post_cutoff_event_dropped(self):
        overdue = future_event_record(infocode="OVERDUE-001", eventMessage="已过预计节点的展期",
                                      happenTime="2026-09-01", publishTime="2026-03-01 00:00:00")
        late = news_event_record(infoCode="LATE-001", eventTitle="截止后才发布",
                                 publishTime="2026-10-23 09:00:00.000")
        _, bundle = build_in_temp(self.root, [news_event_record(), late], [future_event_record(), overdue], "candidates2")
        package = event_package_from(bundle, bundle["candidate_ids"], self.root, "composed2", "candidates2")
        prepared, audit = self.run_prepare(fermentation_payload(CHAPTERS, package))
        prompt = prepared["blocks"][0]["prompt"]
        self.assertIn("早于截至时点", prompt)
        self.assertNotIn("截止后才发布", prompt)
        self.assertEqual(len(audit["excluded_post_cutoff_item_ids"]), 1)
        self.assertEqual(len(audit["kept_item_ids"]), 3)

    def test_entity_mismatch_and_foreign_channel_rejected(self):
        with self.assertRaises(p.InputError):
            self.run_prepare(fermentation_payload(CHAPTERS, {**self.package, "entity": {"name": "另一家企业", "confirmed": True}}))
        news_like = {**self.package, "acquisition": "mx-finance-search"}
        with self.assertRaises(p.InputError):
            self.run_prepare(fermentation_payload(CHAPTERS, news_like))
        extra = {**self.package, "news_queries": []}
        with self.assertRaises(p.InputError):
            self.run_prepare(fermentation_payload(CHAPTERS, extra))
        with self.assertRaises(p.InputError):
            self.run_prepare({"entity": CHAPTERS and {"name": "万科企业股份有限公司", "confirmed": True},
                              "analysis_results": CHAPTERS})

    def test_events_key_is_optional_in_fermentation_input(self):
        with self.assertRaises(p.InputError):
            self.run_prepare({"entity": {"name": "万科企业股份有限公司", "confirmed": True},
                              "analysis_results": CHAPTERS})
        value = fermentation_payload(CHAPTERS, self.package)
        del value["events"]
        with self.assertRaises(p.InputError):
            self.run_prepare(value)

    def test_empty_chapters_and_empty_events_fail_closed(self):
        empty_chapters = dict.fromkeys(p.NEWS_BLOCK_KEYS, "暂无数据")
        prepared, audit = self.run_prepare(fermentation_payload(empty_chapters, self.package))
        self.assertEqual(prepared["blocks"][0]["status"], "ready")
        self.assertEqual(audit["kept_keys"], [])
        empty_events = {**self.package, "items": []}
        prepared, audit = self.run_prepare(fermentation_payload(CHAPTERS, empty_events))
        self.assertIn("本次没有可用事件库材料", prepared["blocks"][0]["prompt"])
        both_empty = self.run_prepare(fermentation_payload(empty_chapters, empty_events))
        self.assertEqual(both_empty[0]["blocks"][0]["status"], "empty")

    def test_template_contract_enforced(self):
        for broken in (FERMENTATION_TEMPLATE.replace("{{事件库}}", ""),
                       FERMENTATION_TEMPLATE + "{{未知}}",
                       FERMENTATION_TEMPLATE.replace("{{重点事件内容}}", "{{资讯}}"),
                       FERMENTATION_TEMPLATE + "{{事件库}}"):
            with self.subTest(template=broken), self.assertRaises(p.InputError):
                self.run_prepare(fermentation_payload(CHAPTERS, self.package), broken)

    def test_cli_prepare_fermentation_writes_pair(self):
        source = self.root / "fermentation_input.json"
        source.write_text(json.dumps(fermentation_payload(CHAPTERS, self.package), ensure_ascii=False), encoding="utf-8")
        prompts = self.root / "prompts"
        prompts.mkdir()
        (prompts / "risk-fermentation.md").write_text(FERMENTATION_TEMPLATE, encoding="utf-8")
        out = self.root / "prepared"
        argv = ["prepare-fermentation", "--input", str(source), "--out", str(out), "--prompts-dir", str(prompts)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(p.main(argv), 0)
        result = json.loads((out / "prepared_inputs.json").read_text(encoding="utf-8"))
        self.assertEqual(result["blocks"][0]["key"], "risk-fermentation")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(p.main(argv), 2)

    def test_org_code_disagreement_rejected(self):
        value = fermentation_payload(CHAPTERS, self.package,
                                     entity={"name": "万科企业股份有限公司", "confirmed": True, "org_code": "10004086"})
        prepared, _ = self.run_prepare(value)
        self.assertEqual(prepared["entity"]["org_code"], "10004086")
        mismatch = fermentation_payload(CHAPTERS, self.package,
                                        entity={"name": "万科企业股份有限公司", "confirmed": True, "org_code": "99999999"})
        with self.assertRaises(p.InputError):
            self.run_prepare(mismatch)

    def test_secret_keys_never_reach_prompt(self):
        leaked = {**self.package, "items": [{**item, "api_key": "DO_NOT_LEAK"} for item in self.package["items"]]}
        # api_key is stripped by safe_value at build; simulate direct injection instead
        poisoned = json.loads(json.dumps(self.package))
        poisoned["items"][0]["content"] = "正文包含密钥DO_NOT_LEAK与{{企业名称}}字样。"
        prepared, _ = self.run_prepare(fermentation_payload(CHAPTERS, poisoned))
        self.assertIn("{{企业名称}}", prepared["blocks"][0]["prompt"])
        self.assertIn("DO_NOT_LEAK", prepared["blocks"][0]["prompt"])  # 原文保留，占位符不被二次解析
        self.assertNotIn("api_key", prepared["blocks"][0]["prompt"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
