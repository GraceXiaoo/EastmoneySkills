"""U4 回归测试：run_manifest 落盘链路与可复用判定（2026-10-22）。

缺陷背景：`run_manifest.py` 早已具备 check/record 能力，但阶段脚本从未调用，
导致任务目录始终没有 `run_manifest.json`，续跑时无法按指纹复用已完成操作。

本模块覆盖三类不变量：
1. CLI 的 record → check 往返：PASS + 指纹一致 + 结果存在才算 reusable；
2. 指纹漂移、结果缺失、BLOCKED 状态均必须判为不可复用；
3. 阶段脚本 `--manifest` 集成：成功落盘后自动记录，缺省时不产生 manifest；
   记录动作不得丢弃任务级字段（refresh_capability / external_blockers）。

所有输入为进程内合成的离线夹具，不调用外部服务。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
MANIFEST_CLI = SCRIPTS / "run_manifest.py"
PHASES = SCRIPTS / "prepare_workbook_phases.py"

sys.path.insert(0, str(SCRIPTS))
from run_manifest import load_manifest, record_operation  # noqa: E402


def _run(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *arguments], capture_output=True, text=True)


def _evidence_payload() -> dict:
    return {
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


class ManifestRoundTripTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.directory = Path(self._directory.name)
        self.manifest = self.directory / "run_manifest.json"
        self.input = self.directory / "input.mql"
        self.input.write_text("SELECT 1;", encoding="utf-8")
        self.result = self.directory / "result.json"
        self.result.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self._directory.cleanup()

    def _record(self, status="PASS", result=True, execution_id="run-1"):
        arguments = [
            str(MANIFEST_CLI), "--manifest", str(self.manifest), "record",
            "--stage", "4", "--object-id", "p1-t1-a", "--operation", "mql_execute",
            "--input", str(self.input), "--status", status,
            "--execution-id", execution_id,
        ]
        if result:
            arguments += ["--result-path", str(self.result)]
        completed = _run(*arguments)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def _check(self) -> tuple[bool, int]:
        completed = _run(
            str(MANIFEST_CLI), "--manifest", str(self.manifest), "check",
            "--stage", "4", "--object-id", "p1-t1-a", "--operation", "mql_execute",
            "--input", str(self.input),
        )
        return json.loads(completed.stdout)["reusable"], completed.returncode

    def test_pass_with_matching_fingerprint_is_reusable(self):
        self._record()
        reusable, code = self._check()
        self.assertTrue(reusable)
        self.assertEqual(code, 0)

    def test_records_status_fingerprint_and_execution_id(self):
        self._record(execution_id="run-p1-t1-a-1019")
        entry = load_manifest(self.manifest)["operations"]["4:p1-t1-a:mql_execute"]
        self.assertEqual(entry["status"], "PASS")
        self.assertEqual(entry["execution_id"], "run-p1-t1-a-1019")
        self.assertEqual(entry["result_path"], str(self.result.resolve()))
        self.assertIn(str(self.input.resolve()), entry["input_fingerprints"])

    def test_input_drift_invalidates_reuse(self):
        self._record()
        self.input.write_text("SELECT 2;", encoding="utf-8")
        reusable, code = self._check()
        self.assertFalse(reusable)
        self.assertEqual(code, 1)

    def test_missing_result_path_invalidates_reuse(self):
        self._record()
        self.result.unlink()
        reusable, code = self._check()
        self.assertFalse(reusable)
        self.assertEqual(code, 1)

    def test_blocked_status_never_reusable(self):
        self._record(status="BLOCKED")
        reusable, code = self._check()
        self.assertFalse(reusable)
        self.assertEqual(code, 1)

    def test_unknown_operation_not_reusable(self):
        self._record()
        completed = _run(
            str(MANIFEST_CLI), "--manifest", str(self.manifest), "check",
            "--stage", "4", "--object-id", "p9-t9-a", "--operation", "mql_execute",
            "--input", str(self.input),
        )
        self.assertFalse(json.loads(completed.stdout)["reusable"])
        self.assertEqual(completed.returncode, 1)


class PhaseManifestIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.directory = Path(self._directory.name)

    def tearDown(self):
        self._directory.cleanup()

    def _normalize(self, manifest: Path | None, object_id: str = "demo-task") -> subprocess.CompletedProcess:
        input_path = self.directory / "in.json"
        input_path.write_text(json.dumps(_evidence_payload(), ensure_ascii=False), encoding="utf-8")
        arguments = [
            str(PHASES), "normalize-evidence",
            "--input", str(input_path), "--output", str(self.directory / "out.json"),
        ]
        if manifest is not None:
            arguments += ["--manifest", str(manifest), "--object-id", object_id]
        return _run(*arguments)

    def test_normalize_records_evidence_operation(self):
        manifest = self.directory / "run_manifest.json"
        completed = self._normalize(manifest)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        data = load_manifest(manifest)
        entry = data["operations"]["2:demo-task:evidence"]
        self.assertEqual(entry["status"], "PASS")
        self.assertEqual(entry["object_id"], "demo-task")
        self.assertEqual(entry["result_path"], str((self.directory / "out.json").resolve()))

    def test_normalize_without_manifest_creates_none(self):
        completed = self._normalize(None)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse((self.directory / "run_manifest.json").exists())

    def test_recording_preserves_task_level_fields(self):
        manifest = self.directory / "run_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": {},
                    "task_id": "demo-task",
                    "refresh_capability": {"refreshable_anchors": [], "online_refresh_verified": False},
                    "external_blockers": [{"id": "E1"}, {"id": "E3"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        record_operation(manifest, "5", "demo-task", "deliverable", inputs=[], result_path=None)
        data = load_manifest(manifest)
        self.assertEqual(data["task_id"], "demo-task")
        self.assertIn("refreshable_anchors", data["refresh_capability"])
        self.assertEqual([item["id"] for item in data["external_blockers"]], ["E1", "E3"])
        self.assertIn("5:demo-task:deliverable", data["operations"])

    def test_record_operation_never_raises_on_corrupt_manifest(self):
        manifest = self.directory / "run_manifest.json"
        manifest.write_text("not a manifest", encoding="utf-8")
        record_operation(manifest, "5", "demo-task", "deliverable", inputs=[])
        self.assertEqual(manifest.read_text(encoding="utf-8"), "not a manifest")


if __name__ == "__main__":
    unittest.main()
