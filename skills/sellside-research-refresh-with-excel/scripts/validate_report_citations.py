"""Validate that source citations in report markdown are consistent with the
source registry.  Used as a runtime gate by build_writing_workbook.
"""
from __future__ import annotations

import re
from typing import Any


_CITATION_RE = re.compile(r"\[(\d+(?:\.\d+)*)\]")


def _citation_ids(report_markdown: str) -> set[str]:
    """Extract numeric citation ids like [1], [1.2] from report markdown."""
    return set(_CITATION_RE.findall(report_markdown or ""))


def validate(report_markdown: str, context: dict[str, Any]) -> list[str]:
    """Return a list of citation errors; empty list means all citations are valid.

    *context* must contain ``sources`` — the source_registry list.  Each cited
    id must map to a source with ``frontend_source_id`` (for non-mcp origins)
    or ``mcp_source_id`` (for mcp origins).
    """
    errors: list[str] = []
    if not report_markdown:
        return errors
    cited = _citation_ids(report_markdown)
    if not cited:
        return errors
    sources = context.get("sources", [])
    known: set[str] = set()
    for src in sources:
        origin = str(src.get("origin", ""))
        if origin == "mcp":
            front = src.get("mcp_source_id")
        else:
            front = src.get("frontend_source_id")
        if front is not None:
            known.add(str(int(front)))
    for cid in sorted(cited):
        if cid not in known:
            errors.append(f"citation [{cid}] has no matching source in registry")
    return errors
