# 偿债分析数据源

### 12. 偿债分析

仅在城投企业或非城投发债人路径使用。若发行概述专属发行一览查询已成功完成跨市场去重、排除同业存单及 `到期日期 >= 系统日` 过滤，且没有任何有效存续债券，则本板块不生成；该路由状态与发行概述同步。若该查询失败或状态未知，不得据此认定没有债券，仍按原路由尝试本板块取数。`{{数据}}` 必须拆分为以下五个独立数据集，并严格按下列顺序传入 `references/analysis-prompts/solvency.md`：

```text
solvency_financial_key_metrics
solvency_credit_analysis
solvency_liability_structure
solvency_issue_end_statistics
solvency_shareholder
```

五个数据集分别制定并执行 MQL 查询；同一任务共享已取得的语法、业务知识和元数据上下文。即使多个数据集来自同一企业或同一底层接口，也必须在 MQL 返回后按字段白名单拆包、分别记录内部数据集状态，不能把全局 `financial_summary`、`credit_analysis` 或 `bonds` 数据包直接传入偿债提示词。正式 MQL 路径失败时，先尝试已登记或动态发现的同业务 MQL 候选；全部候选失败后才对失败的数据集切换本地 Python REST 兜底，一个数据集失败不影响其它数据集继续使用。`{{资讯}}` 独立使用 `mx-finance-search`，不得把其它板块资讯混入本板块。

本轮状态：财务关键指标、负债结构分别返回中石油 4 个报告期；季度偿债统计未通过。证据及边界见 [MQL核验记录](mql-verification.json)。

#### 12.1 财务关键指标：`solvency_financial_key_metrics`

| 项目 | 配置 |
|---|---|
| MQL UI 路径 | `/Choice金融终端/企业F9/企业一页纸/财务关键指标` |
| 主体过滤 | 目标企业完整 `ORG_CODE`；实际过滤列以 `Search_Context` 返回的 MQL Runtime 绑定字段为准 |
| 字段白名单 | `CASHII`、`CURRENT_RATIO`、`DEBT_ASSET_RATIO`、`EBITZTFNEW`、`INTSTCOVRATE`、`NETPROFIT`、`OCFTOINTEREST`、`ORG_CODE`、`REPORT_DATE`、`SPEED_RATIO`、`TOTAL_ASSETS`、`TOTAL_CURRENT_LIAB`、`TOTAL_NONCURRENT_LIAB`、`YYZB` |
| 数据用途 | 现金及流动性、资产负债率、利息保障、净利润、经营现金流利息覆盖、资产和流动/非流动负债等偿债指标 |

字段白名单是本地数据包和提示词传入字段；正式生成 MQL 时，必须以该路径经 `Search_Context` 返回的实际 `reportFields[].column_name_cn` 字段名为准，不得把未经运行时确认的 Python 字段别名直接写入 `REPORT_FIELD()`。

已验证函数 `RPT_CUSTOM_AIONEPAPER_FINANCE`，加载列为 `发行人`，返回列中的主体名是 `公司代码`，两者不要混淆：

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\财务关键指标\企业一页纸-财务关键指标|RPT_CUSTOM_AIONEPAPER_FINANCE});
SetReportFilter(({发行人} == "<ORG_CODE>"));
{现金比率}: REPORT_FIELD("现金比率");
{流动比率}: REPORT_FIELD("流动比率");
{资产负债率}: REPORT_FIELD("资产负债率");
{EBITDA(正推)}: REPORT_FIELD("EBITDA(正推)");
{利息保障倍数}: REPORT_FIELD("利息保障倍数");
{净利润}: REPORT_FIELD("净利润");
{现金利息保障倍数}: REPORT_FIELD("现金利息保障倍数");
{公司代码}: REPORT_FIELD("公司代码");
{报告期日期}: REPORT_FIELD("报告期日期");
{速动比率}: REPORT_FIELD("速动比率");
{总资产}: REPORT_FIELD("总资产");
{流动负债}: REPORT_FIELD("流动负债");
{非流动负债}: REPORT_FIELD("非流动负债");
{营运资本}: REPORT_FIELD("营运资本");

OutputBlock();
```

#### 12.2 信用分析：`solvency_credit_analysis`

| 项目 | 配置 |
|---|---|
| MQL UI 路径 | `/Choice金融终端/企业F9/企业一页纸/信用分析` |
| 主体过滤 | 目标企业完整 `ORG_CODE`；实际过滤列以 `Search_Context` 返回的 MQL Runtime 绑定字段为准 |
| 字段白名单 | `BANKCT_AMOUNT`、`BANKCT_COUNT`、`BANKCT_NAME`、`BANKCT_USE_AMOUNT`、`CASHTOSTDEBT`、`DEFAULT_PRICE`、`GUARANTAMT_ASSETS_RATIO`、`GUARANTAMT_EQUITY_RATIO`、`ISSUERRATECWS`、`ISSUERRATEFWS`、`ISSUERRATES`、`JYXJECDX`、`JYXJECLD`、`NEWEST_DEFAULT`、`ORG_CODE`、`PROLONG_NUM`、`REAL_DEFAULT_NUM`、`REPORT_DATE`、`TOP10_GUARANTEED`、`UCD_RATIO` |
| 数据用途 | 银行授信、授信使用、现金债务覆盖、担保、违约、展期和信用风险指标 |

指定主表 `RPT_CUSTOM_ORG_CREDITANALYSIS` 已通过 `credit_full` 模板取回 19 个业务输出字段，按公司代码和截止日期过滤，详见 [信用分析](credit-analysis.md)。相近报表 `RPT_ORG_COMBFINCREDIT` 只提供部分授信、评级和担保字段，不覆盖此白名单，仅作候选。本数据集是偿债分析专属信用分析输入，须按白名单单独裁剪；不得把全局信用分析结果直接传入，也不得以 `RPT_COP_ORG_INFO` 的字段冒充。全部同业务 MQL 候选失败后才可使用同源 Python 兜底。

#### 12.3 负债结构：`solvency_liability_structure`

| 项目 | 配置 |
|---|---|
| MQL UI 路径 | `/Choice金融终端/企业F9/企业一页纸/负债结构` |
| 主体过滤 | 目标企业完整 `ORG_CODE`；实际过滤列以 `Search_Context` 返回的 MQL Runtime 绑定字段为准 |
| 字段白名单 | `ACCOUNTS_PAYABLE`、`BOND_PAYABLE`、`CD_NOTE_PAYABLE`、`LONG_LOAN`、`ORG_CODE`、`OTHER_CURRENT_LIAB`、`OTHER_LIAB`、`REPORT_DATE`、`SHORT_LOAN`、`TYPE_CODE` |
| 数据用途 | 应付账款、应付债券、应付票据、长短期借款及其他流动/非流动负债的期限结构 |

本数据集只服务偿债分析；不得以财务摘要中的资产负债字段替代负债结构表的字段，也不得在 MQL 元数据缺失时自行猜测函数名、报表列或 `TYPE_CODE` 枚举。

偿债分析正文后可从该数据集生成独立的“图表N 负债结构”环状图。整理出实际项目后，须在正文生成过程中直接请求“生成环状图”，并提供项目名称、金额、单位和报告期。使用同一最新有效报告期的短期借款、长期借款、应付债券、应付票据、应付账款、其他流动负债和其他负债等实际返回项目；仅纳入明确有效的非负金额，不将空值解释为零。金额单位、报表类型和报告期必须一致，图例标注各项实际名称、金额、单位和报告期。该图不复用财务状况模块的数据。

已验证函数 `RPT_CUSTOM_AIONEPAPER_DEBT`，加载列同样为 `发行人`：

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\负债结构\企业一页纸-负债结构|RPT_CUSTOM_AIONEPAPER_DEBT});
SetReportFilter(({发行人} == "<ORG_CODE>"));
{应付账款}: REPORT_FIELD("应付账款");
{应付债券}: REPORT_FIELD("应付债券");
{应付票据}: REPORT_FIELD("应付票据");
{长期借款}: REPORT_FIELD("长期借款");
{公司代码}: REPORT_FIELD("公司代码");
{其他流动负债}: REPORT_FIELD("其他流动负债");
{其他负债}: REPORT_FIELD("其他负债");
{报告期日期}: REPORT_FIELD("报告期日期");
{短期借款}: REPORT_FIELD("短期借款");
{报表类型}: REPORT_FIELD("报表类型");

OutputBlock();
```

上述两表同源 REST 也已验证，使用 `ORG_CODE` 过滤。不能将 MQL 的中文加载列名写进 REST filter。

#### 12.4 发行与到期：`solvency_issue_end_statistics`

下方仅为 `solvency_statistics_diagnostic` 诊断样例，验证了两列可取，不是完整发行与到期模板。正式键 `solvency_statistics` 保持阻塞，不能直接用于绘图：

```mql
ReportBlock(#1, {Choice报表\报表指标\服务端\妙想服务\细分场景\企业分析\企业融资偿债情况\偿债统计\企业融资偿债情况偿债统计|RPT_CUSTOM_BOND_ISSUEEND_IS_C});
SetReportFilter(({实体代码} == "<ORG_CODE>.FXR") AND ({起始日期} == "<START_DATE>") AND ({截止日期} == "<END_DATE>") AND ({周期} == 4) AND ({发行日期类型} == "2"));
{偿债总额}: REPORT_FIELD("偿债总额");
{偿债只数}: REPORT_FIELD("偿债只数");
OutputBlock();
```

该样例在民生银行窗口 `2024-09-30` 至 `2027-09-30` 返回 13 行；加入实际字段“到期年份”后返回日期格式校验错误（执行编号 `36dae5f4-90d0-4417-9611-731d74674c37`）。现有结果也未验证下述六类债券排除条件，缺少发行额、到期额和季度日期的完整可比序列。不能按行序猜季度、把偿债总额改名为发行额或到期额，也不能省略排除条件后宣称业务验证通过。

| 项目 | 配置 |
|---|---|
| MQL UI 路径 | `/服务端/妙想服务/细分场景/企业分析/企业融资偿债情况/偿债统计` |
| 函数 | `RPT_CUSTOM_BOND_ISSUEEND_IS_C` |
| 主体过滤 | 目标企业主体；具体主体字段、日期字段和债券类型字段必须由 `Search_Context` 核对后使用 |
| 时间窗口 | 以运行时系统日为基准，系统日前两年至系统日后一年，即 `system_date - 2 calendar years` 至 `system_date + 1 calendar year` |
| 统计频率 | 按季度统计 |
| 债券类型排除 | `利率债`、`同业存单`、`可转债`、`资产支持债券`、`可交换债券`、`境外债` |
| 数据用途 | 发行规模、到期规模、净融资及未来集中偿债时间，用于滚续率和偿债压力分析 |

本轮已召回元数据，但尚未完成业务口径验证：

- 路径：`Choice报表\报表指标\服务端\妙想服务\细分场景\企业分析\企业融资偿债情况\偿债统计\企业融资偿债情况偿债统计|RPT_CUSTOM_BOND_ISSUEEND_IS_C`。
- 过滤为 `实体代码="<ORG_CODE>.FXR"`、`起始日期`、`截止日期`、`周期=4`（整数，季度）、`发行日期类型="2"`。
- 返回仅有 `偿债总额`、`到期年份`、`偿债只数`，未暴露六类债券排除参数，也没有发行额，不能据此宣称发行与到期、净融资全部取得。
- 民生窗口 2024-09-20 至 2027-09-20 执行报 `报表字段返回值日期格式无效：到期年份`。不能去掉日期列或排除要求后宣称通过。
- 保留动态窗口、quarter 和六类排除清单；`fields_status="元数据已发现，季度日期解析及债券排除口径待验证"`。当前 Python 未确认完整同口径接口，返回空与明确原因，不造数。

季度发行与到期图表标题为“图表N 发行与到期统计”，使用两条同口径金额序列绘制折线图。当前 MQL 结果未暴露发行额，且季度日期解析和排除债券类型口径仍待验证，因此现有 `偿债总额`、`到期年份`、`偿债只数` 不能支持该图表：不得把偿债总额当作发行额或到期额。只有在 MQL 返回可比季度、发行额和到期额及其币种/单位后，才在正文中请求“生成折线图”，并提供完整两组数值；不足则仅跳过此图，不影响有依据的正文或负债结构图。

#### 12.5 股东情况：`solvency_shareholder`

| 项目 | 配置 |
|---|---|
| MQL 数据源 | 复用股东情况板块同一 `block_data_package` 中的股东股权摘要结果 |
| 主体过滤 | 目标企业完整 `ORG_CODE`，取系统日对应的最新有效记录；实际过滤列和日期列以 `Search_Context` 返回为准 |
| 字段白名单 | `SJKZR`、`TOP1_HOLDER_ST` |
| 数据用途 | 实际控制人性质、第一大股东及外部融资支持判断 |

该数据集允许复用股东情况板块同源 MQL 查询结果，但必须在传入偿债提示词前单独复制并裁剪为 `SJKZR`、`TOP1_HOLDER_ST` 两个字段，单独记录 `solvency_shareholder` 内部状态；十大股东逐名次明细、前十名合计、关联交易及其它字段不得混入。发行人指标逐名次查询只服务于主要股东表格，不能替代这两个摘要字段。

#### 12.6 偿债分析资讯

`{{资讯}}` 使用 `mx-finance-search`，query 固定为：

```text
<企业全名> 偿债 相关资讯 最新动态
```

例如：

```text
中国民生银行股份有限公司 偿债 相关资讯 最新动态
```

资讯返回结果仍须按 [news-processing.md](../news-processing.md) 的来源分类、权威度和发布时间规则排序；资讯只进入偿债分析的 `{{资讯}}`，不得替代五个 MQL 数据集。

