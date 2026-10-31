"""Tests for entity, period, coverage and information adaptation."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
MODULE_PATH = PACKAGE / "scripts" / "adapt_target_framework.py"
MODULE_SPEC = importlib.util.spec_from_file_location("adapt_target_framework", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Cannot load {MODULE_PATH}")
ADAPTER = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(ADAPTER)
adapt_framework = ADAPTER.adapt_framework
load_confirmed_framework = ADAPTER.load_confirmed_framework
sha256_file = ADAPTER.sha256_file
write_outputs = ADAPTER.write_outputs


def framework() -> dict:
    return json.loads(
        (
            PACKAGE
            / "examples"
            / "stage-b-sample"
            / "metric_framework.json"
        ).read_text(encoding="utf-8")
    )


def request() -> dict:
    return {
        "source_entities": [
            {
                "entity_id": "A",
                "name": "原公司",
                "code": "000001.SZ",
                "role": "PRIMARY",
            },
            {
                "entity_id": "CMP1",
                "name": "可比公司",
                "code": "000002.SZ",
                "role": "COMPARABLE",
            },
            {
                "entity_id": "IND1",
                "name": "行业板块",
                "role": "INDUSTRY_OR_SECTOR",
            },
        ],
        "target_entity": {
            "entity_id": "B",
            "name": "目标公司",
            "code": "600000.SH",
        },
        "target_actual_anchor": "2026A",
        "data_cutoff": "2027-09-30",
        "explicit_period_mappings": {
            "2026-09-30": "2027-09-30"
        },
        "information_items": [
            {
                "title": "目标公司发布新品",
                "source_organization": "公司公告",
                "published_at": "2027-09-01",
                "url": "https://example.com/news/1#top",
                "summary": "新品已发布。",
                "report_location": "行业与公司动态",
                "source_id": "source-1",
            },
            {
                "title": " 目标公司发布新品 ",
                "source_organization": "公司公告",
                "published_at": "2027-09-01",
                "url": "https://EXAMPLE.com/news/1/",
                "summary": "新品已发布。",
                "report_location": "行业与公司动态",
                "source_id": "source-1",
            },
        ],
    }


def create_stage1_handoff(root: Path, framework_path: Path, status: str = "CONFIRMED") -> Path:
    path = root / "stage-1-handoff.json"
    payload = {
        "schema_version": 1,
        "task_id": "stage-c-test",
        "stage": 1,
        "status": status,
        "producer": {
            "skill": "sellside-research-refresh-with-excel20",
            "version": "2.0.0",
            "mode": "完整框架提取",
        },
        "inputs": [],
        "outputs": [
            {
                "path": str(framework_path.resolve()),
                "sha256": sha256_file(framework_path),
                "size_bytes": framework_path.stat().st_size,
                "media_type": "application/json",
            }
        ],
        "validation": [{"name": "metric framework completeness", "status": "PASS"}],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class TargetAdaptationTests(unittest.TestCase):
    def test_replaces_only_primary_and_preserves_context_entities(self) -> None:
        result = adapt_framework(framework(), request())
        self.assertEqual(result["status"], "PASS")
        mappings = {
            item["source_entity_id"]: item for item in result["entity_mapping"]["mappings"]
        }
        self.assertEqual(mappings["A"]["action"], "REPLACE")
        self.assertEqual(mappings["A"]["target_entity_id"], "B")
        self.assertEqual(mappings["CMP1"]["action"], "PRESERVE")
        self.assertEqual(mappings["IND1"]["action"], "PRESERVE")

    def test_preserves_period_semantics_and_maps_every_period(self) -> None:
        result = adapt_framework(framework(), request())
        mapping = {
            item["source_period"]: item["target_period"]
            for item in result["period_mapping"]["mappings"]
        }
        self.assertEqual(mapping["2025A"], "2026A")
        self.assertEqual(mapping["2026F"], "2027F")
        self.assertEqual(mapping["2026-09-30"], "2027-09-30")
        self.assertEqual(result["period_mapping"]["unresolved"], [])
        self.assertTrue(
            all(
                all(period for period in item["target_periods"])
                for item in result["coverage_requirements"]
                if item["source_periods"]
            )
        )

    def test_generates_coverage_and_object_mapping_without_source_values(self) -> None:
        source = framework()
        result = adapt_framework(source, request())
        self.assertEqual(
            len(result["coverage_requirements"]),
            len(source["metrics"]),
        )
        self.assertEqual(
            len(result["target_table_mapping"]),
            len(source["objects"]),
        )
        serialized = json.dumps(result["coverage_requirements"], ensure_ascii=False)
        self.assertNotIn('"source_values"', serialized)
        self.assertIn("planned_mql", serialized)
        self.assertIn("not_applicable", serialized)

    def test_deduplicates_information_with_normalized_title_and_url(self) -> None:
        result = adapt_framework(framework(), request())
        self.assertEqual(len(result["information_rows"]), 1)
        self.assertEqual(
            result["information_rows"][0]["url"],
            "https://example.com/news/1",
        )

    def test_blocks_ambiguous_primary_entity(self) -> None:
        value = request()
        value["source_entities"].append(
            {"entity_id": "A2", "name": "第二主标的", "role": "PRIMARY"}
        )
        result = adapt_framework(framework(), value)
        self.assertEqual(result["status"], "BLOCKED")
        codes = {item["code"] for item in result["blockers"]}
        self.assertIn("PRIMARY_ENTITY_AMBIGUOUS", codes)

    def test_blocks_subsidiary_without_explicit_action(self) -> None:
        value = request()
        value["source_entities"].append(
            {
                "entity_id": "SUB1",
                "name": "原公司子公司",
                "role": "SUBSIDIARY_OR_BUSINESS",
            }
        )
        result = adapt_framework(framework(), value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(
            "ENTITY_REVIEW_REQUIRED",
            {item["code"] for item in result["blockers"]},
        )

    def test_blocks_nonannual_period_without_explicit_mapping(self) -> None:
        value = request()
        value["explicit_period_mappings"] = {}
        result = adapt_framework(framework(), value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("2026-09-30", result["period_mapping"]["unresolved"])
        self.assertIn(
            "PERIOD_MAPPING_REQUIRED",
            {item["code"] for item in result["blockers"]},
        )

    def test_blocks_conflicting_duplicate_information(self) -> None:
        value = request()
        value["information_items"][1]["summary"] = "冲突摘要"
        result = adapt_framework(framework(), value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(
            "INFORMATION_DEDUP_CONFLICT",
            {item["code"] for item in result["blockers"]},
        )

    def test_blocks_information_after_cutoff(self) -> None:
        value = request()
        value["information_items"][0]["published_at"] = "2027-10-01"
        value["information_items"] = value["information_items"][:1]
        result = adapt_framework(framework(), value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(
            "INFORMATION_AFTER_CUTOFF",
            {item["code"] for item in result["blockers"]},
        )

    def test_requires_confirmed_stage_one_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            framework_path = root / "metric_framework.json"
            framework_path.write_text(
                json.dumps(framework(), ensure_ascii=False),
                encoding="utf-8",
            )
            handoff_path = create_stage1_handoff(
                root, framework_path, "PASS_WAITING_CONFIRMATION"
            )
            with self.assertRaisesRegex(ValueError, "must be CONFIRMED"):
                load_confirmed_framework(handoff_path)

    def test_rejects_changed_framework_from_stage_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            framework_path = root / "metric_framework.json"
            framework_path.write_text(
                json.dumps(framework(), ensure_ascii=False),
                encoding="utf-8",
            )
            handoff_path = create_stage1_handoff(root, framework_path)
            framework_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "(size|hash) mismatch"):
                load_confirmed_framework(handoff_path)

    def test_writes_stage_two_handoff_and_all_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            framework_path = root / "metric_framework.json"
            request_path = root / "adaptation_request.json"
            framework_path.write_text(
                json.dumps(framework(), ensure_ascii=False),
                encoding="utf-8",
            )
            request_path.write_text(
                json.dumps(request(), ensure_ascii=False),
                encoding="utf-8",
            )
            stage1_handoff_path = create_stage1_handoff(root, framework_path)
            output_dir = root / "out"
            handoff = write_outputs(
                adapt_framework(framework(), request()),
                stage1_handoff_path,
                framework_path,
                request_path,
                output_dir,
            )
            self.assertEqual(handoff["status"], "CONFIRMED")
            for name in (
                "entity_mapping.json",
                "period_mapping.json",
                "coverage_requirements.json",
                "target_table_mapping.json",
                "information_rows.json",
                "stage-2-handoff.json",
            ):
                self.assertTrue((output_dir / name).is_file())

    def test_blocked_adaptation_writes_blocked_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            framework_path = root / "metric_framework.json"
            framework_path.write_text(
                json.dumps(framework(), ensure_ascii=False),
                encoding="utf-8",
            )
            stage1_handoff_path = create_stage1_handoff(root, framework_path)
            blocked_request = request()
            blocked_request["explicit_period_mappings"] = {}
            request_path = root / "adaptation_request.json"
            request_path.write_text(
                json.dumps(blocked_request, ensure_ascii=False),
                encoding="utf-8",
            )
            output_dir = root / "out"
            handoff = write_outputs(
                adapt_framework(framework(), blocked_request),
                stage1_handoff_path,
                framework_path,
                request_path,
                output_dir,
            )
            self.assertEqual(handoff["status"], "BLOCKED")
            self.assertEqual(handoff["validation"][0]["status"], "FAIL")
            self.assertEqual(handoff["error"]["category"], "ADAPTATION_BLOCKED")

    def test_schema_freezes_actions_and_dispositions(self) -> None:
        schema = json.loads(
            (PACKAGE / "reference" / "target_adaptation.schema.json").read_text(
                encoding="utf-8"
            )
        )
        disposition = schema["properties"]["coverage_requirements"]["items"]["properties"][
            "disposition"
        ]["enum"]
        action = schema["properties"]["target_table_mapping"]["items"]["properties"][
            "action"
        ]["enum"]
        self.assertEqual(disposition, ["planned_mql", "not_applicable"])
        self.assertEqual(action, ["adapt", "preserve", "omit_with_reason"])


if __name__ == "__main__":
    unittest.main()
