# 地方化债报表数据接口与字段速查（2.0）

本文件汇总「地方化债」研究报告依赖的报表数据接口。所有接口的 `reportName`、`columns`（出参字段英文名）、
`filter`（入参）示例均以官方接口说明文档为准。**字段一律使用英文名；字段语义以本文档释义为准。**

## 0. 化债前端核心字段速查（2.0 主线）

化债跟踪前端六大模块的字段，集中在 `RPT_DEBT_AREAHOMEPAGE_LEFT` 一张快照表（模块 1-5）与
`RPT_CUSTOM_DEBTREMOVE_GOV_PROCESS`（模块 6）。**建议 `columns=ALL` 一次取回。**
前端字段 ↔ 接口字段的完整映射见 `frontend_indicators.md`。

| 前端模块 | 关键接口字段 |
|---|---|
| 最新化债情况 | `INVEST_INDEX`,`HIDDENDEBT_BALANCE`,`IMPLICIT_DEBT`,`IMPLICIT_DEBT_CHANGE` |
| 本息覆盖率 | `REEX_GAP`,`LOCAL_FUND`,`BOND_BALANCE`,`COVERAGE` |
| 专项债余额 | `GDP`,`BALANCE`,`RELATIVE_SCALE` |
| 未来偿债 | `REPAY_AMT_DFZ`,`REPAY_AMT_CTZ` |
| 商品房销售 | `PRICE_COMHOUSE`,`PRICE_COMHOUSE_MOM`,`STR_REPORTMONTH` |
| 政府化债动态 | `DEFUSE_DEBT_PROCESS`,`DEFUSE_DEBT_OUTLOOK`,`NOTICE_TITLE`,`NOTICE_URL`,`SOURCE` |

## 接口分级速查（性能优化）

| 级别 | 报表 | 何时调用 |
|---|---|---|
| ✅ 核心 | `RPT_DEBT_AREAHOMEPAGE_LEFT` | 每份报告必调，`columns=ALL` 一次取回（最新化债/本息覆盖率/专项债/未来偿债/商品房 5 个模块） |
| ✅ 核心 | `RPT_BOND_REGION_ECONOMYALL` | 每份报告必调（GDP 分母、政府债务、财政背景） |
| ✅ 核心 | `RPT_CUSTOM_DEBTREMOVE_PROVINCE_DEBT` | 每份报告必调（省级化债指标与排名） |
| ✅ 核心 | `RPT_CUSTOM_DEBTREMOVE_GOV_PROCESS` | 每份报告必调（政府化债动态，`IS_NEW=1`） |
| ✅ 核心 | `RPT_DEBTREMOVE_EXITORG_LIST` | 每份报告必调（退平台名单/平台压降） |
| ⚪ 可选 | `RPT_DEBTREMOVE_REGION_ECONOMY` / `RPT_DEBTREMOVE_DISDEBT` / `RPT_DEBTREMOVE_LAND_TRANSFER` | 仅当需多年序列或土地出让明细佐证“以地化债”时调用 |
| ⚪ 可选 | `RPT_CUSTOM_DEBTREMOVE_PROVINCE_DEBT_RANK` | 仅做省级排名/风险矩阵时调用 |
| ❌ 一般不调 | 利差类（12-15）、成交类(18)、城投平台搜索(23)、行政地图(12/16)、二手房、产值按行业 | 与化债主题无关，**默认跳过**；仅用户明确要求时调用 |

**规则：优先 5 个核心接口；其余接口数据可被核心接口覆盖时一律跳过。接口失败（9501/9201）最多重试 1 次，失败即跳过对应模块，避免耗时。**

## 统一接口规范

- CHOICE 域（地方化债各报表基本都走此域）：测试与正式环境各有一个接口地址（格式为
  `{数据服务接口地址}/api/data/v1/get?`，具体地址由运行环境提供）。
- 部分报表走 `distinct` 域：`{数据服务接口地址}/distinct/api/data/v1/get?`
- 部分报表为总前台 `/api/data/v1/get`（如投资指数、二手房、土地等），同前两类域地址。

### 返回结构

```json
{ "code":0, "message":"", "result":{ "data":[...], "pages":n, "count":n, "pageNumber":1 } }
```
- `code`：0=成功且有数据；9201=成功但 0 条；9501=异常。
- `result.data` 为数据数组。

### 通用参数

| 参数 | 说明 |
|---|---|
| `reportName` | 报表英文名（每次必传） |
| `columns` | 返回字段英文名，逗号分隔 |
| `filter` | 过滤条件，多个用括号连接；字符串值用双引号，日期用单引号 |
| `pageNumber` / `pageSize` | 分页；建议 `pageSize=200` |
| `sortColumns` / `sortTypes` | 排序字段与排序方式（-n 倒序，n 正序；字符字段用 -2/2 支持拼音） |
| `source` | 固定 `CHOICE` |
| `client` | 固定 `SW` |

### filter 写法要点

- 单值：`(AREA_CODE="320000")`
- 多值：`(AREA_CODE in ("110000","320000"))`
- 日期：`(REPORT_DATE='2023-12-01')`
- 区间：`(REPORT_DATE>='2023-12-01')(REPORT_DATE<='2024-12-01')`
- 空值参与筛选（字符）：`((字段 in ("值"))(%7C(字段="")))`
- 空值参与筛选（日期/数值）：`((字段 in ("值"))(%7C(字段="NULL")))`
- `%2B` 为 `+` 转义；`%25` 为 `%` 转义（like 模糊查询）；`%7C` 为 `|`。

## 一、首页/总览（化债主线，核心①）

### 1) RPT_DEBT_AREAHOMEPAGE_LEFT —— 全国/地区首页主表（快照，默认最新）

整张主表同时承载「限额分配、财政资金覆盖、商品房、未来偿债、最新化债情况」等模块。
**该表为快照报表，`AREA_TYPE` 区分层级**：`1` 省级 / `2` 市级 / `3` 全国+省级（部分接口用 `in (1,3)`）。

**子模块取数示例：**

| 场景 | columns | filter |
|---|---|---|
| 最新化债情况 | `AREA_CODE,AREA,AREA_TYPE,INVEST_INDEX,HIDDENDEBT_BALANCE,IMPLICIT_DEBT,IMPLICIT_DEBT_CHANGE` | `(AREA_TYPE in (1,3))` |
| 本息覆盖率 | `AREA_CODE,AREA,REEX_GAP,LOCAL_FUND,BOND_BALANCE,COVERAGE,HIDDENDEBT_BALANCE` | `(AREA_TYPE=1)` |
| 专项债余额 | `AREA_CODE,AREA,GDP,BALANCE,RELATIVE_SCALE` | `(AREA_TYPE=1)` |
| 未来偿债 | `AREA_CODE,AREA,REPAY_AMT_DFZ,REPAY_AMT_CTZ` | `(AREA_TYPE=1)` |
| 商品房销售 | `AREA,AREA_CODE,PRICE_COMHOUSE,PRICE_COMHOUSE_MOM,STR_REPORTMONTH` | `(AREA_TYPE=1)` |
| 全字段（推荐） | `ALL` | 按需 |

**字段语义：** `INVEST_INDEX`=地方债投资指数；`HIDDENDEBT_BALANCE`=最新隐债规模(亿)；
`IMPLICIT_DEBT`=城投及地方国企债务(亿)；`IMPLICIT_DEBT_CHANGE`=债务变动百分比(城投及地方国企)(%)；
`REEX_GAP`=收支缺口(亿)；`LOCAL_FUND`=可供还债的地方财政资金(亿)；`BOND_BALANCE`=专项债券还本付息支出(亿)；
`COVERAGE`=覆盖率(%)；`GDP`=地区生产总值(亿)；`BALANCE`=专项债务余额；`RELATIVE_SCALE`=专项债务余额的相对规模；
`REPAY_AMT_DFZ`=地方债偿还(亿)；`REPAY_AMT_CTZ`=城投债偿还(亿)；
`PRICE_COMHOUSE`=商品房销售价格；`PRICE_COMHOUSE_MOM`=商品房销售价格环比(%)。

### 2) RPT_CUSTOM_DEBTREMOVE_PROVINCE_DEBT —— 省级指标（含分位数，核心③）

- `columns`：`INDICATOR_NAME,INDICATOR_VALUE,RANK,QUANTILE,INDICATOR_TYPE`
- `filter`：`(AREA_CODE="110000")(END_DATE='2024-12-12')`
- 用途：某一省份的多项化债指标的数值、排名、分位数。

### 3) RPT_CUSTOM_DEBTREMOVE_PROVINCE_DEBT_RANK —— 全国热力图（排名汇总，可选 D）

- `columns`：`AREA_CODE,RANK_SUM`（无需 filter）
- 用途：生成全国省份化债成效热力图（东财地方化债成效评分）。

### 4) RPT_DEBTREMOVE_AREA_PLATFORM —— 省市区热力图（融资平台，可选）

- `filter`：`(AREA_CODE_F="320000")`
- `columns`：`AREA_CODE_F,AREA_F,AREA_CODE,AREA,LFP_NUM,LOCAL_GOV_NUM,LFP_LOCALGOV_NUM`

### 5) RPT_DEBTREMOVE_EXITORG_LIST —— 退平台名单（核心⑤）

- 前缀：`distinct` 域。
- `columns`：`ORG_CODE,ORG_NAME,EXIT_PUBLISH_DATE,PROVINCE_CODE,PROVINCE,CITY_CODE,CITY,RATING_ORG,RATING_ORG_FILTER,REMAIN_VOL,SJKZR,INTEREST_DEBT_RATIO,ZCFZL,ISSUE_MARGIN,WEIGHTED_COST,STR_EXIT_PUBLISH_DATE,IS_MARKET,IS_IMPLICIT,IS_EXIT`
- `filter`：`(PROVINCE in ("江苏省","河北省"))(RATING_ORG_FILTER in ("AA%2B"))`
- `sortColumns`：`REMAIN_VOL`（末尾补 `ORG_CODE`）。

### 6) RPT_BOND_REGION_INVESTINDEX —— 专项债券分省投资指数（时序）

- 前缀：`/api/data/v1/get`
- `columns`：`PROVINCE_CODE,PROVINCE_NAME,NOTICE_DATE,END_DATE,INVEST_INDEX`
- `filter`：`(PROVINCE_CODE="450000")`
- **长期序取最新：`sortColumns=END_DATE&sortTypes=-1`。**

## 二、区域经济与财政（核心②，主要用于 GDP 分母与财政背景）

### 7) RPT_BOND_REGION_ECONOMYALL —— 地方经济与财政(总览)

字段非常全，reportName=`RPT_BOND_REGION_ECONOMYALL`。**2.0 版仅取化债所需字段（GDP、政府债务、
财政收支背景），不做长篇幅经济综述。**

常用 columns（精简，聚焦化债分母与背景）：

```
REGION_CODE,REGION,REPORT_DATE,YEAR,GDP,GDP_AVG,GDP_AVG_RATIO,
BUDGETARY_RECEIPT,TAX_INCOME_RATIO,FUNDED_INCOME,SELF_SUFFICIENCY_RATE,
BUDGETARY_OUTLAY,GOVERNMENT_DEBT,LIABILITIES_RATIO,NARROW_DEBT_RATIO,BOND_BALANCE,
LAND_SALE_REVE,RESIDENT_POP,GDPDYCY,GDPDECY,GDPDSCY,INVEST_INDEX
```

- **取某省最新年度**：`columns=...&filter=(REGION_CODE="320000")(REPORT_DATE='2023-12-01')&sortColumns=REPORT_DATE&sortTypes=-1`。
- **取全国/省级下级**：`filter=(REGION_CODE in (省级列表))(REPORT_DATE='2023-12-01')(AREA_LEVEL="0")` 或 `(AREA_CODE_F in ("100000"))`。
- **告警**：`REPORT_DATE` 用月度/年度(通常 `yyyy-MM-01`)；取最新非空即可。

字段中文含义（化债相关部分）：

| 英文 | 中文 | 英文 | 中文 |
|---|---|---|---|
| `GDP` | 地区生产总值(亿) | `GOVERNMENT_DEBT` | 地方政府债务(余额) |
| `LIABILITIES_RATIO` | 负债率(%) | `NARROW_DEBT_RATIO` | 债务负担率 |
| `BUDGETARY_RECEIPT` | 一般公共预算收入 | `BUDGETARY_OUTLAY` | 一般公共预算支出 |
| `FUNDED_INCOME` | 政府基金性收入 | `TAX_INCOME_RATIO` | 税收占比 |
| `SELF_SUFFICIENCY_RATE` | 财政自给率 | `LAND_SALE_REVE` | 国有土地使用权出让收入 |
| `RESIDENT_POP` | 常住人口(万人) | `BOND_BALANCE` | 债券余额 |
| `GDPDYCY/GDPDECY/GDPDSCY` | 一/二/三产业值 | `INVEST_INDEX` | 投资指数 |

### 8. 区域配套时序接口（仅在需多年序列时使用）

| 模块 | reportName | 关键 columns | filter 示例 |
|---|---|---|---|
| 区域财政 | `RPT_DEBTREMOVE_REGION_ECONOMY` | `BUDGETARY_RECEIPT,TAX_INCOME,FUNDED_INCOME,GYTDSYQCR,SSYLD,...` | `(AREA_CODE="110000")(IS_SELF="0")` |
| 区域债务 | `RPT_DEBTREMOVE_DISDEBT` | `DFZFZWYE,DFZFYBZWYE,DFZFZXZWYE,DFZFZWXE,...*_YOY` | `(AREA_CODE="110000")` |
| 土地出让 | `RPT_DEBTREMOVE_LAND_TRANSFER` | `TDGZF,TDGZMJ,GYTDSYQCRSR` | `(AREA_CODE="110000")` |
| 投资开发 | `RPT_DEBTREMOVE_INVDEV` | `GDZCTZ,GDZCTZZS,FDCTZ,FDCTZZS` | `(AREA_CODE="110000")` |
| 金融机构存贷款 | `RPT_DEBTREMOVE_FI_DEPOLOAN` | `JRJGGXCKYE,JRJGGXDKYE,...` | `(AREA_CODE="110000")(FREQUENCY="月")` |

## 三、政府化债动态（核心④）

### 9) RPT_CUSTOM_DEBTREMOVE_GOV_PROCESS —— 政府化债动态

- **最新**（`IS_NEW=1`）：`columns=INFO_CODE,AREA_CODE,NOTICE_DATE,STR_NOTICE_DATE,PROCINCE,PROCINCE_CODE,CITY_RN,CITY,CITY_CODE,DISTRICT_RN,DISTRICT,DISTRICT_CODE,DEFUSE_DEBT_PROCESS,DEFUSE_DEBT_OUTLOOK,NOTICE_TITLE,NOTICE_URL,SOURCE,SOURCE_CODE`
  `filter=(END_DATE='2025-03-20')(PROCINCE_CODE+in+("110000","130000"))(CITY_CODE+in+("340100","340200"))(IS_NEW="1")`
- **历程**（`IS_NEW=0`，某地区全部动态）：`filter=(END_DATE='2025-03-20')(AREA_CODE+in+("110000"))(IS_NEW="0")&sortColumns=NOTICE_DATE&sortTypes=-1`
- 字段：`DEFUSE_DEBT_PROCESS`=化债进度，`DEFUSE_DEBT_OUTLOOK`=化债展望，`NOTICE_TITLE`=公告标题，
  `NOTICE_URL`=公告链接，`SOURCE`=来源，`PROCINCE/CITY/DISTRICT`=省市区。

### 10) RPT_DEBTREMOVE_GOV_PROCESSFJ —— 政府化债动态附件

- `filter=(INFO_CODE="AN202504011649775992")&columns=INFO_CODE,NOTICE_TITLE,NOTICE_URL`

## 四、其它接口（默认跳过，仅用户明确要求时调用）

| 报表 | 用途 | 2.0 处置 |
|---|---|---|
| `RPT_CUSTOM_BOND_PLAN_AREAREPAY_UP/_DOWN`、`RPT_CUSTOM_BOND_PLAN_AREAISSUEQUTA` | 地方债计划偿还/发行限额 | 输出“政府债发行节奏与计划执行”维度时调用，其余情况跳过 |
| `RPT_BOND_BS_BALANCESTATLISTFO`、`RPT_BOND_BS_GOVBALANCEINFOFO` | 地方债存量/个券明细 | 一般跳过 |
| `RPT_BOND_MAP_PRODL` | 行政地图 | 一般跳过 |
| `RPT_DEBTREMOVE_MARGIN_TDATE`、`RPT_CUSTOM_DEBTREMOVE_MARGIN_INFO2/_INFO/_INFO_DOWN` | 地方债/城投债利差 | 与主题无关，默认跳过 |
| `RPT_BOND_CITYBOND_MAP`、`RPT_CUSTOM_URBANINVEST_MAPS_BONDF/_BONDF_DOWN` | 城投债计划偿还地图/上下表 | 一般跳过 |
| `RPT_CUSTOM_BOND_TS_BONDMARKET_CTZSTAT` | 城投债成交统计 | 默认跳过 |
| `RPT_BOND_BS_URBATERR` | 城投平台搜索 | 默认跳过 |
| `RPT_BOND_REALTY_*` | 房地产施工/二手房/产值/人口/就业 | 默认跳过 |

## 使用建议（生成报告时的“最新数据”编排）

生成 HTML 报告时，尽量把“最新一期”数值打上数据源标签，并在备注行注明“数据来源：东方财富Choice”。
若某字段返回为空或“-”，则该段落或图表相应省略或标注“数据披露滞后”，不写虚构值。
派生指标（广义债务率、到期覆盖倍数等）须标注“测算”，见 `analysis_dimensions.md`。

> 本文件为运行路由；调用时以本表 reportName 与 columns 为准，不要自行拼接不存在的报表或字段。