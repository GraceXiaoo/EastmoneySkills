#!/usr/bin/env python3
"""Create a compact searchable index from one saved MQL context response."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

PATH_RE = re.compile(r"(?:Choice指标|Choice报表|全球宏观数据库|行业经济数据库|大宗商品数据库)\\[^\r\n\"']+")


def strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                yield from strings(json.loads(stripped))
            except json.JSONDecodeError:
                pass
    elif isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--term", action="append", default=[], help="Keep paths matching any term")
    args = parser.parse_args()
    raw = args.input.read_text("utf-8", errors="replace")
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        payload = raw
    candidates: list[str] = []
    seen: set[str] = set()
    for text in strings(payload):
        for candidate in PATH_RE.findall(text):
            clean = candidate.replace("\\\\", "\\").strip()
            if clean not in seen:
                seen.add(clean)
                candidates.append(clean)
    terms = [term.casefold() for term in args.term if term.strip()]
    if terms:
        candidates = [candidate for candidate in candidates if any(term in candidate.casefold() for term in terms)]
    result = {"source": str(args.input), "terms": args.term, "candidate_count": len(candidates), "candidates": candidates}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"status": "PASS", "candidate_count": len(candidates), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
