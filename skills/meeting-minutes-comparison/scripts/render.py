#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""占位：本 skill 不使用。完整实现见 skills/overnight-research-brief/scripts/。"""
from __future__ import annotations

import json
import sys

_MESSAGE = "本 skill 未启用 render.py，请使用 overnight-research-brief skill。"


def main() -> int:
    print(json.dumps({"ok": False, "error": "NOT_APPLICABLE", "message": _MESSAGE}, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
