"""U2 回归测试：阶段工件生成端必须写入 schema_version=1（2026-10-19）。

缺陷背景：`prepare_workbook_phases.py` 的 `from-layout` 与 `normalize-evidence` 子命令
此前输出的 census/evidence 工件缺少 `schema_version`，被 `merge_workbook_phases.py`
判定为 LEGACY，触发不必要的 FULL→PARTIAL 降级与 migration_log 污染。

本模块通过子进程调用 CLI 端到端验证输出工件顶层含 `schema_version == 1`。
所有输入为进程内合成的离线夹具，不调用外部服务。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "prepare_workbook_phases.py"
PHASE_SCHEMA_VERSION = 1


def _layout_payload() -> dict:
    return {
        "textBlocks": [
            {
                "page": 1,
                "index": 0,
                "classType": "table",
                "content": "| 项目 | 2024A |\n|---|---|\n| 营业收入 | 100 |",
                "minX": 0,
                "minY": 0,
                "maxX": 595,
                "maxY": 842,
            }
        ]
    }


def _evidence_payload(with_version: bool = False) -> dict:
    payload = {
        "snapshots": [
            {
                "table_id": "p1-t1",
                "table_name": "测试表",
                "headers": ["项目", "2024A"],
                "rows": [["营业收入", "100"]],
                "bbox": [0.0, 0.0, 1.0, 1.0],
            }
        ],
        "chart_snapshots": [],
        "chart_data": [],
    }
    if with_version:
        payload["schema_version"] = PHASE_SCHEMA_VERSION
    return payload


class PhaseSchemaVersionTests(unittest.TestCase):
    def test_from_layout_outputs_carry_schema_version(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            layout_path = directory / "layout.json"
            layout_path.write_text(json.dumps(_layout_payload(), ensure_ascii=False), encoding="utf-8")
            census_path = directory / "01_census.json"
            evidence_path = directory / "02_evidence.json"
            result = subprocess.run(
                [
                    sys.executable, str(GENERATOR), "from-layout",
                    "--layout-json", str(layout_path),
                    "--census-output", str(census_path),
                    "--evidence-output", str(evidence_path),
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            census = json.loads(census_path.read_text(encoding="utf-8"))
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(census.get("schema_version"), PHASE_SCHEMA_VERSION)
            self.assertEqual(evidence.get("schema_version"), PHASE_SCHEMA_VERSION)

    def test_normalize_evidence_adds_schema_version_when_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            input_path = directory / "in.json"
            output_path = directory / "out.json"
            input_path.write_text(json.dumps(_evidence_payload(with_version=False), ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(GENERATOR), "normalize-evidence", "--input", str(input_path), "--output", str(output_path)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(output.get("schema_version"), PHASE_SCHEMA_VERSION)

    def test_normalize_evidence_keeps_schema_version_one(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            input_path = directory / "in.json"
            output_path = directory / "out.json"
            input_path.write_text(json.dumps(_evidence_payload(with_version=True), ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(GENERATOR), "normalize-evidence", "--input", str(input_path), "--output", str(output_path)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(output.get("schema_version"), PHASE_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
