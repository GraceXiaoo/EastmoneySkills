# HTML 报告模板规范（债券一页纸 new）

本文件定义「债券一页纸 new」skill 的 **HTML 报告** 完整骨架、CSS、图表脚本与离线 ECharts 库复用方法。生成 HTML 报告时以此为准，保证与历史报告（如 `241116.SH_GK赣投01_F9AI解读报告.html`）风格一致。

## 1. 文件命名与存放

- 保存路径：`./{债券代码}_{债券简称}_F9AI解读报告.html`（输出到 skill 当前运行目录）
- 命名示例：`241116.SH_GK赣投01_F9AI解读报告.html`、`2305945.IB_23重庆债36_F9AI解读报告.html`
- 生成后必须用结果呈现工具（present_files）打开预览，供用户直接查看。

## 2. 离线 ECharts 库复用方法（重要）

历史 HTML 报告已内嵌完整 ECharts 压缩库（Apache-2.0 许可，约 1MB），**优先复用**，避免联网加载或重复下载：

方法（Python 提取示例）：

```python
import re
from pathlib import Path
# 旧报告路径按实际存放位置填写（示例），优先复用其内嵌的离线 echarts 库
old = Path("241116.SH_GK赣投01_F9AI解读报告.html")
s = open(old, encoding='utf-8', errors='replace').read()
m = re.search(r'<script[^>]*>(.*?)</script>', s, re.S)
echarts_js = m.group(1)  # 即内嵌的 echarts 库代码
# 将其写入新 HTML 的 <script>...</script>
```

若无现成报告可复用，用 CDN 引入：

```html
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
```

## 3. 完整页面骨架（可直接套用）

```html
<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{债券名称}（{债券代码}）{信用债/地方债}研究</title>
<style>
/* 见下方 CSS */
</style>
<script>
/* 内嵌离线 ECharts 库（从历史报告提取，或 CDN 引入）*/
</script>
</head>
<body>
<div class="wrap">

<div class="head">
  <span class="tag">城投债</span><span class="tag">科创债</span><span class="tag">绿色债</span><span class="tag">存续中</span>
  <h1>{债券简称}（{债券代码}）信用债研究</h1>
  <div class="time">生成时间：{YYYY年MM月DD日 HH时mm分ss秒} · 数据截至：{YYYY-MM-DD} · 数据来源：Choice 数据中心</div>
</div>

<div class="summary">
  <h2>摘要</h2>
  <p>{150-250字摘要，重点可 <b>加粗</b>}</p>
</div>

<div class="kpis">
  <div class="kpi"><div class="k">债券余额</div><div class="v">2.00 亿元</div><div class="s">{补充说明}</div></div>
  <div class="kpi"><div class="k">票面利率</div><div class="v">2.38%</div><div class="s">{补充说明}</div></div>
  <div class="kpi"><div class="k">最新估价收益率</div><div class="v">1.6451%</div><div class="s">{补充说明}</div></div>
  <div class="kpi"><div class="k">剩余期限</div><div class="v">约 2.75 年</div><div class="s">{补充说明}</div></div>
</div>

<div class="sec">
  <h2>{段落标题（二次总结）}</h2>
  <p>{正文段落}</p>
  <table>
    <tr><th>{指标}</th><th>{数值}</th></tr>
    <tr><td>...</td><td>...</td></tr>
  </table>
  <div class="chart" id="ch1"></div>
  <div class="chart-note">图1：{图表说明} · 数据来源：Choice</div>
</div>

<!-- 更多 .sec 章节 ... -->

<div class="sec">
  <h2>履约与流动性：{二次总结}</h2>
  <p>{正文，含 <b>风险关注点：</b>①... ②... }</p>
</div>

<div class="disc">
<strong>免责声明：</strong>本报告数据来源于 Choice 数据中心，仅供参考，不构成投资建议。
</div>

</div>
<script>
var ch1 = echarts.init(document.getElementById('ch1'));
ch1.setOption({ /* 图1 option */ });

var ch2 = echarts.init(document.getElementById('ch2'));
ch2.setOption({ /* 图2 option */ });

/* ... 每个图表一个 init */

window.addEventListener('resize', function(){
  ['ch1','ch2','ch3','ch4','ch5'].forEach(function(id){
    var el = document.getElementById(id);
    if (el) { var inst = echarts.getInstanceByDom(el); if (inst) inst.resize(); }
  });
});
</script>
</body></html>
```

## 4. CSS（与历史报告一致）

```css
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#f2f4f8;color:#1f2733;line-height:1.8;padding:24px}
.wrap{max-width:980px;margin:0 auto}
.head{background:linear-gradient(135deg,#10316b,#1e4f9e);color:#fff;border-radius:14px;padding:30px 34px;box-shadow:0 4px 18px rgba(16,49,107,.18)}
.head .tag{display:inline-block;background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.3);font-size:13px;padding:3px 12px;border-radius:20px;margin:0 6px 10px 0}
.head h1{font-size:26px;letter-spacing:.5px}
.head .time{opacity:.85;font-size:13px;margin-top:8px}
.summary{background:#fff;border-radius:14px;padding:22px 28px;margin-top:20px;box-shadow:0 2px 10px rgba(0,0,0,.05);border-left:5px solid #4392F2}
.summary h2{font-size:17px;color:#10316b;margin-bottom:8px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:20px}
.kpi{background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 2px 8px rgba(0,0,0,.05);border-top:3px solid #FF9044}
.kpi .k{font-size:12.5px;color:#8a93a3}
.kpi .v{font-size:21px;font-weight:700;color:#10316b;margin-top:4px}
.kpi .s{font-size:12px;color:#8a93a3;margin-top:2px}
.sec{background:#fff;border-radius:14px;padding:26px 30px;margin-top:20px;box-shadow:0 2px 10px rgba(0,0,0,.05)}
.sec h2{font-size:19px;color:#10316b;border-left:5px solid #FF9044;padding-left:12px;margin-bottom:14px}
.sec p{margin-bottom:13px;font-size:15px;text-align:justify}
.chart{width:100%;height:360px;margin:16px 0 6px}
.chart-note{font-size:12.5px;color:#97a0ae;text-align:center;margin-bottom:8px}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:14px}
th,td{border:1px solid #e6eaf0;padding:9px 12px;text-align:left}
th{background:#eef3fb;color:#10316b;font-weight:600}
tr:nth-child(even) td{background:#f8fafd}
.disc{background:#fff8f2;border:1px dashed #FFB70B;border-radius:12px;padding:16px 22px;margin-top:22px;font-size:12.5px;color:#8a6d3b}
@media(max-width:640px){.kpis{grid-template-columns:repeat(2,1fr)}.chart{height:300px}}
```

## 5. 图表规范

- 每个图表：`<div class="chart" id="ch{n}"></div>` + 图注 `<div class="chart-note">图{n}：{说明}</div>`。
- 页面底部统一 `<script>`：每个 `ch{n}` 一个 `echarts.init(document.getElementById('ch{n}'))` + `setOption`。
- 建议 3-6 张图，类型：柱状/折线/饼图（环形）/雷达/仪表盘。
- 配色：主强调红 `#E6432D`、次橙 `#F5A623`、绿 `#2E8B57`、蓝 `#4392F2`、灰 `#A0A8B8`；涨红跌绿（中国市场约定）。
- 图表标题 `title.text` 居中、字号 14、颜色 `#10316b`；数值标签自然展示。
- 数据不足的图表不输出。

## 6. 内容纪律（与 SKILL.md 一致）

- 标题：地方政府债用"地方债研究"，其余用"信用债研究"。
- 生成时间精确到秒；正文不含图表 ≥800 字。
- 段落标题二次总结，原文不照搬栏目名；加粗每段 ≤3 处。
- 声明数据来源、不加唱空/极端/买卖表述、不泄露任何 Key。
- **数据来源纪律（强制，见 SKILL.md《注意事项》）**：报告中所有数据、对应分析与文字必须来源于 Choice 数据中心并经 MQL 取数；无数据维度整体省略——不写缺口说明（"暂无数据""数据缺失"等）、不引用其他来源（含 RAG/新闻/公告数值）补齐、不输出空图表。
- **来源标注位置纪律（强制）**：**正文段落内不出现"（Choice）"等来源括注**；来源只在三处体现——头部 meta（数据截至行注明"Choice 数据中心"）、图表图注（统一标注 `数据来源：Choice`）、页脚免责声明。报告末尾**不加"来源与说明"章节**。
- **免责声明**：页脚仅保留一行——"本报告数据来源于 Choice 数据中心，仅供参考，不构成投资建议"（与 SKILL.md 模板一致）。

## 7. Markdown 降级输出

当用户明确要求 Markdown 时：直接输出 `# 标题` + 生成时间 + `数据截至：{日期} · 数据来源：Choice 数据中心` + `> 本报告数据来源于 Choice 数据中心，仅供参考，不构成投资建议。` + `## 摘要` + 各段落（含 ```js const option = {...}``` 代码块）+ `## 免责声明`（一行：本报告数据来源于 Choice 数据中心，仅供参考，不构成投资建议），结构见 SKILL.md「第五步」Markdown 部分。来源标注纪律与 HTML 一致：正文段落内不出现"（Choice）"括注，图表图注统一标"数据来源：Choice"，末尾不加"来源与说明"章节。