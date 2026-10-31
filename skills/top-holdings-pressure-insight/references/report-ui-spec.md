# 报告交互与版式规范（6.0）

## 1. 页首元信息

页首只展示以下三项：

- 数据截止日期
- 执行日期
- `数据来源：Choice数据`

数据来源不得扩写为具体报表、业务主题、MQL 取数或其他技术描述。

## 2. Hover + Click 原始数据溯源

### 2.1 用户效果

HTML 中的数据型结论、证券名称、关键数值和榜单标题均应设置为可溯源元素：

- Hover：只显示轻量提示“点击查看原始数据”，不展示技术信息。
- Click：打开模态弹层或右侧抽屉，直接展示对应报表本次 MQL 查询实际返回的数据表。
- Close：支持关闭按钮、点击遮罩和 `Esc` 键关闭。
- Keyboard：可溯源元素使用按钮或 `tabindex="0"`，支持 Enter/Space 打开，并具有清晰的 `:focus-visible` 样式。

不得只使用浏览器 `title` 属性，也不得把原始数据表常驻在正文或页尾。

### 2.2 点击后展示内容

弹层只展示业务可读的数据内容：

1. 弹层标题使用对应榜单的业务名称，例如“日度潜在买入 TOP20 原始数据”。
2. 显示该榜单本次 MQL 返回的完整数据表，保留实际字段、原始数值和原始顺序。
3. 点击证券、数值或表格行时，完整表格中对应记录应使用浅色背景和左侧强调线高亮，并自动滚动到该行。
4. 点击榜单标题时展示该榜单全部记录，不预设高亮行。
5. 点击由多张榜单共同支持的结论时，使用标签页或分组按钮切换各张完整数据表，并在每张表中高亮支撑该结论的记录。

弹层中禁止展示报表英文名、报表路径、MQL 脚本、请求参数、执行器信息或内部字段映射说明。上述技术信息仅保留在生成过程内部。

### 2.3 推荐 HTML 数据结构

```html
<button class="traceable" type="button" data-trace-id="daily-buy-001">
  301202.SZ 朗威股份
  <span class="trace-hint" role="tooltip">点击查看原始数据</span>
</button>

<script type="application/json" id="trace-data">
{
  "daily-buy-001": {
    "title": "日度潜在买入 TOP20 原始数据",
    "datasets": ["daily-buy"],
    "highlight": {"daily-buy": ["301202.SZ"]}
  }
}
</script>

<script type="application/json" id="report-data">
{
  "daily-buy": {
    "title": "日度潜在买入 TOP20 原始数据",
    "columns": ["排名", "股票代码带后缀", "股票简称", "所属行业", "潜在买入压力"],
    "rows": [{"排名": 1, "股票代码带后缀": "301202.SZ"}]
  }
}
</script>
```

`report-data` 必须由本次 MQL Runtime 的实际返回结果生成。实际生成时必须对嵌入 JSON 和 HTML 文本进行安全转义，不得把未转义的原始值直接拼入脚本。

### 2.4 视觉要求

- 可溯源元素可用细虚线下划线、小型信息图标或轻微背景变化提示交互，不使用刺眼高亮。
- Hover 提示应位于元素附近且不遮挡主要数据。
- 弹层标题、表头和强调线使用 `#8B1E2D`；正文使用深灰。原始数据表应支持横向滚动、固定表头和高亮定位。
- 打印和 PDF 样式中隐藏 tooltip、遮罩、弹层和交互图标。

## 3. 四榜概览与明细

### 3.1 “2.1 概览”结构

使用四张卡片，不使用连续段落模拟表格：

```html
<div class="overview-grid">
  <article class="overview-card">
    <h4>日度潜在卖出</h4>
    <div class="leader-list">...</div>
    <p class="industry-summary">...</p>
    <p class="overview-note">...</p>
  </article>
</div>
```

最低样式约束：

```css
.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.overview-card {
  border: 1px solid #e5e7eb;
  border-top: 3px solid #8B1E2D;
  border-radius: 8px;
  padding: 16px 18px;
  background: #fff;
  color: #1f2937;
}
.overview-card h4 { color: #8B1E2D; margin: 0 0 10px; }
.overview-card p, .leader-list { color: #374151; line-height: 1.7; }
@media (max-width: 800px) {
  .overview-grid { grid-template-columns: 1fr; }
}
```

禁止：正文浅灰、单行塞入多个榜单、用 `>` 分隔证券、用空格模拟列、四张榜单无视觉边界。

### 3.2 “2.2 明细榜单”结构

每张榜单只保留三级标题和表格：

```html
<h3>日度潜在卖出 TOP20</h3>
<div class="table-wrap">
  <table>...</table>
</div>
```

标题与表格之间不得插入说明段落；表格结束后不得添加小字号注释。跨周期匹配规则、字段口径和限制统一移至报告末尾“数据说明”。

## 4. 交付检查

- 页首是否严格显示“数据来源：Choice数据”。
- 2.1 是否为四张独立卡片，正文是否为深色且在白底清晰可读。
- 2.2 的每张标题是否直接连接表格，前后是否没有多余小字说明。
- 任取至少一个核心结论、一个证券和一个榜单标题，验证 hover 提示、点击弹层、关闭和键盘操作。
- 点击后是否展示对应报表本次实际返回的完整数据表，而不是报表路径、请求参数或 MQL 脚本。
- 单证券点击是否高亮对应行；跨榜结论点击是否能切换相关榜单并高亮支撑记录。
- 弹层的数据行数、字段、顺序和数值是否与本次 MQL 返回结果一致。
- 打印/PDF 中是否隐藏交互控件与弹层内容。

## 5. 打印稳定性

- 打印样式必须隐藏 tooltip、遮罩、弹层、交互图标和仅用于屏幕操作的控件。
- 宽表报告默认整份 A4 横向，避免依赖不同浏览器支持不一致的章节级 `@page` 方向切换。
- 表格允许横向滚动仅用于屏幕；打印时必须通过列宽、换行或拆表适配纸张，不得把滚动区域直接裁切进 PDF。
- 使用 `break-inside: avoid` 保护概览卡片和短表，长表允许跨页并重复表头；避免对整个长表设置不可分页。
- 打印前确认所有字体和资源来自本地或内联，不等待外部网络资源。
