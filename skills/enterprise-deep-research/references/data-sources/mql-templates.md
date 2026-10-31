# 固化 MQL 查询模板

本文件是 `enterprise-deep-research` 的固定 MQL 样例索引。模板按 MQL Runtime 2.6.0 的实际执行结果整理；版本和口径一致时只替换变量，不重新生成整段 MQL。若记录与当前 MQL 元数据或真实返回冲突，以实际可绑定字段为准，核对业务含义和单位后修正并重新验证；不能为执行成功而删掉必需条件、更换指标含义。

## 运行规则

- 先识别企业的 `ORG_CODE`、发行人代码 `<ORG_CODE>.FXR`、股票代码和日期，再读取当前板块对应的模板键。
- 用 `scripts/render_mql_template.py` 渲染固定模板。模板脚本的 `--json` 输出是 ASCII JSON 字符串，必须先 JSON 解码，再将解码后的字符串传给 `Execute_MQL`，不能把 PowerShell 的显示文本直接复制到 MQL 工具。
- 固定模板执行成功且返回字段满足板块要求后，直接使用结果；不得为了补列再拼接另一个候选的行。
- 固定模板失败时，保留用户指定的主路径，按同业务候选规则调用 `Search_Context`；只有所有同业务 MQL 候选失败后才使用 Python REST 兜底。
- `mql-verification.json` 保存执行证据，`latest_template_checks` 为本轮复测，历史失败不覆盖新结果。脚本仅从明确白名单的成功历史记录或内置常量渲染模板，不加载任意成功查询。`ok=true` 不等于业务完整，零行、缺列或口径不满足须分别记录。

## 模板参数

| 参数 | 用途 |
|---|---|
| `<ORG_CODE>` | 企业机构代码，不含 `.FXR` |
| `<ISSUER_CODE>` | 发行人代码，通常为 `<ORG_CODE>.FXR` |
| `<STOCK_CODE>` | 股票代码，含市场后缀 |
| `<SYSTEM_DATE>` | 执行时系统日 |
| `<START_DATE>` / `<END_DATE>` | 对范围型报表为查询区间；其他模板中 END_DATE 可表示指定截止日，以该报表语义为准 |
| `<REPORT_DATE>` | 指定报告期 |
| `<IS_HISTORY>` | 司法汇总表当前/历史标记，分别为 `0` 或 `1` |
| `<TRADE_DATE>` | 样本关系和样本估值共同的定价日 |
| `<SAMPLE_CODES_JSON>` / `<SAMPLE_TYPES>` | 同一顺序的债券代码数组及逐券类型串，由实际样本关系产生 |

脚本参数为 `--org-code`、`--issuer-code`、`--stock-code`、`--system-date`、`--start-date`、`--end-date`、`--report-date`、`--period-start`、`--trade-date`、`--is-history`。样本估值使用 `--samples-json` 或 `--samples-file`，内容为实际取得的 `[[债券代码, 样本类型], ...]`；Windows 命令行优先传已保存的 JSON 数据文件，避免引号丢失。不要替换报表 ID。主体利差的 `StartDate/EndDate` 与 `TDATE` 不共用参数，后者是存续债自身截止口径，不是查询时间范围。

## 模板索引

下列模板键已经固化在 `scripts/render_mql_template.py`；对应成功核验记录由脚本按键读取，主要股东、司法、发行概述和发行人曲线样本模板直接固化在脚本中。

| 模块 | 模板键 | 固定内容 | 状态 |
|---|---|---|---|
| 企业类型/基本信息 | `org_info_all`、`basic_noid_cn`、`industry_fixed`、`urban_filter`、`issuer_filter` | 机构基本信息、基本信息、行业、省份及类型筛选 | 已执行 |
| 股东情况 | `shareholder_main`、`shareholder_partial`、`related_noid` | 主要股东明细、股东股权摘要、关联交易 | 主路径已执行；摘要和关联交易已执行 |
| 经营状况 | `operation_product_fixed`、`operation_region_fixed`、`operation_other_entity_chart` | 产品、地区和其他企业主营构成 | 已执行 |
| ESG | `esg_scope`、`esg_summary`、`esg_detail_fixed`、`esg_level1` | ESG 范围、汇总、构成与一级明细 | 范围、构成和一级明细有数据；esg_summary 样本零行 |
| 两类财务状况 | `finance_metrics`、`finance_chart`、`credit_full` | 核心指标、六年图表序列、信用分析 | 已执行子集；财务摘要主表仍存在合并类型重名 |
| 定价分析 | `curve_types`、`curve_samples`、`curve_valuation` | 发行人曲线债券类型、样本券对应关系、样本估值 | 样本关系和样本估值已执行；全市场补点和最终拟合仍按板块规则核验 |
| 科创能力 | `sci_tech_profile`、`patents`、`rd_metric`、`staff` | 行业与称号、专利、研发费用、研发人员 | 已执行子集；产权三张表及研发费用与人员指定表仍缺可用元数据 |
| 偿债分析 | `solvency_key`、`credit_full`、`solvency_debt`、`shareholder_partial` | 关键指标、信用、负债结构、股东 | 已执行子集；完整发行与到期仍阻塞 |
| 信用分析 | `credit_full`、`credit_noid` | 指定主表19列及部分字段候选 | 已执行；按实际非空字段生成表格 |
| 发行概述 | `issuance_fixed` | 存续债券发行一览 | 已执行12列；信用主体未绑定 |
| 司法风险 | `judicial_dishonest`、`judicial_executed_main`、`judicial_executed_backup`、`judicial_restricted`、`judicial_termination` | 四张司法汇总表及被执行人备选 | 主路径/备选按实测状态执行 |
| 重点关注 | 无 | 仅使用前序分析结果 | 不发起 MQL |

`定价分析（城投）`的区域对比、区域利差和主体利差尚未形成全部可执行固定模板，必须按该板块文档通过 `Search_Context` 核验后执行，不得复制失败记录中的 MQL。

## 新增固化模板与验证边界（2026-09-30）

以下模板已写入 `scripts/render_mql_template.py`，运行时只替换企业代码和日期，并已用 MQL Runtime 2.6.0 实测通过：

### 股东明细表

主路径为用户确认的完整“主要股东”路径。展示列使用 `股东名称`、`持有数量(股)`、`持有比例(%)`、`股东是否为发行人`；其中展示列 `持有数量(股)` 映射报表返回列 `持有数量/金额`。贵州茅台 `10002602`、`2026-06-30` 返回 11 行，接口返回的 `合计` 行由整理逻辑置于表格末行。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\股东股权\股东明细\股东明细\主要股东|789604172179402});
SetReportFilter({发行人代码} == "<ORG_CODE>" AND {截止日期} == "<END_DATE>");
{股东名称}: REPORT_FIELD("股东名称");
{持有数量(股)}: REPORT_FIELD("持有数量/金额");
{持有比例(%)}: REPORT_FIELD("持有比例(%)");
{股东是否为发行人}: REPORT_FIELD("股东是否为发行人");
Sort({持有比例(%)}, "DESC");
Head(15);
OutputBlock();
```

### 信用分析全字段

信用分析主路径必须同时提供 `公司代码` 和 `截止日期`，当前日期使用系统日。`货币资金/短期债务` 的返回列名含一个实际 NUL 字符，脚本模板已按 Runtime 元数据保留该名称。民生银行实测返回 1 行、19 个输出列。

### 偿债统计

`solvency_statistics_diagnostic` 只用于诊断两列返回，不能用于正式发行与到期图表。加入“到期年份”后触发日期格式错误，发行序列和六类债券排除条件也尚未验证。脚本拒绝正式键 `solvency_statistics`；不能将删掉日期列的查询标记为完整通过。详见 [偿债分析](solvency.md)。

### 科创基本信息

`sci_tech_profile` 固定使用 `企业F9_机构基本信息|148758350698551`，读取 `行业`、`省份`、`科创称号`、`科创领域`。芯碁微装 `10000069733` 实测返回 1 行。产权数量、年度变化和商标分布仍必须按动态字段规则核验，不能用该基本信息模板替代。

### 未固化为可执行模板的链路

债券发行人拟合曲线的多点输入、发行人行情监控，以及城投区域对比、区域利差、主体利差，当前仅完成部分元数据或单步候选验证，仍由 `Search_Context` 按同业务候选动态核验；脚本会明确拒绝将这些未通过键当作固定 MQL 执行模板。旧 `ok=false` 记录只作失败审计，不得加载为模板。

## 完整样例

### 发行概述：已执行的存续债发行一览

该模板已用中国民生银行发行人代码 `10002264`、系统日 `2026-09-30` 执行成功，返回 58 行。`信用主体`目前未被 Runtime 暴露为可绑定返回列，不用发行人名称冒充；其余字段按发行概述板块白名单读取。

```mql
ReportBlock(#1, {Choice报表\报表指标\服务端\妙想服务\量化查数\债券\企业F9\发行一览\发行债券|RPT_CUSTOM_BOND_BS_SAMEISSUER});
SetReportFilter(({发行人代码} == "<ORG_CODE>") AND ({集团系} == "0") AND ({跨市场去重排序} == 1) AND ({到期日期} >= "<SYSTEM_DATE>") AND ({债券类型} <> "同业存单"));
{债券代码}: REPORT_FIELD("债券代码带后缀");
{债券简称}: REPORT_FIELD("债券简称");
{债券类型}: REPORT_FIELD("证券类别");
{债券余额}: REPORT_FIELD("当前余额(亿)");
{币种}: REPORT_FIELD("币种");
{发行日期}: REPORT_FIELD("发行日期");
{到期日期}: REPORT_FIELD("到期日期");
{剩余期限}: REPORT_FIELD("剩余期限");
{最新债项评级}: REPORT_FIELD("债券评级");
{最新主体评级}: REPORT_FIELD("主体评级");
{票面利率}: REPORT_FIELD("票面利率(发行参考利率)");
{所属集团}: REPORT_FIELD("所属集团");
OutputBlock();
```

### 财务状况：已执行的核心指标

该模板使用发行人代码和报告期，包含商业银行专属指标，只对已核验行业使用，不得直接用于一般企业；`净利润`也不能改名为归母净利润。图表优先使用下方已验证的同业务 `finance_chart` 候选，取六年年报、展示五年；额外一年只用于首年同比。

```mql
CrossSectionBlock(#1, {EM_CODE});
SetCodes(["<ISSUER_CODE>"]);
{资产总计}: {Choice指标\发行人\企业全部指标\财务与分析\财务数据(大陆准则,标准)\商业银行\资产负债表\资产\资产总计|100000000010127}({报告期} = "<REPORT_DATE>", {报告类型} = "合并报表");
{负债合计}: {Choice指标\发行人\企业全部指标\财务与分析\财务数据(大陆准则,标准)\商业银行\资产负债表\负债\负债合计|100000000011173}({报告期} = "<REPORT_DATE>", {报告类型} = "合并报表");
{净利润}: {Choice指标\发行人\企业全部指标\财务与分析\财务数据(大陆准则,标准)\商业银行\利润表\净利润|100000000011098}({报告期} = "<REPORT_DATE>", {报告类型} = "合并报表");
{营业总收入}: {Choice指标\发行人\企业全部指标\财务与分析\财务数据(大陆准则,标准)\一般企业\利润表\营业总收入|100000000010015}({报告期} = "<REPORT_DATE>", {报告类型} = "合并报表");
{经营现金净流量}: {Choice指标\发行人\企业全部指标\财务与分析\财务数据(大陆准则,标准)\一般企业\现金流量表\经营活动产生的现金流量\经营活动产生的现金流量净额|100000000009247}({报告期} = "<REPORT_DATE>", {报告类型} = "合并报表");
OutputBlock();
```

### 经营状况：产品主营构成

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\主营构成\主营构成_沪深});
SetReportFilter(({机构代码} == "<ORG_CODE>") AND ({分布类型} == "产品") AND ({报告日期} >= "<START_DATE>") AND ({报告日期} <= "<END_DATE>"));
{实际披露项目名称}: REPORT_FIELD("实际披露项目名称");
{分布类型}: REPORT_FIELD("分布类型");
{本期主营业务收入}: REPORT_FIELD("本期主营业务收入");
{本期主营业务成本}: REPORT_FIELD("本期主营业务成本");
{占主营业务收入比例}: REPORT_FIELD("占主营业务收入比例");
{是否最新报告期}: REPORT_FIELD("是否最新报告期");
{计算方式代码}: REPORT_FIELD("计算方式代码");
{报告日期}: REPORT_FIELD("报告日期");
{报告年度}: REPORT_FIELD("报告年度");
{项目编码}: REPORT_FIELD("项目编码");
OutputBlock();
```

产品查询无有效行时，才渲染同结构的地区模板；地区与产品不能混合求和。详细字段白名单以 [operation.md](operation.md) 为准。

### 司法风险：失信被执行人

四张司法汇总表都使用同一套变量替换方式。当前 Runtime 2.6.0 支持一次 `IN` 查询 `TYPE/关系类型=1、2、3、4`；只有具体报表拒绝集合条件时才拆成四次单值查询。当前和历史需要分别执行，将 `<IS_HISTORY>` 替换为 `0`、`1`。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9(发行人+工商企业)\企业一页纸\司法风险汇总信息\失信被执行人汇总|081751076337787});
SetReportFilter({公司代码} == "<ORG_CODE>" AND {是否历史信息} == "<IS_HISTORY>" AND IN({关系类型}, ["1", "2", "3", "4"]));
{关系类型}: REPORT_FIELD("关系类型");
{对象}: REPORT_FIELD("失信被执行人");
{当前案件数}: REPORT_FIELD("当前案件数");
{历史案件数}: REPORT_FIELD("历史案件数");
{当前执行标的}: REPORT_FIELD("当前执行标的（万元）");
{历史执行标的}: REPORT_FIELD("历史执行标的（万元）");
OutputBlock();
```

### 司法风险：被执行人备选

被执行人新主路径 `.../被执行人汇总|006194229816016` 曾被上游服务拒绝，2026-09-30 本轮用阳光城复测当前和历史均已通过，仍须首先使用主路径。下面备选也已通过，仅主路径本次失败或关键结果不可用时使用；渲染器本身不调用接口，也不自动切换。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\司法风险汇总信息\被执行人\被执行人汇总|024220940284594});
SetReportFilter({公司代码} == "<ORG_CODE>" AND {是否历史信息} == "<IS_HISTORY>" AND IN({关系类型}, ["1", "2", "3", "4"]));
{关系类型}: REPORT_FIELD("关系类型");
{对象}: REPORT_FIELD("被执行人");
{当前案件数}: REPORT_FIELD("当前案件数");
{历史案件数}: REPORT_FIELD("历史案件数");
{当前执行标的}: REPORT_FIELD("当前执行标的（万元）");
{历史执行标的}: REPORT_FIELD("历史执行标的（万元）");
OutputBlock();
```

### 司法风险：限制高消费与终本案件

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9(发行人+工商企业)\企业一页纸\司法风险汇总信息\限制高消费汇总|868338831875985});
SetReportFilter({公司代码} == "<ORG_CODE>" AND {是否历史信息} == "<IS_HISTORY>" AND IN({关系类型}, ["1", "2", "3", "4"]));
{关系类型}: REPORT_FIELD("关系类型");
{对象}: REPORT_FIELD("限消令对象");
{当前案件数}: REPORT_FIELD("当前案件数");
{历史案件数}: REPORT_FIELD("历史案件数");
OutputBlock();
```

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9(发行人+工商企业)\企业一页纸\司法风险汇总信息\终本案件汇总|349894282139442});
SetReportFilter({公司代码} == "<ORG_CODE>" AND {是否历史信息} == "<IS_HISTORY>" AND IN({关系类型}, ["1", "2", "3", "4"]));
{关系类型}: REPORT_FIELD("关系类型");
{对象}: REPORT_FIELD("被执行人");
{当前案件数}: REPORT_FIELD("当前案件数");
{历史案件数}: REPORT_FIELD("历史案件数");
{当前执行总金额}: REPORT_FIELD("当前执行总金额（万元）");
{历史执行总金额}: REPORT_FIELD("历史执行总金额（万元）");
{当前未履行总金额}: REPORT_FIELD("当前未履行总金额（万元）");
{历史未履行总金额}: REPORT_FIELD("历史未履行总金额（万元）");
{当前未履行比例}: REPORT_FIELD("当前未履行比例(%)");
{历史未履行比例}: REPORT_FIELD("历史未履行比例(%)");
OutputBlock();
```

### 主要股东主路径：已执行的十大股东明细

用户确认的 `RPT_BOND_GQJG_ISHOLDER` 完整路径已按实际字段执行成功。该报表一次返回十大股东及接口提供的合计行；模板只替换发行人代码和截止日期，不改写路径、字段、排序和截取逻辑。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\股东股权\股东明细\股东明细\主要股东|789604172179402});
SetReportFilter({发行人代码} == "<ORG_CODE>" AND {截止日期} == "<END_DATE>");
{股东名称}: REPORT_FIELD("股东名称");
{持有数量/金额}: REPORT_FIELD("持有数量/金额");
{持有比例(%)}: REPORT_FIELD("持有比例(%)");
{股东是否为发行人}: REPORT_FIELD("股东是否为发行人");
Sort({持有比例(%)}, "DESC");
Head(15);
OutputBlock();
```

该主路径已用贵州茅台发行人代码 `10002602`、截止日期 `2026-06-30` 验证，执行耗时约 646 毫秒，返回 11 行、4 个字段，包含合计和十名股东。整理时将接口返回的合计行移到最后，表格展示为：股东名称、持有数量(股)、持有比例(%)、股东是否为发行人；其中 `股东是否为发行人=1` 显示“是”，空值显示“-”。不得自行把明细相加替代接口合计值。

若本次主路径召回失败、字段不能绑定或执行失败，再使用同业务候选；主路径和备选不得混合拼接：

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9(发行人+工商企业)\关联关系\主要股东\主要股东|436679648370810});
SetReportFilter({公司代码} == "<ORG_CODE>");
{股东名称}: REPORT_FIELD("股东名称");
{持有数量/金额}: REPORT_FIELD("持有数量/金额");
{持有比例(%)}: REPORT_FIELD("持有比例(%)");
{公司代码}: REPORT_FIELD("公司代码");
OutputBlock();
```

该备选已用蚂蚁科技集团股份有限公司返回 11 行。若备选不返回 `股东是否为发行人`，该列只能显示“-”，不得根据股东名称推断。


### 财务图表：六年取数、五年展示

模板键 `finance_chart`。主财务摘要失败后才使用此候选，保留六个完整年报，2020年等示例日期不得硬编码。`每股经营现金流`不是现金流总额。

```mql
ReportBlock(#1, {Choice报表\报表指标\服务端\妙想服务\对接API\F10_财务分析_主要财务指标|594237169895505});
SetCodes(["<STOCK_CODE>"]);
SetReportFilter(({报告期} >= "<START_DATE>") AND ({报告期} <= "<END_DATE>"));
{公司代码}: REPORT_FIELD("公司代码");
{证券代码(带后缀)}: REPORT_FIELD("证券代码(带后缀)");
{机构类型}: REPORT_FIELD("机构类型");
{币种}: REPORT_FIELD("币种");
{报告期}: REPORT_FIELD("报告期");
{报告期标签}: REPORT_FIELD("报告期标签");
{报告期类型}: REPORT_FIELD("报告期类型");
{营业总收入}: REPORT_FIELD("营业总收入");
{营业总收入同比增长}: REPORT_FIELD("营业总收入同比增长");
{归属净利润}: REPORT_FIELD("归属净利润");
{归属净利润同比增长}: REPORT_FIELD("归属净利润同比增长");
{资产负债率}: REPORT_FIELD("资产负债率");
{净资产收益率(加权)}: REPORT_FIELD("净资产收益率(加权)");
{每股经营现金流}: REPORT_FIELD("每股经营现金流");
OutputBlock();
```

### ESG：一级指标明细

模板键 `esg_level1`。按实际证券及更新日期取数，选择与汇总同日期、同机构的有效明细并去重。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\API专题报表函数\A股\F9\ESG\ESG-明细弹窗接口|545851408591004});
SetCodes(["<STOCK_CODE>"]);
SetReportFilter({更新日期} <= "<END_DATE>");
{证券代码带后缀}: REPORT_FIELD("证券代码带后缀");
{所属子项中文}: REPORT_FIELD("所属子项中文");
{一级指标名称}: REPORT_FIELD("一级指标名称");
{一级指标得分}: REPORT_FIELD("一级指标得分");
{更新日期}: REPORT_FIELD("更新日期");
OutputBlock();
```

### 发行人曲线：样本关系

模板键 `curve_samples`。输出成对的代码和类型，完整传给下一个模板。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\发行人曲线\样本券对应关系\发行人曲线_样本券|873037266287012});
SetReportFilter(({原始发行人代码} == "<ISSUER_CODE>") AND ({定价日} == "<TRADE_DATE>"));
{样本券类型}: REPORT_FIELD("样本券类型");
{样本券代码}: REPORT_FIELD("样本券代码");
OutputBlock();
```

### 发行人曲线：样本估值

模板键 `curve_valuation`。`<SAMPLE_CODES_JSON>`为排序后的实际债券代码JSON数组；`<SAMPLE_TYPES>`为完全相同顺序、相同长度的类型串，不是去重类型集合。渲染器接收成对记录并完成排序对齐。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\发行人曲线\条件筛选-债券列表\发行人曲线_相似债_估值|025324135305196});
SetCodes(<SAMPLE_CODES_JSON>);
SetReportFilter(({交易日期} == "<TRADE_DATE>") AND ({通用类型1} == "<SAMPLE_TYPES>"));
{债券代码}: REPORT_FIELD("债券代码");
{样本类型编码}: REPORT_FIELD("样本类型编码");
{样本类型}: REPORT_FIELD("样本类型");
{定价日}: REPORT_FIELD("定价日");
{剩余期限(中债)}: REPORT_FIELD("剩余期限(中债)");
{中债估值(推荐)}: REPORT_FIELD("中债估值(推荐)");
{债券简称}: REPORT_FIELD("债券简称");
{债项评级}: REPORT_FIELD("债项评级");
{东财债券分类}: REPORT_FIELD("东财债券分类");
{东财债券分类编码}: REPORT_FIELD("东财债券分类编码");
{到期日}: REPORT_FIELD("到期日");
{发行日}: REPORT_FIELD("发行日");
{发行规模}: REPORT_FIELD("发行规模");
{债券余额}: REPORT_FIELD("债券余额");
{上一日成交收益率}: REPORT_FIELD("上一日成交收益率");
{募集方式}: REPORT_FIELD("募集方式");
{YY评级}: REPORT_FIELD("YY评级");
{YY行业}: REPORT_FIELD("YY行业");
{票面利率}: REPORT_FIELD("票面利率");
OutputBlock();
```


## 验证状态

2026-09-30 使用 MQL Runtime 2.6.0 完成的代表性验证：

- 固定模板批量验证：机构基本信息、基本信息、行业、产品/地区主营构成、ESG、财务核心指标、发行人债券类型、专利/研发/员工、偿债关键指标、负债结构和信用分析模板均通过语法、字段绑定和取数执行；零行仅按企业和日期口径记录为空。
- 主要股东明细：`RPT_BOND_GQJG_ISHOLDER` 主路径使用贵州茅台 `10002602` 和 `2026-06-30` 验证通过，返回 11 行、4 个字段；合计行由接口返回，整理后置于表格末行。
- 发行概述：`RPT_CUSTOM_BOND_BS_SAMEISSUER` 主样例通过，返回 58 行、12 个输出字段；`信用主体`仍是未确认字段，不在模板中冒充绑定。
- 司法风险：四张主表及被执行人备选，当前/历史共10次查询均通过；请求关系类型1/2/3/4，阳光城实际均返回1/3/4，不将未返回的2解释为零或声称四类都有数据。
- 城投定价的区域对比、区域利差和主体利差没有全部形成可执行固定模板，仍按 `Search_Context` 动态核验，不得从失败记录复制 MQL。
