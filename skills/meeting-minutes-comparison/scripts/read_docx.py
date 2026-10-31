#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read Word docx content and emit JSON to stdout."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def read_docx_content(docx_path: str) -> str:
    """Extract plain text from a docx file."""
    from docx import Document

    doc = Document(docx_path)
    content = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            content.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read docx and output JSON")
    parser.add_argument("--path", required=True, help="Absolute or relative path to docx")
    parser.add_argument("--preview-chars", type=int, default=500, help="Preview length in JSON")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.is_file():
        print(json.dumps({"ok": False, "error": f"file not found: {path}"}, ensure_ascii=False))
        return 1

    try:
        content = read_docx_content(str(path))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "path": str(path)}, ensure_ascii=False))
        return 1

    preview_len = max(0, args.preview_chars)
    result = {
        "ok": True,
        "path": str(path),
        "char_count": len(content),
        "content": content,
        "preview": content[:preview_len] if preview_len else "",
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if content else 1


if __name__ == "__main__":
    raise SystemExit(main())
