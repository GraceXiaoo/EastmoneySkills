#!/usr/bin/env python3
"""svg_inline.py — SVG样式内联工具：把<style>内class规则展开为元素属性。

用途：LibreOffice（soffice）对SVG内CSS class选择器渲染不全（字体/填充丢失，
实测CSS类文字渲染量仅为内联属性的~28%），导致SVG转PNG位图文字缺失。
本工具在转换前把类样式内联到每个text/rect/line/path/circle元素，
并正确处理自闭合斜杠与font简写展开（font-family内双引号转单引号保证XML合法）。
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def inline_svg_styles(svg_text: str) -> str:
    style_m = re.search(r"<style>(.*?)</style>", svg_text, re.S)
    if not style_m:
        return svg_text
    css = style_m.group(1)
    rules = {}
    for m in re.finditer(r"\.([\w-]+)\s*\{([^}]+)\}", css):
        cls, body = m.group(1), m.group(2)
        props = {}
        for decl in body.split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                props[k.strip()] = v.strip()
        rules[cls] = props

    def expand_font(props):
        out = dict(props)
        f = out.get("font")
        if f:
            fm = re.match(r"(\d+)\s+(\d+)px\s+(.+)", f)
            if fm:
                out["font-weight"] = fm.group(1)
                out["font-size"] = fm.group(2)
                out["font-family"] = fm.group(3).replace('"', "'")
            del out["font"]
        return out

    def el_repl(m):
        tag, attrs = m.group(1), m.group(2)
        self_close = ""
        if attrs.rstrip().endswith("/"):
            self_close = "/"
            attrs = attrs.rstrip()[:-1]
        cls_m = re.search(r'class="([\w -]+)"', attrs)
        if not cls_m:
            return f"<{tag}{attrs}{self_close}>"
        merged = {}
        for c in cls_m.group(1).split():
            if c in rules:
                merged.update(expand_font(rules[c]))
        if not merged:
            return f"<{tag}{attrs}{self_close}>"
        new_attrs = re.sub(r'\s*class="[^"]*"', "", attrs)
        for k in merged:
            new_attrs = re.sub(r"\s*" + re.escape(k) + r'="[^"]*"', "", new_attrs)
        for k, v in merged.items():
            if '"' in v:
                v = v.replace('"', "'")
            new_attrs += f' {k}="{v}"'
        return f"<{tag}{new_attrs}{self_close}>"

    out = re.sub(r"<(text|rect|line|path|circle|tspan)((?:\s[^<>]*?)?/?)>", el_repl, svg_text)
    out = re.sub(r"<style>.*?</style>", "", out, flags=re.S)
    return out


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", help="input SVG file")
    parser.add_argument("--out", help="output SVG path (default: <name>_inlined.svg)")
    args = parser.parse_args(argv)
    src = Path(args.svg).read_text(encoding="utf-8")
    result = inline_svg_styles(src)
    ET.fromstring(result)  # 合法性校验，失败即报错
    out = Path(args.out) if args.out else Path(args.svg).with_name(Path(args.svg).stem + "_inlined.svg")
    out.write_text(result, encoding="utf-8")
    print(f"INLINED={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
