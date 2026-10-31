# HTML 一页纸版式规范（references/html-guide.md）

本文件定义信用利差分析技能的 HTML 一页纸报告版式规范，包括配色、段落样式、表格、图表规格与完整骨架模板。

## 1. 通用约束

- 交付物：**单个自包含 HTML 文件**（内联 CSS/JS，无外部依赖；图表可引用 ECharts CDN）
- 文件标题与文件名：`信用利差分析(xxxx-xx-xx)`
- 语言：中文；利差单位统一为 **bp**，保留 2 位小数；注明基准曲线和计算口径
- 正文字数：约 1200-1500 字（不含图表与图注）
- 结尾注明：`本报告数据来源于 Choice 数据中心等公开渠道，仅供参考，不构成投资建议`

## 2. 配色规范

| 用途 | 色值 | 说明 |
|------|------|------|
| 主色（深蓝） | `#1a3a4a` | 头部渐变、标题、表头 |
| 强调色（青） | `#24C0C0` | 左侧条、焦点 |
| 图表色板 E001-E004 | `#FF9044 / #4392F2 / #24C0C0 / #FFB70B` | 折线/柱状系列 |
| 极低/偏窄 | `#24C0C0`（青） | 历史分位<20% |
| 极高/偏阔 | `#FF9044`（橙） | 历史分位>80% |
| 上行 | `#FF5252`（红） | 变化>0 |
| 下行 | `#4CAF50`（绿） | 变化<0 |
| 背景 | `#f5f6fa` / 卡片 `#fff` | |

> 注：遵循"涨红跌绿"中文市场惯例；报告中"利差走阔"用暖色提示、"利差收窄"用冷色提示，与收益率上行/下行颜色规则一致。

## 3. HTML 骨架模板

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>信用利差分析(xxxx-xx-xx)</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: "Microsoft YaHei", "PingFang SC", "Helvetica Neue", Arial, sans-serif; background: #f5f6fa; color: #2c3e50; line-height: 1.8; padding: 24px 0; }
  .report-container { max-width: 960px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 16px rgba(0,0,0,0.08); overflow: hidden; }
  .report-header { background: linear-gradient(135deg, #1a3a4a 0%, #2c6a7a 100%); color: #fff; padding: 36px 40px 28px; }
  .report-header h1 { font-size: 22px; font-weight: 600; margin-bottom: 12px; line-height: 1.4; }
  .report-header .meta { font-size: 13px; color: rgba(255,255,255,0.7); margin-bottom: 8px; }
  .report-header .disclaimer-top { font-size: 12px; color: rgba(255,255,255,0.5); border-left: 3px solid rgba(255,255,255,0.3); padding-left: 10px; margin-top: 10px; }
  .report-body { padding: 32px 40px 40px; }
  h2 { font-size: 17px; font-weight: 600; color: #1a3a4a; margin: 32px 0 16px; padding-left: 12px; border-left: 4px solid #24C0C0; line-height: 1.5; }
  h3 { font-size: 14px; font-weight: 500; color: #666; margin: 20px 0 8px; }
  p { font-size: 14px; color: #333; margin-bottom: 14px; text-align: justify; line-height: 2; }
  strong { color: #1a3a4a; font-weight: 600; }
  .chart-container { width: 100%; height: 380px; margin: 16px 0 24px; border: 1px solid #eef0f4; border-radius: 8px; background: #fff; }
  .summary-box { background: linear-gradient(135deg, #f0fffa 0%, #e8f8fe 100%); border-left: 4px solid #24C0C0; border-radius: 8px; padding: 20px 24px; margin: 16px 0 8px; }
  .summary-box p { margin-bottom: 0; font-size: 13.5px; }
  .summary-box ul { margin: 8px 0 0 20px; }
  .summary-box li { font-size: 13.5px; margin-bottom: 6px; }
  .section-divider { height: 1px; background: linear-gradient(90deg, transparent, #e0e0e0, transparent); margin: 28px 0; }
  .spread-table { width: 100%; border-collapse: collapse; margin: 16px 0 24px; font-size: 12px; }
  .spread-table caption { caption-side: top; text-align: left; font-size: 14px; font-weight: 600; color: #1a3a4a; margin-bottom: 8px; }
  .spread-table th { background: #1a3a4a; color: #fff; padding: 8px 10px; text-align: center; font-weight: 500; }
  .spread-table td { padding: 6px 8px; text-align: center; border-bottom: 1px solid #eef0f4; }
  .spread-table tr:nth-child(even) { background: #f8f9fb; }
  .spread-table .low { color: #24C0C0; font-weight: 500; }
  .spread-table .high { color: #FF9044; font-weight: 500; }
  .spread-table .up { color: #FF5252; }
  .spread-table .down { color: #4CAF50; }
  .footer { background: #f8f9fb; padding: 20px 40px; text-align: center; font-size: 12px; color: #999; border-top: 1px solid #eef0f4; }
  .footer p { font-size: 12px; color: #999; text-align: center; }
</style>
</head>
<body>
<div class="report-container">
  <div class="report-header">
    <h1>信用利差分析报告</h1>
    <div class="meta">分析日期：{YYYY年MM月DD日} | 基准：{基准曲线} | 历史分位窗口：{X}年 | 数据来源：Choice 数据中心{与公开渠道}</div>
    <div class="disclaimer-top">内容由 AI 生成，仅供专业研究参考，不构成任何投资建议。</div>
  </div>
  <div class="report-body">

    <!-- 一、结论摘要 -->
    <h2>结论摘要</h2>
    <div class="summary-box">
      <ul>
        <li>结论1...</li>
        <li>结论2...</li>
        <li>结论3...</li>
        <li>结论4...</li>
        <li>结论5...</li>
      </ul>
    </div>

    <div class="section-divider"></div>

    <!-- 二、利差温度计 -->
    <h2>利差温度计</h2>
    <p>{总分与状态描述}（分项：品种利差×  / 期限利差×  / 评级利差×  / 流动性×  / 供需×）</p>

    <div class="section-divider"></div>

    <!-- 三、分维度分析 -->
    <h2>分维度分析</h2>
    <h3>品种利差</h3>
    <p>{段落正文}</p>
    <table class="spread-table">
      <caption>品种利差（bp/历史分位/近1月变化bp）</caption>
      <thead>
        <tr><th>品种</th><th>期限</th><th>评级</th><th>当前利差</th><th>历史分位</th><th>近1月变化</th><th>近3月变化</th><th>判断</th><th>风险</th></tr>
      </thead>
      <tbody><!-- 数据行 --></tbody>
    </table>

    <h3>期限利差</h3>
    <p>{段落正文}</p>
    <table class="spread-table">
      <caption>期限利差（bp）</caption>
      <thead>
        <tr><th>品种</th><th>组合</th><th>当前利差</th><th>历史分位</th><th>近1月变化</th><th>曲线形态</th><th>判断</th></tr>
      </thead>
      <tbody><!-- 数据行 --></tbody>
    </table>

    <h3>评级利差</h3>
    <p>{段落正文}</p>
    <table class="spread-table">
      <caption>评级利差（bp）</caption>
      <thead>
        <tr><th>品种</th><th>期限</th><th>组合</th><th>当前利差</th><th>历史分位</th><th>近1月变化</th><th>判断</th></tr>
      </thead>
      <tbody><!-- 数据行 --></tbody>
    </table>

    <h3>利差矩阵</h3>
    <table class="spread-table">
      <caption>利差矩阵（bp/历史分位/近1月变化）</caption>
      <thead>
        <tr><th>品种\期限</th><th>1Y</th><th>3Y</th><th>5Y</th><th>7Y</th><th>10Y</th></tr>
      </thead>
      <tbody><!-- 品种行，单元格 数值/分位/变化 --></tbody>
    </table>

    <div class="section-divider"></div>

    <!-- 四、驱动归因 -->
    <h2>驱动归因</h2>
    <table class="spread-table">
      <caption>利差驱动因素</caption>
      <thead>
        <tr><th>维度</th><th>现状</th><th>对利差影响</th><th>关键指标</th></tr>
      </thead>
      <tbody>
        <tr><td>宏观</td><td>...</td><td>...</td><td>...</td></tr>
        <tr><td>政策</td><td>...</td><td>...</td><td>...</td></tr>
        <tr><td>资金</td><td>...</td><td>...</td><td>...</td></tr>
        <tr><td>信用</td><td>...</td><td>...</td><td>...</td></tr>
        <tr><td>供需</td><td>...</td><td>...</td><td>...</td></tr>
        <tr><td>机构</td><td>...</td><td>...</td><td>...</td></tr>
      </tbody>
    </table>

    <div class="section-divider"></div>

    <!-- 五、未来推演 -->
    <h2>未来推演</h2>
    <p><strong>1-5 日：</strong>...</p>
    <p><strong>1-2 周：</strong>...</p>
    <p><strong>1-3 月：</strong>...</p>
    <p><strong>关键触发因素：</strong>...</p>

    <div class="section-divider"></div>

    <!-- 六、跟踪清单 -->
    <h2>跟踪清单</h2>
    <table class="spread-table">
      <caption>关键利差跟踪指标（阈值按历史分位与市场校准）</caption>
      <thead>
        <tr><th>指标</th><th>当前值</th><th>偏窄阈值</th><th>偏阔阈值</th><th>信号</th></tr>
      </thead>
      <tbody>
        <tr><td>10Y-1Y 国债</td><td>...</td><td>&lt;50BP</td><td>&gt;100BP</td><td>...</td></tr>
        <tr><td>AA+-AAA 中短票3Y</td><td>...</td><td>&lt;30BP</td><td>&gt;60BP</td><td>...</td></tr>
        <tr><td>二级资本债-普通债3Y</td><td>...</td><td>&lt;20BP</td><td>&gt;40BP</td><td>...</td></tr>
        <tr><td>城投-产业3Y AA+</td><td>...</td><td>&lt;20BP</td><td>&gt;50BP</td><td>...</td></tr>
        <tr><td>中短票-国开3Y AAA</td><td>...</td><td>...</td><td>...</td><td>...</td></tr>
        <tr><td>国开-国债10Y</td><td>...</td><td>&lt;10BP</td><td>&gt;20BP</td><td>...</td></tr>
      </tbody>
    </table>

    <div class="section-divider"></div>

    <!-- 七、策略建议 -->
    <h2>策略建议</h2>
    <p><strong>久期：</strong>...</p>
    <p><strong>评级：</strong>...</p>
    <p><strong>品种：</strong>...</p>
    <p><strong>曲线：</strong>...</p>
    <p><strong>杠杆：</strong>...</p>
    <p><strong>对冲：</strong>...</p>
  </div>
  <div class="footer">
    <p>内容由 AI 生成，仅供专业研究参考，不构成任何投资建议。数据来源于 Choice 数据中心等公开渠道。</p>
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

## 4. 表格样式说明

- 利差历史分位极低（<20%）用 `.low` 类（青绿色）
- 利差历史分位极高（>80%）用 `.high` 类（橙色）
- 近1月/近3月变化上行（>0）用 `.up` 类（红色）
- 近1月/近3月变化下行（<0）用 `.down` 类（绿色）
- 数据缺失时单元格标「-」，不编造

## 5. 图表规格（ECharts）

- 容器 `<div id="chartN" class="chart-container">`；每个图表 IIFE 独立包裹，禁止变量共享
- 引入 ECharts CDN：`https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js`
- 系列样式：`symbol:'emptyCircle'`、`symbolSize:6`、`lineStyle.width:2`
- 坐标轴网格：`grid:{left:8,right:16,top:48,bottom:48,containLabel:true}`
- 提示框：`tooltip:{trigger:'axis',confine:true}`
- 柱状图：`barMaxWidth:24`
- Choice 色板：E001-E004（`#FF9044 / #4392F2 / #24C0C0 / #FFB70B`）
- 全文图表 ≤ 5 个；顺序先文后图

图表演进建议：

1. **品种利差对比图**：柱状图/条形图，横轴品种，纵轴利差 bp，标注历史分位
2. **期限利差走势图**：折线图，多期限利差近1年走势
3. **评级利差走势图**：折线图，多评级组合近1年走势
4. **利差矩阵热力图**：heatmap，品种 × 期限 利差颜色映射
5. **收益率曲线形态图**：折线图，对比不同品种/评级曲线

## 6. 历史分位展示规范

- `历史分位` 以百分比展示（如 12%），与判断档位对应：<10% 极窄 / 10-30% 偏窄 / 30-70% 中性 / 70-90% 偏阔 / >90% 极阔
- 历史分位窗口在头部 meta 标注（默认为近 1 年，若使用接口自带更长窗口则以接口为准）

## 7. 重点与措辞

- 核心指标数值和重要判断用 `<strong>` 加粗，同一自然段不超过 3 处
- 措辞专业严谨、中性化；使用「可能」「需关注」「若……则」「复盘显示」「或」等概率化表达
- 报告中**严禁暴露底层接口字段名**（如 REPORT_FIELD 中的英文名、报表名 RPT_ 前缀等一律不写）
- 不写「暂无数据」；数据不足以支撑判断时明确说明「依据不足」