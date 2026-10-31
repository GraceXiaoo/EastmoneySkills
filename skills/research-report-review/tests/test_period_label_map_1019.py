"""Regression tests for the reporting-period label mapping contract (U1, 2026-10-19).

研报财务表的期间列表头是研报标签（`2025A`），而 Choice 任何取数路径都返回不出 `YYYYA`
（报表块 `报告期` 返回 `2025-12-31 00:00:00`、时序块 `EM_DATE` 返回 `2025-12-31`）。
本契约把期间列纳入 `display_label_map`：`kind="REPORTING_PERIOD"` 条目的 `key` 记录真实
执行返回的取数标签，`display_name` 记录研报期间标签；`column_axis_labels` / `covered_periods`
仍使用研报标签，仅把「结果表头逐字相等」改为按映射条目逐列比对。

所有输入均为进程内合成的离线夹具：不调用外部服务，也不代表真实的工具调用记录。
"""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_workbook_phases  # noqa: E402
import build_workbook  # noqa: E402


def _sha(script: str) -> str:
    return hashlib.sha256(script.replace("\r\n", "\n").replace("\r", "\n").strip().encode("utf-8")).hexdigest()


BS_SCRIPT = (
    'ReportBlock(#1,{Choice报表\\报表指标\\服务端\\妙想服务\\API查数\\基本面\\F10_财务分析_资产负债表_通用|747950456281025});\n'
    'SetCodes(["300308.SZ"]);\n'
    '{货币资金}: REPORT_FIELD("货币资金");\n'
    '{应收账款}: REPORT_FIELD("应收账款");\n'
    'OutputBlock();'
)

REPORT_PERIODS = ["2025A", "2024A"]
RESULT_LABELS = ["2025-12-31", "2024-12-31"]
METRICS = ["货币资金", "应收账款"]


def _snapshot(periods):
    table = prepare_workbook_phases.normalize_table({
        "table_id": "p1-t1", "table_name": "资产负债表", "headers": ["EM_DATE"] + list(periods),
        "rows": [[name, *values] for name, values in zip(METRICS, [(100, 90), (50, 40)])],
        "bbox": [10.0, 10.0, 500.0, 400.0], "source_semantic_type": "FINANCIAL_STATEMENT",
    })
    table.update(page=1, layout_group="g1", lane="main", reading_order=1,
                 layout_contract_reason="rows are financial metrics; columns are reporting periods",
                 header_kinds=["OTHER"] + ["ACTUAL"] * len(periods),
                 source_row_axis="FINANCIAL_METRIC", source_column_axis="REPORTING_PERIOD",
                 source_semantic_type="FINANCIAL_STATEMENT", source_period_basis="REPORTING_PERIOD",
                 source_periods=list(periods), queryable_fields=list(METRICS), is_visual_object=False,
                 bbox=[0.0, 0.0, 1.0, 1.0],
                 row_bboxes=[[0.0, 0.0, 1.0, 1.0] for _ in METRICS],
                 source_status="PASS", visual_check="PASS")
    return table


def _display_label_map(periods, result_labels, with_mapping):
    label_map = [{"key": name, "display_name": name, "kind": "METRIC"} for name in METRICS]
    if with_mapping:
        label_map.extend(
            {"key": result_label, "display_name": period, "kind": "REPORTING_PERIOD"}
            for result_label, period in zip(result_labels, periods)
        )
    return label_map


def _workpaper(periods, result_labels, with_mapping):
    raw = [["EM_DATE"] + METRICS, [result_labels[0], 100, 50], [result_labels[1], 90, 40]]
    last = [["EM_DATE"] + list(result_labels), ["货币资金", 100, 90], ["应收账款", 50, 40]]
    return {
        "source_type": "TABLE", "source_id": "p1-t1", "mapping_id": "table:p1-t1:report",
        "execution_status": "SUCCESS", "data_source": "MQL", "mapping_status": "FULL",
        "mapping_note": "整篇资产负债表，按整表报表直取",
        "source_semantic_type": "FINANCIAL_STATEMENT", "query_interface": "Choice指标",
        "data_path_type": "REPORT",
        "financial_query_mode": "REPORT_FULL_TABLE",
        "financial_query_mode_evidence": "整表科目×报告期全覆盖，报表路径整表直取（mql_templates/01）",
        "report_selection_reason": "整张资产负债表优先报表路径整表直取，科目名贴近研报口径",
        "mql_script": BS_SCRIPT, "block_selector": "#1",
        "mql_orientation": 1, "orientation_reason": "原始返回为报告期×科目，转置为科目×报告期",
        "result_as_of": "2026-10-19",
        "result_origin": "MQL_TOOLCHAIN", "script_sha256": _sha(BS_SCRIPT), "execution_run_id": "run-fin1",
        "queried_at": "2026-10-19T10:00:00+08:00",
        "raw_result": raw, "last_result": last, "cached_table": last,
        "query_shape": "REPORT_MATRIX",
        "target_row_axis": "FINANCIAL_METRIC", "target_column_axis": "REPORTING_PERIOD",
        "row_axis_labels": list(METRICS), "column_axis_labels": list(periods),
        "display_label_map": _display_label_map(periods, result_labels, with_mapping),
        "source_fields": list(METRICS), "covered_fields": list(METRICS),
        "omitted_fields": [], "script_output_fields": list(METRICS),
        "source_periods": list(periods), "covered_periods": list(periods),
        "omitted_periods": [], "expected_rows": 3, "expected_columns": 3,
        "unit_contracts": [
            {"field": name, "value_type": "NUMBER", "source_unit": "元", "display_unit": "元",
             "scale_factor": 1, "source_semantics": "ABSOLUTE", "display_semantics": "ABSOLUTE"}
            for name in METRICS
        ],
    }


def _exec_log():
    return [{
        "attempt_id": "run-fin1", "source_id": "p1-t1", "data_source": "MQL", "data_path_type": "REPORT",
        "status": "SUCCESS", "metric": "资产负债表整表", "source_block": "#1",
        "query_path": "服务端\\妙想服务\\F10_财务分析_资产负债表_通用", "execution_run_id": "run-fin1",
        "queried_at": "2026-10-19T10:00:00+08:00", "raw_result_summary": "3x3", "unit": "元",
        "script_sha256": _sha(BS_SCRIPT),
    }]


def _payload(periods=REPORT_PERIODS, result_labels=RESULT_LABELS, with_mapping=True):
    return {
        "guide": {"company_name": "测试", "security_code": "300308.SZ", "report_title": "t",
                  "report_date": "2026-08-03", "verification_date": "2026-10-19",
                  "pdf_page_count": 1, "census_table_count": 1, "visual_object_count": 0},
        "snapshots": [_snapshot(periods)], "excluded_tables": [], "chart_snapshots": [], "chart_data": [],
        "workpapers": [_workpaper(periods, result_labels, with_mapping)],
        "verification": [], "execution_log": _exec_log(),
        "forecast": {"revenue_forecast": []},
    }


class PeriodLabelMapTests(unittest.TestCase):
    def test_period_mapping_passes(self):
        # 研报标签 2025A 与取数标签 2025-12-31 由 REPORTING_PERIOD 条目分别承载。
        build_workbook.validate_payload(_payload())

    def test_period_mismatch_without_mapping_rejected(self):
        # 缺映射时回退到原有逐字比对，必须失败并提示补齐映射。
        with self.assertRaises(ValueError) as ctx:
            build_workbook.validate_payload(_payload(with_mapping=False))
        self.assertIn("column_axis_labels", str(ctx.exception))
        self.assertIn("REPORTING_PERIOD entries", str(ctx.exception))

    def test_period_mapping_count_mismatch_rejected(self):
        payload = _payload()
        payload["workpapers"][0]["display_label_map"].append(
            {"key": "2023-12-31", "display_name": "2023A", "kind": "REPORTING_PERIOD"}
        )
        with self.assertRaises(ValueError) as ctx:
            build_workbook.validate_payload(payload)
        self.assertIn("period columns", str(ctx.exception))

    def test_period_key_must_equal_executed_result_header(self):
        payload = _payload()
        payload["workpapers"][0]["display_label_map"][2]["key"] = "2025-06-30"
        with self.assertRaises(ValueError) as ctx:
            build_workbook.validate_payload(payload)
        self.assertIn("period headers", str(ctx.exception))

    def test_period_display_name_must_be_period_label(self):
        payload = _payload()
        payload["workpapers"][0]["display_label_map"][3]["display_name"] = "营业总收入"
        with self.assertRaises(ValueError) as ctx:
            build_workbook.validate_payload(payload)
        self.assertIn("period display names", str(ctx.exception))

    def test_period_entries_require_reporting_period_axis(self):
        payload = _payload()
        payload["workpapers"][0]["target_column_axis"] = "SERIES"
        with self.assertRaises(ValueError) as ctx:
            build_workbook.validate_payload(payload)
        self.assertIn("REPORTING_PERIOD", str(ctx.exception))

    def test_identity_period_labels_still_pass(self):
        # 结果表头与研报标签字面相同时无需映射，保持既有行为不变。
        build_workbook.validate_payload(
            _payload(periods=["2025A", "2024A"], result_labels=["2025A", "2024A"], with_mapping=False)
        )


if __name__ == "__main__":
    unittest.main()
