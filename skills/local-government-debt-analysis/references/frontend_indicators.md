# 化债跟踪前端指标与接口字段映射

本文件对应「地方化债跟踪」前端页面实际展示的字段（来源：前端展示页面效果及字段样例），
是 2.0 版报告的**取数清单与解读清单**。凡本表列出的字段，为报告主线指标（必取必读）；
未列出的字段属背景或无关指标（见 SKILL.md「主题聚焦原则」）。

## 一、六大前端模块字段清单

### 1. 最新化债情况

| 前端字段 | 接口英文名 | 单位 | 所属报表 | 化债解读 |
|---|---|---|---|---|
| 省及直辖市 | `AREA` / `AREA_CODE` | — | `RPT_DEBT_AREAHOMEPAGE_LEFT` | 地区主键 |
| 地方债投资指数 | `INVEST_INDEX` | — | 同上 | 专项债投向景气/化债支持力度参考 |
| 最新隐债规模 | `HIDDENDEBT_BALANCE` | 亿 | 同上 | 隐性债务体量（化债主战场） |
| 城投及地方国企债务 | `IMPLICIT_DEBT` | 亿 | 同上 | 经营性债务体量 |
| 债务变动百分比(城投及地方国企) | `IMPLICIT_DEBT_CHANGE` | % | 同上 | 城投债务同比增减，识别“边化边增” |

取数：`reportName=RPT_DEBT_AREAHOMEPAGE_LEFT&columns=AREA_CODE,AREA,AREA_TYPE,INVEST_INDEX,HIDDENDEBT_BALANCE,IMPLICIT_DEBT,IMPLICIT_DEBT_CHANGE&filter=(AREA_TYPE in (1,3))`
（也可 `columns=ALL` 与其它模块一次取回）。

### 2. 本息覆盖率

| 前端字段 | 接口英文名 | 单位 | 所属报表 | 化债解读 |
|---|---|---|---|---|
| 省及直辖市 | `AREA` / `AREA_CODE` | — | `RPT_DEBT_AREAHOMEPAGE_LEFT` | 地区主键 |
| 收支缺口 | `REEX_GAP` | 亿 | 同上 | 财政“造血”能力（负值且绝对值大＝依赖外部输血） |
| 可供还债的地方财政资金 | `LOCAL_FUND` | 亿 | 同上 | 内生偿债资金池 |
| 专项债券还本付息支出 | `BOND_BALANCE` | 亿 | 同上 | 专项债刚性还本付息负担 |
| 覆盖率 | `COVERAGE` | % | 同上 | 供还资金 ÷ 专项债本息，<30% 为“靠外部输血”梯队 |

取数：`columns=AREA_CODE,AREA,REEX_GAP,LOCAL_FUND,BOND_BALANCE,COVERAGE,HIDDENDEBT_BALANCE&filter=(AREA_TYPE=1)`。

### 3. 专项债余额

| 前端字段 | 接口英文名 | 单位 | 所属报表 | 化债解读 |
|---|---|---|---|---|
| 省及直辖市 | `AREA` / `AREA_CODE` | — | `RPT_DEBT_AREAHOMEPAGE_LEFT` | 地区主键 |
| GDP | `GDP` | 亿 | 同上 | 债务率分母 |
| 专项债务余额的相对规模 | `RELATIVE_SCALE` | 倍(余额/GDP) | 同上 | 显性债务压力；>1 即余额超 GDP |

取数：`columns=AREA_CODE,AREA,GDP,BALANCE,RELATIVE_SCALE&filter=(AREA_TYPE=1)`
（`BALANCE`=专项债务余额，配合 `RELATIVE_SCALE` 展示；GDP 与结论 ② 同源，全文只用一个口径）。

### 4. 未来偿债

| 前端字段 | 接口英文名 | 单位 | 所属报表 | 化债解读 |
|---|---|---|---|---|
| 省及直辖市 | `AREA` / `AREA_CODE` | — | `RPT_DEBT_AREAHOMEPAGE_LEFT` | 地区主键 |
| 地方债偿还 | `REPAY_AMT_DFZ` | 亿 | 同上 | 政府债券到期偿还压力（偏财政内生） |
| 城投债偿还 | `REPAY_AMT_CTZ` | 亿 | 同上 | 城投公开债到期压力（偏市场/再融资敏感） |

取数：`columns=AREA_CODE,AREA,REPAY_AMT_DFZ,REPAY_AMT_CTZ&filter=(AREA_TYPE=1)`。

### 5. 商品房销售

| 前端字段 | 接口英文名 | 单位 | 所属报表 | 化债解读 |
|---|---|---|---|---|
| 省及直辖市 | `AREA` / `AREA_CODE` | — | `RPT_DEBT_AREAHOMEPAGE_LEFT` | 地区主键 |
| 商品房销售价格环比 | `PRICE_COMHOUSE_MOM` | % | 同上 | 房价动能 → 土地出让/政府性基金收入前瞻 |
| 商品房销售价格 | `PRICE_COMHOUSE` | 万元/平方米 | 同上 | 房价水平 |

取数：`columns=AREA,AREA_CODE,PRICE_COMHOUSE,PRICE_COMHOUSE_MOM,STR_REPORTMONTH&filter=(AREA_TYPE=1)`。
若返回为空（前端页面对部分省份该模块为空/0），该模块不渲染图表，正文以“数据披露滞后”说明。

### 6. 政府化债动态

| 前端字段 | 接口英文名 | 所属报表 | 化债解读 |
|---|---|---|---|
| 公告时间 | `NOTICE_DATE` / `STR_NOTICE_DATE` | `RPT_CUSTOM_DEBTREMOVE_GOV_PROCESS` | 动态时点 |
| 省 | `PROCINCE` / `PROVINCE_CODE` | 同上 | 地区筛选 |
| 市 | `CITY` | 同上 | 层级 |
| 区县 | `DISTRICT` | 同上 | 层级 |
| 化债进度 | `DEFUSE_DEBT_PROCESS` | 同上 | 文本：置换额、进度%、债务率、平台压降、利率降幅 |
| 化债展望 | `DEFUSE_DEBT_OUTLOOK` | 同上 | 文本：官方情绪信号 |
| 披露网站 | `NOTICE_URL` | 同上 | 公告链接 |
| 来源 | `SOURCE` | 同上 | 发文机构 |

取数（最新一批）：`filter=(IS_NEW="1")`；某地区全部动态：`filter=(AREA_CODE in ("..."))(IS_NEW="0")&sortColumns=NOTICE_DATE&sortTypes=-1`。

## 二、前端模块 → 接口字段映射速查（反向）

| 接口英文名 | 中文（前端口径） |
|---|---|
| `AREA` / `AREA_CODE` | 省及直辖市 |
| `GDP` | GDP(亿) |
| `BALANCE` | 专项债务余额(亿) |
| `RELATIVE_SCALE` | 专项债务余额的相对规模 |
| `REEX_GAP` | 收支缺口(亿) |
| `LOCAL_FUND` | 可供还债的地方财政资金(亿) |
| `BOND_BALANCE` | 专项债券还本付息支出(亿) |
| `COVERAGE` | 覆盖率(%) |
| `PRICE_COMHOUSE` | 商品房销售价格(万元/平方米) |
| `PRICE_COMHOUSE_MOM` | 商品房销售价格环比(%) |
| `REPAY_AMT_DFZ` | 地方债偿还(亿) |
| `REPAY_AMT_CTZ` | 城投债偿还(亿) |
| `INVEST_INDEX` | 地方债投资指数 |
| `HIDDENDEBT_BALANCE` | 最新隐债规模(亿) |
| `IMPLICIT_DEBT` | 城投及地方国企债务(亿) |
| `IMPLICIT_DEBT_CHANGE` | 债务变动百分比(城投及地方国企)(%) |
| `DEFUSE_DEBT_PROCESS` | 化债进度（文本） |
| `DEFUSE_DEBT_OUTLOOK` | 化债展望（文本） |

## 三、政府债发行节奏与计划执行（维度二）数据源

维度二回答“新增额度用得快不快、供给压力大不大”，取数来自地方债计划发行限额与一级市场。

| 数据项 | 接口/报表英文名 | 单位 | 说明 |
|---|---|---|---|
| 地方债发行计划限额（省级×月度） | `RPT_CUSTOM_BOND_PLAN_AREAISSUEQUTA` | 亿 | 含新增一般债/再融资一般债/新增专项债/再融资专项债四类券种的“计划值/实际值”，及全年新增限额 |
| 地方债一级市场（招标/发行） | 一级市场模块 | 亿 | 用于佐证发行温度与节奏 |

**预处理要点**：
- 限额表为**两级表头**，需按“券种 × 计划值/实际值”展开为长表；`-` 按空值处理。
- 全年新增限额含**千分位逗号**，须清洗后再参与计算。
- Sheet 名含季度标识，需**动态匹配最新季度**。

**派生指标（测算）**：
- 发行计划执行偏差 = 累计实际发行 ÷ 同期计划发行 − 1。
- 全年额度累计落地进度 = 累计实际发行 ÷ 全年新增限额 × 100%。

> **正文表述约束**：上述"计划执行偏差""全年额度累计落地进度"写入报告正文、图表标签与脚注时，
> 一律使用**中文口径名称**（"累计实际发行""同期计划发行""全年新增限额"），
> **严禁出现报表英文名或字段英文名**。

> 本维度仅输出“全年额度累计落地进度”折线图 + “省份×券种季度计划发行额”热力图与正文，**不出各省分券种季度计划发行额明细表**。

## 四、背景/无关指标处置

- **仅作背景**：三次产业占比、固定资产投资、房地产开发投资、常住人口、金融机构存贷款、财政自给率等——
  仅在解释债务分母或偿债能力时一句话带过，不单独成段。
- **原则上不写**：地方债/城投债二级市场利差、成交统计、城投平台搜索、行政地图、就业分布、二手房均价、
  产值按行业等——除非用户明确要求，否则取数层直接跳过、报告层不出现。

> 字段语义以 `interface_catalog.md` 为准；本表仅做“前端展示口径 ↔ 接口字段”的对应，不新增字段。