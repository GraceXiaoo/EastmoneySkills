# HTML 输出规范（七段式一页纸）

本文档定义宏观资金面一页纸 HTML 报告的版式与图表规格。版式基准随附 `assets/资金面一页纸_示例_20260928.html`（数据为实测示例，结构、CSS、图表规格以此为基准）。

## 1. 整体结构

单文件自包含 HTML（内联 CSS/JS，无外部依赖）。布局顺序：

```
<head>
  <title>宏观资金面一页纸(xxxx年xx月xx日)</title>
  <style>…CSS 变量与样式…</style>
</head>
<body>
  <div class="page"><div class="paper">
    <div class="head">
      <h1>宏观资金面一页纸</h1>
      <div class="meta">报告日期：<date> | 数据截至：<date>（Choice 数据中心）</div>
    </div>

    <div class="summary">
      <div class="t">结论摘要</div>
      <ul / p>3-5 条结论摘要：资金面松紧、核心矛盾、央行态度、未来 1-5 日判断</div>
    </div>
    （注：结论摘要段只呈现事实性结论，不添加"中性/偏紧/偏松"等评分徽章；评分状态仅出现在下方"资金面温度计"分项条中）

    <h2>资金面温度计</h2>
    <div class="gauge">分项状态条（OMO/货币市场/财政/时点/一级）+ 综合状态标签</div>

    <h2>分维度分析</h2>
    <table>| 维度 | 现状 | 驱动 | 关键指标 | 判断 | 风险 |</table>
    （正文段落穿插图表：先文后图）

    <h2>未来推演</h2>
    <p>1-5 日 / 1-2 周 / 节后或税期后</p>

    <h2>跟踪清单</h2>
    <table>| 指标 | 当前值 | 偏松阈值 | 偏紧阈值 | 信号 |</table>

    <h2>策略建议</h2>
    <p>杠杆、久期、备付、融入融出、存单、交易所</p>

    <div class="disclaimer">本报告数据来源于 Choice 数据中心，仅供参考，不构成投资建议</div>
  </div></div>
</body>
```

## 2. CSS 规格

配色变量（全报告统一蓝色系，不出现红/绿）：

```css
:root{
  --ink:#1f2430; --sub:#5b6472; --line:#e6e9ef; --bg:#f7f8fa;
  --blue:#2f6fed; --blue-soft:#9db5e0; --amber:#e8a13c; --card:#ffffff;
}
```

- 字体：`"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif`；正文 15px、行高 1.75
- 页面：`.page{max-width:860px; margin:0 auto; padding:32px 40px 40px;}`；`.paper{background:var(--card); border:1px solid var(--line); border-radius:12px; padding:36px 44px 32px; box-shadow:0 2px 12px rgba(20,30,60,.05);}`
- 标题：`.head{border-bottom:2px solid var(--ink); padding-bottom:14px;}`；h1 24px 字距 1px；meta 13px 灰色
- 结论标签：`.verdict{display:inline-block; background:var(--blue); color:#fff; font-size:13px; padding:3px 14px; border-radius:999px;}`
- 摘要框：`.summary{background:#f0f4ff; border:1px solid #dbe5ff; border-radius:10px; padding:16px 20px;}`
- 小标题：`h2{font-size:17px; padding-left:10px; border-left:4px solid var(--blue);}`
- 正文段落：`p.body-text{text-indent:2em; color:#333b4d; margin-bottom:8px;}`
- 图表容器：`.fig{background:#fbfcfe; border:1px solid var(--line); border-radius:10px; padding:18px 14px 10px;}`，图注 `.fig .ft{text-align:center; color:var(--sub); font-size:12px; border-top:1px dashed var(--line); margin-top:6px; padding-top:8px;}`
- 表格：`.tbl{width:100%; border-collapse:collapse; font-size:13px;}` th 背景 `#f0f4ff`；td/th `border:1px solid var(--line); padding:8px 10px;`
- 温度计分项条：用色块/进度条表现 -2~+2（蓝色系深浅表达松紧），配文字标签
- 免责声明：`.disclaimer{margin-top:28px; padding-top:14px; border-top:1px solid var(--line); color:#98a0ad; font-size:12px;}`
- 图表类：`.bar-label{font-size:11px; fill:#5b6472;}` `.axis-text{font-size:11px; fill:#8a93a3;}` `.zero-line{stroke:#c4cad6;}` `.grid-line{stroke:#eef0f4;}` `.policy-line{stroke:var(--amber); stroke-dasharray:6 4;}` `.dot{fill:#2f6fed;}`

## 3. 图表规格

图表穿插在对应正文段落之后（先文后图），图注统一格式：`图：<图表名>（<单位>，<起> 至 <止>）— 数据来源：Choice`。

### 3.1 央行日度净投放/净回笼柱状图（有数据则必画）

- 数据：`daily` 的近 15 个自然日净投放/净回笼
- viewBox：宽度 = `柱数×72 + 96`（柱宽 42、柱间距 72、首柱 x=88、左边距 70）；高度 = `顶部留白 40 + (最大正值+最大负值)×比例 + 底部留白约 40`
- 0 线固定 `y=220`，比例 `30px/千元`；净投放柱向上（柱顶 `y=220-柱高`，品牌蓝 `#2f6fed`），净回笼柱向下（浅蓝 `#9db5e0`）
- 数值标签：柱顶上方 6px（正值）/ 柱底下方 6px（负值）；日期标签在绘图区底部
- 网格线取 ±2000、±4000 等整千刻度；Y 轴 0 刻度在图内

### 3.2 DR001/DR007 走势与 R007-DR007 利差组合图（有条件，有历史序列则画）

- 数据：`rates` 的 DR007 与 DR001 近 20-30 交易日 + 7 天逆回购政策利率参考线 + `R007-DR007` 利差（bp，`利率日报_资金面_明细` 直接提供）
- 布局：上下双区——上区画 DR001/DR007 折线 + 政策利率虚线（`--amber:#e8a13c` 虚线，主蓝 `--blue:#2f6fed` 画 DR007、浅蓝 `#7aa5f0` 画 DR001，末点加 `.dot`），下区画 R007-DR007 利差柱（浅蓝 `#9db5e0`），中间以 0 线分隔；顶部放图例
- 上区纵轴为利率（%），下区纵轴为利差（bp），横轴共享同一组日期刻度；网格线适当，图注含单位与起止日期
- 无历史序列时不绘制（不编造数据）；DR001 或利差序列缺失时可退化为仅 DR007 + 政策利率单线图

### 3.3 可选图表

- 同业存单/GC007 短周期趋势线（若利率明细提供序列）
- 资金日历抽水/补水条形图（若资金日历报表可取）

## 4. 写作约束

- 结论先行：摘要段先给一句话整体判定 + 各维度要点（3-5 条），只陈述事实性结论与对未来的判断，不放"中性/偏紧"评分徽章
- 小节标题提炼维度要点，不与"央行操作""银行间流动性"等原维度名完全重复
- 数据来源标注：头部 meta（数据截至行注明"Choice 数据中心"；若使用外部兜底数据则扩展为"Choice 数据中心与公开渠道"）、图表图注（"数据来源：Choice"；外部数据则写具体来源）、页脚免责声明；正文对引用的外部数据可加简洁来源括注
- 外部兜底数据：MQL 取不到时经 `WebSearch`/`WebFetch`/已授权 API 引用权威外部数据，须标注来源名称与日期，禁止使用未经核实的来源
- 语言：中文；金额亿元、利率 bp/% 并注明
- 全文约 1200-1500 字（不含图表与图注）
- 禁止：展示内部评分值；硬编码政策利率；把单日波动直接定性为趋势；引用未经核实的未知来源数据

## 5. 示例参考

以 `assets/资金面一页纸_示例_20260928.html` 为版式基准：配色、温度计布局、表格样式、SVG 图表规格均与该文件保持一致，用当日实际数据替换示例内容。