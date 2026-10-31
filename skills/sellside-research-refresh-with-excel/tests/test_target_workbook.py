from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook


PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "scripts"))

from build_target_workbook import build_stage3, load_confirmed_stage2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def stage2_fixture(root: Path, status: str = "CONFIRMED") -> Path:
    stage2_dir = root / "stage2"
    artifacts = {
        "entity_mapping.json": {
            "target_primary": {
                "entity_id": "B",
                "name": "目标公司",
                "code": "600000.SH",
            },
            "mappings": [
                {
                    "source_entity_id": "A",
                    "role": "PRIMARY",
                    "action": "REPLACE",
                    "target_entity_id": "B",
                }
            ],
        },
        "period_mapping.json": [
            {
                "source_period": "2024A",
                "target_period": "2025A",
                "status": "MAPPED",
            }
        ],
        "coverage_requirements.json": [
            {
                "coverage_id": "cov-revenue",
                "object_id": "revenue-table",
                "metric_name": "营业收入",
                "target_entity_id": "B",
                "target_entity_name": "目标公司",
                "source_periods": ["2024A"],
                "target_periods": ["2025A"],
                "frequency": "ANNUAL",
                "actual_forecast": "ACTUAL",
                "unit": "亿元",
                "indicator_path_hint": "Choice\\财务\\营业收入",
                "disposition": "planned_mql",
                "reason": "",
                "report_priority": "CORE",
                "source_location": "10_研报快照!A1",
            }
        ],
        "target_table_mapping.json": [
            {
                "source_object_id": "revenue-table",
                "target_object_id": "target-revenue-table",
                "object_type": "TABLE",
                "source_title": "收入表",
                "target_title": "收入表",
                "action": "adapt",
                "coverage_ids": ["cov-revenue"],
                "reason": "Adapt source structure using target facts",
            }
        ],
        "information_rows.json": [],
    }
    outputs = []
    for name, value in artifacts.items():
        path = stage2_dir / name
        write_json(path, value)
        outputs.append(
            {
                "path": str(path.resolve()),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
                "media_type": "application/json",
            }
        )
    handoff_path = stage2_dir / "stage-2-handoff.json"
    write_json(
        handoff_path,
        {
            "schema_version": 1,
            "task_id": "stage-d-test",
            "stage": 2,
            "status": status,
            "producer": {
                "skill": "sellside-research-refresh-with-excel20",
                "version": "2.0.0",
                "mode": "目标适配与取数计划",
            },
            "inputs": [],
            "outputs": outputs,
            "started_at": "2026-10-03T00:00:00+08:00",
            "completed_at": "2026-10-03T00:00:01+08:00",
            "validation": [{"name": "target adaptation gates", "status": "PASS"}],
            "limitations": [],
            "error": None,
            "resume": {
                "next_stage": 3,
                "requires_user_confirmation": True,
                "input_hashes": {},
            },
        },
    )
    return handoff_path


def evidence_fixture() -> dict:
    script = (
        "CrossSectionBlock(#1, {EM_CODE});\n"
        'SetCodes(["600000.SH"]);\n'
        "{营业收入}: {Choice指标\\股票\\营业收入}();\n"
        "OutputBlock();"
    )
    response = {
        "ok": True,
        "traceparent": "actual-test-trace",
        "mql": script,
        "result": {
            "blocks": [
                {
                    "blockId": 1,
                    "column_schema": [
                        {"name": "EM_CODE", "hidden_key": False},
                        {"name": "营业收入", "hidden_key": False},
                    ],
                    "columns": ["EM_CODE", "营业收入"],
                    "rows": [{"EM_CODE": "600000.SH", "营业收入": 1000000000}],
                    "total": 1,
                }
            ],
            "type": "blocks",
        },
    }
    coverage = {
        "coverage_id": "cov-revenue",
        "workbook_row_id": "cov-revenue",
        "object_id": "revenue-table",
        "source_row_ids": ["revenue-table:row:1"],
        "item": "营业收入",
        "category": "financial_statement",
        "data_kind": "structured",
        "disposition": "mql_returned",
        "block_key": "revenue-query",
        "returned_field": "营业收入",
        "source_unit": "元",
        "target_unit": "元",
        "report_location": "正文1.1 表1",
    }
    fact = {
        "evidence_id": "cov-revenue",
        "source_id": 1,
        "metric_id": "revenue",
        "item": "营业收入",
        "source": "Choice 金融查数",
        "data_date": "2025-12-31",
        "raw_value": 1000000000,
        "source_unit": "元",
        "period_semantics": "2025A",
        "value_semantics": "年度实际",
        "normalization_factor": 1,
        "normalized_value": 1000000000,
        "display_unit": "元",
        "caliber": "合并口径",
        "raw_locator": "actual-test-trace #1",
        "report_location": "正文1.1 表1",
        "source_type": "Choice 金融查数",
        "block_key": "revenue-query",
        "execution_id": "actual-test-trace",
        "returned_field": "营业收入",
        "coverage_status": "已返回",
        "coverage_id": "cov-revenue",
        "acquired_at": "2026-10-03",
    }
    return {
        "schema_version": 1,
        "target_identity": {
            "entity_id": "B",
            "entity_name": "目标公司",
            "security_code": "600000.SH",
        },
        "writing_payload": {
            "workbook_meta": {
                "subject": "目标公司",
                "security_code": "600000.SH",
                "report_type": "研究报告",
                "report_date": "2026-10-03",
                "data_cutoff": "2025-12-31",
                "currency": "人民币",
                "forecast_period": "不适用",
                "deliverables": "阶段D新标的底稿",
            },
            "scope": "full_reproduction",
            "category_applicability": {
                "financial_statement": {"status": "required"}
            },
            "reference_objects": {
                "tables": [
                    {
                        "table_id": "revenue-table",
                        "page": 1,
                        "source_order": 1,
                        "title": "收入表",
                        "headers": ["科目", "2025A"],
                        "header_levels": [],
                        "row_sequence": [
                            {
                                "source_row_id": "revenue-table:row:1",
                                "label": "营业收入",
                            }
                        ],
                        "required_periods": ["2025A"],
                        "unit": "元",
                        "footnotes": [],
                    }
                ]
            },
            "reference_display_tables": [
                {
                    "object_id": "revenue-table",
                    "title": "收入表",
                    "source_page_index": 1,
                    "source_order": 1,
                    "headers": ["科目", "2025A"],
                    "rows": [
                        {
                            "source_row_id": "revenue-table:row:1",
                            "label": "营业收入",
                            "cells": [
                                {
                                    "block_key": "revenue-query",
                                    "returned_field": "营业收入",
                                    "result_row": 1,
                                }
                            ],
                        }
                    ],
                }
            ],
            "coverage_requirements": [coverage],
            "mql_execution_records": [
                {
                    "tool_execution": {
                        "tool_call_id": "actual-test-trace",
                        "request": {"mql": script},
                        "response": response,
                    },
                    "result_as_of": "2025-12-31",
                    "plan": {
                        "table_id": "revenue-query",
                        "coverage_ids": ["cov-revenue"],
                        "returned_fields": {"cov-revenue": "营业收入"},
                        "source_object_ids": ["revenue-table"],
                    },
                    "excel": {
                        "source_page": "1",
                        "source_page_index": 1,
                        "source_order": 1,
                        "source_figure_name": "收入表",
                        "target_table_name": "收入表",
                        "layout_class": "financial",
                        "mql_orientation": 1,
                        "mql_formula_cols": 2,
                        "mql_formula_rows": 2,
                        "refresh_rows": 3,
                        "refresh_columns": 2,
                        "refresh_shape_evidence": "result_matrix",
                    },
                }
            ],
            "fact_rows": [fact],
            "forecast_rows": [],
            "information_rows": [],
            "report_mapping_rows": [
                {
                    "report_location": "正文1.1 表1",
                    "evidence_ids": ["cov-revenue"],
                    "use_content": "营业收入",
                    "status": "已登记",
                }
            ],
            "source_registry": [
                {
                    "source_id": 1,
                    "origin": "mql",
                    "provider": "Choice 金融查数",
                    "record_id": "actual-test-trace",
                    "evidence_ids": ["cov-revenue"],
                }
            ],
        },
    }


def replay_fixture(evidence: dict, mismatch: str | None = None) -> dict:
    """Build mql_replay_records.json from an evidence fixture.

    When *mismatch* is None, every replay returns identical data.
    When *mismatch* is "value", one cell value is altered.
    When *mismatch* is "missing", one record is omitted from replay.
    """
    records = evidence["writing_payload"]["mql_execution_records"]
    replay_records = []
    for idx, rec in enumerate(records):
        if mismatch == "missing" and idx == 0:
            continue
        tool_exec = rec["tool_execution"]
        response = json.loads(json.dumps(tool_exec["response"]))
        if mismatch == "value" and idx == 0:
            response["result"]["blocks"][0]["rows"][0]["营业收入"] = 999
        replay_records.append({
            "request": {"mql": tool_exec["request"]["mql"]},
            "response": response,
            "replay_tool_call_id": f"replay-{idx}",
        })
    return {
        "schema_version": 1,
        "replayed_at": "2026-10-08T10:00:00+08:00",
        "records": replay_records,
    }


class TargetWorkbookTests(unittest.TestCase):
    def test_copied_core_builder_matches_frozen_baseline(self) -> None:
        baseline = (
            PACKAGE.parent
            / "sellside-research-refresh-with-excel"
            / "scripts"
        )
        if not baseline.is_dir():
            self.skipTest(
                "旧版基线 skill 在当前布局下不可用，跳过同步比对"
            )
        # Only check files that are intentionally kept in sync with the baseline.
        # build_writing_workbook.py and validate_mql_workbook_coverage.py have been
        # intentionally modified to produce 5-Sheet format matching research-report-review.
        for name in (
            "reproduction_contract.py",
            "validate_report_citations.py",
        ):
            self.assertEqual(
                (PACKAGE / "scripts" / name).read_bytes(),
                (baseline / name).read_bytes(),
            )

    def test_requires_confirmed_stage_two_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            handoff = stage2_fixture(Path(directory), "PASS_WAITING_CONFIRMATION")
            with self.assertRaisesRegex(ValueError, "must be CONFIRMED"):
                load_confirmed_stage2(handoff)

    def test_rejects_changed_stage_two_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff = stage2_fixture(root)
            path = root / "stage2" / "coverage_requirements.json"
            path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "size mismatch"):
                load_confirmed_stage2(handoff)

    def test_rejects_source_workbook_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff = stage2_fixture(root)
            evidence = evidence_fixture()
            evidence["writing_payload"]["source_registry"][0]["origin"] = "source_workbook"
            evidence_path = root / "evidence.json"
            write_json(evidence_path, evidence)
            with self.assertRaisesRegex(ValueError, "cannot enter target workbook"):
                build_stage3(handoff, evidence_path, root / "out")

    def test_rejects_incomplete_final_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff = stage2_fixture(root)
            evidence = evidence_fixture()
            evidence["writing_payload"]["coverage_requirements"] = []
            evidence_path = root / "evidence.json"
            write_json(evidence_path, evidence)
            with self.assertRaisesRegex(ValueError, "coverage IDs differ"):
                build_stage3(handoff, evidence_path, root / "out")

    def test_builds_five_sheet_workbook_and_stage_three_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff = stage2_fixture(root)
            evidence = evidence_fixture()
            evidence_path = root / "evidence.json"
            write_json(evidence_path, evidence)
            replay_path = root / "replay.json"
            write_json(replay_path, replay_fixture(evidence))
            output = root / "out"
            result = build_stage3(handoff, evidence_path, output, replay_path=replay_path)
            self.assertEqual(result["status"], "CONFIRMED")
            self.assertEqual(len(result["validation"]), 4)
            self.assertEqual(result["validation"][0]["name"], "MQL replay verification")
            workbook = load_workbook(output / "B_新标的底稿.xlsx")
            self.assertEqual(
                workbook.sheetnames,
                [
                    "00_导读",
                    "10_研报快照",
                    "20_研报底稿",
                    "30_预测框架",
                    "90_执行日志",
                ],
            )
            for name in (
                "mql_audit.json",
                "mql_coverage_receipt.json",
                "reference_coverage_receipt.json",
                "workbook_structure_receipt.json",
                "mql_replay_receipt.json",
                "stage-3-handoff.json",
            ):
                self.assertTrue((output / name).is_file())

    def test_rejects_missing_replay_when_mql_records_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff = stage2_fixture(root)
            evidence = evidence_fixture()
            evidence_path = root / "evidence.json"
            write_json(evidence_path, evidence)
            with self.assertRaisesRegex(ValueError, "mql_replay_records.json is required"):
                build_stage3(handoff, evidence_path, root / "out")

    def test_rejects_replay_value_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff = stage2_fixture(root)
            evidence = evidence_fixture()
            evidence_path = root / "evidence.json"
            write_json(evidence_path, evidence)
            replay_path = root / "replay.json"
            write_json(replay_path, replay_fixture(evidence, mismatch="value"))
            with self.assertRaisesRegex(ValueError, "validator failed"):
                build_stage3(handoff, evidence_path, root / "out", replay_path=replay_path)

    def test_rejects_replay_missing_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff = stage2_fixture(root)
            evidence = evidence_fixture()
            evidence_path = root / "evidence.json"
            write_json(evidence_path, evidence)
            replay_path = root / "replay.json"
            write_json(replay_path, replay_fixture(evidence, mismatch="missing"))
            with self.assertRaisesRegex(ValueError, "validator failed"):
                build_stage3(handoff, evidence_path, root / "out", replay_path=replay_path)


if __name__ == "__main__":
    unittest.main()
