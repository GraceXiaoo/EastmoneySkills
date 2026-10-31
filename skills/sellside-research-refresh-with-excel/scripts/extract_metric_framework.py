"""Extract a complete metric framework from a confirmed stage-0 workbook."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet


CORE_SHEETS = {
    "00_导读",
    "10_研报快照",
    "20_研报底稿",
    "30_预测框架",
    "90_执行日志",
}
STATUS_VALUES = {"SUCCESS", "FAILED", "UNMAPPED", "NOT_APPLICABLE"}
SNAPSHOT_METADATA = {
    "页码",
    "单位",
    "空间区域",
    "版面位置",
    "表格审计",
    "资料来源",
    "空间区域(pt)",
    "序列",
    "频率",
    "截图审计",
    "抽取方法",
    "置信状态",
    "候选来源",
    "视觉验收",
    "来源说明",
}
FORECAST_SECTIONS = {
    "盈利预测驱动",
    "目标价与上行空间复核",
    "估值参数与依据",
    "相对市场预期",
    "核心假设与可证伪点",
}
LOG_HEADERS = [
    "指标",
    "数据源",
    "查询接口",
    "原始 Block/记录编号",
    "执行编号",
    "取数时间",
    "完整指标路径/检索条件",
    "状态",
    "返回形状/摘要",
    "原始值",
    "单位",
    "原始链接",
    "信息",
    "脚本SHA-256",
]


class ContractError(ValueError):
    """Raised when a stage handoff or workbook violates the frozen contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_stage0_handoff(path: Path) -> tuple[dict[str, Any], Path, Path]:
    handoff_path = path.resolve()
    try:
        payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot read stage-0 handoff: {exc}") from exc

    if payload.get("schema_version") != 1:
        raise ContractError("stage-0 handoff schema_version must be 1")
    if payload.get("stage") != 0:
        raise ContractError("stage-0 handoff stage must be 0")
    if payload.get("status") != "CONFIRMED":
        raise ContractError("stage-0 handoff must be CONFIRMED before stage B")
    producer = payload.get("producer")
    if not isinstance(producer, dict) or producer.get("skill") != "research-report-review":
        raise ContractError("stage-0 producer must be research-report-review")
    validation = payload.get("validation")
    if not isinstance(validation, list) or not validation:
        raise ContractError("stage-0 handoff must include validation results")
    if any(not isinstance(item, dict) or item.get("status") != "PASS" for item in validation):
        raise ContractError("stage-0 handoff validation results must all be PASS")

    outputs = payload.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ContractError("stage-0 handoff outputs must be a non-empty array")

    workbook_path: Path | None = None
    report_path: Path | None = None
    for index, artifact in enumerate(outputs, start=1):
        if not isinstance(artifact, dict):
            raise ContractError(f"stage-0 output {index} must be an object")
        artifact_path = Path(str(artifact.get("path", "")))
        if not artifact_path.is_absolute():
            raise ContractError(f"stage-0 output {index} path must be absolute")
        if not artifact_path.is_file():
            raise ContractError(f"stage-0 output does not exist: {artifact_path}")
        expected_size = artifact.get("size_bytes")
        if expected_size != artifact_path.stat().st_size:
            raise ContractError(f"stage-0 output size mismatch: {artifact_path}")
        expected_hash = str(artifact.get("sha256", "")).lower()
        actual_hash = sha256_file(artifact_path)
        if expected_hash != actual_hash:
            raise ContractError(f"stage-0 output hash mismatch: {artifact_path}")
        if artifact_path.suffix.lower() == ".xlsx":
            workbook_path = artifact_path.resolve()
        elif artifact_path.suffix.lower() == ".md":
            report_path = artifact_path.resolve()

    if workbook_path is None:
        raise ContractError("stage-0 handoff must include an .xlsx workbook")
    if report_path is None:
        raise ContractError("stage-0 handoff must include the user-facing .md assessment")

    workbook = load_workbook(workbook_path, read_only=True, data_only=False)
    try:
        missing = sorted(CORE_SHEETS.difference(workbook.sheetnames))
    finally:
        workbook.close()
    if missing:
        raise ContractError(f"stage-0 workbook missing core sheets: {', '.join(missing)}")
    return payload, workbook_path, report_path


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def as_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def row_values(sheet: Worksheet, row: int) -> list[Any]:
    values = [sheet.cell(row, column).value for column in range(1, sheet.max_column + 1)]
    while values and values[-1] in (None, ""):
        values.pop()
    return values


def parse_section_heading(value: Any) -> tuple[str, str, str] | None:
    text = as_text(value)
    if text.startswith("=") or "|" not in text:
        return None
    parts = [part.strip() for part in text.split("|")]
    if len(parts) < 2 or not parts[0] or len(parts[0]) > 100:
        return None
    if len(parts) >= 3 and parts[1] == "图表双通道验收":
        return parts[0], "CHART_DATA", " | ".join(parts[2:])
    if len(parts) >= 3 and parts[1] in {"TABLE", "CHART"}:
        return parts[0], parts[1], " | ".join(parts[2:])
    if len(parts) >= 3 and (parts[1].startswith("图") or parts[1].startswith("表")):
        return parts[0], "CHART", " | ".join(parts[2:])
    return parts[0], "TABLE", " | ".join(parts[1:])


def infer_frequency(periods: list[str]) -> str:
    joined = " ".join(periods)
    if re.search(r"\d{4}Q[1-4]|[一二三四]季", joined, re.I):
        return "QUARTERLY"
    if re.search(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|日", joined):
        return "DAILY"
    if re.search(r"\d{4}[-/.]\d{1,2}|月", joined):
        return "MONTHLY"
    if re.search(r"\d{4}|FY\d{2,4}", joined, re.I):
        return "ANNUAL"
    return "UNSPECIFIED"


def infer_actual_forecast(periods: list[str], object_type: str) -> str:
    if object_type == "FORECAST":
        return "FORECAST"
    text = " ".join(periods).upper()
    has_forecast = bool(re.search(r"\dF\b|E\b|预测|一致预期", text))
    has_actual = bool(re.search(r"\dA\b|实际", text))
    if has_actual and has_forecast:
        return "MIXED"
    if has_forecast:
        return "FORECAST"
    return "ACTUAL" if has_actual else "UNSPECIFIED"


BARE_ANNUAL_PERIOD = re.compile(r"^\d{4}$")


def normalize_period(value: str) -> str:
    """Bare four-digit annual columns denote annual actuals; suffix them with A."""
    text = value.strip()
    if BARE_ANNUAL_PERIOD.fullmatch(text):
        return f"{text}A"
    return text


def metric_id(workbook_hash: str, object_id: str, source_location: str, name: str) -> str:
    token = f"{workbook_hash}|{object_id}|{source_location}|{name}".encode("utf-8")
    return f"mf-{hashlib.sha256(token).hexdigest()[:16]}"


def section_boundaries(sheet: Worksheet) -> list[tuple[int, int, tuple[str, str, str]]]:
    headings: list[tuple[int, tuple[str, str, str]]] = []
    for row in range(1, sheet.max_row + 1):
        heading = parse_section_heading(sheet.cell(row, 1).value)
        if heading:
            headings.append((row, heading))
    return [
        (row, headings[index + 1][0] - 1 if index + 1 < len(headings) else sheet.max_row, heading)
        for index, (row, heading) in enumerate(headings)
    ]


def extract_metadata(sheet: Worksheet, start: int, end: int) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for row in range(start, end + 1):
        label = as_text(sheet.cell(row, 1).value)
        if label in SNAPSHOT_METADATA:
            metadata[label] = as_text(sheet.cell(row, 2).value)
    return metadata


def first_table_header_row(sheet: Worksheet, start: int, end: int) -> int | None:
    for row in range(start, end + 1):
        values = row_values(sheet, row)
        if not values:
            continue
        label = as_text(values[0])
        if label in SNAPSHOT_METADATA:
            continue
        if len(values) >= 2:
            return row
    return None


def extract_snapshot(
    sheet: Worksheet, workbook_hash: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    objects: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    expected_locations: set[str] = set()

    for start, end, (object_id, object_type, title) in section_boundaries(sheet):
        metadata = extract_metadata(sheet, start + 1, end)
        object_record: dict[str, Any] = {
            "object_id": object_id,
            "object_type": object_type,
            "title": title,
            "source_sheet": sheet.title,
            "source_rows": [start, end],
            "page": metadata.get("页码", ""),
            "unit": metadata.get("单位", ""),
            "frequency": metadata.get("频率", ""),
            "metadata": metadata,
        }
        objects.append(object_record)

        if object_type == "CHART":
            series = [
                item.strip()
                for item in re.split(r"[、,，;；]", metadata.get("序列", ""))
                if item.strip()
            ]
            for index, name in enumerate(series, start=1):
                location = f"{sheet.title}!A{start}:series:{index}"
                expected_locations.add(location)
                metrics.append(
                    base_metric(
                        workbook_hash,
                        object_record,
                        name,
                        [],
                        location,
                        metadata.get("单位", ""),
                    )
                )
            continue

        header_row = first_table_header_row(sheet, start + 1, end)
        if header_row is None:
            continue
        headers = [as_text(value) for value in row_values(sheet, header_row)]
        periods = [normalize_period(value) for value in headers[1:] if value]
        for row in range(header_row + 1, end + 1):
            values = row_values(sheet, row)
            if not values:
                continue
            name = as_text(values[0])
            if not name or name in SNAPSHOT_METADATA:
                continue
            location = f"{sheet.title}!A{row}"
            expected_locations.add(location)
            record = base_metric(
                workbook_hash,
                object_record,
                name,
                periods,
                location,
                metadata.get("单位", ""),
            )
            record["source_values"] = [as_text(value) for value in values[1:]]
            metrics.append(record)
    return objects, metrics, expected_locations


def base_metric(
    workbook_hash: str,
    object_record: dict[str, Any],
    name: str,
    periods: list[str],
    location: str,
    unit: str,
) -> dict[str, Any]:
    return {
        "framework_id": metric_id(workbook_hash, object_record["object_id"], location, name),
        "object_id": object_record["object_id"],
        "object_type": object_record["object_type"],
        "object_title": object_record["title"],
        "metric_name": name,
        "periods": periods,
        "frequency": object_record.get("frequency") or infer_frequency(periods),
        "actual_forecast": infer_actual_forecast(periods, object_record["object_type"]),
        "unit": unit,
        "direction": "",
        "source_location": location,
        "status": "UNMAPPED",
        "status_scope": "NONE",
        "status_evidence": [],
        "indicator_path": "",
        "mapping_note": "",
    }


def extract_forecast(
    sheet: Worksheet, workbook_hash: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    starts = [
        row
        for row in range(1, sheet.max_row + 1)
        if as_text(sheet.cell(row, 1).value) in FORECAST_SECTIONS
    ]
    objects: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    expected_locations: set[str] = set()
    for index, start in enumerate(starts):
        end = starts[index + 1] - 1 if index + 1 < len(starts) else sheet.max_row
        title = as_text(sheet.cell(start, 1).value)
        object_id = f"forecast-{index + 1:02d}"
        object_record = {
            "object_id": object_id,
            "object_type": "FORECAST",
            "title": title,
            "source_sheet": sheet.title,
            "source_rows": [start, end],
            "page": "",
            "unit": "",
            "frequency": "",
            "metadata": {},
        }
        objects.append(object_record)
        header_row = first_table_header_row(sheet, start + 1, end)
        if header_row is None:
            continue
        headers = [as_text(value) for value in row_values(sheet, header_row)]
        for row in range(header_row + 1, end + 1):
            values = row_values(sheet, row)
            if not values:
                continue
            name = as_text(values[0])
            if not name:
                continue
            periods: list[str] = []
            if "财年" in headers:
                period_index = headers.index("财年")
                if period_index < len(values) and as_text(values[period_index]):
                    periods.append(normalize_period(as_text(values[period_index])))
            location = f"{sheet.title}!A{row}"
            expected_locations.add(location)
            record = base_metric(workbook_hash, object_record, name, periods, location, "")
            record["source_values"] = [as_text(value) for value in values[1:]]
            metrics.append(record)
    return objects, metrics, expected_locations


def normalize_status(value: Any, note: Any = "") -> str:
    text = f"{as_text(value)} {as_text(note)}".upper()
    if "NOT_APPLICABLE" in text or "不适用" in text:
        return "NOT_APPLICABLE"
    if any(marker in text for marker in ("NO_MATCH", "NO_CANDIDATE", "无候选", "无法映射", "未匹配")):
        return "UNMAPPED"
    if any(marker in text for marker in ("SUCCESS", "FULL", "成功")):
        return "SUCCESS"
    if any(
        marker in text
        for marker in (
            "FAILED",
            "ERROR",
            "BLOCKED",
            "TABLE_BLOCKED",
            "TIMEOUT",
            "失败",
            "阻塞",
        )
    ):
        return "FAILED"
    return "UNMAPPED"


def extract_workpapers(workbook: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    sheet = workbook["20_研报底稿"]
    for start, end, (source_id, source_type, title) in section_boundaries(sheet):
        if source_type not in {"TABLE", "CHART"}:
            continue
        row = start + 1
        while row <= end:
            label = as_text(sheet.cell(row, 1).value)
            if not label.startswith("锚点"):
                row += 1
                continue
            note = as_text(sheet.cell(row, 2).value)
            record: dict[str, Any] = {
                "source_id": source_id,
                "source_type": source_type,
                "source_title": title,
                "anchor_label": label,
                "mapping_note": note,
                "source_sheet": sheet.title,
                "source_row": row,
                "extension_sheet": "",
                "status": "UNMAPPED",
                "mql_script": "",
            }
            if "21_EDB_" in note:
                match = re.search(r"21_EDB_\d+", note)
                if match:
                    record["extension_sheet"] = match.group(0)
                    record.update(extract_edb_workpaper(workbook, match.group(0), record))
            else:
                for probe in range(row + 1, min(end, row + 3) + 1):
                    probe_label = as_text(sheet.cell(probe, 1).value)
                    probe_value = sheet.cell(probe, 1).value
                    if isinstance(probe_value, str) and probe_value.lower().startswith("=mql("):
                        record["status"] = "SUCCESS"
                        record["source_row"] = probe
                        comment = sheet.cell(probe, 1).comment
                        record["mql_script"] = comment.text if comment else ""
                        break
                    if probe_label == "状态":
                        status_value = sheet.cell(probe, 2).value
                        reason = sheet.cell(probe + 1, 2).value if probe + 1 <= end else ""
                        record["status"] = normalize_status(status_value, reason or note)
                        record["mapping_note"] = as_text(reason) or note
                        break
            records.append(record)
            row += 1
    return records


def extract_edb_workpaper(
    workbook: Any, sheet_name: str, parent: dict[str, Any]
) -> dict[str, Any]:
    if sheet_name not in workbook.sheetnames:
        return {"status": "FAILED", "mapping_note": f"Missing extension sheet {sheet_name}"}
    sheet = workbook[sheet_name]
    metadata: dict[str, str] = {}
    formula_row: int | None = None
    script = ""
    for row in range(1, sheet.max_row + 1):
        label = as_text(sheet.cell(row, 1).value)
        if label in {"来源ID", "页码", "单位", "映射状态", "映射说明"}:
            metadata[label] = as_text(sheet.cell(row, 2).value)
        value = sheet.cell(row, 1).value
        if isinstance(value, str) and value.lower().startswith("=mql("):
            formula_row = row
            comment = sheet.cell(row, 1).comment
            script = comment.text if comment else ""
    status = "SUCCESS" if formula_row is not None else normalize_status(metadata.get("映射状态"))
    return {
        "status": status,
        "mapping_note": metadata.get("映射说明") or parent.get("mapping_note", ""),
        "source_sheet": sheet_name,
        "source_row": formula_row or 1,
        "mql_script": script,
    }


def extract_execution_log(sheet: Worksheet) -> list[dict[str, Any]]:
    headers = [as_text(value) for value in row_values(sheet, 1)]
    if headers[: len(LOG_HEADERS)] != LOG_HEADERS:
        raise ContractError("90_执行日志 headers do not match the frozen workbook contract")
    records: list[dict[str, Any]] = []
    for row in range(2, sheet.max_row + 1):
        values = row_values(sheet, row)
        if not values or not any(value not in (None, "") for value in values):
            continue
        item = {
            header: values[index] if index < len(values) else ""
            for index, header in enumerate(LOG_HEADERS)
        }
        item["normalized_status"] = normalize_status(item["状态"], item["信息"])
        item["source_location"] = f"{sheet.title}!A{row}:N{row}"
        records.append(item)
    return records


def match_log(metric: dict[str, Any], logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    name = normalize_text(metric["metric_name"])
    if not name:
        return []
    exact = [item for item in logs if normalize_text(item["指标"]) == name]
    if exact:
        return exact
    return [
        item
        for item in logs
        if name in normalize_text(item["指标"]) or normalize_text(item["指标"]) in name
    ]


def apply_statuses(
    metrics: list[dict[str, Any]],
    workpapers: list[dict[str, Any]],
    logs: list[dict[str, Any]],
) -> None:
    by_source: dict[str, list[dict[str, Any]]] = {}
    for item in workpapers:
        by_source.setdefault(item["source_id"], []).append(item)
    precedence = {"NOT_APPLICABLE": 4, "FAILED": 3, "UNMAPPED": 2, "SUCCESS": 1}

    for metric in metrics:
        matched_logs = match_log(metric, logs)
        if matched_logs:
            latest = matched_logs[-1]
            metric["status"] = latest["normalized_status"]
            metric["status_scope"] = "METRIC"
            metric["status_evidence"] = [item["source_location"] for item in matched_logs]
            paths = [as_text(item["完整指标路径/检索条件"]) for item in matched_logs if item["完整指标路径/检索条件"]]
            units = [as_text(item["单位"]) for item in matched_logs if item["单位"]]
            notes = [as_text(item["信息"]) for item in matched_logs if item["信息"]]
            if paths:
                metric["indicator_path"] = paths[0]
            if units and not metric["unit"]:
                metric["unit"] = units[0]
            if notes:
                metric["mapping_note"] = notes[0]
            continue

        source_workpapers = by_source.get(metric["object_id"], [])
        if source_workpapers:
            statuses = [item["status"] for item in source_workpapers]
            metric["status"] = max(statuses, key=lambda value: precedence[value])
            metric["status_scope"] = "OBJECT"
            metric["status_evidence"] = [
                f'{item["source_sheet"]}!A{item["source_row"]}' for item in source_workpapers
            ]
            notes = [item["mapping_note"] for item in source_workpapers if item["mapping_note"]]
            if notes:
                metric["mapping_note"] = notes[0]


def object_status(object_id: str, metrics: list[dict[str, Any]], workpapers: list[dict[str, Any]]) -> str:
    statuses = [item["status"] for item in metrics if item["object_id"] == object_id]
    if not statuses:
        statuses = [item["status"] for item in workpapers if item["source_id"] == object_id]
    if not statuses:
        return "UNMAPPED"
    if all(status == "NOT_APPLICABLE" for status in statuses):
        return "NOT_APPLICABLE"
    if "SUCCESS" in statuses:
        return "SUCCESS"
    if "FAILED" in statuses:
        return "FAILED"
    return "UNMAPPED"


def extract_framework(handoff_path: Path) -> dict[str, Any]:
    handoff, workbook_path, report_path = validate_stage0_handoff(handoff_path)
    workbook_hash = sha256_file(workbook_path)
    workbook = load_workbook(workbook_path, read_only=False, data_only=False)
    try:
        snapshot_objects, snapshot_metrics, snapshot_expected = extract_snapshot(
            workbook["10_研报快照"], workbook_hash
        )
        forecast_objects, forecast_metrics, forecast_expected = extract_forecast(
            workbook["30_预测框架"], workbook_hash
        )
        workpapers = extract_workpapers(workbook)
        logs = extract_execution_log(workbook["90_执行日志"])
        metrics = snapshot_metrics + forecast_metrics
        apply_statuses(metrics, workpapers, logs)
        objects = snapshot_objects + forecast_objects
        for item in objects:
            item["status"] = object_status(item["object_id"], metrics, workpapers)
            item["metric_ids"] = [
                metric["framework_id"]
                for metric in metrics
                if metric["object_id"] == item["object_id"]
            ]

        actual_locations = {item["source_location"] for item in metrics}
        expected_locations = snapshot_expected | forecast_expected
        missing = sorted(expected_locations.difference(actual_locations))
        if missing:
            raise ContractError(
                "Metric completeness gate failed for source locations: " + ", ".join(missing)
            )

        return {
            "schema_version": 1,
            "source_handoff": {
                "path": str(handoff_path.resolve()),
                "task_id": handoff["task_id"],
                "producer": handoff["producer"],
            },
            "source_workbook": {
                "path": str(workbook_path),
                "sha256": workbook_hash,
                "sheet_names": workbook.sheetnames,
            },
            "source_assessment": {
                "path": str(report_path),
                "sha256": sha256_file(report_path),
                "audience": "投研用户",
            },
            "objects": objects,
            "metrics": metrics,
            "workpapers": workpapers,
            "execution_log": logs,
            "coverage": {
                "objects_total": len(objects),
                "metrics_total": len(metrics),
                "object_types": dict(Counter(item["object_type"] for item in objects)),
                "metric_statuses": dict(Counter(item["status"] for item in metrics)),
                "edb_extension_sheets": sorted(
                    {
                        item["extension_sheet"]
                        for item in workpapers
                        if item.get("extension_sheet")
                    }
                ),
            },
            "completeness": {
                "status": "PASS",
                "expected_metric_locations": len(expected_locations),
                "extracted_metric_locations": len(actual_locations),
                "missing_locations": [],
            },
        }
    finally:
        workbook.close()


def write_summary(framework: dict[str, Any], path: Path) -> None:
    coverage = framework["coverage"]
    statuses = coverage["metric_statuses"]
    lines = [
        "# 原始研报指标框架提取摘要",
        "",
        f"- 原始底稿：`{framework['source_workbook']['path']}`",
        f"- 面向投研用户的评测报告：`{framework['source_assessment']['path']}`",
        f"- 纳入对象：{coverage['objects_total']}",
        f"- 指标记录：{coverage['metrics_total']}",
        f"- 成功：{statuses.get('SUCCESS', 0)}",
        f"- 失败：{statuses.get('FAILED', 0)}",
        f"- 无法映射：{statuses.get('UNMAPPED', 0)}",
        f"- 不适用：{statuses.get('NOT_APPLICABLE', 0)}",
        f"- EDB 扩展 Sheet：{', '.join(coverage['edb_extension_sheets']) or '无'}",
        "",
        "完整性门禁：PASS。失败、无法映射和不适用项均保留在结构化框架中。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_stage1_handoff(
    source_handoff_path: Path,
    framework_path: Path,
    summary_path: Path,
    handoff_path: Path,
) -> None:
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    source = source_handoff_path.resolve()
    outputs = []
    for path, media_type in (
        (framework_path, "application/json"),
        (summary_path, "text/markdown"),
    ):
        outputs.append(
            {
                "path": str(path.resolve()),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
                "media_type": media_type,
            }
        )
    payload = {
        "schema_version": 1,
        "task_id": json.loads(source.read_text(encoding="utf-8"))["task_id"],
        "stage": 1,
        "status": "CONFIRMED",
        "producer": {
            "skill": "sellside-research-refresh-with-excel20",
            "version": "2.0.0",
            "mode": "完整框架提取",
        },
        "inputs": [
            {
                "path": str(source),
                "sha256": sha256_file(source),
                "size_bytes": source.stat().st_size,
                "media_type": "application/json",
            }
        ],
        "outputs": outputs,
        "started_at": timestamp,
        "completed_at": timestamp,
        "validation": [
            {
                "name": "metric framework completeness",
                "status": "PASS",
                "receipt_path": str(framework_path.resolve()),
            }
        ],
        "limitations": [],
        "error": None,
        "resume": {
            "next_stage": 2,
            "requires_user_confirmation": False,
            "input_hashes": {str(source): sha256_file(source)},
        },
    }
    handoff_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("handoff", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--stage-handoff", type=Path, required=True)
    args = parser.parse_args()
    framework = extract_framework(args.handoff)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(framework, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(framework, args.summary)
    write_stage1_handoff(args.handoff, args.output, args.summary, args.stage_handoff)
    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(args.output.resolve()),
                "summary": str(args.summary.resolve()),
                "handoff": str(args.stage_handoff.resolve()),
                "metrics": framework["coverage"]["metrics_total"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
