import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "reference" / "tolerance_rules.json"

sys.path.insert(0, str(ROOT / "scripts"))

import result_comparison  # noqa: E402


class ToleranceDecisionTests(unittest.TestCase):
    """R09 / T23：容差分级有序、无重叠、无未覆盖；单位不混；多口径只产候选；倒挤可重建。"""

    def setUp(self):
        self.rules = result_comparison.load_rules(RULES)

    def grade(self, metric_type, mql, report, **kwargs):
        return result_comparison.classify(metric_type, mql, report, rules=self.rules, **kwargs)["grade"]

    def test_boundaries_are_unique_and_exhaustive(self):
        # 每处边界恰好命中一个等级，且更大误差总能落到开放末级（无未覆盖区间）
        self.assertEqual(self.grade("RATIO_PERCENT", 14.005, 14.0), "EXACT")
        self.assertEqual(self.grade("RATIO_PERCENT", 14.005001, 14.0), "TOLERANCE")
        self.assertEqual(self.grade("RATIO_PERCENT", 14.05, 14.0), "TOLERANCE")
        self.assertEqual(self.grade("RATIO_PERCENT", 14.050001, 14.0), "SIGNIFICANT")
        self.assertEqual(self.grade("RATIO_PERCENT", 140.0, 14.0), "SIGNIFICANT")

    def test_money_rule_contradiction_is_resolved(self):
        # 改前：§1.2 判不通过 与 §1.1 判精确一致 同时成立；改后必须单一定级
        self.assertEqual(self.grade("MONEY", 160.68, 160.66), "TOLERANCE")
        self.assertEqual(self.grade("MONEY", 160.68, 160.675), "EXACT")
        self.assertEqual(self.grade("MONEY", 160.68, 160.60), "SIGNIFICANT")

    def test_negative_base_is_deterministic(self):
        self.assertEqual(self.grade("MONEY", -100.00, -100.02), "TOLERANCE")
        self.assertEqual(self.grade("MONEY", -100.00, -100.005), "EXACT")

    def test_decimal_percent_is_not_mixed_with_percentage_point(self):
        # 声明小数基准时应归一化后再比对；否则 0.14 与 14.00 会被误判为显著偏差
        self.assertEqual(self.grade("RATIO_PERCENT", 0.14, 14.00, unit_basis="小数"), "EXACT")
        self.assertEqual(self.grade("RATIO_PERCENT", 0.14, 14.00), "SIGNIFICANT")
        self.assertAlmostEqual(result_comparison.normalize_to_unit(0.14, "小数", "百分点"), 14.0)

    def test_consensus_drift_requires_consistent_direction(self):
        kwargs = {"direction_consistent": True}
        self.assertEqual(self.grade("CONSENSUS", 103.0, 100.0, **kwargs), "DRIFT")
        self.assertEqual(self.grade("CONSENSUS", 103.0, 100.0, direction_consistent=False), "SIGNIFICANT")

    def test_preconditions_run_before_comparison(self):
        mql = {"definition_id": "ROE_WEIGHTED", "currency": "CNY", "unit_basis": "小数",
               "period": "2025-12-31", "share_basis_date": "2025-12-31", "adjustment_type": "NONE"}
        report = dict(mql)
        self.assertEqual(result_comparison.check_preconditions(mql, report), [])
        report.update({"currency": "USD", "period": "2024-12-31", "share_basis_date": "2024-12-31"})
        self.assertEqual(result_comparison.check_preconditions(mql, report),
                         ["currency", "period", "share_basis_date"])
        report = dict(mql, unit_basis="%")
        self.assertEqual(result_comparison.check_preconditions(mql, report), ["unit_basis"])

    def test_multi_candidate_never_proves_definition(self):
        outcome = result_comparison.candidates("RATIO_PERCENT", 14.00, {"加权": 14.03, "摊薄": 13.15}, rules=self.rules)
        self.assertFalse(outcome["definition_proven"])
        self.assertEqual(outcome["closest"]["candidate"], "加权")
        self.assertEqual(outcome["closest"]["grade"], "TOLERANCE")
        self.assertEqual([item["candidate"] for item in outcome["ranking"]], ["加权", "摊薄"])
        self.assertIn("仅为候选", outcome["note"])

    def test_share_basis_fixture_keeps_values_distinct(self):
        eps_old = 859.29 / 204.53  # ≈4.20（较小股本基数）
        eps_new = 859.29 / 199.03  # ≈4.32（较大分母→每股更低?此处仅验证基数影响）
        self.assertNotEqual(eps_old, eps_new)
        self.assertEqual(self.grade("MULTIPLE", eps_new, eps_old), "SIGNIFICANT")

    def test_backsolve_fixture_reconstructs(self):
        outcome = result_comparison.verify_backsolve(
            "({total}) - ({payables}) - ({other})",
            {"total": 2361.30, "payables": 363.16, "other": 911.97},
            1086.17, rules=self.rules)
        self.assertAlmostEqual(outcome["computed"], 1086.17, places=6)
        self.assertEqual(outcome["grade"], "EXACT")
        self.assertFalse(outcome["duplicate_deduction_risk"])
        self.assertEqual(outcome["operands"], {"total": 2361.30, "payables": 363.16, "other": 911.97})

    def test_backsolve_flags_duplicate_operand_use(self):
        outcome = result_comparison.verify_backsolve(
            "({total}) - ({other}) - ({other})",
            {"total": 2361.30, "other": 911.97}, 2361.30, rules=self.rules)
        self.assertEqual(outcome["repeated_operands"], ["other"])
        self.assertTrue(outcome["duplicate_deduction_risk"])

    def test_backsolve_rejects_non_arithmetic_formula(self):
        with self.assertRaises(ValueError):
            result_comparison.verify_backsolve("({total}) - unknown_name",
                                               {"total": 1.0}, 1.0, rules=self.rules)

    def test_unknown_metric_type_is_rejected(self):
        with self.assertRaises(ValueError):
            result_comparison.classify("NOT_A_TYPE", 1.0, 1.0, rules=self.rules)


if __name__ == "__main__":
    unittest.main()
