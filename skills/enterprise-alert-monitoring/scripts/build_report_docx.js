// 通用预警监测报告 Word 构建器（docx-js）
// 读取当前目录下 content.json（正文/表格/卡片/图片，markdown 式 [n] 角标与 **粗体**）与
// md_footnotes.json（n -> "标题｜机构｜日期｜URL"），输出 <content.title>.docx。
// V19 规范：正文 23 半点(11.5pt)/行距1.5；分布图按 content 内 w/h（V19 为 620px 宽）嵌入。
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  AlignmentType, ExternalHyperlink, HeadingLevel, BorderStyle,
  WidthType, ShadingType, PageNumber, Footer, Header, TableLayoutType
} = require("docx");
const fs = require("fs");
const path = require("path");

// 支持在 report_build 目录内运行，也支持直接运行（RB 取含 content.json 的目录）
const RB = fs.existsSync(path.join(process.cwd(), "content.json")) ? process.cwd() : __dirname;
const C = [];
const CTRL = JSON.parse(fs.readFileSync(path.join(RB, "content.json"), "utf-8"));
const FN = JSON.parse(fs.readFileSync(path.join(RB, "md_footnotes.json"), "utf-8"));
const FONT = "Microsoft YaHei";

const T = (text, opts = {}) => new TextRun({ text, font: FONT, size: 23, ...opts });
const SUP = (n) => new TextRun({ text: `[${n}]`, font: FONT, size: 19, color: "1A66FF", superScript: true });
const para = (children, opts = {}) => new Paragraph({ children: Array.isArray(children) ? children : [children], spacing: { line: 360, after: 120 }, ...opts });

function rich(text) {
  const runs = [];
  const re = /(\*\*[^*]+\*\*)|(\[\d+\])/g;
  let m, last = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) runs.push(T(text.slice(last, m.index)));
    if (m[1]) runs.push(T(m[1].slice(2, -2), { bold: true }));
    else runs.push(SUP(parseInt(m[2].slice(1, -1), 10)));
    last = re.lastIndex;
  }
  if (last < text.length) runs.push(T(text.slice(last)));
  return runs;
}
const P = (text, opts = {}) => para(rich(text), opts);

function addMd(text) {
  text.split("\n").forEach(ln => {
    ln = ln.trim();
    if (!ln) return;
    const m = ln.match(/^(\d+)\.\s+(.*)$/);
    if (m) C.push(new Paragraph({ children: rich(m[2]), bullet: { level: 0 }, spacing: { line: 360, after: 80 } }));
    else C.push(P(ln));
  });
}

function addTable(t) {
  const colW = t.widths || [1300, 2000, 3338, 1500, 1500];
  const totalW = colW.reduce((a, b) => a + b, 0);
  C.push(new Table({
    width: { size: totalW, type: WidthType.DXA },
    columnWidths: colW,
    layout: TableLayoutType.FIXED,
    rows: [t.cols, ...t.rows].map((r, ri) => new TableRow({
      children: r.map((cell, ci) => new TableCell({
        width: { size: colW[ci], type: WidthType.DXA },
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        shading: ri === 0 ? { type: ShadingType.CLEAR, fill: "F0F3F8" } : undefined,
        children: [new Paragraph({ children: rich(cell), spacing: { line: 360 } })],
      })),
    })),
  }));
  if (t.note) C.push(para(T(t.note, { size: 19, color: "667085" }), { spacing: { before: 80, after: 160, line: 300 } }));
}

function card(kind, title, fields) {
  const red = kind === "y";
  const tc = red ? "8A6A1C" : "B03030", bc = red ? "C9A13B" : "D64545", bg = red ? "FDF9EC" : "FDF3F3";
  C.push(new Paragraph({ children: [new TextRun({ text: title, font: FONT, size: 23, bold: true, color: tc })], spacing: { line: 360, after: 60 }, border: { left: { style: BorderStyle.SINGLE, size: 12, color: bc, space: 6 } }, shading: { type: ShadingType.CLEAR, fill: bg } }));
  fields.forEach(([k, v]) => C.push(para([...rich(`**${k}**：${v}`)], { spacing: { line: 360, after: 40 }, indent: { left: 120 } })));
}

// V20：标题强制单行——按内容宽度（页宽 11906−边距×2≈9638 twips）与标题字宽反推字号，放不下逐级调小
function titleUnits(title) {
  let u = 0;
  for (const ch of title) u += ch.codePointAt(0) > 0x2E80 ? 1 : 0.55;
  return u;
}
const TITLE_AVAIL = 9638 * 0.94;
const TITLE_SIZE = Math.min(40, Math.max(26, Math.floor(TITLE_AVAIL / (titleUnits(CTRL.title) * 20))));
C.push(new Paragraph({ children: [new TextRun({ text: CTRL.title, font: FONT, size: TITLE_SIZE, bold: true })], alignment: AlignmentType.CENTER, spacing: { after: 100, line: 360 } }));
C.push(P(CTRL.meta, { alignment: AlignmentType.CENTER, spacing: { line: 360, after: 240 } }));

for (const s of CTRL.sections || []) {
  if (s.h1) C.push(new Paragraph({ text: s.h1, heading: HeadingLevel.HEADING_1, spacing: { before: 300, after: 140, line: 360 } }));
  else if (s.h2) C.push(new Paragraph({ text: s.h2, heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 100, line: 360 } }));
  else if (s.p) addMd(s.p);
  else if (s.list) s.list.forEach(x => C.push(new Paragraph({ children: rich(x), bullet: { level: 0 }, spacing: { line: 360, after: 80 } })));
  else if (s.image) {
    C.push(new Paragraph({ children: [new ImageRun({ type: "png", data: fs.readFileSync(path.join(RB, s.image.path)), transformation: { width: s.image.w, height: s.image.h } })], spacing: { after: 60 } }));
    C.push(para(T(s.image.note, { size: 19, color: "667085" }), { spacing: { after: 120, line: 300 } }));
  } else if (s.table) addTable(s.table);
  else if (s.card) card(s.card.kind, s.card.title, s.card.fields);
}

for (let i = 0; i < 3; i++) C.push(new Paragraph({ text: "", spacing: { line: 240 } }));
C.push(new Paragraph({ text: "溯源", heading: HeadingLevel.HEADING_1, spacing: { before: 120, after: 140, line: 360 } }));
const nums = Object.keys(FN).map(Number).sort((a, b) => a - b);
nums.forEach(n => {
  const [title, org, dt, url] = FN[String(n)].split("｜").map(s => s.trim());
  const runs = [new TextRun({ text: `[${n}] `, font: FONT, size: 19, bold: true, color: "1A66FF" })];
  if (url && url.startsWith("http")) {
    runs.push(new TextRun({ text: `${title}｜${org}｜${dt}｜`, font: FONT, size: 19 }));
    runs.push(new ExternalHyperlink({ children: [new TextRun({ text: url, font: FONT, size: 19, color: "1A66FF", underline: {} })], link: url }));
  } else {
    runs.push(new TextRun({ text: `${title}｜${org}｜${dt}｜${url || "无原文链接"}`, font: FONT, size: 19 }));
  }
  C.push(new Paragraph({ children: runs, spacing: { line: 300, after: 40 } }));
});

C.push(para(T("内容由 AI 生成，仅供研究参考，不构成投资建议。", { size: 18, color: "8A94A6" }), { spacing: { before: 360, line: 300 }, border: { top: { style: BorderStyle.SINGLE, size: 6, color: "E3E8F0", space: 8 } } }));

const doc = new Document({
  styles: {
    default: {
      document: { run: { font: FONT, size: 23 } },
      heading1: { run: { font: FONT, size: 28, bold: true, color: "1F2933" }, paragraph: { spacing: { line: 360 } } },
      heading2: { run: { font: FONT, size: 25, bold: true, color: "223333" }, paragraph: { spacing: { line: 360 } } },
    },
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1134, right: 1134, bottom: 1134, left: 1134 },
      },
    },
    headers: [new Header({ children: [new Paragraph({ children: [new TextRun({ text: CTRL.title, font: FONT, size: 16, color: "8A94A6" })], alignment: AlignmentType.RIGHT })] })],
    footers: [new Footer({ children: [new Paragraph({ children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: "8A94A6" })], alignment: AlignmentType.CENTER })] })],
    children: C,
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(path.join(RB, CTRL.title + ".docx"), buf);
  console.log("DOCX written:", buf.length, "bytes");
});
