# 输出与交付规范（Step 7 / 7b）

> 到达出文件、发布、写溯源时读本文件。一次性读完即可。

## 1. 唯一输出出口

```bash
python3 {baseDir}/scripts/save_report.py \
  --title "{{主体名称}}产业深度分析报告" \
  --content_file "output/{{主体名称}}产业深度分析报告.md" \
  --outdir "/workspace/sessions/<session_id>/output" \
  --format all
```

- **硬规则：严禁 `--content "..."` 内联传参**（正文含中文、引号、换行、`|`，会被 shell 转义破坏且长度超限）。必须先写 Markdown 文件，再 `--content_file`。
- `--format all`（默认）一次产出 `{title}.md` / `.docx` / `.pdf` / `.html` 到 `--outdir`（默认脚本同级 `output/`）。
- 图片相对路径（`assets/xxx.png`）统一相对 `--outdir` 解析，与调用时工作目录无关；DOCX 内嵌图片（非外链）。
- 可选 `--sources_json <路径>` 显式指定溯源元数据。
- 依赖见 `requirements.txt`（python-docx / reportlab / matplotlib / pypdf / pyecharts；Windows 另装 pywin32）。
- **执行时工具 `timeout` 至少 300000 ms 并等待返回**；脚本返回接口失败/超时 → 原样回复「报告生成服务暂时不可用，请稍后重试。」

## 2. 四类产物（缺一不可）

| 产物 | 格式 | 生成方式 |
|---|---|---|
| 分享链接 | 在线 URL | `{title}.html` 经「发布应用」发布，**须用户同意** |
| Word | `.docx` | `save_report.py --format all` |
| PDF | `.pdf` | 同上（优先 docx→pdf 转换，保持与 Word 版式一致） |
| Markdown | `.md` | 同上（原文直写） |

- **PDF 策略（优先与 Word 版式一致）**：① Windows 且装有 Word + pywin32 → Word 导出；② LibreOffice/soffice 无头模式（`-env:UserInstallation` 指向可写临时目录）；③ 都不可用 → 回退 reportlab 重排版。
- 未获明确发布指令时：先交付三份本地文件（Word/PDF/MD），并询问是否发布为分享链接。
- 交付时向用户逐项列出四类产物的名称与用途。

## 3. 排版约束（脚本已内置，勿绕过）

1. **主标题**：正文首位的 `# 报告标题` 在 HTML 中只保留一个 `<h1>`（正文一级标题行自动去除），避免「两个标题头」；Word/PDF 中主标题居中、20pt，**段前＝段后＝16pt（约 1 行正文）**——严禁出现「标题上方一大片空白」，段前不要超过 24pt。正文写作时正常写 `# 报告标题` 即可。
2. **标题层级（Word/PDF）**：主标题 20pt > 一级章节（`## 5. 产业业绩表现`）13pt > 二级小节（`### 5.1 最新表现`）12pt > 正文 10.5pt。**不要在正文另设标题字号**。
3. **标题段前段后对称**：一级章节 12pt/12pt，二级小节 10pt/10pt，主标题 16pt/16pt。禁止「段前 10pt、段后 0pt」。
4. **行距**：Word/PDF **正文与标题统一 1.5 倍行距**（docx 写入 `line_spacing = 1.5` → `w:line=360 auto`；reportlab 回退路径亦按 fontSize×1.5 设置 leading）；HTML 保持 `line-height:1.75`，二者互不影响。
5. **图片**：Markdown 里的「`<!--img:assets/x.png-->` + 图表围栏」在 Word / PDF / HTML 侧自动折叠为同源 PNG（见 §5）；HTML 中本地图片自动内嵌 base64 data URI（脱离 `assets/` 也能显示）；DOCX/PDF 按原始宽高比等比缩放居中（DOCX ≤6.0×8.0 英寸，PDF ≤440×470 pt），不强制拉伸。
6. **饼图类近方形图自动缩小**：宽高比 0.72~1.6 的图按 3.4 英寸（PDF 300pt）；横向趋势图仍 6.0 英寸；HTML 中对近方形图加 `chart-pie` 类限制为 380px。**同一产物内饼图大小必须一致**。
7. **表格**：Markdown 表头分隔行（`| :--- |`）在 DOCX/PDF 被识别并剔除；PDF 表格按内容算列宽、单元格自动换行、表头跨页重复；正文与单元格文本做 XML 转义。DOCX 表格表头加粗、自动适应页宽。
8. **有序列表按列表独立重编号**：脚本为每段有序列表新建独立 `numId` 并写 `startOverride=1`，每个章节列表都从 1 开始，无需手工干预。
9. **中文字体跨平台回退**：PDF 用 Windows 雅黑/宋体 → Linux Noto CJK/文泉驿 → macOS 苹方。注意 Noto Sans CJK 为 CFF/OTF 轮廓，reportlab 无法嵌入，会回退文泉驿正黑等 TrueType 字体，属预期行为。matplotlib 出图须显式设置中文字体，否则图例/标题显示为方块。
10. **禁止两端对齐**：正文不要用 justify。
11. **Word/PDF 不展示溯源标记**：`[source:N]` 仅 MD 保留原文；HTML 自动渲染为可点击标签；docx/pdf 由脚本自动剔除。**正文写作时照常标注即可，无需手工删**。

## 4. 溯源规范

报告数据点与图表应可溯源（hover 看摘要、click 看完整面板）。

- **HTML 自动可点击**：`[source:N]` 由脚本转为可点击标签，悬停显示来源摘要，点击弹出完整来源面板（类型/标题/机构/发布时间/原文链接）。
- **溯源元数据（自动装配，优先于手工配置）**：脚本按以下顺序取元数据 ①`--sources_json`；②与内容文件同名的 `{报告名}.md.sources.json`；③**自动扫描运行期落盘的 `{outdir}/.sources/source-<N>.json`**（检索类来源读 `title/url/published_at/kind`；MQL 报表类无标题字段，自动生成「东方财富 Choice 报表：{报表名}」+ 取数日期）。一般无需手工准备 sources.json。
- **无元数据的标记一律不显示溯源符号**：若某 `[source:N]` 既无显式元数据、也无法从 `.sources/` 装配出标题或链接，脚本在 HTML 中**直接删除该标记**（与 Word/PDF 行为一致），**严禁**渲染成「未提供该标记的来源元数据」的空壳标签。弹窗内为空的字段也不再占用空行。

```json
{"sources": {"2": {"t": "标题", "o": "机构", "d": "日期", "k": "类型", "l": "链接"}}}
```

- **溯源报表名称映射（Hover 显示用）**：

| 数据块 | Hover 报表名 |
|---|---|
| 产业搜索 | 产业链首页_企业搜索 |
| 市场主题结构 | 产业深度分析_市场主题图谱 |
| 标准产业中游 | 产业深度分析_标准产业图谱(中游) |
| 标准产业上下游 | 产业深度分析_标准产业图谱(上下游) |
| 指数基本信息 | 指数F9_指数基本信息 |
| 指数业绩表现 | 指数F9_估值通道_周频 |
| 成分股详情 | 指数F9_成分数据_成分股详情(综合) |
| 指数成分行业分布 | 指数F9成分行业（当前走成分股「行业」聚合兜底） |
| 研报/资讯、公告/政策 | 妙想搜索 |

- Hover 格式：`来源: MQL ReportBlock / 报表: {中文简称} / 查询: {关键词} / 时间: {获取时间} / 字段: {字段名}`。
- **溯源标记口径遵循平台规则**：对话正文与 **Markdown 产物**必须为带 `[source:N]` 的工具结果挂标（`mx_finance_data` / `mx_finance_search` / `mx_macro_data` / `mx_stocks_screener` 及 skill 返回结果）；**docx/pdf/html** 默认不挂（脚本自动剔除），HTML 转为可点击标签。不得发明 <ref> 或 `[cite:N]`。

## 5. 图表双形态（默认写法，MD 用围栏 / Office 用 PNG）

**Markdown 交付件从写作阶段就直接用图表围栏，不依赖交付后再转换**——图表规范与「定位注释 + 围栏」写法见 `reference/chapters.md` §4。要点：

| 通道 | 形态 | 说明 |
|---|---|---|
| Markdown 交付件（含点「开」后的在线协同文档） | `<!--img:assets/xxx.png-->` + ```` ```echarts ````／```` ```mermaid ```` 围栏 | 编辑器前端直接渲染围栏；**不存在图片解析失败、显示占位框的问题** |
| Word / PDF / HTML | 同源 PNG（`assets/*.png`） | `save_report.py` 自动把「定位注释 + 围栏」折叠成 `![](assets/xxx.png)`，无需手工处理 |

- **禁止**在 Markdown 里只写 `![](assets/xxx.png)`（在线协同态会变成占位框）；也**禁止**只写围栏不带定位注释（Word/PDF 会丢图）。没有定位注释的围栏不会被折叠、也不会被删除。
- 饼图必须环状（`radius` 内径 ≥30%）、同类图尺寸统一（`width:600, height:320`）、类目 >9 个时归并为「其他」。
- **不要**把图片转成 base64 data URL 塞进文档（单图数百 KB，会撑爆上下文与节点体积）。
- 若某张图确实无法渲染：**直接删除该图节点，不要输出「暂无数据」之类的占位框**。

## 6. 安全与隐私

- 报告与图片保存到输出目录（`--outdir`）。
- 鉴权信息由 MQL 工具链 / 妙想 MCP 连接配置注入，**报告与本 Skill 中不出现任何 Key**。
- 数据全部来自东方财富 Choice，经 MQL ReportBlock 获取；查询仅在本地 Runtime 执行。
- 研究内容仅供参考，不构成投资建议；文末附固定免责声明。