"""Regression tests for stage-0 validation and metric framework extraction."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment


PACKAGE = Path(__file__).resolve().parents[1]
MODULE_PATH = PACKAGE / "scripts" / "extract_metric_framework.py"
MODULE_SPEC = importlib.util.spec_from_file_location("extract_metric_framework", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Cannot load {MODULE_PATH}")
EXTRACTOR = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(EXTRACTOR)
ContractError = EXTRACTOR.ContractError
extract_framework = EXTRACTOR.extract_framework
normalize_period = EXTRACTOR.normalize_period
sha256_file = EXTRACTOR.sha256_file
write_stage1_handoff = EXTRACTOR.write_stage1_handoff


LOG_HEADERS = [
    "指标",
    "数据源",
    "查询接口",
    "原始 Block/记录编号",
    "执行编号",
    "取数时间",
    "完整指标路径/检索条件",
    "状态",
    "返回形状/摘要",
    "原始值",
    "单位",
    "原始链接",
    "信息",
    "脚本SHA-256",
]


def add_snapshot_section(
    sheet: object,
    row: int,
    heading: str,
    headers: list[str],
    data: list[list[object]],
    *,
    unit: str = "亿元",
    series: str = "",
) -> int:
    sheet.cell(row, 1, heading)
    row += 1
    sheet.cell(row, 1, "页码")
    sheet.cell(row, 2, 2)
    row += 1
    sheet.cell(row, 1, "单位")
    sheet.cell(row, 2, unit)
    row += 1
    if series:
        sheet.cell(row, 1, "序列")
        sheet.cell(row, 2, series)
        row += 1
    for column, value in enumerate(headers, start=1):
        sheet.cell(row, column, value)
    row += 1
    for values in data:
        for column, value in enumerate(values, start=1):
            sheet.cell(row, column, value)
        row += 1
    return row + 1


def add_workpaper_section(
    sheet: object,
    row: int,
    heading: str,
    anchor: str,
    note: str,
    *,
    status: str | None = None,
    reason: str = "",
    formula: str | None = None,
    edb_sheet: str = "",
) -> int:
    sheet.cell(row, 1, heading)
    row += 1
    for label, value in (
        ("来源ID", heading.split("|")[0].strip()),
        ("页码", 2),
        ("单位", "亿元"),
        ("可刷新锚点数", 1),
    ):
        sheet.cell(row, 1, label)
        sheet.cell(row, 2, value)
        row += 1
    sheet.cell(row, 1, anchor)
    sheet.cell(row, 2, f"打开独立 EDB 时序 Sheet：{edb_sheet}" if edb_sheet else note)
    row += 1
    if formula:
        cell = sheet.cell(row, 1, formula)
        cell.comment = Comment("TimeSeriesBlock(#1);", "test")
        row += 1
    elif status:
        sheet.cell(row, 1, "状态")
        sheet.cell(row, 2, status)
        sheet.cell(row + 1, 1, "原因")
        sheet.cell(row + 1, 2, reason)
        row += 2
    return row + 1


def create_fixture(root: Path) -> tuple[Path, Path, Path]:
    workbook_path = root / "A_原始底稿.xlsx"
    report_path = root / "A_底稿评测报告.md"
    handoff_path = root / "stage-0-handoff.json"

    workbook = Workbook()
    guide = workbook.active
    guide.title = "00_导读"
    guide.append(["项目", "内容"])
    guide.append(["研报", "测试研报"])

    snapshot = workbook.create_sheet("10_研报快照")
    row = add_snapshot_section(
        snapshot,
        1,
        "t1 | 利润表",
        ["指标", "2025A", "2026F"],
        [["营业收入", 100, 120], ["净利润", 10, 15]],
    )
    row = add_snapshot_section(
        snapshot,
        row,
        "c1 | 图1 | 行业指数",
        [],
        [],
        unit="点",
        series="指数A、指数B",
    )
    row = add_snapshot_section(
        snapshot,
        row,
        "c1-d1 | 图表双通道验收 | 行业指数",
        ["指标", "2026-09-30"],
        [["指数A", 1200], ["指数B", 980]],
        unit="点",
    )
    row = add_snapshot_section(
        snapshot,
        row,
        "t2 | 不适用表",
        ["指标", "2025A"],
        [["门店数", 30]],
        unit="家",
    )
    row = add_snapshot_section(
        snapshot,
        row,
        "t3 | 未映射表",
        ["指标", "2025A"],
        [["客户留存率", "80%"]],
        unit="%",
    )
    add_snapshot_section(
        snapshot,
        row,
        "c2 | 图2 | EDB序列",
        [],
        [],
        unit="点",
        series="EDB指标",
    )

    workpaper = workbook.create_sheet("20_研报底稿")
    row = add_workpaper_section(
        workpaper,
        1,
        "t1 | TABLE | 利润表",
        "锚点1 · t1-m1",
        "完整映射",
        formula='=mql("#1",0)',
    )
    row = add_workpaper_section(
        workpaper,
        row,
        "c1 | CHART | 行业指数",
        "锚点1 · c1-m1",
        "查询失败",
        status="TABLE_BLOCKED",
        reason="远端执行失败",
    )
    row = add_workpaper_section(
        workpaper,
        row,
        "t2 | TABLE | 不适用表",
        "锚点1 · t2-m1",
        "目标公司不适用",
        status="NOT_APPLICABLE",
        reason="目标公司不适用",
    )
    add_workpaper_section(
        workpaper,
        row,
        "c2 | CHART | EDB序列",
        "锚点1 · c2-m1",
        "EDB部分映射",
        edb_sheet="21_EDB_001",
    )

    edb = workbook.create_sheet("21_EDB_001")
    edb.append(["c2 | EDB | EDB序列"])
    edb.append(["来源ID", "c2"])
    edb.append(["页码", 2])
    edb.append(["单位", "点"])
    edb.append(["映射状态", "PARTIAL"])
    edb.append(["映射说明", "EDB时序已映射"])
    edb.append(["锚点1 · c2-m1"])
    cell = edb.cell(8, 1, '=mql("#1",0)')
    cell.comment = Comment("EdbBlock(#1);", "test")

    forecast = workbook.create_sheet("30_预测框架")
    forecast.append(["盈利预测驱动"])
    forecast.append(["驱动环节", "预测值或方向", "调整幅度", "原文依据", "可验证时点"])
    forecast.append(["销量", "增长", "10%", "订单", "2026F"])
    forecast.append([])
    forecast.append(["相对市场预期"])
    forecast.append(["指标", "财年", "分析师预测", "一致预期", "偏离度", "说明"])
    forecast.append(["EPS", "2026F", 1.2, 1.1, "9%", "高于预期"])

    log = workbook.create_sheet("90_执行日志")
    log.append(LOG_HEADERS)
    log.append(
        [
            "营业收入",
            "MQL",
            "MQL_TOOLCHAIN",
            "#1",
            "run-1",
            "2026-10-03T10:00:00+08:00",
            "Choice\\财务\\营业收入",
            "SUCCESS",
            "2x3",
            "",
            "亿元",
            "",
            "",
            hashlib.sha256(b"revenue").hexdigest(),
        ]
    )
    log.append(
        [
            "净利润",
            "MQL",
            "MQL_TOOLCHAIN",
            "#1",
            "run-2",
            "2026-10-03T10:01:00+08:00",
            "Choice\\财务\\净利润",
            "ERROR",
            "",
            "",
            "亿元",
            "",
            "远端执行失败",
            hashlib.sha256(b"profit").hexdigest(),
        ]
    )
    log.append(
        [
            "指数A",
            "MQL",
            "MQL_TOOLCHAIN",
            "#1",
            "",
            "2026-10-03T10:02:00+08:00",
            "Choice\\指数\\指数A",
            "NO_MATCH",
            "",
            "",
            "点",
            "",
            "无候选",
            "",
        ]
    )
    log.append(
        [
            "门店数",
            "MQL",
            "MQL_TOOLCHAIN",
            "",
            "",
            "2026-10-03T10:03:00+08:00",
            "",
            "NOT_APPLICABLE",
            "",
            "",
            "家",
            "",
            "目标公司不适用",
            "",
        ]
    )
    log.sheet_state = "hidden"

    workbook.save(workbook_path)
    report_path.write_text("# 原始底稿评测报告\n\n面向投研用户。\n", encoding="utf-8")
    payload = {
        "schema_version": 1,
        "task_id": "stage-b-test",
        "stage": 0,
        "status": "CONFIRMED",
        "producer": {
            "skill": "research-report-review",
            "version": "1.6.20",
            "mode": "生成研报底稿",
        },
        "inputs": [],
        "outputs": [
            {
                "path": str(workbook_path.resolve()),
                "sha256": sha256_file(workbook_path),
                "size_bytes": workbook_path.stat().st_size,
                "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
            {
                "path": str(report_path.resolve()),
                "sha256": sha256_file(report_path),
                "size_bytes": report_path.stat().st_size,
                "media_type": "text/markdown",
            },
        ],
        "started_at": "2026-10-03T10:00:00+08:00",
        "completed_at": "2026-10-03T10:10:00+08:00",
        "validation": [{"name": "底稿完成门禁", "status": "PASS"}],
        "limitations": [],
        "error": None,
        "resume": {
            "next_stage": 1,
            "requires_user_confirmation": False,
            "input_hashes": {},
        },
    }
    handoff_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return handoff_path, workbook_path, report_path


class MetricFrameworkExtractionTests(unittest.TestCase):
    def test_metric_framework_schema_freezes_status_values(self) -> None:
        schema = json.loads(
            (PACKAGE / "reference" / "metric_framework.schema.json").read_text(
                encoding="utf-8"
            )
        )
        status_values = schema["properties"]["metrics"]["items"]["properties"]["status"]["enum"]
        self.assertEqual(
            status_values,
            ["SUCCESS", "FAILED", "UNMAPPED", "NOT_APPLICABLE"],
        )

    def test_writes_stage_one_handoff_with_hashed_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_handoff, _, _ = create_fixture(root)
            framework_path = root / "metric_framework.json"
            summary_path = root / "framework_extracted.md"
            framework_path.write_text(
                json.dumps(extract_framework(source_handoff), ensure_ascii=False),
                encoding="utf-8",
            )
            summary_path.write_text("# 摘要\n", encoding="utf-8")
            handoff_path = root / "stage-1-handoff.json"
            write_stage1_handoff(
                source_handoff,
                framework_path,
                summary_path,
                handoff_path,
            )
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            self.assertEqual(handoff["stage"], 1)
            self.assertEqual(handoff["status"], "CONFIRMED")
            self.assertEqual(
                {Path(item["path"]).name for item in handoff["outputs"]},
                {"metric_framework.json", "framework_extracted.md"},
            )

    def test_extracts_all_statuses_forecast_and_edb(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            handoff_path, _, _ = create_fixture(Path(directory))
            framework = extract_framework(handoff_path)
            statuses = {item["status"] for item in framework["metrics"]}
            self.assertEqual(
                statuses,
                {"SUCCESS", "FAILED", "UNMAPPED", "NOT_APPLICABLE"},
            )
            labels = {item["metric_name"] for item in framework["metrics"]}
            self.assertTrue(
                {
                    "营业收入",
                    "净利润",
                    "指数A",
                    "指数B",
                    "门店数",
                    "客户留存率",
                    "EDB指标",
                    "销量",
                    "EPS",
                }.issubset(labels)
            )
            self.assertEqual(framework["coverage"]["edb_extension_sheets"], ["21_EDB_001"])
            self.assertEqual(framework["completeness"]["status"], "PASS")

    def test_metric_log_overrides_source_level_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            handoff_path, _, _ = create_fixture(Path(directory))
            metrics = {
                item["metric_name"]: item for item in extract_framework(handoff_path)["metrics"]
            }
            self.assertEqual(metrics["营业收入"]["status"], "SUCCESS")
            self.assertEqual(metrics["净利润"]["status"], "FAILED")
            self.assertEqual(metrics["净利润"]["status_scope"], "METRIC")
            self.assertEqual(metrics["客户留存率"]["status"], "UNMAPPED")
            self.assertEqual(metrics["门店数"]["status"], "NOT_APPLICABLE")

    def test_normalize_period_suffixes_bare_annual_year(self) -> None:
        self.assertEqual(normalize_period("2025"), "2025A")
        self.assertEqual(normalize_period(" 2025 "), "2025A")
        self.assertEqual(normalize_period("2025A"), "2025A")
        self.assertEqual(normalize_period("2026E"), "2026E")
        self.assertEqual(normalize_period("2026F"), "2026F")
        self.assertEqual(normalize_period("今年至今"), "今年至今")
        self.assertEqual(normalize_period("2026-09-30"), "2026-09-30")

    def test_bare_annual_headers_extract_as_actual_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            handoff_path, workbook_path, _ = create_fixture(Path(directory))
            workbook = load_workbook(workbook_path)
            for row in workbook["10_研报快照"].iter_rows():
                for cell in row:
                    if cell.value == "2025A":
                        cell.value = "2025"
            for row in workbook["30_预测框架"].iter_rows():
                for cell in row:
                    if cell.value == "2026F":
                        cell.value = "2026"
            workbook.save(workbook_path)
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            handoff["outputs"][0]["sha256"] = sha256_file(workbook_path)
            handoff["outputs"][0]["size_bytes"] = workbook_path.stat().st_size
            handoff_path.write_text(json.dumps(handoff, ensure_ascii=False), encoding="utf-8")
            metrics = {
                item["metric_name"]: item for item in extract_framework(handoff_path)["metrics"]
            }
            self.assertEqual(metrics["营业收入"]["periods"], ["2025A", "2026F"])
            self.assertEqual(metrics["EPS"]["periods"], ["2026A"])
            bare_years = [
                period
                for item in metrics.values()
                for period in item["periods"]
                if period.isdigit() and len(period) == 4
            ]
            self.assertEqual(bare_years, [])

    def test_rejects_changed_output_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            handoff_path, workbook_path, _ = create_fixture(Path(directory))
            workbook = load_workbook(workbook_path)
            workbook["00_导读"]["B2"] = "篡改"
            workbook.save(workbook_path)
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            handoff["outputs"][0]["size_bytes"] = workbook_path.stat().st_size
            handoff_path.write_text(json.dumps(handoff, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "hash mismatch"):
                extract_framework(handoff_path)

    def test_rejects_missing_core_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            handoff_path, workbook_path, _ = create_fixture(Path(directory))
            workbook = load_workbook(workbook_path)
            del workbook["90_执行日志"]
            workbook.save(workbook_path)
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            handoff["outputs"][0]["sha256"] = sha256_file(workbook_path)
            handoff["outputs"][0]["size_bytes"] = workbook_path.stat().st_size
            handoff_path.write_text(json.dumps(handoff, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "missing core sheets"):
                extract_framework(handoff_path)

    def test_requires_confirmed_stage_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            handoff_path, _, _ = create_fixture(Path(directory))
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            handoff["status"] = "PASS_WAITING_CONFIRMATION"
            handoff_path.write_text(json.dumps(handoff, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "must be CONFIRMED"):
                extract_framework(handoff_path)

    def test_latest_metric_log_status_wins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            handoff_path, workbook_path, _ = create_fixture(Path(directory))
            workbook = load_workbook(workbook_path)
            log = workbook["90_执行日志"]
            log.append(
                [
                    "净利润",
                    "MQL",
                    "MQL_TOOLCHAIN",
                    "#1",
                    "run-3",
                    "2026-10-03T10:05:00+08:00",
                    "Choice\\财务\\净利润",
                    "SUCCESS",
                    "2x3",
                    "",
                    "亿元",
                    "",
                    "",
                    hashlib.sha256(b"profit-success").hexdigest(),
                ]
            )
            workbook.save(workbook_path)
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            handoff["outputs"][0]["sha256"] = sha256_file(workbook_path)
            handoff["outputs"][0]["size_bytes"] = workbook_path.stat().st_size
            handoff_path.write_text(json.dumps(handoff, ensure_ascii=False), encoding="utf-8")
            metrics = {
                item["metric_name"]: item for item in extract_framework(handoff_path)["metrics"]
            }
            self.assertEqual(metrics["净利润"]["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
