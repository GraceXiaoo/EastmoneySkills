"""Regression tests for the declared reporting-period structural key and the
financial-source OTHER anchor exemption (2026-10-19).

真实引擎实证：ReportBlock/MergeBlock 只有脚本公开声明 `{报告期}: ...` 才返回期间列；
声明后「报告期」被解析为输出别名，令财务表陷入二律背反（声明则别名比对失败，
不声明则无期间列、期间映射无附着点）。本次修订：
1. `target_column_axis=REPORTING_PERIOD` 的 workpaper 中，脚本公开声明的「报告期」
   列视为结构键：计入 raw_result 表头与 REPORTING_PERIOD 映射 key，但不计入
   script_output_fields / covered_fields / unit_contracts 的业务别名比对。
2. 财务来源（FINANCIAL_STATEMENT/FINANCIAL_METRICS）拆出的非财务形态锚点
   （如估值截面 ENTITY×METRIC）允许登记 source_semantic_type=OTHER；仅降级方向，
   且轴不得仍为 FINANCIAL_METRIC×REPORTING_PERIOD。

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


METRICS = ["货币资金", "应收账款"]
PERIODS = ["2025A"]
PERIOD_KEY = "2025-12-31 00:00:00"
VALUATION_METRIC = "正常化摊薄市盈率(倍)"

BS_SCRIPT = (
    'ReportBlock(#1,{Choice报表\\报表指标\\服务端\\妙想服务\\API查数\\基本面\\F10_财务分析_资产负债表_通用|747950456281025});\n'
    'SetCodes(["300308.SZ"]);\n'
    '{报告期}: REPORT_FIELD("报告期");\n'
    '{货币资金}: REPORT_FIELD("货币资金");\n'
    '{应收账款}: REPORT_FIELD("应收账款");\n'
    'OutputBlock();'
)

CS_SCRIPT = (
    'CrossSectionBlock(#1,{EM_CODE});\n'
    'SetCodes(["300308.SZ"]);\n'
    '{正常化摊薄市盈率(倍)}: {Choice指标\\股票\\沪深京股票指标\\估值指标\\市盈率PE(TTM)|100000000004742}({交易日期}="2026-07-31");\n'
    'OutputBlock();'
)


def _fin_snapshot(semantic, fields, values):
    table = prepare_workbook_phases.normalize_table({
        "table_id": "p1-t1", "table_name": "财务摘要", "headers": ["EM_DATE"] + list(PERIODS),
        "rows": [[name, value] for name, value in zip(fields, values)],
        "bbox": [10.0, 10.0, 500.0, 400.0], "source_semantic_type": semantic,
    })
    table.update(page=1, layout_group="g1", lane="main", reading_order=1,
                 layout_contract_reason="rows are financial metrics; columns are reporting periods",
                 header_kinds=["OTHER"] + ["ACTUAL"] * len(PERIODS),
                 source_row_axis="FINANCIAL_METRIC", source_column_axis="REPORTING_PERIOD",
                 source_semantic_type=semantic, source_period_basis="REPORTING_PERIOD",
                 source_periods=list(PERIODS), queryable_fields=list(fields), is_visual_object=False,
                 bbox=[0.0, 0.0, 1.0, 1.0],
                 row_bboxes=[[0.0, 0.0, 1.0, 1.0] for _ in fields],
                 source_status="PASS", visual_check="PASS")
    return table


def _other_snapshot():
    table = prepare_workbook_phases.normalize_table({
        "table_id": "p1-t1", "table_name": "估值对比表", "headers": ["证券简称", VALUATION_METRIC],
        "rows": [["中际旭创", 70.58]],
        "bbox": [10.0, 10.0, 500.0, 400.0], "source_semantic_type": "OTHER",
    })
    table.update(page=1, layout_group="g1", lane="main", reading_order=1,
                 layout_contract_reason="rows are entities; columns are valuation metrics",
                 header_kinds=["OTHER", "OTHER"],
                 source_row_axis="ENTITY", source_column_axis="METRIC",
                 source_semantic_type="OTHER",
                 source_periods=[], queryable_fields=[VALUATION_METRIC], is_visual_object=False,
                 bbox=[0.0, 0.0, 1.0, 1.0],
                 row_bboxes=[[0.0, 0.0, 1.0, 1.0]],
                 source_status="PASS", visual_check="PASS")
    return table


def _report_workpaper(column_axis="REPORTING_PERIOD"):
    raw = [["报告期"] + METRICS, [PERIOD_KEY, 100, 50]]
    last = [["报告期", PERIOD_KEY], ["货币资金", 100], ["应收账款", 50]]
    return {
        "source_type": "TABLE", "source_id": "p1-t1", "mapping_id": "table:p1-t1:report",
        "execution_status": "SUCCESS", "data_source": "MQL", "mapping_status": "FULL",
        "mapping_note": "整表科目×报告期，报表路径整表直取",
        "source_semantic_type": "FINANCIAL_STATEMENT", "query_interface": "Choice指标",
        "data_path_type": "REPORT",
        "financial_query_mode": "REPORT_FULL_TABLE",
        "financial_query_mode_evidence": "整表科目×报告期全覆盖，报表路径整表直取（mql_templates/01）",
        "report_selection_reason": "整张财务表优先报表路径整表直取，科目名贴近研报口径",
        "mql_script": BS_SCRIPT, "block_selector": "#1",
        "mql_orientation": 1, "orientation_reason": "原始返回为报告期×科目，转置为科目×报告期",
        "result_as_of": "2026-10-19",
        "result_origin": "MQL_TOOLCHAIN", "script_sha256": _sha(BS_SCRIPT), "execution_run_id": "run-rep1",
        "queried_at": "2026-10-19T10:00:00+08:00",
        "raw_result": [row[:] for row in raw], "last_result": [row[:] for row in last],
        "cached_table": [row[:] for row in last],
        "query_shape": "REPORT_MATRIX",
        "target_row_axis": "FINANCIAL_METRIC", "target_column_axis": column_axis,
        "row_axis_labels": list(METRICS), "column_axis_labels": list(PERIODS),
        "display_label_map": [
            {"key": "货币资金", "display_name": "货币资金", "kind": "METRIC"},
            {"key": "应收账款", "display_name": "应收账款", "kind": "METRIC"},
            {"key": PERIOD_KEY, "display_name": "2025A", "kind": "REPORTING_PERIOD"},
        ],
        "source_fields": list(METRICS), "covered_fields": list(METRICS),
        "omitted_fields": [], "script_output_fields": list(METRICS),
        "source_periods": list(PERIODS), "covered_periods": list(PERIODS),
        "omitted_periods": [], "expected_rows": 3, "expected_columns": 2,
        "unit_contracts": [
            {"field": name, "value_type": "NUMBER", "source_unit": "元", "display_unit": "元",
             "scale_factor": 1, "source_semantics": "ABSOLUTE", "display_semantics": "ABSOLUTE"}
            for name in METRICS
        ],
    }


def _cross_section_workpaper(row_axis="ENTITY", column_axis="METRIC", semantic="OTHER"):
    raw = [["EM_CODE", VALUATION_METRIC], ["300308.SZ", 70.58]]
    return {
        "source_type": "TABLE", "source_id": "p1-t1", "mapping_id": "table:p1-t1:valuation",
        "execution_status": "SUCCESS", "data_source": "MQL", "mapping_status": "FULL",
        "mapping_note": "财务摘要来源拆出的估值截面锚点，单实体单指标",
        "source_semantic_type": semantic, "query_interface": "Choice指标",
        "data_path_type": "INDICATOR",
        "mql_script": CS_SCRIPT, "block_selector": "#1",
        "mql_orientation": 0, "orientation_reason": "原始返回已为实体×指标的目标布局，无需转置",
        "result_as_of": "2026-10-19",
        "result_origin": "MQL_TOOLCHAIN", "script_sha256": _sha(CS_SCRIPT), "execution_run_id": "run-cs1",
        "queried_at": "2026-10-19T10:00:00+08:00",
        "raw_result": [row[:] for row in raw], "last_result": [row[:] for row in raw],
        "cached_table": [row[:] for row in raw],
        "query_shape": "CROSS_SECTION",
        "target_row_axis": row_axis, "target_column_axis": column_axis,
        "row_axis_labels": ["300308.SZ"], "column_axis_labels": [VALUATION_METRIC],
        "display_label_map": [
            {"key": "300308.SZ", "display_name": "中际旭创", "kind": "ENTITY"},
        ],
        "source_fields": [VALUATION_METRIC], "covered_fields": [VALUATION_METRIC],
        "omitted_fields": [], "script_output_fields": [VALUATION_METRIC],
        "source_periods": list(PERIODS), "covered_periods": list(PERIODS),
        "omitted_periods": [], "expected_rows": 2, "expected_columns": 2,
        "unit_contracts": [
            {"field": VALUATION_METRIC, "value_type": "NUMBER", "source_unit": "倍", "display_unit": "倍",
             "scale_factor": 1, "source_semantics": "DECIMAL_RATIO", "display_semantics": "DECIMAL_RATIO"},
        ],
    }


def _exec_log(*run_ids):
    entries = []
    for run_id in run_ids:
        script = BS_SCRIPT if run_id == "run-rep1" else CS_SCRIPT
        entries.append({
            "attempt_id": run_id, "source_id": "p1-t1", "data_source": "MQL",
            "data_path_type": "REPORT" if run_id == "run-rep1" else "INDICATOR",
            "status": "SUCCESS",
            "metric": "财务摘要整表" if run_id == "run-rep1" else VALUATION_METRIC,
            "source_block": "#1",
            "query_path": "服务端\\妙想服务\\F10_财务分析_资产负债表_通用" if run_id == "run-rep1" else "Choice指标\\股票\\沪深京股票指标\\估值指标\\市盈率PE(TTM)",
            "execution_run_id": run_id, "queried_at": "2026-10-19T10:00:00+08:00",
            "raw_result_summary": "2x3" if run_id == "run-rep1" else "2x2",
            "unit": "元" if run_id == "run-rep1" else "倍",
            "script_sha256": _sha(script),
        })
    return entries


def _payload(snapshot, workpapers, run_ids):
    return {
        "guide": {"company_name": "测试", "security_code": "300308.SZ", "report_title": "t",
                  "report_date": "2026-08-03", "verification_date": "2026-10-19",
                  "pdf_page_count": 1, "census_table_count": 1, "visual_object_count": 0},
        "snapshots": [snapshot], "excluded_tables": [], "chart_snapshots": [], "chart_data": [],
        "workpapers": workpapers,
        "verification": [], "execution_log": _exec_log(*run_ids),
        "forecast": {"revenue_forecast": []},
    }


class DeclaredPeriodKeyTests(unittest.TestCase):
    def test_declared_period_structural_key_passes(self):
        # 真实形态：脚本公开声明 {报告期}，raw 表头含「报告期」，业务别名仅两个科目。
        build_workbook.validate_payload(
            _payload(_fin_snapshot("FINANCIAL_STATEMENT", METRICS, (100, 50)), [_report_workpaper()], ["run-rep1"])
        )

    def test_structural_key_exemption_requires_reporting_period_axis(self):
        # target_column_axis 非 REPORTING_PERIOD 时结构键豁免不得生效：
        # 「报告期」仍是业务别名，script_output_fields 不含它即报字段比对错误。
        with self.assertRaises(ValueError) as ctx:
            build_workbook.validate_payload(
                _payload(
                    _fin_snapshot("FINANCIAL_STATEMENT", METRICS, (100, 50)),
                    [_report_workpaper(column_axis="METRIC")],
                    ["run-rep1"],
                )
            )
        self.assertIn("OUTPUT_FIELDS", str(ctx.exception))

    def test_financial_source_other_anchor_passes(self):
        # 财务摘要来源（FINANCIAL_METRICS）拆出的估值截面锚点允许登记 OTHER。
        build_workbook.validate_payload(
            _payload(
                _fin_snapshot("FINANCIAL_METRICS", [VALUATION_METRIC], (70.58,)),
                [_cross_section_workpaper()],
                ["run-cs1"],
            )
        )

    def test_other_anchor_with_financial_axes_rejected(self):
        # 降级 OTHER 但轴仍是 FINANCIAL_METRIC×REPORTING_PERIOD → 不享受豁免。
        with self.assertRaises(ValueError) as ctx:
            build_workbook.validate_payload(
                _payload(
                    _fin_snapshot("FINANCIAL_METRICS", [VALUATION_METRIC], (70.58,)),
                    [_cross_section_workpaper(row_axis="FINANCIAL_METRIC", column_axis="REPORTING_PERIOD")],
                    ["run-cs1"],
                )
            )
        self.assertIn("source_semantic_type must inherit", str(ctx.exception))

    def test_upgrade_to_financial_semantic_rejected(self):
        # 升级方向（快照 OTHER → workpaper 财务语义）不在豁免范围，必须拒绝。
        with self.assertRaises(ValueError) as ctx:
            build_workbook.validate_payload(
                _payload(_other_snapshot(), [_cross_section_workpaper(semantic="FINANCIAL_STATEMENT")], ["run-cs1"])
            )
        self.assertIn("source_semantic_type must inherit", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
