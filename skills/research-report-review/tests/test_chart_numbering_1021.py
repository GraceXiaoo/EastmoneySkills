"""U3 回归测试：图表编号口径统一（2026-10-21）。

缺陷背景：`extract_pdf_charts.py` 的 `chart_id` 曾用**跨页全局序号**（`enumerate(blocks, start=1)`），
同一份研报的第 3 页首图被编成 `p3-c7`；而交付证据（`02_evidence_normalized.json` 的
`chart_snapshots`）用**页内图序** `p1-c1` / `p3-c1`。两套编号无法互相引用。
同时 `chart_no` 在标题未识别时会伪造 `图{全局序号}`（第 3 页首图被标成「图8」），属虚构图号。

本契约：
1. `chart_id` = `p{page}-c{页内图序}`，每页从 1 重新计数，与交付证据一致；
2. 只有「图」占图号：`classType=image`，或内容**开头**即图题的 table；数据表裁图不占图号；
3. 标题未识别时 `chart_no` 为空字符串，不得臆造图号。

所有输入为进程内合成的离线夹具，不调用外部服务，也不代表真实工具调用记录。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import extract_pdf_charts  # noqa: E402


def _block(page: int, index: int, content: str = "", class_type: str = "image") -> dict:
    return {
        "page": page,
        "index": index,
        "classType": class_type,
        "content": content,
        "minX": 0.0, "maxX": 100.0, "minY": 0.0, "maxY": 100.0,
    }


def _chart_ids(blocks):
    return [
        f"p{int(b['page'])}-c{order}" if order is not None else ""
        for b, order in zip(blocks, extract_pdf_charts.chart_page_orders(blocks))
    ]


class ChartNumberingTests(unittest.TestCase):
    def test_orders_are_per_page_and_only_figures_take_numbers(self):
        blocks = [
            _block(1, 13, "<table><tr><td>数据</td></tr></table>", "table"),  # 数据表，不占图号
            _block(1, 15),                                                    # 图：股价相对表现
            _block(2, 0, "<table><tr><td>利润表</td></tr></table>", "table"),
            _block(3, 3, "图7：发行人信息披露\n表格内容", "table"),            # 图题在开头 → 图
            _block(3, 7),                                                      # 图：评级及目标价图表
        ]
        self.assertEqual(extract_pdf_charts.chart_page_orders(blocks), [None, 1, None, 1, 2])
        self.assertEqual(_chart_ids(blocks), ["", "p1-c1", "", "p3-c1", "p3-c2"])

    def test_global_order_ids_no_longer_appear(self):
        blocks = [_block(1, 13, ""), _block(1, 14, ""), _block(1, 15, ""),
                  _block(2, 0, ""), _block(3, 7, "")]
        ids = [i for i in _chart_ids(blocks) if i]
        self.assertEqual(ids, ["p1-c1", "p1-c2", "p1-c3", "p2-c1", "p3-c1"])
        self.assertNotIn("p2-c4", ids)
        self.assertNotIn("p3-c5", ids)

    def test_table_referencing_figure_in_body_is_not_a_figure(self):
        # 正文数据表内部引用「图1」不代表它是图，不得占用图号
        block = _block(1, 13, "<table><tr><td>见图1</td></tr></table>", "table")
        self.assertFalse(extract_pdf_charts.is_figure_block(block))
        self.assertEqual(extract_pdf_charts.chart_page_orders([block]), [None])

    def test_unknown_title_does_not_fabricate_chart_no(self):
        chart_no, title, _source, _serial = extract_pdf_charts.parse_text("", "")
        self.assertEqual(chart_no, "")
        self.assertEqual(title, "未识别标题")

    def test_declared_chart_no_is_preserved(self):
        chart_no, title, _source, _serial = extract_pdf_charts.parse_text("图1：股价相对表现\n资料来源：Wind", "")
        self.assertEqual(chart_no, "图1")
        self.assertEqual(title, "股价相对表现")


if __name__ == "__main__":
    unittest.main()
