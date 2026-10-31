# HTML 报告规范（按需加载）

> 本文件在渲染 HTML 报告步骤时加载，包含：HTML 骨架模板、数据表格模板、ECharts 渲染规范、格式硬约束。

## HTML 骨架模板

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{转债简称}({转债代码})可转债研究</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: "Microsoft YaHei", "PingFang SC", "Helvetica Neue", Arial, sans-serif; background: #f5f6fa; color: #2c3e50; line-height: 1.8; padding: 24px 0; }
  .report-container { max-width: 900px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 16px rgba(0,0,0,0.08); overflow: hidden; }
  .report-header { background: linear-gradient(135deg, #2a1a4a 0%, #4a2c7a 100%); color: #fff; padding: 36px 40px 28px; }
  .report-header h1 { font-size: 22px; font-weight: 600; margin-bottom: 12px; line-height: 1.4; }
  .report-header .meta { font-size: 13px; color: rgba(255,255,255,0.7); margin-bottom: 8px; }
  .report-header .disclaimer-top { font-size: 12px; color: rgba(255,255,255,0.5); border-left: 3px solid rgba(255,255,255,0.3); padding-left: 10px; margin-top: 10px; }
  .report-body { padding: 32px 40px 40px; }
  h2 { font-size: 17px; font-weight: 600; color: #2a1a4a; margin: 32px 0 16px; padding-left: 12px; border-left: 4px solid #FF9044; line-height: 1.5; }
  h3 { font-size: 14px; font-weight: 500; color: #666; margin: 20px 0 8px; }
  p { font-size: 14px; color: #333; margin-bottom: 14px; text-align: justify; line-height: 2; }
  strong { color: #2a1a4a; font-weight: 600; }
  .chart-container { width: 100%; height: 380px; margin: 16px 0 24px; border: 1px solid #eef0f4; border-radius: 8px; background: #fff; }
  .summary-box { background: linear-gradient(135deg, #fff5f0 0%, #fee8f0 100%); border-left: 4px solid #FF9044; border-radius: 8px; padding: 20px 24px; margin: 16px 0 8px; }
  .summary-box p { margin-bottom: 0; font-size: 13.5px; }
  .section-divider { height: 1px; background: linear-gradient(90deg, transparent, #e0e0e0, transparent); margin: 28px 0; }
  .data-table { width: 100%; border-collapse: collapse; margin: 16px 0 24px; font-size: 13px; }
  .data-table caption { caption-side: top; text-align: left; font-size: 14px; font-weight: 600; color: #2a1a4a; margin-bottom: 8px; }
  .data-table th { background: #2a1a4a; color: #fff; padding: 10px 12px; text-align: center; font-weight: 500; }
  .data-table td { padding: 8px 12px; text-align: center; border-bottom: 1px solid #eef0f4; }
  .data-table tr:nth-child(even) { background: #f8f9fb; }
  .footer { background: #f8f9fb; padding: 20px 40px; text-align: center; font-size: 12px; color: #999; border-top: 1px solid #eef0f4; }
  .footer p { font-size: 12px; color: #999; text-align: center; }
</style>
</head>
<body>
<div class="report-container">
  <div class="report-header">
    <h1>{转债简称}({转债代码})可转债研究</h1>
    <div class="meta">生成时间：{YYYY年MM月DD日 HH时mm分ss秒}</div>
    <div class="disclaimer-top">内容由 AI 生成，仅供专业研究参考，不构成任何投资建议。</div>
  </div>
  <div class="report-body">

    <h2>摘要</h2>
    <div class="summary-box">
      <p>{摘要正文}</p>
    </div>

    <div class="section-divider"></div>

    <!-- 每个分析段落：标题 + 正文 + 图表（先文后图） -->
    <h2>{段落标题}</h2>
    <p>{段落正文}</p>
    <h3>图表：{图表标题}</h3>
    <div id="chart1" class="chart-container"></div>

    <div class="section-divider"></div>

    <!-- 数据表格 -->
    <h2>关键指标速览</h2>
    <table class="data-table">
      <caption>可转债分析指标表</caption>
      <thead><tr>...</tr></thead>
      <tbody><tr>...</tr></tbody>
    </table>

    <!-- ... 后续段落同结构 ... -->

  </div>
  <div class="footer">
    <p>内容由 AI 生成，仅供参考，不代表开发者立场，请知悉。</p>
  </div>
</div>

<script>
(function(){
  var chart = echarts.init(document.getElementById('chart1'));
  chart.setOption({ /* ECharts option */ });
})();
</script>
</body>
</html>
```

## 数据表格模板

> 所有表格中的数值单元格（价格、比例、收益率、波动率、规模、PE/PB 等）一律输出保留 4 位小数的值（`toFixed(4)`，如 `134.3070`）；字符串类与日期类原样输出。

### cbtable 可转债分析指标表（存续期）

```html
<table class="data-table">
  <caption>可转债分析指标表</caption>
  <thead>
    <tr>
      <th>转债简称</th><th>剩余年限(年)</th><th>转股价(元)</th><th>转债价格(元)</th><th>转股价值(元)</th><th>纯债价值(元)</th><th>到期收益率(%)</th><th>转股溢价率(%)</th><th>纯债溢价率(%)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>{转债简称或-}</td><td>{剩余年限或-}</td><td>{转股价或-}</td><td>{转债价格或-}</td><td>{转股价值或-}</td><td>{纯债价值或-}</td><td>{到期收益率或-}</td><td>{转股溢价率或-}</td><td>{纯债溢价率或-}</td>
    </tr>
  </tbody>
</table>
```

### stocktable 正股分析指标表（存续期）

```html
<table class="data-table">
  <caption>正股分析指标表</caption>
  <thead>
    <tr>
      <th>正股简称</th><th>正股行业</th><th>正股现价(元)</th><th>PE_TTM</th><th>PB</th><th>ROE</th><th>资产负债率(%)</th><th>每股净资产</th><th>近一年营收增速(%)</th><th>近一年净利润增速(%)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>{正股简称或-}</td><td>{正股行业或-}</td><td>{正股现价或-}</td><td>{PE_TTM或-}</td><td>{PB或-}</td><td>{ROE或-}</td><td>{资产负债率或-}</td><td>{每股净资产或-}</td><td>{营收增速或-}</td><td>{净利润增速或-}</td>
    </tr>
  </tbody>
</table>
```

### cbcxtable 存续期市场表现表（到期可转债）

```html
<table class="data-table">
  <caption>可转债存续期市场表现表</caption>
  <thead>
    <tr>
      <th>转债简称</th><th>发行规模(亿元)</th><th>剩余规模(亿元)</th><th>上市首日价格(元)</th><th>存续期最高价/最低价(元)</th><th>转股溢价率区间(%)</th><th>纯债溢价率区间(%)</th><th>正股存续期涨跌幅(%)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>{转债简称或-}</td><td>{发行规模或-}</td><td>{剩余规模或-}</td><td>{上市首日价格或-}</td><td>{最高价}/{最低价}</td><td>{溢价率区间或-}</td><td>{纯债溢价率区间或-}</td><td>{正股涨跌幅或-}</td>
    </tr>
  </tbody>
</table>
```

### cbtctable 退出方式分布表（到期可转债）

```html
<table class="data-table">
  <caption>可转债退出方式分布表</caption>
  <thead>
    <tr>
      <th>转债简称</th><th>转股金额(万元)</th><th>转股比例(%)</th><th>赎回金额(万元)</th><th>赎回比例(%)</th><th>回售金额(万元)</th><th>回售比例(%)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>{转债简称或-}</td><td>{转股金额或-}</td><td>{转股比例或-}</td><td>{赎回金额或-}</td><td>{赎回比例或-}</td><td>{回售金额或-}</td><td>{回售比例或-}</td>
    </tr>
  </tbody>
</table>
```

## ECharts HTML 渲染规范

- `<div id="chartN" class="chart-container">` 容器
- IIFE 包裹 `echarts.init()` + `setOption()`
- `option` 为合法 JavaScript 对象
- 每个图表 IIFE 必须独立，禁止变量共享
- **数值精度**：图表中展示的数值（轴 label、tooltip、柱/线条上的数值标签）一律用 `toFixed(4)` 保留 4 位小数，例如 `tooltip: { trigger:'axis', confine:true, valueFormatter: function(v){ return (v==null?'-':v.toFixed(4)); } }`、「`label.formatter` 用 `function(p){ return p.value.toFixed(4); }`」；数值型的 y 轴可配合 `axisLabel.formatter`

图表类型参考（根据个券状态和数据可用性选择）：

- **存续期可转债**：
  - 仅输出条款触发进度雷达图（强赎/下修/回售进度）一个图表，置于「条款博弈」维度正文之后（先文后图）
  - 不输出转债价格 vs 转股价值 vs 纯债价值对比柱状图
  - 不输出正股财务与估值指标雷达图
- **到期可转债**：
  - 不输出存续期价格走势折线图（最高价/最低价/上市首日价格标记）
  - 不输出退出方式占比饼图（转股/赎回/回售比例）
- **新发可转债**：
  - 上市首日价格区间预测柱状图（悲观/中性/乐观情景）
  - 可比溢价率对比柱状图

## 格式硬约束

1. **标题**：`<h1>` 格式固定为 `{转债简称}({转债代码})可转债研究`，使用英文括号，例如 `中贝转债(113678.SH)可转债研究`
2. **生成时间**：精确到秒，格式 `YYYY年MM月DD日 HH时mm分ss秒`
3. **段落结构**：每个段落由「`<h2>` 段落标题 + `<p>` 段落正文 + `<h3>` 图表标题 + `<div>` 图表容器」构成，**先文后图**（图表置于对应段落正文之后，而非正文之前）；段落标题须根据本段实际分析内容**二次总结凝练**，严禁使用固定模板标题
4. **可视化图表**：引入 ECharts CDN（`https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js`），每个图表用 `<div id="chartN">` 容器 + IIFE 包裹的 `<script>` 渲染；遵循 Choice 可视化色板 E001-E004（#FF9044/#4392F2/#24C0C0/#FFB70B）、`symbol:'emptyCircle'`、`symbolSize:6`、`lineStyle.width:2`、`grid:{left:8,right:16,top:48,bottom:48,containLabel:true}`、`tooltip:{trigger:'axis',confine:true}`、`barMaxWidth:24`；每种图表最多1次，全文 ≤ 5个
5. **重点加粗**：`<strong>` 标签，同一自然段不超过3处
6. **字数**：正文分析 ≥ 800字
7. **摘要**：不插入图表
8. **数值精度**：报告中所有数值型指标（价格、比例、收益率、波动率、规模、PE/PB 等）一律保留 **4 位小数**
   - 表格单元（`<td>`）直接输出 `toFixed(4)` 后的值，如 `134.3070`、`64.5281`、`81.6317`
   - 图表轴标签、`tooltip.formatter`、`label.formatter` 均用 `toFixed(4)` 格式化，如 `formatter: function(p){ return p.value.toFixed(4); }`
   - 正文行文中引用指标数值时同样保留 4 位小数，与表格/图表保持一致
   - 字符串类（转债简称、行业、条款、区间、说明等）与日期类原样输出，不受精度约束
9. **输出**：完整 HTML 文件
