#!/usr/bin/env python3
"""Offline provenance, frequency, rendering, and CLI checks for the word cloud."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from PIL import Image

import render_wordcloud as w


TARGET = "虚构示例汽车股份有限公司"
SVG_NS = {"svg": "http://www.w3.org/2000/svg"}


class DocumentInspector(HTMLParser):
    """Inspect actual DOM tags, rather than strings inside escaped source titles."""
    def __init__(self):
        super().__init__()
        self.tags = []
        self.visible = []
        self._hidden = 0

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag in {"style", "script"}:
            self._hidden += 1

    def handle_endtag(self, tag):
        if tag in {"style", "script"}:
            self._hidden -= 1

    def handle_data(self, text):
        if not self._hidden:
            self.visible.append(text)


def item(item_id="s1", **changes):
    return {"id": item_id, "title": f"虚构资料 {item_id}", "content": "仅用于离线软件验证的虚构事件材料，不构成企业事实。",
            "source": "虚构示例官网", "published_at": "2026-10-10T09:00:00+08:00",
            "url": f"https://example.com/fictional/{item_id}", "citation": f"[虚构来源 {item_id}]", **changes}


def package(items=None):
    return {"acquisition": "mx-finance-search", "entity": {"name": TARGET, "confirmed": True},
            "context": {"start_date": "2026-09-15", "end_date": "2026-10-15", "data_as_of": "2026-10-15T12:00:00+08:00", "scope": "纯虚构离线软件测试"},
            "news_queries": [], "items": items if items is not None else [item()], "events": []}


def event(event_id="e1", tags=None, refs=None, **changes):
    return {"event_id": event_id, "subject": TARGET, "labels": tags or ["股票停牌"],
            "source_ids": refs or ["s1"], "verified": True, **changes}


def data(events=None):
    return {"events": events if events is not None else [event()]}


class ProvenanceTests(unittest.TestCase):
    def test_duplicate_event_label_and_source_do_not_raise_frequency(self):
        result = w.prepare_labels(package([item(), item("s2")]), data([
            event(tags=["股票停牌", "股票停牌"], refs=["s1", "s1"]),
            event(tags=["股票停牌", "复牌进展"], refs=["s2"]), event("e2")]))
        self.assertEqual(result["unique_event_count"], 2)
        rows = {row["label"]: row for row in result["labels"]}
        self.assertEqual(rows["股票停牌"]["frequency"], 2)
        self.assertEqual(rows["复牌进展"]["frequency"], 1)
        self.assertEqual(result["events"][0]["source_ids"], ["s1", "s2"])
        self.assertEqual(rows["股票停牌"]["sources"][0]["citation"], "[虚构来源 s1]")

    def test_positive_and_negative_labels_share_the_same_counting_rule(self):
        result = w.prepare_labels(package(), data([event(tags=["盈利增长", "业绩亏损"])]))
        self.assertEqual([r["frequency"] for r in result["labels"]], [1, 1])
        self.assertEqual(result["unique_event_count"], 1)

    def test_rejects_unknown_and_malformed_reference_ids(self):
        for refs in (["missing"], [1], "s1"):
            with self.subTest(refs=refs), self.assertRaises(w.InputError):
                w.prepare_labels(package(), data([event(refs=refs)]))

    def test_rejects_affiliate_and_unverified_record(self):
        for changes in ({"subject": "虚构关联公司"}, {"verified": False}, {"verified": "true"}):
            with self.subTest(changes=changes), self.assertRaises(w.InputError):
                w.prepare_labels(package(), data([event(**changes)]))

    def test_rejects_unconfirmed_entity_foreign_channel_and_analysis_prose(self):
        values = [package(), package(), package()]
        values[0]["entity"]["confirmed"] = False
        values[1]["acquisition"] = "other"
        values[2]["analysis_results"] = {"monitoring-overview": "正文"}
        for value in values:
            with self.subTest(value=value), self.assertRaises(w.InputError):
                w.prepare_labels(value, data())

    def test_no_unknown_future_or_different_period_only_support(self):
        for stamp in ("", "not-a-date", "2026-10-15T13:00:00+08:00", "2026-09-14", "2026-10-16"):
            with self.subTest(stamp=stamp), self.assertRaises(w.InputError):
                w.prepare_labels(package([item(published_at=stamp)]), data())

    def test_period_uses_client_local_date_and_inclusive_endpoints(self):
        for stamp in ("2026-09-14T16:00:00Z", "2026-10-15T04:00:00Z"):
            with self.subTest(stamp=stamp):
                result = w.prepare_labels(package([item(published_at=stamp)]), data())
                self.assertEqual(result["unique_event_count"], 1)

    def test_older_background_allowed_only_with_a_current_original_article(self):
        result = w.prepare_labels(package([item(), item("old", published_at="2025-01-01")]), data([event(refs=["s1", "old"])]))
        self.assertEqual(result["events"][0]["period_source_ids"], ["s1"])

    def test_aggregate_alone_cannot_be_an_independent_period_event(self):
        summary = item(material_kind="search_summary", title_origin="material_label")
        with self.assertRaises(w.InputError):
            w.prepare_labels(package([summary]), data())

    def test_requires_actual_original_http_url(self):
        for url in ("", "javascript:alert(1)", "https://user:password@example.com", "https://example.com?access_token=secret"):
            with self.subTest(url=url), self.assertRaises(w.InputError):
                w.prepare_labels(package([item(url=url)]), data())

    def test_preserves_actual_source_metadata_without_fake_citations(self):
        source = item(citation="", source="公告原始机构", url="https://example.com/original/a")
        result = w.prepare_labels(package([source]), data())
        row = result["labels"][0]["sources"][0]
        self.assertEqual(row["citation"], "")
        self.assertEqual(row["url"], source["url"])
        self.assertEqual(row["published_at"], source["published_at"])

    def test_invalid_label_and_input_shapes_rejected(self):
        invalid = [None, [], "股票停牌", [""], ["一"], ["这个事件发生了很多变化，接着继续观察。"], ["https://example.com"], ["1234"]]
        for tags in invalid:
            value = event()
            value["labels"] = tags
            with self.subTest(tags=tags), self.assertRaises(w.InputError):
                w.prepare_labels(package(), data([value]))
        for value in ({}, {"events": {}}, {"events": [], "generated_analysis": "正文"}):
            with self.subTest(value=value), self.assertRaises(w.InputError):
                w.prepare_labels(package(), value)

    def test_no_semantic_labels_or_verification_added_by_script(self):
        value = data([event(tags=["自定义新事项类型"])])
        frozen = copy.deepcopy(value)
        result = w.prepare_labels(package(), value)
        self.assertEqual(value, frozen)
        self.assertEqual(result["labels"][0]["label"], "自定义新事项类型")
        del value["events"][0]["verified"]
        with self.assertRaises(w.InputError):
            w.prepare_labels(package(), value)

    def test_empty_events_returns_empty_manifest_without_png_or_font(self):
        manifest = w.prepare_labels(package([]), data([]))
        rendered, png = w.render(manifest, w.load_style(), "/missing-font.ttf")
        self.assertIsNone(png)
        self.assertIsNone(rendered["image"])
        self.assertEqual(rendered["status"], "empty")
        self.assertEqual(rendered["unique_event_count"], 0)


class RenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = w.resolve_font(None, "股票停牌盈利增长立案调查产能不足")

    def fixture(self, count=12):
        tags = ["股票停牌", "立案调查", "盈利增长", "产能不足", "产品发布", "回款改善", "债务展期", "合同签署", "股东增持", "业绩亏损", "订单增长", "股权冻结"]
        if count > len(tags):
            tags += [f"虚构事项{i}" for i in range(count - len(tags))]
        records = [event(f"e{i}", [tag]) for i, tag in enumerate(tags[:count])]
        records += [event("growth2", ["盈利增长"]), event("growth3", ["盈利增长"])]
        return w.prepare_labels(package(), data(records))

    def test_same_frequency_same_font_and_frequency_monotonic_size(self):
        manifest, _ = w.render(self.fixture(), w.load_style(), self.font)
        sizes = {}
        for word in manifest["rendering"]["layout"]:
            sizes.setdefault(word["frequency"], set()).add(word["font_size"])
        self.assertTrue(all(len(values) == 1 for values in sizes.values()))
        self.assertGreater(next(iter(sizes[3])), next(iter(sizes[1])))

    def test_exact_png_determinism_and_data_uri(self):
        first, png = w.render(self.fixture(), w.load_style(), self.font)
        second, again = w.render(self.fixture(), w.load_style(), self.font)
        self.assertEqual(png, again)
        self.assertEqual(first, second)
        self.assertEqual(base64.b64decode(first["image"]["data_uri"].split(",", 1)[1]), png)
        self.assertEqual(hashlib.sha256(png).hexdigest(), first["image"]["sha256"])

    def test_every_tag_is_horizontal_in_bounds_and_no_rectangles_overlap(self):
        manifest, png = w.render(self.fixture(40), w.load_style(), self.font)
        layout, image = manifest["rendering"]["layout"], manifest["image"]
        self.assertEqual({word["label"] for word in layout}, {row["label"] for row in manifest["labels"]})
        for index, word in enumerate(layout):
            self.assertEqual(word["rotation"], 0)
            left, top, right, bottom = word["bounds"]
            self.assertTrue(0 <= left < right <= image["width"])
            self.assertTrue(0 <= top < bottom <= image["height"])
            self.assertFalse(any(w.overlaps(word["bounds"], prior["bounds"]) for prior in layout[:index]))
        import io
        with Image.open(io.BytesIO(png)) as actual:
            self.assertEqual(actual.size, (image["width"], image["height"]))

    def test_no_word_cap_and_canvas_adapts_for_dense_input(self):
        manifest, _ = w.render(self.fixture(110), w.load_style(), self.font)
        self.assertEqual(len(manifest["rendering"]["layout"]), 110)
        self.assertGreater(manifest["image"]["width"], w.load_style()["width"])

    def test_missing_font_and_missing_glyph_have_actionable_error(self):
        with self.assertRaisesRegex(w.InputError, "--font"):
            w.resolve_font("/does/not/exist.ttf", "股票停牌")
        with self.assertRaisesRegex(w.InputError, "Missing glyphs"):
            w.resolve_font(self.font, "股票停牌\U0010ffff")

    def test_environment_font_is_accepted(self):
        original = os.environ.get(w.FONT_ENV)
        os.environ[w.FONT_ENV] = self.font
        try:
            self.assertEqual(w.resolve_font(None, "股票停牌"), self.font)
        finally:
            if original is None:
                os.environ.pop(w.FONT_ENV, None)
            else:
                os.environ[w.FONT_ENV] = original

    def test_style_cannot_supply_semantics_or_word_drop_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-style.json"
            value = w.load_style()
            value["max_words"] = 3
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(w.InputError):
                w.load_style(path)

    def test_cli_outputs_no_base64_and_never_overwrites_existing_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            news, labels, out = root / "news.json", root / "labels.json", root / "out"
            news.write_text(json.dumps(package(), ensure_ascii=False), encoding="utf-8")
            labels.write_text(json.dumps(data(), ensure_ascii=False), encoding="utf-8")
            command = [sys.executable, "-B", "-X", "utf8", str(Path(w.__file__)), "--news-package", str(news), "--labels", str(labels), "--out", str(out), "--font", self.font]
            first = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertNotIn("data:image", first.stdout)
            png = (out / w.PNG_NAME).read_bytes()
            svg = (out / w.SVG_NAME).read_bytes()
            html = (out / w.HTML_NAME).read_bytes()
            manifest_bytes = (out / w.MANIFEST_NAME).read_bytes()
            manifest = json.loads(manifest_bytes)
            self.assertEqual(svg.decode("utf-8"), manifest["interactive"]["svg"])
            self.assertEqual(hashlib.sha256(svg).hexdigest(), manifest["interactive"]["sha256"])
            self.assertIn(b"<svg", html)
            self.assertEqual({path.name for path in out.iterdir()}, {w.PNG_NAME, w.SVG_NAME, w.HTML_NAME, w.MANIFEST_NAME})
            second = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(second.returncode, 2)
            self.assertEqual((out / w.PNG_NAME).read_bytes(), png)
            self.assertEqual((out / w.SVG_NAME).read_bytes(), svg)
            self.assertEqual((out / w.HTML_NAME).read_bytes(), html)
            self.assertEqual((out / w.MANIFEST_NAME).read_bytes(), manifest_bytes)
            self.assertTrue(news.exists() and labels.exists())

    def test_empty_cli_writes_only_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "out"
            manifest, png = w.render(w.prepare_labels(package([]), data([])), w.load_style())
            w.write_outputs(manifest, png, out)
            self.assertEqual([p.name for p in out.iterdir()], [w.MANIFEST_NAME])
            with self.assertRaises(w.InputError):
                w.write_outputs(manifest, png, out)


class InteractiveRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = w.resolve_font(None, "股票停牌盈利增长立案调查产能不足")

    fixture = RenderingTests.fixture

    def interactive_fixture(self):
        style = w.load_style()
        manifest, png = w.render(self.fixture(), style, self.font)
        return manifest, png, style

    def test_manifest_interactive_contract_and_exact_svg_digest(self):
        manifest, png, style = self.interactive_fixture()
        interactive = manifest["interactive"]
        self.assertEqual(interactive["filename"], w.SVG_NAME)
        self.assertEqual(interactive["html_filename"], w.HTML_NAME)
        self.assertEqual(interactive["mime_type"], "image/svg+xml")
        self.assertEqual(interactive["embedding"], "inline_svg")
        self.assertIs(interactive["uses_scripts"], False)
        self.assertEqual(interactive["sha256"], hashlib.sha256(interactive["svg"].encode("utf-8")).hexdigest())
        self.assertEqual(interactive["svg"], w.build_svg(manifest, style))
        self.assertEqual(base64.b64decode(manifest["image"]["data_uri"].split(",", 1)[1]), png)

    def test_svg_retains_every_layout_word_frequency_and_geometry(self):
        manifest, _, _ = self.interactive_fixture()
        root = ET.fromstring(manifest["interactive"]["svg"])
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual([float(v) for v in root.attrib["viewBox"].split()], [0, 0, manifest["image"]["width"], manifest["image"]["height"]])
        groups = [node for node in root.findall(".//svg:g", SVG_NS) if "wc-word" in node.attrib.get("class", "").split()]
        layout = {word["label"]: word for word in manifest["rendering"]["layout"]}
        self.assertEqual(len(groups), len(layout))
        self.assertEqual({node.attrib["data-label"] for node in groups}, set(layout))
        for group in groups:
            expected = layout[group.attrib["data-label"]]
            self.assertEqual(int(group.attrib["data-frequency"]), expected["frequency"])
            self.assertEqual(group.attrib.get("tabindex"), "0")
            self.assertEqual(group.attrib.get("role"), "img")
            texts = group.findall(".//svg:text", SVG_NS)
            self.assertEqual(len(texts), 1)
            self.assertEqual(texts[0].text, expected["label"])
            self.assertEqual(float(texts[0].attrib["font-size"]), expected["font_size"])
            self.assertEqual(texts[0].attrib["fill"], expected["color"])
            self.assertTrue(any("wc-visual" in node.attrib.get("class", "").split() for node in group.findall("svg:g", SVG_NS)))
            match = re.fullmatch(r"translate\(\s*([-+.\d]+)[\s,]+([-+.\d]+)\s*\)", group.attrib["transform"])
            self.assertIsNotNone(match)
            left, top, right, bottom = expected["bounds"]
            self.assertAlmostEqual(float(match[1]), (left + right) / 2)
            self.assertAlmostEqual(float(match[2]), (top + bottom) / 2)
            self.assertAlmostEqual(float(texts[0].attrib["x"]) + float(match[1]), expected["draw_xy"][0])
            self.assertAlmostEqual(float(texts[0].attrib["y"]) + float(match[2]), expected["baseline_xy"][1])

    def test_svg_hover_and_keyboard_focus_apply_the_configured_emphasis(self):
        manifest, _, style = self.interactive_fixture()
        root = ET.fromstring(manifest["interactive"]["svg"])
        css = "\n".join(node.text or "" for node in root.findall(".//svg:style", SVG_NS))
        hover = manifest["interactive"]["hover"]
        self.assertEqual(hover["scale"], style["hover_scale"])
        self.assertEqual(hover["font_weight"], style["hover_font_weight"])
        self.assertEqual(hover["brightness"], style["hover_brightness"])
        self.assertEqual(hover["transition_ms"], style["transition_ms"])
        self.assertRegex(css, r"\.wc-word(?:-\d+)?:hover\b")
        self.assertRegex(css, r"\.wc-word(?:-\d+)?:focus-within\b")
        self.assertIn(".wc-hover-visual", css)
        self.assertRegex(css, rf"scale\(\s*{re.escape(str(style['hover_scale']))}\s*\)")
        self.assertRegex(css, rf"font-weight\s*:\s*{style['hover_font_weight']}\b")
        self.assertRegex(css, rf"brightness\(\s*{re.escape(str(style['hover_brightness']))}\s*\)")
        self.assertIn(f"{style['transition_ms']}ms", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertRegex(css, r"transition\s*:\s*none")
        self.assertNotRegex(css, r"(?i)@import|url\s*\(")
        self.assertEqual(root.findall(".//svg:script", SVG_NS), [])
        self.assertEqual(root.findall(".//svg:image", SVG_NS), [])

    def test_hover_style_rejects_unsafe_or_ill_typed_values(self):
        invalid = {"hover_scale": [True, "1.18", 0, -1],
                   "hover_font_weight": [True, "700", 0, 1100],
                   "hover_brightness": [True, "0.8", 0, -1],
                   "transition_ms": [True, "160", -1]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "style.json"
            for key, values in invalid.items():
                for value in values:
                    with self.subTest(key=key, value=value):
                        style = w.load_style()
                        style[key] = value
                        path.write_text(json.dumps(style), encoding="utf-8")
                        with self.assertRaises(w.InputError):
                            w.load_style(path)

    def test_emphasized_word_is_on_top_without_duplicate_accessible_content(self):
        manifest, _, _ = self.interactive_fixture()
        root = ET.fromstring(manifest["interactive"]["svg"])
        children = list(root)
        layers = [node for node in children if "wc-hover-layer" in node.attrib.get("class", "").split()]
        self.assertEqual(len(layers), 1)
        layer = layers[0]
        words = [node for node in children if "wc-word" in node.attrib.get("class", "").split()]
        self.assertTrue(all(children.index(node) < children.index(layer) for node in words))
        self.assertEqual(layer.attrib.get("aria-hidden"), "true")
        self.assertEqual({node.text for node in layer.findall(".//svg:text", SVG_NS)}, {word["label"] for word in manifest["rendering"]["layout"]})
        css = "\n".join(node.text or "" for node in root.findall(".//svg:style", SVG_NS))
        self.assertIn(".wc-hover-layer", css)
        self.assertRegex(css, r"pointer-events\s*:\s*none")
        self.assertRegex(css, r":hover\s*~\s*\.wc-hover-layer")

    def test_standalone_html_embeds_actual_svg_and_no_external_code(self):
        manifest, _, _ = self.interactive_fixture()
        html = w.build_html(manifest, manifest["interactive"]["svg"])
        document = DocumentInspector()
        document.feed(html)
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html>"))
        self.assertEqual(sum(tag == "svg" for tag, _ in document.tags), 1)
        self.assertFalse(any(tag == "script" for tag, _ in document.tags))
        self.assertFalse(any(tag == "link" and attrs.get("rel") == "stylesheet" for tag, attrs in document.tags))
        self.assertFalse(any(tag in {"iframe", "object", "embed"} for tag, _ in document.tags))
        self.assertFalse(any(tag == "img" and ".svg" in attrs.get("src", "") for tag, attrs in document.tags))
        self.assertFalse(any(key.lower().startswith("on") for _, attrs in document.tags for key in attrs))
        self.assertIn(TARGET, "".join(document.visible))
        for source in manifest["sources"]:
            self.assertTrue(any(attrs.get("href") == source["url"] for _, attrs in document.tags))
            self.assertIn(source["title"], "".join(document.visible))

    def test_markup_escapes_labels_and_source_metadata_without_visible_internal_ids(self):
        source = item("private-material-id-7ab", title='公告 <img src=x onerror="alert(1)"> & 原文', source="公告机构 <测试>", citation="[虚构原文]")
        raw = w.prepare_labels(package([source]), data([event("private-event-id-f91", ["产能&需求"], [source["id"]])]))
        raw["entity"]["name"] += " <script>alert(1)</script>"
        manifest, _ = w.render(raw, w.load_style(), self.font)
        svg = ET.fromstring(manifest["interactive"]["svg"])
        self.assertEqual(svg.find(".//svg:text", SVG_NS).text, "产能&需求")
        self.assertIn("产能&amp;需求", manifest["interactive"]["svg"])
        document = DocumentInspector()
        document.feed(w.build_html(manifest, manifest["interactive"]["svg"]))
        self.assertFalse(any(tag in {"script", "img"} for tag, _ in document.tags))
        self.assertFalse(any(key.lower().startswith("on") for _, attrs in document.tags for key in attrs))
        visible = "".join(document.visible)
        self.assertIn(source["title"], visible)
        self.assertIn(source["source"], visible)
        self.assertNotIn(source["id"], visible)
        self.assertNotIn("private-event-id-f91", visible)

    def test_empty_events_do_not_emit_interactive_artifacts(self):
        style = w.load_style()
        manifest, png = w.render(w.prepare_labels(package([]), data([])), style)
        self.assertIsNone(manifest["interactive"])
        self.assertIsNone(w.build_svg(manifest, style))
        self.assertIsNone(w.build_html(manifest, None))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "out"
            targets = w.write_outputs(manifest, png, out)
            self.assertEqual({path.name for path in targets}, {w.MANIFEST_NAME})


if __name__ == "__main__":
    unittest.main()
