"""T25：阶段工件版本契约与显式迁移（R13）。

缺陷背景：阶段工件（01_census / 02_source_evidence / 04_query_results / forecast）与
合并产物此前不声明任何 schema 版本，旧 schema 工件与新 schema 工件会被静默合并，
既无迁移记录也无版本拒绝。

本模块全部输入为进程内合成的离线夹具，不调用任何外部服务，也不携带真实工具调用记录；
断言针对真实业务不变量（是否留下迁移证据、是否拒绝未知版本），而不是仅断言字段存在。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MERGER = ROOT / "scripts" / "merge_workbook_phases.py"
PHASE_SCHEMA_VERSION = 1
LEGACY_PHASE_SCHEMA = "LEGACY"


def _phase_payloads() -> dict:
    return {
        "census": {"guide": {}, "excluded_tables": []},
        "evidence": {"snapshots": [], "chart_snapshots": [], "chart_data": []},
        "queries": {"workpapers": [], "verification": [], "execution_log": [], "blocked_items": []},
        "forecast": {"forecast": {}},
    }


class PhaseSchemaMigrationTests(unittest.TestCase):
    def _run_merge(
        self, directory: Path, versions: dict, overrides: dict | None = None
    ) -> tuple[subprocess.CompletedProcess, Path]:
        payloads = _phase_payloads()
        for label, extra in (overrides or {}).items():
            payloads[label].update(extra)
        arguments = [sys.executable, str(MERGER)]
        for label in ("census", "evidence", "queries", "forecast"):
            payload = dict(payloads[label])
            declared = versions.get(label)
            if declared is not None:
                payload["schema_version"] = declared
            path = directory / f"{label}.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            arguments += [f"--{label}", str(path)]
        output = directory / "05_workbook_input.json"
        arguments += ["--output", str(output)]
        return subprocess.run(arguments, capture_output=True, text=True), output

    def test_current_schema_artifacts_need_no_migration(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            versions = {label: PHASE_SCHEMA_VERSION for label in ("census", "evidence", "queries", "forecast")}
            result, output = self._run_merge(directory, versions)
            self.assertEqual(result.returncode, 0, result.stderr)
            merged = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(merged["schema_version"], PHASE_SCHEMA_VERSION)
            self.assertEqual(merged["migration_log"], [])

    def test_legacy_artifacts_are_migrated_with_explicit_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            result, output = self._run_merge(directory, {})
            self.assertEqual(result.returncode, 0, result.stderr)
            merged = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(merged["schema_version"], PHASE_SCHEMA_VERSION)
            migrated = {record["phase"] for record in merged["migration_log"]}
            self.assertEqual(migrated, {"census", "evidence", "queries", "forecast"})
            for record in merged["migration_log"]:
                self.assertEqual(record["from_version"], LEGACY_PHASE_SCHEMA)
                self.assertEqual(record["to_version"], PHASE_SCHEMA_VERSION)

    def test_mixed_artifacts_migrate_only_the_legacy_ones(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            versions = {
                "census": PHASE_SCHEMA_VERSION,
                "evidence": None,
                "queries": PHASE_SCHEMA_VERSION,
                "forecast": PHASE_SCHEMA_VERSION,
            }
            result, output = self._run_merge(directory, versions)
            self.assertEqual(result.returncode, 0, result.stderr)
            merged = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual([record["phase"] for record in merged["migration_log"]], ["evidence"])

    def test_unsupported_schema_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            result, output = self._run_merge(directory, {"census": 99})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported schema_version", result.stderr)
            self.assertFalse(output.exists())

    def test_legacy_artifacts_never_pass_without_migration_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            result, output = self._run_merge(directory, {"census": LEGACY_PHASE_SCHEMA})
            self.assertEqual(result.returncode, 0, result.stderr)
            merged = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(merged["migration_log"], "旧 schema 工件不得在没有迁移证据的情况下通过")
            self.assertEqual(merged["migration_log"][0]["artifact"], "census.json")


    def test_legacy_full_workpaper_is_downgraded_with_revalidation_record(self):
        workpaper = {
            "mapping_id": "table:p1-t4",
            "source_id": "p1-t4",
            "source_type": "TABLE",
            "mapping_status": "FULL",
        }
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            result, output = self._run_merge(directory, {}, {"queries": {"workpapers": [workpaper]}})
            self.assertEqual(result.returncode, 0, result.stderr)
            merged = json.loads(output.read_text(encoding="utf-8"))
            merged_workpaper = merged["workpapers"][0]
            self.assertEqual(merged_workpaper["mapping_status"], "PARTIAL")
            self.assertTrue(merged_workpaper.get("mapping_note"))
            downgrades = [
                record
                for record in merged["migration_log"]
                if record.get("field") == "mapping_status"
            ]
            self.assertEqual(len(downgrades), 1)
            self.assertEqual(downgrades[0]["reason"], "LEGACY_SCHEMA_FULL_NOT_REVERIFIED")
            self.assertEqual(downgrades[0]["object_id"], "table:p1-t4")

    def test_legacy_full_chart_data_is_downgraded_with_note(self):
        chart_data = {
            "chart_id": "p1-c1",
            "mql_mapping_status": "FULL",
            "omitted_metrics": ["净利润"],
        }
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            result, output = self._run_merge(directory, {}, {"evidence": {"chart_data": [chart_data]}})
            self.assertEqual(result.returncode, 0, result.stderr)
            merged = json.loads(output.read_text(encoding="utf-8"))
            merged_chart = merged["chart_data"][0]
            self.assertEqual(merged_chart["mql_mapping_status"], "PARTIAL")
            self.assertTrue(merged_chart.get("mql_mapping_note"))
            self.assertEqual(merged_chart["omitted_metrics"], ["净利润"])
            self.assertTrue(
                any(
                    record.get("field") == "mql_mapping_status"
                    and record.get("reason") == "LEGACY_SCHEMA_FULL_NOT_REVERIFIED"
                    for record in merged["migration_log"]
                )
            )

    def test_current_schema_full_is_left_untouched(self):
        workpaper = {
            "mapping_id": "table:p1-t4",
            "source_id": "p1-t4",
            "source_type": "TABLE",
            "mapping_status": "FULL",
        }
        versions = {label: PHASE_SCHEMA_VERSION for label in ("census", "evidence", "queries", "forecast")}
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            result, output = self._run_merge(directory, versions, {"queries": {"workpapers": [workpaper]}})
            self.assertEqual(result.returncode, 0, result.stderr)
            merged = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(merged["workpapers"][0]["mapping_status"], "FULL")
            self.assertEqual(merged["migration_log"], [])

    def test_legacy_full_chart_without_derivable_evidence_blocks_merge(self):
        workpaper = {
            "mapping_id": "chart:p1-c1",
            "source_id": "p1-c1",
            "source_type": "CHART",
            "mapping_status": "FULL",
        }
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            result, output = self._run_merge(directory, {}, {"queries": {"workpapers": [workpaper]}})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("without omitted_metrics", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
