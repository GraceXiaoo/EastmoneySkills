"""
保存报告脚本

报告产物（四类，缺一不可）：
- MD    ：{title}.md          —— 报告源文件
- Word  ：{title}.docx        —— 可编辑文档
- PDF   ：{title}.pdf         —— 固定版式（优先用本机 Word 从 docx 导出，与 Word 版式完全一致）
- HTML  ：{title}.html        —— 分享链接的载体页面（自包含：内嵌 CSS + 内嵌图片 base64）

分享链接由 HTML 页面经「发布应用」生成，详见 SKILL.md 输出章节。
支持格式：md、docx、pdf、html、all（默认 all，即四类产物全部生成）

PDF 生成策略（优先级从高到低）：
1. Windows 且已安装 Microsoft Word + pywin32 —— 调用 Word 将 docx 导出为 pdf。
2. 已安装 LibreOffice/soffice —— 无头模式将 docx 转为 pdf（跨平台，保证 PDF 与 Word 版式一致）。
3. 以上均不可用 —— 回退 reportlab 重新排版生成 pdf。

溯源标记：MD 保留 [source:N] 原文；HTML 自动转为可点击溯源标签；Word / PDF 自动剔除。

图片路径：Markdown 中的相对图片路径（如 assets/xxx.png）统一相对输出目录（--outdir，默认 output/）解析，
不受脚本调用时的工作目录影响。所有位图均按原始宽高比等比缩放，避免变形。

排版要点（本版修复）：
1. HTML 只保留一个报告主标题（正文若自带一级标题则不再重复添加）。
2. HTML 内嵌图片为 base64 data URI，脱离 assets/ 目录也能正常显示图形。
3. DOCX / PDF 图片按原始宽高比等比缩放并居中，不再强制拉伸。
4. PDF 中文字体跨平台回退（Windows 雅黑/宋体 → Linux Noto/文泉驿 → macOS 苹方），
   避免中文因缺字体渲染为空白/方框。
5. PDF 表格按内容计算列宽、单元格自动换行、表头跨页重复；正文与单元格文本做 XML 转义。
6. DOCX 支持行内加粗/行内代码/链接、列表、引用、分隔线，表格表头加粗、自动适应页宽。
"""

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# 默认输出目录（脚本运行时可被 --outdir 覆盖）
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR = DEFAULT_OUTPUT_DIR  # 运行期由 save_report(outdir=...) 覆盖

# 中文字体候选（跨平台回退，按优先级）
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",                              # Windows 微软雅黑
    "C:/Windows/Fonts/simsun.ttc",                            # Windows 宋体
    "C:/Windows/Fonts/simhei.ttf",                            # Windows 黑体
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux Noto Sans CJK
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",  # Linux Noto Serif CJK
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",            # Linux 文泉驿正黑
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",          # Linux 文泉驿微米黑
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/System/Library/Fonts/PingFang.ttc",                      # macOS 苹方
    "/System/Library/Fonts/STHeiti Light.ttc",                 # macOS 黑体
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/msyh.ttc",
    "/home/node/.openclaw/msyh.ttc",                           # 旧版 Linux 部署路径
]

# DOCX 中文字体名（Word 打开时按名称解析；缺失时由 Word/LibreOffice 回退到系统 CJK 字体）
_DOCX_CJK_FONT = "Microsoft YaHei"

# 注册成功的中文字体名；None 表示尚未注册 / 待回退
_REGISTERED_FONT = None
# 已解析出的可用中文字体文件路径
_RESOLVED_FONT_PATH = None


def find_cjk_font_path():
    """返回第一个存在的中文字体文件路径；都没有时返回 None。"""
    global _RESOLVED_FONT_PATH
    if _RESOLVED_FONT_PATH:
        return _RESOLVED_FONT_PATH
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            _RESOLVED_FONT_PATH = p
            return p
    return None


def _resolve_ttc_index(path: str, prefer: str = "SC") -> int:
    """在 .ttc 字体集合中挑选包含 prefer 关键字（如 SC）的子字体索引；失败返回 0。"""
    if not str(path).lower().endswith(".ttc"):
        return 0
    try:
        from fontTools.ttLib import TTCollection
        coll = TTCollection(path, lazy=True)
        for i, f in enumerate(coll.fonts):
            names = []
            for rec in f["name"].names:
                try:
                    names.append(rec.toUnicode())
                except Exception:
                    pass
            if prefer and prefer in " ".join(names):
                return i
        return 0
    except Exception:
        return 0


def _register_cjk_font() -> str:
    """注册中文字体，返回可用于 reportlab 的字体名。

    跨平台健壮降级：
    1. 依次尝试候选字体路径（.ttc 集合自动挑选简体中文子字体）；
    2. 全部失败时回退 reportlab 内置 Helvetica —— PDF 仍能生成、流程不中断。
    """
    global _REGISTERED_FONT
    if _REGISTERED_FONT:
        return _REGISTERED_FONT

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for p in _FONT_CANDIDATES:
        if not Path(p).exists():
            continue
        idxs = [_resolve_ttc_index(p), 0] if str(p).lower().endswith(".ttc") else [None]
        seen = set()
        for idx in idxs:
            if idx in seen:
                continue
            seen.add(idx)
            try:
                if idx is None:
                    font = TTFont('CJKFont', p)
                else:
                    font = TTFont('CJKFont', p, subfontIndex=idx)
                pdfmetrics.registerFont(font)
                _REGISTERED_FONT = 'CJKFont'
                _RESOLVED_FONT_PATH = p
                return _REGISTERED_FONT
            except Exception:
                continue

    _REGISTERED_FONT = 'Helvetica'
    return _REGISTERED_FONT


def safe_filename(title: str) -> str:
    """生成安全文件名"""
    name = "".join(c if c.isalnum() or c in "()_- " else "_" for c in title).strip()
    return name or "industry_deep_analysis"


# --------------------------------------------------------------------------
# 图片处理：路径解析 / 等比缩放 / base64 内嵌
# --------------------------------------------------------------------------

_IMG_MD_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')


def _resolve_image_path(src: str):
    """把 Markdown 图片路径解析为本地存在的文件路径；无法解析返回 None。"""
    src = (src or "").strip()
    if not src or src.startswith("data:"):
        return None
    p = Path(src)
    candidates = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(OUTPUT_DIR / src)
        candidates.append(Path.cwd() / src)
    for c in candidates:
        try:
            if c.exists():
                return c
        except OSError:
            continue
    return None


def _image_display_size(path: Path, max_w: float, max_h: float):
    """按原始宽高比等比缩放，返回 (宽, 高)，单位与 max_w/max_h 一致。"""
    w = h = None
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(path) as im:
            w, h = im.size
    except Exception:
        w = h = None
    if not w or not h:
        # 无法读取尺寸：按上限宽度、常见比例兜底
        return max_w, max_w * 0.62
    ratio = h / w
    out_w = max_w
    out_h = out_w * ratio
    if out_h > max_h:
        out_h = max_h
        out_w = out_h / ratio
    return out_w, out_h


_CHART_FENCE_RE = re.compile(r'^\s*```(?:echarts|mermaid|svg)\s*$')
_IMG_LOCATOR_RE = re.compile(r'^\s*<!--\s*img:\s*(.+?)\s*-->\s*$')
_FENCE_END_RE = re.compile(r'^\s*```\s*$')


def _charts_to_images(content: str) -> str:
    """把「<!--img:assets/x.png--> + 图表围栏」折叠成普通图片引用。

    Markdown 交付件（以及在线协同文档）保留 ```echarts / ```mermaid 围栏，前端可直接渲染；
    Word / PDF / HTML 则改用同一张图在本地渲染好的 PNG —— 两种形态同源，不重复维护。
    没有定位注释的围栏保持原样，不做静默删除。
    """
    lines = content.split("\n")
    out, i = [], 0
    while i < len(lines):
        loc = _IMG_LOCATOR_RE.match(lines[i])
        if loc:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and _CHART_FENCE_RE.match(lines[j]):
                k = j + 1
                while k < len(lines) and not _FENCE_END_RE.match(lines[k]):
                    k += 1
                out.append("![](%s)" % loc.group(1))
                i = k + 1 if k < len(lines) else k
                continue
            out.append("![](%s)" % loc.group(1))
            i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _embed_images_as_datauri(content: str) -> str:
    """把本地图片引用替换为 base64 data URI，使 HTML 自包含。"""
    def repl(m):
        alt, src = m.group(1), m.group(2)
        local = _resolve_image_path(src)
        if not local:
            return m.group(0)
        try:
            raw = local.read_bytes()
            mime = mimetypes.guess_type(local.name)[0] or "image/png"
            if mime.endswith("svg"):
                mime = "image/svg+xml"
            b64 = base64.b64encode(raw).decode("ascii")
            # 近似方形图（饼图等）附加 chart-pie 类，HTML 中按更小宽度展示
            cls = ' class="chart-pie"' if _is_squareish_image(local) else ""
            return f'<img{cls} alt="{alt}" src="data:{mime};base64,{b64}">'
        except Exception:
            return m.group(0)

    return _IMG_MD_RE.sub(repl, content)


def _strip_leading_h1(content: str) -> str:
    """若正文首个非空行是一级标题，则去掉它（避免与页面主标题重复）。"""
    lines = content.splitlines()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        if s.startswith("# ") and not s.startswith("## "):
            return "\n".join(lines[i + 1:])
        break
    return content


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------

def _set_run_east_asian(run, font_name: str = _DOCX_CJK_FONT):
    """为 run 设置东亚字体，保证 Word 中中文正常显示。"""
    try:
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
    except Exception:
        return
    try:
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.find(qn('w:rFonts'))
        if rFonts is None:
            rFonts = OxmlElement('w:rFonts')
            rPr.append(rFonts)
        rFonts.set(qn('w:eastAsia'), font_name)
    except Exception:
        pass


_SOURCE_MARK_RE = re.compile(r'\[source:\d+\]')


def _strip_source_markers(content: str) -> str:
    """移除 [source:N] 溯源标记。

    Word / PDF 为正式交付件，不展示溯源标识；MD / HTML 保留（便于溯源核对）。
    """
    return _SOURCE_MARK_RE.sub("", content)


def _is_squareish_image(path, lo: float = 0.72, hi: float = 1.4) -> bool:
    """判断图片是否近似方形（饼图等），用于采用更小的展示宽度。"""
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(path) as im:
            w, h = im.size
        if w and h:
            return lo <= (w / float(h)) <= hi
    except Exception:
        pass
    return False


def _next_numbering_id(doc, abstract_id: str = "7") -> int:
    """为新的有序列表创建独立 numId（复用同一 abstractNum，并 startOverride=1）。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    numbering = doc.part.numbering_part.element
    used = []
    for n in numbering.findall(qn('w:num')):
        try:
            used.append(int(n.get(qn('w:numId'))))
        except (TypeError, ValueError):
            pass
    new_id = (max(used) + 1) if used else 1
    num = OxmlElement('w:num')
    num.set(qn('w:numId'), str(new_id))
    ab = OxmlElement('w:abstractNumId')
    ab.set(qn('w:val'), str(abstract_id))
    num.append(ab)
    ov = OxmlElement('w:lvlOverride')
    ov.set(qn('w:ilvl'), '0')
    so = OxmlElement('w:startOverride')
    so.set(qn('w:val'), '1')
    ov.append(so)
    num.append(ov)
    numbering.append(num)
    return new_id


def _apply_list_numbering(paragraph, num_id: int, ilvl: int = 0):
    """在段落级写 numPr，覆盖样式级编号，使每个列表各自从 1 重新编号。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    pPr = paragraph._p.get_or_add_pPr()
    for old in pPr.findall(qn('w:numPr')):
        pPr.remove(old)
    numPr = OxmlElement('w:numPr')
    i = OxmlElement('w:ilvl'); i.set(qn('w:val'), str(ilvl))
    n = OxmlElement('w:numId'); n.set(qn('w:val'), str(num_id))
    numPr.append(i); numPr.append(n)
    # pPr 子元素顺序要求：numPr 需紧随 pStyle
    pStyle = pPr.find(qn('w:pStyle'))
    if pStyle is not None:
        pStyle.addnext(numPr)
    else:
        pPr.insert(0, numPr)


_INLINE_SPLIT_RE = re.compile(r'(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))')


def _add_inline_runs(paragraph, text: str, bold_all: bool = False):
    """把行内 Markdown（**加粗** / `代码` / [链接](url)）写入 docx 段落。"""
    for part in _INLINE_SPLIT_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) >= 4:
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("`") and part.endswith("`") and len(part) >= 2:
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Consolas"
        elif part.startswith("[") and "](" in part:
            m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', part)
            if m:
                run = paragraph.add_run(m.group(1))
                run.underline = True
            else:
                run = paragraph.add_run(part)
        else:
            run = paragraph.add_run(part)
        if bold_all:
            run.bold = True
        _set_run_east_asian(run)


def markdown_to_docx(content: str, output_path: Path):
    """将 Markdown 内容转换为 DOCX"""
    from docx import Document
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
    from docx.oxml.ns import qn

    doc = Document()

    # 页边距（A4，1 英寸）
    try:
        from docx.shared import Inches as _In
        for section in doc.sections:
            section.left_margin = _In(1.0)
            section.right_margin = _In(1.0)
            section.top_margin = _In(1.0)
            section.bottom_margin = _In(1.0)
    except Exception:
        pass

    # 设置中文字体 + 正文行距（1.25 倍；Word/PDF 一致，HTML 不受影响）
    style = doc.styles['Normal']
    style.font.name = _DOCX_CJK_FONT
    style.font.size = Pt(10.5)
    try:
        style._element.rPr.rFonts.set(qn('w:eastAsia'), _DOCX_CJK_FONT)
    except Exception:
        pass
    try:
        style.paragraph_format.line_spacing = 1.5
    except Exception:
        pass

    # 标题样式也补东亚字体 + 使用 1.5 倍行距
    for lvl in range(1, 7):
        try:
            hstyle = doc.styles[f'Heading {lvl}']
            hstyle.font.name = _DOCX_CJK_FONT
            hstyle._element.rPr.rFonts.set(qn('w:eastAsia'), _DOCX_CJK_FONT)
            hstyle.paragraph_format.line_spacing = 1.5
        except Exception:
            pass

    lines = content.splitlines()
    table_lines = []
    in_table = False
    cur_ol_num_id = None   # 当前有序列表的编号实例；遇非列表内容即重置

    def flush_table():
        nonlocal table_lines, in_table
        if table_lines:
            _add_table(doc, table_lines)
        table_lines = []
        in_table = False

    for line in lines:
        stripped = line.strip()

        # 非有序列表的内容行 → 结束当前列表作用域
        if stripped and not re.match(r'^\d+[.)]\s+', stripped):
            cur_ol_num_id = None

        # 图片
        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
        if img_match:
            if in_table:
                flush_table()
            img_path = img_match.group(2)
            local = _resolve_image_path(img_path)
            if local:
                # 近似方形图（饼图等）缩小展示宽度，避免占满整页
                max_w = 3.4 if _is_squareish_image(local) else 6.0
                w_in, h_in = _image_display_size(local, max_w=max_w, max_h=8.0)
                p = doc.add_paragraph()
                p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
                run = p.add_run()
                try:
                    run.add_picture(str(local), width=Inches(w_in), height=Inches(h_in))
                except Exception:
                    pass
            continue

        # 表格
        if stripped.startswith('|'):
            table_lines.append(stripped)
            in_table = True
            continue
        elif in_table:
            flush_table()

        if not stripped:
            continue

        # 分隔线
        if re.fullmatch(r'([-*_])\1{2,}', stripped):
            p = doc.add_paragraph()
            p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            _add_inline_runs(p, "────────")
            continue

        # 标题
        if stripped.startswith('#'):
            level = len(stripped) - len(stripped.lstrip('#'))
            text = stripped.lstrip('#').strip()
            h = doc.add_heading(level=min(level, 6))
            _add_inline_runs(h, text, bold_all=True)
            if level == 1:
                # 报告主标题：居中 + 加大字号；段前段后各约 1 行正文（16pt），不留大块空白
                h.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
                try:
                    h.paragraph_format.space_before = Pt(16)
                    h.paragraph_format.space_after = Pt(16)
                    for _r in h.runs:
                        _r.font.size = Pt(20)
                except Exception:
                    pass
            elif level == 2:
                # 一级章节标题：13pt，段前段后对称（避免“前后间距不一致”）
                try:
                    h.paragraph_format.space_before = Pt(12)
                    h.paragraph_format.space_after = Pt(12)
                    for _r in h.runs:
                        _r.font.size = Pt(13)
                except Exception:
                    pass
            elif level == 3:
                # 二级小节标题：12pt（> 正文 10.5pt，且 < 一级章节 13pt），段前段后对称
                try:
                    h.paragraph_format.space_before = Pt(10)
                    h.paragraph_format.space_after = Pt(10)
                    for _r in h.runs:
                        _r.font.size = Pt(12)
                except Exception:
                    pass
            else:
                # 三级及以下：11pt，段前段后对称
                try:
                    h.paragraph_format.space_before = Pt(8)
                    h.paragraph_format.space_after = Pt(8)
                    for _r in h.runs:
                        _r.font.size = Pt(11)
                except Exception:
                    pass
            continue

        # 引用
        if stripped.startswith('>'):
            text = stripped.lstrip('>').strip()
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.3)
            _add_inline_runs(p, text)
            for r in p.runs:
                r.italic = True
            continue

        # 无序列表
        m_ul = re.match(r'^[-*+]\s+(.*)$', stripped)
        if m_ul:
            p = doc.add_paragraph(style='List Bullet')
            _add_inline_runs(p, m_ul.group(1))
            continue

        # 有序列表（每个列表独立编号，从 1 开始）
        m_ol = re.match(r'^\d+[.)]\s+(.*)$', stripped)
        if m_ol:
            p = doc.add_paragraph(style='List Number')
            _add_inline_runs(p, m_ol.group(1))
            if cur_ol_num_id is None:
                try:
                    cur_ol_num_id = _next_numbering_id(doc)
                except Exception:
                    cur_ol_num_id = None
            if cur_ol_num_id is not None:
                try:
                    _apply_list_numbering(p, cur_ol_num_id)
                except Exception:
                    pass
            continue

        # 普通段落
        p = doc.add_paragraph()
        _add_inline_runs(p, stripped)

    flush_table()

    doc.save(output_path)


def _add_table(doc, table_lines):
    """从 Markdown 表格行添加表格到 DOCX（自动适应页宽、表头加粗）。"""
    from docx.shared import Pt
    from docx.enum.table import WD_TABLE_ALIGNMENT

    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if cells and not all(set(c) <= set(' :-') for c in cells):
            rows.append(cells)

    if not rows:
        return

    ncols = max(len(r) for r in rows)
    rows = [r + [''] * (ncols - len(r)) for r in rows]

    table = doc.add_table(rows=len(rows), cols=ncols)
    try:
        table.style = 'Table Grid'
    except Exception:
        pass
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    try:
        table.autofit = True
    except Exception:
        pass

    for i, row in enumerate(rows):
        for j, cell_text in enumerate(row):
            cell = table.rows[i].cells[j]
            cell.text = ''
            p = cell.paragraphs[0]
            _add_inline_runs(p, cell_text, bold_all=(i == 0))
            for r in p.runs:
                r.font.size = Pt(9)


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------

def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _inline_to_pdf_markup(text: str) -> str:
    """先做 XML 转义，再把 **加粗** 转成 reportlab 可识别的 <b>。"""
    escaped = _xml_escape(text)
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped)


def markdown_to_pdf(content: str, output_path: Path):
    """将 Markdown 内容转换为 PDF（等比图片 / 自动列宽表格 / 中文字体回退）。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, Image, HRFlowable)
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER

    cjk_font = _register_cjk_font()

    styles = getSampleStyleSheet()
    # 主标题：段前段后各约 1 行正文，不留大块空白；行距按 1.5 倍（18 * 1.5 = 27）
    styles.add(ParagraphStyle(name='ChineseTitle', fontName=cjk_font, fontSize=18,
                              leading=27, alignment=TA_CENTER, spaceBefore=16, spaceAfter=16,
                              textColor=colors.HexColor('#1a1a1a')))
    styles.add(ParagraphStyle(name='ChineseHeading1', fontName=cjk_font, fontSize=14,
                              leading=21, spaceBefore=8, spaceAfter=10,
                              textColor=colors.HexColor('#2E5BFF')))
    styles.add(ParagraphStyle(name='ChineseHeading2', fontName=cjk_font, fontSize=12,
                              leading=18, spaceBefore=6, spaceAfter=8,
                              textColor=colors.HexColor('#333333')))
    styles.add(ParagraphStyle(name='ChineseNormal', fontName=cjk_font, fontSize=10,
                              leading=15, spaceAfter=7, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='ChineseBold', fontName=cjk_font, fontSize=10,
                              leading=15, spaceAfter=7, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name='ChineseBullet', fontName=cjk_font, fontSize=10,
                              leading=15, spaceAfter=4, leftIndent=16, bulletIndent=4,
                              bulletFontName=cjk_font))
    styles.add(ParagraphStyle(name='ChineseQuote', fontName=cjk_font, fontSize=9.5,
                              leading=14.25, spaceAfter=6, leftIndent=16,
                              textColor=colors.HexColor('#555555')))
    styles.add(ParagraphStyle(name='ChineseTableCell', fontName=cjk_font, fontSize=8.5,
                              leading=11))
    styles.add(ParagraphStyle(name='ChineseTableHead', fontName=cjk_font, fontSize=8.5,
                              leading=11, textColor=colors.HexColor('#1a1a1a')))

    # 页面可用宽度
    PAGE_W, PAGE_H = A4
    MARGIN = 60
    AVAIL_W = PAGE_W - 2 * MARGIN  # ≈ 475pt

    doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                            rightMargin=MARGIN, leftMargin=MARGIN,
                            topMargin=60, bottomMargin=60)
    story = []

    lines = content.splitlines()
    table_lines = []
    in_table = False

    def flush_pdf_table():
        nonlocal table_lines, in_table
        if table_lines:
            _add_pdf_table(story, table_lines, AVAIL_W, styles, cjk_font)
        table_lines = []
        in_table = False

    for line in lines:
        stripped = line.strip()

        # 图片：等比缩放，居中
        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
        if img_match:
            if in_table:
                flush_pdf_table()
            local = _resolve_image_path(img_match.group(2))
            if local:
                max_w = 300.0 if _is_squareish_image(local) else min(440.0, AVAIL_W)
                w, h = _image_display_size(local, max_w=max_w, max_h=470.0)
                try:
                    img = Image(str(local), width=w, height=h)
                    img.hAlign = 'CENTER'
                    story.append(img)
                    story.append(Spacer(1, 10))
                except Exception:
                    pass
            continue

        # 表格
        if stripped.startswith('|'):
            table_lines.append(stripped)
            in_table = True
            continue
        elif in_table:
            flush_pdf_table()

        if not stripped:
            story.append(Spacer(1, 4))
            continue

        # 分隔线
        if re.fullmatch(r'([-*_])\1{2,}', stripped):
            story.append(HRFlowable(width="100%", thickness=0.6,
                                    color=colors.HexColor('#dddddd'),
                                    spaceBefore=6, spaceAfter=10))
            continue

        # 标题
        if stripped.startswith('#'):
            level = len(stripped) - len(stripped.lstrip('#'))
            text = stripped.lstrip('#').strip()
            markup = _inline_to_pdf_markup(text)
            if level == 1:
                story.append(Paragraph(markup, styles['ChineseTitle']))
            elif level == 2:
                story.append(Paragraph(markup, styles['ChineseHeading1']))
            else:
                story.append(Paragraph(markup, styles['ChineseHeading2']))
            continue

        # 引用
        if stripped.startswith('>'):
            text = stripped.lstrip('>').strip()
            story.append(Paragraph(_inline_to_pdf_markup(text), styles['ChineseQuote']))
            continue

        # 无序列表
        m_ul = re.match(r'^[-*+]\s+(.*)$', stripped)
        if m_ul:
            story.append(Paragraph(_inline_to_pdf_markup(m_ul.group(1)),
                                   styles['ChineseBullet'], bulletText='•'))
            continue

        # 有序列表
        m_ol = re.match(r'^(\d+)[.)]\s+(.*)$', stripped)
        if m_ol:
            story.append(Paragraph(_inline_to_pdf_markup(m_ol.group(2)),
                                   styles['ChineseBullet'], bulletText=m_ol.group(1) + '.'))
            continue

        # 普通段落
        story.append(Paragraph(_inline_to_pdf_markup(stripped), styles['ChineseNormal']))

    flush_pdf_table()

    # 页码
    def _on_page(canv, _d):
        canv.saveState()
        canv.setFont(cjk_font, 8)
        canv.setFillColor(colors.HexColor('#888888'))
        canv.drawCentredString(PAGE_W / 2.0, 30, f"{_d.page}")
        canv.restoreState()

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)


def _add_pdf_table(story, table_lines, avail_w, styles, cjk_font):
    """从 Markdown 表格行添加表格到 PDF：内容自适应列宽、单元格换行、表头跨页重复。"""
    from reportlab.platypus import Table, TableStyle, Spacer, Paragraph
    from reportlab.lib import colors

    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if cells and not all(set(c) <= set(' :-') for c in cells):
            rows.append(cells)

    if not rows:
        return

    ncols = max(len(r) for r in rows)
    rows = [r + [''] * (ncols - len(r)) for r in rows]

    # 单元格转成可换行的 Paragraph
    body = []
    for i, row in enumerate(rows):
        style = styles['ChineseTableHead'] if i == 0 else styles['ChineseTableCell']
        body.append([Paragraph(_inline_to_pdf_markup(c), style) for c in row])

    # 依据内容长度计算列宽（中文按 2 个字符宽）
    widths = [1.0] * ncols
    for row in rows:
        for j in range(ncols):
            txt = row[j]
            w = sum(2 if ord(ch) > 0x2E80 else 1 for ch in txt)
            widths[j] = max(widths[j], min(w, 34))
    total = sum(widths) or 1
    col_widths = [max(28.0, avail_w * w / total) for w in widths]
    # 归一化到可用宽度
    scale = avail_w / sum(col_widths)
    col_widths = [w * scale for w in col_widths]

    table = Table(body, colWidths=col_widths, repeatRows=1, hAlign='CENTER')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef2fb')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#c9c9c9')),
        ('FONTNAME', (0, 0), (-1, -1), cjk_font),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafbfd')]),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# HTML 溯源标签（[source:N] -> 可点击标签）
# --------------------------------------------------------------------------

_TRACE_CSS = """
    /* 溯源标签 */
    .trace-source { display: inline-block; min-width: 15px; padding: 0 4px; margin: 0 2px;
        border-radius: 8px; background: #e9f1ff; border: 1px solid #bcd4f6; color: #2E5BFF;
        font-size: 10.5px; line-height: 15px; text-align: center; vertical-align: super;
        cursor: pointer; font-family: Arial, Helvetica, sans-serif; user-select: none; }
    .trace-source:hover, .trace-source:focus { background: #2E5BFF; color: #fff; outline: none; }
    #mxTraceMask { position: fixed; inset: 0; background: rgba(15,23,42,.42); display: none; z-index: 9998; }
    #mxTracePanel { position: fixed; left: 50%; top: 50%; transform: translate(-50%,-50%);
        width: min(520px, 88vw); max-height: 76vh; overflow: auto; background: #fff; border-radius: 10px;
        box-shadow: 0 18px 48px rgba(15,23,42,.28); z-index: 9999; display: none;
        font-size: 13.5px; line-height: 1.7; color: #243044; }
    #mxTracePanel h4 { margin: 0; padding: 14px 18px 10px; font-size: 15px; color: #12305c;
        border-bottom: 1px solid #eef2f7; }
    #mxTracePanel .mx-body { padding: 12px 18px 4px; }
    #mxTracePanel .mx-row { display: flex; gap: 10px; padding: 5px 0; border-bottom: 1px dashed #f0f3f8; }
    #mxTracePanel .mx-k { flex: 0 0 76px; color: #8595ad; }
    #mxTracePanel .mx-v { flex: 1; word-break: break-all; }
    #mxTracePanel a { color: #2E5BFF; text-decoration: none; }
    #mxTracePanel a:hover { text-decoration: underline; }
    #mxTracePanel .mx-foot { padding: 10px 18px 16px; text-align: right; }
    #mxTracePanel button { cursor: pointer; border: 1px solid #bcd4f6; background: #e9f1ff;
        color: #2E5BFF; border-radius: 6px; padding: 5px 14px; font-size: 13px; }
"""

_TRACE_JS_TMPL = """
(function () {
  var S = __SOURCES__;
  var M = __LOCAL__;
  var mask = document.createElement('div'); mask.id = 'mxTraceMask';
  var panel = document.createElement('div'); panel.id = 'mxTracePanel';
  document.body.appendChild(mask); document.body.appendChild(panel);
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function show(n) {
    var s = S[n];
    var html = '<h4>数据溯源 · 本报告第 ' + esc(M[n] || n) + ' 条</h4><div class="mx-body">';
    if (s) {
      // 空字段不渲染成空行（缺元数据的标记已在生成阶段删除，不会走到这里）
      var infoRows = [['来源类型', s.k], ['标题', s.t], ['机构/出处', s.o], ['发布时间', s.d]];
      for (var ri = 0; ri < infoRows.length; ri++) {
        if (infoRows[ri][1]) {
          html += '<div class="mx-row"><span class="mx-k">' + esc(infoRows[ri][0]) + '</span><span class="mx-v">' + esc(infoRows[ri][1]) + '</span></div>';
        }
      }
      html += '<div class="mx-row"><span class="mx-k">原文链接</span><span class="mx-v">' +
        (s.l ? '<a href="' + esc(s.l) + '" target="_blank" rel="noopener">' + esc(s.l) + '</a>'
             : '该来源无公开链接') + '</span></div>';
    } else {
      html += '<div class="mx-row"><span class="mx-k">说明</span><span class="mx-v">未提供该标记的来源元数据。</span></div>';
    }
    html += '</div><div class="mx-foot"><button type="button" id="mxTraceClose">关闭</button></div>';
    panel.innerHTML = html;
    mask.style.display = 'block'; panel.style.display = 'block';
    document.getElementById('mxTraceClose').onclick = hide;
  }
  function hide() { mask.style.display = 'none'; panel.style.display = 'none'; }
  mask.onclick = hide;
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') hide(); });
  document.querySelectorAll('.trace-source').forEach(function (el) {
    var n = el.getAttribute('data-marker-id');
    el.addEventListener('click', function (e) { e.preventDefault(); show(n); });
    el.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); show(n); }
    });
  });
})();
"""

_TAG_SPLIT_RE = re.compile(r'(<[^>]*>)')
_TRACE_MARK_RE = re.compile(r'\[source:(\d+)\]')

# 溯源标签显示「本报告内顺序编号」（从 1 开始，按正文首次出现顺序）：
# [source:N] 的 N 在整个会话内全局分配（跨多次报表连续累加），直接展示会出现 200+ 这类与正文无关的数字。
# 真实编号仍保留在 data-marker / data-marker-id 属性中（界面不展示），不影响与来源台账的一一对应。


def normalize_sources(sources) -> dict:
    """把溯源元数据统一为 {标记编号字符串: {t,o,d,k,l}}。"""
    if not sources:
        return {}
    if isinstance(sources, dict) and isinstance(sources.get("sources"), dict):
        sources = sources["sources"]
    out = {}
    if isinstance(sources, dict):
        items = sources.items()
    elif isinstance(sources, list):
        items = [(str(it.get("marker", it.get("id", ""))), it) for it in sources if isinstance(it, dict)]
    else:
        return {}
    for k, v in items:
        key = str(k).strip()
        key = re.sub(r'^\[?source:?', '', key).strip('[] ')
        if not key or not isinstance(v, dict):
            continue
        out[key] = {
            "t": v.get("t") or v.get("title") or "",
            "o": v.get("o") or v.get("org") or v.get("source") or "",
            "d": v.get("d") or v.get("date") or "",
            "k": v.get("k") or v.get("type") or "外部来源",
            "l": v.get("l") or v.get("link") or "",
        }
    return out


def load_sources_from_dir(*dirs) -> dict:
    """从运行期落盘的 .sources/source-<N>.json 汇总溯源元数据。

    检索类来源（资讯/公告/研报）含 title / url / published_at / kind，直接映射；
    结构化取数类来源（MQL 报表）无标题字段，用报表名 + 取数日期生成可读标签。
    """
    out = {}
    for d in dirs:
        if not d:
            continue
        for base in (Path(d) / ".sources", Path(d)):
            if not base.is_dir():
                continue
            for f in sorted(base.glob("source-*.json")):
                m = re.search(r"source-(\d+)\.json$", f.name)
                if not m:
                    continue
                n = m.group(1)
                if n in out:
                    continue
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        raw = json.load(fh)
                except (OSError, ValueError):
                    continue
                if not isinstance(raw, dict):
                    continue
                created = str(raw.get("created_at") or "")[:10]
                title = str(raw.get("title") or "").strip()
                if not title:
                    rn = ""
                    try:
                        body = raw.get("content") or ""
                        body = json.loads(body) if isinstance(body, str) else body
                        reps = ((body or {}).get("fetch_summary") or {}).get("reports") or []
                        rn = str(reps[0].get("report") or "").strip() if reps else ""
                    except (ValueError, AttributeError, IndexError):
                        rn = ""
                    if rn:
                        title = "东方财富 Choice 报表：" + rn
                    if not title:
                        # 结构化取数工具（金融数据/宏观数据/选股）无标题字段，
                        # 用调用时的问句生成可读标签，避免该来源在 HTML 中被整体丢弃。
                        q = raw.get("input")
                        q = str((q or {}).get("query") or "").strip() if isinstance(q, dict) else ""
                        if q:
                            title = "东方财富 Choice 数据查询：" + (q[:60] + "…" if len(q) > 60 else q)
                org = raw.get("org") or raw.get("source_name") or ""
                kind = str(raw.get("kind") or "").strip()
                if not kind:
                    kind = "结构化数据" if title.startswith("东方财富 Choice") else "外部来源"
                entry = {
                    "t": title,
                    "o": str(org).strip() if isinstance(org, str) else "",
                    "d": created,
                    "k": kind,
                    "l": str(raw.get("url") or "").strip(),
                }
                if entry["t"] or entry["l"]:
                    out[n] = entry
    return out


def render_source_trace(body_html: str, sources=None):
    """把正文 HTML 中的 [source:N] 文本替换为可点击溯源标签。

    只在文本节点内替换，避免破坏标签属性；原始标记文本保留在 data-marker 属性中（不渲染到界面）。
    标签显示的是「本报告内顺序编号」（从 1 开始，按正文首次出现顺序），
    真实会话级编号仍保留在 data-marker / data-marker-id 属性中，界面与弹窗均不展示。

    返回 (渲染后的 HTML, {会话级编号: 报告内序号})。
    """
    smap = normalize_sources(sources)
    parts = _TAG_SPLIT_RE.split(body_html)

    def _usable(n):
        s = smap.get(n)
        return bool(s and (s.get("t") or s.get("o") or s.get("l") or s.get("d")))

    # 第一遍：按正文首次出现顺序给可渲染的来源分配报告内序号
    order = []
    for seg in parts:
        if seg.startswith("<"):
            continue
        for n in _TRACE_MARK_RE.findall(seg):
            if _usable(n) and n not in order:
                order.append(n)
    local = {n: str(i + 1) for i, n in enumerate(order)}

    def repl(mo):
        n = mo.group(1)
        s = smap.get(n)
        # 无元数据的标记不生成溯源标签，直接删除标记本身（与 Word / PDF 行为一致），
        # 避免出现「未提供该标记的来源元数据」这类空壳弹窗。
        if not _usable(n):
            return ""
        bits = [x for x in (s.get("o"), s.get("d")) if x]
        title = ("溯源 " + local[n] + "：" + ("《" + s["t"] + "》" if s.get("t") else "")
                 + ("（" + "·".join(bits) + "）" if bits else ""))
        return ('<span class="trace-source" data-marker="[source:%s]" data-marker-id="%s" '
                'role="button" tabindex="0" title="%s" aria-label="%s">%s</span>'
                % (n, n, _escape_html(title), _escape_html(title), local[n]))

    for i, seg in enumerate(parts):
        if seg.startswith("<"):
            continue
        parts[i] = _TRACE_MARK_RE.sub(repl, seg)
    return "".join(parts), local


def _trace_script(sources=None, local=None) -> str:
    smap = normalize_sources(sources)
    return "<script>" + _TRACE_JS_TMPL.replace(
        "__SOURCES__", json.dumps(smap, ensure_ascii=False)).replace(
        "__LOCAL__", json.dumps(local or {}, ensure_ascii=False)) + "</script>"


def markdown_to_html(content: str, title: str, output_path: Path, sources=None):
    """将 Markdown 内容转换为自包含 HTML（分享链接载体）。

    - 只保留一个主标题（正文自带一级标题时不重复添加）；
    - 图片内嵌为 base64 data URI，脱离 assets/ 也能正常显示；
    - 内嵌全套 CSS，不依赖外部资源；
    - 正文中的 [source:N] 自动转为可点击溯源标签（sources 提供来源标题/机构/日期/链接，
      缺省时标签仅显示编号）。
    """
    try:
        import markdown as md_mod  # type: ignore
    except ImportError:
        md_mod = None

    body_md = _strip_leading_h1(content)
    body_md = _embed_images_as_datauri(body_md)

    if md_mod is not None:
        body = md_mod.markdown(body_md, extensions=["tables", "fenced_code", "sane_lists"])
    else:
        body = _simple_md_to_html(body_md)

    # [source:N] -> 可点击溯源标签
    body, trace_local = render_source_trace(body, sources)

    css = """
    :root { color-scheme: light; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
           max-width: 860px; margin: 0 auto; padding: 40px 28px 64px; color: #1a1a1a;
           line-height: 1.75; background: #fff; }
    h1 { font-size: 28px; border-bottom: 2px solid #e6e6e6; padding-bottom: 12px; margin: 8px 0 24px; }
    h2 { font-size: 22px; margin: 32px 0 14px; padding-left: 10px; border-left: 4px solid #2E5BFF; }
    h3 { font-size: 18px; margin: 24px 0 10px; }
    h4 { font-size: 16px; margin: 20px 0 8px; }
    table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 14px; }
    th, td { border: 1px solid #e2e2e2; padding: 8px 12px; text-align: left; }
    th { background: #f5f7fb; font-weight: 600; }
    tr:nth-child(even) td { background: #fafbfd; }
    img { display: block; max-width: 100%; height: auto; margin: 16px auto; border-radius: 6px; }
    img.chart-pie { max-width: 380px; }
    code { background: #f2f4f8; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
    pre { background: #f6f8fa; padding: 16px; border-radius: 8px; overflow-x: auto; }
    pre code { background: none; padding: 0; }
    blockquote { border-left: 3px solid #d0d7e2; margin: 16px 0; padding: 4px 16px; color: #555; }
    hr { border: none; border-top: 1px solid #eee; margin: 32px 0; }
    a { color: #2E5BFF; text-decoration: none; }
    """.strip()

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_escape_html(title)}</title>
<style>{css}
{_TRACE_CSS}</style>
</head>
<body>
<h1>{_escape_html(title)}</h1>
{body}
{_trace_script(sources, trace_local)}
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def _escape_html(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;"))


def _simple_md_to_html(content: str) -> str:
    """无 markdown 库时的极简降级转换（表格/标题/加粗/图片）。"""
    import html as _html
    lines = content.splitlines()
    out = []
    in_table = False
    table_lines = []

    def flush_table():
        nonlocal table_lines, in_table
        if not table_lines:
            return
        rows = []
        for ln in table_lines:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            rows.append(cells)
        if not rows:
            table_lines = []
            in_table = False
            return
        buf = ["<table>"]
        for i, r in enumerate(rows):
            tag = "th" if i == 0 else "td"
            buf.append("<tr>" + "".join(f"<{tag}>{_html.escape(c)}</{tag}>" for c in r) + "</tr>")
        buf.append("</table>")
        out.extend(buf)
        table_lines = []
        in_table = False

    for ln in lines:
        s = ln.strip()
        if s.startswith("|") and set(s.replace("|", "").replace(" ", "").replace("-", "").replace(":", "")) == set():
            table_lines.append(s)
            in_table = True
            continue
        if s.startswith("|"):
            table_lines.append(s)
            in_table = True
            continue
        if in_table:
            flush_table()
            in_table = False
        if not s:
            continue
        if s.startswith("#"):
            level = len(s) - len(s.lstrip("#"))
            text = s.lstrip("#").strip()
            out.append(f"<h{min(level, 6)}>{_html.escape(text)}</h{min(level, 6)}>")
        elif s.startswith("!["):
            import re as _re
            m = _re.match(r"!\[([^\]]*)\]\(([^)]+)\)", s)
            if m:
                out.append(f'<img src="{_html.escape(m.group(2))}" alt="{_html.escape(m.group(1))}">')
            else:
                out.append(f"<p>{_html.escape(s)}</p>")
        elif s.startswith(("- ", "* ")):
            out.append(f"<ul><li>{_html.escape(s[2:].strip())}</li></ul>")
        else:
            import re as _re
            txt = _re.sub(r"\*\*(.+?)\*\*", lambda m: f"<strong>{_html.escape(m.group(1))}</strong>", s)
            out.append(f"<p>{txt}</p>")

    if table_lines:
        flush_table()
    return "\n".join(out)


# --------------------------------------------------------------------------
# Word → PDF（Windows 专用，失败回退 reportlab）
# --------------------------------------------------------------------------

def docx_to_pdf_via_word(docx_path: Path, pdf_path: Path) -> bool:
    """用本机 Microsoft Word 将 DOCX 导出为 PDF，使 PDF 排版与 Word 完全一致。

    环境要求：Windows + 已安装 Microsoft Office；不满足或失败时返回 False（调用方应回退）。
    """
    if os.name != "nt":
        return False
    try:
        import win32com.client  # pywin32
    except Exception:
        return False
    try:
        word = win32com.client.Dispatch("Word.Application")
    except Exception:
        return False
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(docx_path), False, True)
        try:
            doc.ExportAsFixedFormat(str(pdf_path), 17)  # 17 = wdExportFormatPDF
            return pdf_path.exists() and pdf_path.stat().st_size > 0
        finally:
            doc.Close(False)
    except Exception:
        return False
    finally:
        try:
            word.Quit()
        except Exception:
            pass


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def docx_to_pdf_via_soffice(docx_path: Path, pdf_path: Path) -> bool:
    """用 LibreOffice/soffice 无头模式把 DOCX 转成 PDF，使 PDF 与 Word 版式一致。

    找不到 soffice 或转换失败时返回 False（调用方应回退 reportlab）。
    使用独立且可写的用户配置目录，避免沙箱 HOME 不可写导致启动失败。
    """
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        return False
    try:
        outdir = pdf_path.parent
        profile = Path(tempfile.gettempdir()) / "lo_profile_save_report"
        profile.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [exe, f"-env:UserInstallation=file://{profile}",
             "--headless", "--norestore", "--nolockcheck",
             "--convert-to", "pdf", "--outdir", str(outdir), str(docx_path)],
            check=True, capture_output=True, timeout=300,
        )
        produced = outdir / (docx_path.stem + ".pdf")
        if produced.exists() and produced.stat().st_size > 0:
            if produced != pdf_path:
                try:
                    if pdf_path.exists():
                        pdf_path.unlink()
                    produced.replace(pdf_path)
                except Exception:
                    return produced.exists()
            return pdf_path.exists() and pdf_path.stat().st_size > 0
    except Exception:
        return False
    return False


def save_report(title: str, content: str, fmt: str = "all", outdir=None, sources=None) -> dict:
    """保存报告到文件。

    Args:
        title: 报告标题
        content: Markdown 格式的报告内容
        fmt: 输出格式（md / docx / pdf / html / all）
        outdir: 输出目录（默认脚本同级 output/）
        sources: 溯源元数据（{标记编号: {t:标题, o:机构, d:日期, k:类型, l:链接}}），
                 仅用于 HTML 的可点击溯源标签，不影响 MD / Word / PDF

    Returns:
        dict：含各类输出路径；html_output_path 用于生成分享链接。
    """
    global OUTPUT_DIR
    if outdir:
        OUTPUT_DIR = Path(outdir)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    safe_name = safe_filename(title)
    result = {"title": title, "status": "success", "output_dir": str(OUTPUT_DIR)}

    md_path = OUTPUT_DIR / f"{safe_name}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)
    result["md_output_path"] = str(md_path)

    # Word / PDF 属正式交付件，不展示 [source:N] 溯源标记（MD / HTML 保留以便溯源核对）；
    # 图表围栏在 Office / HTML 侧折叠为同源 PNG（Markdown 交付件保留围栏，在线协同文档可直接渲染）
    formal_content = _charts_to_images(_strip_source_markers(content))

    docx_path = OUTPUT_DIR / f"{safe_name}.docx"
    if fmt in ("docx", "all"):
        markdown_to_docx(formal_content, docx_path)
    result["docx_output_path"] = str(docx_path)

    pdf_path = OUTPUT_DIR / f"{safe_name}.pdf"
    if fmt in ("pdf", "all"):
        # 优先「直接把 docx 转 pdf」以保证 PDF 与 Word 版式一致：
        # Windows Word -> LibreOffice/soffice -> 回退 reportlab 重排版
        ok = False
        if docx_path.exists():
            if os.name == "nt":
                ok = docx_to_pdf_via_word(docx_path, pdf_path)
            if not ok:
                ok = docx_to_pdf_via_soffice(docx_path, pdf_path)
        if not ok:
            markdown_to_pdf(formal_content, pdf_path)
    result["pdf_output_path"] = str(pdf_path)

    html_path = OUTPUT_DIR / f"{safe_name}.html"
    if fmt in ("html", "all"):
        markdown_to_html(_charts_to_images(content), title, html_path, sources=sources)
    result["html_output_path"] = str(html_path)

    return result


def run_cli():
    parser = argparse.ArgumentParser(description="保存产业深度分析报告")
    parser.add_argument("--title", type=str, required=True, help="报告标题")
    parser.add_argument("--content", type=str, help="报告内容（Markdown）")
    parser.add_argument("--content_file", type=str, help="报告内容文件路径")
    parser.add_argument("--outdir", type=str, default=None,
                        help="输出目录（默认脚本同级 output/）")
    parser.add_argument("--format", type=str, choices=["md", "docx", "pdf", "html", "all"],
                        default="all", help="输出格式，默认 all（md+docx+pdf+html）")
    parser.add_argument("--sources_json", type=str, default=None,
                        help="溯源元数据 JSON（标记编号 -> 标题/机构/日期/类型/链接），"
                             "用于 HTML 可点击溯源标签；缺省时自动查找与内容文件同名的 .sources.json")

    args = parser.parse_args()

    content = args.content or ""
    if args.content_file:
        with open(args.content_file, "r", encoding="utf-8") as f:
            content = f.read()

    # 溯源元数据：显式 --sources_json 优先，否则自动查找同名 .sources.json
    sources = None
    src_path = args.sources_json
    if not src_path and args.content_file:
        for cand in (args.content_file + ".sources.json",
                     str(Path(args.content_file).with_suffix(".sources.json"))):
            if os.path.exists(cand):
                src_path = cand
                break
    if src_path:
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                sources = json.load(f)
        except (OSError, ValueError) as exc:
            print(json.dumps({"warning": f"溯源元数据读取失败：{exc}"}, ensure_ascii=False))

    # 兜底：直接从运行期落盘的 .sources/source-<N>.json 汇总元数据，
    # 没有任何元数据的标记在 HTML 中会被删除（不再出现空壳溯源标签）。
    if not normalize_sources(sources):
        content_dir = os.path.dirname(os.path.abspath(args.content_file)) if args.content_file else None
        auto = load_sources_from_dir(args.outdir, content_dir, os.getcwd(), Path(__file__).resolve().parent.parent)
        if auto:
            sources = auto

    result = save_report(args.title, content, args.format, outdir=args.outdir, sources=sources)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    run_cli()