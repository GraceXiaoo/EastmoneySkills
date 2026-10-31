# HTML 渲染规范（按需加载）

> 本文件在渲染 HTML 时加载，包含：自包含 HTML 骨架、CSS 变量、ECharts 渲染规范、表格模板、格式硬约束。
> 交付物为**单个自包含 HTML 文件**（内联 CSS/JS，图表经 ECharts CDN 引入），可在浏览器直接打开。

## 一、HTML 骨架

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
:root{
  --c1:#FF9044; --c2:#4392F2; --c3:#24C0C0; --c4:#FFB70B;
  --up:#E5342A; --down:#1BA866;
  --ink:#1F2329; --sub:#646A73; --line:#E7E9EC; --bg:#F5F6F8; --card:#FFFFFF;
}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Microsoft YaHei","PingFang SC",-apple-system,sans-serif;font-size:13px;line-height:1.7;}
.page{max-width:1080px;margin:0 auto;padding:24px 20px 48px;}
.hd{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;
  border-bottom:2px solid var(--c2);padding-bottom:12px;margin-bottom:16px;flex-wrap:wrap;}
.hd h1{margin:0;font-size:22px;font-weight:700;letter-spacing:.5px;}
.hd .meta{color:var(--sub);font-size:12px;text-align:right;line-height:1.6;}
.notice{margin:0 0 16px;padding:8px 12px;background:#FFF7E8;border:1px solid #FFE1B0;
  border-radius:6px;color:#8A6100;font-size:12px;}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:16px 18px;margin-bottom:16px;box-shadow:0 1px 3px rgba(20,30,50,.04);}
.card h2{margin:0 0 12px;font-size:15px;font-weight:700;color:var(--ink);
  border-left:3px solid var(--c1);padding-left:9px;}
.card h2 .idx{color:var(--sub);font-weight:400;margin-right:6px;}
.summary ol{margin:0;padding-left:20px;}
.summary li{margin-bottom:6px;}
p{margin:8px 0;}
strong{color:var(--ink);font-weight:700;}
.up{color:var(--up);} .down{color:var(--down);}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px;}
th,td{border:1px solid var(--line);padding:7px 10px;text-align:right;}
th{background:#F7F8FA;color:var(--sub);font-weight:600;text-align:center;}
td:first-child,th:first-child{text-align:left;}
tbody tr:nth-child(even){background:#FBFCFD;}
.chart{width:100%;height:320px;margin-top:6px;}
.chart.tall{height:380px;}
.foot{color:var(--sub);font-size:11.5px;line-height:1.7;margin-top:8px;}
.src{color:var(--sub);font-size:11px;margin-top:6px;}
.risk,.refs{margin:0;padding-left:20px;font-size:12.5px;line-height:1.8;}
.risk li,.refs li{margin-bottom:4px;}
.refs li{color:var(--sub);font-size:11.5px;}
sup{font-size:10px;color:var(--c2);}
</style>
</head>
<body>
<div class="page">
  <div class="hd">
    <h1>__TITLE__</h1>
    <div class="meta">生成时间：__GENERATED_AT__<br>数据日期：__DATA_DATE__</div>
  </div>
  <p class="notice">内容由 AI 生成，仅供专业研究参考，不构成任何投资建议。</p>

  <div class="card summary">
    <h2><span class="idx">摘要</span>结论摘要</h2>
    <ol>__ABSTRACT_LIST__</ol>
  </div>

  <div class="card">
    <h2><span class="idx">01</span>合约概况</h2>
    __OVERVIEW_TABLE__
  </div>

  <div class="card">
    <h2><span class="idx">02</span>__SECTION2_TITLE__</h2>
    <div id="chartPrice" class="chart"></div>
    <div class="src">数据来源：Choice数据</div>
    __SECTION2_TEXT__
  </div>

  <!-- 依此重复：期限结构 / 基差现货 / 库存仓单 / 会员持仓 等小节；每张图表下方均须紧跟 <div class="src">数据来源：Choice数据</div> -->

  <div class="card">
    <h2><span class="idx">06</span>__SECTION_POS_TITLE__</h2>
    <div id="chartPos" class="chart"></div>
    <div class="src">数据来源：Choice数据</div>
    __SECTION_POS_TEXT__
  </div>

  <div class="card">
    <h2><span class="idx">07</span>__SECTION_FUND_TITLE__</h2>
    <!-- 供需基本面：有数据则放置图表或表格，无则省略整卡但不写缺口说明 -->
    __SECTION_FUND_TABLE__
    __SECTION_FUND_TEXT__
  </div>

  <div class="card">
    <h2><span class="idx">08</span>__SECTION_MACRO_TITLE__</h2>
    <!-- 宏观与资金：可与外盘联动合并为一卡 -->
    __SECTION_MACRO_TEXT__
  </div>

  <div class="card">
    <h2><span class="idx">09</span>__SECTION_TECH_TITLE__</h2>
    <div id="chartTech" class="chart"></div>
    <div class="src">数据来源：Choice数据</div>
    __SECTION_TECH_TABLE__
    __SECTION_TECH_TEXT__
  </div>

  <div class="card">
    <h2><span class="idx">10</span>__SECTION_LOGICO_TITLE__</h2>
    <!-- 品种逻辑、走势判断与情景推演：只做条件化情形推演，不含操作指令 -->
    __SECTION_LOGICO_TEXT__
    __SCENARIO_TABLE__
  </div>

  <div class="card">
    <h2><span class="idx">11</span>风险提示</h2>
    <ol class="risk">
      __RISK_LIST__
    </ol>
  </div>

  <div class="card">
    <h2><span class="idx">12</span>跟踪清单</h2>
    __WATCHLIST_TABLE__
  </div>

  <div class="card">
    <h2><span class="idx">13</span>参考资料</h2>
    <ol class="refs">
      __REFERENCE_LIST__
    </ol>
  </div>

  <p class="foot">免责声明：本报告内容由 AI 生成，数据来源为 Choice数据，仅供专业研究参考，不代表任何机构立场，不构成投资建议。市场有风险，决策需谨慎。</p>
</div>

<script>
(function(){
  var el = document.getElementById('chartPrice');
  if(el && window.echarts){
    var chart = echarts.init(el);
    chart.setOption(__CHART_PRICE_OPTION__);
  }
})();
/* 其余图表均用 IIFE 包裹，避免变量冲突 */
window.addEventListener('resize', function(){
  document.querySelectorAll('.chart').forEach(function(el){
    var inst = echarts.getInstanceByDom(el); if(inst){ inst.resize(); }
  });
});
</script>
</body>
</html>
```

> 多个图表必须**各自用 IIFE 包裹**：`(function(){ var chart = echarts.init(document.getElementById('chartN')); chart.setOption({...}); })();`，避免同名变量互相覆盖。

## 二、ECharts 渲染规范

- 版本：`echarts@5.5.0`（CDN）。
- Choice 色板：E001 `#FF9044`、E002 `#4392F2`、E003 `#24C0C0`、E004 `#FFB70B`。
- **红涨绿跌**：上涨/多头用红 `#E5342A`，下跌/空头用绿 `#1BA866`（柱状、K 线、涨跌着色一致）。
- 线条：`symbol:'emptyCircle'`、`symbolSize:6`、`lineStyle:{width:2}`。
- 提示：`tooltip:{trigger:'axis',confine:true,axisPointer:{type:'cross'}}`。
- 柱状：`barMaxWidth:24`。
- 双轴：明确指定 `yAxisIndex`；成交量/持仓量惯用右轴。
- 文本：`textStyle:{fontFamily:'Microsoft YaHei',fontSize:12}`。
- 每类图表最多出现 1 次；全文图表建议 ≤ 6 个；某图核心数据缺失则**不画该图**。

### 布局与防重叠（强制）

坐标轴、图例、轴名称是最易重叠的三处，**不得依赖 ECharts 默认值**，统一按下列规则设置：

1. **图例固定顶部居中且自适应**：`legend:{top:0,left:'center',type:'scroll',itemGap:14,itemWidth:16,itemHeight:8,textStyle:{fontSize:11,color:'#646A73'}}`；图例项多时用 `type:'scroll'` 分页，禁止换行后压住坐标轴。
2. **网格为图例让出空间**：`grid.top` 必须 ≥ 图例高度——单行取 `44`，可能两行取 `56`；`grid` 统一 `containLabel:true`，**严禁 `grid.top` 小于 `40`**。
3. **双轴各自留白**：有右轴时 `grid.right:56`、无右轴时 `20`；`grid.left` 不小于 `8`。轴刻度用简短格式（如 `万`/`亿`），避免过长顶到画布边缘。
4. **轴名称不与图例打架**：优先不写 `yAxis.name`，把单位放进图例文字或图下「数据来源」行；确需轴名时设 `nameGap:32`，并把 `grid.top` 抬到 `56`。
5. **X 轴标签防重叠**：`xAxis.axisLabel:{hideOverlap:true,margin:8,fontSize:11}`；时间/类别过密时自动隐藏，不要旋转堆叠。
6. **横向柱（会员多空）**：`grid.left:96`，或配合 `yAxis.axisLabel:{width:88,overflow:'truncate'}`，避免会员名与刻度线重叠；行数多时用 `.chart.tall`。
7. **图表高度**：普通图 `320px`；含图例+双轴或图例可能两行的用 `.chart.tall`（`380px`）；横向柱行数 > 12 用 `380px`。
8. **硬性禁止**：图例与网格重叠、坐标轴刻度溢出画布、轴名称压住刻度、图例遮挡数据曲线。

**基础母版 option（各图在此之上按需覆盖）**：

```js
var BASE_OPTION = {
  textStyle:{fontFamily:'Microsoft YaHei',fontSize:12,color:'#1F2329'},
  color:['#FF9044','#4392F2','#24C0C0','#FFB70B'],
  tooltip:{trigger:'axis',confine:true,axisPointer:{type:'cross'}},
  legend:{top:0,left:'center',type:'scroll',itemGap:14,itemWidth:16,itemHeight:8,
    textStyle:{fontSize:11,color:'#646A73'}},
  grid:{left:8,right:20,top:44,bottom:8,containLabel:true},
  xAxis:{type:'category',boundaryGap:false,
    axisLabel:{fontSize:11,color:'#646A73',hideOverlap:true,margin:8},
    axisLine:{lineStyle:{color:'#E7E9EC'}},axisTick:{show:false}},
  yAxis:{type:'value',scale:true,
    axisLabel:{fontSize:11,color:'#646A73'},
    splitLine:{lineStyle:{color:'#F0F2F5'}},axisLine:{show:false},axisTick:{show:false}}
};
```

> 有双轴时：`grid.right:56`，并给第二根轴设 `yAxisIndex:1`、`splitLine:{show:false}`。
> 横轴为日期/月份时，务必保证 `xAxis.data` 与各 `series.data.length` 完全一致，否则会出现「错位/重叠」的错觉。

### 常用图表范式

1. **价格与量仓（双/三轴）**：`xAxis` 为日期，`yAxis[0]` 价格（`scale:true`），`yAxis[1]` 成交量/持仓量（右轴）；此时 `grid.right:56`，第二根轴设 `yAxisIndex:1` 且 `splitLine:{show:false}`，轴单位放进图例文字。
2. **期限结构曲线**：`xAxis` 为合约月份（如 `2611,2612,2701...`），`yAxis` 为价格（`scale:true`），`type:'line'` + `symbol:'emptyCircle'`；可叠加昨日曲线对比。
3. **基差走势 / 基差率**：折线；基差率可加参考线 `markLine`（0 轴）。
4. **仓单量**：柱状（增减）或折线（存量）。
5. **会员多空**：横向柱状（`yAxis` 为会员名，`type:'category'`），多头红、空头绿；`grid.left:96`，`yAxis.axisLabel:{width:88,overflow:'truncate'}`，避免会员名与刻度线重叠。
6. **技术面（价格+均线+MACD）**：主图折线叠加 MA5/MA10/MA20/MA60（不同色），MACD 的 DIF/DEA 与柱状**另起一张图**（避免同坐标系拥挤与图例过多）；DIF/DEA 用线、柱状用红绿（正红负绿）。多均线时图例可能两行，`grid.top:56` 并用 `.chart.tall`。
7. **宏观/产业/外盘**：单指标折线或柱状（`xAxis` 为时间/频率），单位与频率放进图例或数据来源行；多个相关指标可做双轴，但不得混用不同量纲而不标注。

## 三、表格模板

**合约概况表**：

```html
<table>
  <thead><tr>
    <th>期货代码</th><th>合约简称</th><th>所属品种</th><th>最新价</th><th>结算价</th>
    <th>涨跌</th><th>涨跌幅</th><th>成交量(手)</th><th>持仓量(手)</th><th>成交额(亿元)</th><th>合约乘数</th>
  </tr></thead>
  <tbody><tr>
    <td>__CODE__</td><td>__NAME__</td><td>__VARIETY__</td><td>__LAST__</td><td>__SETTLE__</td>
    <td class="up">__CHG__</td><td class="up">__CHGPCT__</td><td>__VOL__</td><td>__OI__</td><td>__AMT__</td><td>__MULT__</td>
  </tr></tbody>
</table>
```

**期限结构表**：`| 合约 | 到期月份 | 最新价 | 结算价 | 较近月价差 | 持仓量 |`

**会员持仓表**：`| 会员 | 多头持仓 | 空头持仓 | 净持仓 | 多头增减 | 空头增减 |`（按净持仓绝对值降序，取前 10~20）

**技术指标表**：`| 指标 | 数值 | 判读 |`（行：最新价、MA5、MA10、MA20、MA60、DIF、DEA、MACD柱、支撑位、压力位；判读为中性描述）

**情景推演表**：`| 情形 | 触发条件 | 可能演化 |`（2-3 行；只描述结构性演化，不含操作指令）

**跟踪清单表**：`| 指标 | 当前值 | 阈值/信号 | 关注方向 |`（3-6 行）

**风险提示**：有序列表（`<ol class="risk">`），3-6 条，编号形如 `1. 2. 3.`，每条一句话；正文可用 `[n]` 与风险条目呼应时须保持一致。

**参考资料**：有序列表（`<ol class="refs">`），每条格式为 `来源类型 · 材料日期 · 标题/摘要要点`；正文引用处以 `<sup>[n]</sup>` 标注，编号与列表一一对应。

> 数值缺失的单元格留空或整行省略，不写「-」「暂无」「N/A」。

## 四、格式硬约束

1. **标题**：`{合约简称}（{期货代码}）期货一页纸`，不得改为「分析报告」等其它措辞。
2. **生成时间**：精确到秒，`YYYY-MM-DD HH:mm:ss`；同时展示数据日期。
3. **自包含**：单个 HTML 文件，除 ECharts CDN 外无外部依赖；不引用本地图片、不引用内网资源。
4. **数据来源标注（统一）**：全文数据来源表述统一为 **「数据来源：Choice数据」**（含图表与页脚），不得写成「Choice 数据中心」等其它形式。**每一张图表下方都必须紧跟一行 `<div class="src">数据来源：Choice数据</div>`**（表格如需可合并数据日期/单位，但来源须为「Choice数据」）；页脚免责声明中的来源同样统一为「Choice数据」。
5. **正文字数**：不含图表与图注，正文建议 900-1800 字。
6. **不含禁用表述**：无「买入/卖出/持有/必涨/必跌/稳赚」等操作指令或绝对化表达；**走势判断与情景推演段不得含建仓/目标价/止损/仓位/对冲比例等交易指令**。
7. **不暴露字段名**：正文与图表标签均用业务语言，不出现英文接口字段名。
8. **不暴露内部地址**：HTML 内不得出现任何研报下载地址、内网地址或密钥。
9. **无产物路径**：HTML 文件本身不含任何写死的输出路径信息。
10. **图表健壮性与防重叠**：`echarts` 未加载时不报错阻塞（IIFE 内判空）；多图作用域隔离；`resize` 统一重绘；**坐标轴、图例、轴名称不得重叠**，须按「布局与防重叠」规则设置 legend/grid.top/grid.right/axisLabel。
11. **必备板块**：须含结论摘要、合约概况、**风险提示（编号，≥3 条）**、**跟踪清单**、**参考资料（编号，与正文 `[n]` 对应）**；技术面、供需基本面、宏观与资金、外盘联动按数据可得性增删。
12. **技术口径**：技术面段须注明均线与 MACD 的计算口径，数值须由行情序列如实计算；序列不足则省略对应指标而不臆造。
13. **主力与交割**：若入参为品种主力合约，须标注「主力合约」并给出交割月提示（仅提示，不含操作指令）。

## 五、交付

- 将生成的 HTML 写入**当前工作目录**（文件名建议：`{合约简称}（{期货代码}）期货一页纸_{YYYYMMDD}.html`），不要写入任何固定绝对路径。
- 交付后在对话中给出简短文字摘要（合约 + 核心变化点 + 结构判断），不复述报告全文。