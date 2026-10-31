"""Regression tests for the 2026-10-12 contract relaxation (R1 / R2).

R1: any really-executed MQL script (incl. server-side 服务端/妙想 report paths) may enter
    20_研报底稿 as an =mql() anchor; the excel_refresh_compatible / server-path gate is gone.
R2: every snapshot keeps a position in 20_研报底稿: SUCCESS (FULL/PARTIAL) writes =mql();
    a fully unqueryable table is emitted as TABLE_BLOCKED (status + reason, no formula),
    which still satisfies the per-snapshot coverage gate.

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


def _snapshot(table_id, name, headers, rows, sem, row_axis, col_axis, qfields, layout_group):
    t = prepare_workbook_phases.normalize_table({
        "table_id": table_id, "table_name": name, "headers": headers, "rows": rows,
        "bbox": [10.0, 10.0, 500.0, 400.0], "source_semantic_type": sem,
    })
    t.update(page=1, layout_group=layout_group, lane="main", reading_order=1,
             layout_contract_reason="rows are records; columns are fields",
             source_row_axis=row_axis, source_column_axis=col_axis, source_semantic_type=sem,
             source_period_basis="REPORTING_PERIOD", queryable_fields=qfields, is_visual_object=False,
             bbox=[0.0, 0.0, 1.0, 1.0], row_bboxes=[[0.0, 0.0, 1.0, 1.0] for _ in rows],
             source_status="PASS", visual_check="PASS")
    return t


def _payload():
    s1 = _snapshot("p1-t1", "估值指标", ["EM_CODE", "总市值(百万元)"],
                   [["002594.SZ", "804136.8"]], "CROSS_SECTION_TABLE",
                   "ENTITY", "METRIC", ["总市值(百万元)"], "g1")
    s2 = _snapshot("p1-t2", "评级与目标价", ["项目", "值"],
                   [["评级", "买入"], ["目标价", "20.5"]], "OTHER",
                   "CATEGORY", "METRIC", ["评级", "目标价"], "g2")

    # R1: a successful MQL script that contains a server-side 服务端/妙想 path.
    script = 'CrossSectionBlock(#1,{EM_CODE});\n{总市值(百万元)}: X("服务端\\妙想服务\\F10_估值");'
    raw = [["EM_CODE", "总市值(百万元)"], ["002594.SZ", 804136.8]]
    src_fields = ["总市值(百万元)"]
    w_success = {
        "source_type": "TABLE", "source_id": "p1-t1", "mapping_id": "table:p1-t1:ind",
        "execution_status": "SUCCESS", "data_source": "MQL", "mapping_status": "FULL",
        "mapping_note": "含服务端妙想路径，R1 放开后允许进入 20 研报底稿",
        "source_semantic_type": "CROSS_SECTION_TABLE", "query_interface": "Choice指标",
        "data_path_type": "INDICATOR", "mql_script": script, "block_selector": "#1",
        "mql_orientation": 0, "orientation_reason": "保持原始方向", "result_as_of": "2026-10-12",
        "result_origin": "MQL_TOOLCHAIN", "script_sha256": _sha(script), "execution_run_id": "run-w1",
        "queried_at": "2026-10-12T10:00:00+08:00", "raw_result": raw, "last_result": [r[:] for r in raw],
        "cached_table": [r[:] for r in raw], "query_shape": "CROSS_SECTION",
        "target_row_axis": "ENTITY", "target_column_axis": "METRIC",
        "row_axis_labels": ["002594.SZ"], "column_axis_labels": ["总市值(百万元)"],
        "display_label_map": [{"key": "002594.SZ", "display_name": "比亚迪", "kind": "ENTITY"}],
        "source_fields": src_fields, "covered_fields": src_fields, "omitted_fields": [],
        "script_output_fields": src_fields, "source_periods": [], "covered_periods": [],
        "omitted_periods": [], "expected_rows": 2, "expected_columns": 2,
        "unit_contracts": [{"field": "总市值(百万元)", "value_type": "NUMBER", "source_unit": "百万元",
                            "display_unit": "百万元", "scale_factor": 1,
                            "source_semantics": "ABSOLUTE", "display_semantics": "ABSOLUTE"}],
    }
    # R2: a fully unqueryable table keeps its position as TABLE_BLOCKED (no formula).
    w_blocked = {
        "source_type": "TABLE", "source_id": "p1-t2", "mapping_id": "table:p1-t2:blocked",
        "execution_status": "TABLE_BLOCKED", "mapping_status": "TABLE_BLOCKED",
        "data_source": "MQL", "query_interface": "Choice指标", "expected_rows": 1,
        "expected_columns": 1, "source_semantic_type": "OTHER",
        "block_reason": "评级与目标价为券商主观判断，无对应 MQL 可查口径",
        "mapping_note": "整表不可查，保留位置", "source_periods": [], "covered_periods": [],
        "omitted_periods": [], "source_fields": ["评级", "目标价"], "covered_fields": [],
        "omitted_fields": [
            {"field": "评级", "reason": "主观评级，不可查", "evidence_ids": ["att-p1t2-rating"]},
            {"field": "目标价", "reason": "主观目标价，不可查", "evidence_ids": ["att-p1t2-target"]},
        ],
    }
    exec_log = [{
        "attempt_id": "run-w1", "source_id": "p1-t1", "data_source": "MQL", "data_path_type": "INDICATOR",
        "status": "SUCCESS", "metric": "总市值(百万元)", "source_block": "#1",
        "query_path": "服务端\\妙想服务\\F10_估值", "execution_run_id": "run-w1",
        "queried_at": "2026-10-12T10:00:00+08:00", "raw_result_summary": "1x1", "unit": "百万元",
        "script_sha256": _sha(script),
    }, {
        "attempt_id": "att-p1t2-rating", "source_id": "p1-t2", "data_source": "MQL",
        "data_path_type": "INDICATOR", "status": "NO_DATA",
        "failure_category": "NO_CANDIDATE_AFTER_SEARCH", "metric": "评级", "source_block": "#1",
        "query_path": "-", "queried_at": "2026-10-12T10:00:00+08:00",
        "raw_result_summary": "无候选", "unit": "-",
    }, {
        "attempt_id": "att-p1t2-target", "source_id": "p1-t2", "data_source": "MQL",
        "data_path_type": "INDICATOR", "status": "NO_DATA",
        "failure_category": "NO_CANDIDATE_AFTER_SEARCH", "metric": "目标价", "source_block": "#1",
        "query_path": "-", "queried_at": "2026-10-12T10:00:00+08:00",
        "raw_result_summary": "无候选", "unit": "-",
    }]
    return {
        "guide": {"company_name": "测试", "security_code": "002594.SZ", "report_title": "t",
                  "report_date": "2026-09-16", "verification_date": "2026-10-12",
                  "pdf_page_count": 1, "census_table_count": 2, "visual_object_count": 0},
        "snapshots": [s1, s2], "excluded_tables": [], "chart_snapshots": [], "chart_data": [],
        "workpapers": [w_success, w_blocked], "verification": [], "execution_log": exec_log,
        "forecast": {"revenue_forecast": []},
    }


class RelaxedContractTests(unittest.TestCase):
    def test_server_path_mql_and_blocked_position_pass_validation(self):
        # Would have raised "server-only MiaoXiang paths cannot be placed..." before R1,
        # and would have failed the coverage gate without a TABLE_BLOCKED workpaper before R2.
        build_workbook.validate_payload(_payload())

    def test_server_path_writes_mql_and_blocked_keeps_position(self):
        from openpyxl import Workbook
        payload = _payload()
        workbook = Workbook()
        workbook.active.title = "00_导读"
        build_workbook.build_workpaper_sheet(workbook, payload["snapshots"], payload["workpapers"], [])
        ws = workbook["20_研报底稿"]
        formulas = [c for row in ws.iter_rows() for c in row
                    if isinstance(c.value, str) and c.value.startswith("=mql")]
        self.assertEqual(len(formulas), 1)
        self.assertIn("妙想", formulas[0].comment.text)  # server-side path kept in the anchor
        blocked = [c.value for row in ws.iter_rows() for c in row
                   if isinstance(c.value, str) and "TABLE_BLOCKED" in c.value]
        self.assertTrue(blocked)


if __name__ == "__main__":
    unittest.main()
