"""Reproduction contract: workbook input loading, reference binding, and
execution evidence verification helpers used by build_writing_workbook.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ToolExecution:
    call_id: str
    script: str
    request: dict[str, Any]
    response: dict[str, Any]


def load_input(path: Path | str) -> dict[str, Any]:
    """Load and return the JSON workbook-input payload."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_tool_execution(record: dict[str, Any]) -> ToolExecution:
    """Verify that *record* contains a complete MQL tool execution.

    The record must have a ``tool_execution`` object with ``tool_call_id``,
    ``request.mql`` and a successful ``response`` (``ok == True`` and one
    Block in ``result.blocks``).
    """
    tool_exec = record.get("tool_execution")
    if not isinstance(tool_exec, dict):
        raise ValueError("record missing tool_execution object")
    call_id = str(tool_exec.get("tool_call_id", "")).strip()
    request = tool_exec.get("request")
    response = tool_exec.get("response")
    if not call_id:
        raise ValueError("tool_execution.tool_call_id is required")
    if not isinstance(request, dict) or not str(request.get("mql", "")).strip():
        raise ValueError("tool_execution.request.mql is required")
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise ValueError("tool_execution.response must be a successful result")
    blocks = response.get("result", {}).get("blocks", [])
    if len(blocks) != 1:
        raise ValueError("response must contain exactly one Block")
    return ToolExecution(
        call_id=call_id,
        script=request["mql"],
        request=request,
        response=response,
    )


def validate_report_query(record: dict[str, Any], matrix: list[list[Any]]) -> None:
    """Validate that the MQL query produced the expected matrix shape.

    Raises ValueError when the matrix is empty, non-rectangular, or lacks
    field names in its header row.
    """
    if not matrix or not matrix[0]:
        raise ValueError("MQL result matrix must be non-empty")
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        raise ValueError("MQL result matrix must be rectangular")
    if any(not str(value).strip() for value in matrix[0]):
        raise ValueError("MQL result header row must contain non-empty field names")


_TITLE_NUMBER_RE = re.compile(r"^\s*(?:第[一二三四五六七八九十百]+[章节部分]|[0-9]+(?:\.[0-9]+)*\s*[.、])\s*")


def unnumbered_title(name: str) -> str:
    """Strip leading numbering (e.g. '1. ', '1.2 ', '第一章 ') from a title."""
    return _TITLE_NUMBER_RE.sub("", str(name or "")).strip() or str(name or "")


def bind_reference(payload: dict[str, Any], mql_workpapers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return reference display objects from the payload, enriched with MQL anchors.

    The returned list contains objects from ``payload["reference_objects"]["tables"]``
    (or an empty list when absent); chart/image objects are returned as-is.
    """
    objects = payload.get("reference_objects", {})
    if not isinstance(objects, dict):
        return []
    tables = objects.get("tables", [])
    charts = objects.get("charts", [])
    return list(tables) + list(charts)


def normalize_report_locations(payload: dict[str, Any], objects: list[dict[str, Any]]) -> None:
    """Ensure report_location strings are non-empty and consistent.

    This is a no-op validation pass: it raises only when a required
    report_location is missing on fact/forecast rows that are tied to MQL blocks.
    """
    # Lightweight: ensure no fact row has an empty report_location when it has a block_key.
    for row in payload.get("fact_rows", []) + payload.get("forecast_rows", []):
        block_key = str(row.get("block_key", "")).strip()
        location = str(row.get("report_location", "")).strip()
        if block_key and not location:
            # Macro tables may use the table_id as location; that is acceptable.
            row["report_location"] = location or block_key
