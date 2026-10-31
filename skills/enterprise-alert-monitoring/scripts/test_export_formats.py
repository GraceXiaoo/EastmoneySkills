#!/usr/bin/env python3
"""Offline tests for dual-format export contract (report-export-formats.md).
HTML + Word only; no Markdown/PDF deliverables. Verifies svg_inline behavior,
source-index rules and spec documentation without generating real files."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_inline import inline_svg_styles

SVG_FIXTURE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 40">
<style>.t{font:600 15px \"PingFang SC\",sans-serif;fill:#1f2933}.gd{stroke:#e3e8f0;stroke-width:1}</style>
<text x="4" y="20" class="t">标题文字</text>
<rect class="gd" x="0" y="30" width="90" height="1"/>
<line x1="0" y1="35" x2="90" y2="35" class="gd"/>
<path class="ce" d="M 5 5 L 50 5"/>
</svg>"""


class SvgInlineTests(unittest.TestCase):
    def test_styles_inlined_and_xml_valid(self):
        out = inline_svg_styles(SVG_FIXTURE)
        self.assertNotIn("<style>", out)
        # 定义了规则的元素class被内联并移除；未定义规则的path允许保留class
        self.assertNotIn('class="t"', out)
        self.assertNotIn('class="gd"', out)
        import xml.etree.ElementTree as ET
        ET.fromstring(out)

    def test_font_shorthand_expanded_with_safe_quotes(self):
        out = inline_svg_styles(SVG_FIXTURE)
        self.assertIn('font-size="15"', out)
        self.assertIn("font-weight=", out)
        # font-family 内引号必须是单引号（保证XML属性合法）
        m = re.search(r'font-family="([^"]*)"', out)
        self.assertIsNotNone(m)
        self.assertNotIn(chr(34), m.group(1))

    def test_self_closing_tags_preserved(self):
        out = inline_svg_styles(SVG_FIXTURE)
        self.assertRegex(out, r"<line[^>]*/>")

    def test_no_style_elements_untouched(self):
        out = inline_svg_styles(SVG_FIXTURE)
        # path无对应class规则时保持原样（class ce未定义）
        self.assertIn("<path", out)

    def test_svg_without_style_returns_unchanged(self):
        plain = "<svg xmlns=\"http://www.w3.org/2000/svg\"><text>ok</text></svg>"
        self.assertEqual(inline_svg_styles(plain), plain)


class DualFormatSpecTests(unittest.TestCase):
    def test_spec_declares_html_word_only(self):
        spec = Path(__file__).resolve().parent.parent / "references" / "report-export-formats.md"
        text = spec.read_text(encoding="utf-8")
        self.assertIn("HTML", text)
        self.assertIn("Word", text)
        self.assertIn("不交付", text)
        self.assertIn("svg_inline", text)
        self.assertIn("200dpi", text)
        self.assertIn("pdftoppm", text)

    def test_spec_forbids_word_footnotes(self):
        spec = Path(__file__).resolve().parent.parent / "references" / "report-export-formats.md"
        text = spec.read_text(encoding="utf-8")
        self.assertIn("禁止用 Word 脚注", text)
        self.assertIn("ExternalHyperlink", text)

    def test_docx_builder_template_exists(self):
        js = Path(__file__).resolve().parent / "build_report_docx.js"
        self.assertTrue(js.exists())
        text = js.read_text(encoding="utf-8")
        self.assertIn("superScript: true", text)
        self.assertIn("ExternalHyperlink", text)
        self.assertIn("HeadingLevel", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
