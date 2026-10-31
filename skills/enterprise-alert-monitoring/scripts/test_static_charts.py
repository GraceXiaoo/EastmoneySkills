#!/usr/bin/env python3
"""Offline tests for render_static_charts.py; XML validity + format rules."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import render_static_charts as rc


VOLUME = [
    {"bucket": "9/23–9/29", "total": 5, "focus": 2},
    {"bucket": "9/30–10/6", "total": 1, "focus": 0},
    {"bucket": "10/7–10/13", "total": 0, "focus": 0},
    {"bucket": "10/14–10/23", "total": 4, "focus": 3},
]

DISTRIBUTION = [
    {"grade": "红", "label": "红色预警", "count": 1},
    {"grade": "黄", "label": "黄色预警", "count": 2},
    {"grade": "蓝", "label": "蓝色观察", "count": 3},
    {"grade": "灰", "label": "不设预警（利好或已解除）", "count": 3},
]

CHAIN = {
    "warning": "红色预警：股价资金负反馈｜持续发酵",
    "sources": ["10-22 创本轮新低 600 元", "四个月累计 −56.82%，市值蒸发 9,739 亿元"],
    "mechanism": {"title": "传导机制：融资盘去杠杆", "details": ["板块融资余额较峰值降45%", "单日净卖出17亿元"]},
    "trigger": {"condition": "维持百亿级放量且股价下行"},
    "impact": {"details": ["估值中枢或继续下移", "属交易面风险，非经营恶化"]},
    "nodes_future": ["10-29 董事会（三季报+回购注销）"],
    "observations": ["CPO 技术路线替代（远期）"],
    "obs_reasons": ["待观察：商用时间表缺失"],
    "hedge": "黄色预警按证据缺失降级观察｜数据截至报告当日",
}

TIMELINE = {
    "as_of": "10-23",
    "windows": [["+7天", 7], ["+30天", 30], ["+90天", 90]],
    "events": [
        {"title": "10-29 董事会：三季报+回购注销", "days": 6, "cert": "红", "note": "公告排定｜表决结果当日落地", "up": True},
        {"title": "11-22 中石科技尾款支付", "days": 30, "cert": "黄", "note": "合同约定｜与解约预期并存", "up": True},
        {"title": "2026-12 解除合同并要求退款", "days": 60, "cert": "黄", "note": "单方主张｜风险标注：负面", "up": True},
        {"title": "2026-11 铜陵三期投产", "days": 20, "cert": "蓝", "note": "建设排期｜正面节点"},
    ],
}


class VolumeTests(unittest.TestCase):
    def test_renders_valid_svg_with_legend_and_note(self):
        svg = rc.render_volume_chart([dict(r) for r in VOLUME])
        ET.fromstring(svg)
        for token in ("资讯篇数", "其中回购类", "9/23–9/29"):
            self.assertIn(token, svg)
        self.assertIn('stroke-dasharray="7,4"', svg)
        # V20：统计口径备注不再绘制在 SVG 内（并入图下说明），防止图表下出现两段备注
        self.assertNotIn("统计范围为本次", svg)
        self.assertNotIn('<text x="56" y="352" class="note">', svg)

    def test_without_focus_line_and_custom_name(self):
        svg = rc.render_volume_chart([{"bucket": "W1", "total": 3}, {"bucket": "W2", "total": 1}])
        ET.fromstring(svg)
        self.assertNotIn("其中回购类", svg)
        self.assertIn("资讯篇数", svg)

    def test_zero_bucket_renders_without_negative_rect(self):
        svg = rc.render_volume_chart([{"bucket": "W1", "total": 0}, {"bucket": "W2", "total": 2}])
        ET.fromstring(svg)
        self.assertNotIn('height="-', svg)

    def test_rejects_bad_rows(self):
        for bad in ([], [{"bucket": "W"}], [{"bucket": "W", "total": -1}],
                    [{"bucket": "W", "total": "3"}, {"bucket": "W2", "total": 1}],
                    [{"bucket": "W", "total": 1, "focus": "x"}, {"bucket": "W2", "total": 1}]):
            with self.subTest(bad=bad), self.assertRaises(rc.InputError):
                rc.render_volume_chart(bad)


class DistributionTests(unittest.TestCase):
    def test_renders_valid_donut_with_counts_and_meanings(self):
        svg = rc.render_distribution_chart([dict(r) for r in DISTRIBUTION])
        ET.fromstring(svg)
        self.assertIn("9 项", svg)
        for token in ("红色：正在发生，须立即处置", "不设预警（利好或已解除）", "分级依据：发酵判断"):
            self.assertIn(token, svg)

    def test_zero_total_renders_without_divide_error(self):
        svg = rc.render_distribution_chart([{"grade": "红", "label": "红色预警", "count": 0}])
        ET.fromstring(svg)
        self.assertIn("0 项", svg)

    def test_rejects_bad_grade_or_count(self):
        for bad in ([], [{"grade": "紫", "label": "x", "count": 1}],
                    [{"grade": "红", "label": "", "count": 1}], [{"grade": "红", "count": 1}]):
            with self.subTest(bad=bad), self.assertRaises(rc.InputError):
                rc.render_distribution_chart(bad)


class ChainTests(unittest.TestCase):
    def test_renders_valid_chain_with_sections_and_no_badge(self):
        svg = rc.render_chain_chart(json.loads(json.dumps(CHAIN)))
        ET.fromstring(svg)
        for token in ("源头事实（已发生）", "传导机制与触发条件", "未来节点与潜在影响", "证据不足待观察",
                      "持续恶化条件", "潜在影响（条件性）", "关键未来节点"):
            self.assertIn(token, svg)
        # V21：观察项文本按列宽自动换行后仍在图中（不删字，仅断行）
        self.assertIn("待观察：商用时间表缺", svg)
        self.assertIn("失", svg)
        # V19：右上角说明框已移除（badge 专用 class gr 不再出现），warning 只进 <title>
        self.assertNotIn('class="gr"', svg)

    def test_boxes_never_overflow_viewbox(self):
        svg = rc.render_chain_chart(json.loads(json.dumps(CHAIN)))
        ET.fromstring(svg)
        m = re.search(r'viewBox="0 0 1200 ([0-9.]+)"', svg)
        H = float(m.group(1))
        root = ET.fromstring(svg)
        ns = {"s": "http://www.w3.org/2000/svg"}
        for g in root.findall(".//s:g", ns):
            tr = g.get("transform", "")
            mm = re.match(r"translate\(([\d.]+)[ ,]([\d.]+)\)", tr)
            if not mm:
                continue
            gy = float(mm.group(2))
            rect = g.find("s:rect", ns)
            if rect is None:
                continue
            bottom = gy + float(rect.get("height", "0"))
            self.assertLessEqual(bottom + 4, H, f"box bottom {bottom} exceeds viewBox height {H}")

    def test_rejects_missing_keys(self):
        for missing in ("warning", "sources", "mechanism", "trigger", "impact"):
            data = json.loads(json.dumps(CHAIN))
            del data[missing]
            with self.subTest(missing=missing), self.assertRaises(rc.InputError):
                rc.render_chain_chart(data)

    def test_long_lines_are_truncated_not_overflowing(self):
        data = json.loads(json.dumps(CHAIN))
        data["sources"] = ["极长的事件描述" * 10]
        svg = rc.render_chain_chart(data)
        ET.fromstring(svg)
        self.assertNotIn("极长的事件描述极长的事件描述极长的事件描述极长的事件描述极长的事件描述极长的事件描述极长的事件描述极长的事件描述极长", svg)


class TimelineTests(unittest.TestCase):
    def test_renders_valid_timeline_with_windows_and_colors(self):
        svg = rc.render_timeline_chart(json.loads(json.dumps(TIMELINE)))
        ET.fromstring(svg)
        for token in ("T0 = 10-23", "+7天", "+30天", "+90天", "公告排定｜表决结果当日落地",
                      "红色：高确定性、高影响", "以公司公告为准"):
            self.assertIn(token, svg)
        self.assertIn('class="nr"', svg)
        self.assertIn('class="ny"', svg)
        self.assertIn('class="nb"', svg)

    def test_all_events_above_axis_still_render(self):
        data = json.loads(json.dumps(TIMELINE))
        for ev in data["events"]:
            ev["up"] = True
        svg = rc.render_timeline_chart(data)
        ET.fromstring(svg)
        self.assertEqual(svg.count('class="nr"') + svg.count('class="ny"') + svg.count('class="nb"'),
                         len(data["events"]) + 3)  # 3 legend swatches

    def test_no_box_overlap_and_balanced_sides(self):
        """V8/V20: 事件盒上下均匀分布且不重叠（V20 盒高66、行距84、轴Y=320）。"""
        import re as _re
        data = json.loads(json.dumps(TIMELINE))
        svg = rc.render_timeline_chart(data)
        ET.fromstring(svg)
        boxes = [(float(m.group(1)), float(m.group(2)))
                 for m in _re.finditer(r'translate\((\d+\.?\d*),(\d+\.?\d*)\)"><rect class="[nryb]+" width="320" height="66"', svg)]
        self.assertTrue(len(boxes) >= len(data["events"]))
        # 同侧不重叠：按y分组，每组盒高66、步长>=66
        ys = sorted({round(y, 1) for _, y in boxes})
        for a, b in zip(ys, ys[1:]):
            self.assertGreaterEqual(b - a, 66.0 - 1e-6, f"vertical gap {b-a} < box height")
        # 上下两侧都有分布（除非事件数<=1）
        above_axis = [y for _, y in boxes if y + 66 <= 320]
        below_axis = [y for _, y in boxes if y >= 320]
        self.assertTrue(above_axis and below_axis)

    def test_volume_legend_at_top(self):
        """V15: 声量图图例位于图表顶部（标题下方、绘图区上方），避开斜排日期区。"""
        svg = rc.render_volume_chart([dict(r) for r in VOLUME])
        ET.fromstring(svg)
        m = __import__("re").search(r'<rect x="(\d+\.?\d*)" y="(\d+)" width="13" height="13" rx="2.5" fill="#4a7fd4"/>', svg)
        self.assertIsNotNone(m)
        legend_y = float(m.group(2))
        self.assertLess(legend_y, 100)   # 图例在绘图区上方（zero_y=224）
        self.assertGreater(legend_y, 26) # 在标题(26)下方

    def test_rejects_bad_events(self):
        base = json.loads(json.dumps(TIMELINE))
        for bad in ([], [{"title": "x"}], [{"title": "x", "days": 6, "cert": "紫"}],
                    [{"title": "x", "days": -1, "cert": "红"}]):
            data = json.loads(json.dumps(base))
            data["events"] = bad
            with self.subTest(bad=bad), self.assertRaises(rc.InputError):
                rc.render_timeline_chart(data)
        with self.assertRaises(rc.InputError):
            rc.render_timeline_chart({"events": TIMELINE["events"]})


class CLITests(unittest.TestCase):
    def test_cli_writes_file_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            data_file = root / "data.json"
            data_file.write_text(json.dumps([dict(r) for r in VOLUME]), encoding="utf-8")
            out = root / "chart.svg"
            self.assertEqual(rc.main(["--mode", "volume", "--data", str(data_file), "--out", str(out)]), 0)
            ET.fromstring(out.read_text(encoding="utf-8"))
            self.assertEqual(rc.main(["--mode", "volume", "--data", str(data_file), "--out", str(out)]), 2)
            bad = root / "bad.json"
            bad.write_text("[]", encoding="utf-8")
            self.assertEqual(rc.main(["--mode", "volume", "--data", str(bad), "--out", str(root / "b.svg")]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
