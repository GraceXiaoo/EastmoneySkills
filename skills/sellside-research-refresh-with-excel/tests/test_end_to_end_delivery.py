from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import Workbook, load_workbook


PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "scripts"))

from assemble_delivery import assemble_delivery, assess_resume


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(path: Path, media_type: str) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "media_type": media_type,
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def make_workbook(path: Path, *, extended: bool = False) -> None:
    workbook = Workbook()
    workbook.active.title = "10_研报快照"
    if extended:
        workbook.create_sheet("21_EDB_001")
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def make_chain(
    root: Path,
    *,
    statuses: dict[int, str] | None = None,
    stage3_limitations: list[str] | None = None,
    extended: bool = False,
    workflow_status: str = "COMPLETE",
) -> list[Path]:
    statuses = statuses or {}
    source_workbook = root / "A_原始底稿.xlsx"
    make_workbook(source_workbook, extended=extended)
    source_review = root / "A_底稿评测报告.md"
    source_review.write_text("投研用户评测报告", encoding="utf-8")
    target_workbook = root / "B_新标的底稿.xlsx"
    make_workbook(target_workbook)
    target_md = root / "B_新研报.md"
    target_md.write_text(
        "**非原机构正式报告**　2026-10-03\n\n# 新研报",
        encoding="utf-8",
    )
    markdown_hash = sha256(target_md)
    target_html = root / "B_新研报.html"
    target_html.write_text(
        "<!doctype html><html><head>"
        f'<meta name="source-md-sha256" content="{markdown_hash}">'
        "</head><body>新研报</body></html>",
        encoding="utf-8",
    )
    workflow_state = root / "workflow_state.json"
    write_json(
        workflow_state,
        {
            "status": workflow_status,
            "generated_at": "2026-10-03T10:01:00+08:00",
        },
    )
    generic_outputs: list[list[dict[str, object]]] = [
        [
            artifact(
                source_workbook,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            artifact(source_review, "text/markdown"),
        ],
        [],
        [],
        [
            artifact(
                target_workbook,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        ],
        [
            artifact(target_md, "text/markdown"),
            artifact(target_html, "text/html"),
            artifact(workflow_state, "application/json"),
        ],
    ]
    paths: list[Path] = []
    previous: Path | None = None
    for stage in range(5):
        inputs = (
            [artifact(previous, "application/json")]
            if previous is not None
            else []
        )
        if stage in {1, 2}:
            output = root / f"stage-{stage}-artifact.json"
            write_json(output, {"stage": stage})
            generic_outputs[stage] = [artifact(output, "application/json")]
        handoff = {
            "schema_version": 1,
            "task_id": "end-to-end-test",
            "stage": stage,
            "status": statuses.get(stage, "CONFIRMED"),
            "producer": {
                "skill": "fixture",
                "version": "1.0.0",
                "mode": "test",
            },
            "inputs": inputs,
            "outputs": generic_outputs[stage],
            "started_at": "2026-10-03T10:00:00+08:00",
            "completed_at": "2026-10-03T10:01:00+08:00",
            "validation": [{"name": "fixture", "status": "PASS"}],
            "limitations": (
                stage3_limitations if stage == 3 and stage3_limitations else []
            ),
            "error": (
                {"category": "blocked fixture"}
                if statuses.get(stage) == "BLOCKED"
                else None
            ),
            "resume": {
                "next_stage": stage + 1 if stage < 4 else 5,
                "requires_user_confirmation": True,
                "input_hashes": {
                    str(previous.resolve()): sha256(previous)
                }
                if previous is not None
                else {},
            },
        }
        if stage == 4:
            handoff["generator"] = {
                "skill": "fixture",
                "script": "prepare_drafting_handoff.py finalize",
                "version": "3.0.4",
            }
            handoff["engine_receipt"] = {
                "workflow_state": {
                    "path": str(workflow_state.resolve()),
                    "sha256": sha256(workflow_state),
                    "status": workflow_status,
                },
                "markdown_sha256": markdown_hash,
                "html_sha256": sha256(target_html),
                "source_md_sha256_meta": markdown_hash,
            }
        path = root / f"stage-{stage}-handoff.json"
        write_json(path, handoff)
        paths.append(path)
        previous = path
    return paths


class EndToEndDeliveryTests(unittest.TestCase):
    def test_assembles_minimum_delivery_set_without_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_chain(root)
            manifest, stage5 = assemble_delivery(paths, root / "delivery")
            self.assertEqual(manifest["status"], "PASS")
            self.assertEqual(stage5["status"], "CONFIRMED")
            self.assertEqual(
                {item["kind"] for item in manifest["deliveries"]},
                {
                    "source_workbook",
                    "source_review_report",
                    "target_workbook",
                    "target_report_markdown",
                    "target_report_html",
                },
            )
            self.assertEqual(
                manifest["validation"][3]["reused_stages"],
                [0, 1, 2, 3, 4],
            )

    def test_changed_artifact_resumes_first_affected_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_chain(root)
            stage1 = json.loads(paths[1].read_text(encoding="utf-8"))
            changed = Path(stage1["outputs"][0]["path"])
            changed.write_text('{"changed": true}', encoding="utf-8")
            result = assess_resume(paths)
            self.assertEqual(result["status"], "RESUME_REQUIRED")
            self.assertEqual(result["first_stage"], 1)
            self.assertEqual(result["reusable_stages"], [0])

    def test_partial_mql_failure_is_preserved_as_limitation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_chain(
                root,
                stage3_limitations=["部分MQL失败，未返回指标已显式标记"],
            )
            manifest, _ = assemble_delivery(paths, root / "delivery")
            self.assertIn(
                "部分MQL失败，未返回指标已显式标记",
                manifest["limitations"],
            )

    def test_extended_edb_sheet_does_not_block_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_chain(root, extended=True)
            manifest, _ = assemble_delivery(paths, root / "delivery")
            source = next(
                item
                for item in manifest["deliveries"]
                if item["kind"] == "source_workbook"
            )
            workbook = load_workbook(source["path"], read_only=True)
            try:
                self.assertIn("21_EDB_001", workbook.sheetnames)
            finally:
                workbook.close()

    def test_entity_or_period_ambiguity_resumes_stage_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = make_chain(Path(directory), statuses={2: "BLOCKED"})
            result = assess_resume(paths)
            self.assertEqual(result["first_stage"], 2)
            self.assertEqual(result["reusable_stages"], [0, 1])

    def test_blocked_child_skill_resumes_its_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = make_chain(Path(directory), statuses={4: "BLOCKED"})
            result = assess_resume(paths)
            self.assertEqual(result["first_stage"], 4)
            self.assertEqual(result["reusable_stages"], [0, 1, 2, 3])

    def test_strict_chain_rejects_missing_previous_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_chain(root)
            stage3 = json.loads(paths[3].read_text(encoding="utf-8"))
            stage3["inputs"] = []
            write_json(paths[3], stage3)
            stage4 = json.loads(paths[4].read_text(encoding="utf-8"))
            stage4["inputs"][0] = artifact(paths[3], "application/json")
            write_json(paths[4], stage4)
            result = assess_resume(paths)
            self.assertEqual(result["first_stage"], 3)
            self.assertIn("does not bind", result["reason"])

    def test_unverified_layout_adds_render_audit_limitation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_chain(
                root,
                workflow_status="COMPLETE_WITH_UNVERIFIED_LAYOUT",
            )
            manifest, stage5 = assemble_delivery(paths, root / "delivery")
            self.assertEqual(manifest["status"], "PASS")
            self.assertEqual(stage5["status"], "CONFIRMED")
            self.assertTrue(
                any(
                    limitation.startswith("版式未渲染审计")
                    for limitation in manifest["limitations"]
                )
            )
            provenance = manifest["validation"][4]
            self.assertEqual(provenance["name"], "stage-4 drafting provenance")
            self.assertEqual(
                provenance["workflow_status"],
                "COMPLETE_WITH_UNVERIFIED_LAYOUT",
            )

    def test_missing_generator_fails_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_chain(root)
            stage4 = json.loads(paths[4].read_text(encoding="utf-8"))
            del stage4["generator"]
            write_json(paths[4], stage4)
            manifest, stage5 = assemble_delivery(paths, root / "delivery")
            self.assertEqual(manifest["status"], "FAIL")
            self.assertEqual(stage5["status"], "FAILED")
            self.assertEqual(
                stage5["error"]["category"], "STAGE4_BYPASSED"
            )
            self.assertTrue(
                any("generator" in reason for reason in manifest["failure_reasons"])
            )
            self.assertIn("STAGE4_BYPASSED", "\n".join(manifest["failure_reasons"]))
            failed_kinds = {
                item["kind"]
                for item in manifest["deliveries"]
                if item["acceptance_status"] == "FAIL"
            }
            self.assertEqual(
                failed_kinds,
                {"target_report_markdown", "target_report_html"},
            )

    def test_receipt_hash_mismatch_fails_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_chain(root)
            stage4 = json.loads(paths[4].read_text(encoding="utf-8"))
            stage4["engine_receipt"]["markdown_sha256"] = "0" * 64
            write_json(paths[4], stage4)
            manifest, stage5 = assemble_delivery(paths, root / "delivery")
            self.assertEqual(manifest["status"], "FAIL")
            self.assertEqual(stage5["status"], "FAILED")
            self.assertTrue(
                any(
                    "markdown sha256 differs" in reason
                    for reason in manifest["failure_reasons"]
                )
            )

    def test_illegal_workflow_status_fails_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_chain(root)
            stage4 = json.loads(paths[4].read_text(encoding="utf-8"))
            stage4["engine_receipt"]["workflow_state"]["status"] = "SUCCESS"
            write_json(paths[4], stage4)
            manifest, stage5 = assemble_delivery(paths, root / "delivery")
            self.assertEqual(manifest["status"], "FAIL")
            self.assertEqual(stage5["status"], "FAILED")
            self.assertTrue(
                any(
                    "legal delivery state" in reason
                    for reason in manifest["failure_reasons"]
                )
            )

    def test_main_returns_nonzero_when_provenance_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_chain(root)
            stage4 = json.loads(paths[4].read_text(encoding="utf-8"))
            del stage4["generator"]
            write_json(paths[4], stage4)
            argv = [
                "assemble_delivery",
                *[str(path) for path in paths],
                "--output-dir",
                str(root / "delivery"),
            ]
            from assemble_delivery import main

            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(main(), 1)


if __name__ == "__main__":
    unittest.main()
