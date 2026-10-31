# MQL 取数模板（信用债skill）

本文件收录【信用债skill】的全部已验证 MQL 取数模板与探测结论。所有模板均通过 MQL 工具链 `Execute_MQL` 实测。

> **模板书写规范（本版统一，务必遵守）**
> 1. `ReportBlock` 的报表路径**必须带 `|报表ID`**（完整引用 = `报表路径|报表ID`，来自 `Search_Context` 的 `indicatorPath`）。
> 2. `SetReportFilter(...)` **单行书写**，多个条件用 `AND` 连接；仅 `reportStandardCodeSupported=false` 时使用。
> 3. 每个输出列一行：`{别名}: REPORT_FIELD("报表字段中文名");`。
> 4. **脚本结尾必须有 `OutputBlock();`**（只返回被标记的 Block）。
> 5. 日期 filter 值用 `"yyyy-MM-dd"`；字符串值用双引号。

## 一、已验证的真实债券样本

| 债券代码 | 债券简称 | 标签 | 存续状态 |
|---|---|---|---|
| 2605149.IB | 26湖北债19 | 地方政府债 | 存续 |
| 104501.IB | 19海南债01 | 地方政府债 | 到期 |
| 199333.IB | 25广东债41 | 地方政府债 | 存续 |
| 102680471.IB | 26长沙城投MTN001 | 城投债 | 存续（发行人代码 10078059） |
| 2620007.IB | 26苏州银行01 | 银行金融机构债 | 存续 |
| 1620007.IB | 16泉州银行二级 | 银行金融机构债 | 到期（发行人 泉州银行，公司代码 10058582，发行 2016-01-28，到期 2021-01-29） |
| 137514.SH | 22华福G4 | 非银金融机构债 | 存续 |
| 115067.SH | 交筑YK01 | 科创债 | 到期 |
| 222500006.IB | 25渤海银行绿债01 | 银行+绿色（双标签） | 存续（发行人 渤海银行，公司代码 10068138） |
| 1620036.IB | 16江西银行绿色金融04 | 银行+绿色（双标签） | 到期 |
| 112799.SZ | 18苏宁06 | 无标签（全否） | — |

## 二、MQL 调用前置规则

1. 首次检索前必须先调用 `Get_MQL_Reference`（一次即可）。
2. 再调用 `Search_Business_Knowledge`（传 `varieties=["债券"]`、`user_query`、`keywords`、`query_rewrites`）。
3. 首次 `Search_Context` 必须全量传入上一步返回的全部 `typeCodes`。
4. 后续 `Search_Context` 补调可直接基于前序结果，用 `searchIndicator.keys` 精确检索报表。
5. 最终用 `Execute_MQL` 执行。生成 MQL 时 **一律采用 `Search_Context` 返回的 `indicatorPath` 完整引用（含 `|报表ID`）**，不得只取 `|` 前的路径。

## 三、报表取数通用结构（ReportBlock）

```mql
ReportBlock(#1, {报表完整路径|报表ID});
SetCodes("{债券代码}");                       // 仅当 reportStandardCodeSupported=true，必须且只能写一个
SetReportFilter({中文列名} == "值" AND {中文列名} == "值");   // 仅当 reportStandardCodeSupported=false，单行、AND 连接
{输出别名}: REPORT_FIELD("报表字段中文名");      // 每句末尾必须有分号
OutputBlock();                                 // 脚本末尾必须有
```

- `reportStandardCodeSupported=true`：只能写 `SetCodes`，禁止再写代码列的 `SetReportFilter`。
- `reportStandardCodeSupported=false`：禁止 `SetCodes`，改用 `SetReportFilter`；若还需按代码/地区收窄，请先把该列用 `REPORT_FIELD` 读成输出列，再追加本地 `FILTER_ROWS({列} == "值");`（远端 filter 对部分报表不生效时尤其必要）。
- **债券标签、AI研究员搜索报表一次 `SetCodes` 多只只返回第一只，必须逐只循环调用。**

## 四、标签判定模板

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\债券标签\债券标签|457922590417606});
SetCodes("{债券代码}");
{是否地方政府债}: REPORT_FIELD("是否地方政府债(AI用)");
{是否银行}: REPORT_FIELD("是否银行金融机构债(AI用)");
{是否非银}: REPORT_FIELD("是否非银金融机构债(AI用)");
{是否城投}: REPORT_FIELD("是否城投债(东财口径)(AI用)");
{是否科创}: REPORT_FIELD("是否科创债(AI用)");
{是否绿色}: REPORT_FIELD("是否绿色债(AI用)");
{是否存续}: REPORT_FIELD("是否存续");
{省市}: REPORT_FIELD("省市(计划单列市）");
{省市代码}: REPORT_FIELD("省市代码(计划单列市）");
OutputBlock();
```

辅助：AI研究员搜索（同族报表，`reportStandardCodeSupported=true`，逐只调用）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\AI研究员搜索\AI研究员搜索|457922590417606});
SetCodes("{债券代码}");
{债券全称}: REPORT_FIELD("债券全称");
{债券简称}: REPORT_FIELD("债券简称");
{债券代码}: REPORT_FIELD("债券代码");
OutputBlock();
```

## 五、各标签核心报表模板

### 5.1 存续城投债（可用）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\城投债\存续城投债\存续城投债|077542525591078});
SetCodes("{债券代码}");
{债券简称}: REPORT_FIELD("债券简称");
{债券代码}: REPORT_FIELD("债券代码");
{发行人全称}: REPORT_FIELD("发行人全称");
{所属地区}: REPORT_FIELD("所属地区");
{行政级别}: REPORT_FIELD("行政级别");
{城投地位}: REPORT_FIELD("城投地位");
{票面利率}: REPORT_FIELD("票面利率(当期参考)(%)");
{发行规模}: REPORT_FIELD("发行规模(亿元)");
{债券余额}: REPORT_FIELD("债券余额(亿元)");
{最新主体评级}: REPORT_FIELD("最新主体评级");
{最新债项评级}: REPORT_FIELD("最新债项评级");
{银行授信总额}: REPORT_FIELD("银行授信总额");
{未使用额度}: REPORT_FIELD("未使用额度");
{发行人代码}: REPORT_FIELD("发行人代码");
OutputBlock();
```

> 字段级规避：跳过 `估价收益率(中债)(行权/到期)(%)`、`剩余期限(年)`。

### 5.2 到期城投债（**已实测可调用**，原「整体不可用」结论作废）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\城投债\到期城投债\到期城投债|770476112283445});
SetCodes("{债券代码}");
{债券简称}: REPORT_FIELD("债券简称");
{发行人全称}: REPORT_FIELD("发行人全称");
{行政级别}: REPORT_FIELD("行政级别");
{所属地区}: REPORT_FIELD("所属地区");
{实际控制人}: REPORT_FIELD("实际控制人");
{票面利率}: REPORT_FIELD("票面利率(发行参考)(%)");
{发行规模}: REPORT_FIELD("发行规模(亿元)");
{发行起始日}: REPORT_FIELD("发行起始日");
{实际到期日}: REPORT_FIELD("实际到期日");
{持有期年化回报率}: REPORT_FIELD("持有期年化回报率(%)");
{持有期累计票息}: REPORT_FIELD("持有期累计票息收入（每百元）");
{最终估价全价}: REPORT_FIELD("最终估价全价");
{发行时主体评级}: REPORT_FIELD("发行时主体评级");
{到期时主体评级}: REPORT_FIELD("到期时主体评级");
{存续期间估值收益率最高值}: REPORT_FIELD("存续期间估值收益率最高值");
{存续期间估值收益率最低值}: REPORT_FIELD("存续期间估值收益率最低值");
{兑付方式}: REPORT_FIELD("兑付方式");
OutputBlock();
```

### 5.3 城投平台基本资料表（STD=false，公司代码来自存续城投债的「发行人代码」）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\城投债\城投债复用线上接口\城投平台基本资料表\城投平台基本资料表|823827806486891});
SetReportFilter({公司代码} == "10078059");
{公司名称}: REPORT_FIELD("公司名称");
{行政级别}: REPORT_FIELD("行政级别");
{所属地区}: REPORT_FIELD("所属地区");
{实际控制人}: REPORT_FIELD("实际控制人");
{实际控制人控股穿透比例}: REPORT_FIELD("实际控制人控股穿透比例(%)");
{发行人评级}: REPORT_FIELD("发行人评级");
{是否市场化声明}: REPORT_FIELD("是否市场化声明");
{是否上市}: REPORT_FIELD("是否上市");
{报告期}: REPORT_FIELD("报告期");
OutputBlock();
```

> 实测：`{公司代码} == "10078059"` 成功返回（长沙市城市建设投资开发集团有限公司，报告期 2026-06-30）。**filter 值不要带 `.FXR` 后缀**（带后缀返回 0 行）。该表返回多期序列，取最新报告期一行。

### 5.4 城投债财务部分（STD=false，**已实测可用**，原「ORG_CODE 冲突不可用」结论作废）

存续版：

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\城投债\存续城投债\城投债财务部分|556585164769088});
SetReportFilter({发行人} == "10078059");
{公司代码}: REPORT_FIELD("公司代码");
{资产负债率}: REPORT_FIELD("资产负债率");
{带息债务}: REPORT_FIELD("带息债务");
{EBITDA}: REPORT_FIELD("EBITDA(正推)");
{总资产}: REPORT_FIELD("总资产");
{总负债}: REPORT_FIELD("总负债");
{货币资金}: REPORT_FIELD("货币资金");
{受限货币资金}: REPORT_FIELD("受限货币资金");
{经营活动现金流量净额}: REPORT_FIELD("经营活动产生的现金流量净额");
{担保金额合计}: REPORT_FIELD("担保金额合计");
{担保金额占净资产比例}: REPORT_FIELD("担保金额占净资产比例");
{报告期日期}: REPORT_FIELD("报告期日期");
OutputBlock();
```

到期版：报表路径改为 `...\城投债\到期城投债\城投债财务部分|556585164769088`，filter 为 `{发行人} == "{发行人代码}" AND {到期日期} == "{实际到期日}"`。

> 实测：`{发行人} == "10078059"` 成功返回 1 行（报告期 2026-06-30，资产负债率 53.12%）。**filter 加载列的中文名是「发行人」，不是「公司代码」**（「公司代码」是返回列）。

### 5.5 近期所属地区化债进度（STD=false）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\城投债\存续城投债\近期所属地区化债进度|645935680656235});
SetReportFilter({地区编码} == "430000" AND {截止日期} == "2026-09-30" AND {是否最新} == "1");
{地区编码}: REPORT_FIELD("地区编码");
{近期所属地区化债进度}: REPORT_FIELD("近期所属地区化债进度");
{近期所属地区化债展望}: REPORT_FIELD("近期所属地区化债展望");
FILTER_ROWS({地区编码} == "430000");
OutputBlock();
```

到期券版（存续期内所属地区化债进度）：

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\城投债\到期城投债\存续期内所属地区化债进度|645935680656235});
SetReportFilter({地区编码} == "430000" AND {截止日期} == "2026-09-30" AND {是否最新} == "1");
{地区编码}: REPORT_FIELD("地区编码");
{近期所属地区化债进度}: REPORT_FIELD("近期所属地区化债进度");
{近期所属地区化债展望}: REPORT_FIELD("近期所属地区化债展望");
FILTER_ROWS({地区编码} == "430000");
OutputBlock();
```

> **实测重要结论**：
> - `SetReportFilter` **必须包含 `{截止日期}`（END_DATE）**，否则报错 `报表数据量预检失败：filter参数必须包含END_DATE`。
> - 远端 **不会按 `{地区编码}` 收窄**（返回 2676 行全量），必须在输出列之后追加本地 `FILTER_ROWS({地区编码} == "430000");` 才能筛到目标省份（实测可得到 1 行）。
> - 因此原「IS_NEW 参数未验证、整体不可用」的结论修正为：**可用，但必须带 END_DATE + 本地 FILTER_ROWS**。

### 5.6 估值与市场信号_债券利差（**硬卡点，不可用**）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\城投债\存续城投债\估值与市场信号_债券利差|061066940812509});
SetCodes("{债券代码}");
{债券代码}: REPORT_FIELD("债券代码");
{债券利差}: REPORT_FIELD("债券利差");
{超额利差}: REPORT_FIELD("超额利差(BP)");
{中债估价收益率}: REPORT_FIELD("中债估价收益率");
{中证估价收益率}: REPORT_FIELD("中证估价收益率");
{上清所估价收益率}: REPORT_FIELD("上清所估价收益率");
OutputBlock();
```

> **实测报错**：`REPORT_METADATA_INVALID: unsupported column type: 基准日期/detime`（stage=metadata）。该报表加载列 `基准日期` 的类型为无效的 `detime`，服务端元数据损坏，**调用即失败，直接跳过**。城投债的估价收益率/信用利差维度改用 5.7 区域化债进度 + 基础信息表述，或省略该维度。

### 5.7 存续银行债基础信息（STD=true）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\银行金融机构债\存续银行金融机构债\AI一页纸存续银行金融机构债|172514974433160});
SetCodes("{债券代码}");
{债券简称}: REPORT_FIELD("债券简称");
{债券代码}: REPORT_FIELD("债券代码");
{发行人名称}: REPORT_FIELD("发行人名称");
{票面利率}: REPORT_FIELD("票面利率(当期参考)(%)");
{估值收益率}: REPORT_FIELD("估值收益率");
{剩余期限}: REPORT_FIELD("剩余期限(行情用，年)");
{发行规模}: REPORT_FIELD("发行规模(亿元)");
{主体评级}: REPORT_FIELD("主体评级_国内评级机构(除中债资信))");
{债项评级}: REPORT_FIELD("债项评级_国内评级机构(除中债资信))");
{是否系统重要银行}: REPORT_FIELD("是否系统重要银行");
{是否TLAC债}: REPORT_FIELD("是否TLAC债");
{最新与国开利差}: REPORT_FIELD("最新与国开利差");
OutputBlock();
```

> 字段级规避：避免引用「发行人代码」字段（`ISSUE_CODE` 的 `column_name_cn` 实际为 `发行人代码\u0000`，含空字符，`REPORT_FIELD` 无法绑定）。

### 5.8 存续银行债财务部分（STD=false，单参数 公司代码）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\银行金融机构债\存续银行金融机构债\AI一页纸_存续银行债财务部分|872852055351144});
SetReportFilter({公司代码} == "{公司代码}");
{不良贷款率}: REPORT_FIELD("不良贷款率(%)");
{拨备覆盖率}: REPORT_FIELD("不良贷款拨备覆盖率(%)");
{核心一级资本充足率}: REPORT_FIELD("核心一级资本充足率(%)");
{资本充足率}: REPORT_FIELD("资本充足率(2013)(%)");
{净息差}: REPORT_FIELD("净息差(计算值)(%)");
{ROE}: REPORT_FIELD("ROE");
{总资产}: REPORT_FIELD("总资产");
{存款总额}: REPORT_FIELD("存款总额");
{贷款总额}: REPORT_FIELD("贷款总额");
{报告期}: REPORT_FIELD("报告期日期");
OutputBlock();
```

### 5.9 到期银行债基础信息（STD=true）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\银行金融机构债\到期银行金融机构债\AI一页纸到期银行金融机构债|930522266378689});
SetCodes("{债券代码}");
{债券简称}: REPORT_FIELD("债券简称");
{债券代码}: REPORT_FIELD("债券代码");
{发行人名称}: REPORT_FIELD("发行人名称");
{发行规模}: REPORT_FIELD("发行规模(亿元)");
{票面利率}: REPORT_FIELD("票面利率(当期参考)(%)");
{发行日期}: REPORT_FIELD("发行日期");
{到期日}: REPORT_FIELD("到期日(实际)");
{持有期年化回报率}: REPORT_FIELD("持有期年化回报率(%)");
{持有期累计票息}: REPORT_FIELD("持有期累计票息收入（每百元）");
{最终估价全价}: REPORT_FIELD("最终估价全价");
{发行时主体评级}: REPORT_FIELD("发行时主体评级");
{到期时主体评级}: REPORT_FIELD("到期时主体评级");
{首次债项评级}: REPORT_FIELD("首次债项评级");
{增信方式}: REPORT_FIELD("增信方式");
{违约类型}: REPORT_FIELD("违约类型");
OutputBlock();
```

### 5.10 到期银行债财务部分（STD=false，**已实测可用**，原「多 filter 解析异常」结论作废）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\银行金融机构债\到期银行金融机构债\AI一页纸_到期银行债财务部分|869534090566691});
SetReportFilter({公司代码} == "10058582" AND {发行日} == "2016-01-28" AND {到期日} == "2021-01-29");
{公司代码}: REPORT_FIELD("公司代码");
{不良贷款率_到期前}: REPORT_FIELD("不良贷款率（到期前）");
{不良贷款拨备覆盖率_到期前}: REPORT_FIELD("不良贷款拨备覆盖率（到期前）");
{核心一级资本充足率_到期前}: REPORT_FIELD("核心一级资本充足率（到期前）");
{净息差_到期前}: REPORT_FIELD("净息差（到期前）");
{不良贷款率_发行时}: REPORT_FIELD("不良贷款率（发行时）");
{不良贷款拨备覆盖率_发行时}: REPORT_FIELD("不良贷款拨备覆盖率（发行时）");
{核心一级资本充足率_发行时}: REPORT_FIELD("核心一级资本充足率（发行时）");
{净息差_发行时}: REPORT_FIELD("净息差（发行时）");
OutputBlock();
```

> 实测：三条件 `公司代码 + 发行日 + 到期日` 同时传入成功返回 1 行（泉州银行：不良率到期前 1.43%、发行时 1.55%、拨备覆盖 151.05%、核心一级 7.93%、净息差 2.29%）。

### 5.11 到期银行债信用评级变动（STD=true）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\银行金融机构债\到期银行金融机构债\AI一页纸_到期银行金融机构债_信用评级变动|977367229404407});
SetCodes("{债券代码}");
{债券代码}: REPORT_FIELD("债券代码");
{评级日期}: REPORT_FIELD("评级日期");
{评级变动方向}: REPORT_FIELD("评级变动方向");
OutputBlock();
```

### 5.12 存续非银债基础信息（STD=true）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\非银金融机构债\存续非银金融机构债\AI一页纸_存续非银金融机构债_基础信息|516727124777846});
SetCodes("{债券代码}");
{债券简称}: REPORT_FIELD("债券简称");
{债券代码}: REPORT_FIELD("债券代码");
{发行人名称}: REPORT_FIELD("发行人名称");
{实际控制人}: REPORT_FIELD("实际控制人");
{实际控制人类型}: REPORT_FIELD("实际控制人类型");
{票面利率}: REPORT_FIELD("票面利率(当期参考)(%)");
{估值收益率}: REPORT_FIELD("估值收益率");
{剩余期限}: REPORT_FIELD("剩余期限(年)");
{发行规模}: REPORT_FIELD("发行规模(亿元)");
{主体评级}: REPORT_FIELD("主体评级_国内评级机构(除中债资信))");
{债项评级}: REPORT_FIELD("债项评级_国内评级机构(除中资信))");
{最新与国开利差}: REPORT_FIELD("最新与国开利差");
OutputBlock();
```

> 注：若「债项评级」绑定失败，请改用元数据精确名 `债项评级_国内评级机构(除中债资信))`。

### 5.13 到期非银债基础信息（STD=true，**可用，需传到期券**）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\非银金融机构债\到期非银金融机构债\AI一页纸_到期非银金融机构债_基础信息|087160458814034});
SetCodes("{债券代码}");
{债券简称}: REPORT_FIELD("债券简称");
{债券代码}: REPORT_FIELD("债券代码");
{发行人名称}: REPORT_FIELD("发行人名称");
{估值收益率}: REPORT_FIELD("估值收益率");
{发行规模}: REPORT_FIELD("发行规模(亿元)");
{主体评级}: REPORT_FIELD("主体评级_国内评级机构(除中债资信))");
{债项评级}: REPORT_FIELD("债项评级_国内评级机构(除中债资信))");
OutputBlock();
```

> 实测：传存续券 `137514.SH` 时 `ok=true`、0 行（该报表只含到期券，属正常）。**原「报表服务请求失败」结论作废**：报表本身可调用，只要传到期非银券即可。

### 5.14 存续科创债

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\科创债\存续科创债\AI一页纸存续科创债|339799887788335});
SetCodes("{债券代码}");
{债券简称}: REPORT_FIELD("债券简称");
{债券代码}: REPORT_FIELD("债券代码");
{发行人名称}: REPORT_FIELD("发行人名称");
{科创领域}: REPORT_FIELD("科创领域");
{科创称号}: REPORT_FIELD("科创称号");
{专利数量}: REPORT_FIELD("专利数量");
{票面利率}: REPORT_FIELD("票面利率(当期)");
{估值收益率}: REPORT_FIELD("估值收益率");
{剩余期限}: REPORT_FIELD("剩余期限(行情用,年)");
{发行规模}: REPORT_FIELD("发行规模(亿元)");
{主体评级}: REPORT_FIELD("最新主体评级（国内除中债资信）");
{可比科创债利差}: REPORT_FIELD("可比科创债利差");
OutputBlock();
```

> ⚠️ 字段名陷阱：该报表「发行人代码」字段的 `column_name_cn` 实际为 `" 发行人代码 "`（**前后带空格**），直接 `REPORT_FIELD("发行人代码")` 会报 `CQL_TYPE_ERROR: 报表返回列无法唯一绑定`。**不要引用该字段**；如确需，请用 `REPORT_FIELD(" 发行人代码 ")`。

### 5.15 到期科创债

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\科创债\到期科创债\AI一页纸到期科创债|930008147975023});
SetCodes("{债券代码}");
{债券简称}: REPORT_FIELD("债券简称");
{债券代码}: REPORT_FIELD("债券代码");
{发行人名称}: REPORT_FIELD("发行人名称");
{科创称号}: REPORT_FIELD("科创称号");
{发行规模}: REPORT_FIELD("发行规模(亿元)");
{票面利率}: REPORT_FIELD("票面利率(当期)");
{发行日期}: REPORT_FIELD(" 发行日期 ");
{到期日期}: REPORT_FIELD("到期日期");
{上市首日收益率}: REPORT_FIELD("上市首日收益率");
{存续期最高收益率}: REPORT_FIELD("存续期最高收益率");
{存续期最低收益率}: REPORT_FIELD("存续期最低收益率");
OutputBlock();
```

> ⚠️ 「发行日期」的实际 `column_name_cn` 为 `" 发行日期 "`（带空格）。写 `REPORT_FIELD("发行日期")` 会绑定失败。

### 5.16 存续/到期科创债财务部分（STD=false）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\科创债\存续科创债\AI一页纸存续科创债财务部分|503474644730190});
SetReportFilter({发行人} == "{公司代码}");
{公司代码}: REPORT_FIELD("公司代码");
{资产负债率}: REPORT_FIELD("资产负债率");
{营业总收入}: REPORT_FIELD("营业总收入");
{营业收入同比增长率}: REPORT_FIELD("营业收入同比增长率");
{净利润}: REPORT_FIELD("净利润");
{净利润同比增长率}: REPORT_FIELD("净利润同比增长率");
{经营活动现金流量净额}: REPORT_FIELD("经营活动产生的现金流量净额");
{研发支出}: REPORT_FIELD("研发支出");
{研发强度}: REPORT_FIELD("研发强度");
{ROE}: REPORT_FIELD("ROE");
{总资产}: REPORT_FIELD("总资产");
{速动比率}: REPORT_FIELD("速动比率");
{利息保障倍数}: REPORT_FIELD("利息保障倍数");
{货币资金短期债务比}: REPORT_FIELD("货币资金/短期债务");
{报告期}: REPORT_FIELD("报告期");
OutputBlock();
```

到期版：路径改 `...\科创债\到期科创债\AI一页纸到期科创债财务部分|871388107529439`，filter 为 `{发行人} == "{公司代码}" AND {发行日} == "{起息日期}" AND {到期日} == "{到期日期}"`，返回字段为「资产负债率-发行前 / -到期前、营收-、净利润-、经营现金流-、总资产-」等（`ISSUE_*` 与 `MATURE_*` 两套）。

### 5.17 存续绿色债

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\绿色债\存续绿色债\AI一页纸存续绿色债|487408955865830});
SetCodes("{债券代码}");
{债券简称}: REPORT_FIELD("债券简称");
{债券代码}: REPORT_FIELD("债券代码");
{发行人名称}: REPORT_FIELD("发行人名称");
{绿债口径}: REPORT_FIELD("绿债口径");
{绿债等级}: REPORT_FIELD("绿债等级");
{绿色债券认证机构}: REPORT_FIELD("绿色债券认证机构");
{认证日期}: REPORT_FIELD("认证日期");
{募投领域}: REPORT_FIELD("募投领域");
{挂钩目标}: REPORT_FIELD("挂钩目标");
{是否符合中欧共同分类目录}: REPORT_FIELD("是否符合中欧《共同分类目录》");
{绿债环境效益}: REPORT_FIELD("绿债环境效益");
{票面利率}: REPORT_FIELD("票面利率(当期)");
{估值收益率}: REPORT_FIELD("估值收益率");
{剩余期限}: REPORT_FIELD("剩余期限(行情用,年)");
{发行规模}: REPORT_FIELD("发行规模(亿元)");
{主体评级}: REPORT_FIELD("最新主体评级-国内机构除中债资信");
{可比绿色债利差}: REPORT_FIELD("可比绿色债利差");
OutputBlock();
```

### 5.18 到期绿色债

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\绿色债\到期绿色债\AI一页纸到期绿色债|115626454629710});
SetCodes("{债券代码}");
{债券简称}: REPORT_FIELD("债券简称");
{债券代码}: REPORT_FIELD("债券代码");
{发行人名称}: REPORT_FIELD("发行人名称");
{发行规模}: REPORT_FIELD("发行规模(亿元)");
{票面利率}: REPORT_FIELD("票面利率(当期)");
{发行日期}: REPORT_FIELD("发行日期");
{到期日期}: REPORT_FIELD("到期日期");
{上市首日收益率}: REPORT_FIELD("上市首日收益率");
{存续期最高收益率}: REPORT_FIELD("存续期最高收益率");
{存续期最低收益率}: REPORT_FIELD("存续期最低收益率");
{是否实际违约}: REPORT_FIELD("是否实际违约");
{绿债环境效益}: REPORT_FIELD("绿债环境效益");
OutputBlock();
```

### 5.19 存续/到期绿色债财务部分（STD=false）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\绿色债\存续绿色债\AI一页纸_存续绿色债财务部分|503474644730190});
SetReportFilter({发行人} == "{公司代码}");
{公司代码}: REPORT_FIELD("公司代码");
{资产负债率}: REPORT_FIELD("资产负债率");
{营业总收入}: REPORT_FIELD("营业总收入");
{净利润}: REPORT_FIELD("净利润");
{经营活动现金流量净额}: REPORT_FIELD("经营活动产生的现金流量净额");
{ROE}: REPORT_FIELD("ROE");
{总资产}: REPORT_FIELD("总资产");
{速动比率}: REPORT_FIELD("速动比率");
{报告期}: REPORT_FIELD("报告期");
OutputBlock();
```

到期版：路径改 `...\绿色债\到期绿色债\AI一页纸_到期绿色债财务部分|871388107529439`，filter 为 `{发行人} == "{公司代码}" AND {发行日} == "{起息日期}" AND {到期日} == "{到期日期}"`。

## 六、RAG 文本搜索示例

```text
mx_finance_search_news:
  query = "{发行人名称} {债券简称} {标签特征} 近30天 新闻 研报 评级观点 市场讨论"

mx_finance_search_notice:
  query = "{发行人名称} {债券简称} 募集说明书 发行公告 评级报告 兑付公告 {年份}"
```

返回结构化表格：标题、摘要、发布时间、来源、跳转链接。

## 七、报表探测结论速查（2026-10 实测）

| 报表 | 报表ID | STD | 实测结论 |
|---|---|---|---|
| 债券标签 | 457922590417606 | true | 可用，逐只 SetCodes |
| AI研究员搜索 | 457922590417606 | true | 可用，逐只 SetCodes |
| 存续城投债 | 077542525591078 | true | 可用 |
| 到期城投债 | 770476112283445 | true | **可用**（字段可唯一绑定；存续券返回 0 行属正常） |
| 城投平台基本资料表 | 823827806486891 | false | 可用；filter=公司代码（不带 .FXR 后缀），多期取最新 |
| 城投债财务部分（存续） | 556585164769088 | false | **可用**；filter 加载列中文名为「发行人」 |
| 城投债财务部分（到期） | 556585164769088 | false | 可用；filter=发行人 + 到期日期 |
| 近期所属地区化债进度 | 645935680656235 | false | 可用；**必须带截止日期**，地区需本地 FILTER_ROWS |
| 存续期内所属地区化债进度 | 645935680656235 | false | 同上 |
| 估值与市场信号_债券利差 | 061066940812509 | true | **硬卡点**：加载列类型 `detime` 无效，元数据损坏，不可用 |
| AI一页纸存续银行金融机构债 | 172514974433160 | true | 可用；勿引用含空字符的「发行人代码」 |
| AI一页纸_存续银行债财务部分 | 872852055351144 | false | 可用；filter=公司代码 |
| AI一页纸到期银行金融机构债 | 930522266378689 | true | 可用 |
| AI一页纸_到期银行债财务部分 | 869534090566691 | false | **可用**；filter=公司代码 + 发行日 + 到期日 |
| AI一页纸_到期银行金融机构债_信用评级变动 | 977367229404407 | true | 可用 |
| AI一页纸_存续非银金融机构债_基础信息 | 516727124777846 | true | 可用 |
| AI一页纸_到期非银金融机构债_基础信息 | 087160458814034 | true | **可用**（须传到期券；原「服务失败」作废） |
| AI一页纸存续科创债 | 339799887788335 | true | 可用；勿引用带空格的「发行人代码」 |
| AI一页纸到期科创债 | 930008147975023 | true | 可用；「发行日期」实际名带空格 |
| AI一页纸存续科创债财务部分 | 503474644730190 | false | 可用；filter=发行人 |
| AI一页纸到期科创债财务部分 | 871388107529439 | false | 可用；filter=发行人 + 发行日 + 到期日 |
| AI一页纸存续绿色债 | 487408955865830 | true | 可用 |
| AI一页纸到期绿色债 | 115626454629710 | true | 可用 |
| AI一页纸_存续绿色债财务部分 | 503474644730190 | false | 可用；filter=发行人 |
| AI一页纸_到期绿色债财务部分 | 871388107529439 | false | 可用；filter=发行人 + 发行日 + 到期日 |
