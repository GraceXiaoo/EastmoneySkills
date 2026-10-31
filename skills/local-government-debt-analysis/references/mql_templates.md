# MQL 取数模板（地方化债skill · MQL 通道）

本文件提供【地方化债skill】所依赖报表在 **妙想数据 MQL 报表体系**中的对应报表与取数模板（统一新样式），
供「可选：MQL 数据服务取数」通道使用（见 SKILL.md《一、报表数据服务 → 可选：MQL 数据服务取数》）。

> **两条通道的关系（重要）**
> - **HTTP 报表数据服务（主通道，不变）**：`RPT_*` 报表名、`columns`/`filter` 英文名，见 `interface_catalog.md`。
> - **MQL 报表通道（本文件）**：以下报表是同一批数据在 Choice「债券专题\地方化债」报表目录中的对应报表，
>   字段为中文 `column_name_cn`，用 `REPORT_FIELD` 读取。
> - **禁止交叉来源混搭口径**：同一指标全文只取一个来源。选定通道后全程一致，不得用 MQL 值「校正」接口值。

## 一、模板书写规范（统一）

1. `ReportBlock` 的目标路径**必须带 `|报表ID`**（完整引用取自 `Search_Context` 的 `indicatorPath`）。
2. `SetReportFilter(...)` **单行书写**，多条件用 `AND` 连接。
3. 每个输出列一行：`{别名}: REPORT_FIELD("报表字段中文名");`。
4. **脚本结尾必须有 `OutputBlock();`**。
5. 日期 filter 值用 `"yyyy-MM-dd"`。

## 二、MQL 调用前置规则

1. 先调用 `Get_MQL_Reference`（一次）。
2. 再调用 `Search_Business_Knowledge`（`varieties=["债券"]`）。
3. 首次 `Search_Context` 须全量传入 `typeCodes`；后续补调用 `searchIndicator.keys` 精确检索报表。
4. 用 `Execute_MQL` 执行；一律采用返回的 `indicatorPath` 完整引用（含 `|报表ID`）。

## 三、核心报表对应关系与模板

| 前端模块 / HTTP 接口 | MQL 对应报表 | 报表ID | STD |
|---|---|---|---|
| `RPT_DEBT_AREAHOMEPAGE_LEFT`（最新化债情况、本息覆盖率、专项债余额、未来偿债、商品房销售） | 地方化债_全国指标左侧栏 | 796063565160051 | false |
| `RPT_BOND_REGION_ECONOMYALL`（地方经济与财政总览） | 地区经济与财政 | 938162136306624 | false |
| `RPT_DEBTREMOVE_EXITORG_LIST`（退平台名单） | 地方化债_退平台名单 | 580271070823137 | false |
| 省市区热力图（融资平台） | 地方化债_地区平台数量 | 211553395861833 | false |
| 政府化债动态（附件） | 地方化债_政府化债动态_附件 | 493265748990442 | false |
| `RPT_CUSTOM_DEBTREMOVE_GOV_PROCESS`（化债进度/化债展望） | 近期所属地区化债进度 | 645935680656235 | false |

### 3.1 地方化债_全国指标左侧栏（核心①，覆盖化债前端 5 个模块）

`{地区类型}`：`1`=省级、`2`=市级、`3`=全国+省级（部分场景用 `IN` 列多值）。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券专题\地方化债\地方化债跟踪\最新化债情况\地方化债_全国指标左侧栏|796063565160051});
SetReportFilter({地区类型} == "1");
{地区名称}: REPORT_FIELD("地区名称");
{地区编码}: REPORT_FIELD("地区编码");
{地区类型}: REPORT_FIELD("地区类型");
{地方债投资指数}: REPORT_FIELD("地方债投资指数");
{隐性债务规模}: REPORT_FIELD("隐性债务规模(亿元)");
{隐性债务规模披露值}: REPORT_FIELD("隐性债务规模披露值");
{化债以来消减债务变动}: REPORT_FIELD("化债以来消减债务变动");
{隐债规模降速}: REPORT_FIELD("隐债规模降速(%)");
{显性债务规模}: REPORT_FIELD("显性债务规模(亿元)");
{专项债务余额}: REPORT_FIELD("专项债务余额(亿元)");
{专项债务余额占GDP}: REPORT_FIELD("专项债务余额/GDP");
{专项债券还本付息支出}: REPORT_FIELD("专项债券还本付息支出(亿元)");
{收支缺口}: REPORT_FIELD("收支缺口(亿元)");
{可供还债的地方财政资金}: REPORT_FIELD("可供还债的地方财政资金(亿元)");
{覆盖率}: REPORT_FIELD("覆盖率(%)");
{地方债偿还金额}: REPORT_FIELD("地方债偿还金额(亿元)");
{城投债偿还金额}: REPORT_FIELD("城投债偿还金额(亿元)");
{商品房销售价格}: REPORT_FIELD("商品房销售价格(元/㎡)");
{商品房销售价格环比}: REPORT_FIELD("商品房销售价格环比(%)");
{区域高收益债务占比}: REPORT_FIELD("区域高收益债务占比(%)");
{加权融资成本}: REPORT_FIELD("加权融资成本(%)");
{GDP}: REPORT_FIELD("GDP");
OutputBlock();
```

> 派生指标（广义债务率、到期覆盖倍数等）仍按 `analysis_dimensions.md` 公式由上述字段**交叉测算**，并标注「测算」。
> 若只需某一模块，可只保留该模块的 `REPORT_FIELD` 行；**仍建议一次取回全部字段**（性能优化原则）。

### 3.2 地区经济与财政（核心②：GDP 分母与财政背景）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券专题\地方化债\地方经济与财政\报表明细\地区经济与财政|938162136306624});
SetReportFilter({地区编码} == "320000" AND {报告期} == "2023-12-01");
{地区中文名}: REPORT_FIELD("地区中文名");
{报告期}: REPORT_FIELD("报告期");
{GDP}: REPORT_FIELD("GDP(亿元)");
{一般公共预算收入}: REPORT_FIELD("一般公共预算收入(亿元)");
{一般公共预算支出}: REPORT_FIELD("一般公共预算支出(亿元)");
{政府基金性收入}: REPORT_FIELD("政府基金性收入");
{税收收入占比}: REPORT_FIELD("税收收入占比(%)");
{财政自给率}: REPORT_FIELD("财政自给率(%)");
{地方政府债务余额}: REPORT_FIELD("地方政府债务余额(亿元)");
{负债率}: REPORT_FIELD("负债率(%)");
{窄口径债务率}: REPORT_FIELD("窄口径债务率(%)");
{土地出让收入}: REPORT_FIELD("土地出让收入(亿)");
{城投债余额}: REPORT_FIELD("城投债余额(亿元)");
{城投平台数}: REPORT_FIELD("城投平台数(家)");
{常住人口}: REPORT_FIELD("常住人口");
OutputBlock();
```

> 该表返回多期序列；如需最新一期，可读取 `{报告期}` 为输出列后按需 `Sort({报告期}, "DESC"); Head(1);`，或直接用最新报告期作 filter 值。

### 3.3 地方化债_退平台名单（核心⑤：平台压降/整合转型）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券专题\地方化债\城投债分析\退平台名单\地方化债_退平台名单|580271070823137});
SetReportFilter({省份} == "江苏省" AND {主体评级(筛选用)} == "AA+");
{发行人中文名}: REPORT_FIELD("发行人中文名");
{发行人代码}: REPORT_FIELD("发行人代码");
{省份}: REPORT_FIELD("省份");
{市区}: REPORT_FIELD("市区");
{发布时间}: REPORT_FIELD("发布时间");
{主体评级}: REPORT_FIELD("主体评级");
{债券余额}: REPORT_FIELD("债券余额");
{有息负债率}: REPORT_FIELD("有息负债率(%)");
{资产负债率}: REPORT_FIELD("资产负债率(%)");
{主体利差}: REPORT_FIELD("主体利差(BP)");
{加权融资成本}: REPORT_FIELD("加权融资成本(%)");
{实际控制人}: REPORT_FIELD("实际控制人");
OutputBlock();
```

> 该表供「平台压降数量」信号使用；省级筛选后按市区汇总统计。加载列中文名：`省份`、`市区`、`主体评级(筛选用)`。

### 3.4 地方化债_地区平台数量（省市区热力图）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券专题\地方化债\地方化债跟踪\化债动态热力图\热力指数\地方化债_地区平台数量|211553395861833});
SetReportFilter({上级地区编码} == "320000");
{地区名称}: REPORT_FIELD("地区名称");
{地区编码}: REPORT_FIELD("地区编码");
{上级地区名称}: REPORT_FIELD("上级地区名称");
{城投平台数量}: REPORT_FIELD("城投平台数量");
{地方国企数量}: REPORT_FIELD("地方国企数量");
{地区发行人数量}: REPORT_FIELD("地区发行人数量");
OutputBlock();
```

### 3.5 地方化债_政府化债动态_附件

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券专题\地方化债\政府化债动态\最新动态\地方化债_政府化债动态_附件|493265748990442});
SetReportFilter({总公告编码} == "{INFO_CODE}");
{总公告编码}: REPORT_FIELD("总公告编码");
{附件标题}: REPORT_FIELD("附件标题");
{附件地址}: REPORT_FIELD("附件地址");
OutputBlock();
```

> `{总公告编码}` 传入 `RPT_CUSTOM_DEBTREMOVE_GOV_PROCESS` 出参 `INFO_CODE`。

### 3.6 化债进度 / 化债展望（对应政府化债动态文本模块）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\城投债\存续城投债\近期所属地区化债进度|645935680656235});
SetReportFilter({地区编码} == "{AREA_CODE}" AND {截止日期} == "{系统日期}" AND {是否最新} == "1");
{地区编码}: REPORT_FIELD("地区编码");
{近期所属地区化债进度}: REPORT_FIELD("近期所属地区化债进度");
{近期所属地区化债展望}: REPORT_FIELD("近期所属地区化债展望");
FILTER_ROWS({地区编码} == "{AREA_CODE}");
OutputBlock();
```

> **实测约束**：`SetReportFilter` **必须带 `{截止日期}`**，否则报 `filter参数必须包含END_DATE`；
> 远端不按 `{地区编码}` 收窄（返回全量），必须追加本地 `FILTER_ROWS({地区编码} == "{AREA_CODE}");`。

## 四、报表探测结论速查（2026-10 实测）

| MQL 报表 | 报表ID | STD | 结论 |
|---|---|---|---|
| 地方化债_全国指标左侧栏 | 796063565160051 | false | 可用（5 个前端模块一次取回） |
| 地方债_全国指标左侧栏（未来偿债子表） | 796063565160051 | false | 可用（地方债偿还/城投债偿还） |
| 地区经济与财政 | 938162136306624 | false | 可用（GDP/政府债务/财政背景；多期取最新） |
| 地方化债_退平台名单 | 580271070823137 | false | 可用（省份/市区/评级筛选） |
| 地方化债_地区平台数量 | 211553395861833 | false | 可用（上级地区编码筛选） |
| 地方化债_政府化债动态_附件 | 493265748990442 | false | 可用（总公告编码筛选） |
| 近期所属地区化债进度 | 645935680656235 | false | 可用（**必须带截止日期** + 本地 FILTER_ROWS） |

> 说明：`RPT_CUSTOM_DEBTREMOVE_PROVINCE_DEBT`（省级化债指标与全国排名）在 MQL 报表目录中未检索到同名对应报表，
> 该接口请继续走 **HTTP 报表数据服务**通道；如需 MQL 口径的省级化债成效排名，可改用 `地方化债_全国指标左侧栏` 的省级切片，
> 并在报告中注明口径差异。
