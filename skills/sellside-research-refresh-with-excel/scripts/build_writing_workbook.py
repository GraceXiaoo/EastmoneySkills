"""Build the evidence workbook for a completed research report.

The workbook is intentionally evidence-first: report facts, information items,
forecast assumptions, and report mappings are stored before final prose is
approved.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reproduction_contract import (bind_reference,
                                   load_input, verify_tool_execution, validate_report_query,
                                   unnumbered_title, normalize_report_locations)



FACT_HEADERS = ["证据编号", "source_id", "metric_id", "数据项", "来源/接口", "数据日期", "原始值", "原始单位", "期间语义", "数值语义", "标准化因子", "标准化值", "展示单位", "口径", "原始定位", "报告位置", "来源类型", "MQL区块", "执行请求ID", "返回字段", "覆盖状态", "覆盖需求ID"]
INFO_HEADERS = ["证据编号", "source_id", "标题", "来源机构", "发布日期", "来源类型", "链接/定位", "摘要", "报告位置"]
FORECAST_HEADERS = ["证据编号", "source_id", "metric_id", "项目", "类型", "数值", "依据", "期间", "情景", "模型输出键", "备注", "覆盖需求ID"]
MAPPING_HEADERS = ["报告位置", "证据编号", "使用内容", "状态"]
TRACE_HEADERS = ["数据项", "标准数值", "单位", "数据日期", "来源/接口", "获取日期", "用于报告何处", "证据编号"]

HEADER_FILL = PatternFill(fill_type="solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
SECTION_FILL = PatternFill("solid", fgColor="D9EAF7")
YELLOW_FILL = PatternFill("solid", fgColor="FFF2CC")
WHITE_FONT = Font(color="FFFFFF", bold=True)
BOLD_FONT = Font(bold=True)
WRAP = Alignment(vertical="top", wrap_text=True)
NOWRAP = Alignment(vertical="top", wrap_text=False)
LEFT = Alignment(horizontal="left", vertical="top", wrap_text=False)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
CHOICE_DOWNLOAD_URL = "https://choice.eastmoney.com/downloads"
VALID_LAYOUT_CLASSES = {"financial", "non_financial"}
LAYOUT_RATIO_THRESHOLD = 3
LAYOUT_LONG_SIDE_THRESHOLD = 12


def style_section(worksheet, row, title, column_count):
    """Blue-tinted section header spanning A:H, left-aligned."""
    import math
    column_count = max(column_count, 8)
    worksheet.cell(row=row, column=1, value=title)
    if column_count > 1:
        worksheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=column_count)
    cell = worksheet.cell(row=row, column=1)
    cell.fill = SECTION_FILL
    cell.font = BOLD_FONT
    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    worksheet.row_dimensions[row].height = max(24, 18 * math.ceil(len(title) / 70))


def mql_formula(orientation, selector):
    """Generate =mql("#N",0|1) formula matching research-report-review format."""
    if orientation is None:
        call = f'mql("{selector}")' if selector else "mql()"
    else:
        call = f'mql("{selector}",{orientation})'
    return f"={call}"


def result_geometry(matrix: list[list], orientation: int) -> dict[str, int]:
    """Choice keeps the anchor/status row above the complete result matrix."""
    if not matrix or not matrix[0]:
        raise ValueError("MQL result matrix must be non-empty")
    rows, columns = len(matrix), len(matrix[0])
    if any(len(row) != columns for row in matrix):
        raise ValueError("MQL result matrix must be rectangular")
    return {"mql_formula_cols": columns, "mql_formula_rows": rows,
            "refresh_rows": 1 + (columns if orientation == 1 else rows),
            "refresh_columns": rows if orientation == 1 else columns}


def style_header_cell(cell) -> None:
    """Apply the workbook-wide table-header style without replacing alignment."""
    cell.fill = HEADER_FILL
    cell.font = HEADER_FONT


def style_sheet(sheet) -> None:
    sheet.freeze_panes = "A2"
    if sheet.title != "20_研报底稿":
        for cell in sheet[1]:
            if cell.value is not None:
                style_header_cell(cell)
    for column in sheet.columns:
        width = min(max(len(str(cell.value or "")) for cell in column) + 2, 42)
        sheet.column_dimensions[column[0].column_letter].width = width


def display_width(value: Any) -> int:
    text = str(value or "")
    return sum(2 if unicodedata.east_asian_width(char) in {"W", "F", "A"} else 1 for char in text)


def style_guide_sheet(sheet) -> None:
    for row in sheet.iter_rows():
        for cell in row:
            cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=False)
    for column_letter, minimum in (("B", 48), ("C", 28)):
        longest = max((display_width(cell.value) for cell in sheet[column_letter]), default=0)
        sheet.column_dimensions[column_letter].width = max(minimum, longest + 4)


def validate_mql_workpapers(items: list[dict[str, Any]]) -> None:
    """Validate traceability, indicator coverage, and spill geometry."""
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(items, start=1):
        label = f"mql_workpapers[{index}]"
        for key in (
            "table_id", "source_page", "source_figure_name", "target_table_name",
            "block_selector", "mql_orientation", "_execution", "execution_run_id",
            "result_as_of", "last_result", "required_items", "returned_items", "layout_class",
            "source_page_index", "source_order", "mql_formula_cols", "mql_formula_rows",
            "refresh_rows", "refresh_columns", "refresh_shape_evidence",
        ):
            if key not in item or item[key] in (None, "", []):
                raise ValueError(f"{label} missing required field: {key}")
        if "omitted_items" not in item or not isinstance(item["omitted_items"], list):
            raise ValueError(f"{label} missing required field: omitted_items")
        identity = (str(item["table_id"]), str(item["block_selector"]))
        if identity in seen:
            raise ValueError(f"duplicate MQL table/block: {identity}")
        seen.add(identity)
        if item["mql_orientation"] not in (0, 1):
            raise ValueError(f"{label} mql_orientation must be 0 or 1")
        for key in ("source_page_index", "source_order", "mql_formula_cols", "mql_formula_rows", "refresh_rows", "refresh_columns"):
            if not isinstance(item[key], int) or item[key] < 1:
                raise ValueError(f"{label} {key} must be a positive integer")
        if item["refresh_shape_evidence"] not in {"observed_refresh", "provider_contract", "result_matrix"}:
            raise ValueError(f"{label} refresh_shape_evidence must be observed_refresh or provider_contract")
        layout_class = str(item["layout_class"])
        if layout_class not in VALID_LAYOUT_CLASSES:
            raise ValueError(f"{label} layout_class must be financial or non_financial")
        matrix = item["last_result"]
        if not isinstance(matrix, list) or not matrix or not all(isinstance(row, list) for row in matrix):
            raise ValueError(f"{label} last_result must be a non-empty 2D matrix")
        widths = {len(row) for row in matrix}
        if len(widths) != 1 or 0 in widths:
            raise ValueError(f"{label} last_result must be rectangular")
        rows, columns = len(matrix), widths.pop()
        geometry = result_geometry(matrix, item["mql_orientation"])
        if any(item[name] != value for name, value in geometry.items()):
            raise ValueError(f"{label} refresh dimensions differ from the complete result matrix")
        if item.get("expected_rows", rows) != rows or item.get("expected_columns", columns) != columns:
            raise ValueError(f"{label} expected shape does not match last_result")
        required = {str(value) for value in item["required_items"]}
        returned = {str(value) for value in item["returned_items"]}
        header = [str(value).strip() for value in matrix[0]]
        if any(not value for value in header):
            raise ValueError(f"{label} last_result first row must contain non-empty field names")
        header_fields = set(header)
        if not returned.issubset(header_fields):
            raise ValueError(
                f"{label} last_result header fields must equal returned_items: "
                f"header={sorted(header_fields)!r}, returned={sorted(returned)!r}"
            )
        omitted_raw = item["omitted_items"]
        if not isinstance(omitted_raw, list) or any(not isinstance(value, dict) for value in omitted_raw):
            raise ValueError(f"{label} omitted_items must contain item/reason objects")
        omitted = {str(value.get("item", "")) for value in omitted_raw}
        if "" in omitted or any(not str(value.get("reason", "")).strip() for value in omitted_raw):
            raise ValueError(f"{label} every omitted item requires a reason")
        if returned & omitted or required != returned | omitted:
            raise ValueError(f"{label} required/returned/omitted coverage mismatch")
        reference_orientation = item.get("reference_orientation")
        if reference_orientation is not None:
            if reference_orientation not in (0, 1):
                raise ValueError(f"{label} reference_orientation must be 0 or 1")
            if int(item["mql_orientation"]) != int(reference_orientation):
                raise ValueError(f"{label} must follow the reference report orientation")
        elif (
            columns >= LAYOUT_LONG_SIDE_THRESHOLD
            and columns >= rows * LAYOUT_RATIO_THRESHOLD
            and int(item["mql_orientation"]) != 1
        ):
            raise ValueError(
                f"{label} is disproportionately wide; transpose it so the long dimension runs vertically"
            )
        elif (
            rows >= LAYOUT_LONG_SIDE_THRESHOLD
            and rows >= columns * LAYOUT_RATIO_THRESHOLD
            and int(item["mql_orientation"]) != 0
        ):
            raise ValueError(
                f"{label} is already vertically oriented; keep the original matrix direction"
            )


def build_mql_sheet(workbook: Workbook, items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Create 20_研报底稿 with =mql() formula anchors, matching research-report-review format.

    Each source group gets a blue-tinted section header (merged A:H), metadata rows,
    then =mql("#N",0|1) formula anchors with MQL script in cell comments.
    Spill area below each formula is left blank for Choice add-in refresh.
    """
    validate_mql_workpapers(items)
    sheet = workbook.create_sheet("20_研报底稿")
    sheet.sheet_view.showGridLines = False
    current_row = 1
    anchors: dict[str, dict[str, Any]] = {}
    occupied: list[tuple[int, int, int, int, str]] = []

    # Group items by source (table_id / source figure)
    grouped: dict[str, list[dict[str, Any]]] = {}
    ordered_items = sorted(items, key=lambda item: (item["source_page_index"], item["source_order"], str(item["table_id"])))
    for item in ordered_items:
        group_key = str(item.get("table_id", ""))
        grouped.setdefault(group_key, []).append(item)

    for group_key, group_items in grouped.items():
        first = group_items[0]
        source_title = query_display_title(first)
        source_page = first.get("source_page", "")
        source_unit = first.get("unit", "")

        # Section header: merged A:H, blue-tinted, left-aligned
        columns = max(8, max((len(item["last_result"][0]) for item in group_items), default=2))
        style_section(sheet, current_row, f'{group_key} | {source_title}', columns)
        current_row += 1

        # Metadata rows
        metadata = (
            ("来源ID", group_key),
            ("页码", source_page),
            ("单位", source_unit),
            ("可刷新锚点数", len(group_items)),
        )
        for label, value in metadata:
            sheet.cell(current_row, 1, label).font = BOLD_FONT
            sheet.cell(current_row, 1).alignment = LEFT
            sheet.cell(current_row, 2, value).alignment = LEFT
            current_row += 1

        # Anchor blocks
        for anchor_index, item in enumerate(group_items, start=1):
            anchor_label = f'锚点{anchor_index} · {item["table_id"]}'
            sheet.cell(current_row, 1, anchor_label).font = BOLD_FONT
            sheet.cell(current_row, 1).alignment = LEFT
            sheet.cell(current_row, 2, f'原始Block {item["block_selector"]}；用于：{item.get("source_figure_name", "")}').alignment = LEFT
            current_row += 1

            # Write =mql() formula with MQL script in comment
            formula = mql_formula(item["mql_orientation"], item["block_selector"])
            anchor = sheet.cell(current_row, 1, formula)
            anchors[item["table_id"]] = {"row": current_row, "item": item}
            anchor.comment = Comment(item["_execution"].script, "sellside-research-refresh-with-excel")
            anchor.fill = YELLOW_FILL
            anchor.font = BOLD_FONT

            # Notice text in column B
            sheet.cell(current_row, 2, "安装Choice加载项并刷新后，本锚点结果将从下一行开始显示；生成文件不预填静态结果。").alignment = NOWRAP

            # Spill area reservation: match research-report-review (len(last_result) + 3 rows gap)
            spill_rows = len(item["last_result"])
            spill_cols = len(item["last_result"][0])
            display_rows = int(item["refresh_rows"])
            display_columns = int(item["refresh_columns"])
            spill = (current_row, 1, current_row + display_rows - 1, display_columns, str(item["table_id"]))
            for top, left, bottom, right, other in occupied:
                intersects = not (spill[2] < top or bottom < spill[0] or spill[3] < left or right < spill[1])
                if intersects:
                    raise ValueError(f'MQL spill collision: {item["table_id"]} vs {other}')
            occupied.append(spill)

            # Advance: formula row + max(spill_rows, display_rows) + 3 gap rows
            current_row += max(spill_rows, display_rows) + 3

        current_row += 1  # extra gap between source groups

    sheet.freeze_panes = "A2"
    # Column widths matching research-report-review
    sheet.column_dimensions["A"].width = 28
    sheet.column_dimensions["B"].width = 90
    for col_idx in range(3, 9):
        sheet.column_dimensions[get_column_letter(col_idx)].width = 18
    return anchors



def query_display_title(item):
    return item.get('display_title') or f"{item.get('display_id', item['table_id'])} {unnumbered_title(item['target_table_name'])}"


def reference_headers(table, obj):
    """header_levels already describes the entire visual header, including leaf cells."""
    headers = table['headers']
    levels = table.get('header_levels', obj.get('header_levels', []))
    if not levels:
        return [headers]
    expanded = []
    for level in levels:
        if len(level) == len(headers):
            expanded.append(list(level))
            continue
        row = [None] * len(headers)
        for label in level:
            if label is None:
                continue
            normalized = re.sub(r'\s+', '', str(label))
            matches = [i for i,h in enumerate(headers) if re.sub(r'\s+', '', str(h)).startswith(normalized)]
            if not matches or any(row[i] is not None for i in matches):
                raise ValueError('compact header groups need explicit aligned header_levels for target columns')
            for i in matches:
                row[i] = label
        expanded.append(row)
    # Repeated copies of a leaf level do not create another visible header row.
    return [row for n,row in enumerate(expanded) if n == 0 or row != expanded[n-1]]


def write_reference_headers(sheet, start, levels):
    width = len(levels[0])
    for offset, level in enumerate(levels):
        for col, value in enumerate(level, 1):
            style_header_cell(sheet.cell(start+offset, col, value))
        sheet.row_dimensions[start+offset].height = 24
    # Expand compact groups horizontally, and vertically span labels with no child.
    for offset, level in enumerate(levels):
        col = 0
        while col < width:
            value = level[col]
            end = col+1
            while value is not None and end < width and level[end] == value:
                end += 1
            if end-col > 1:
                sheet.merge_cells(start_row=start+offset,end_row=start+offset,start_column=col+1,end_column=end)
            elif value is not None:
                bottom = offset+1
                while bottom < len(levels) and levels[bottom][col] is None:
                    bottom += 1
                if bottom-offset > 1:
                    sheet.merge_cells(start_row=start+offset,end_row=start+bottom-1,start_column=col+1,end_column=col+1)
            col = end


def mql_cell_coordinate(item, anchor_row, field, result_row):
    index = item['last_result'][0].index(field)
    if not isinstance(result_row, int) or not 1 <= result_row < len(item['last_result']):
        raise ValueError('reference view points outside actual execution matrix')
    return ((anchor_row+1+index, result_row+1) if item['mql_orientation'] == 1
            else (anchor_row+1+result_row, index+1))


def live_reference_formula(anchor, binding):
    """Locate the refreshed field and record by labels, rather than fixed row offsets."""
    item = anchor['item']
    field, result_row = binding['returned_field'], binding['result_row']
    mql_cell_coordinate(item, anchor['row'], field, result_row)
    matrix = item['last_result']
    first = anchor['row'] + 1
    last = anchor['row'] + item['refresh_rows'] - 1
    end_column = get_column_letter(item['refresh_columns'])
    rectangle = f"'20_研报底稿'!$A${first}:${end_column}${last}"
    field_axis = (f"'20_研报底稿'!$A${first}:$A${last}" if item['mql_orientation'] == 1
                  else f"'20_研报底稿'!$A${first}:${end_column}${first}")
    def literal(value):
        if isinstance(value, (int,float)):
            return str(value)
        return '"'+str(value).replace('"','""')+'"'
    field_match = f'MATCH({literal(field)},{field_axis},0)'
    keys = (item.get('record_key_fields') or item.get('report_contract', {}).get('unique_key_fields')
            or [k for k in ('EM_DATE', 'EM_CODE') if k in matrix[0]])
    if keys and all(k in matrix[0] for k in keys):
        identity = tuple(matrix[result_row][matrix[0].index(k)] for k in keys)
        if sum(tuple(row[matrix[0].index(k)] for k in keys) == identity for row in matrix[1:]) != 1:
            raise ValueError('live reference needs visible record keys identifying one observation')
    predicates = []
    for key in keys:
        if key not in matrix[0]:
            raise ValueError('live record key must be returned as a visible field')
        match = f'MATCH({literal(key)},{field_axis},0)'
        key_range = f'INDEX({rectangle},{match},0)' if item['mql_orientation'] == 1 else f'INDEX({rectangle},0,{match})'
        value = matrix[result_row][matrix[0].index(key)]
        predicate = f'({key_range}={literal(value)})'
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(value)):
            year, month, day = map(int, value.split('-'))
            variants = [predicate, f'({key_range}=DATE({year},{month},{day}))',
                        f'({key_range}="{year}/{month}/{day}")',
                        f'({key_range}="{year}/{month:02d}/{day:02d}")']
            predicate = '(' + '+'.join(variants) + '>0)'
        predicates.append(predicate)
    record_match = f'MATCH(1,INDEX(1*{"*".join(predicates)},0),0)' if predicates else str(result_row+1)
    row, col = (field_match,record_match) if item['mql_orientation'] == 1 else (record_match,field_match)
    return f'=INDEX({rectangle},{row},{col})*{float(binding.get("scale_factor",1))}'


def build_reference_views(workbook: Workbook, tables: list[dict], anchors: dict, objects=None) -> None:
    """Render reference tables separately, linked to live MQL spill cells."""
    if not tables:
        return
    sheet = workbook.create_sheet("16_参考表展示")
    originals = {o['object_id']:o for o in objects or []}
    current = 1
    for table in sorted(tables, key=lambda x: (x["source_page_index"], x["source_order"])):
        sheet.cell(current, 1, table["title"])
        current += 1
        obj = originals.get(table.get('object_id'), {})
        style_header_cell(sheet.cell(current-1,1))
        sheet.row_dimensions[current-1].height = 26
        levels = reference_headers(table,obj)
        write_reference_headers(sheet,current,levels)
        header_row = current+len(levels)-1
        current += len(levels)
        for row in table["rows"]:
            sheet.cell(current, 1, row["label"])
            for col, value in enumerate(row["cells"], 2):
                if isinstance(value, dict):
                    if "formula" in value:
                        formula = value["formula"]
                        if not str(formula).startswith("="):
                            raise ValueError("reference view formula must be an Excel formula")
                    else:
                        formula = live_reference_formula(anchors[value['block_key']], value)
                    sheet.cell(current, col, formula)
                else:
                    # Labels/missing-data reasons only; numerical inputs belong in evidence sheets.
                    if isinstance(value, (int, float)):
                        raise ValueError("reference numeric cells must link to evidence or a formula")
                    cell = sheet.cell(current, col, value)
                    if isinstance(value, str):
                        # Only an explicit {formula: ...} binding is executable.
                        # Plain explanations such as '=股东权益合计(未拆细)'
                        # must remain text when exported to Excel.
                        cell.data_type = 's'
            current += 1
        for footnote in obj.get('footnotes', []):
            sheet.cell(current, 1, str(footnote))
            current += 1
        if obj.get('kind') == '图表' and table.get('status') != 'MISSING':
            current = add_live_chart(sheet, table, obj, header_row, current)
        current += 3


def add_live_chart(sheet, table, obj, header_row, current):
    from openpyxl.chart import LineChart, BarChart, AreaChart, Reference
    spec = obj['chart_spec']
    bindings = table.get('chart_series', [])
    if [b.get('series_id') for b in bindings] != [s['series_id'] for s in spec['series']]:
        raise ValueError('live Excel chart must contain every original series in order')
    first, last = header_row + 1, header_row + len(table['rows'])
    start_col = len(table['headers']) + 3
    # Calculated display area stays outside all refresh rectangles.
    for i,(definition,binding) in enumerate(zip(spec['series'],bindings)):
        source_col = binding['column']
        col = start_col+i
        sheet.cell(header_row,col,definition['name'])
        for r in range(first,last+1):
            src = f'{get_column_letter(source_col)}{r}'
            formula = f'={src}'
            for calculation in spec['calculations']:
                if calculation['operation'] == 'relative_return':
                    formula = f'=({src}/{get_column_letter(source_col)}${first}-1)*{calculation.get("factor",100)}'
                elif calculation['operation'] != 'identity':
                    raise ValueError('live chart calculation requires evaluated evidence')
            sheet.cell(r,col,formula)
    combined = None
    chart_groups = {}
    for i,definition in enumerate(spec['series']):
        kind = definition.get('type',spec['type'])
        if kind in ('line','scatter'):
            chart = LineChart()
        elif kind == 'bar':
            chart = BarChart()
        elif kind == 'area':
            chart = AreaChart()
        else:
            raise ValueError(f'Excel chart type {kind} needs an appropriate renderer; do not substitute another shape')
        chart.add_data(Reference(sheet,min_col=start_col+i,min_row=header_row,max_row=last),titles_from_data=True)
        chart.set_categories(Reference(sheet,min_col=1,min_row=first,max_row=last))
        if kind == 'scatter':
            chart.series[0].graphicalProperties.line.noFill = True
            chart.series[0].marker.symbol = definition.get('marker','circle')
            chart.series[0].marker.size = 6
        color=definition.get('color',['C42B32','264B75','527D58','E5A43A'][i%4]).lstrip('#')
        chart.series[0].graphicalProperties.line.solidFill=color
        if definition['axis'] == 'right':
            chart.y_axis.axId = 200
            chart.y_axis.crosses = 'max'
        chart.y_axis.title=spec['axes'][definition['axis']]['label']+' ('+spec['axes'][definition['axis']]['unit']+')'
        group_key = (type(chart), definition['axis'])
        if group_key in chart_groups:
            chart_groups[group_key].ser.extend(chart.ser)
        elif combined is None:
            combined = chart
            chart_groups[group_key] = chart
        else:
            combined += chart
            chart_groups[group_key] = chart
    combined.title=table['title']
    combined.x_axis.title=spec['x_axis']['label']
    combined.height=13; combined.width=23
    combined.legend = combined.legend if spec['legend'].get('visible',True) else None
    sheet.add_chart(combined,f'A{current+1}')
    return current+28


def _coverage_by_row_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    seen_coverage_ids: set[str] = set()
    for item in items:
        row_id = str(item.get("workbook_row_id", "")).strip()
        coverage_id = str(item.get("coverage_id", "")).strip()
        if not row_id or not coverage_id or row_id in result or coverage_id in seen_coverage_ids:
            raise ValueError("each coverage requirement needs a unique workbook_row_id and coverage_id")
        result[row_id] = item
        seen_coverage_ids.add(coverage_id)
    return result


def hydrate_execution(record: dict[str, Any]) -> dict[str, Any]:
    """Use the saved provider response, never a reconstructed SUCCESS record."""
    captured = verify_tool_execution(record)
    raw = captured.response
    script = captured.script
    execution_id = raw.get("traceparent") or captured.call_id
    blocks = raw.get("result", {}).get("blocks", [])
    if not script or not execution_id or len(blocks) != 1:
        raise ValueError("save one complete executable Block per request with its raw provider output")
    if "response" in record:
        raise ValueError("do not supply a reconstructed response; read the current raw result")
    block = blocks[0]
    # hidden_key is tool presentation metadata. Choice Excel still emits EM_CODE,
    # as observed in the live add-in; its complete matrix determines spill size.
    columns = list(block["columns"])
    rows = block["rows"]
    matrix = [columns] + [[row[name] for name in columns] for row in rows]
    validate_report_query({**record, "request": captured.request}, matrix)
    returned_fields = record["plan"].get("returned_fields")
    if not isinstance(returned_fields, dict) or not set(returned_fields.values()).issubset(columns):
        raise ValueError("plan.returned_fields must map coverage IDs to actual visible provider fields")
    return {**record, "request": captured.request, "raw_execution": raw, "_execution": captured,
            "response": {"status": "SUCCESS", "execution_run_id": execution_id,
                         "block_selector": "#" + str(block["blockId"]),
                         "result_as_of": record["result_as_of"], "last_result": matrix,
                         "returned_fields": returned_fields}}


def workpapers_from_execution_records(
    records: list[dict[str, Any]], coverage_requirements: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build refresh blocks only from immutable successful MQL_TOOLCHAIN records.

    Missing cells are replanned and executed separately; they are never hidden
    as omissions inside a successful workbook block.
    """
    coverage_by_id = {str(item["coverage_id"]): item for item in coverage_requirements}
    workpapers: list[dict[str, Any]] = []
    assigned: set[str] = set()
    seen_calls: set[str] = set()
    seen_scripts: set[str] = set()
    for index, record in enumerate(records, start=1):
        record = hydrate_execution(record)
        call_id = record['tool_execution']['tool_call_id']
        if call_id in seen_calls or record['request']['mql'] in seen_scripts:
            raise ValueError('reuse one successful query across views; do not duplicate calls/scripts as anchors')
        seen_calls.add(call_id)
        seen_scripts.add(record['request']['mql'])
        label = f"mql_execution_records[{index}]"
        plan = record.get("plan")
        request = record.get("request")
        response = record.get("response")
        excel = record.get("excel")
        if not all(isinstance(value, dict) for value in (plan, request, response, excel)):
            raise ValueError(f"{label} needs plan/request/response/excel objects")
        if response.get("status") != "SUCCESS":
            raise ValueError(f"{label} is not a successful MQL_TOOLCHAIN record")
        if re.search(r"ReportBlock\s*\(", request["mql"]) and (
            plan.get("financial_cache_required") or re.search("利润表|现金流量表|资产负债表", request["mql"])
        ):
            evidence = plan.get("indicator_fallback_evidence", [])
            if not evidence or any(not e.get("evidence_locator") or e.get("status") not in {
                "NO_INDICATOR_CANDIDATE", "INDICATOR_EXECUTION_NO_DATA", "INDICATOR_COVERAGE_INCOMPLETE"
            } for e in evidence):
                raise ValueError(f"{label} ReportBlock requires actual indicator fallback evidence")
            evidenced_ids = {str(e.get("coverage_id", "")) for e in evidence}
            if not set(map(str, plan.get("coverage_ids", []))).issubset(evidenced_ids):
                raise ValueError(f"{label} financial ReportBlock needs fallback evidence for each queried metric")
        _require_fields(request, ("mql",), f"{label}.request")
        _require_fields(response, ("execution_run_id", "block_selector", "result_as_of", "last_result", "returned_fields"), f"{label}.response")
        coverage_ids = plan.get("coverage_ids")
        if not isinstance(coverage_ids, list) or not coverage_ids:
            raise ValueError(f"{label}.plan.coverage_ids must be a non-empty list")
        returned_fields = response.get("returned_fields")
        if not isinstance(returned_fields, dict):
            raise ValueError(f"{label}.response.returned_fields must be an object")
        if set(map(str, coverage_ids)) != set(map(str, returned_fields)):
            raise ValueError(
                f"{label} is successful, so every planned coverage item must have a "
                "returned field; replan missing cells as a new query"
            )
        required_items: list[str] = []
        returned_items: list[str] = []
        for coverage_id in map(str, coverage_ids):
            if coverage_id in assigned or coverage_id not in coverage_by_id:
                raise ValueError(f"{label} has duplicate or unknown coverage_id {coverage_id}")
            assigned.add(coverage_id)
            coverage_item = coverage_by_id[coverage_id]
            item_name = str(coverage_item["item"])
            required_items.append(item_name)
            returned_field = str(returned_fields[coverage_id])
            if returned_field != item_name:
                raise ValueError(f"{label} returned alias for {coverage_id} must equal the planned item name")
            if coverage_item.get("disposition") != "mql_returned":
                raise ValueError(f"{label} returned coverage {coverage_id} is not marked mql_returned")
            if str(coverage_item.get("block_key", "")) != str(plan.get("table_id", "")):
                raise ValueError(f"{label} coverage {coverage_id} has a different block_key")
            if str(coverage_item.get("returned_field", "")) != returned_field:
                raise ValueError(f"{label} coverage {coverage_id} has a different returned_field")
            returned_items.append(returned_field)
        item = {
            **plan,
            "_execution": record["_execution"],
            "execution_run_id": response["execution_run_id"],
            "block_selector": response["block_selector"],
            "result_as_of": response["result_as_of"],
            "execution_status": response["status"],
            "last_result": response["last_result"],
            "expected_rows": len(response["last_result"]),
            "expected_columns": len(response["last_result"][0]),
            "required_items": required_items,
            "returned_items": returned_items,
            "omitted_items": [],
            **{key: value for key, value in excel.items() if key in {
                "source_page", "source_page_index", "source_order", "source_figure_name",
                "target_table_name", "layout_class", "reference_orientation", "mql_orientation",
                "mql_formula_cols", "mql_formula_rows", "refresh_rows", "refresh_columns",
                "refresh_shape_evidence",
            }},
        }
        # Caller-supplied 1x1 placeholders and assumed report counts never control
        # where the next anchor starts. Count every actual row, including quarters.
        item.update(result_geometry(item["last_result"], item["mql_orientation"]))
        item["refresh_shape_evidence"] = "result_matrix"
        workpapers.append(item)
    expected_returned = {
        str(item["coverage_id"])
        for item in coverage_requirements
        if item.get("disposition") == "mql_returned"
    }
    if assigned != expected_returned:
        raise ValueError(
            "successful execution records must exactly cover mql_returned requirements; "
            f"missing={sorted(expected_returned - assigned)}, extra={sorted(assigned - expected_returned)}"
        )
    return workpapers


def audit_from_execution_records(
    payload: dict[str, Any], workpapers: list[dict[str, Any]]
) -> dict[str, Any]:
    """Derive the audit from the exact records that produced the workbook."""
    scope = str(payload.get("scope", "")).strip()
    applicability = payload.get("category_applicability")
    if not scope or not isinstance(applicability, dict):
        raise ValueError("scope and category_applicability are required")
    blocks = []
    for item in workpapers:
        blocks.append({
            "key": item["table_id"],
            "display_title": query_display_title(item),
            "status": item["execution_status"],
            "execution_id": item["execution_run_id"],
            "mql_script": item["_execution"].script,
            "columns": list(item["last_result"][0]),
            "expected_rows": item["expected_rows"],
            "expected_columns": item["expected_columns"],
            "mql_orientation": item["mql_orientation"],
            "source_page_index": item["source_page_index"],
            "source_order": item["source_order"],
            "mql_formula_cols": item["mql_formula_cols"],
            "mql_formula_rows": item["mql_formula_rows"],
            "refresh_rows": item["refresh_rows"],
            "refresh_columns": item["refresh_columns"],
            "refresh_shape_evidence": item["refresh_shape_evidence"],
            "layout_class": item["layout_class"],
            "reference_orientation": item.get("reference_orientation"),
            "required_items": item["required_items"],
            "returned_items": item["returned_items"],
            "omitted_items": [],
        })
    return {
        "scope": scope,
        "category_applicability": applicability,
        "coverage_requirements": payload["coverage_requirements"],
        "blocks": blocks,
    }


def _require_rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = payload.get(key)
    if not isinstance(rows, list):
        raise ValueError(f"{key} must be a list")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{key} must contain objects")
    return rows


def _require_fields(row: dict[str, Any], fields: tuple[str, ...], label: str) -> None:
    missing = [field for field in fields if row.get(field) in (None, "", [])]
    if missing:
        raise ValueError(f"{label} missing fields: {missing}")


def _require_keys(row: dict[str, Any], fields: tuple[str, ...], label: str) -> None:
    missing = [field for field in fields if field not in row]
    if missing:
        raise ValueError(f"{label} missing keys: {missing}")


def _source_evidence_map(source_registry: list[dict[str, Any]]) -> dict[str, int]:
    source_ids: set[int] = set()
    evidence_map: dict[str, int] = {}
    for index, source in enumerate(source_registry, start=1):
        _require_fields(source, ("source_id", "origin", "provider", "record_id", "evidence_ids"), f"source_registry[{index}]")
        source_id = int(source["source_id"])
        if source_id in source_ids:
            raise ValueError(f"duplicate source_id: {source_id}")
        source_ids.add(source_id)
        if not isinstance(source["evidence_ids"], list) or not source["evidence_ids"]:
            raise ValueError(f"source_registry[{index}] evidence_ids must be a non-empty list")
        for evidence_id in source["evidence_ids"]:
            key = str(evidence_id)
            if key in evidence_map:
                raise ValueError(f"duplicate source mapping for evidence_id {key}")
            evidence_map[key] = source_id
    return evidence_map


def _append_dict_rows(sheet, rows: list[dict[str, Any]], fields: tuple[str, ...], evidence_map: dict[str, int], label: str) -> None:
    seen_evidence: set[str] = set()
    for index, row in enumerate(rows, start=1):
        _require_keys(row, fields, f"{label}[{index}]")
        _require_fields(row, ("evidence_id", "source_id"), f"{label}[{index}]")
        evidence_id = str(row["evidence_id"])
        if evidence_id in seen_evidence:
            raise ValueError(f"duplicate evidence_id in {label}: {evidence_id}")
        seen_evidence.add(evidence_id)
        if evidence_map.get(evidence_id) != int(row["source_id"]):
            raise ValueError(f"{label}[{index}] source_id does not match source_registry evidence mapping")
        sheet.append([row.get(field, "") for field in fields])


def derive_report_mappings(payload, evidence_rows):
    """Preserve explicit mappings, fill missing uses from existing evidence rows."""
    rows = [dict(r) for r in payload['report_mapping_rows']]
    known = {str(r['evidence_id']) for r in evidence_rows}
    covered = set()
    for mapping in rows:
        _require_fields(mapping, ('report_location', 'evidence_ids', 'use_content', 'status'), 'report mapping')
        if not isinstance(mapping['evidence_ids'], list) or not set(map(str, mapping['evidence_ids'])).issubset(known):
            raise ValueError('report mapping references unknown evidence')
        covered.update(map(str, mapping['evidence_ids']))
    query_ids = {r['plan']['table_id'] for r in payload['mql_execution_records']}
    for row in evidence_rows:
        location = str(row.get('report_location', '')).strip()
        if location in query_ids:
            raise ValueError('report_location must identify a report chapter/table/figure, not a query ID')
        if row['evidence_id'] not in covered and location:
            rows.append({'report_location': location, 'evidence_ids': [row['evidence_id']],
                         'use_content': row.get('item') or row.get('title') or row.get('summary'),
                         'status': '已登记'})
    if evidence_rows and not rows:
        raise ValueError('report evidence exists but 40_报告映射 has no report uses')
    return rows


def validate_source_usage(payload, mappings):
    from validate_report_citations import validate, _citation_ids
    report = payload.get('report_markdown', '')
    registry = payload['source_registry']
    errors = validate(report, {'sources': registry})
    if errors:
        raise ValueError('; '.join(errors))
    cited = _citation_ids(report)
    mapped_ids = {str(e) for row in mappings for e in row['evidence_ids']}
    infos = {str(r['evidence_id']) for r in payload['information_rows']}
    for src in registry:
        front = src.get('mcp_source_id') if src.get('origin') == 'mcp' else src.get('frontend_source_id')
        if front is not None and int(front) in cited:
            evidence = set(map(str, src['evidence_ids']))
            if not evidence & mapped_ids:
                raise ValueError(f'cited source {front} has no report evidence mapping')
            if not evidence & infos:
                raise ValueError(f'cited information source {front} is missing from 20_资讯来源')


def build_trace_sheet(sheet, facts, fact_rows, mappings, records):
    """05 is a formula view of 10, not an independently maintained value table."""
    sheet.append(TRACE_HEADERS)
    columns = {cell.value: cell.column_letter for cell in facts[1]}
    locations = {}
    for mapping in mappings:
        for evidence in mapping['evidence_ids']:
            locations.setdefault(str(evidence), []).append(mapping['report_location'])
    acquired = {r['plan']['table_id']: r['result_as_of'] for r in records}
    for index, fact in enumerate(fact_rows, 2):
        def link(header):
            return f"='10_研报快照'!{columns[header]}{index}"
        used = '；'.join(dict.fromkeys(locations.get(str(fact['evidence_id']), []))) or '未用于正文'
        sheet.append([link('数据项'), link('标准化值'), link('展示单位'), link('数据日期'),
                      link('来源/接口'), fact.get('acquired_at') or acquired.get(fact.get('block_key'), '未登记'),
                      used, link('证据编号')])


def build_execution_log_sheet(workbook, payload, fact_rows, information_rows, forecast_rows,
                              report_mapping_rows, mql_execution_records, mql_workpapers, evidence_map):
    """Build 90_执行日志: MQL execution records, info sources, trace, and report mappings."""
    sheet = workbook.create_sheet("90_执行日志")
    sheet.sheet_state = "hidden"
    current_row = 1

    # Section 1: MQL execution records
    style_section(sheet, current_row, "MQL 执行记录", 14)
    current_row += 1
    log_headers = ["指标/对象", "数据源", "查询接口", "原始Block/记录编号", "执行编号", "取数时间",
                   "返回形状", "单位", "脚本SHA256(前16位)", "状态"]
    for col_idx, header in enumerate(log_headers, 1):
        cell = sheet.cell(current_row, col_idx, header)
        style_header_cell(cell)
    current_row += 1
    for item in mql_workpapers:
        script_hash = item.get("_execution", {}).script_sha256 if hasattr(item.get("_execution", {}), 'script_sha256') else ""
        if not script_hash:
            import hashlib
            script_text = item["_execution"].script if hasattr(item["_execution"], 'script') else str(item.get("mql_script", ""))
            script_hash = hashlib.sha256(script_text.encode("utf-8")).hexdigest()[:16]
        shape = f'{item["expected_rows"]}×{item["expected_columns"]}'
        sheet.cell(current_row, 1, item.get("source_figure_name", item.get("table_id", "")))
        sheet.cell(current_row, 2, "MQL")
        sheet.cell(current_row, 3, "通过MQL工具链获取结构化数据")
        sheet.cell(current_row, 4, item.get("block_selector", "#1"))
        sheet.cell(current_row, 5, item.get("execution_run_id", ""))
        sheet.cell(current_row, 6, item.get("result_as_of", ""))
        sheet.cell(current_row, 7, shape)
        sheet.cell(current_row, 8, item.get("unit", ""))
        sheet.cell(current_row, 9, script_hash)
        sheet.cell(current_row, 10, item.get("execution_status", "SUCCESS"))
        current_row += 1
    current_row += 2

    # Section 2: Information sources (资讯来源)
    style_section(sheet, current_row, "资讯来源", 9)
    current_row += 1
    info_headers = ["证据编号", "source_id", "标题", "来源机构", "发布日期", "来源类型", "链接/定位", "摘要", "报告位置"]
    for col_idx, header in enumerate(info_headers, 1):
        cell = sheet.cell(current_row, col_idx, header)
        style_header_cell(cell)
    current_row += 1
    information_fields = ("evidence_id", "source_id", "title", "provider", "published_at", "source_type", "locator", "summary", "report_location")
    for row in information_rows:
        sheet.append([row.get(field, "") for field in information_fields])
        current_row += 1
    current_row += 2

    # Section 3: Report mappings
    style_section(sheet, current_row, "报告映射", 4)
    current_row += 1
    map_headers = ["报告位置", "证据编号", "使用内容", "状态"]
    for col_idx, header in enumerate(map_headers, 1):
        cell = sheet.cell(current_row, col_idx, header)
        style_header_cell(cell)
    current_row += 1
    for row in report_mapping_rows:
        evidence_ids = row.get("evidence_ids", [])
        sheet.append([row.get("report_location", ""), ";".join(map(str, evidence_ids)),
                      row.get("use_content", ""), row.get("status", "")])
        current_row += 1

    return sheet


def build(
    output: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    meta = payload.get("workbook_meta")
    if not isinstance(meta, dict):
        raise ValueError("workbook_meta must be an object")
    _require_fields(meta, ("subject", "report_date", "data_cutoff", "deliverables"), "workbook_meta")
    mql_execution_records = _require_rows(payload, "mql_execution_records")
    coverage_requirements = _require_rows(payload, "coverage_requirements")
    source_registry = _require_rows(payload, "source_registry")
    fact_rows = _require_rows(payload, "fact_rows")
    information_rows = _require_rows(payload, "information_rows")
    forecast_rows = _require_rows(payload, "forecast_rows")
    report_mapping_rows = _require_rows(payload, "report_mapping_rows")
    coverage = _coverage_by_row_id(coverage_requirements)
    mql_workpapers = workpapers_from_execution_records(mql_execution_records, coverage_requirements)
    objects = bind_reference(payload, mql_workpapers)
    normalize_report_locations(payload, objects)
    report_mapping_rows = derive_report_mappings(payload, evidence_rows=fact_rows + information_rows + forecast_rows)
    validate_source_usage(payload, report_mapping_rows)
    evidence_map = _source_evidence_map(source_registry)

    workbook = Workbook()

    # Sheet 1: 00_导读
    guide = workbook.active
    guide.title = "00_导读"
    guide.sheet_view.showGridLines = False
    guide["A1"] = "研报复现底稿"
    guide["A1"].font = Font(size=16, bold=True)
    guide_rows = [
        ("标的公司", meta["subject"]),
        ("证券代码", meta.get("security_code", "不适用")),
        ("研报标题", meta.get("report_title", meta.get("report_type", "研究报告"))),
        ("研报发布日期", meta["report_date"]),
        ("数据截止日", meta["data_cutoff"]),
        ("币种", meta.get("currency", "按各数据项标注")),
        ("预测期", meta.get("forecast_period", "不适用")),
        ("交付边界", meta["deliverables"]),
        ("刷新说明", "20_研报底稿只保留 MQL 公式；安装 Choice Excel 加载项并刷新后显示结果。"),
        ("备注", meta.get("note", "")),
    ]
    for idx, (label, value) in enumerate(guide_rows, start=3):
        guide.cell(idx, 1, label).font = BOLD_FONT
        guide.cell(idx, 1).alignment = LEFT
        guide.cell(idx, 2, value).alignment = LEFT

    # Add Choice download link (required by validator)
    choice_row = len(guide_rows) + 4
    guide.cell(choice_row, 1, "Choice终端下载").font = BOLD_FONT
    guide.cell(choice_row, 1).alignment = LEFT
    link_cell = guide.cell(choice_row, 2, CHOICE_DOWNLOAD_URL)
    link_cell.hyperlink = CHOICE_DOWNLOAD_URL
    link_cell.style = "Hyperlink"
    link_cell.alignment = LEFT

    # Sheet 2: 10_研报快照 (static snapshot values from this execution)
    snapshot = workbook.create_sheet("10_研报快照")
    snapshot.append(FACT_HEADERS)
    fact_fields = ("evidence_id", "source_id", "metric_id", "item", "source", "data_date", "raw_value", "source_unit", "period_semantics", "value_semantics", "normalization_factor", "normalized_value", "display_unit", "caliber", "raw_locator", "report_location", "source_type", "block_key", "execution_id", "returned_field", "coverage_status", "coverage_id")
    _append_dict_rows(snapshot, fact_rows, fact_fields, evidence_map, "fact_rows")

    # Sheet 3: 20_研报底稿 (=mql() formulas + comments + spill areas)
    anchors = build_mql_sheet(workbook, mql_workpapers)

    # Sheet 4: 30_预测框架
    forecast = workbook.create_sheet("30_预测框架")
    forecast.append(FORECAST_HEADERS)
    forecast_fields = ("evidence_id", "source_id", "metric_id", "item", "value_type", "value", "basis", "period", "scenario", "model_output_key", "note", "coverage_id")
    _append_dict_rows(forecast, forecast_rows, forecast_fields, evidence_map, "forecast_rows")

    # Coverage validation
    workbook_coverage_ids = {str(row["coverage_id"]) for row in fact_rows + forecast_rows}
    expected_coverage_ids = {str(item["coverage_id"]) for item in coverage_requirements}
    if workbook_coverage_ids != expected_coverage_ids:
        missing = sorted(expected_coverage_ids - workbook_coverage_ids)
        extra = sorted(workbook_coverage_ids - expected_coverage_ids)
        raise ValueError(f"workbook coverage mismatch; missing={missing}, extra={extra}")
    for row in fact_rows + forecast_rows:
        evidence_id = str(row["evidence_id"])
        item = coverage.get(evidence_id)
        if item is None or str(item["coverage_id"]) != str(row["coverage_id"]):
            raise ValueError(f"coverage requirement does not match workbook row {evidence_id}")

    # Sheet 5: 90_执行日志 (hidden, contains execution records, info sources, mappings)
    build_execution_log_sheet(workbook, payload, fact_rows, information_rows, forecast_rows,
                              report_mapping_rows, mql_execution_records, mql_workpapers, evidence_map)

    # Apply styles
    for sheet in workbook.worksheets:
        if sheet.title not in ("00_导读", "20_研报底稿", "90_执行日志"):
            style_sheet(sheet)
    style_guide_sheet(guide)

    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)
    return audit_from_execution_records(payload, mql_workpapers)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--input-json",
        type=Path,
        required=True,
        help="JSON file containing the coverage plan, exact MQL execution records, and evidence rows.",
    )
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()
    payload = load_input(args.input_json)
    audit = build(args.output, payload)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
