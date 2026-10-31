# 科创能力数据源

### 11. 科创能力

仅在“非城投且是否科创企业=true”时生成。本板块的数据必须单独取数、单独登记来源，并只传入 `references/analysis-prompts/sci-tech-capability.md`。本板块固定使用的资讯 query 为：

```text
<企业全名> 专利 知识产权 科技创新 相关资讯 最新动态
```

MQL 取数的 UI 路径锚点为：

```text
/Choice金融终端/企业F9(发行人+工商企业)/企业经营/企业产权
```

生成 MQL 时必须先通过 `Search_Context` 把该路径下的实际报表候选、`indicatorPath`、`reportFields`、`reportFilterColumns` 和 `reportStandardCodeSupported` 核对清楚；MQL 中只能使用检索结果返回的实际字段名。UI 展示名（例如“专利”“商标”“年度变化”）只能作为语义标签，不能直接当作 `REPORT_FIELD()` 的字段名。

本轮状态（2026-09-20）：专利分布、员工构成及研发费用单项已执行成功，产权全量统计/年度变化/商标分布仍缺元数据；详见 [MQL核验记录](mql-verification.json)。不把单项通过等同于科创模块完整通过。

#### 11.1 MQL 数据集

本板块必须单独形成以下数据集，不得把企业类型判定的完整原始数据包直接传入 prompt：

| 数据集 key | 当前来源状态 | 用途 |
|---|---|---|
| `sci_tech_property_summary` | 企业产权-数量统计；报表路径由 `Search_Context` 实际返回 | 商标、专利、著作权、软件著作权、域名等当前累计数量 |
| `sci_tech_property_yearly` | 企业产权-年度变化图；报表路径由 `Search_Context` 实际返回 | 各知识产权类型按年度新增/变化数据 |
| `sci_tech_patent_distribution` | 已核对：`Choice报表\\报表指标\\Choice金融终端\\A股F9\\公司一页纸\\公司研发实力\\公司一页纸_上市公司专利信息` | 发明、实用新型、外观设计及专利合计等分布字段 |
| `sci_tech_trademark_distribution` | 企业产权-商标分布图；报表路径由 `Search_Context` 实际返回 | 商标按行业/类别的分布数据 |
| `sci_tech_rd_exp_emp` | 已核对：`Choice报表\\报表指标\\Choice金融终端\\A股F9\\公司一页纸\\公司研发实力\\沪深F9_财务附注_研发支出` 与 `Choice报表\\报表指标\\Choice金融终端\\A股F9\\公司基本资料\\员工构成\\沪深F9_基础资料_员工构成`；用户指定函数 `RPT_ENT_RD_EXP_EMP` 作为语义锚点 | 研发投入、费用化/资本化、研发人员数、员工总数及研发人员占比 |
| `sci_tech_titles` | 企业 F9 机构基本信息 + 已核对普通指标 `是否高新技术企业`、`所属概念板块` | 高新技术企业、专精特新小巨人、专精特新中小企业、独角兽等称号/标签 |
| `sci_tech_industry` | 企业 F9 基本信息 | 企业所属行业，至少保留 `GBGI_INDUSTRY`；如 MQL 返回更细行业字段，一并保留 |

上述七组数据在正式运行时均需分别执行 `Get_MQL_Reference → Search_Business_Knowledge → Search_Context → Execute_MQL`；每组结果分别记录内部数据集状态，再合并为科创能力板块自己的 `block_data_package`。不得把其它板块的经营、财务或 ESG 原始数据混入本包。

#### 11.2 已核对 MQL 字段

1. **专利分布**：已核对报表返回字段包括 `ORG_CODE`、`SECURITY_NAME_ABBR`、`END_DATE`、`SYSDATE_DATE`、`TOTAL_ACCUM_NUM`、`INVENT_ACCUM_NUM`、`UTILITY_ACCUM_NUM`、`DESIGN_ACCUM_NUM`、`INTL_ACCUM_NUM`、`BANKNAME`、`DERIVE_SECURITY_CODE`。本地数据包按原字段保留，不改写为猜测字段。
2. **研发支出**：`Search_Context` 已返回候选字段 `ORG_CODE`、`SECUCODE`、`SECURITY_NAME_ABBR`、`REPORT_DATE`、`REPORT_YEAR`、`STD_ITEM_CODE`、`STD_ITEM_NAMENEW`、`CURRENT_AMT`、`REPORT_TYPE`、`REPORT_TYPE_CODE`、`TYPE`、`TYPE_CODE`。研发费用、资本化研发投入和费用化研发投入应以 `STD_ITEM_NAMENEW` 区分项目，不得用本地英文别名替代实际返回字段。当前 Runtime 对该候选路径的直接执行返回“报表名称不能为空”，因此正式运行时仍以用户指定的 `RPT_ENT_RD_EXP_EMP` 语义锚点重新检索可执行报表；若当前 Runtime 仍无法执行，则切换 Python 兜底并记录失败原因。
3. **员工构成**：已核对报表返回字段包括 `SECUCODE`、`SECURITY_CODE`、`SECURITY_NAME_ABBR`、`REPORT_DATE`、`NOTICE_DATE`、`RESEARCH_NUM`、`TOTAL_NUM`、`TECHNOLOGY_NUM`、`DOCTOR_NUM`、`MASTER_NUM`、`GRADUATE_NUM`、`ADMINISTRATOR_NUM`、`PRODUCT_NUM`、`SALE_NUM`、`FINANCE_NUM`、`OTHER_NUM`、`RETIRE_NUM`、`CORE_NUM`。研发人员占比优先使用报表真实字段或同报告期真实指标，不在 prompt 内自行替代统计口径。
4. **科创称号**：普通指标候选已核对 `Choice指标\\股票\\沪深京股票指标\\基本资料\\公司资料\\是否高新技术企业` 与 `Choice指标\\股票\\沪深京股票指标\\基本资料\\证券资料\\所属概念板块`；企业 F9 机构基本信息中的 `TAG_NAME`、`TECH_TITLE` 可作为补充原始字段。
5. **行业**：企业 F9 基本信息中的 `GBGI_INDUSTRY` 为本板块基础行业字段；MQL 若返回 `INDUSTRY`、`INDUSTRY_NAME` 或更细行业字段，只能按实际返回字段追加。

#### 11.2.1 本轮可用查询

科创基本信息固定模板键为 `sci_tech_profile`，已验证路径和样例如下：

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\表头\企业F9_机构基本信息|148758350698551});
SetReportFilter({公司代码} == "<ORG_CODE>");
{行业}: REPORT_FIELD("行业");
{省份}: REPORT_FIELD("省份");
{科创称号}: REPORT_FIELD("科创称号");
{科创领域}: REPORT_FIELD("科创领域");
OutputBlock();
```

芯碁微装样例返回 1 行。该模板只覆盖行业、省份、科创称号和科创领域；企业产权数量、年度变化、专利分布和商标分布仍按各自数据集动态核验。

专利表函数实际为 `RPT_PUBLIC_PAPER_PATENTTOTAL`，支持股票代码，加载 `系统日期`。芯碁微装返回 2026-06-30 的累计专利合计 251（发明101、实用新型137、外观设计13）；这是该报表报告期末口径，不自动等于工商产权库的当前累计数。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\A股F9\公司一页纸\公司研发实力\公司一页纸_上市公司专利信息|RPT_PUBLIC_PAPER_PATENTTOTAL});
SetCodes(["<股票代码>"]);
SetReportFilter(({系统日期} == "<系统日 YYYY-MM-DD>"));
{板块}: REPORT_FIELD("板块");
{衍生证券代码}: REPORT_FIELD("衍生证券代码");
{报告期末累计拥有外观设计专利数量}: REPORT_FIELD("报告期末累计拥有外观设计专利数量");
{截止日期}: REPORT_FIELD("截止日期");
{报告期末累计拥有国际专利数量}: REPORT_FIELD("报告期末累计拥有国际专利数量");
{报告期末累计拥有发明专利数量}: REPORT_FIELD("报告期末累计拥有发明专利数量");
{公司代码}: REPORT_FIELD("公司代码");
{公司简称}: REPORT_FIELD("公司简称");
{系统日期}: REPORT_FIELD("系统日期");
{报告期末累计拥有专利合计数量}: REPORT_FIELD("报告期末累计拥有专利合计数量");
{报告期末累计拥有实用新型专利数量}: REPORT_FIELD("报告期末累计拥有实用新型专利数量");

OutputBlock();
```

员工表 `RPT_HSF9_BASIC_STAFFCOMPOSITION` 过滤 `报告期`，使用 `SetCodes(["<股票代码>"])`，读取 `证券代码(带后缀)、报告期、研发人员、职工总数`。芯碁样本返回 7 行，2025-12-31 研发人员281、职工804；2026-06-30职工总数为空，不把该空值填零或与上一年混算占比。

研发附注报表仍报“报表名称不能为空”，但已核对普通指标作为研发费用单项补充：

```mql
CrossSectionBlock(#1, {EM_CODE});
SetCodes(["<ORG_CODE>.FXR"]);
{研发费用}: {Choice指标\发行人\企业全部指标\财务与分析\财务数据(大陆准则,标准)\一般企业\利润表\研发费用|100000000009850}({报告期} = "<报告期 YYYY-MM-DD>", {报表类型} = "合并报表");
OutputBlock();
```

此指标实际参数为 `报表类型`，不是财务总计指标的 `报告类型`。它只提供研发费用，不能冒充资本化研发投入或总研发投入。用户指定 `RPT_ENT_RD_EXP_EMP` 在本轮仍未召回完整 MQL 元数据。

#### 11.3 产权统计、年度变化和商标分布的动态字段规则

“企业产权-数量统计”“企业产权-年度变化图”“企业产权-商标分布图”在当前 MQL 上下文中没有稳定返回可直接硬编码的字段名，因此正式执行时必须：

- 以企业产权路径和 UI 子表名称提交 `Search_Context`；
- 以返回的 `indicatorPath` 生成 `ReportBlock`；
- 以返回的 `reportFields` 逐项生成 `REPORT_FIELD("<实际字段名>")`；
- 仅在返回列中保留与数量、年度、类别/行业、公司代码、证券简称、日期有关的字段；
- 若同一子表同时返回多个年度或类别记录，保持原始行粒度，不在 MQL 中擅自汇总；年度/类别的排序和去重放在本地数据整理步骤完成；
- 若该子表的 `reportStandardCodeSupported=false`，不得写 `SetCodes`，应优先按已暴露的公司代码加载列使用 `SetReportFilter` 限定主体；仅返回列存在时才核对安全的查询范围后用 `FILTER_ROWS`，不得默认拉取全库；若支持标准代码，则优先使用 `SetCodes(["<证券代码>"])`。

这三组数据不得因字段未返回而改用资讯中的专利或商标数量替代。正式 MQL 路径失败时，先按相同业务语义检索并验证其它 MQL 候选；全部同业务 MQL 候选失败后，Python 只能调用已确认的同源 REST 函数；未确认 REST 函数的子表返回空数据并记录 fallback 原因，不得编造字段或数量。

#### 11.4 科创能力数据包字段整理

科创能力 prompt 接收的统一数据包至少包含以下逻辑分区；逻辑分区内保留 MQL 原始字段和来源信息：

```text
property_summary
property_yearly
patent_distribution
trademark_distribution
rd_expense
rd_employee
titles
industry
```

其中 `TAG_CODE` 仍只用于前置类型判定；科创能力成文可使用同一 MQL 查询返回的 `TAG_NAME`、`TECH_FIELD`、`TECH_TITLE`、`titles`，但不能在 prompt 内重新改写 `is_sci_tech`。

#### 11.5 Python REST 兜底

Python 仅在对应 MQL 数据集失败、超时或关键字段缺失时启用：

- `sci_tech_profile`、`sci_tech_titles`、`sci_tech_industry` 可由已验证的 `RPT_COP_ORG_INFO` 字段裁剪得到；
- `sci_tech_patent_distribution` 优先使用已核对的专利报表 REST 函数；若 REST 函数名未由上下文返回，则记录 `fallback_reason`，不得猜测函数名；
- `sci_tech_rd_exp_emp` 使用用户指定的 `RPT_ENT_RD_EXP_EMP` 作为首选 REST 函数，并按返回字段裁剪；若接口只返回研发支出或只返回员工构成，按实际返回拆分，不补造缺失项；
- `sci_tech_property_summary`、`sci_tech_property_yearly`、`sci_tech_trademark_distribution` 在 REST 函数未核对前只返回空数组和明确的 fallback 原因；不得用资讯替代结构化产权数据。

不得用资讯中的研发投入、专利数量、商标数量或称号替代 MQL 结构化字段；某个子数据集为空时，prompt 只分析其它已有维度。

#### 11.6 资讯来源

资讯只由 `mx-finance-search` 获取，query 固定为：

```text
<企业全名> 专利 知识产权 科技创新 相关资讯 最新动态
```

