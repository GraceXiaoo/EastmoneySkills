#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_report_html.py — 通用预警监测报告 HTML 构建器（V19）。

输入：report_input.json（冻结正文/表格/图表/来源的统一输入，契约见 references/report-build-pipeline.md）
输出：<workdir>/report_build/<title>.html + content.json + md_footnotes.json（供 build_report_docx.js 生成 Word）

设计要点（快速路径）：模型只需写一份 report_input.json，不再手写任何 HTML/CSS/docx 代码；
HTML 与 Word 同源，HTML 校验内置于本脚本；对话侧交付「目录＋核心概要」由模型按 report-format.md 输出。
"""
from __future__ import annotations

import argparse
import html as H
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

CSS = """
:root{--ink:#1f2933;--sub:#5b6472;--line:#e3e8f0;--red:#d64545;--yel:#c9a13b;--blu:#4a7fd4}
*{box-sizing:border-box}
body{margin:0;background:#f5f7fa;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Segoe UI",Roboto,"Noto Sans CJK SC",sans-serif;font-size:15px;line-height:1.5;letter-spacing:.2px;color:var(--ink)}
main{max-width:1000px;margin:28px auto;background:#fff;border-radius:14px;box-shadow:0 2px 14px rgba(31,41,51,.08);padding:40px 52px}
h1.title{line-height:1.5;text-align:center;margin:0 0 6px;white-space:nowrap;overflow:hidden}
p.meta{font-size:15px;color:var(--ink);text-align:center;line-height:1.5;margin:0 0 22px}
h2{font-size:21px;line-height:1.5;margin:38px 0 6px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:17.5px;line-height:1.5;margin:24px 0 6px;color:#223333}
p{margin:0 0 12px;line-height:1.5}
p.li{margin:0 0 10px;padding-left:6px;line-height:1.5}
.li-n{font-weight:700;margin-right:4px}
figure{margin:26px 0 18px;text-align:center}
figure.fig-limited{max-width:640px;margin-left:auto;margin-right:auto}
figcaption{font-size:13px;line-height:1.5;color:var(--sub);margin-top:10px;text-align:left}
table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.5}
th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top;line-height:1.5}
th{background:#f0f3f8;font-weight:600}
.tw{overflow-x:auto;margin:12px 0 18px}
sup.src{position:relative;margin-left:2px}
.src-btn{font-size:9.5px;line-height:1;color:#1a66ff;cursor:pointer;border-bottom:1px dotted #1a66ff;padding:0 1px}
input[type=checkbox]{display:none}
.src-card{display:none;position:absolute;left:0;top:18px;z-index:30;background:#fff;border:1px solid var(--line);border-radius:8px;box-shadow:0 4px 16px rgba(31,41,51,.14);padding:10px 12px;width:300px;font-size:12px;line-height:1.5;font-weight:400;color:var(--ink)}
.src-card a{color:#1a66ff;word-break:break-all;text-decoration:underline}
.nourl{color:#8a94a6}
.sc-t{font-weight:600}
.sc-m{color:var(--sub)}
sup.src input:checked + .src-btn + .src-card{display:block}
sup.src:hover .src-card,sup.src:focus-within .src-card{display:block}
.warn-card{border-left:4px solid var(--red);background:#fdf3f3;border-radius:0 8px 8px 0;padding:12px 16px;margin:12px 0}
.warn-card.y{border-left-color:var(--yel);background:#fdf9ec}
.warn-card h4{margin:0 0 6px;font-size:15.5px;color:#b03030;line-height:1.5}
.warn-card.y h4{color:#8a6a1c}
.warn-card p{margin:0 0 6px;font-size:14px;line-height:1.5}
.disclaim{margin-top:34px;padding-top:14px;border-top:1px solid var(--line);font-size:12px;line-height:1.5;color:#8a94a6}
.blue-box{border-left:4px solid var(--blu);background:#eef4fd;border-radius:0 8px 8px 0;padding:10px 14px;margin:10px 0}
.tbd{font-size:14px;color:var(--sub);background:#f7f9fc;border:1px dashed var(--line);border-radius:8px;padding:10px 14px;margin:8px 0;line-height:1.5}
.srcidx h3{margin:18px 0 4px}
.srcidx p{font-size:12px;line-height:1.5;margin:0 0 8px}
.srcidx a{color:#1a66ff;text-decoration:underline;word-break:break-all}
.srcidx{margin-top:68px}
"""

VOID = {"input", "br", "meta", "img", "link", "hr", "path", "rect", "line", "circle",
        "marker", "use", "stop", "ellipse", "polygon", "polyline", "tspan"}


def esc(value):
    return H.escape(str(value))


def title_font_size(title: str, max_px: int = 27, min_px: int = 15) -> int:
    """V20：报告标题强制单行。按内容宽度（主内容约 896px×0.94）反推字号，
    放不下则逐级调小，保证不换行（white-space:nowrap）。"""
    units = sum(1.0 if ord(ch) > 0x2E80 else 0.55 for ch in title)
    avail = 896 * 0.94
    return max(min_px, min(max_px, int(avail / units)))


def sup_html(foot, n):
    title, org, dt, url = foot
    url_part = (f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(url[:68])}</a>'
                if url else '<span class="nourl">该条无原文链接</span>')
    return (f'<sup class="src"><input type="checkbox" id="src{n}"><label for="src{n}" class="src-btn">[{n}]</label>'
            f'<span class="src-card"><b>溯源 1 条</b><br>'
            f'<span class="sc-t">{esc(title)}</span><br>'
            f'<span class="sc-m">{esc(org)}｜{esc(dt)}</span><br>{url_part}</span></sup>')


def render_inline(text, foot):
    """把 [n]（n 为溯源编号）转成角标；**粗体** 转 <strong>。"""
    def repl(m):
        n = int(m.group(1))
        return sup_html(foot[n], n) if n in foot else f"[{n}]"
    text = re.sub(r"\[(\d+)\]", repl, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def para_html(text, foot):
    out = []
    for ln in str(text).strip().split("\n"):
        ln = ln.strip()
        if not ln or ln.startswith(("## ", "### ")):
            continue
        m = re.match(r"^(\d+)\.\s+(.*)$", ln)
        if m:
            out.append(f'<p class="li"><span class="li-n">{m.group(1)}.</span>{render_inline(m.group(2), foot)}</p>')
        else:
            out.append(f"<p>{render_inline(ln, foot)}</p>")
    return "\n".join(out)


def bullet_html(items, foot):
    return "\n".join(f'<p class="li"><span class="li-n">•</span>{render_inline(it, foot)}</p>' for it in items)


def table_html(block, foot):
    ths = "".join(f"<th>{esc(h)}</th>" for h in block["cols"])
    rows = []
    for r in block.get("rows", []):
        rows.append("<tr>" + "".join(f"<td>{render_inline(c, foot)}</td>" for c in r) + "</tr>")
    note = (f'<p class="tbd">{render_inline(block["note"], foot)}</p>' if block.get("note") else "")
    return f'<div class="tw"><table><thead><tr>{ths}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>{note}'


def card_html(block, foot):
    kind = block.get("kind", "y")
    cls = "y" if kind == "y" else "r"
    h4 = render_inline(f"**{block['title']}**", foot)
    body = bullet_html([f"**{k}**：{v}" for k, v in block.get("fields", [])], foot)
    return f'<div class="warn-card {cls}"><h4>{h4}</h4>{body}</div>'


def build(input_json: dict, base_dir: Path) -> dict:
    title = input_json["title"]
    foot = {int(k): v for k, v in input_json.get("footnotes", {}).items()}
    parts = [f"<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"UTF-8\">\n"
             f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
             f"<title>{esc(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n<main>\n"]
    parts.append(f'<h1 class="title" style="font-size:{title_font_size(title)}px">{esc(title)}</h1>')
    parts.append(f'<p class="meta">{esc(input_json.get("meta", ""))}</p>')

    def resolve_svg(p: str) -> str:
        f = Path(p)
        if not f.is_absolute():
            f = base_dir / f
        return f.read_text(encoding="utf-8")

    for sec in input_json.get("sections", []):
        if "h1" in sec:
            parts.append(f'<h2>{esc(sec["h1"])}</h2>')
        elif "h2" in sec:
            parts.append(f'<h3>{esc(sec["h2"])}</h3>')
        elif "p" in sec:
            parts.append(para_html(sec["p"], foot))
        elif "list" in sec:
            parts.append(bullet_html(sec["list"], foot))
        elif "table" in sec:
            parts.append(table_html(sec["table"], foot))
        elif "card" in sec:
            parts.append(card_html(sec["card"], foot))
        elif "figures" in sec:
            for fig in sec["figures"]:
                svg = resolve_svg(fig["svg"])
                lim = ' class="fig-limited"' if fig.get("limited") else ""
                parts.append(f'<figure{lim}>{svg}<figcaption>{render_inline(fig["caption"], foot)}</figcaption></figure>')

    # 溯源索引
    used = sorted(foot)
    if used:
        parts.append('<div class="srcidx"><h3>溯源索引</h3>')
        for n in used:
            t, org, dt, url = foot[n]
            link = (f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(url)}</a>'
                    if url else '<span class="nourl">无原文链接</span>')
            parts.append(f'<p><b>[{n}]</b> {esc(t)}｜{esc(org)}｜{esc(dt)}<br>{link}</p>')
        parts.append('</div>')
    parts.append('<p class="disclaim">内容由 AI 生成，仅供研究参考，不构成投资建议。</p>')
    parts.append("</main>\n</body>\n</html>")
    return "".join(parts), foot


def validate(html_doc: str) -> list:
    errors = []

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.stack = []
            self.p_count = 0

        def handle_starttag(self, tag, attrs):
            if tag in VOID:
                return
            self.stack.append(tag)
            if tag == "p":
                self.p_count += 1

        def handle_endtag(self, tag):
            if tag in VOID:
                return
            if not self.stack:
                errors.append(f"unmatched </{tag}>@{self.getpos()}")
                return
            if self.stack[-1] == tag:
                self.stack.pop()
            else:
                errors.append(f"mismatch </{self.stack[-1]}> vs </{tag}>@{self.getpos()}")

    p = P()
    p.feed(html_doc)
    p.close()
    if p.stack:
        errors.append(f"unclosed tags left: {p.stack[:8]}")
    if "<details" in html_doc.lower():
        errors.append("details residue")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="通用预警监测报告 HTML 构建器（V19）")
    parser.add_argument("--input", required=True, help="report_input.json 路径")
    parser.add_argument("--workdir", required=True, help="运行工作目录（章/表/图/来源所在）")
    args = parser.parse_args(argv)
    base = Path(args.workdir).resolve()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    html_doc, foot = build(payload, base)
    rb = base / "report_build"
    rb.mkdir(exist_ok=True)
    out_html = rb / f"{payload['title']}.html"
    out_html.write_text(html_doc, encoding="utf-8")

    def png_size(path: Path):
        """从 PNG 文件头读取位图宽高（零依赖，防止 Word 嵌入按硬编码 h 拉伸字体）。"""
        try:
            with open(path, "rb") as f:
                head = f.read(26)
        except OSError:
            return None
        if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
            return None
        import struct
        w, h = struct.unpack(">II", head[16:24])
        return w, h

    def svg_viewbox(p: str):
        """读取 SVG viewBox 宽高作为图片比例回退（当无 PNG 时）。"""
        f = Path(p)
        if not f.is_absolute():
            f = base / f
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            return None
        m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', text)
        return (float(m.group(1)), float(m.group(2))) if m else None

    # 同源 Word 输入：figures -> image（docx 需 PNG 路径与显示尺寸）
    # V22：高度一律按位图实际比例自动校正（h = w × png_h / png_w），
    # 禁止沿用 report_input 中手写 h（过去曾导致 Word 只拉宽不拉高、字体拉伸变形）。
    def to_docx_sections(sections):
        out = []
        for sec in sections:
            if "figures" in sec:
                for fig in sec["figures"]:
                    if fig.get("png") and fig.get("w"):
                        png = fig["png"]
                        if png.startswith("report_build/"):
                            png = png[len("report_build/"):]  # content.json 位于 report_build 内
                        w = fig["w"]
                        h = fig.get("h", 0)
                        size = png_size(rb / png) or svg_viewbox(fig["svg"])
                        if size:
                            pw, ph = size
                            h = round(w * ph / pw)
                            print(f"FIGFIT {Path(png).name}: {w}x{h} (png {pw}x{ph})")
                        else:
                            print(f"FIGFIT {Path(png).name}: WARN fallback h={h}")
                        out.append({"image": {"path": png, "w": w, "h": h, "note": fig["caption"]}})
            else:
                out.append(sec)
        return out

    content = {
        "title": payload["title"],
        "meta": payload.get("meta", ""),
        "sections": to_docx_sections(payload.get("sections", [])),
    }
    (rb / "content.json").write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    (rb / "md_footnotes.json").write_text(
        json.dumps({str(k): "｜".join(v) for k, v in sorted(foot.items())}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    errors = validate(html_doc)
    print(f"HTML={out_html} ({len(html_doc)} chars)")
    print(f"FOOTNOTES={len(foot)} VALIDATION={'PASS' if not errors else 'FAIL: ' + '; '.join(errors[:5])}")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())