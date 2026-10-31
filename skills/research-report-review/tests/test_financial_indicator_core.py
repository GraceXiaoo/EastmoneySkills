import json
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "reference" / "a_share_financial_timeseries_core.json"
SEED = ROOT / "reference" / "financial_indicator_seed.json"
RULES = ROOT / "reference" / "derived_metric_formulas.json"

sys.path.insert(0, str(ROOT / "scripts"))

import source_coverage_compiler  # noqa: E402


class CoreFinancialIndicatorCatalogTests(unittest.TestCase):
    def setUp(self):
        self.core = json.loads(CORE.read_text(encoding="utf-8"))
        self.seed = json.loads(SEED.read_text(encoding="utf-8"))

    def test_catalog_has_exact_attachment_coverage(self):
        entries = self.core["entries"]
        self.assertEqual(len(entries), 119)
        self.assertEqual(len({entry["metric_id"] for entry in entries.values()}), 119)
        self.assertEqual(
            Counter(entry["statement_family"] for entry in entries.values()),
            Counter({"BALANCE_SHEET": 40, "CASH_FLOW": 22, "INCOME_STATEMENT": 24, "PER_SHARE": 8, "FINANCIAL_RATIO": 25}),
        )

    def test_paths_and_units_are_complete(self):
        for key, entry in self.core["entries"].items():
            self.assertTrue(entry["indicator_path"].startswith("Choice指标\\序列函数\\股票\\沪深京股票指标\\"), key)
            self.assertTrue(entry["indicator_path"].endswith("|" + entry["metric_id"]), key)
            self.assertTrue(entry["metric_id"].endswith("_s"), key)
            self.assertTrue(entry["unit"], key)
            self.assertTrue(entry["period_semantics"], key)

    def test_seed_matches_catalog_names(self):
        # core 仅包含有 _s 时序版的指标；seed 允许包含无 _s 但有截面版的指标
        # （如净负债率、资产负债率、产权比率等），故校验 core 名称 ⊆ seed 名称
        for family, names in self.seed["families"].items():
            core_names = {
                entry["canonical_name"]
                for entry in self.core["entries"].values()
                if entry["statement_family"] == family
            }
            self.assertTrue(core_names.issubset(set(names)), f"core names not subset of seed for {family}: {core_names - set(names)}")


class FinancialRatioRetrievalNormalizationTests(unittest.TestCase):
    """R08 / T22：财务比率检索归一化、processing 分类与 entry-alias 消费。"""

    def setUp(self):
        self.core = json.loads(CORE.read_text(encoding="utf-8"))
        self.rules = json.loads(RULES.read_text(encoding="utf-8"))

    def compile(self, fields, rules=None):
        return source_coverage_compiler.compile_fields(fields, self.core, rules or self.rules)

    def test_entry_level_aliases_are_consumed(self):
        result = self.compile(["应收票据及应收账款", "资产总计", "负债合计", "归母净利润"])
        keys = {metric["field"]: metric["cache_key"] for metric in result["metrics"]}
        self.assertEqual(keys, {
            "应收票据及应收账款": "balance_sheet.应收账款及票据",
            "资产总计": "balance_sheet.总资产",
            "负债合计": "balance_sheet.总负债",
            "归母净利润": "income_statement.归属于母公司股东的净利润",
        })
        self.assertEqual(result["unresolved_fields"], [])

    def test_semantic_normalization_bridges_fullwidth_and_whitespace(self):
        # 全角括号/空格与半角写法应得到一致的判定结果（仅做语义安全归一化）
        for fields in (
            ["资产负债率（%）", "ROE（摊薄,%）"],
            ["资产负债率(%)", "ROE(摊薄,%)"],
            ["资产负债率（%） ", " ROE( 摊薄,%) "],
        ):
            result = self.compile(fields)
            self.assertEqual(list(result["field_dispositions"].values()), ["DERIVED", "DIRECT"], fields)
            self.assertEqual(result["unresolved_fields"], [])

    def test_business_modifiers_are_preserved(self):
        result = self.compile(["每股收益EPS(最新股本摊薄)", "应收账款周转率(含应收票据)", "应收账款周转率(不含票据)"])
        keys = {metric["field"]: metric["cache_key"] for metric in result["metrics"]}
        self.assertEqual(keys["每股收益EPS(最新股本摊薄)"], "per_share.每股收益EPS(最新股本摊薄)")
        self.assertEqual(keys["应收账款周转率(含应收票据)"], "financial_ratio.应收账款周转率")
        # 「不含票据」与「含票据」不是同一口径，不得被归一化吞掉修饰词而误命中
        unresolved = {item["field"] for item in result["unresolved_fields"]}
        self.assertIn("应收账款周转率(不含票据)", unresolved)

    def test_bare_pe_is_not_silently_equated_to_ttm(self):
        result = self.compile(["市盈率", "PE", "正常化市盈率"])
        unresolved = {item["field"] for item in result["unresolved_fields"]}
        self.assertIn("市盈率", unresolved)
        self.assertIn("PE", unresolved)
        # 正常化市盈率只能作为「近似参考」，且不得被静默替换为 TTM 口径
        approximate = [metric for metric in result["metrics"] if metric["field"] == "正常化市盈率"]
        self.assertEqual(len(approximate), 1)
        self.assertEqual(approximate[0]["kind"], "APPROXIMATE")
        # 近似参考只能指向「扣非」候选，且必须显式标注不等价，不得静默等同 TTM
        self.assertIn("扣除非经常性损益", approximate[0]["candidate_path"])
        self.assertNotEqual(approximate[0]["kind"], "DIRECT")
        self.assertEqual(result["coverage_status"], "PARTIAL")

    def test_report_field_disposition_enters_query_plan(self):
        result = self.compile(["应付账款周转率"])
        self.assertEqual(result["unresolved_fields"], [])
        self.assertEqual(result["coverage_status"], "FULL")
        metric = result["metrics"][0]
        self.assertEqual(metric["kind"], "REPORT_FIELD")
        self.assertEqual(metric["report_field"], "应付账款周转率")
        self.assertTrue(metric["report_path"].startswith("Choice报表"))
        self.assertEqual(result["covered_fields"], ["应付账款周转率"])

    def test_derived_chain_requires_all_operands_before_claiming_completion(self):
        # 资本支出/收入 的 operands 齐全 → DERIVED
        self.assertEqual(self.compile(["资本支出/收入"])["field_dispositions"], {"资本支出/收入": "DERIVED"})
        # 任一 operand 缺失时不得声称派生完成
        broken_rules = {
            **self.rules,
            "formulas": {**self.rules["formulas"], "EV/EBIT(测试)": {
                "operands": ["balance_sheet.总资产", "balance_sheet.不存在的科目"],
                "expression": "({0}) / ({1})", "display_unit": "倍"}},
        }
        result = self.compile(["EV/EBIT(测试)"], broken_rules)
        self.assertEqual(result["field_dispositions"], {"EV/EBIT(测试)": "PENDING_DEFINITION"})
        unresolved = {item["field"]: item["reason"] for item in result["unresolved_fields"]}
        self.assertEqual(unresolved, {"EV/EBIT(测试)": "NO_DIRECT_ALIAS_OR_FORMULA"})

    def test_every_field_receives_a_disposition(self):
        fields = ["货币资金", "市盈率", "应付账款周转率", "正常化市盈率", "资本支出/收入"]
        result = self.compile(fields)
        self.assertEqual(set(result["field_dispositions"]), set(fields))
        self.assertEqual(set(result["field_dispositions"].values()) - {"DIRECT", "DERIVED", "REPORT_FIELD", "APPROXIMATE", "PENDING_DEFINITION", "NO_DATA"}, set())


if __name__ == "__main__":
    unittest.main()
