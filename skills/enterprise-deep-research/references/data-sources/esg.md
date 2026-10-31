# ESG分析数据源

状态：指定核心字段与更新时间已由 MQL 明细报表取得；汇总和明细均有可执行候选。主路径与同业务 MQL 候选均须保留，执行失败时先回退同业务候选，不得直接跳到 REST。见 [MQL核验记录](mql-verification.json)。

## 数据来源

用户展示路径：`/Choice金融终端/企业F9/评级分析/ESG评级/ESG详情页/ESG评级汇总+评级构成`。
用户函数 `RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS` 保留作同源 REST 兜底；实际可执行的 MQL 汇总候选为 `RPT_ESG_STOCK_CODE`，一级指标明细的已验证 MQL 候选为 `RPT_DETAILS_WID`。来源登记必须分别记录，不得把用户函数、MQL 候选和 REST 兜底写成同一个接口。

只有前置判断 `is_esg_scope=true` 才生成。评级机构固定“中诚信绿金”，主评分 `ESG_SCORE` 非空即有效，0 也有效；`ESG_STDSCORE` 不替代主评分。

## 已验证字段

| 用户字段含义 | MQL 请求名称 | MQL 物理列 |
|---|---|---|
| ESG_RATING | ESG评级 | ESG_RATING |
| ESG_RATING_MID | 行业内esg评级中位数 | ESGRATING_MID |
| ESG_SCORE | ESG评分 | ESG_SCORE |
| ESG_SCORE_AVG | 行业内esg评分平均值 | ESG_AVG |
| ESG_SCORE_MID | 行业内esg评分中位数 | ESGSCORE_MID |
| ESG_SCORE_RN | 行业ESG评分排名 | ESG_NO |
| ESG_STDSCORE | esg总分 | ESG_STDSCORE |
| INDUSTRY | 所属行业名称 | INDUSTRY_NAME |
| INDUSTRY_NUM | 行业总数 | INDUSTRY_NUM |
| UPDATEDATE | 更新日期 | UPDATEDATE |

物理列映射只用于本地归一，`REPORT_FIELD` 和过滤均使用表中 MQL 请求名称。E/S/G 得分可按实际返回列 `E得分`、`S得分`、`G得分` 单独追加，不能猜测英文列别名。

## 可执行模板

`SetCodes` 使用已识别的目标证券代码。机构和日期是加载过滤，行业分类固定为同一口径；下方验证使用“申万三级行业(2021)”。如业务另选分类，须保留对应分类名称，不能把多个行业口径的均分、排名和行业总数混在一起。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\API专题报表函数\A股\F9\ESG\ESG-个股|RPT_ESG_STOCK_CODE});
SetCodes(["<目标证券代码>"]);
SetReportFilter(({指数机构名称} == "中诚信绿金") AND ({所属行业} == "申万三级行业(2021)") AND ({更新日期} <= "<系统日 YYYY-MM-DD>"));
{公司代码}: REPORT_FIELD("公司代码");
{指数机构名称}: REPORT_FIELD("指数机构名称");
{ESG评级}: REPORT_FIELD("ESG评级");
{行业内esg评级中位数}: REPORT_FIELD("行业内esg评级中位数");
{ESG评分}: REPORT_FIELD("ESG评分");
{行业内esg评分平均值}: REPORT_FIELD("行业内esg评分平均值");
{行业内esg评分中位数}: REPORT_FIELD("行业内esg评分中位数");
{行业ESG评分排名}: REPORT_FIELD("行业ESG评分排名");
{esg总分}: REPORT_FIELD("esg总分");
{所属行业名称}: REPORT_FIELD("所属行业名称");
{行业总数}: REPORT_FIELD("行业总数");
{更新日期}: REPORT_FIELD("更新日期");
Sort({更新日期}, "DESC");
OutputBlock();
```

茅台样本返回 4 个更新时间；最新为 2024-12-31，ESG评分 76.68。这是本次接口实际最新可用记录，不得改写为系统日评分。

## 整理与隔离

- 先固定主体、评级机构、行业口径，再按更新日期降序。选择最新有评分记录，保留实际截止日期。
- 将同一查询裁剪为当前板块的评级汇总/评级构成，以及按 `更新日期` 去重的日期列表。另为一级指标评级明细建立同板块专属 MQL 数据集，不得把汇总字段或日期列表当作明细行。
- 同一日期若出现内容不同的重复记录，不任意合并排名和均分；先核实行业口径。日期列表可去重，评分行必须仍可追溯。
- `RPT_ESG_RATINGSUM` 作为汇总候选，其加载过滤仅有 `所属行业`，机构和日期须在返回后过滤。本轮茅台测试零行，不能标为完整通过。
- 单独形成 ESG 的 `block_data_package`，只传入 `references/analysis-prompts/esg.md`。其它板块的数据不混入；与资讯组装后执行统一 16000 字符完整 input 限制。

### 一级指标评级明细表的数据要求

ESG 板块的“图表N 一级指标评级明细”使用独立明细行，展示列固定为“所属子项、一级指标、评分”。MQL 主路径应在已配置的 ESG 详情来源中检索并读取最新有效 `UPDATEDATE` 对应的明细行，按当前企业证券代码及固定评级机构“中诚信绿金”限定主体和口径。`所属子项`、`一级指标`、`评分`的 MQL 绑定名必须以该次 `Search_Context` 的 reportFields 和 MQL Runtime 可绑定字段为准，映射到这三个展示列；不得从 `ESG_SCORE`、E/S/G 汇总分或其它汇总字段推造指标明细。

已验证的一级指标明细 MQL 报表为：`Choice报表\\报表指标\\Choice金融终端\\API专题报表函数\\A股\\F9\\ESG\\ESG-明细弹窗接口|RPT_DETAILS_WID`。该报表支持 `SetCodes(<证券代码>)`，按 `更新日期` 过滤，实际可绑定字段为“所属子项中文”“一级指标名称”“一级指标得分”“更新日期”。执行时先取明细返回的日期并选择与当前汇总口径一致的最新有效日期；若汇总口径与明细最新日期不一致，不能直接混用日期，应先按共同日期复核。评分为空的明细行不生成图表行，其它有效行可生成“一级指标评级明细”表格。仅当该明细候选及同业务 MQL 候选均不可用时，才使用同源 REST 兜底。

2026-09-30 固化模板键 `esg_level1` 使用完整路径 `Choice报表\报表指标\Choice金融终端\API专题报表函数\A股\F9\ESG\ESG-明细弹窗接口|545851408591004`。中创智领 `601717.SH` 截至系统日查询返回676行历史明细，明细自身最新日期2026-04-30有16条，但中诚信绿金汇总最新日期为2024-12-31，不能直接配对。已核对两者共同日期2024-12-31：53条原始明细按所属子项与一级指标去重后20项、无同键评分冲突。正式整理仅选择与汇总一致的日期和机构，按证券、更新日期、所属子项、一级指标去重；同键不同分值不能任意保留一条。不得把676条跨期记录全部放进最新一期表。完整 MQL 见 [固定模板](mql-templates.md)。

#### `{{资讯}}` mx-finance-search 查询

ESG 分析板块的 `{{资讯}}` 必须使用 `mx-finance-search`，query 格式固定为：

```text
<企业全名> ESG 相关资讯 最新动态
```

示例：

```text
合肥芯碁微电子装备股份有限公司 ESG 相关资讯 最新动态
```

资讯结果整理为当前板块专属 `block_news_package`，只传入 `esg.md` 的 `{{资讯}}`。优先保留 ESG 报告、环境治理、员工与安全、产品责任、公司治理、合规处罚和相关争议动态；不得将该资讯包传给其它板块。

`block_news_package` 登记要求：

```json
{
  "block_name": "ESG分析",
  "prompt_file": "references/analysis-prompts/esg.md",
  "news_queries": [
    {
      "query": "<企业全名> ESG 相关资讯 最新动态",
      "tool": "mx-finance-search",
      "purpose": "ESG政策、环境、社会、治理和争议事项补充"
    }
  ],
  "sources": [
    {
      "block": "ESG分析",
      "placeholder": "{{资讯}}",
      "path": "mx-finance-search",
      "dataset": "<企业全名> ESG 相关资讯 最新动态",
      "status": "ok"
    }
  ]
}
```

#### Python REST 兜底

仅当 ESG 分析板块的正式路径、`RPT_ESG_STOCK_CODE`/`RPT_DETAILS_WID` 等已验证候选及本次 `Search_Context` 发现的同业务 ESG 候选均失败、超时或关键字段缺失时，才允许使用以下 REST 函数作为同板块兜底：

```text
reportName=RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS
columns=SECUCODE,SECURITY_CODE,SNAME,@ORG_CODE;@ORG_CODE,ORG_NAME,USCC,
INDUSTRY,INDUSTRY_CODE,INDUSTRY_TYPE,INDUSTRY_TYPE_CODE,ESG_ORG,UPDATEDATE,
ESG_RATING,ESG_RATING_MID,ESG_SCORE,ESG_SCORE_AVG,ESG_SCORE_MID,ESG_SCORE_RN,
ESG_STDSCORE,INDUSTRY_NUM,E_SCORE,E_RATING,S_SCORE,S_RATING,G_SCORE,G_RATING,
ESG_MANAGE_SCORE,ESG_RA_SCORE,SOURCE_TYPE,SECUCODE2,ESG_RATING_T
filter=(SECUCODE="<SECUCODE>");(ORG_CODE="")(UPDATEDATE>='1900-01-01')
(UPDATEDATE<='<系统日 yyyy-MM-dd>')(INDUSTRY_TYPE_CODE="0203")
(ESG_ORG="中诚信绿金")
sortColumns=UPDATEDATE&sortTypes=-1&pageNumber=1&pageSize=200&client=SW&source=choice
```

Python 兜底必须同时完成以下处理：

- 以 `ESG_SCORE` 非空作为 ESG 范围主判定，`0` 不视为空；若前置判定已确认在 ESG 范围内但 ESG 分析明细无法取得，应记录失败，不得用其它板块数据替代。
- 以 `UPDATEDATE` 降序选择最新有效汇总记录，并对明细返回的 `UPDATEDATE` 去重；相同日期只保留一条日期记录。
- 最终传入 `esg.md` 的 `block_data_package` 仅包含 ESG 汇总/评级构成字段和去重后的 `UPDATEDATE`，不得把完整 REST 行、证券筛选候选或其它板块字段混入。

