# MQL 取数规程（本 skill 数据层主通道）

> 本 skill 主取数链路为 **MQL（妙想查询语言）**，覆盖 **0 前置 + 章节 3/4/5/6/7/8 的表格与图表数据**。
> **不再**调用妙想 MCP 中台的 HTTP 取数接口（`datacenter-choice.eastmoney.com`），**不再**构造 URL、`reportName` / `columns` / `filter` 参数。
> 取数 = **检索上下文 → 生成 MQL 脚本 → Execute_MQL 执行 → 拿结构化结果**。
>
> 例外通道：**全部 9 个章节的「文字描述部分」**走妙想 MCP 工具 `mx_finance_search`（11 个场景），规程见 `资讯检索-取数规范.md`。
> 两个通道**按内容类型分工**，互不替代：资讯接口不取结构化表，MQL 不写文字描述。
>
> **⚡ 零检索快车道（v2.2.0 新增）**：若目标报表命中 [MQL-报表路径固化表](MQL-报表路径固化表.md)，
> 可直接跳过 `Search_Business_Knowledge` 与 `Search_Context`，用固化路径直取（见 §2A）。

## 1. 参与的唯一 MCP 服务

| 服务 | 类型 | 工具 | 职责 |
|---|---|---|---|
| `mcp-mql-tools` | 远程 Streamable HTTP | `Get_MQL_Reference` | 取 MQL 生成参考、执行器参考、全局约束 |
| | | `Search_Business_Knowledge` | 确认品种（varieties）、业务知识、typeCodes |
| | | `Search_Context` | 检索证券、板块、指标、报表、宏观、时间上下文 |
| | | `Execute_MQL` | MQL 校验 + 元数据准备 + 取数 + 计算（唯一执行入口） |

检索与执行**同属 `mcp-mql-tools` 一个服务**，不再需要单独的 runtime 服务（旧 `mcp-mql-runtime` 本地 stdio 服务已取消）。

成本提示：`Search_*` 与 `Execute_MQL` 均为计费调用。
**同一次报告任务内，`Get_MQL_Reference` 与 `Search_Business_Knowledge` 各调用一次即可**；后续补充检索只重复 `Search_Context`。
**若目标对象命中 [MQL-报表路径固化表](MQL-报表路径固化表.md)，则 `Search_Business_Knowledge` 与 `Search_Context` 全部免去**（见 §2A），只需 `Get_MQL_Reference` 做版本校验。

## 2. 强制工作流（每次生成报告）

本 skill 有**两条并行工作流**，按目标对象**是否命中固化表**二选一。

### 2.0 先查固化表（决定走哪条）

**开工第一步**：打开 `reference/MQL-报表路径固化表.md`，对照本次要取的报表。

- **命中** → 走 §2A **零检索直取**（省去 S1 + S2）
- **未命中** → 走 §2B **标准工作流**（完整检索）

> 固化表收录的是 2026-10-01 实测确认的 F9 常用报表（沪深京 9 类 + 港股 7 类），
> 覆盖章节 0/3/4/5/6/7/8 的表格与图表数据。

### 2A. 零检索直取（命中固化表时）

```
S-1 版本校验 ── Get_MQL_Reference.requiredRuntimeCompatibilityVersion  vs  Execute_MQL 工具描述里的"MQL 执行器版本"
  │
S0  读参考   ── Get_MQL_Reference（一次）→ workflow / mqlReference / executorReference / globalConstraints
  │             ⚠️ 本步不可省：全局约束第 1 条要求版本校验
  │
S1/S2 跳过 ── 路径 / 字段中文名 / 加载列枚举 全部取自《MQL-报表路径固化表》
  │
S3  生成并执行 ── 按固化表拼装 MQL 脚本 → Execute_MQL
  │     产出：各 Block 的 columns + rows（超过阈值时落 result_file，读文件）
```

**生成方式（推荐，禁止手写 Block）**：
`python scripts/mql_api.py --script <批次名> --code <SECUCODE>` 一次生成整段可执行 MQL——
**Block 编号由脚本连续分配（1..N）**、**加载列条件按固定顺序写出**；生成后可用 `--check` 自检，
从源头消除"编号跳号 + 参数乱序"的语法返工。用法与脚本名清单见 `取数脚本一次成型.md`
（**脚本名与 §8 的批次编排对应，改动须两处同步**）。

成本口径：检索调用由 3 类（`Get_MQL_Reference` + `Search_Business_Knowledge` + `Search_Context`）
降为 1 类（仅 `Get_MQL_Reference`）。

**硬约束**：
- 路径必须从固化表**原样复制**（含末尾 `|metricId`），不得改写、不得去 ID。
- 字段中文名必须从固化表**逐字复制**，不得写物理列代码，不得自造。
- 若固化表已给出加载列枚举（如港股「报告期类型编码」），可直接写 `SetReportFilter`。
- 一旦 `Execute_MQL` 报路径/字段错误 → 立即按 §2B 回退检索，**不得**在固化表外猜路径。

### 2B. 标准工作流（未命中固化表时）

```
S-1 版本校验 ── Get_MQL_Reference.requiredRuntimeCompatibilityVersion  vs  Execute_MQL 工具描述里的"MQL 执行器版本"
  │
S0  读参考   ── Get_MQL_Reference（一次）→ workflow / mqlReference / executorReference / globalConstraints
  │
S1  品种与业务知识 ── Search_Business_Knowledge（一次）
  │     入参：varieties + user_query（照原句）+ query_rewrites（2~3 条）+ keywords
  │     产出：varieties、typeCodes、Business_Knowledge
  │
S2  上下文检索 ── Search_Context（可多次补调）
  │     首次：必须原样全量传入 S1 返回的全部 typeCodes，且一次性提交全部已知分区
  │     产出：证券实体、指标候选（indicatorPath / indicatorTimeShape / unit / parameters / reportFields / reportFilterColumns）、报表候选
  │
S3  生成并执行 ── 按候选拼装 MQL 脚本 → Execute_MQL
  │     产出：各 Block 的 columns + rows（超过阈值时落 result_file，读文件）
```

**中断规则**：`Get_MQL_Reference` 未成功返回 → 不得生成或执行任何 MQL，也不得调用后续检索。

## 3. 版本校验细则

- `requiredRuntimeCompatibilityVersion`（当前为 `2.6.0`）来自 `Get_MQL_Reference`。
- 必须从**将要调用的 `Execute_MQL` 工具描述**里读取"MQL 执行器版本"，按 `x.y.z` 逐段数值比较。
- 未找到 `Execute_MQL` 工具、或未读到版本 → 向用户说明双方版本（未知则明确写"未读取到"）并**立即停止**，不得生成、修改或执行 MQL。
- 要求版本 **高于** 实际版本 → 说明两边版本并建议升级 `mcp-mql-tools` 服务，**仍继续**后续工作流。
- 要求版本 **低于或等于** 实际版本 → 直接继续（执行器新版本兼容低版本语法）。

## 4. 本 skill 的检索入参固定口径

| 参数 | 沪深京链路 | 港股链路 |
|---|---|---|
| `varieties` | `["沪深股票"]` | `["港股"]` |
| `user_query` | 本次公司的一句完整需求原句（如"生成宁德时代300750.SZ的公司一页纸报告"） | 同左（换公司/代码） |
| `query_rewrites` | 2~3 条非口语化改写句 | 同左 |
| `keywords` | 业务词数组，见分章节清单「检索词」列 | 同左 |
| `Search_Context.typeCodes` | 用 `Search_Business_Knowledge` 返回的**全部** typeCodes（实测 `["1","2","3","4","5","6","203","216","222","236"]`） | 用返回的全部 typeCodes（实测 `["71","72","73","74","79"]`） |
| `searchEntity.words` | `["<SECUCODE>", "<公司名>"]` | 同左（如 `["09992.HK","泡泡玛特"]`） |
| `searchIndicator.keys` | 分章节清单给出的检索词 | 同左 |

硬性要求：
1. 首次 `Search_Context` 必须**原样全量**传入 typeCodes，不得按局部关键词自行剪裁。
2. 首次 `Search_Context` 应把 `searchSector` / `searchEntity` / `searchIndicator` / `timeRecognition` 等**已知分区一次提交**，避免多轮往返。
3. 后续补检索可只传变化的分区；类型范围不变时继续传当前范围的完整 typeCodes。
4. 空结果或分区失败**不算已确认**，不得据此编造路径。

## 5. 检索结果 → MQL 的三条路由

| 候选特征 | 判定 | 生成方式 |
|---|---|---|
| `type = "指标"` | 普通指标 | 按 `indicatorTimeShape` 选 `CrossSectionBlock`（`cross_section`）或 `TimeSeriesBlock`（`time_series`） |
| `type = "报表"`（含 `reportFields` + `matchedReportFields`） | 报表 | `ReportBlock` + `REPORT_FIELD("中文返回列名")`，**不得**写成普通指标调用 |
| `type = "指标标准值"` | 某指标的枚举标准值 | 只用于该关联指标的 `FILTER_ROWS` 比较值，**不得**当指标路径调用 |

## 6. Block 选择（本 skill 常用）

| 取数目标 | Block | 说明 |
|---|---|---|
| 主营构成、财务摘要、员工构成、研发支出、专利、高管、一致预测 | `ReportBlock` | 一次取回多报告期/多行 |
| 前五名客户/供应商（5.1/5.2） | `ReportBlock` | **📌 已固化**：`主要客户情况和主要供应商情况`；证券范围由 `SetCodes(["<SECUCODE>"])` 承担，`SetReportFilter` 按**固定顺序**写 `IS_MAXREPORTDATE == 1` → `REPORT_DATE == "<Y-M-D>"` → `TYPE == "客户\|供应商"`（该报表共 4 个加载列，其中 `SECUCODE` 走 `SetCodes`、不重复写进筛选），**零检索直取**；旧的 `CrossSectionBlock` 5 个名次指标写法**已停用** |
| 单年度研发人数、员工总数、实际控制人 | `CrossSectionBlock` | 用 `{年度}` / `{报告期}` 参数定位 |
| 多报告期指标序列（如近 5 年研发费用率） | `TimeSeriesBlock` | 路径末尾 `metricId` 以 `_s` 结尾 → 只能 `{周期}="季"/"年"`，且不写 `{市场类型}` |
| 港股历史汇率 | `ReportBlock`（`RPT_HK_HISTORY_EXRATE`）或 `TimeSeriesBlock` | 视候选形态而定 |
| 分组统计、补列 | `GroupBlock` / `MergeBlock` | 按参考规则 |

## 7. 路径与名称硬规则（写错即校验失败）

1. **单反斜杠**：所有路径（指标、报表、板块、EDB）内部路径边界只能有一个实际反斜杠。`Search_Context` JSON 里出现的 `\\` 或 `\\\\` 是转义表示，**不得照抄数量**。
2. **花括号包裹路径**，不加双引号、不做字符串转义；路径末尾的 `|指标ID` 是路径内容，必须原样保留。
3. 字符串用双引号；`==` 用于比较，`=` 只用于私有赋值与参数绑定。
4. **报表字段只能用中文名**：`REPORT_FIELD("<reportFields[].column_name_cn>")`；`SetReportFilter` 只能用 `reportFilterColumns[].column_name_cn`。**不要**填写 `OPERATE_INCOME`、`REPORT_DATE` 之类物理字段代码——旧妙想 MCP 的字段名在 MQL 里不适用。
5. 需要按名称引用的返回字段，先定义为当前列（`{私有列} = REPORT_FIELD("…");` 或 `{输出列}: REPORT_FIELD("…");`）。
6. **数值字面量按指标的 `unit` 口径写**：`unit="元"` 时"221.47 亿"写 `22147000000`；`unit="%"` 时"5.23%"写 `5.23`。不得写业务单位后缀。
7. **报告期用动态函数字符串**：`{报告期} = "GetReportDate(1, \"Q4\")"`（最近 1 个年报）、`"GetReportDate(2, \"Q4\")"`（2 年前年报）；最新报告期可用选项 `"最新一期(MRQ)"`。选项原文来自候选的 `parameters[].options`。**表格类报告期集合（"最新报告期 + 近 5 个年报期"）与 8.1 历史年（近 3 个已披露年报）的完整规程见 §11**：一律通过传参/筛选条件表达，**禁止**执行后对报告期窗口做本地二次筛选去重（唯一例外：成表时 4.2 / 7.2 各自剔除「整列为空」的报告期列，见 §11.2 第 4 条）。
8. `ReportBlock` 的证券范围按 `reportStandardCodeSupported` 决定：`true` → 写一个 `SetCodes` 或 `GetSectors`；`false` → 禁止写，改为读代码相关列后用本地 `FILTER_ROWS` 过滤。
9. 每个 Block 至少一个输出列；编号唯一递增，只能引用更小编号。
10. 一条筛选优先写成一条 `FILTER_ROWS(...)`，位置在输出列之后、`Sort` 之前。

## 8. 本 skill 的取数批次编排

| 批次 | 内容 | 建议脚本形态 |
|---|---|---|
| 批次 0（仅港股） | 汇率：`RPT_HK_HISTORY_EXRATE` | 单独 `ReportBlock`，输出报告期/币种/汇率（未固化，需检索） |
| 批次 1（前置） | 取值范围 + 公司简介/最新报告期（含 `ORG_CODE`、`LISTING_STATE`、主营业务、发展历程、实际控制人） | 1~2 个 `ReportBlock` / `CrossSectionBlock`；命中固化表时 `--script 批次1` 一次成型 |
| 批次 2 | 章节 4（主营构成）、6（研发）、7（财务）、8（一致预测） | 可写在同一脚本内，多个 Block + `OutputBlock()` 一次执行；`--script 批次2` 一次成型 |
| 批次 3 | 章节 5（前五名客户 / 供应商，含"其他"二次计算） | **📌 已固化 `ReportBlock`**：`主要客户情况和主要供应商情况`，两个 Block 分别传 `TYPE="客户"` / `TYPE="供应商"`（加 `IS_MAXREPORTDATE=1` / `REPORT_DATE`），零检索直取；`--script 批次3 --report-date <YYYY-MM-DD>` 一次成型 |
| 批次 4 | 章节文字描述（11 个资讯检索场景） | **不走 MQL**，改调资讯检索接口（见 `资讯检索-取数规范.md`）；11 个场景无依赖 → **分 3 批并发提交（每批 3–4 个，规范 §10.1）**；归一化用 `scripts/news_api.py --all` 一次取全，与 MQL 批次无依赖 |

> 批次 1/2/3 的脚本名（`批次1` / `批次2` / `批次3`，另有 `章节3`–`章节8` / `全量` 别名）定义在
> `scripts/mql_api.py` 的 `SCRIPTS` 中，用法见 `取数脚本一次成型.md`。**本表与 `SCRIPTS` 必须一致。**

批次 2/3 之间无依赖时可合并为一次 `Execute_MQL`，但**报告期基准**必须先由批次 1 确定，再进入批次 2。
章节文字描述的资讯取数与 MQL 批次无依赖，可在批次 1 之后任意时点执行（建议与批次 2 并行准备）；
其 11 个场景彼此也无依赖，**检索按每批 3–4 个并发提交**（见 `资讯检索-取数规范.md` §10.1）。

> 注意：章节 2、9 在 MQL 侧确实"不取数"，但它们的**文字描述由资讯检索场景 `2` / `9` 供数**（v3.3.0 起），
> 不再由模型自行生成。同理章节 5、6 的港股 MQL 侧无数据，但其文字描述仍有场景 `5.1` / `5.2` / `6` 供数。

## 9. 失败与降级（与 `合规与降级.md` §4 一致）

- 检索不到候选 / 分区 `success=false` / 结果为空 → **不得编造路径或默认值**；该维度按零幻觉三级降级处理（删除 → 改述 → 标注）。
- `Execute_MQL` 返回 `ok=false` → 依据 `error` 的阶段与错误码定位 MQL 或已确认上下文；**不得**通过补写未知参数、指标或默认值规避错误。
- 单个 Block 失败不阻塞其它 Block 的结果；报告可交付，但须保证"取不到的维度绝不出现"。
- 大结果集会被写入 `result_file.path`，此时读文件而不是找 `rows`。

## 10. 旧妙想 MCP 通道 → MQL 对应关系（迁移备忘）

| 旧报表代码（妙想 MCP） | MQL 侧对应对象（基线，须以当次检索为准） |
|---|---|
| `RPT_F9_BASICINFO` | 报表 `Choice报表\报表指标\Choice金融终端\A股F9\头部标签\股票F9_首页基础数据|RPT_F9_BASICINFO` |
| `RPT_HSF9_BASIC_ORGINFO` | 报表 `…\A股F9\公司一页纸\前置接口\沪深F9_基础资料_公司介绍|RPT_HSF9_BASIC_ORGINFO` |
| `RPT_MAIN_BUSINESS` | 报表 `…\企业F9\企业一页纸\主营构成\主营构成_沪深|RPT_HSF9_FN_MAINOPBUSINESS_NORMAL` |
| `RPT_CUSTOM_F9_BASICINFO_SKBD_JOIN_BOND_FN_CUSTOMERN` | 报表 `Choice报表\报表指标\Choice金融终端\A股F9\公司一页纸\公司产销链分析\主要客户情况和主要供应商情况`（**📌 已固化**：`\|464277271454376`；传参 `SECUCODE` / `IS_MAXREPORTDATE=1` / `REPORT_DATE` / `TYPE=客户\|供应商`） |
| `RPT_HSF9_RDEXPEND` | 报表 `…\A股F9\公司一页纸\公司研发实力\沪深F9_财务附注_研发支出|RPT_HSF9_RDEXPEND` |
| `RPT_HSF9_BASIC_STAFFCOMPOSITION` | 报表 `…\A股F9\公司一页纸\公司研发实力\沪深F9_基础资料_员工构成|RPT_HSF9_BASIC_STAFFCOMPOSITION` |
| `RPT_PUBLIC_PAPER_PATENTTOTAL` | 报表 `…\A股F9\公司一页纸\公司研发实力\公司一页纸_上市公司专利信息|RPT_PUBLIC_PAPER_PATENTTOTAL` |
| `RPT_CUSTOM_ORGF9_FIN_SUMMARY` | 报表 `RPT_F10_FINANCE_MAINFINADATA` / F9 财务分析专题（利润表、现金流、杜邦、资本结构） |
| `RPT_HSF9_RES_CONSISPREDICT` | 报表 `…\A股F9\公司一页纸\公司盈利预测\股票F9_盈利预测_一致预测|RPT_HSF9_RES_CONSISPREDICT` |
| `RPT_DMSK_OS_MANAGER` | 报表 `…\A股F9\公司基本资料\历任管理层成员\沪深F9_发行资料_历任管理层成员|RPT_HSF9_ISSUEINFO_MANAGEMENT` |
| `RPT_HKF9_MAINOPBUSINESS` | 报表 `…\量化查数\企业\企业一页纸\主营构成\主营构成_港股|RPT_HKF9_MAINOPBUSINESS` |
| `RPT_HKF9_FN_MAINSUMMARY` | 报表 `…\企金工作台\港股\财务分析摘要\港股财务分析摘要|RPT_HKF9_FN_MAINSUMMARY` |
| `RPT_HK_HISTORY_EXRATE` | 报表 `…\企业F9\企业一页纸\主营构成\港股汇率|RPT_HK_HISTORY_EXRATE` |
| `RPT_HKF9_SECURITY_SECURITYINFO` | 报表 `…\港股F9\公司一页纸\公司一页纸_证券基本资料|RPT_HKF9_SECURITY_SECURITYINFO` |
| `RPT_HKF9_RES_STATISTICSAVG` | 指标族 `Choice指标\股票\港股及美股指标\盈利预测\盈利预测综合值(滚动)\…` |

> 该表仅用于**加速检索**（把"章节要什么数据"快速映射到该搜什么词）；每次任务仍必须由当次 `Search_Context` 返回的 `indicatorPath` 决定最终写法。

> **补充（v2.2.0）**：上表中已由 [MQL-报表路径固化表](MQL-报表路径固化表.md) 完成实测确认的对象
> （`RPT_HSF9_BASIC_ORGINFO` 对应公司介绍、`RPT_HSF9_RES_CONSISPREDICT` 对应一致预测、
> `RPT_HSF9_RDEXPEND`、`RPT_HSF9_BASIC_STAFFCOMPOSITION`、`RPT_PUBLIC_PAPER_PATENTTOTAL`、
> `RPT_MAIN_BUSINESS` 对应主营标准化平台、`RPT_HKF9_MAINOPBUSINESS`、`RPT_HKF9_FN_MAINSUMMARY` 等）
> **改为直接使用固化表中的完整路径，不再重新检索**。上表因此降级为"固化表未收录对象时的检索提示词来源"。

## 11. 报告期取值规程（已确认口径，传参实现）

> 一句话结论：**这两类表格的报告期取值逻辑可以通过传参（筛选条件 / 报告期参数）一次性表达，取数后不需要对报告期窗口做本地二次筛选或去重**；成表时两张表再**各自剔除「整列为空」的报告期列**（§11.2 第 4 条）。

### 11.1 适用范围（2 类表 × 2 市场 = 4 张表）

| 市场 | 表格 | 原口径报表（妙想，**仅作口径来源，不作为取数通道**） | 报告期取值逻辑 |
|---|---|---|---|
| 沪深京 | 分板块业务情况（4.2） | `RPT_MAIN_BUSINESS` | 近 5 年年报期 **∪** 最新报告期 |
| 沪深京 | 主要财务指标（7.2） | `RPT_CUSTOM_ORGF9_FIN_SUMMARY` | 近 5 年年报期 **∪** 最新报告期 |
| 港股 | 分板块业务情况（4.2） | `RPT_HKF9_MAINOPBUSINESS` | 近 5 年年报期 **∪** 最新报告期 |
| 港股 | 主要财务指标（7.2） | `RPT_HKF9_GSD_INCOME` / `RPT_HKF9_GSD_CASHFLOW` | 近 5 年年报期 **∪** 最新报告期 |

> **取数口径 vs 成表口径**：上表的「报告期取值逻辑」是**取数口径**（决定从报表里取哪几期）；成表时 4.2 与 7.2 两张表各自再按「整列为空即不展示」独立剔除报告期列，两表最终列集合**不要求一致**（见 §11.2 第 4 条）。
>
> 原口径报表代码与字段仅用于**理解取值语义**（尤其确认"年报类型枚举"与"最新报告期标志"两件事）。取数仍必须走 MQL，不得回退到 HTTP 接口。

### 11.2 口径定义（取数三段式 + 成表一段，缺一不可）

1. **时间窗** = 系统日往前推 5 年的**滑动窗口**（非自然年、非财年）。
   参考原口径：沪深京主营构成 `2021-06-11 ~ 2026-06-10`、沪深京财务摘要 `2021-06-17 ~ 2026-06-16`、港股两张表 `2021-07-06 ~ 2026-07-06`（各表按各自系统日）→ 统一按 `[系统日 − 5 年, 系统日]` 现算，**不得写死示例日期**。
   > 起点差 1 天不影响年报期集合（年报期只有 12-31 一个点），但代码里必须用系统日动态计算。
2. **报告期类型 = 年报**：只取年报期。各市场/报表的等价枚举（来自原口径，供在 MQL 侧找对应的"报告期类型"加载列时比对）：
   | 市场 / 表 | 原口径枚举 | 语义 |
   |---|---|---|
   | 沪深京 主营构成 | `DATE_TYPE_CODE = "001"` | 年报 |
   | 沪深京 财务摘要 | `DATE_TYPE_CODE = "6"`（并 `TYPE_CODE="2"`、`DATE_TYPE_NEW="2"`、`INDEX_TYPE_CODE="1"`） | 年报 |
   | 港股 主营构成 | `REPORT_TYPE_CODE ∈ {"4","5"}` | 年报类（并 `REPORT_TYPE="1"`、`TYPE="1"`、`BELONG_TYPE="1"`） |
   | 港股 财务摘要 | `DATE_TYPE_CODE ∈ {"001","999"}` | 年报（并 `REPORT_TYPE_CODE="1"`、`LISTING_MARK_CODE ∈ {"0","1"}`） |
3. **并集**：上述窗口内年报期 **OR** 「最新报告期」（对应原口径的 `IS_MAXREPORTDATE="1"` / `IS_NEWEST="1"`）。同一期间重复出现只保留一列 → **候选报告期集合最多 6 列**（若最新报告期本身即年报期，去重后为 5 列）。该集合是**取数口径**；成表时按第 4 条再剔空列。

> 关键差别：这不是"发两次查询再合并"，而是**一条带 OR 的取值条件**；因此**一次取数即得候选报告期集合**，取数后不对报告期窗口做本地重算或去重。

4. **成表：每表独立剔除「整列为空」的报告期（v2.7.2 起，口径变更点）**：候选集合（最多 6 期）落到报告上时，`4.2` 与 `7.2` **各自独立**判断——若某个报告期在**该表内没有任何有效数据**（该列的全部数据单元格都为空），则该表**不展示这个报告期**（整列删除）。
   - **判定粒度是「列」，不是「单元格」**：仅个别单元格为空（如港股某板块无毛利率、某期无扣非口径）仍**保留该列**、单元格留空（沿用既有「缺失单元格留空」规则）。
   - **两表的报告期列集合因此允许不一致**，不需要对齐；**禁止**为了与另一张表对齐而回补数据、保留空列，或删改另一张表的列。
   - 剔除后仍须满足全局列序规则：**从左到右降序、最新报告期在最左列**（见 `报告版式与图表规范.md` §0）。
   - 若某表剔除后已无任何报告期列 → 该表**整表不渲染**（该二级小节标题与表一并省略），不输出空表或占位行。
   - 该步骤属**展示层空列剔除**，与 §11.5 第 4 条禁止的「本地重算 / 裁剪时间窗」是两件事，不冲突。
   - 机读实现：`scripts/build_report.py` 的 `drop_all_empty_periods()`（4.2 / 7.2 渲染前自动执行）；`scripts/validate_report.py` 的「4.2/7.2 无整列为空的报告期列」会拦截漏剔。

### 11.3 MQL 实现（按对象类型选形态）

**形态 A（首选）：`ReportBlock` + `SetReportFilter`**
`SetReportFilter` 原生支持括号、`AND`、`OR`、`IN`、比较运算，可完整表达"窗口 ∪ 最新报告期"：

```mql
ReportBlock(#1, {<当次检索确认的报表路径>});
SetCodes(["<SECUCODE>"]);
SetReportFilter(
    (
        ({报告期} >= "2021-06-11" AND {报告期} <= "2026-06-10")
        OR {最新报告期标志} == "1"
    )
);

{报告期}: REPORT_FIELD("<报告期返回列中文名>");
{<指标列>}: REPORT_FIELD("<指标返回列中文名>");
```

- `{报告期}` / `{最新报告期标志}` 必须使用本次 `reportFilterColumns[].column_name_cn` 的**中文加载列名**；两个日期字面量按 §11.2 第 1 条现算。
- 若候选**有**"报告期类型"加载列 → 可在同一条件内再加 `AND {报告期类型} == "<年报枚举原文>"`；**枚举值必须来自候选，不得自造**。
- 若候选**没有**"最新报告期标志"加载列 → 退化为「窗口内年报 + 单独补一期最新报告期」，以两次取数结果**做并集合并**（只合并列，不做行级去重、不做本地裁剪）；并在 `degraded_notes` 标注。

**形态 B：报告期作为指标参数传参**（该表只能走普通指标族时）

```mql
{报告期} = ["最新一期(MRQ)", "GetReportDate(1, \"Q4\")", "GetReportDate(2, \"Q4\")",
            "GetReportDate(3, \"Q4\")", "GetReportDate(4, \"Q4\")", "GetReportDate(5, \"Q4\")"]
```

- 该写法要求候选 `parameters[].options` 已声明上述取值原文；**未声明即不得使用**（§4.3）。
- 若候选参数只支持单值 → 对每个报告期各写一次指标调用（同一 Block 内并列多列），**不得**改成"先取全量再本地裁 6 列"。

### 11.4 8.1 一致预测的历史年（#23 已确认）

- 8.1 表中 **3 个历史年（A）= 最近 3 个已披露的年报报告期**（即"已经披露的近 3 年年报数据"）。
  - 不是"最近 3 个报告期"，不是任意 3 年；列头写 `YYYYA`。
  - 若最新披露的是年报，则 3 个 A 年为该年报期及其前两个年报期。
- 3 个预测年（E）取一致预测指标族 `FY1/FY2/FY3`，列头写 `YYYYE`；A → E 保持时间递进。
- `PEG` 预测年为空 → 留空（不造数），8.2 相应弱化 PEG 论证。

### 11.5 一致性红线

1. `4.2` 与 `7.2` 共用**同一份取数口径**（最新报告期 + 近 5 个年报期），但成表时**各自独立剔除整列为空的报告期列**，两表最终列集合**不要求一致**（§11.2 第 4 条）；两张表各自的列序都必须为降序、最新报告期在最左。
2. 列序：**从左到右降序，最新报告期在最左列**（见 `报告版式与图表规范.md`）。
3. "近 5 年"只用系统日计算；不得按自然年/财年，不得手写死日期，不得按上一轮运行的结果复用。
4. 报告期窗口全部通过**传参 / 筛选条件**表达；**禁止**"先取全量、再在本地筛出 6 列"的二次去重实现。**唯一允许的本地裁剪 = §11.2 第 4 条的「整列为空的报告期列剔除」**（只删空列，不重算窗口、不裁剪有值列、不补数）。
5. 窗口或年报枚举若被上游改变，只改本节定义，不改下游加工；反之，成表剔空列规则只改 §11.2 第 4 条与 `scripts/build_report.py` 的 `drop_all_empty_periods()`，**不动报告期窗口口径**。
