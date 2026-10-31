#!/usr/bin/env python3
"""Offline checks for synthesizing key concerns from completed chapter prose."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

import prepare_inputs as p


CHAPTERS = ("monitoring-overview", "key-events", "related-environment", "risk-fermentation")
SLOTS = ("舆情概览内容", "重点事件内容", "关联主体内容", "风险发酵链路内容")
TEMPLATE = (
    "企业：{{企业名称}}\n"
    "概览：{{舆情概览内容}}\n"
    "事件：{{重点事件内容}}\n"
    "关联：{{关联主体内容}}\n"
    "发酵：{{风险发酵链路内容}}"
)


def payload(**changes):
    value = {
        "entity": {"name": "虚拟企业股份有限公司", "confirmed": True},
        "analysis_results": {
            "monitoring-overview": "**舆情总体平稳**，样本数量不足以判断全网趋势。[source:overview-A]",
            "key-events": "**项目已获批**，尚无资金到账证据。\n原文保留第二行。",
            "related-environment": "**子公司事项独立归属**，不能直接归为母公司负债。",
            "risk-fermentation": "**债务展期事件存在发酵条件**，触发依赖后续兑付节点。",
        },
    }
    value.update(changes)
    return value


def run(value, template=TEMPLATE):
    return p.prepare_key_concerns(value, template)


class KeyConcernsTests(unittest.TestCase):
    def test_all_three_completed_bodies_are_passed_in_report_order(self):
        value = payload()
        prepared, audit = run(value)
        self.assertEqual(len(prepared["blocks"]), 1)
        block = prepared["blocks"][0]
        self.assertEqual((block["key"], block["status"]), ("key-concerns", "ready"))
        data = block["prompt_data"]
        self.assertEqual(data["analysis_results"], value["analysis_results"])
        self.assertEqual(data["active_blocks"], list(CHAPTERS))
        self.assertEqual(data["empty_blocks"], [])
        self.assertEqual(data["prompt_inputs"], {
            "企业名称": value["entity"]["name"],
            **{slot: value["analysis_results"][key] for key, slot in zip(CHAPTERS, SLOTS)},
        })
        for body in value["analysis_results"].values():
            self.assertIn(body, block["prompt"])
        self.assertEqual(audit["kept_keys"], list(CHAPTERS))
        self.assertEqual(audit["prompt_length"], len(block["prompt"]))
        self.assertNotIn("items", data)
        self.assertNotIn("news_text", block)

    def test_raw_news_and_other_top_level_packages_are_rejected(self):
        for field, raw in (("items", []), ("events", []), ("raw", {}),
                           ("acquisition", "mx-finance-search"), ("context", {}),
                           ("blocks", []), ("generated_analysis", "已有分析")):
            with self.subTest(field=field):
                value = payload(**{field: raw})
                with self.assertRaises(p.InputError):
                    run(value)

    def test_analysis_inputs_must_be_exactly_the_three_preceding_chapters(self):
        for extra_key in ("key-concerns", "follow-up", "unknown-module"):
            with self.subTest(extra_key=extra_key):
                value = payload()
                value["analysis_results"][extra_key] = "不得循环作为总结入参。"
                with self.assertRaises(p.InputError):
                    run(value)
        value = payload()
        del value["analysis_results"][CHAPTERS[0]]
        with self.assertRaises(p.InputError):
            run(value)

    def test_non_text_results_cannot_smuggle_news_packages_or_containers(self):
        for non_text in (None, 123, True, ["正文"], {"items": []}):
            with self.subTest(value=non_text):
                value = payload()
                value["analysis_results"]["key-events"] = non_text
                with self.assertRaises(p.InputError):
                    run(value)
        for non_object in (None, [], "三章正文"):
            with self.subTest(analysis_results=non_object):
                with self.assertRaises(p.InputError):
                    run(payload(analysis_results=non_object))

    def test_confirmed_entity_is_required_and_metadata_cannot_be_injected(self):
        for entity in ({"name": "甲企业", "confirmed": False},
                       {"name": "甲企业"},
                       {"name": "甲企业", "confirmed": True, "news": "多余资讯"},
                       {"name": "甲企业", "confirmed": True, "org_code": "600418"}):
            with self.subTest(entity=entity):
                with self.assertRaises(p.InputError):
                    run(payload(entity=entity))
        value = payload(entity={"name": "甲企业", "confirmed": True, "org_code": "10000069733.FXR"})
        prepared, _ = run(value)
        self.assertEqual(prepared["entity"], value["entity"])
        self.assertNotIn("10000069733", prepared["blocks"][0]["prompt"])

    def test_empty_chapters_do_not_prevent_other_supported_chapters(self):
        value = payload()
        value["analysis_results"].update({"monitoring-overview": "  \n ", "related-environment": "暂无数据。"})
        value["analysis_results"]["risk-fermentation"] = "暂无数据"
        prepared, audit = run(value)
        block = prepared["blocks"][0]
        self.assertEqual(block["status"], "ready")
        self.assertEqual(block["prompt_data"]["active_blocks"], ["key-events"])
        self.assertEqual(block["prompt_data"]["empty_blocks"], ["monitoring-overview", "related-environment", "risk-fermentation"])
        self.assertEqual(block["prompt_data"]["analysis_results"]["related-environment"], "")
        self.assertEqual(audit["original_empty_keys"], ["monitoring-overview", "related-environment", "risk-fermentation"])
        self.assertEqual(audit["kept_keys"], ["key-events"])

    def test_all_empty_chapters_are_empty_without_fabricated_material(self):
        original = dict(zip(CHAPTERS, ("", " \n ", "暂无数据", "暂无数据。")))
        prepared, audit = run(payload(analysis_results=original))
        block = prepared["blocks"][0]
        self.assertEqual(block["status"], "empty")
        self.assertEqual(block["prompt_data"]["active_blocks"], [])
        self.assertEqual(block["prompt_data"]["analysis_results"], dict.fromkeys(CHAPTERS, ""))
        self.assertEqual(audit["kept_keys"], [])
        self.assertEqual(audit["original_empty_keys"], list(CHAPTERS))

    def test_completed_body_citations_order_whitespace_and_uncertainty_are_unchanged(self):
        body = (
            "  **尚待核验**：先保留较低来源判断，再说明权威公告。[source:late-B]\n\n"
            "不得据此确认母公司承担责任。[source:early-A] "
            "https://example.invalid/original?x=1&y=2\n"
        )
        value = payload()
        value["analysis_results"]["key-events"] = body
        before = copy.deepcopy(value)
        prepared, _ = run(value)
        block = prepared["blocks"][0]
        self.assertEqual(block["prompt_data"]["analysis_results"]["key-events"], body)
        self.assertIn(body, block["prompt"])
        self.assertEqual(value, before)

    def test_placeholder_text_inside_inserted_bodies_and_company_is_literal(self):
        value = payload(entity={"name": "甲{{关联主体内容}}企业", "confirmed": True})
        value["analysis_results"]["monitoring-overview"] = "原文中的 {{企业名称}}、{{重点事件内容}} 和 {{资讯}} 应保留。"
        prepared, _ = run(value)
        prompt = prepared["blocks"][0]["prompt"]
        self.assertIn(value["entity"]["name"], prompt)
        self.assertIn(value["analysis_results"]["monitoring-overview"], prompt)
        self.assertEqual(prompt.count(value["analysis_results"]["key-events"]), 1)

    def test_template_has_only_the_company_and_three_completed_prose_slots(self):
        for template in (TEMPLATE + "{{资讯}}", TEMPLATE + "{{未知占位}}",
                         TEMPLATE.replace("{{关联主体内容}}", ""), "{{企业名称}}{{资讯}}"):
            with self.subTest(template=template):
                with self.assertRaises(p.InputError):
                    run(payload(), template)
        prepared, _ = run(payload(), TEMPLATE + "\n重复观点：{{舆情概览内容}}")
        body = payload()["analysis_results"]["monitoring-overview"]
        self.assertEqual(prepared["blocks"][0]["prompt"].count(body), 2)

    def test_long_completed_body_and_its_citations_are_preserved_completely(self):
        value = payload(analysis_results=dict.fromkeys(CHAPTERS, ""))
        body = "章节开头。[source:start]\n" + "文" * 50000 + "\n章节结尾。[source:end]"
        value["analysis_results"][CHAPTERS[0]] = body
        prepared, audit = run(value)
        block = prepared["blocks"][0]
        self.assertEqual(block["prompt_data"]["analysis_results"][CHAPTERS[0]], body)
        self.assertIn(body, block["prompt"])
        self.assertEqual(audit["kept_keys"], [CHAPTERS[0]])
        self.assertEqual(audit["input_lengths"][CHAPTERS[0]], len(body))

    def test_long_middle_chapter_keeps_all_three_completed_chapters(self):
        value = payload()
        value["analysis_results"].update({
            CHAPTERS[0]: "完整首章。[source:one]",
            CHAPTERS[1]: "完整第二章。[source:two]" * 2000,
            CHAPTERS[2]: "很小的第三章。",
        })
        before = copy.deepcopy(value)
        prepared, audit = run(value)
        block = prepared["blocks"][0]
        self.assertEqual(block["prompt_data"]["active_blocks"], list(CHAPTERS))
        self.assertEqual(block["prompt_data"]["analysis_results"], value["analysis_results"])
        self.assertEqual(audit["kept_keys"], list(CHAPTERS))
        for body in value["analysis_results"].values():
            self.assertIn(body, block["prompt"])
        self.assertEqual(value, before)

    def test_long_first_chapter_keeps_shorter_later_chapters(self):
        value = payload()
        value["analysis_results"][CHAPTERS[0]] = "大" * 50000
        prepared, audit = run(value)
        block = prepared["blocks"][0]
        self.assertEqual(block["status"], "ready")
        self.assertEqual(audit["kept_keys"], list(CHAPTERS))
        self.assertEqual(block["prompt_data"]["analysis_results"], value["analysis_results"])
        for body in value["analysis_results"].values():
            self.assertIn(body, block["prompt"])

    def test_audit_report_order_is_stable_when_template_slot_order_differs(self):
        reversed_template = "{{关联主体内容}}{{重点事件内容}}{{舆情概览内容}}{{风险发酵链路内容}}{{企业名称}}"
        value = payload()
        value["analysis_results"][CHAPTERS[1]] = "大" * 50000
        prepared, audit = run(value, reversed_template)
        block = prepared["blocks"][0]
        self.assertEqual(block["prompt_data"]["active_blocks"], list(CHAPTERS))
        self.assertEqual(audit["kept_keys"], list(CHAPTERS))
        expected = "".join(value["analysis_results"][key] for key in ("related-environment", "key-events", "monitoring-overview", "risk-fermentation")) + value["entity"]["name"]
        self.assertEqual(block["prompt"], expected)

    def test_long_fixed_template_keeps_all_completed_bodies(self):
        prefix = "固" * 50000
        value = payload()
        prepared, audit = run(value, prefix + TEMPLATE)
        block = prepared["blocks"][0]
        self.assertTrue(block["prompt"].startswith(prefix))
        self.assertEqual(block["prompt_data"]["analysis_results"], value["analysis_results"])
        self.assertEqual(audit["prompt_length"], len(block["prompt"]))

    def test_cli_writes_prepared_pair_and_protects_inputs_and_existing_results(self):
        with tempfile.TemporaryDirectory(prefix="alert-concerns-test-") as directory:
            root = Path(directory)
            source = root / "input.json"
            original = json.dumps(payload(), ensure_ascii=False, indent=2)
            source.write_text(original, encoding="utf-8")
            prompts = root / "prompts"
            prompts.mkdir()
            (prompts / "key-concerns.md").write_text(TEMPLATE, encoding="utf-8")
            output = root / "output"
            argv = ["prepare-concerns", "--input", str(source), "--out", str(output), "--prompts-dir", str(prompts)]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(p.main(argv), 0)
            generated = {path.name: path.read_bytes() for path in output.iterdir()}
            self.assertEqual(set(generated), {"prepared_inputs.json", "audit.json"})
            self.assertEqual(json.loads(generated["prepared_inputs.json"])["blocks"][0]["key"], "key-concerns")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(p.main(argv), 2)
            self.assertEqual(generated, {path.name: path.read_bytes() for path in output.iterdir()})
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            protected = root / "prepared_inputs.json"
            protected.write_text(original, encoding="utf-8")
            argv[2] = str(protected)
            argv[4] = str(root)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(p.main(argv), 2)
            self.assertEqual(protected.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
