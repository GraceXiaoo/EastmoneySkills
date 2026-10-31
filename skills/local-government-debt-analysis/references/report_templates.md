# HTML 报告可视化模板（地方化债研究报告 2.0）

本文件提供「地方化债研究报告」HTML 输出的骨架模板与图表样例。生成报告时必须：
- 使用**真实接口数据**（或由其测算），不得虚构数值；
- 图表数量 = 分析维度数（**4~7 张**），与正文维度一一对应；
- 优先 ECharts（CDN），CDN 失效降级为内联 SVG；
- 中国市场配色：**涨用红（#E60012 系）、跌用绿（#0A8F43 系）**；
- 中文字体：`Microsoft YaHei, PingFang SC, sans-serif`。

## 一、HTML 骨架模板

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{地区名称}地方化债研究</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  :root{ --primary:#E60012; --up:#E60012; --down:#0A8F43; --ink:#1a1a1a;
         --sub:#666; --line:#e8e8e8; --card:#f7f8fa; }
  body{ font-family:"Microsoft YaHei","PingFang SC",sans-serif; color:var(--ink);
        max-width:960px; margin:0 auto; padding:32px 24px; line-height:1.8; }
  h1{ font-size:28px; border-bottom:3px solid var(--primary);
      padding-bottom:12px; margin-bottom:6px; }
  .meta{ color:var(--sub); font-size:13px; margin-bottom:24px; }
  section{ margin:32px 0; }
  h2{ font-size:20px; padding-left:10px; border-left:4px solid var(--primary); }
  .chart{ width:100%; height:360px; margin:14px 0; }
  .chart-tall{ height:440px; }
  p{ text-align:justify; }
  strong{ color:var(--primary); font-weight:700; }
  .note{ color:var(--sub); font-size:12px; }
  table{ border-collapse:collapse; width:100%; font-size:13px; }
  th,td{ border:1px solid var(--line); padding:6px 10px; text-align:right; }
  th{ background:var(--card); }
  .abstract{ background:var(--card); border-radius:8px; padding:16px 20px; }
  .disclaimer{ margin-top:40px; padding:16px; background:#fafafa;
               border-top:1px solid var(--line); font-size:12px; color:var(--sub); }
  @media print{ .chart{ page-break-inside:avoid; } }
</style>
</head>
<body>
  <h1>{地区名称}地方化债研究</h1>
  <p class="meta">生成时间：{YYYY年MM月DD日 HH时mm分ss秒} · 数据来源：东方财富Choice</p>

  <section class="abstract">
    <h2>摘要</h2>
    <p>{150~250 字摘要}</p>
  </section>

  <!-- 4~7 个维度：每个 = 维度标题 + 图表 + 正文 -->
  <section>
    <h2>{维度标题}</h2>
    <div id="chart-1" class="chart"></div>
    <p>{维度正文，重点加粗}</p>
    <p class="note">数据来源：东方财富Choice</p>
  </section>
  <!-- 重复至 4~7 个维度 -->

  <section class="disclaimer">
    <h2>免责声明</h2>
    <p>{免责声明文字，见 SKILL.md 模板}</p>
  </section>

<script>
  // 在 echarts.init 前做 CDN 可用性检查，加载失败走内联 SVG 降级
  if (typeof echarts === "undefined") {
    document.querySelectorAll(".chart").forEach(function(el){
      el.innerHTML = "<svg viewBox='0 0 600 300' xmlns='http://www.w3.org/2000/svg'>"
        + "<text x='300' y='150' text-anchor='middle' fill='#999'>图表渲染组件不可用，数据见段落正文</text></svg>";
    });
  }
</script>
</body>
</html>
```

## 二、维度 → 图表映射（与 analysis_dimensions.md 对应）

| 维度 | 推荐图表 | ECharts 类型 |
|---|---|---|
| 一 债务压力与结构 | 三层债务结构 + 广义债务率 | `pie`/堆叠 `bar` + `bar`（含涨跌染色） |
| 二 政府债发行节奏与计划执行 | 全年额度累计落地进度 + 省份×券种季度计划发行额 | `line` + `heatmap`（**不出明细表**） |
| 三 偿债洪峰与流动性 | 地方债偿还 vs 城投债偿还 | 堆叠 `bar` + `markLine`（覆盖倍数） |
| 四 财政内生偿债能力 | 本息覆盖率 + 收支缺口 + 房价环比 | `gauge`/`bar` + `line` |
| 五 化债进度与执行强度 | 动作强度信号计数 + 事件卡片 | `bar` + HTML 卡片 |
| 六 化债方式与政策工具 | 六类工具使用频次 | `pie`/`bar` |
| 七 风险等级与前景研判 | 风险矩阵 + 红橙黄绿名单 | `scatter`（气泡）+ `table` |

## 三、ECharts 常用写法

### 1. 三层债务结构（堆叠柱 / 饼图）

```js
c.setOption({
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
  legend: { data: ["显性(专项债余额)","隐性(隐债规模)","经营性(城投及地方国企债务)"] },
  xAxis: { type: "category", data: ["{本地区}"] },
  yAxis: { type: "value", name: "亿元" },
  series: [
    { name: "显性(专项债余额)", type: "bar", stack: "d", data: [..], itemStyle:{color:"#E60012"} },
    { name: "隐性(隐债规模)", type: "bar", stack: "d", data: [..], itemStyle:{color:"#F5A623"} },
    { name: "经营性(城投及地方国企债务)", type: "bar", stack: "d", data: [..], itemStyle:{color:"#4A90D9"} }
  ]
});
```

### 2. 堆叠柱状（未来偿债：地方债偿还 + 城投债偿还）＋覆盖倍数标注

```js
c.setOption({
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
  legend: { data: ["地方债偿还(亿)","城投债偿还(亿)"] },
  xAxis: { type: "category", data: ["未来1年","未来2年"] },
  yAxis: { type: "value", name: "亿元" },
  series: [
    { name: "地方债偿还(亿)", type: "bar", stack: "t", data: [..], itemStyle:{color:"#E60012"},
      markLine: { data: [{ yAxis: .., name: "可供还债资金" }], lineStyle:{color:"#999",type:"dashed"} } },
    { name: "城投债偿还(亿)", type: "bar", stack: "t", data: [..], itemStyle:{color:"#F5A623"} }
  ]
});
```

### 3. 仪表盘（本息覆盖率）

```js
c.setOption({
  series: [{
    type: "gauge", min: 0, max: 300, splitNumber: 6,
    progress: { show: true, width: 16, itemStyle: { color: "#E60012" } },
    axisLine: { lineStyle: { width: 16, color: [[0.1,"#0A8F43"],[0.2,"#F5A623"],[1,"#E60012"]] } },
    axisLabel: { formatter: "{value}%" },
    detail: { valueAnimation: true, formatter: "{value}%", fontSize: 26 },
    data: [{ value: .., name: "本息覆盖率" }]
  }]
});
```

### 4. 条件染色柱状（覆盖倍数 / 增减，正负红绿）

```js
series: [{
  type: "bar",
  data: [..].map(function(v){ return {
    value: v, itemStyle: { color: v >= 0 ? "#E60012" : "#0A8F43" }
  };})
}]
```

### 5. 全国对比 + 高亮本地区

```js
var target = "{本地区名}";
series: [{
  type: "bar", data: dataList.map(function(d){
    return { value: d.value,
      itemStyle: { color: d.name === target ? "#E60012" : "#C9CDD4" } };
  })
}]
```

### 6. 风险矩阵气泡（维度六）

```js
c.setOption({
  xAxis: { type: "value", name: "偿债压力指数", min: 0 },
  yAxis: { type: "value", name: "内生偿债能力(覆盖率%)" },
  series: [{
    type: "scatter",
    data: points, // [[压力, 覆盖率, 化债强度, "地区名"], ...]
    symbolSize: function (val) { return Math.max(10, Math.min(50, val[2])); },
    itemStyle: { color: "#E60012", opacity: 0.65 },
    label: { show: true, formatter: function(p){ return p.data[3]; }, position: "top" },
    markLine: { silent: true, data: [
      { xAxis: .., name: "压力均值" }, { yAxis: .., name: "能力均值" }
    ] }
  }]
});
```

### 7. 热力图（省份 × 券种季度计划发行额，维度二）

```js
c.setOption({
  tooltip: { position: "top" },
  xAxis: { type: "category", data: ["新增一般债","再融资一般债","新增专项债","再融资专项债"] },
  yAxis: { type: "category", data: provinceList },
  visualMap: { min: 0, max: maxVal, calculable: true, orient: "horizontal",
               inRange: { color: ["#FDF3F3","#F5A623","#E60012"] } },
  series: [{ type: "heatmap", data: heatData /* [x, y, value] */ }]
});
```

## 四、内联 SVG 降级（CDN 不可用时）

每张图至少准备一个内联 SVG 静态版本兜底：

```html
<svg viewBox="0 0 640 320" xmlns="http://www.w3.org/2000/svg" font-family="Microsoft YaHei">
  <line x1="60" y1="30" x2="60" y2="260" stroke="#999"/>
  <line x1="60" y1="260" x2="600" y2="260" stroke="#999"/>
  <rect x="80" y="120" width="60" height="140" fill="#E60012"/>
  <text x="110" y="110" text-anchor="middle" font-size="12">2023: {值}</text>
  ...
</svg>
```

## 五、事件卡片（政府化债动态 / 政策）

```html
<div style="border-left:3px solid #E60012;padding:8px 14px;margin:10px 0;background:#fafafa;">
  <p style="margin:0;font-weight:700;">{公告标题}</p>
  <p style="margin:2px 0;color:#666;font-size:13px;">{地区} · {公告时间} · 来源：东方财富Choice</p>
  <p style="margin:4px 0;">{化债进度 / 化债展望摘要}</p>
  {# 有链接时}<a href="{NOTICE_URL}" target="_blank" rel="noopener">查看公告原文 →</a>
</div>
```

## 六、质量要求

1. 图表数据 100% 来自接口返回（或由其测算），禁止手写样例数值。
2. 无数据的维度不渲染图表，段落用文字说明“数据披露滞后”。
3. 图表数量 = 分析维度数（4~7 张）；维度数不得超出 4~7。
4. 图表高度不小于 320px；大图（全国对比/风险矩阵/事件时间轴）用 `chart-tall`。
5. 数值保留 2 位小数；单位在图例或标题中注明；测算指标注明“测算”与公式，**公式、标签与脚注一律用中文口径名称，严禁出现报表名（`RPT_...`）与字段英文名**。
6. 红色系用于上涨/压力抬升，绿色系用于下跌/压力缓解，符合中国市场习惯。
7. 数据来源标注一律为“数据来源：东方财富Choice”，不附加接口名、参数或口径解释。
8. 维度正文精简（1~3 段），不出现“本维度回答……”等元表述，不单列“解读/解读要点”小节。
9. “政府债发行节奏与计划执行”维度仅用折线图 + 热力图，不渲染各省分券种计划发行额明细表。