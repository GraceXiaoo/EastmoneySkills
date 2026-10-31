# 多格式导出规范

本文件固化预警监测报告的交付格式：**HTML（主交付）＋ Word（.docx）**。两种格式同源——同一份冻结正文、图表数据与来源索引。

## 交付矩阵

| 格式 | 生成方式 | 用途 |
| --- | --- | --- |
| HTML | 主构建脚本 | 在线浏览、交互溯源（角标点击弹卡片） |
| Word (.docx) | docx-js 构建（`scripts/build_report_docx.js` 模板） | 编辑、批注、正式流转 |

**不交付** Markdown 与 PDF 版本（2026-10-29 用户定稿：只要 HTML 和 Word）。

## Word 版图片管线（关键）

Word 内嵌位图必须走**高清管线**，否则图内文字在缩放/打印时不完整：

1. **样式内联**：`scripts/svg_inline.py` 把静态图 SVG 的 `<style>` 类规则展开为元素属性——LibreOffice 对 SVG CSS 类渲染不全（实测类文字渲染量仅为内联属性的约 28%），不内联则文字缺失。
2. **位图转换**：`svg_inline.py` 输出 → `soffice --headless -env:UserInstallation=file:///tmp/lo_profile --convert-to pdf` → `pdftoppm -png -r 200 -singlefile` 得 200dpi 位图（620px 显示宽下等效 ≥300dpi）。
3. **词云例外**：`render_wordcloud.py` 原生输出 PNG（程序绘制，无 CSS 依赖），直接使用。
4. **docx 嵌入**：`ImageRun({ type: "png", transformation: { width: 620, height: 按原图比例 } })`；**高度一律由构建器按 PNG 头实际尺寸自动校正**（`h = w × png_h / png_w`，见 build_report_html.py `png_size()`），禁止沿用 report_input 手写 `h`——手写 h 与自适应 viewBox 不同步会把图“只拉宽不拉高”导致字体拉伸变形（V22 根治，构建时打印 `FIGFIT 文件名: w×h` 便于核对）。V20：**全部图表统一按 620px 宽嵌入**（HTML 容器上限 640px），两渠道图内文字比例一致；图表内文字按 630px 显示基准反推字号（标题/图例/轴/正文四档统一，见 report-format V20）。

## Word 版版式规范（docx-js 构建）

版式与 HTML 视觉规范同源移植：

- **字号体系（V17 上调）**：正文/表格/卡片 23 半点（11.5pt）；角标 19 半点上标蓝色 `1A66FF`；图注/索引 19 半点（9.5pt）。标题：题 42 半点、H1 28、H2 25。
- **行高**：正文 `spacing.line: 360`（**1.5 倍**行距）；图注/索引 300。
- **页面**：A4（11906×16838 twips），四边距 1134 twips（2cm）；页眉右侧报告名（16 半点灰）、页脚居中页码。
- **章节标题**：内置 `HeadingLevel.HEADING_1/2`（保证大纲层级与导航窗格可用）。
- **角标**：`TextRun({ text: "[N]", superScript: true, size: 14, color: "1A66FF" })`——Word 原生上标，不截断段落；**禁止用 Word 脚注承载溯源**（编号会与 HTML 失配），统一走文末「来源索引」。
- **来源索引**：编号蓝色＋`ExternalHyperlink` 蓝色下划线真链接；无 URL 条目如实写「无原文链接」。
- **表格**：`WidthType.DXA`＋columnWidths＋每格 width 三者一致；**表格总宽=页面可用宽**（A4 11906−2×1134 边距=9638），事件列占大头（如 [1000, 6438, 1000, 1200]）；表头浅底 `F0F3F8`。
- **来源章节**：章标题「**溯源**」（HEADING_1），标题前插入 3 个空段落与上文隔开；条目 [N] 编号蓝色＋真链接。
- **预警卡片**：左侧色条（红 D64545/FDF3F3、黄 C9A13B/FDF9EC）复刻 HTML。
- **列表**：`bullet: { level: 0 }` 编号系统，禁止手写 `•`。

## 构建链与验收

```
build_report.py (HTML, 含 md_footnotes.json 来源映射)
  → build_report_docx.js（Word, docx-js, 读 md_footnotes.json）
图片链: charts/*.svg → svg_inline.py → *_inlined.svg → soffice → pdf → pdftoppm → 200dpi PNG
```

验收清单（交付前执行）：

1. **双格式同源**：HTML 与 Word 正文章节数、角标总数、来源索引条数一致。
2. **docx 校验**：`validate.py` 通过 0 错误。
3. **图片验收**：Word 转出 PDF 后 `pdftoppm -r 100` 抽首页/图表页/索引页位图，视觉检查——图内文字（柱标签、节点框内容、图例、徽章）锐利完整、宽高比无拉伸、无裁切。
4. **HTML 校验**：html.parser 零错误、p 配对、无 details。
5. 一致性抽检：同一事实句在两格式中文字一致。

依赖：`docx`（npm global，NODE_PATH=$(npm root -g)）、`soffice`（LibreOffice，PDF/PNG 转换，需独立 `-env:UserInstallation` profile）、`pdftoppm`。soffice 不可用时仅交付 HTML 并注明。
