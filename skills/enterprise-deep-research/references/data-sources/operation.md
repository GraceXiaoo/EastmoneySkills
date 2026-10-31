# 经营状况数据源

状态：沪深主体产品、地区两种口径均已返回数据；蚂蚁科技集团股份有限公司的“其他企业”产品口径已实测通过（2026-09-24），可返回图表所需的三项产品收入。执行编号及边界见 [MQL核验记录](mql-verification.json)。本文件中的 MQL 使用 MQL Runtime 实际绑定字段名；英文物理列名只用于来源映射和 REST。

## 数据来源与优先级

用户路径：`/Choice金融终端/企业F9/企业一页纸/主营构成`。报表选择必须按企业实体类型和当次 `Search_Context` 元数据确定，不能把沪深主体报表套用于所有企业：沪深主体使用 `RPT_HSF9_FN_MAINOPBUSINESS_NORMAL`；其它企业/发行人使用 `RPT_ORGF9_FN_MAINOPBUSINESS`；下方路径均已按相应主体验证。

1. 优先按产品取数：`分布类型 == "产品"`。
2. 只有产品查询正常完成且无有效主营数据时，才改为 `分布类型 == "地区"` 重查；查询报错不能当作产品无数据。
3. 产品有数据时，不将地区结果混入分析包。本次地区查询仅用于验证备用链路。
4. 发行人或其它非沪深主体优先使用 `主营构成-其他企业|RPT_ORGF9_FN_MAINOPBUSINESS`，过滤 `机构代码=<ORG_CODE>`；蚂蚁科技集团股份有限公司实测代码为 `10426109`，2020-06-30 返回数字金融科技平台、数字支付与商家服务、创新业务及其他三项产品。

**实测纠错**：`Type` 是物理列，对应 MQL Runtime 绑定字段 `分布类型`，实际返回字符串“产品”“地区”。`BELONG_TYPE_CODE` 对应 `分布类型编码` 才返回“2”“3”，但该编码不是已暴露的加载过滤列。原 `Type == "2"/"3"` 条件导致错误空结果，禁止继续使用。

`RPT_USF9_INFO_PRODUCTSTRUCTURE` 已在 MQL 召回为**美股**主营构成报表，不是所有企业的通用表。美股应继续按产品报表、地区报表顺序核对；港股及其它企业用当次元数据确认的相应市场报表，不把沪深验证结果泛化到所有市场。

### 其他企业/发行人 MQL 模板

该模板适用于 `Search_Context` 返回“主营构成-其他企业”且 `reportFilterColumns` 包含 `机构代码`、`分布类型`、`是否最新报告期`、`计算方式代码` 的主体。`项目编码`属于报表返回列，不属于加载列，不能放入 `SetReportFilter`；在返回列声明后用 `FILTER_ROWS` 排除“合计”项目。`计算方式代码 == "0"` 保留普通报表，排除同比增长率等派生行。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\主营构成\主营构成-其他企业|RPT_ORGF9_FN_MAINOPBUSINESS});
SetReportFilter(({机构代码} == "<ORG_CODE>") AND ({分布类型} == "产品") AND ({是否最新报告期} == "1") AND ({计算方式代码} == "0"));
{实际披露项目名称}: REPORT_FIELD("实际披露项目名称");
{分布类型}: REPORT_FIELD("分布类型");
{币种}: REPORT_FIELD("币种");
{币种中文}: REPORT_FIELD("币种中文");
{本期主营业务收入}: REPORT_FIELD("本期主营业务收入");
{本期主营业务成本}: REPORT_FIELD("本期主营业务成本");
{占主营业务收入比例}: REPORT_FIELD("占主营业务收入比例");
{是否最新报告期}: REPORT_FIELD("是否最新报告期");
{计算方式代码}: REPORT_FIELD("计算方式代码");
{计算方式类型}: REPORT_FIELD("计算方式类型");
{报告日期}: REPORT_FIELD("报告日期");
{报告年度}: REPORT_FIELD("报告年度");
{报告期类型}: REPORT_FIELD("报告期类型");
{项目编码}: REPORT_FIELD("项目编码");
FILTER_ROWS({项目编码} <> "999");
OutputBlock();
```

蚂蚁科技集团股份有限公司的验证结果（2020-06-30，人民币）：数字金融科技平台收入 45,972,489,000 元，数字支付与商家服务收入 26,011,490,000 元，创新业务及其他收入 544,366,000 元；换算为万元后分别为 4,597,248.90、2,601,149.00、54,436.60。三项合计行不进入图表，收入占比分别使用返回的 `占主营业务收入比例`。该主体的营业成本返回空值时，仍生成表格，营业成本列显示 `-`，不得因成本为空而放弃收入图表。

## MQL 模板

读取全部 26 个实际字段。默认最近 5 个年度报告期或可返回的最近多期数据；模板日期按运行时窗口替换，用户指定范围优先。查询结果保留报告期和计算方式，避免将同一期间不同计算方式的行重复求和。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\主营构成\主营构成_沪深});
SetReportFilter(({机构代码} == "<ORG_CODE>") AND ({分布类型} == "产品") AND ({报告日期} >= "<START_DATE>") AND ({报告日期} <= "<END_DATE>"));
{实际披露项目名称}: REPORT_FIELD("实际披露项目名称");
{分布类型编码}: REPORT_FIELD("分布类型编码");
{币种(英文)}: REPORT_FIELD("币种(英文)");
{币种(中文)}: REPORT_FIELD("币种(中文)");
{本期毛利率}: REPORT_FIELD("本期毛利率");
{是否最新报告期}: REPORT_FIELD("是否最新报告期");
{本期主营业务成本}: REPORT_FIELD("本期主营业务成本");
{本期主营业务收入}: REPORT_FIELD("本期主营业务收入");
{本期主营业务利润}: REPORT_FIELD("本期主营业务利润");
{占主营业务成本比例}: REPORT_FIELD("占主营业务成本比例");
{占主营业务收入比例}: REPORT_FIELD("占主营业务收入比例");
{占主营业务利润比例}: REPORT_FIELD("占主营业务利润比例");
{计算方式代码}: REPORT_FIELD("计算方式代码");
{计算方式类型}: REPORT_FIELD("计算方式类型");
{机构代码}: REPORT_FIELD("机构代码");
{机构名称}: REPORT_FIELD("机构名称");
{报告期编码}: REPORT_FIELD("报告期编码");
{报告日期}: REPORT_FIELD("报告日期");
{报告期类型}: REPORT_FIELD("报告期类型");
{报告年度}: REPORT_FIELD("报告年度");
{证券代码}: REPORT_FIELD("证券代码");
{证券内码}: REPORT_FIELD("证券内码");
{证券简称}: REPORT_FIELD("证券简称");
{项目编码}: REPORT_FIELD("项目编码");
{标准披露项目名称}: REPORT_FIELD("标准披露项目名称");
{分布类型}: REPORT_FIELD("分布类型");

OutputBlock();
```

地区回退只将上面的 `分布类型 == "产品"` 换为 `分布类型 == "地区"`，其余字段及日期窗口保持一致。

## 整理与隔离

仅形成经营状况专属 `block_data_package`，只传入 `references/analysis-prompts/operation.md`。保留产品或地区、报告期、收入、成本、利润、毛利率、构成比例、币种；空值不变为零。对“其他企业”报表，先筛选 `是否最新报告期=1`、`计算方式代码=0`，再用 `FILTER_ROWS` 排除项目编码 `999` 的合计行；不得把同比增长率行或合计行混入图表。成本为空时保留该字段的空值，由表格渲染为 `-`，不能将其改成 0。切换地区时在 notes 写明产品口径成功但无有效数据。不得混入其它板块原始数据。

经营状况组件在文字分析完成后从该独立数据包生成，使用最新报告期的单一有效口径；产品口径有数据时不得混入地区口径。组件包含主营业务收入构成环状图及 Markdown 明细表。整理出真实分类值后，须在正文生成过程中直接请求“生成环状图”，并随请求提供分类名称、营业收入金额、占比、单位和报告期，不能仅期待 Markdown 表格触发图形。环状图的扇区值只传营业收入金额（万元），占比只传作标签和浮窗显示字段；标签中只展示一次百分比，浮窗不得将同一百分比重复放在括号内外。环状图优先使用 `占主营业务收入比例`，否则按同币种收入金额计算构成并注明按收入金额整理。明细表请求“生成表格”，固定展示产品名称、营业收入(万元)、营业成本(万元)，并以 Markdown 表格格式输出；产品名称对应实际披露项目名称，金额对应本期主营业务收入和本期主营业务成本。金额单位及币种以 MQL 返回元数据为准，只有可可靠整理成人民币万元时才使用“万元”列值，不做未经数据支持的汇率换算。图表及表格的项目、报告期、口径和币种必须来自本板块实际返回值。

#### `{{资讯}}` mx-finance-search 查询

经营状况板块的 `{{资讯}}` 必须使用 `mx-finance-search`，query 格式固定为：

```text
<企业全名> 相关资讯 最新动态
```

示例：

```text
中国民生银行股份有限公司 相关资讯 最新动态
```

资讯结果整理为当前板块专属 `block_news_package`，只传入 `operation.md` 的 `{{资讯}}`。优先保留与主营业务、商业模式、业务拓展、网点/产品/客户结构、经营效率、成本变化和近期经营动态相关的公告、研报和新闻；不得将该资讯包传给其它板块。

`block_news_package` 登记要求：

```json
{
  "block_name": "经营状况",
  "prompt_file": "references/analysis-prompts/operation.md",
  "news_queries": [
    {
      "query": "<企业全名> 相关资讯 最新动态",
      "tool": "mx-finance-search",
      "purpose": "主营业务、商业模式、经营动态和近期舆情补充"
    }
  ],
  "sources": [
    {
      "block": "经营状况",
      "placeholder": "{{资讯}}",
      "path": "mx-finance-search",
      "dataset": "<企业全名> 相关资讯 最新动态",
      "status": "ok"
    }
  ]
}
```

#### Python REST 兜底

仅当经营状况板块正式 MQL 主路径、已登记或动态发现的同业务候选均失败、超时或关键字段缺失时，才允许使用下方主营构成表作为 Python REST 兜底模板。兜底也必须遵守“产品优先、产品为空才用地区”的口径顺序。其他企业/发行人的 MQL 主路径已验证；其 REST 兜底仅作应急尝试，若接口返回空结果不得视为主营业务为空，也不得覆盖 MQL 已取得的数据。

```text
# 主营构成：按产品/业务
reportName=RPT_USF9_INFO_PRODUCTSTRUCTURE
columns=ALL
filter=(ORG_CODE="<ORG_CODE>")
sortColumns=REPORT_DATE&sortTypes=-1&pageNumber=1&pageSize=200&source=choice&client=SW

# 主营构成：按地区，仅产品口径为空时使用
reportName=RPT_USF9_INFO_AREASTRUCTURE
columns=ALL
filter=(ORG_CODE="<ORG_CODE>")
sortColumns=REPORT_DATE&sortTypes=-1&pageNumber=1&pageSize=200&source=choice&client=SW
```

Python 兜底结果必须拆成经营状况板块自己的 `block_data_package`，`placeholder` 标记为 `{{数据}}`。若产品口径有数据，不得再把地区口径混入；若产品口径为空且地区口径有数据，最终传入 prompt 的 `datasets[]` 只保留地区口径数据，并在来源登记中记录切换原因。
已验证沪深 REST 与 MQL 同源，不能套用美股表：

```text
reportName=RPT_HSF9_FN_MAINOPBUSINESS_NORMAL
columns=ALL
filter=(ORG_CODE="<ORG_CODE>")(Type="产品")(REPORT_DATE>='<START_DATE>')(REPORT_DATE<='<END_DATE>')
sortColumns=REPORT_DATE&sortTypes=-1&pageNumber=1&pageSize=200&source=choice&client=SW
```

产品正常完成但无有效指标时才改 `Type="地区"`，异常不能触发地区回退。必须按 count 翻页取完整记录；只保留当前板块字段和原始币种。

美股仍按 `RPT_USF9_INFO_PRODUCTSTRUCTURE`、`RPT_USF9_INFO_AREASTRUCTURE` 的顺序发现和核对字段，不能据沪深样本宣称已通过。港股/其它市场未验证的 Python 模板应返回明确失败，不猜报表或套用美股。

其他企业/发行人 REST 兜底如需尝试，使用 `RPT_ORGF9_FN_MAINOPBUSINESS`，并按接口实际字段保留 `BELONG_TYPE`、`CURRENCY`、`CURRENCY_CN`、`ACT_REPORT_NAME`、`MAIN_BUSINESS_INCOME`、`MAIN_BUSINESS_COST`、`MBI_RATIO`、`REPORT_DATE`、`IS_MAXREPORTDATE`、`METHOD_CODE`、`STD_CLASSIFY_CODE` 等字段；该接口的产品优先和最新普通报表过滤以 MQL 已验证条件为准。当前蚂蚁集团的 REST 兜底未返回有效记录，因此不能将 REST 空结果作为业务事实。

Python 兜底结果只进入经营状况独立数据包，产品与地区不得混传。

