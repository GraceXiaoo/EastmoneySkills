# 企业深度研究通用数据源规则

本文件用于维护 `enterprise-deep-research` 的本地化取数方案。本技能不调用服务端一页纸生成接口。前 14 个原始数据板块的 `{{数据}}` 均按“用户确认的正式 MQL 路径 → 已验证的同业务 MQL 回退路径 → 本次运行通过 `Search_Context` 找到并验证的同业务 MQL 候选 → 本地 Python REST 兜底”的顺序获取结构化数据。前 14 个板块的 `{{资讯}}` 均应通过 `mx-finance-search` 获取公告、研报、新闻、政策或舆情材料，再用本地 prompt 成文。`重点关注`不取原始数据、不取资讯，只接收前 14 个板块已经生成的分析正文。

## MQL 实际字段名约束

- MQL 脚本中的 `REPORT_FIELD("...")`、`SetReportFilter()`、`FILTER_ROWS()` 和指标参数名，必须使用本次 `Search_Context` 与 MQL Runtime 实际可绑定的字段名/参数名；对报表候选，优先采用运行时返回的 `column_name_cn` 字段名（例如信用分析报表中的 `公司代码`、`最新主体评级`），不能把 Python REST 字段别名直接写进 MQL。指标候选使用实际 `parameters[].name`。
- `reportFields[].column_name`、用户给出的 Python REST 字段名、数据源文件中的本地逻辑标记和 `display_field_map` 只用于元数据识别、查询后整理、展示和提示词传入；只有被本次运行时确认可绑定的 MQL Runtime 字段名才能写入 MQL。
- 本文的 MQL 代码块只允许使用已由 `Search_Context` 核对过的实际字段；若某个字段、完整报表路径、过滤列或枚举值尚未核对，必须保留为“待 Search_Context 确认”，不得用中文别名或经验字段替代。

本文件当前固化通用取数原则、数据集状态与内部审计元数据规则、板块数据源配置位置和可复用的已验证报表。固定 MQL 样例集中见 [mql-templates.md](mql-templates.md)，各板块的具体取数配置分别维护在同目录的板块文件中，后续用户提供某个板块需要查询的表、字段、过滤条件和判断逻辑时，按对应板块文件补充，不要改动用户给定字段语义。

## 已验证执行边界

- 先按模块读取 [MQL核验记录](mql-verification.json) 中的对应 `queries`、`unresolved_metadata` 和 `rest_checks`。配置完成、元数据已发现、执行成功且零行、部分字段成功、完整需求通过是不同状态；`ok=true` 仅代表对应单条核验查询成功，不代表整个板块完整通过。
- 首次 `Search_Context` 原样传回业务知识的全部 typeCodes；缺失报表若属于 `typeCodes=[]`，补调不限类型检索。不要每个报表都重新获取语法参考。
- 当前 Execute_MQL 工具声明的 Runtime 为 2.6.0，参考要求也是 2.6.0。固定模板已按该版本实际执行结果固化；集合条件优先使用已验证的 `IN`，具体报表拒绝时才拆成 `OR` 等值比较。非等值使用 `<>`；日期 NULL 分支的限制见企业类型文档。
- 同名报表路径不能仅凭函数后缀互换。工商信息、关联交易、信用分析当前采用已验证的不带函数后缀路径；保留本次元数据与执行证据，版本变化后复核。
- 机构代码不是固定 8 位。芯碁微装实体为 `10000069733.FXR`，机构代码必须保留为 `10000069733`，不截断、不补位。
- 查询错误或关键列缺失记为 `failed` 或 `partial`，不能记为 `empty`；只有成功完成且无行才是空结果。类型判定失败且兜底失败时保持未完成，不生成虚假的 false。
- 不通过删除业务筛选、关键列或跨市场去重条件来宣称“链路已通过”。同源部分字段可保留，但必须在内部底稿明确未取得的字段，不能将缺失说明写入正式报告。

## 前 14 个板块统一执行要求

以下各板块数据源文件中的“当前可参考”报表，不代表可以直接通过 REST 取数。实际生成报告时，先读取 [mql-templates.md](mql-templates.md) 中当前板块的固定模板键，并通过 `scripts/render_mql_template.py` 仅替换企业代码、证券代码和日期；模板没有覆盖、字段已变化或固定模板执行失败时，再通过 `Get_MQL_Reference → Search_Business_Knowledge → Search_Context → Execute_MQL` 动态核验同一查询。主路径失败后，必须继续尝试该数据集已登记的同业务 MQL 候选，并在必要时用 `Search_Context` 动态检索、验证等价候选；只有全部同业务 MQL 候选失败、超时或缺关键字段时，才使用该板块配置的 Python REST 兜底。前 14 个板块的 `{{资讯}}` 需按对应文件配置的 `mx-finance-search` 查询主题执行；第 15 个重点关注板块不适用原始报表和资讯要求。前 14 个数据板块应至少登记：

1. `{{数据}}` 的 MQL 报表/指标路径；
2. MQL 过滤主体、报告期/日期和排序口径；
3. 该板块允许进入 `block_data_package` 的字段白名单；
4. 空值、单位、重复行和主体匹配规则；
5. `{{资讯}}` 的 `mx-finance-search` 查询主题、时间范围和资讯类型；
6. 仅供内部审计使用的数据集状态，并标明数据集用于 `{{数据}}` 还是 `{{资讯}}`。

未配置上述信息的板块，不得凭旧版服务端逻辑或其他板块数据临时生成；应说明该板块的数据源配置尚未完成。

## 通用取数原则

- 所有企业级结构化查询都必须先识别目标企业的 完整机构代码（`ORG_CODE` / `ISSUE_CODE`）；该结构化查询结果只能进入对应板块 prompt 的 `{{数据}}`。
- MQL 路径是唯一主取数路径。已固化模板的标准顺序为：识别实体和变量 → 读取对应模板键 → `render_mql_template.py` 渲染 → `Execute_MQL`；未固化模板、模板失效或字段变化时，才使用 `Get_MQL_Reference → Search_Business_Knowledge → Search_Context → Execute_MQL` 生成候选。企业类型判定和每个已选分析板块必须分别形成查询并执行；同一次任务可共享已成功的语法和业务知识上下文，缺失元数据才补查，不得把 REST 示例当作主路径。
- **同业务多路径回退**：用户确认的原始路径和函数名必须保留为该数据集的第一候选，不能因当前版本暂时无法召回或执行失败而删除。若第一候选出现元数据错误、执行失败、关键字段无法绑定或返回结果不满足该数据集的有效性要求，必须继续使用 `Search_Context` 在相同业务主题下检索候选报表/指标，并按“业务语义一致、主体字段可过滤、所需字段可绑定、已实际执行成功”的顺序逐一尝试。候选回退仍属于 MQL 主路径，不得直接跳到 Python。只有全部已确认的 MQL 候选均失败、超时或缺关键字段时，才使用该数据集配置的 Python REST 兜底。
- **候选选择与隔离**：每个数据集只选择一个最终有效来源；同一数据集不同候选的结果不得未经核对直接拼接、相加或互相补列。可以在内部审计中保留候选尝试记录，但传入 prompt 的 `block_data_package` 只包含最终选定来源及其明确返回的字段。若主路径恢复可用，下次仍优先使用主路径；回退路径不得永久覆盖主路径。
- **候选链执行顺序**：每次运行都重新从第一候选开始。已验证候选按板块文件登记的顺序执行；登记候选不足时，才由 `Search_Context` 检索同业务候选。动态候选必须同时满足业务语义一致、主体过滤可用、关键字段可绑定、实际执行成功四项条件，不能仅凭报表名称相近采用。某个候选成功且满足数据集有效性要求后立即停止该数据集的候选尝试，不再用后续候选补列或混合结果。
- 首次 `Search_Context` 必须原样带回全部 `typeCodes`；实体识别时优先取发行人实体（typeCode 248，代码形如 `10169711.FXR`，仅去掉 .FXR 后缀作为机构代码，保留完整数字部分）。A 股证券实体（如 `688223.SH`）仅作交叉参考，其 6 位证券代码不是机构代码。
- 只有 `Execute_MQL` 返回的数据才能作为 MQL 结构化事实依据。
- 企业类型判定是报告路由的关键前置数据集，必须先由 MQL MCP 取回 ESG、城投、科创、发债人四类判定字段。Python REST 只允许在 MQL 不可用、执行报错或关键字段缺失时作为同源兜底。
- MQL 工具不可用，或主路径、已验证候选和本次动态发现的同业务 MQL 候选均执行报错、超时或缺少关键日期/金额/主体标识时，才允许将对应板块、对应数据集切换到本地 Python REST 兜底；兜底结果仍须拆分到该板块的独立数据包。单一路径失败不构成 Python 兜底条件。
- Python 兜底仅允许调用 Choice/东财结构化数据接口并输出本地 JSON 数据底稿；不得调用企业一页纸服务端生成接口。
- 资讯检索统一使用 `mx-finance-search`，检索结果只能进入对应板块 prompt 的 `{{资讯}}`。资讯不得替代 MQL 结构化取数；资讯中的数值、评级、债券余额、司法金额等结构化事实，除非 prompt 明确要求“资讯口径”，否则不得覆盖 `{{数据}}` 中的数据库指标。
- 用户后续提供的板块专属报表、字段、过滤条件优先于本文中“可复用报表”的通用建议。
- 前 14 个原始数据板块的数据源必须逐板块登记、逐板块取数、逐板块形成独立数据包。即使多个板块使用同一张表，也必须在对应板块下分别列明字段用途，传入 prompt 前拆成各自字段子集。`重点关注`不建立原始 MQL 数据集。
- 前 14 个板块的 MQL 查询必须使用该板块自己的查询任务和字段白名单；允许一次 MQL 返回同一板块的多个数据集，但不得将不同板块的字段、行或分析中间结果作为一个未拆分的输入包。`重点关注`只在前 14 个板块成文后组装本地分析结果交接包。
- 各板块数据源文件中出现的 REST 报表、URL、字段列表，除非明确标注为 MQL 路径，否则均为字段语义参考或 Python 兜底模板；执行报告时不得据此绕过 MQL。

## 数据集状态与内部审计元数据

生成报告前必须维护数据集状态表，用于执行排错、资讯排序和输入截断。该表只保存在内部底稿中，不传入分析 prompt，也不输出到报告正文：

| 字段 | 说明 |
|---|---|
| `source_id` | 可选的内部数据集标识，不得传入分析 prompt 或报告正文 |
| `block` | 使用该来源的报告板块 |
| `path` | `MQL`、`Python REST fallback`、`mx-finance-search`、`用户提供数据` 等 |
| `placeholder` | 来源用于 `{{数据}}`、`{{资讯}}` 或前置判定 |
| `dataset` | MQL 报表名、REST 报表名、mx-finance-search query 或用户文件名 |
| `filter` | 关键筛选条件 |
| `as_of` | 数据日期、报告期、公告日或抓取时间 |
| `status` | `ok`、`partial`、`empty`、`fallback`、`failed` |
| `notes` | 单位、口径、异常字段或兜底说明 |

分析正文按 [句内溯源规则](../analysis-prompt.md#句内溯源规则) 使用实际材料对应的原生可点击引用。平台/工具返回的原始引用与本地审计编号须区分：前者随对应材料保留，后者不能冒充引用；内部状态表本身不作为成文内容。

### 空值与正式成文

- 原始包保留真实空值和查询状态，完成应有的 MQL 补取及 Python 兜底后再判断哪些材料可用于成文；不得为了省略缺失说明而跳过取数、将失败改记为空或更改企业类型判定。
- 传入 prompt 的业务表格可保留空单元格以维持行列、主体、日期和单位对应关系，但不得把空值渲染成“某字段为空”“未披露”等分析句，也不得把 `errors`、失败原因或字段完整性诊断拼入 `{{数据}}`、`{{资讯}}`。不改变既有完整信源截断规则，不把空值填为零。
- 有效值 `0` 或明确业务否定值不按空值丢弃；只有标识字段或全空业务指标的记录不算有效分析材料。部分材料为空时，使用本板块其余有效数据和资讯；两者均不可用时按 prompt 返回内部空结果，正式输出见 [成文输出检查](../analysis-prompt.md#成文输出检查)。
- “字段缺失”和“公司未发生该事项”必须区分；空值或空查询结果本身不能证明无评级、无债券、无担保或无风险。即使存在明确的零值，也只能表述该字段定义及覆盖范围内的事实，不能推断企业没有相关需求。

## 板块输入包规范

每个板块 prompt 至少有两个输入通道：

| 占位符 | 输入包 | 主来源 | 兜底/失败处理 |
|---|---|---|---|
| `{{数据}}` | `block_data_package` | MQL MCP（正式路径或同业务候选） | 全部同业务 MQL 候选失败后才用同板块 Python REST fallback；兜底仍失败则该板块按 prompt 的空数据规则处理 |
| `{{资讯}}` | `block_news_package` | `mx-finance-search` | 检索失败则该板块资讯包记为空或 failed；不得用其它板块资讯替代 |

两个输入包必须分别生成、分别维护内部状态，传入 prompt 时渲染本板块材料、必要业务元数据及实际返回的原始引用绑定。内部 `sources` 审计表、本地自编 `source_id`/`source_ids`、查询错误及日志不进入 prompt；下列 JSON 中的 `sources` 仅用于底稿兼容，真实原始引用按工具返回格式保留，不从本地编号或报表名推造。不得把 `block_data_package` 合并进 `block_news_package`，也不得把资讯检索正文混入 `{{数据}}`。

### 板块数据包规范

每个被路由选中的前 14 个原始数据板块，都必须先通过 MQL 形成独立的 `block_data_package`，再传入对应 prompt。重点关注使用独立的本地分析结果交接包，规则见其数据源文件。建议结构如下：

```json
{
  "block_name": "基本情况",
  "prompt_file": "references/analysis-prompts/basic-info.md",
  "entity": {
    "org_code": "<机构代码>",
    "org_name": "<企业全称>"
  },
  "route_flags_allowed": {
    "is_esg_scope": true,
    "is_urban_investment": false,
    "is_sci_tech": true,
    "is_bond_issuer": false
  },
  "datasets": [
    {
      "dataset": "<MQL报表或指标路径>",
      "query_path": "MQL",
      "fields": ["<仅本板块需要的字段>"],
      "filter": "<本板块过滤条件>",
      "rows": []
    }
  ],
  "sources": [
    {
      "source_id": 1,
      "block": "基本情况",
      "placeholder": "{{数据}}",
      "path": "MQL",
      "dataset": "<MQL报表或指标路径>",
      "status": "ok"
    }
  ]
}
```

强制规则：

- `block_name` 必须等于当前路由板块名，使用 `references/analysis-prompt.md` 映射表中的完整名称；最终报告标题可按输出规范使用中文序号和展示板块名，不能反向改写 `block_name`。
- `prompt_file` 必须与 `references/analysis-prompt.md` 中该板块映射一致。
- `datasets[].fields` 只能包含该板块在本文对应章节登记的字段；不得把其它板块字段打包传入。
- `datasets[].query_path` 首选且默认必须为 `MQL`；只有该数据集的主路径及同业务 MQL 候选均失败后，才可改为 `Python REST fallback`，并在 `errors` 或内部状态表中说明失败原因。MQL 候选回退仍标记为 `MQL`，同时在内部审计记录实际采用的候选路径。
- 一个 `block_data_package` 只能服务一个 prompt。即使底层 MQL 查询同时返回多个板块字段，也必须复制为多个板块数据包，并删除当前板块不需要的字段后再传入。
- 未完成当前板块 MQL 取数或对应 Python 兜底前，不得读取该板块 prompt 生成正文；不得使用其他板块已经取到的数据代替当前板块数据。
- `sources[].block` 必须等于当前板块名。若一次 MQL 结果被多个板块复用，应按板块拆分内部审计条目，并在各板块数据包中分别记录同一查询的字段子集。
- Python 兜底输出也必须按上述结构拆包后传入 prompt，不能把完整 JSON 底稿直接喂给所有板块。

### 板块资讯包规范

每个被路由选中的前 14 个原始数据板块，如对应 prompt 含 `{{资讯}}` 或该板块配置了资讯需求，都必须使用 `mx-finance-search` 形成独立的 `block_news_package`。重点关注不建立资讯包。建议结构如下：

```json
{
  "block_name": "所处行业",
  "prompt_file": "references/analysis-prompts/industry.md",
  "entity": {
    "org_code": "<机构代码>",
    "org_name": "<企业全称>"
  },
  "news_queries": [
    {
      "query": "<企业全称> 所处行业 最新政策 研报 新闻",
      "tool": "mx-finance-search",
      "purpose": "行业背景与近期动态",
      "time_range": "<如 prompt 或板块配置要求>"
    }
  ],
  "items": [
    {
      "title": "<资讯标题或摘要标题>",
      "content": "<mx-finance-search 返回正文或摘要>",
      "source": "<媒体/公告/研报来源，如返回可得>",
      "published_at": "<发布时间，如返回可得>",
      "query": "<对应检索 query>"
    }
  ],
  "sources": [
    {
      "source_id": 2,
      "block": "所处行业",
      "placeholder": "{{资讯}}",
      "path": "mx-finance-search",
      "dataset": "<检索 query>",
      "status": "ok"
    }
  ]
}
```

强制规则：

- `block_news_package.block_name` 必须等于当前路由板块名，使用 `references/analysis-prompt.md` 映射表中的完整名称；最终报告标题可按输出规范使用中文序号和展示板块名，不能反向改写 `block_name`。
- `news_queries[]` 必须围绕当前板块 prompt 的资讯需求设计；不得用“一家公司最新消息”这类全局查询结果替代全部板块。
- `items[]` 只能包含当前板块检索得到的资讯正文、摘要和元数据；不得放入 MQL 原始表格或其它板块资讯。
- `sources[].placeholder` 必须为 `{{资讯}}`，`sources[].block` 必须等于当前板块名。`sources` 仅用于内部审计；资讯标题、正文、日期、单位、来源分类与权威度保留在输入中，实际返回的可解析引用随对应资讯传入 prompt，引用与原始材料的绑定保持不变。
- `mx-finance-search` 返回空或失败时，保留空 `block_news_package` 并登记 `empty` 或 `failed`；不得编造资讯，不得用其它板块资讯补位。
- 资讯中的数值、评级、债券、司法、财务指标必须与 `{{数据}}` 中的结构化结果区分口径；两者冲突时，结构化数据库事实优先，资讯仅用于背景、事件、公告和舆情描述，除非 prompt 明确要求披露资讯口径。
- 全部 15 个模块的最终完整 input 分别执行 16000 字符硬上限。按“专业数据库数据优先 → 权威度由高至低 → 发布时间由近及远”对当前模块信源排序；加入第 N 条超限即剔除第 `[N, ∞)` 条，不能切片或跳过后补。数据与资讯仍写入各自占位符，完整原始包留在底稿；重点关注以完整前序分析结果为单元。具体排序字段、长度计算、固定内容超限处理和内部审计要求见 [news-processing.md](../news-processing.md)。


## 融资变化可复用数据源

若后续板块需要融资变化数据，可参考 `corporate-financing-analysis/references/data-sources.md` 的已验证表：

- `RPT_ORGF9_FINANCE_DYNAMICS`：融资动态；
- `RPT_CUSTOM_ORGF9_INVFIN_SECURITY`：发行股票信息；
- `RPT_CUSTOM_BOND_BS_SAMEISSUER`：发行债券/ABS；
- `RPT_ORGF9_FINANCE_DETAIL`：直接融资明细；
- `RPT_ORGF9_IFINANCING_DETAIL`：间接融资明细；
- `RPT_BOND_REGISTERQUOT`：项目及注册额度明细；
- `RPT_BOND_BORBANK`：银行借款；
- `RPT_BOND_FINLEASES`：融资租赁；
- `RPT_BOND_TRUSTFINA`：信托融资；
- `RPT_BOND_ACCOUNTFINA`：应收账款融资/保理。

使用时必须遵守原技能的单位和状态规则：注册额度不等于已融资；融资租赁/应收账款融资中的 `ASSET_VALUE` 不得当作融资金额；存量、流量、累计额不得相加。

## Python 兜底脚本要求

本技能的 Python 兜底脚本应满足：

- 只做实体解析、REST 取数、单位归一、JSON 落盘和摘要输出；
- 不生成整篇报告，不调用企业一页纸服务端接口；
- 输出 JSON 可保留全局 `datasets` 作为调试底稿，但生成正文时只能使用 `selected_blocks` 和 `block_data_packages`；不得把全局 `datasets` 直接传给 prompt；
- 前 14 个原始数据板块的 `block_data_packages` 必须按已选板块一一生成，每个包只能服务一个板块 prompt，全部同业务 MQL 候选失败时的 `query_path` 才标记为 `Python REST fallback`；`重点关注`的唯一数据包 `key_concerns_context` 使用 `local analysis handoff`，不得标记为 MQL 或 Python 兜底；
- 每个数据集独立记录 `ok/empty/failed`，失败原因写入 JSON 的 `errors`；
- 网络超时或 5xx 可重试，但总重试超过 10 次必须失败退出；
- 退出码：`0` 表示至少一个数据集成功，`1` 表示参数错误，`2` 表示网络或业务失败。


