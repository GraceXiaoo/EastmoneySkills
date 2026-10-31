# 快速构建流水线（V20：一次取数、一次构建、双格式同源）

本文件固化「分析完成后 → 双格式交付」的最小步骤，替代历史上每轮手写 HTML/docx 构建代码的做法。

## 为什么快（2026-10-30 复盘结论）

- 旧路径最耗时的是**报告组装与双格式构建**：每个企业/每期都要为 HTML 临时编写样式与章节装配脚本、为 Word 硬改模板、反复调试重建，约占整轮耗时的 40%+；其次是**章节正文反复扩写与返工**（口径不一致导致的重新生成）。
- 优化手段（不压缩质量）：
  1. **通用构建器**：`build_report_html.py`＋`build_report_docx.js` 只读一份 `report_input.json`，一次生成 HTML＋Word＋校验结果；模型不再编写任何构建代码。
  2. **单一事实源**：正文引用编号、表格、图注、预警分布计数都由同一份冻结正文/判断清单生成，杜绝「分布图 1 项 vs 3.3 蓝色 2 项」类跨组件不一致返工。
  3. **一次成型写作**：按 V20 要点化规范写作——1.2/1.3/2.1 表格即全部内容（不放重复文字总结，流转/口径并入表格 note），1.1 与 2.2/2.3/3.x/第四章按总述＋编号要点；引用在写作时即用最终 `[n]` 编号。
  4. **内置校验**：HTML 构建器自带标签配对校验（零错误才通过）；Word 完成后必须过 `docx XML 检查 + soffice→PDF 抽检`（命令见下）。

## 输入契约：report_input.json

构建器读取的唯一输入，模型在五任务正文冻结后填写：

```json
{
  "title": "企业全称预警监测报告",
  "meta": "监测期间：2026-07-30 至 2026-10-30",
  "sections": [
    {"h1": "一、监测信息总结"},
    {"h2": "1.1 舆情总结"},
    {"figures": [{"svg": "charts/public_opinion_wordcloud.svg", "caption": "图表1 舆情词云｜…", "png": "report_build/wc_out/public_opinion_wordcloud.png", "w": 620, "h": 302}]},
    {"figures": [{"svg": "charts/volume.svg", "caption": "图表2 …", "png": "report_build/charts_hi/volume.png", "w": 620, "h": 232}]},
    {"p": "…正文（**粗体**与[n]角标）…"},
    {"h2": "1.2 事件总结"},
    {"table": {"cols": ["时间", "事件主体", "事件简况", "事件类型", "舆情方向"],
               "rows": [["…", "…[1]", "…", "…", "…"]], "widths": [900, 1700, 4438, 1100, 1500], "note": "…"}},
    {"h2": "2.1 风险发酵链路"},
    {"figures": [{"svg": "charts/chain.svg", "caption": "图表3 …", "limited": false, "png": "report_build/charts_hi/chain.png", "w": 620, "h": 289}]},
    {"card": {"kind": "y", "title": "Y1｜…", "fields": [["事项说明", "…[1]"], ["触发依据", "…"], ["建议动作", "…"], ["解除条件", "…"]]}},
    {"list": ["**要点**：…[5]"]}
  ],
  "footnotes": {"1": ["标题", "机构", "2026-10-30", "https://…"], "2": ["…", "…", "…", ""]}
}
```

字段说明：
- `sections` 支持：`h1/h2` 章节标题、`p` 段落（可换行、自动识别 `N.` 列表当有序列表）、`list` 要点列表、`table` 五列表格（`cols/rows/widths/note`）、`card` 预警卡片（红/黄）、`figures`（`svg` 用于 HTML 内联，`png/w/h` 用于 Word）。
- `figures[]` 仅需 `svg/png/caption/w`；`h` 可不写——构建器按 PNG 实际尺寸自动校正（V22），保证 Word 嵌入长宽比与源图一致、字体不变形。
- `figures[].limited=true` 用于**词云/声量/分布/时间轴**（HTML 容器上限 640px，与 Word 620px 一致）；**链路图不设 limited，HTML 占满报告正文宽度**，保证两格式图内文字比例一致；图表内文字按 630px 显示基准反推字号（V20 统一字体体系）。
- `footnotes` 键为最终角标编号 `[n]`，正文/表格/图注中出现 `[n]` 即渲染为该编号的溯源角标；正文**不得**出现「事件库/未来事件库」等渠道名（V19）。

## 一次性构建命令（在任务工作目录内）

```text
# 1) 图表（第一次或图表数据变化时）
python3 -X utf8 <skill>/scripts/render_static_charts.py --mode volume      --data charts/volume_data.json      --out charts/volume.svg
python3 -X utf8 <skill>/scripts/render_static_charts.py --mode distribution --data charts/distribution_data.json --out charts/distribution.svg
python3 -X utf8 <skill>/scripts/render_static_charts.py --mode chain        --data charts/chain_data.json        --out charts/chain.svg
python3 -X utf8 <skill>/scripts/render_static_charts.py --mode timeline     --data charts/timeline_data.json     --out charts/timeline.svg
python3 -X utf8 <skill>/scripts/render_wordcloud.py --news-package composed/news_package.json \
  --labels wordcloud_labels.json --out wordcloud \
  --style <skill>/assets/wordcloud-style.json --font "<中文字体>"

# 2) HTML（含校验；同时输出 report_build/content.json 与 md_footnotes.json）
python3 -X utf8 <skill>/scripts/build_report_html.py --input report_input.json --workdir .

# 3) Word 图片管线（svg_inline → soffice 200dpi → PNG）
mkdir -p report_build/charts_hi report_build/wc_out
cp wordcloud/public_opinion_wordcloud.png report_build/wc_out/
for f in volume distribution chain timeline; do
  python3 -X utf8 <skill>/scripts/svg_inline.py charts/$f.svg --out report_build/charts_hi/${f}_inlined.svg
  soffice --headless -env:UserInstallation=file:///tmp/lo_lo --convert-to pdf --outdir report_build/charts_hi report_build/charts_hi/${f}_inlined.svg
  pdftoppm -png -r 200 -singlefile report_build/charts_hi/${f}_inlined.pdf report_build/charts_hi/${f}
done

# 4) Word（report_build 目录内执行）
cd report_build && export NODE_PATH=$(npm root -g) && node <skill>/scripts/build_report_docx.js

# 5) 验收（必须通过）
# HTML：build_report_html.py 输出 VALIDATION=PASS
# docx：解包校验 document.xml 良构、角标数、图片数；soffice 转 PDF 后 pdftoppm 抽页视觉核对
```

## 验收硬门槛

1. HTML 校验 PASS（无残留 `<details>`、标签配对、`<p>` 配对）。
2. Word 校验：`document.xml` 良构；正文/表格/图注角标编号与 HTML 一致；Word→PDF 页图抽检图内文字锐利完整（分布图文字与正文同大）。
3. 一致性：警告分布计数（红/黄/蓝/不设预警）在 分布图、图注、1.2 流转说明、第四章基线句中完全一致。
4. 无渠道名：正文/图注/表格不出现「事件库」「未来事件库」等来源说明（大事记归属只经溯源角标）。
5. 对话交付 = 目录＋核心概要（≤8 条），不返回整篇正文。