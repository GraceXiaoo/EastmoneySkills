# 信用分析数据源

### 13. 信用分析

状态：部分验证（2026-09-20），见 [MQL核验记录](mql-verification.json)。信用分析是固定收尾板块之一，必须单独取数、单独登记来源，并只将本板块专属 `block_data_package` 传入 `references/analysis-prompts/credit-analysis.md`。不得把基本情况、财务摘要、存续债券或偿债分析的完整数据包直接混入本板块。

#### 13.1 MQL 主路径

用户展示路径：

```text
/Choice金融终端/企业F9/企业一页纸/信用分析
```

指定函数：

```text
RPT_CUSTOM_ORG_CREDITANALYSIS
```

上述业务路径与函数的对应关系已由用户确认，正式取数优先同时使用路径和函数名检索。指定函数未召回或执行失败时，不立即切换 REST；先检索并执行同业务相近报表。当前已验证的 MQL 候选为 `RPT_ORG_COMBFINCREDIT`，不是 `RPT_CUSTOM_ORG_CREDITANALYSIS`。它仅在指定表不可用或缺字段时提供 8 个评级、担保及授信字段作为部分输入，不能替代指定表的违约、展期、担保对象和覆盖指标。主路径恢复可用后仍优先使用主路径，候选结果不得与主路径原始行混合。

相近报表的已执行路径为：

```text
Choice报表\报表指标\Choice金融终端\企业F9\智能发行人\信用分析\信用分析
```

该报表 `reportStandardCodeSupported=false`，不能写 `SetCodes` 或 `GetSectors`。实际过滤列为 `ORG_CODE`，MQL Runtime 绑定名称为“公司代码”，因此使用：

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\智能发行人\信用分析\信用分析});
SetReportFilter({公司代码} == "<ORG_CODE>");
{公司代码}: REPORT_FIELD("公司代码");
{公司代码(带后缀)}: REPORT_FIELD("公司代码(带后缀)");
{最新主体评级}: REPORT_FIELD("最新主体评级");
{评级展望}: REPORT_FIELD("评级展望");
{变动方向}: REPORT_FIELD("变动方向");
{最新担保余额}: REPORT_FIELD("最新担保余额");
{银行授信总额度}: REPORT_FIELD("银行授信总额度");
{银行授信已使用额度}: REPORT_FIELD("银行授信已使用额度");
OutputBlock();
```

已用中国民生银行发行人代码 `10002264.FXR` 完成执行验证，按“公司代码”过滤返回 1 条信用分析记录。正式执行时，报表路径、过滤列、`REPORT_FIELD()` 请求名和输出字段仍必须以当前 `Search_Context` 与 Runtime 实际返回为准。

#### 13.2 数据字段与整理

MQL 报表当前已确认的字段白名单为：

```text
公司代码、公司代码(带后缀)、最新主体评级、评级展望、变动方向、最新担保余额、银行授信总额度、银行授信已使用额度
```

为覆盖提示词要求的违约、展期、担保对象、授信银行、授信机构数量及偿债覆盖指标，信用分析板块还应查询指定的 `RPT_CUSTOM_ORG_CREDITANALYSIS` 的实际报表字段。当前已由该函数的 REST 返回核对的字段语义包括：

```text
REPORT_DATE、ISSUERRATES、ISSUERRATEFWS、ISSUERRATECWS、DEFAULT_PRICE、TOP10_GUARANTEED、BANKCT_AMOUNT、BANKCT_USE_AMOUNT、UCD_RATIO、BANKCT_NAME、BANKCT_COUNT、REAL_DEFAULT_NUM、NEWEST_DEFAULT、PROLONG_NUM、GUARANTAMT_EQUITY_RATIO、GUARANTAMT_ASSETS_RATIO、JYXJECDX、JYXJECLD、CASHTOSTDEBT
```

正式 MQL 中只能写 `Search_Context` 实际返回的字段名称；上述 REST 字段名只能用于返回结果整理和字段语义映射，不得直接当作未经核对的 `REPORT_FIELD()` 名称。若某个 MQL 候选只返回部分字段，保留真实函数名并登记 partial；继续尝试其它同业务 MQL 候选补足数据，但不得把不同候选原始行混合。只有全部候选仍缺少指定字段时，才按下方同源 Python REST 兜底，不得用其它板块数据或 `RPT_COP_ORG_INFO` 评级字段冒充完整结果。

`{{数据}}` 的独立数据包应包含：

```text
credit_analysis：保留真实来源函数；RPT_ORG_COMBFINCREDIT 的部分 MQL 字段，与 RPT_CUSTOM_ORG_CREDITANALYSIS 的同源兜底字段分别登记
```

信用分析正文后可附加“信用分析”表格，字段范围仅限以下 14 项：`RATING`、`RATING_EXPECT`、`DIRECTION`、`REAL_DEFAULT_NUM`、`NEWEST_DEFAULT`、`PROLONG_NUM`、`DEFAULT_PRICE`、`TOP10_GUARANTEED`、`BANKCT_AMOUNT`、`BANKCT_USE_AMOUNT`、`BANKCT_NAME`、`BANKCT_COUNT`、`GUARANTAMT_EQUITY_RATIO`、`GUARANTAMT_ASSETS_RATIO`。其中评级字段可按本文件的 REST/MQL 实际字段映射归一。表格的生成门槛、展示标签、空值和零值处理见 [报告视觉组件](../visual-assets.md#信用分析表格)；信用分析模块未实际生成并保留正文时，不展示该表。

信用分析板块的 `{{资讯}}` 必须使用 `mx-finance-search`，query 固定为：

```text
<企业全名> 信用 担保 诉讼 相关资讯 最新动态
```

例如：

```text
中国民生银行股份有限公司 信用 担保 诉讼 相关资讯 最新动态
```

资讯只用于信用记录、担保风险、诉讼及行政处罚等背景补充，必须形成当前板块独立的 `block_news_package`，不能复用其它板块的全局资讯结果。

#### 成文边界

- 最新主体评级、评级展望或变动方向为空时，略去相应内容，不输出字段状态，也不得据此写“公司无公开主体评级”“未纳入境内外评级范围”或“无外部评级需求”。评级有值而展望为空时，只写有依据的评级事实。
- 授信、担保、违约和展期等指标采用相同规则：空值不等于零，缺记录不等于无相关事项；有效零值仅在该指标的主体、日期和统计范围内表述。任何否定性结论须有明确业务数据或公告事实支持。
- 仅依据本板块实际取得的有效材料成文。某个角度无依据时略去该角度及空的小标题；不能只删除“字段为空”的括号却留下由空值推断的结论，也不能为填补空缺混入其它板块指标。成文和重点关注交接均执行 [成文输出检查](../analysis-prompt.md#成文输出检查)。

#### 13.1.1 已固化的全字段 MQL 样例

信用分析的固定模板键为 `credit_full`，路径为 `信用分析|088883350557610`。过滤条件必须包含 `公司代码` 和 `截止日期`；完整字段绑定及运行时替换由 `scripts/render_mql_template.py` 执行。民生银行样例已验证返回 1 行、19 列。模板中 `货币资金/短期债务` 的请求名保留 Runtime 暴露的 NUL 后缀，不能手工删改。若模板执行失败，才进入本节所述同业务 MQL 候选回退。

#### 13.3 Python REST 兜底

仅当本板块信用分析的指定主路径、`RPT_ORG_COMBFINCREDIT` 已验证候选及本次 `Search_Context` 发现的其它同业务候选均执行失败、超时、元数据无法绑定或关键字段缺失时，才允许使用本地 Python 兜底：

```text
reportName=RPT_CUSTOM_ORG_CREDITANALYSIS
columns=ALL
filter=(ORG_CODE="<ORG_CODE>")(END_DATE<='<系统日 yyyy-MM-dd>')
sortColumns=REPORT_DATE&sortTypes=-1
pageNumber=1&pageSize=200&source=choice&client=SW
```

2026-09-20 同源 REST 复测民生银行返回 1 行、报告期 2026-06-30；部分授信/担保字段为空，违约次数为 0，这不表示所有字段均非空。接口错误必须保持失败，不作为正常空结果。

该接口实际返回的信用分析字段按 `REPORT_DATE` 倒序保留；Python 兜底整理时将 `ISSUERRATES`、`ISSUERRATEFWS`、`ISSUERRATECWS` 分别映射为本地统一字段 `RATING`、`RATING_EXPECT`、`DIRECTION`，同时保留原始字段及其余信用分析字段。`END_DATE` 是该接口的必需过滤条件，不得省略。兜底结果的 `query_path` 必须登记为 `Python REST fallback`，并注明 MQL 失败原因。

信用分析板块不允许再使用 `RPT_COP_ORG_INFO` 冒充独立信用分析结果；该接口仅可作为企业类型判定或其它明确配置板块的兜底来源。MQL 与 Python 均失败时，保留内部失败状态；若本板块仍有有效资讯，只分析有依据的内容。数据与资讯均无可用内容时，信用分析 prompt 按其空数据规则返回内部结果 `暂无数据`，正式报告省略该章节。

