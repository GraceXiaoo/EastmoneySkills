"""Stage A contract checks for the research reproduction 2.0 package."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]


class OrchestrationContractTests(unittest.TestCase):
    def test_dependency_closure_contains_direct_workbook_import(self) -> None:
        inventory = self._json("reference/dependency_inventory.json")
        scripts = {item["path"]: item for item in inventory["source_baseline"]["scripts"]}
        self.assertIn("scripts/build_writing_workbook.py", scripts)
        self.assertIn(
            "scripts/reproduction_contract.py",
            scripts["scripts/build_writing_workbook.py"]["local_imports"],
        )
        self.assertIn("scripts/reproduction_contract.py", scripts)
        self.assertIn("scripts/validate_report_citations.py", scripts)
        self.assertIn(
            "reference/workbook_spec.md",
            inventory["source_baseline"]["references"],
        )

    def test_handoff_schema_and_contract_freeze_required_states(self) -> None:
        schema = self._json("reference/orchestration_contract.schema.json")
        statuses = schema["properties"]["status"]["enum"]
        self.assertEqual(
            statuses,
            [
                "PENDING",
                "IN_PROGRESS",
                "CONFIRMED",
                "BLOCKED",
            ],
        )
        self.assertEqual(schema["properties"]["stage"]["maximum"], 5)

    def test_contract_covers_every_runtime_stage_and_delivery(self) -> None:
        contract = (PACKAGE / "reference" / "orchestration_contract.md").read_text(
            encoding="utf-8"
        )
        for stage in range(6):
            self.assertIn(f"### 阶段 {stage}", contract)
        for marker in (
            "A_原始底稿.xlsx",
            "A_底稿评测报告.md",
            "B_新标的底稿.xlsx",
            "B_新研报.md",
            "B_新研报.html",
            "30_预测框架",
        ):
            self.assertIn(marker, contract)

    def test_manifest_respects_stage_confirmation_gate(self) -> None:
        manifest = self._json("run_manifest.json")
        stages = {item["id"]: item for item in manifest["implementation_stages"]}
        self.assertEqual(stages["A"]["status"], "CONFIRMED")
        self.assertIn(
            stages["B"]["status"],
            {"PENDING", "IN_PROGRESS", "CONFIRMED"},
        )
        self.assertEqual(stages["C"]["status"], "CONFIRMED")
        self.assertEqual(stages["D"]["status"], "CONFIRMED")
        self.assertEqual(stages["E"]["status"], "CONFIRMED")
        self.assertEqual(stages["F"]["status"], "CONFIRMED")
        self.assertEqual(manifest["implementation_status"], "CONFIRMED")
        skill = (PACKAGE / "SKILL.md").read_text(encoding="utf-8")
        # 2026-10-12 SKILL.md 迁移至 v3.x 自包含单体（vendor 模型），
        # 旧的 2.0 完成标记改为版本号 + 架构标记。
        self.assertIn('version: "3.0.4"', skill)
        self.assertIn("自包含单体", skill)
        self.assertIn("受控夹具不得冒充真实端到端执行", skill)

    def _json(self, relative: str) -> dict:
        return json.loads((PACKAGE / relative).read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
