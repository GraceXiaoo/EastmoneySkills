"""Regression tests for the research-report workbook pipeline.

All inputs in this module are synthetic offline fixtures built in-process: they
never call an external service and carry no real tool-invocation record. Do not
treat their timestamps or execution records as production evidence.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import call_pdf_layout
import financial_workpaper_factory
import structured_mql_factory
import prepare_workbook_phases
import preflight_workbook_input
import research_report_pipeline
import source_coverage_compiler


ENVIRONMENT_KEY_BASE_URL = "EM_BASE_URL"


def _environment_without_base_url() -> dict:
    """Copy the process environment without `EM_BASE_URL` so gateway tests stay isolated."""
    return {key: value for key, value in os.environ.items() if key != ENVIRONMENT_KEY_BASE_URL}


class PdfGatewayRegressionTests(unittest.TestCase):
    def test_environment_base_url_is_not_mistaken_for_placeholder(self):
        with patch.object(call_pdf_layout, "EM_BASE_URL", "http://10.150.229.15:8900"):
            self.assertEqual(call_pdf_layout.resolve_base_url(), "http://10.150.229.15:8900")

    def test_build_replacement_does_not_rewrite_placeholder_sentinel(self):
        source = (ROOT / "scripts" / "call_pdf_layout.py").read_text(encoding="utf-8")
        built = source.replace("https://ai-saas.eastmoney.com", "http://10.150.229.15:8900")
        namespace = {"__name__": "packaged_call_pdf_layout"}
        with patch.dict(os.environ, _environment_without_base_url(), clear=True):
            exec(compile(built, "packaged_call_pdf_layout.py", "exec"), namespace)
        self.assertEqual(namespace["resolve_base_url"](), "http://10.150.229.15:8900")

    def test_local_environment_variable_takes_precedence_over_built_constant(self):
        source = (ROOT / "scripts" / "call_pdf_layout.py").read_text(encoding="utf-8")
        built = source.replace("https://ai-saas.eastmoney.com", "http://10.150.229.15:8900")
        namespace = {"__name__": "packaged_call_pdf_layout"}
        environment = _environment_without_base_url()
        environment["EM_BASE_URL"] = "http://127.0.0.1:9999"
        with patch.dict(os.environ, environment, clear=True):
            exec(compile(built, "packaged_call_pdf_layout.py", "exec"), namespace)
        self.assertEqual(namespace["resolve_base_url"](), "http://127.0.0.1:9999")

    def test_placeholder_is_rejected(self):
        with patch.object(call_pdf_layout, "EM_BASE_URL", call_pdf_layout.EM_BASE_URL_PLACEHOLDER):
            with self.assertRaises(ValueError):
                call_pdf_layout.resolve_base_url()


class EvidenceNormalizationRegressionTests(unittest.TestCase):
    def test_latest_filing_header_becomes_actual_period(self):
        source = {
            "table_id": "p1-t4", "table_name": "资产负债表摘要(LF)",
            "headers": ["项目", "LF"], "rows": [["现金", "1"]],
            "bbox": [0.1, 0.1, 0.9, 0.9], "source_semantic_type": "FINANCIAL_METRICS",
        }
        table = prepare_workbook_phases.normalize_table(source)
        self.assertEqual(table["header_kinds"], ["OTHER", "ACTUAL"])
        self.assertEqual(table["source_periods"], ["LF"])
        self.assertEqual(table["source_period_basis"], "LATEST_FILING")


class PreflightParityRegressionTests(unittest.TestCase):
    def test_final_validator_failure_prevents_preflight_pass(self):
        payload = {"guide": {"census_table_count": 0}, "snapshots": [], "excluded_tables": [], "chart_snapshots": [], "chart_data": [], "workpapers": [], "execution_log": []}
        def fail(_payload):
            raise ValueError("late build error")
        errors = preflight_workbook_input.collect_with_final_validation(payload, final_validator=fail)
        self.assertEqual(errors[0]["code"], "FINAL_VALIDATOR")
        self.assertIn("late build error", errors[0]["message"])


class NumericBodyValidityRegressionTests(unittest.TestCase):
    def test_all_null_value_body_is_rejected(self):
        import test_relaxed_contract_1012 as fixture
        import build_workbook

        payload = fixture._payload()
        workpaper = payload["workpapers"][0]
        nulled = [["EM_CODE", "总市值(百万元)"], ["002594.SZ", None]]  # 指标名非空、数值全 None
        workpaper["raw_result"] = [row[:] for row in nulled]
        workpaper["last_result"] = [row[:] for row in nulled]
        workpaper["cached_table"] = [row[:] for row in nulled]
        with self.assertRaisesRegex(ValueError, "data body"):
            build_workbook.validate_payload(payload)


class BlockedWorkpaperRegressionTests(unittest.TestCase):
    def test_table_blocked_status_is_accepted(self):
        spec = importlib.util.spec_from_file_location("build_workbook_for_status", ROOT / "scripts" / "build_workbook.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"openpyxl": MagicMock(), "openpyxl.comments": MagicMock(), "openpyxl.drawing.image": MagicMock(), "openpyxl.styles": MagicMock(), "openpyxl.utils": MagicMock(), "PIL": MagicMock(), "PIL.Image": MagicMock()}):
            spec.loader.exec_module(module)
        self.assertEqual(module.validate_workpaper_status({"execution_status": "TABLE_BLOCKED", "mapping_status": "TABLE_BLOCKED"}, "w"), ("TABLE_BLOCKED", "TABLE_BLOCKED"))


class ContinuousTimeSeriesBlockRegressionTests(unittest.TestCase):
    def test_edb_block_is_accepted_for_continuous_time_series(self):
        import build_workbook

        self.assertTrue(build_workbook.has_continuous_time_series_block("EdbBlock(#1,{EM_DATE});"))

    def test_time_series_block_remains_accepted(self):
        import build_workbook

        self.assertTrue(build_workbook.has_continuous_time_series_block("TimeSeriesBlock(#1,{EM_DATE},{EM_CODE});"))

    def test_cross_section_block_is_not_accepted(self):
        import build_workbook

        self.assertFalse(build_workbook.has_continuous_time_series_block("CrossSectionBlock(#1,{EM_CODE});"))

    def test_edb_workpaper_gets_an_isolated_sheet(self):
        import build_workbook
        from openpyxl import Workbook

        workbook = Workbook()
        workbook.active.title = "00_导读"
        snapshots = [{"table_id": "p1-t1", "table_name": "信用利差", "page": 1, "unit": "bp"}]
        workpapers = [{
            "source_type": "TABLE", "source_id": "p1-t1", "mapping_id": "table:p1-t1:edb",
            "execution_status": "SUCCESS", "data_source": "MQL", "mapping_status": "PARTIAL",
            "mapping_note": "原表为截面，直接提供已匹配 EDB 日度序列",
            "mql_script": "EdbBlock(#1,{EM_DATE});{国债1Y}: X();", "block_selector": "#1",
            "mql_orientation": 0, "last_result": [["EM_DATE", "国债1Y"], ["2026-09-30", 1.2]],
        }]
        build_workbook.build_workpaper_sheet(workbook, snapshots, workpapers, [])

        self.assertIn("21_EDB_001", workbook.sheetnames)
        self.assertFalse(any(
            isinstance(cell.value, str) and cell.value.startswith("=mql")
            for row in workbook["20_研报底稿"].iter_rows() for cell in row
        ))
        edb_formulas = [
            cell for row in workbook["21_EDB_001"].iter_rows() for cell in row
            if isinstance(cell.value, str) and cell.value.startswith("=mql")
        ]
        self.assertEqual(len(edb_formulas), 1)
        self.assertEqual(edb_formulas[0].comment.text, workpapers[0]["mql_script"])
        self.assertTrue(all(
            cell.value is None
            for row in workbook["21_EDB_001"].iter_rows(min_row=edb_formulas[0].row + 1)
            for cell in row
        ))


class FinancialFactoryTests(unittest.TestCase):
    def test_generates_independent_block_and_unit_transforms(self):
        catalog = json.loads((ROOT / "reference" / "a_share_financial_timeseries_core.json").read_text(encoding="utf-8"))
        spec = {
            "security_code": "002594.SZ", "start_date": "2024-01-01", "end_date": "2025-12-31", "period": "年",
            "metrics": [
                {"cache_key": "balance_sheet.货币资金", "field": "货币资金", "display_unit": "百万元"},
                {"cache_key": "financial_ratio.销售毛利率", "field": "销售毛利率", "display_unit": "%"},
                {"cache_key": "financial_ratio.净资产收益率ROE(摊薄)", "field": "ROE", "display_unit": "%"},
            ],
        }
        plan = financial_workpaper_factory.generate(spec, catalog)
        self.assertEqual(plan["mql_script"].count("TimeSeriesBlock("), 1)
        self.assertIn("TimeSeriesBlock(#1", plan["mql_script"])
        self.assertIn("/ 1000000", plan["mql_script"])
        self.assertIn("* 100", plan["mql_script"])
        roe = next(value for value in plan["unit_contracts"] if value["field"] == "ROE")
        self.assertEqual(roe["scale_factor"], 1)
        self.assertIsNone(roe["script_transform_token"])

    def test_assembles_runtime_matrix_without_manual_copying(self):
        runtime = {"ok": True, "traceparent": "run-1", "result": {"blocks": [{"columns": ["EM_DATE", "EM_CODE", "货币资金"], "rows": [{"EM_DATE": "2025-12-31", "EM_CODE": "002594.SZ", "货币资金": 10}]}]}}
        run_id, matrix = financial_workpaper_factory.runtime_matrix(runtime)
        self.assertEqual(run_id, "run-1")
        self.assertEqual(matrix, [["EM_DATE", "EM_CODE", "货币资金"], ["2025-12-31", "002594.SZ", 10]])


    def test_current_response_keeps_visible_date_and_first_metric(self):
        runtime = {"ok": True, "traceparent": "actual-trace", "result": {"blocks": [{
            "columns": ["EM_CODE", "EM_DATE", "收入"],
            "column_schema": [{"name": "EM_CODE", "hidden_key": True}, {"name": "EM_DATE", "hidden_key": False}, {"name": "收入", "hidden_key": False}],
            "rows": [{"EM_CODE": "security", "EM_DATE": "2025-12-31", "收入": 12}]}]}}
        before = json.dumps(runtime)
        run_id, matrix = financial_workpaper_factory.runtime_matrix(runtime, {"mql": "actual script"}, "actual script")
        self.assertEqual(run_id, "actual-trace")
        self.assertEqual(matrix, [["EM_DATE", "收入"], ["2025-12-31", 12]])
        self.assertEqual(json.dumps(runtime), before)
        with self.assertRaises(ValueError):
            financial_workpaper_factory.runtime_matrix(runtime, {"mql": "actual script"}, "changed script")
        with self.assertRaises(ValueError):
            financial_workpaper_factory.runtime_matrix({**runtime, "ok": False})
        with self.assertRaises(ValueError):
            financial_workpaper_factory.runtime_matrix({**runtime, "result": {"blocks": runtime["result"]["blocks"] * 2}})


    def test_service_fallback_cannot_use_pending_or_abandoned_calls(self):
        import build_workbook
        item={"fallback_from_mql": True, "mql_failure_category": "SERVICE_FAILURE_CONFIRMED",
              "mql_failure_evidence": "raw-error.json", "mql_service_failure": {
                  "status": "FAILED", "failure_type": "HTTP_5XX", "tool_call_id": "actual-call", "evidence_locator": "raw-error.json"}}
        build_workbook.validate_mql_fallback(item, "test")
        for status in ("PENDING", "IN_PROGRESS", "ABANDONED"):
            item["mql_service_failure"]["status"] = status
            with self.assertRaises(ValueError):
                build_workbook.validate_mql_fallback(item, "test")
        item["mql_service_failure"]["status"] = "FAILED"
        item["mql_service_failure"]["failure_type"] = "SYNTAX_ERROR"
        with self.assertRaises(ValueError):
            build_workbook.validate_mql_fallback(item, "test")


class EquityReportRegressionFixtureTests(unittest.TestCase):
    """The failure fixture is not an approved golden case."""
    def setUp(self):
        self.core=json.loads((ROOT/"reference"/"a_share_financial_timeseries_core.json").read_text(encoding="utf-8"))
        self.rules=json.loads((ROOT/"reference"/"derived_metric_formulas.json").read_text(encoding="utf-8"))

    def test_debt_to_equity_is_not_silently_aliased_to_equity_ratio(self):
        self.assertNotIn("债务权益比", self.rules["aliases"])
        result = source_coverage_compiler.compile_fields(["债务权益比"], self.core, self.rules)
        self.assertEqual(result["coverage_status"], "PARTIAL")
        self.assertEqual(result["unresolved_fields"], [{
            "field": "债务权益比", "reason": "NO_DIRECT_ALIAS_OR_FORMULA", "required_action": "MQL_TOOLCHAIN",
        }])

    def test_basic_and_latest_share_diluted_eps_stay_distinct(self):
        fields = ["每股净收益(元)", "EPS-最新股本摊薄(元)"]
        result = source_coverage_compiler.compile_fields(fields, self.core, self.rules)
        keys = [metric.get("cache_key") for metric in result["metrics"]]
        self.assertEqual(keys, ["per_share.每股收益EPS(基本)", "per_share.每股收益EPS(最新股本摊薄)"])
        self.assertEqual(len(set(keys)), 2)

    def test_ratio_aliases_do_not_route_to_missing_cache_entries(self):
        for name in ("产权比率", "净负债率", "净资产负债率"):
            self.assertNotIn(name, self.rules["aliases"])
        fields = ["产权比率", "净负债率", "净资产负债率"]
        result = source_coverage_compiler.compile_fields(fields, self.core, self.rules)
        self.assertEqual(result["coverage_status"], "PARTIAL")
        self.assertEqual([item["field"] for item in result["unresolved_fields"]], fields)
        self.assertTrue(all(item["required_action"] == "MQL_TOOLCHAIN" for item in result["unresolved_fields"]))

    def test_statement_rows_compile_direct_and_derived_metrics(self):
        fields=["货币资金","交易性金融资产","其他流动资产","无形资产及商誉","其他归母股东权益"]
        result=source_coverage_compiler.compile_fields(fields,self.core,self.rules,"百万元")
        self.assertEqual(result["coverage_status"],"FULL")
        self.assertEqual(result["covered_fields"],fields)
        self.assertEqual([x["kind"] for x in result["metrics"]][-2:],["DERIVED","DERIVED"])

    def test_cashflow_and_income_derived_rows_are_not_dropped(self):
        fields=["折旧与摊销","营运资本变动","减值损失","资产处置损益","营业外收支"]
        result=source_coverage_compiler.compile_fields(fields,self.core,self.rules,"百万元")
        self.assertEqual(result["unresolved_fields"],[])

    def test_summary_compiles_only_its_own_fields(self):
        fields=["营业总收入","净利润(归母)","每股净收益(元)","净资产收益率(%)"]
        compiled=source_coverage_compiler.compile_fields(fields,self.core,self.rules)
        spec={"security_code":"002594.SZ","start_date":"2024-01-01","end_date":"2025-12-31","source_fields":fields,"metrics":compiled["metrics"]}
        plan=financial_workpaper_factory.generate(spec,self.core)
        self.assertEqual(plan["script_output_fields"],fields)
        self.assertNotIn("{营业成本}:",plan["mql_script"])

    def test_table_unit_does_not_overwrite_mixed_field_units(self):
        fields=["营业总收入","每股净收益(元)","净资产收益率(%)"]
        compiled=source_coverage_compiler.compile_fields(fields,self.core,self.rules,"百万元")
        self.assertEqual([x["display_unit"] for x in compiled["metrics"]],["百万元","元/股","%"])

    def test_cross_market_comparable_requires_separate_plans(self):
        with self.assertRaises(ValueError):
            structured_mql_factory.generate({"query_shape":"CROSS_SECTION","split_by_market":True,"markets":["CN","HK"],"codes":["601633.SH","02015.HK"],"fields":[{"field":"收盘价","indicator_path":"verified/path"}]})

    def test_unlisted_structured_domain_still_generates_mql(self):
        plan=structured_mql_factory.generate({"query_shape":"TIME_SERIES","domain":"CUSTOM_OPERATIONAL_METRIC","codes":["ENTITY-1"],"start_date":"2025-01-01","end_date":"2025-12-31","period":"月","fields":[{"field":"自定义指标","indicator_path":"verified/custom/path"}]})
        self.assertIn("TimeSeriesBlock(#1",plan["mql_script"])
        self.assertEqual(plan["structured_domain"],"CUSTOM_OPERATIONAL_METRIC")

    def test_pipeline_rejects_script_reuse_across_sources(self):
        payload={"workpapers":[{"source_id":"p1-t2","script_sha256":"same"},{"source_id":"p2-t3","script_sha256":"same"}]}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"input.json"; path.write_text(json.dumps(payload),encoding="utf-8")
            with self.assertRaises(ValueError): research_report_pipeline.audit(path)


class DynamicEndMarkerFactoryTests(unittest.TestCase):
    def test_structured_factory_emits_unquoted_now_marker(self):
        plan = structured_mql_factory.generate({"query_shape": "TIME_SERIES", "codes": ["600519.SH"], "start_date": "2025-01-01", "end_date": "N()", "period": "日", "fields": [{"field": "收盘价", "indicator_path": "verified/price/path"}]})
        self.assertIn("{结束时间} = N()", plan["mql_script"])
        self.assertNotIn('"N()"', plan["mql_script"])
        self.assertEqual(plan["query_end_date_dynamic"], "N()")

    def test_structured_factory_emits_unquoted_mrq_for_reporting_period_paths(self):
        plan = structured_mql_factory.generate({"query_shape": "TIME_SERIES", "codes": ["600519.SH"], "start_date": "2023-12-31", "end_date": "MRQ()", "period": "季", "fields": [{"field": "每股收益EPS", "indicator_path": "Choice指标/序列函数/每股收益EPS(基本)|100000000002934_s"}]})
        self.assertIn("{结束时间} = MRQ()", plan["mql_script"])
        self.assertEqual(plan["query_end_date_dynamic"], "MRQ()")

    def test_structured_factory_rejects_mrq_for_ordinary_paths(self):
        with self.assertRaises(ValueError):
            structured_mql_factory.generate({"query_shape": "TIME_SERIES", "codes": ["600519.SH"], "start_date": "2023-12-31", "end_date": "MRQ()", "period": "日", "fields": [{"field": "收盘价", "indicator_path": "verified/price/path"}]})

    def test_structured_factory_keeps_fixed_dates_quoted(self):
        plan = structured_mql_factory.generate({"query_shape": "TIME_SERIES", "codes": ["600519.SH"], "start_date": "2025-01-01", "end_date": "2025-12-31", "period": "日", "fields": [{"field": "收盘价", "indicator_path": "verified/price/path"}]})
        self.assertIn('{结束时间} = "2025-12-31"', plan["mql_script"])
        self.assertNotIn("query_end_date_dynamic", plan)

    def test_financial_factory_emits_unquoted_mrq(self):
        core = json.loads((ROOT / "reference" / "a_share_financial_timeseries_core.json").read_text(encoding="utf-8"))
        spec = {"security_code": "002594.SZ", "start_date": "2024-01-01", "end_date": "MRQ()", "period": "年", "metrics": [{"cache_key": "balance_sheet.货币资金", "field": "货币资金", "display_unit": "百万元"}]}
        plan = financial_workpaper_factory.generate(spec, core)
        self.assertIn("{结束时间} = MRQ()", plan["mql_script"])
        self.assertEqual(plan["query_end_date_dynamic"], "MRQ()")

    def test_financial_factory_rejects_now_marker(self):
        core = json.loads((ROOT / "reference" / "a_share_financial_timeseries_core.json").read_text(encoding="utf-8"))
        spec = {"security_code": "002594.SZ", "start_date": "2024-01-01", "end_date": "N()", "period": "年", "metrics": [{"cache_key": "balance_sheet.货币资金", "field": "货币资金", "display_unit": "百万元"}]}
        with self.assertRaises(ValueError):
            financial_workpaper_factory.generate(spec, core)


class DynamicEndMarkerValidationTests(unittest.TestCase):
    def setUp(self):
        import build_workbook
        self.build_workbook = build_workbook
        self.script = 'TimeSeriesBlock(#1, {EM_DATE}, {EM_CODE});\nSetWindow(\n    {开始时间} = "2025-01-01",\n    {结束时间} = N(),\n    {周期} = "日"\n);\n{收盘价}: X();\nOutputBlock();'
        self.item = {"execution_status": "SUCCESS", "data_source": "MQL", "mql_script": self.script, "block_selector": "#1", "query_end_date_dynamic": "N()"}

    def test_declared_marker_matching_script_passes(self):
        self.build_workbook.validate_dynamic_end_marker(self.item, "w")

    def test_declaration_without_script_marker_fails(self):
        item = {**self.item, "mql_script": self.script.replace("{结束时间} = N()", '{结束时间} = "2026-10-14"')}
        with self.assertRaises(ValueError):
            self.build_workbook.validate_dynamic_end_marker(item, "w")

    def test_script_marker_without_declaration_fails(self):
        item = {**self.item, "query_end_date_dynamic": None}
        with self.assertRaises(ValueError):
            self.build_workbook.validate_dynamic_end_marker(item, "w")

    def test_quoted_marker_fails_fast(self):
        item = {**self.item, "mql_script": self.script.replace("{结束时间} = N()", '{结束时间} = "N()"')}
        with self.assertRaises(ValueError):
            self.build_workbook.validate_dynamic_end_marker(item, "w")

    def test_marker_mismatch_between_declaration_and_script_fails(self):
        item = {**self.item, "query_end_date_dynamic": "MRQ()"}
        with self.assertRaises(ValueError):
            self.build_workbook.validate_dynamic_end_marker(item, "w")

    def test_edb_anchor_cannot_use_dynamic_marker(self):
        item = {**self.item, "mql_script": 'EdbBlock(#1,{EM_DATE});\nSetParams({结束时间} = N());\n{国债1Y}: X();', "query_end_date_dynamic": "N()"}
        with self.assertRaises(ValueError):
            self.build_workbook.validate_dynamic_end_marker(item, "w")


class DynamicTimeSeriesSheetTests(unittest.TestCase):
    def test_dynamic_timeseries_workpaper_gets_an_isolated_sheet(self):
        import build_workbook
        from openpyxl import Workbook

        workbook = Workbook()
        workbook.active.title = "00_导读"
        snapshots = [{"table_id": "p1-t1", "table_name": "股价走势", "page": 1, "unit": "元"}]
        workpapers = [{
            "source_type": "TABLE", "source_id": "p1-t1", "mapping_id": "table:p1-t1:ts",
            "execution_status": "SUCCESS", "data_source": "MQL", "mapping_status": "FULL",
            "mapping_note": "走势图启用动态结束时间",
            "mql_script": 'TimeSeriesBlock(#1, {EM_DATE}, {EM_CODE});\nSetWindow(\n    {开始时间} = "2025-01-01",\n    {结束时间} = N(),\n    {周期} = "日"\n);\n{收盘价}: X();\nOutputBlock();',
            "block_selector": "#1", "query_end_date_dynamic": "N()",
            "query_end_date": "2026-10-14", "result_as_of": "2026-10-14T10:00:00+08:00",
            "mql_orientation": 0, "last_result": [["EM_DATE", "收盘价"], ["2026-10-14", 10.0]],
        }]
        build_workbook.build_workpaper_sheet(workbook, snapshots, workpapers, [])

        self.assertIn("22_TS_001", workbook.sheetnames)
        self.assertFalse(any(
            isinstance(cell.value, str) and cell.value.startswith("=mql")
            for row in workbook["20_研报底稿"].iter_rows() for cell in row
        ))
        self.assertTrue(any(
            cell.hyperlink is not None and "22_TS_001" in str(cell.hyperlink.target or "")
            for row in workbook["20_研报底稿"].iter_rows() for cell in row
        ))
        sheet = workbook["22_TS_001"]
        ts_formulas = [
            cell for row in sheet.iter_rows() for cell in row
            if isinstance(cell.value, str) and cell.value.startswith("=mql")
        ]
        self.assertEqual(len(ts_formulas), 1)
        self.assertEqual(ts_formulas[0].comment.text, workpapers[0]["mql_script"])
        self.assertTrue(all(
            cell.value is None
            for row in sheet.iter_rows(min_row=ts_formulas[0].row + 1)
            for cell in row
        ))
        self.assertTrue(any(
            cell.value == "N()"
            for row in sheet.iter_rows(min_col=2, max_col=2) for cell in row
        ))

    def test_financial_mrq_workpaper_gets_an_isolated_sheet(self):
        import build_workbook
        from openpyxl import Workbook

        workbook = Workbook()
        workbook.active.title = "00_导读"
        snapshots = [{"table_id": "p2-t1", "table_name": "货币资金趋势", "page": 2, "unit": "百万元"}]
        workpapers = [{
            "source_type": "TABLE", "source_id": "p2-t1", "mapping_id": "table:p2-t1:mrq",
            "execution_status": "SUCCESS", "data_source": "MQL", "mapping_status": "FULL",
            "mapping_note": "_s 报告期趋势启用 MRQ()",
            "mql_script": 'TimeSeriesBlock(#1, {EM_DATE}, {EM_CODE});\nSetWindow(\n    {开始时间} = "2024-12-31",\n    {结束时间} = MRQ(),\n    {周期} = "季"\n);\n{货币资金}: X();\nOutputBlock();',
            "block_selector": "#1", "query_end_date_dynamic": "MRQ()",
            "query_end_date": "2026-06-30", "result_as_of": "2026-10-14T10:00:00+08:00",
            "mql_orientation": 1, "last_result": [["EM_DATE", "2025-12-31", "2026-06-30"], ["货币资金", 51690.6, 53518.8]],
        }]
        build_workbook.build_workpaper_sheet(workbook, snapshots, workpapers, [])

        self.assertIn("22_TS_001", workbook.sheetnames)
        self.assertFalse(any(
            isinstance(cell.value, str) and cell.value.startswith("=mql")
            for row in workbook["20_研报底稿"].iter_rows() for cell in row
        ))
        sheet = workbook["22_TS_001"]
        formulas = [cell for row in sheet.iter_rows() for cell in row if isinstance(cell.value, str) and cell.value.startswith("=mql")]
        self.assertEqual(len(formulas), 1)
        self.assertEqual(formulas[0].value, '=mql("#1",1)')
        self.assertTrue(all(cell.value is None for row in sheet.iter_rows(min_row=formulas[0].row + 1) for cell in row))
        self.assertTrue(any(cell.value == "MRQ()" for row in sheet.iter_rows(min_col=2, max_col=2) for cell in row))


class GrossProfitDerivationRegressionTests(unittest.TestCase):
    """R04：毛利润 = 营业收入 − 营业成本（同口径）；不得用 营业总收入 − 营业总成本（含期间费用与税金）。"""

    TEMPLATE_06 = ROOT / "reference" / "mql_templates" / "06_A股_派生指标计算.mql"
    TEMPLATE_02 = ROOT / "reference" / "mql_templates" / "02_A股_利润表科目.mql"

    def test_derivation_reads_same_scope_revenue_and_cost(self):
        script = self.TEMPLATE_06.read_text(encoding="utf-8")
        self.assertIn('{营业收入}: REPORT_FIELD("营业收入");', script)
        self.assertIn('{营业成本}: REPORT_FIELD("营业成本");', script)
        self.assertIn("{毛利润} = {营业收入} - {营业成本};", script)
        self.assertNotIn("{营业总收入} - {营业总成本}", script)

    def test_template_02_alias_note_no_longer_points_to_total_cost(self):
        note = self.TEMPLATE_02.read_text(encoding="utf-8")
        self.assertNotIn("营业总成本（见模板 06）", note)
        self.assertIn("同口径，见模板 06", note)

    def test_synthetic_case_yields_forty_not_twenty_five(self):
        import re

        script = self.TEMPLATE_06.read_text(encoding="utf-8")
        match = re.search(r"\{毛利润\}\s*=\s*\{([^}]+)\}\s*-\s*\{([^}]+)\};", script)
        self.assertIsNotNone(match)
        self.assertEqual((match.group(1), match.group(2)), ("营业收入", "营业成本"))
        # 合成：收入 100 / 营业成本 60 / 其他费用 15
        #   同口径毛利 = 100 − 60 = 40（正确）；总收入 − 总成本 = 100 − (60 + 15) = 25（错误口径）
        revenue, cost_of_sales, overhead = 100, 60, 15
        self.assertEqual(revenue - cost_of_sales, 40)
        self.assertNotEqual(revenue - (cost_of_sales + overhead), 40)


class ApproximateNoteRegressionTests(unittest.TestCase):
    """R03：模板中的“近似”说明必须标注口径不等价；估值/每股指标须写明分母与时点契约。"""
    TEMPLATES = ROOT / "reference" / "mql_templates"

    def _note_line(self, name, marker):
        text = (self.TEMPLATES / name).read_text(encoding="utf-8")
        return next(line for line in text.splitlines() if marker in line)

    def test_approximate_notes_declare_non_equivalence(self):
        cases = [
            ("03_A股_现金流量表科目.mql", "现金收益"),
            ("04_A股_财务比率指标宽表.mql", "正常化市盈率"),
            ("05_A股_估值与分红指标.mql", "正常化市盈率"),
        ]
        for name, marker in cases:
            self.assertIn("不等价", self._note_line(name, marker), name)

    def test_share_and_valuation_denominators_are_documented(self):
        t04 = self._note_line("04_A股_财务比率指标宽表.mql", "口径契约")
        self.assertIn("分母=期末股本", t04)
        self.assertIn("分母=最新总股本", t04)
        t05 = (self.TEMPLATES / "05_A股_估值与分红指标.mql").read_text(encoding="utf-8")
        self.assertIn("分母=最新归母净资产/最新总股本", t05)
        self.assertIn("基准日契约", t05)


class SourceLevelCoverageRegressionTests(unittest.TestCase):
    """R06：来源级多锚点覆盖汇总；不再逐锚点强制分区，不再把底稿形状绑定原文形状。"""

    @staticmethod
    def _third_snapshot():
        t = prepare_workbook_phases.normalize_table({
            "table_id": "p1-t3", "table_name": "估值指标",
            "headers": ["EM_CODE", "总市值(百万元)", "市盈率(倍)"],
            "rows": [["002594.SZ", "804136.8", "25.3"]],
            "bbox": [10.0, 10.0, 500.0, 400.0], "source_semantic_type": "CROSS_SECTION_TABLE",
        })
        t.update(page=2, layout_group="g3", lane="main", reading_order=1,
                 layout_contract_reason="rows are entities; columns are metrics",
                 source_row_axis="ENTITY", source_column_axis="METRIC",
                 source_semantic_type="CROSS_SECTION_TABLE", source_period_basis="REPORTING_PERIOD",
                 queryable_fields=["总市值(百万元)", "市盈率(倍)"], is_visual_object=False,
                 bbox=[0.0, 0.0, 1.0, 1.0], row_bboxes=[[0.0, 0.0, 1.0, 1.0]],
                 source_status="PASS", visual_check="PASS")
        return t

    @staticmethod
    def _anchor(alias, run_id, value, *, target_fields, omitted=(), mapping_status="FULL"):
        import test_relaxed_contract_1012 as fixture

        script = 'CrossSectionBlock(#1,{EM_CODE});\n{%s}: X("服务端\\\\妙想服务\\\\F10_估值");' % alias
        raw = [["EM_CODE", alias], ["002594.SZ", value]]
        return {
            "source_type": "TABLE", "source_id": "p1-t3", "mapping_id": f"table:p1-t3:{run_id}",
            "execution_status": "SUCCESS", "data_source": "MQL", "mapping_status": mapping_status,
            "mapping_note": "分锚点覆盖来源的不同字段",
            "source_semantic_type": "CROSS_SECTION_TABLE", "query_interface": "Choice指标",
            "data_path_type": "INDICATOR", "mql_script": script, "block_selector": "#1",
            "mql_orientation": 0, "orientation_reason": "保持原始方向", "result_as_of": "2026-10-15",
            "result_origin": "MQL_TOOLCHAIN", "script_sha256": fixture._sha(script),
            "execution_run_id": run_id, "queried_at": "2026-10-15T10:00:00+08:00",
            "raw_result": [r[:] for r in raw], "last_result": [r[:] for r in raw],
            "cached_table": [r[:] for r in raw], "query_shape": "CROSS_SECTION",
            "target_row_axis": "ENTITY", "target_column_axis": "METRIC",
            "row_axis_labels": ["002594.SZ"], "column_axis_labels": [alias],
            "display_label_map": [{"key": "002594.SZ", "display_name": "比亚迪", "kind": "ENTITY"}],
            "source_fields": list(target_fields), "covered_fields": [alias],
            "omitted_fields": [{"field": field, "reason": "本锚点未取得", "evidence_ids": [run_id]} for field in omitted],
            "script_output_fields": [alias],
            "source_periods": [], "covered_periods": [], "omitted_periods": [],
            "expected_rows": 2, "expected_columns": 2,
            "unit_contracts": [{"field": alias, "value_type": "NUMBER",
                                "source_unit": "倍" if "率" in alias else "百万元",
                                "display_unit": "倍" if "率" in alias else "百万元",
                                "scale_factor": 1, "source_semantics": "ABSOLUTE", "display_semantics": "ABSOLUTE"}],
        }

    @classmethod
    def _payload(cls, *anchors):
        import test_relaxed_contract_1012 as fixture

        payload = fixture._payload()
        payload["snapshots"] = payload["snapshots"] + [cls._third_snapshot()]
        payload["guide"]["census_table_count"] = 3
        payload["guide"]["pdf_page_count"] = 2
        payload["workpapers"] = payload["workpapers"] + list(anchors)
        for anchor in anchors:
            payload["execution_log"].append({
                "attempt_id": anchor["execution_run_id"], "source_id": "p1-t3",
                "data_source": "MQL", "data_path_type": "INDICATOR", "status": "SUCCESS",
                "metric": anchor["covered_fields"][0], "source_block": "#1",
                "query_path": "服务端\\妙想服务\\F10_估值", "execution_run_id": anchor["execution_run_id"],
                "queried_at": "2026-10-15T10:00:00+08:00", "raw_result_summary": "1x1",
                "unit": "百万元", "script_sha256": anchor["script_sha256"],
            })
        return payload

    def test_split_anchors_cover_one_source_without_fake_omissions(self):
        import build_workbook

        anchors = [
            self._anchor("总市值(百万元)", "run-a3", 804136.8, target_fields=["总市值(百万元)"]),
            self._anchor("市盈率(倍)", "run-b3", 25.3, target_fields=["市盈率(倍)"]),
        ]
        build_workbook.validate_payload(self._payload(*anchors))
        self.assertEqual(preflight_workbook_input.collect_with_final_validation(self._payload(*anchors)), [])

    def test_fake_omission_of_sibling_covered_field_is_rejected(self):
        import build_workbook

        anchors = [
            self._anchor("总市值(百万元)", "run-a3", 804136.8,
                         target_fields=["总市值(百万元)", "市盈率(倍)"],
                         omitted=["市盈率(倍)"], mapping_status="PARTIAL"),
            self._anchor("市盈率(倍)", "run-b3", 25.3, target_fields=["市盈率(倍)"]),
        ]
        with self.assertRaisesRegex(ValueError, "cannot also be recorded as omitted"):
            build_workbook.validate_payload(self._payload(*anchors))

    def test_unaccounted_source_field_fails(self):
        import build_workbook

        anchor = self._anchor("总市值(百万元)", "run-a3", 804136.8,
                              target_fields=["总市值(百万元)"], mapping_status="PARTIAL")
        with self.assertRaisesRegex(ValueError, "coverage must account for every source field"):
            build_workbook.validate_payload(self._payload(anchor))

    def test_anchor_level_full_must_cover_its_own_target(self):
        import build_workbook

        anchor = self._anchor("总市值(百万元)", "run-a3", 804136.8,
                              target_fields=["总市值(百万元)", "市盈率(倍)"], omitted=["市盈率(倍)"])
        with self.assertRaisesRegex(ValueError, "FULL mapping requires this anchor"):
            build_workbook.validate_payload(self._payload(anchor))

    def test_source_shape_and_display_labels_no_longer_force_full_match(self):
        import test_relaxed_contract_1012 as fixture
        import build_workbook

        anchor = self._anchor("总市值(百万元)", "run-a3", 804136.8,
                              target_fields=["总市值(百万元)", "市盈率(倍)"])
        script = 'CrossSectionBlock(#1,{EM_CODE});\n{总市值(百万元)}: X("a");\n{市盈率(倍)}: X("b");'
        raw = [["EM_CODE", "总市值(百万元)", "市盈率(倍)"], ["比亚迪", 804136.8, 25.3]]
        anchor.update(
            mql_script=script, script_sha256=fixture._sha(script),
            raw_result=[r[:] for r in raw], last_result=[r[:] for r in raw], cached_table=[r[:] for r in raw],
            covered_fields=["总市值(百万元)", "市盈率(倍)"],
            script_output_fields=["总市值(百万元)", "市盈率(倍)"],
            row_axis_labels=["比亚迪"], column_axis_labels=["总市值(百万元)", "市盈率(倍)"],
            display_label_map=[{"key": "比亚迪", "display_name": "比亚迪", "kind": "ENTITY"}],
            expected_rows=2, expected_columns=3,
            unit_contracts=[
                {"field": "总市值(百万元)", "value_type": "NUMBER", "source_unit": "百万元",
                 "display_unit": "百万元", "scale_factor": 1, "source_semantics": "ABSOLUTE", "display_semantics": "ABSOLUTE"},
                {"field": "市盈率(倍)", "value_type": "NUMBER", "source_unit": "倍",
                 "display_unit": "倍", "scale_factor": 1, "source_semantics": "ABSOLUTE", "display_semantics": "ABSOLUTE"},
            ],
        )
        # 行标签用标准简称、列数与表头均与原文不同：R06 前会因「FULL cached_table row labels
        # must exactly match snapshot rows」失败，现按来源级覆盖验收通过。
        build_workbook.validate_payload(self._payload(anchor))

    def test_pipeline_audit_enforces_source_level_partition(self):
        honest = self._payload(
            self._anchor("总市值(百万元)", "run-a3", 804136.8, target_fields=["总市值(百万元)"]),
            self._anchor("市盈率(倍)", "run-b3", 25.3, target_fields=["市盈率(倍)"]),
        )
        path = Path(tempfile.mkdtemp()) / "workbook_input.json"
        path.write_text(json.dumps(honest, ensure_ascii=False), encoding="utf-8")
        research_report_pipeline.audit(path)

        fake = self._payload(
            self._anchor("总市值(百万元)", "run-a3", 804136.8,
                         target_fields=["总市值(百万元)", "市盈率(倍)"],
                         omitted=["市盈率(倍)"], mapping_status="PARTIAL"),
            self._anchor("市盈率(倍)", "run-b3", 25.3, target_fields=["市盈率(倍)"]),
        )
        path.write_text(json.dumps(fake, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source-level partition"):
            research_report_pipeline.audit(path)


class LatestTradingWindowRegressionTests(unittest.TestCase):
    """R05：应用层窗口策略（LATEST_1000_TRADING_DAYS）+ 市场入 SetWindow + 预加载计数。"""

    @staticmethod
    def _calendar(count, start=None, holidays=()):
        from datetime import date, timedelta

        cursor = start or date(2018, 1, 1)
        days = []
        while len(days) < count:
            if cursor not in holidays:
                days.append(cursor.isoformat())
            cursor += timedelta(days=1)
        return days

    def test_latest_window_takes_1000_trading_days_including_endpoint(self):
        cal = self._calendar(1300)
        start, end, count, truncated = structured_mql_factory.latest_trading_window(cal, cal[-1])
        self.assertEqual((count, truncated), (1000, False))
        self.assertEqual(end, cal[-1])
        self.assertEqual(start, cal[-1000])
        # 含终点恰好 1000 个位置（索引差 999），不是 1001
        self.assertEqual(cal.index(end) - cal.index(start), 999)

    def test_adjacent_trading_days_shift_the_window_together(self):
        cal = self._calendar(1300)
        start_1, end_1, count_1, _ = structured_mql_factory.latest_trading_window(cal, cal[-2])
        start_2, end_2, count_2, _ = structured_mql_factory.latest_trading_window(cal, cal[-1])
        self.assertEqual((count_1, count_2), (1000, 1000))
        self.assertEqual(cal.index(end_2) - cal.index(end_1), 1)
        self.assertEqual(cal.index(start_2) - cal.index(start_1), 1)  # 起点同步后移

    def test_holidays_are_not_counted_as_positions(self):
        from datetime import date

        holidays = {date(2022, 2, 1), date(2022, 2, 2), date(2022, 2, 3)}
        cal = self._calendar(1000, start=date(2022, 1, 1), holidays=holidays)
        start, end, count, truncated = structured_mql_factory.latest_trading_window(cal, cal[-1])
        self.assertEqual((count, truncated), (1000, False))
        natural_span = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        self.assertGreater(natural_span, 1000)  # 自然日跨度大于位置数，节假日未被计入交易日

    def test_preload_is_counted_and_capped_with_official_points(self):
        cal = self._calendar(1300)
        base = {
            "query_shape": "TIME_SERIES", "codes": ["RB0.SHF"], "period": "日",
            "window_policy": "LATEST_1000_TRADING_DAYS", "trading_calendar": cal,
            "confirmed_end_date": cal[-1], "preload_period_count": 0,
            "fields": [{"field": "收盘价", "indicator_path": "verified/price"}],
        }
        plan = structured_mql_factory.generate(base)
        self.assertEqual(plan["query_window_point_count"], 1000)
        self.assertEqual(plan["preload_period_count"], 0)
        self.assertIn("{预加载周期} = 0", plan["mql_script"])
        self.assertFalse(plan["rolling_implemented"])
        with self.assertRaises(ValueError):
            structured_mql_factory.generate({**base, "preload_period_count": 1})
        short = structured_mql_factory.generate({**base, "trading_calendar": cal[-600:]})
        self.assertEqual(short["query_window_point_count"], 600)
        self.assertTrue(short["query_window_truncated"])

    def test_market_goes_into_setwindow_but_not_for_reporting_periods(self):
        cal = self._calendar(200)
        spec = {
            "query_shape": "TIME_SERIES", "codes": ["RB0.SHF"], "market": "SHFE", "period": "日",
            "start_date": cal[0], "end_date": cal[-1], "window_market": "上海期货交易所",
            "fields": [{"field": "收盘价", "indicator_path": "verified/price"}],
        }
        plan = structured_mql_factory.generate(spec)
        self.assertIn('{市场类型} = "上海期货交易所"', plan["mql_script"])
        self.assertEqual(plan["window_market"], "上海期货交易所")
        with self.assertRaises(ValueError):
            structured_mql_factory.generate({**spec, "window_market": "上交所"})
        with self.assertRaises(ValueError):
            structured_mql_factory.generate({
                "query_shape": "TIME_SERIES", "codes": ["600519.SH"], "period": "季",
                "start_date": "2024-12-31", "end_date": "MRQ()", "window_market": "上海证券交易所",
                "fields": [{"field": "货币资金", "indicator_path": "Choice指标/序列函数/货币资金|1_s"}],
            })

    def test_build_workbook_validates_latest_window_positions(self):
        import build_workbook

        item = {
            "execution_status": "SUCCESS", "data_source": "MQL",
            "mql_script": 'TimeSeriesBlock(#1, {EM_DATE}, {EM_CODE});\nSetWindow(\n    {开始时间} = "2020-01-01",\n    {结束时间} = "2026-10-14",\n    {周期} = "日",\n    {市场类型} = "上海期货交易所"\n);\n{收盘价}: X();\nOutputBlock();',
            "block_selector": "#1", "window_policy": "LATEST_1000_TRADING_DAYS",
            "query_window_point_count": 1000, "rolling_implemented": False,
            "query_start_date": "2020-01-01", "query_end_date": "2026-10-14",
        }
        build_workbook.validate_time_series_window(item, "w")
        with self.assertRaises(ValueError):
            build_workbook.validate_time_series_window({**item, "preload_period_count": 1}, "w")
        with self.assertRaises(ValueError):
            build_workbook.validate_time_series_window({**item, "rolling_implemented": True}, "w")
        with self.assertRaises(ValueError):
            build_workbook.validate_time_series_window({**item, "query_window_point_count": None}, "w")


class SegmentCoverageRegressionTests(unittest.TestCase):
    """R07：主营构成/分部来源按「分类×分部×字段」验收；合计数据不得替代明细分部。"""

    FIELDS = ["主营业务收入", "主营业务成本", "毛利", "毛利率"]
    HEADERS = ["分部"] + FIELDS
    ROWS = [
        ["合计", "100", "60", "40", "40%"],
        ["中国大陆", "70", "40", "", ""],
        ["海外", "30", "20", "", ""],
    ]

    @staticmethod
    def _sha(script):
        import test_relaxed_contract_1012 as fixture

        return fixture._sha(script)

    @classmethod
    def _snapshot(cls, rows=None, headers=None):
        rows = [list(row) for row in (rows or cls.ROWS)]
        headers = list(headers or cls.HEADERS)
        table = prepare_workbook_phases.normalize_table({
            "table_id": "p1-t4", "table_name": "主营构成（按地区）",
            "headers": headers, "rows": rows,
            "bbox": [10.0, 10.0, 500.0, 400.0], "source_semantic_type": "OTHER",
        })
        table.update(page=1, layout_group="g4", lane="main", reading_order=1,
                     layout_contract_reason="rows are segments; columns are fields",
                     queryable_fields=list(headers), is_visual_object=False,
                     bbox=[0.0, 0.0, 1.0, 1.0], row_bboxes=[[0.0, 0.0, 1.0, 1.0] for _ in rows],
                     source_status="PASS", visual_check="PASS")
        return table

    @classmethod
    def _anchor(cls, run_id, *, covered_segments, omitted_segments=(), mapping_status="PARTIAL"):
        rows = [list(row) for row in cls.ROWS]
        table = [list(cls.HEADERS)] + [list(row) for row in rows]
        script = ('ReportBlock(#1, {港股F9_主营构成_汇总});\nSetCodes(["00700.HK"]);\n'
                  '{分部}: REPORT_FIELD("标准产品名称");\n'
                  '{主营业务收入}: REPORT_FIELD("主营业务收入");\n'
                  '{主营业务成本}: REPORT_FIELD("主营业务成本");\n'
                  '{毛利}: REPORT_FIELD("毛利");\n'
                  '{毛利率}: REPORT_FIELD("毛利率");\n'
                  'OutputBlock();')
        fields = list(cls.HEADERS)
        return {
            "source_type": "TABLE", "source_id": "p1-t4", "mapping_id": f"table:p1-t4:{run_id}",
            "execution_status": "SUCCESS", "data_source": "MQL", "mapping_status": mapping_status,
            "mapping_note": "主营构成按地区/产品分部取数",
            "source_semantic_type": "OTHER", "query_interface": "Choice报表",
            "data_path_type": "REPORT", "mql_script": script, "block_selector": "#1",
            "mql_orientation": 0, "orientation_reason": "保持原始方向", "result_as_of": "2026-10-15",
            "result_origin": "MQL_TOOLCHAIN", "script_sha256": cls._sha(script),
            "execution_run_id": run_id, "queried_at": "2026-10-15T10:00:00+08:00",
            "raw_result": [r[:] for r in table], "last_result": [r[:] for r in table],
            "cached_table": [r[:] for r in table], "query_shape": "REPORT_MATRIX",
            "target_row_axis": "CATEGORY", "target_column_axis": "METRIC",
            "row_axis_labels": [str(row[0]) for row in rows],
            "column_axis_labels": list(cls.FIELDS),
            "display_label_map": [{"key": str(row[0]), "display_name": str(row[0]), "kind": "CATEGORY"} for row in rows],
            "source_fields": fields, "covered_fields": list(fields), "omitted_fields": [],
            "script_output_fields": list(fields),
            "covered_segments": list(covered_segments),
            "omitted_segments": [{"segment": segment, "reason": "本期该分部无有效数值", "evidence_ids": [run_id]}
                                 for segment in omitted_segments],
            "source_periods": [], "covered_periods": [], "omitted_periods": [],
            "expected_rows": len(table), "expected_columns": len(table[0]),
            "unit_contracts": [{"field": "分部", "value_type": "TEXT", "source_unit": "", "display_unit": "",
                                "scale_factor": 1, "source_semantics": "TEXT", "display_semantics": "TEXT"}]
            + [{"field": field, "value_type": "NUMBER", "source_unit": "%" if "率" in field else "百万元",
                "display_unit": "%" if "率" in field else "百万元", "scale_factor": 1,
                "source_semantics": "ABSOLUTE", "display_semantics": "ABSOLUTE"} for field in cls.FIELDS],
        }

    @classmethod
    def _payload(cls, *anchors, snapshot=None):
        snapshot = snapshot or cls._snapshot()
        payload = {
            "guide": {"company_name": "腾讯控股", "security_code": "00700.HK", "report_title": "t",
                      "report_date": "2026-09-16", "verification_date": "2026-10-15",
                      "pdf_page_count": 1, "census_table_count": 1, "visual_object_count": 0},
            "snapshots": [snapshot], "excluded_tables": [], "chart_snapshots": [], "chart_data": [],
            "workpapers": list(anchors), "verification": [], "execution_log": [],
            "forecast": {"revenue_forecast": []},
        }
        for anchor in anchors:
            payload["execution_log"].append({
                "attempt_id": anchor["execution_run_id"], "source_id": "p1-t4",
                "data_source": "MQL", "data_path_type": "REPORT", "status": "SUCCESS",
                "metric": "主营业务收入", "source_block": "#1",
                "query_path": "港股F9_主营构成_汇总", "execution_run_id": anchor["execution_run_id"],
                "queried_at": "2026-10-15T10:00:00+08:00", "raw_result_summary": "3x5",
                "unit": "百万元", "script_sha256": anchor["script_sha256"],
            })
        return payload

    def test_segment_roles_are_derived_from_source_rows(self):
        snapshot = self._snapshot()
        self.assertEqual(snapshot["source_segments"], [
            {"segment": "合计", "role": "TOTAL"},
            {"segment": "中国大陆", "role": "DETAIL"},
            {"segment": "海外", "role": "DETAIL"},
        ])
        self.assertIn("合计", snapshot["segment_role_basis"])

    def test_detail_segments_with_empty_numeric_fields_are_rejected(self):
        import build_workbook

        # 改前：毛利/毛利率仅合计行有值，明细行全空，却按 FULL 通过（合计替代明细）。
        anchor = self._anchor("run-s1", covered_segments=["合计", "中国大陆", "海外"])
        with self.assertRaisesRegex(ValueError, "TOTAL row must not substitute DETAIL coverage"):
            build_workbook.validate_payload(self._payload(anchor))

    def test_omitting_empty_detail_segments_is_accepted(self):
        import build_workbook

        # 诚实做法：合计可查，明细不可查 -> 把明细分部登记为 omitted，来源降为 PARTIAL。
        anchor = self._anchor("run-s1", covered_segments=["合计"], omitted_segments=["中国大陆", "海外"])
        build_workbook.validate_payload(self._payload(anchor))

    def test_segment_source_requires_segment_coverage(self):
        import build_workbook

        anchor = self._anchor("run-s1", covered_segments=["合计"], omitted_segments=["中国大陆", "海外"])
        anchor.pop("covered_segments")
        with self.assertRaisesRegex(ValueError, "covered_segments must list"):
            build_workbook.validate_payload(self._payload(anchor))

    def test_audit_requires_complete_segment_partition(self):
        payload = self._payload(self._anchor("run-s1", covered_segments=["合计"]))
        path = Path(tempfile.mkdtemp()) / "workbook_input.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "segment coverage is not a partition"):
            research_report_pipeline.audit(path)

    def test_honest_segment_payload_passes_pipeline_gates(self):
        import build_workbook

        payload = self._payload(self._anchor("run-s1", covered_segments=["合计"], omitted_segments=["中国大陆", "海外"]))
        build_workbook.validate_payload(payload)
        self.assertEqual(preflight_workbook_input.collect_with_final_validation(payload), [])
        path = Path(tempfile.mkdtemp()) / "workbook_input.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        research_report_pipeline.audit(path)

    def test_nested_header_parent_child_pairing_is_recorded(self):
        html = ('<table><tr><td rowspan="2">分部</td><td colspan="2">2026H1</td></tr>'
                '<tr><td>收入</td><td>毛利</td></tr>'
                '<tr><td>合计</td><td>100</td><td>40</td></tr></table>')
        headers, rows, hierarchy = prepare_workbook_phases.block_table_detail({"tableContent": html})
        self.assertEqual(headers, ["分部", "2026H1 / 收入", "2026H1 / 毛利"])
        self.assertEqual(hierarchy[0], {"parent": None, "child": "分部"})
        self.assertEqual(hierarchy[1], {"parent": "2026H1", "child": "收入"})
        self.assertEqual(hierarchy[2], {"parent": "2026H1", "child": "毛利"})

    def test_nested_header_without_hierarchy_fails_validation(self):
        import build_workbook

        snapshot = self._snapshot()
        snapshot["header_parse_origin"] = "NESTED_HEADER"
        anchor = self._anchor("run-s1", covered_segments=["合计"], omitted_segments=["中国大陆", "海外"])
        with self.assertRaisesRegex(ValueError, "header_hierarchy must record the parent/child pairing"):
            build_workbook.validate_payload(self._payload(anchor, snapshot=snapshot))

    def test_segment_template_selection_rules_are_registered(self):
        templates = ROOT / "reference" / "mql_templates"
        for name in ("10_A股_主营构成.mql", "11_港股_主营构成.mql", "12_美股_主营构成.mql"):
            self.assertTrue((templates / name).is_file(), name)
        index = (templates / "index.md").read_text(encoding="utf-8")
        for marker in ("分布类型", "报告期类型", "同比", "历史期"):
            self.assertIn(marker, index)

    def test_historical_period_rule_is_not_latest_only(self):
        templates = ROOT / "reference" / "mql_templates"
        for name in ("11_港股_主营构成.mql", "12_美股_主营构成.mql"):
            text = (templates / name).read_text(encoding="utf-8")
            self.assertIn("研报要求历史期", text, name)


class RuleSourceConsistencyTests(unittest.TestCase):
    """T24（R10）：规则单一真源。

    generation_contract.md G2 是 financial_query_mode 优先级链的唯一权威；
    mql_execution_protocol.md Step 2.5 是标准失败类别与兜底准入的唯一权威。
    其余文档只引用、不得各自重列顺序或类别子集，否则同一输入会因入口不同选出相反优先级。
    """

    QUERY_MODE_ORDER = [
        "REPORT_FULL_TABLE",
        "FINANCIAL_TIME_SERIES",
        "NATIVE_MULTI_PERIOD",
        "PERIOD_BLOCK_MERGE",
        "REPORT_FALLBACK",
    ]
    CONFLICT_PHRASES = ("财务标准指标优先级高于报表",)
    CATEGORY_ENUM_MARKERS = ("允许兜底", "只能是", "类别只允许", "失败类别必须是")

    def setUp(self):
        self.docs = {
            "SKILL.md": ROOT / "SKILL.md",
            "generation_contract.md": ROOT / "reference" / "generation_contract.md",
            "mql_execution_protocol.md": ROOT / "reference" / "mql_execution_protocol.md",
            "workbook_spec.md": ROOT / "reference" / "workbook_spec.md",
            "execution_stability.md": ROOT / "reference" / "execution_stability.md",
        }
        self.texts = {name: path.read_text(encoding="utf-8") for name, path in self.docs.items()}

    def test_financial_query_mode_chain_matches_code_constant(self):
        import build_workbook

        chain = self.texts["generation_contract.md"]
        positions = [chain.find(mode) for mode in self.QUERY_MODE_ORDER]
        self.assertTrue(all(pos >= 0 for pos in positions), f"G2 优先级链缺少项: {positions}")
        self.assertEqual(positions, sorted(positions), "G2 优先级链顺序必须固定且唯一")
        self.assertIn("唯一权威", chain)
        self.assertEqual(sorted(build_workbook.FINANCIAL_QUERY_MODES), sorted(self.QUERY_MODE_ORDER))

    def test_fallback_category_set_matches_code_constant(self):
        import build_workbook

        allowed = set(build_workbook.MQL_FALLBACK_FAILURES)
        self.assertEqual(len(allowed), 4)
        self.assertIn("SERVICE_FAILURE_CONFIRMED", allowed)
        for name, text in self.texts.items():
            for line in text.splitlines():
                if "UNSUPPORTED" not in line:
                    continue
                if not any(marker in line for marker in self.CATEGORY_ENUM_MARKERS):
                    continue
                present = {code for code in allowed if code in line}
                self.assertEqual(
                    present, allowed,
                    f"{name} 的兜底类别枚举必须等于代码常量（4 类），不得重列 3 类子集",
                )

    def test_no_document_restates_a_conflicting_rule(self):
        self.assertIn("唯一权威", self.texts["mql_execution_protocol.md"])
        for name, text in self.texts.items():
            for phrase in self.CONFLICT_PHRASES:
                self.assertNotIn(phrase, text, f"{name} 含冲突表述: {phrase}")

    def test_referencing_documents_point_to_authoritative_source(self):
        self.assertIn("generation_contract.md", self.texts["workbook_spec.md"])
        self.assertIn("generation_contract.md", self.texts["SKILL.md"])
        self.assertIn("mql_execution_protocol.md", self.texts["SKILL.md"])
        self.assertIn("mql_execution_protocol.md", self.texts["workbook_spec.md"])


class ResultArtifactContractTests(unittest.TestCase):
    """T29（R11，部分）：结果工件分层与工具契约边界。

    覆盖四点：①契约 JSON 四层齐全；②外部依赖已登记且不声称冲突已解决；
    ③④层工件名在协议中真实存在；④落盘表述引用协议单一真源且无许可式旧句残留。
    R11 未闭环部分（原样落盘合规性裁定）以 EXTERNAL_CONTRACT_PENDING 阻塞登记，不在此伪装为通过。
    """

    CONTRACT_PATH = ROOT / "reference" / "mql_artifact_contract.json"
    LAYER_IDS = ["RAW_RESPONSE", "BLOCK_MATRIX", "DERIVED_AUDIT", "FORMULA_SPILL"]
    PERMISSIVE_PHRASES = (
        "生成 Excel 或 Markdown 派生产物",
        "完整保留工具返回的结构化内容，不得覆盖或改写",
    )

    def setUp(self):
        self.contract = json.loads(self.CONTRACT_PATH.read_text(encoding="utf-8"))
        self.protocol = (ROOT / "reference" / "mql_execution_protocol.md").read_text(encoding="utf-8")
        self.stability = (ROOT / "reference" / "execution_stability.md").read_text(encoding="utf-8")
        self.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

    def test_contract_layers_complete_and_ordered(self):
        layers = self.contract["artifact_layers"]
        self.assertEqual([layer["id"] for layer in layers], self.LAYER_IDS)
        for layer in layers:
            self.assertTrue(layer["artifacts"], layer["id"])
            self.assertTrue(layer["allowed"], layer["id"])
            self.assertTrue(layer["forbidden"], layer["id"])

    def test_external_dependency_registered_not_claimed_resolved(self):
        dep = self.contract["external_dependency"]
        self.assertEqual(dep["id"], "E2")
        self.assertEqual(dep["status"], "EXTERNAL_CONTRACT_PENDING")
        self.assertIn("原样落盘", dep["question"])
        self.assertTrue(dep["no_hosted_reference_mechanism"])
        tool = self.contract["tool_contract"]
        self.assertIn("不得被客户端改写为 HTML、Excel 或其它文件", tool["clause"])
        self.assertIs(tool["changed_since_evaluation"], False)
        self.assertIn("EXTERNAL_CONTRACT_PENDING", self.protocol)
        self.assertIn("不得据此宣称冲突已解决", self.protocol)

    def test_protocol_declares_all_four_layers(self):
        for layer in self.contract["artifact_layers"]:
            self.assertIn(layer["name"], self.protocol, layer["name"])
        self.assertIn("mql_artifact_contract.json", self.protocol)

    def test_raw_response_persistence_has_single_authority(self):
        for name, text in (("execution_stability.md", self.stability), ("SKILL.md", self.skill)):
            self.assertIn("mql_execution_protocol.md", text, name)
            for phrase in self.PERMISSIVE_PHRASES:
                self.assertNotIn(phrase, text, f"{name} 残留许可式旧句: {phrase}")
        for phrase in self.PERMISSIVE_PHRASES:
            self.assertNotIn(phrase, self.protocol, f"协议残留许可式旧句: {phrase}")


class TemplateDiscoveryAndPeriodTests(unittest.TestCase):
    """T20/T26（R12）：模板可发现性、多期参数化与索引一致性。

    覆盖：12 个模板在索引中一一登记且编号与文件名一致；全部模板声明【示例窗口】并引用
    索引使用规则 6；三表模板显式禁止多 ACTUAL 期沿用 `Head(1)`；索引不再残留
    `{是否最新报告期} == "1"` 这类与模板实现冲突的表述，并补登「已知空值边界」。
    """

    TPL_DIR = ROOT / "reference" / "mql_templates"
    INDEX_PATH = TPL_DIR / "index.md"
    ALL_TEMPLATE_NUMBERS = [f"{index:02d}" for index in range(1, 13)]
    INTEGRAL_TEMPLATE_NUMBERS = ("01", "02", "03")
    STALE_LATEST_PERIOD_CLAIM = '{是否最新报告期} == "1"'

    def _index_text(self):
        return self.INDEX_PATH.read_text(encoding="utf-8")

    def _template_path(self, number):
        matches = sorted(self.TPL_DIR.glob(f"{number}_*.mql"))
        self.assertEqual(len(matches), 1, f"模板 {number} 应唯一存在，实际 {len(matches)} 个")
        return matches[0]

    def test_index_registers_every_template(self):
        index_text = self._index_text()
        for number in self.ALL_TEMPLATE_NUMBERS:
            path = self._template_path(number)
            self.assertIn(path.name, index_text, f"索引未登记 {path.name}")
            self.assertTrue(path.name.startswith(f"{number}_"), path.name)
        self.assertIn("本目录下的 12 个", index_text)

    def test_every_template_declares_example_window_not_default(self):
        for number in self.ALL_TEMPLATE_NUMBERS:
            text = self._template_path(number).read_text(encoding="utf-8")
            self.assertIn("【示例窗口】", text, f"模板 {number} 缺【示例窗口】声明")
            self.assertIn("非默认业务窗口", text, f"模板 {number} 未声明年份/窗口非默认")
            self.assertIn("index.md 使用规则 6", text, f"模板 {number} 未引用索引使用规则 6")

    def test_integral_templates_forbid_head1_for_multi_period(self):
        for number in self.INTEGRAL_TEMPLATE_NUMBERS:
            text = self._template_path(number).read_text(encoding="utf-8")
            self.assertIn("不得沿用 `Head(1)`", text, f"模板 {number} 未禁止多期沿用 Head(1)")
            self.assertIn("source_periods/covered_periods", text, f"模板 {number} 未要求登记期间覆盖")

    def test_index_has_no_stale_latest_period_claim(self):
        index_text = self._index_text()
        self.assertNotIn(self.STALE_LATEST_PERIOD_CLAIM, index_text)
        self.assertIn("已知空值边界", index_text)
        self.assertIn("研报要求历史期时", index_text)
        self.assertIn("不得沿用 `Head(1)`", index_text)


if __name__ == "__main__":
    unittest.main()
