from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mql_contract import selected_block_name, script_sha256, validate_market_group, validate_refresh_contract  # noqa: E402


SCRIPT = '''CrossSectionBlock(#1, {EM_CODE});
SetCodes(["002594.SZ"]);
{总市值(百万元)}: {Choice指标\\股票\\总市值|1}() / 1000000;
{净负债率(%)}: {Choice指标\\股票\\净负债率|2}() * 100;
OutputBlock();'''


def good_item() -> dict:
    digest = script_sha256(SCRIPT)
    return {
        "mql_script": SCRIPT,
        "block_selector": "#1",
        "execution_run_id": "run-1",
        "script_sha256": digest,
        "script_output_fields": ["总市值(百万元)", "净负债率(%)"],
        "raw_result": [["EM_CODE", "总市值(百万元)", "净负债率(%)"], ["002594.SZ", 804136.8, 28.7]],
        "unit_contracts": [
            {"field": "总市值(百万元)", "value_type": "NUMBER", "source_unit": "元", "display_unit": "百万元", "scale_factor": 0.000001, "source_semantics": "ABSOLUTE", "display_semantics": "ABSOLUTE", "script_transform_token": "/ 1000000"},
            {"field": "净负债率(%)", "value_type": "NUMBER", "source_unit": "比例", "display_unit": "%", "scale_factor": 100, "source_semantics": "DECIMAL_RATIO", "display_semantics": "PERCENT", "script_transform_token": "* 100"},
        ],
    }


class RefreshContractTests(unittest.TestCase):
    def test_selected_block_name_identifies_edb_selector(self) -> None:
        script = "EdbBlock(#1,{EM_DATE});{CPI}: X();\nCrossSectionBlock(#2,{EM_CODE});{PE}: Y();"
        self.assertEqual(selected_block_name(script, "#1"), "EdbBlock")
        self.assertEqual(selected_block_name(script, "#2"), "CrossSectionBlock")
        self.assertEqual(selected_block_name(script, None), "CrossSectionBlock")

    def test_valid_contract(self) -> None:
        item = good_item()
        logs = [{"execution_run_id": "run-1", "script_sha256": item["script_sha256"]}]
        self.assertEqual(validate_refresh_contract(item, logs), [])

    def test_explicit_business_label_is_not_treated_as_technical_header(self) -> None:
        script = ('CrossSectionBlock(#1, {EM_CODE});\n'
                  'SetCodes(["600519.SH"]);\n'
                  '{证券代码}: REPORT_FIELD("证券代码");\n'
                  '{营业总收入}: REPORT_FIELD("营业总收入");\n'
                  'OutputBlock();')
        digest = script_sha256(script)
        item = {
            "mql_script": script, "block_selector": "#1", "execution_run_id": "run-2",
            "script_sha256": digest, "script_output_fields": ["证券代码", "营业总收入"],
            "raw_result": [["证券代码", "营业总收入"], ["600519.SH", 1000]],
            "unit_contracts": [
                {"field": "证券代码", "value_type": "IDENTIFIER"},
                {"field": "营业总收入", "value_type": "NUMBER", "source_unit": "百万元",
                 "display_unit": "百万元", "scale_factor": 1,
                 "source_semantics": "ABSOLUTE", "display_semantics": "ABSOLUTE"},
            ],
        }
        logs = [{"execution_run_id": "run-2", "script_sha256": digest}]
        self.assertEqual(validate_refresh_contract(item, logs), [])

    def test_rejects_script_result_field_mismatch(self) -> None:
        item = good_item()
        item["raw_result"][0][-1] = "升幅12M"
        logs = [{"execution_run_id": "run-1", "script_sha256": item["script_sha256"]}]
        codes = {code for code, _ in validate_refresh_contract(item, logs)}
        self.assertIn("RUNTIME_HEADERS", codes)

    def test_rejects_unexecuted_excel_script(self) -> None:
        item = good_item()
        logs = [{"execution_run_id": "run-1", "script_sha256": "0" * 64}]
        codes = {code for code, _ in validate_refresh_contract(item, logs)}
        self.assertIn("EXECUTED_SCRIPT_HASH", codes)

    def test_rejects_claimed_conversion_missing_from_script(self) -> None:
        item = good_item()
        item["unit_contracts"][0]["script_transform_token"] = "/ 100000000"
        logs = [{"execution_run_id": "run-1", "script_sha256": item["script_sha256"]}]
        codes = {code for code, _ in validate_refresh_contract(item, logs)}
        self.assertIn("UNIT_TRANSFORM", codes)


class MarketContractTests(unittest.TestCase):
    def test_uniform_market_segments(self) -> None:
        common = ["证券简称", "收盘价"]
        first = {
            "market_schema": common,
            "script_output_fields": common,
            "mql_script": 'CrossSectionBlock(#1, {EM_CODE});\nSetCodes(["601633.SH"]);\n{证券简称}: X();\n{收盘价}: Y();\nOutputBlock();',
            "block_selector": "#1",
            "market_segment": {"market": "A股", "currency": "CNY", "entities": ["长城汽车"], "codes": ["601633.SH"]},
            "market_output_order": ["长城汽车", "理想汽车"],
        }
        second = {
            "market_schema": common,
            "script_output_fields": common,
            "mql_script": 'CrossSectionBlock(#1, {EM_CODE});\nSetCodes(["02015.HK"]);\n{证券简称}: X();\n{收盘价}: Y();\nOutputBlock();',
            "block_selector": "#1",
            "market_segment": {"market": "港股", "currency": "HKD", "entities": ["理想汽车"], "codes": ["02015.HK"]},
            "market_output_order": ["长城汽车", "理想汽车"],
        }
        self.assertEqual(validate_market_group([first, second], ["长城汽车", "理想汽车"]), [])

    def test_rejects_market_schema_drift(self) -> None:
        first = {"market_schema": ["证券简称", "收盘价"], "script_output_fields": ["证券简称", "收盘价"], "mql_script": 'CrossSectionBlock(#1,{EM_CODE}); SetCodes(["1.SH"]);', "block_selector": "#1", "market_segment": {"market": "A股", "currency": "CNY", "entities": ["甲"], "codes": ["1.SH"]}, "market_output_order": ["甲", "乙"]}
        second = {"market_schema": ["收盘价"], "script_output_fields": ["收盘价"], "mql_script": 'CrossSectionBlock(#1,{EM_CODE}); SetCodes(["2.HK"]);', "block_selector": "#1", "market_segment": {"market": "港股", "currency": "HKD", "entities": ["乙"], "codes": ["2.HK"]}, "market_output_order": ["甲", "乙"]}
        codes = {code for code, _ in validate_market_group([first, second], ["甲", "乙"])}
        self.assertIn("MARKET_SCHEMA", codes)


if __name__ == "__main__":
    unittest.main()
