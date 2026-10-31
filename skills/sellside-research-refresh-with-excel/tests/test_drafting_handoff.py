from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
REPOSITORY = PACKAGE.parents[1]
sys.path.insert(0, str(PACKAGE / "scripts"))

from prepare_drafting_handoff import (
    finalize,
    load_confirmed_stage3,
    prepare,
)


STAGE3 = (
    PACKAGE
    / "examples"
    / "stage-d-sample"
    / "output"
    / "stage-3-handoff.json"
)
DRAFTING_SKILL = (
    REPOSITORY / "研报仿写skill" / "periodic-report-drafting"
)
REFERENCE_PDF = (
    REPOSITORY
    / "PDF"
    / "20260803-野村东方国际证券-中际旭创-300308.SZ-维持增持评级.pdf"
)
# 参考 PDF 与仿写 skill 属仓库级夹具，不随发布包 vendor。
# 编译产物被放到其他目录时它们不可用，相关集成测试跳过而非报错。
REPO_FIXTURES_AVAILABLE = (
    REFERENCE_PDF.is_file() and (DRAFTING_SKILL / "scripts").is_dir()
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(path: Path, media_type: str) -> dict:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "media_type": media_type,
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class DraftingHandoffTests(unittest.TestCase):
    def test_requires_confirmed_stage_three(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stage-3-handoff.json"
            handoff = json.loads(STAGE3.read_text(encoding="utf-8"))
            handoff["status"] = "PASS_WAITING_CONFIRMATION"
            write_json(path, handoff)
            with self.assertRaisesRegex(ValueError, "must be CONFIRMED"):
                load_confirmed_stage3(path)

    @unittest.skipUnless(
        REPO_FIXTURES_AVAILABLE,
        "仓库级夹具（参考 PDF / 仿写 skill scripts）在当前布局下不可用",
    )
    def test_prepare_runs_official_probe_and_accepts_readable_core(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            request = prepare(
                STAGE3,
                REFERENCE_PDF,
                DRAFTING_SKILL,
                "贵州茅台",
                "600519.SH",
                "2025A",
                "2025-12-31",
                run_dir,
            )
            self.assertEqual(request["consumer"]["skill"], "periodic-report-drafting")
            # 2026-10-12 drafting 新增 workbook_probe.py（commit 1f80693），
            # 官方 probe 对干净样例返回全 READABLE → status=READY（无降级警告）。
            self.assertEqual(request["status"], "READY")
            self.assertEqual(
                request["preflight"]["core_sheets"],
                ["10_研报快照", "30_预测框架"],
            )
            self.assertTrue(
                (run_dir / "work" / "excel-index.json").is_file()
            )

    def test_finalize_writes_stage_four_handoff_with_limitations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_file = root / "input.json"
            input_file.write_text("{}", encoding="utf-8")
            request_path = root / "stage-4-request.json"
            request = {
                "schema_version": 1,
                "task_id": "stage-e-test",
                "status": "READY_WITH_WARNINGS",
                "inputs": {
                    "stage3_handoff": artifact(input_file, "application/json"),
                    "reference_pdf": artifact(input_file, "application/pdf"),
                    "target_workbook": artifact(
                        input_file,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                },
                "preflight": {
                    "warnings": ["15_查数底稿: CONFIRM_REQUIRED"],
                    "excel_index": artifact(input_file, "application/json"),
                },
            }
            write_json(request_path, request)
            markdown = root / "report.md"
            markdown.write_text("# report", encoding="utf-8")
            markdown_hash = sha256(markdown)
            html = root / "report.html"
            html.write_text(
                "<!doctype html><html><head>"
                f'<meta name="source-md-sha256" content="{markdown_hash}">'
                "</head><body>report</body></html>",
                encoding="utf-8",
            )
            state = root / "workflow_state.json"
            write_json(
                state,
                {
                    "status": "NEEDS_VISUAL_REVIEW",
                    "generated_at": "2026-10-03T13:00:00+08:00",
                },
            )
            notes = root / "delivery-notes.json"
            write_json(notes, ["受控样例"])
            output = root / "output" / "stage-4-handoff.json"
            handoff = finalize(
                request_path,
                markdown,
                html,
                state,
                notes,
                output,
            )
            self.assertEqual(handoff["status"], "CONFIRMED")
            self.assertIn(
                "drafting workflow state: NEEDS_VISUAL_REVIEW",
                handoff["limitations"],
            )
            self.assertEqual(
                handoff["generator"]["script"],
                "prepare_drafting_handoff.py finalize",
            )
            self.assertEqual(
                handoff["engine_receipt"]["markdown_sha256"],
                markdown_hash,
            )
            self.assertEqual(
                handoff["engine_receipt"]["html_sha256"],
                sha256(html),
            )
            self.assertEqual(
                handoff["engine_receipt"]["workflow_state"]["status"],
                "NEEDS_VISUAL_REVIEW",
            )
            self.assertEqual(
                handoff["engine_receipt"]["source_md_sha256_meta"],
                markdown_hash,
            )
            self.assertTrue(output.is_file())

    def test_finalize_rejects_html_without_meta_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_file = root / "input.json"
            input_file.write_text("{}", encoding="utf-8")
            request_path = root / "request.json"
            write_json(
                request_path,
                {
                    "status": "READY",
                    "inputs": {
                        "stage3_handoff": artifact(input_file, "application/json"),
                        "reference_pdf": artifact(input_file, "application/pdf"),
                        "target_workbook": artifact(input_file, "application/json"),
                    },
                    "preflight": {
                        "warnings": [],
                        "excel_index": artifact(input_file, "application/json"),
                    },
                },
            )
            markdown = root / "report.md"
            markdown.write_text("# report", encoding="utf-8")
            html = root / "report.html"
            html.write_text("<html><body>report</body></html>", encoding="utf-8")
            state = root / "state.json"
            write_json(state, {"status": "COMPLETE"})
            notes = root / "notes.json"
            write_json(notes, [])
            with self.assertRaisesRegex(ValueError, "lacks source-md-sha256 meta"):
                finalize(
                    request_path,
                    markdown,
                    html,
                    state,
                    notes,
                    root / "handoff.json",
                )

    def test_finalize_rejects_meta_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_file = root / "input.json"
            input_file.write_text("{}", encoding="utf-8")
            request_path = root / "request.json"
            write_json(
                request_path,
                {
                    "status": "READY",
                    "inputs": {
                        "stage3_handoff": artifact(input_file, "application/json"),
                        "reference_pdf": artifact(input_file, "application/pdf"),
                        "target_workbook": artifact(input_file, "application/json"),
                    },
                    "preflight": {
                        "warnings": [],
                        "excel_index": artifact(input_file, "application/json"),
                    },
                },
            )
            markdown = root / "report.md"
            markdown.write_text("# report", encoding="utf-8")
            stale_hash = "0" * 64
            html = root / "report.html"
            html.write_text(
                "<!doctype html><html><head>"
                f'<meta name="source-md-sha256" content="{stale_hash}">'
                "</head><body>report</body></html>",
                encoding="utf-8",
            )
            state = root / "state.json"
            write_json(state, {"status": "COMPLETE"})
            notes = root / "notes.json"
            write_json(notes, [])
            with self.assertRaisesRegex(ValueError, "does not match the markdown hash"):
                finalize(
                    request_path,
                    markdown,
                    html,
                    state,
                    notes,
                    root / "handoff.json",
                )

    def test_finalize_rejects_unknown_workflow_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_file = root / "input.json"
            input_file.write_text("{}", encoding="utf-8")
            request_path = root / "request.json"
            write_json(
                request_path,
                {
                    "status": "READY",
                    "inputs": {
                        "stage3_handoff": artifact(input_file, "application/json"),
                        "reference_pdf": artifact(input_file, "application/pdf"),
                        "target_workbook": artifact(input_file, "application/json"),
                    },
                    "preflight": {
                        "warnings": [],
                        "excel_index": artifact(input_file, "application/json"),
                    },
                },
            )
            markdown = root / "report.md"
            markdown.write_text("# report", encoding="utf-8")
            html = root / "report.html"
            html.write_text("<html></html>", encoding="utf-8")
            state = root / "state.json"
            write_json(state, {"status": "SUCCESS"})
            notes = root / "notes.json"
            write_json(notes, [])
            with self.assertRaisesRegex(ValueError, "recognized delivery state"):
                finalize(
                    request_path,
                    markdown,
                    html,
                    state,
                    notes,
                    root / "handoff.json",
                )


if __name__ == "__main__":
    unittest.main()
