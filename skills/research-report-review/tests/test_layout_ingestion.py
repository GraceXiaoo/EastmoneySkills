from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prepare_workbook_phases as phases


class LayoutIngestionTests(unittest.TestCase):
    def test_grouped_headers_are_flattened_without_becoming_data(self) -> None:
        block = {"tableContent": '<table><tr><td rowspan="2">Code</td>'
                 '<td colspan="2">Revenue</td></tr><tr><td>2025A</td><td>2026E</td>'
                 '</tr><tr><td>MAR.US</td><td>26,186</td><td>-52</td></tr></table>'}
        headers, rows = phases.block_table(block)
        self.assertEqual(headers, ["Code", "Revenue / 2025A", "Revenue / 2026E"])
        self.assertEqual(rows, [["MAR.US", "26,186", "-52"]])

    def test_rowspan_categories_do_not_shift_brand_values(self) -> None:
        block = {"tableContent": '<table><tr><td>Category</td><td>Brand</td><td>Share</td>'
                 '</tr><tr><td rowspan="2">Luxury</td><td>A</td><td>0.05%</td></tr>'
                 '<tr><td>B</td><td></td></tr></table>'}
        _, rows = phases.block_table(block)
        self.assertEqual(rows, [["Luxury", "A", "0.05%"], ["Luxury", "B", ""]])

    def test_explicit_header_section_and_duplicate_labels(self) -> None:
        block = {"tableContent": '<table><thead><tr><th colspan="2">Metric</th></tr>'
                 '<tr><th>A</th><th>A</th></tr></thead><tbody>'
                 '<tr><td>0</td><td>-</td></tr></tbody></table>'}
        headers, rows = phases.block_table(block)
        self.assertEqual(len(set(headers)), 2)
        self.assertEqual(rows, [["0", "-"]])

    def test_invalid_span_is_not_silently_accepted(self) -> None:
        with self.assertRaisesRegex(ValueError, "span"):
            phases.block_table({"tableContent": '<table><tr><td rowspan="0">A</td>'
                                '</tr><tr><td>1</td></tr></table>'})

    def test_ambiguous_incomplete_grid_is_not_shifted_or_padded(self) -> None:
        with self.assertRaisesRegex(ValueError, "semantic review"):
            phases.block_table({"tableContent": '<table><tr><td>Code</td><td colspan="2">'
                                'Revenue</td></tr><tr><td>2025A</td><td>2026E</td></tr>'
                                '<tr><td>MAR.US</td><td>1</td><td>2</td></tr></table>'})

    def test_summary_only_table_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._run(root, [{"page": 1, "index": 1, "classType": "table",
                              "contentPreview": "A | B", "minX": 0, "minY": 0,
                              "maxX": 100, "maxY": 100}], expect_error=True)

    def _run(self, root: Path, blocks: list[dict], *, expect_error: bool = False) -> dict:
        layout = root / "layout.json"
        layout.write_text(json.dumps({"data": {"textBlocks": blocks}}), encoding="utf-8")
        args = argparse.Namespace(layout_json=layout, census_output=root / "census.json",
                                  evidence_output=root / "evidence.json", company_name="Company",
                                  security_code="MAR.US", report_title="Report", report_date="2026-08-11",
                                  verification_date="2026-10-03")
        if expect_error:
            with self.assertRaisesRegex(ValueError, "LAYOUT_SCHEMA_BLOCKED"):
                phases.from_layout(args)
            return {}
        phases.from_layout(args)
        return json.loads(args.evidence_output.read_text(encoding="utf-8"))

    def test_titles_are_associated_not_counted_as_charts(self) -> None:
        blocks = [
            {"page": 1, "index": 0, "classType": "text", "content": "图表1：Revenue",
             "minX": 0, "minY": 100, "maxX": 100, "maxY": 115},
            {"page": 1, "index": 1, "classType": "image", "content": "",
             "minX": 0, "minY": 20, "maxX": 100, "maxY": 95},
            {"page": 1, "index": 2, "classType": "table", "content": "",
             "tableContent": "<table><tr><td>Metric</td><td>Value</td></tr>"
                             "<tr><td>Profit</td><td>1</td></tr></table>",
             "minX": 200, "minY": 20, "maxX": 300, "maxY": 95},
        ]
        with tempfile.TemporaryDirectory() as directory:
            result = self._run(Path(directory), blocks)
        self.assertEqual(len(result["chart_snapshots"]), 2)
        self.assertEqual(result["chart_snapshots"][0]["title"], "图表1：Revenue")
        self.assertEqual(result["chart_snapshots"][0]["stable_object_key"], "p1-i1")
        self.assertEqual(result["snapshots"][0]["paired_chart_id"], "p1-c2")
        self.assertEqual(result["chart_snapshots"][1]["parsed_table_ids"], ["p1-t1"])
        self.assertTrue(all(c["visual_check"] == "PENDING_REVIEW" for c in result["chart_snapshots"]))


if __name__ == "__main__":
    unittest.main()
