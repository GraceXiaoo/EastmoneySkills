"""Regression tests for the 2026-10-13 financial query-mode routing contract.

Scenario routing (裁决 2026-10-13):
- 整篇财报表格（科目 × 报告期全覆盖）优先报表路径整表直取：financial_query_mode=REPORT_FULL_TABLE,
  data_path_type=REPORT, no indicator failure evidence required (only report_selection_reason).
- 个别科目兜底仍走 REPORT_FALLBACK 并强制 indicator_attempt_ids 证据链。
- REPORT_FULL_TABLE 不允许搭配 INDICATOR 数据路径。

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
    'SetCodes(["600519.SH"]);\n'
    '{货币资金}: REPORT_FIELD("货币资金");\n'
    '{应收账款}: REPORT_FIELD("应收账款");\n'
    'OutputBlock();'
)

PERIODS = ["2025", "2024"]
METRICS = ["货币资金", "应收账款"]
RAW = [["EM_DATE"] + METRICS, ["2025", 100, 50], ["2024", 90, 40]]
LAST = [["EM_DATE"] + PERIODS, ["货币资金", 100, 90], ["应收账款", 50, 40]]


def _snapshot():
    t = prepare_workbook_phases.normalize_table({
        "table_id": "p1-t1", "table_name": "资产负债表", "headers": ["EM_DATE"] + PERIODS,
        "rows": [["货币资金", 100, 90], ["应收账款", 50, 40]],
        "bbox": [10.0, 10.0, 500.0, 400.0], "source_semantic_type": "FINANCIAL_STATEMENT",
    })
    t.update(page=1, layout_group="g1", lane="main", reading_order=1,
             layout_contract_reason="rows are financial metrics; columns are reporting periods",
             header_kinds=["OTHER", "ACTUAL", "ACTUAL"],
             source_row_axis="FINANCIAL_METRIC", source_column_axis="REPORTING_PERIOD",
             source_semantic_type="FINANCIAL_STATEMENT", source_period_basis="REPORTING_PERIOD",
             source_periods=list(PERIODS), queryable_fields=list(METRICS), is_visual_object=False,
             bbox=[0.0, 0.0, 1.0, 1.0], row_bboxes=[[0.0, 0.0, 1.0, 1.0] for _ in range(2)],
             source_status="PASS", visual_check="PASS")
    return t


def _workpaper():
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
        "result_as_of": "2026-10-13",
        "result_origin": "MQL_TOOLCHAIN", "script_sha256": _sha(BS_SCRIPT), "execution_run_id": "run-fin1",
        "queried_at": "2026-10-13T10:00:00+08:00",
        "raw_result": [r[:] for r in RAW], "last_result": [r[:] for r in LAST],
        "cached_table": [r[:] for r in LAST],
        "query_shape": "REPORT_MATRIX",
        "target_row_axis": "FINANCIAL_METRIC", "target_column_axis": "REPORTING_PERIOD",
        "row_axis_labels": list(METRICS), "column_axis_labels": list(PERIODS),
        "display_label_map": [
            {"key": "货币资金", "display_name": "货币资金", "kind": "METRIC"},
            {"key": "应收账款", "display_name": "应收账款", "kind": "METRIC"},
        ],
        "source_fields": list(METRICS), "covered_fields": list(METRICS),
        "omitted_fields": [], "script_output_fields": list(METRICS),
        "source_periods": list(PERIODS), "covered_periods": list(PERIODS),
        "omitted_periods": [], "expected_rows": 3, "expected_columns": 3,
        "unit_contracts": [
            {"field": "货币资金", "value_type": "NUMBER", "source_unit": "元", "display_unit": "元",
             "scale_factor": 1, "source_semantics": "ABSOLUTE", "display_semantics": "ABSOLUTE"},
            {"field": "应收账款", "value_type": "NUMBER", "source_unit": "元", "display_unit": "元",
             "scale_factor": 1, "source_semantics": "ABSOLUTE", "display_semantics": "ABSOLUTE"},
        ],
    }


def _exec_log():
    return [{
        "attempt_id": "run-fin1", "source_id": "p1-t1", "data_source": "MQL", "data_path_type": "REPORT",
        "status": "SUCCESS", "metric": "资产负债表整表", "source_block": "#1",
        "query_path": "服务端\\妙想服务\\F10_财务分析_资产负债表_通用", "execution_run_id": "run-fin1",
        "queried_at": "2026-10-13T10:00:00+08:00", "raw_result_summary": "3x3", "unit": "元",
        "script_sha256": _sha(BS_SCRIPT),
    }]


def _indicator_failure_attempts():
    return [
        {"attempt_id": "att-ind-cash", "source_id": "p1-t1", "data_source": "MQL",
         "data_path_type": "INDICATOR", "status": "NO_DATA", "failure_category": "NO_CANDIDATE_AFTER_SEARCH",
         "metric": "货币资金", "source_block": "#1", "query_path": "-",
         "queried_at": "2026-10-13T09:55:00+08:00", "raw_result_summary": "无候选", "unit": "-"},
        {"attempt_id": "att-ind-receive", "source_id": "p1-t1", "data_source": "MQL",
         "data_path_type": "INDICATOR", "status": "NO_DATA", "failure_category": "NO_CANDIDATE_AFTER_SEARCH",
         "metric": "应收账款", "source_block": "#1", "query_path": "-",
         "queried_at": "2026-10-13T09:55:00+08:00", "raw_result_summary": "无候选", "unit": "-"},
    ]


def _payload():
    return {
        "guide": {"company_name": "测试", "security_code": "600519.SH", "report_title": "t",
                  "report_date": "2026-09-16", "verification_date": "2026-10-13",
                  "pdf_page_count": 1, "census_table_count": 1, "visual_object_count": 0},
        "snapshots": [_snapshot()], "excluded_tables": [], "chart_snapshots": [], "chart_data": [],
        "workpapers": [_workpaper()], "verification": [], "execution_log": _exec_log(),
        "forecast": {"revenue_forecast": []},
    }


class ReportFullTableTests(unittest.TestCase):
    def test_report_full_table_passes_without_indicator_evidence(self):
        # 整表报表直取：只需 report_selection_reason，无需 indicator_attempt_ids 证据链。
        build_workbook.validate_payload(_payload())

    def test_report_full_table_rejected_with_indicator_data_path(self):
        payload = _payload()
        payload["workpapers"][0]["data_path_type"] = "INDICATOR"
        with self.assertRaises(ValueError) as ctx:
            build_workbook.validate_payload(payload)
        self.assertIn("INDICATOR data path", str(ctx.exception))

    def test_report_fallback_still_requires_evidence_chain(self):
        payload = _payload()
        wp = payload["workpapers"][0]
        wp["financial_query_mode"] = "REPORT_FALLBACK"
        with self.assertRaises(ValueError) as ctx:
            build_workbook.validate_payload(payload)
        self.assertIn("report_fallback_reason", str(ctx.exception))

    def test_report_fallback_with_evidence_chain_passes(self):
        payload = _payload()
        wp = payload["workpapers"][0]
        wp["financial_query_mode"] = "REPORT_FALLBACK"
        wp["report_fallback_reason"] = "INDICATOR_COVERAGE_INCOMPLETE"
        wp["indicator_attempt_ids"] = ["att-ind-cash", "att-ind-receive"]
        payload["execution_log"].extend(_indicator_failure_attempts())
        build_workbook.validate_payload(payload)


if __name__ == "__main__":
    unittest.main()
