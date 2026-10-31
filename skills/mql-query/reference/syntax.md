# MQL 语法速查卡（完整版）

> 本文件基于 `Get_MQL_Reference` 返回的 `mqlReference` 固化提炼，并融合基线与财务时序增量实测。实时工具 Schema 与本次 `Get_MQL_Reference` 是最高权威；本文件用于速查，任何冲突均以实时契约为准。

## 0. 实时上下文结果读取

`Search_Context` 的各检索分区可能使用不同的结果容器，生成 MQL 前必须按本次实际响应读取，不能统一假定为 `candidates[]`。2026-09-14 实测结构包括：

- 指标与报表：`results.Search_Indicator.data.results[]`
- 证券实体：`results.Search_Entity.data.candidates[]`
- 板块、普通时间、事件时间：读取各分区本次返回的 `data` 结构，以实时工具 Schema 和响应为准

每个分区都要同时检查 `success`、`diagnostics`、顶层 `errors` 和空结果。只有本次成功返回并唯一确认的 `indicatorPath`、`fullPath`、实体代码、参数、单位和时间才能用于 MQL。

## 1. 基础规则与词法

### 1.1 词法规则

- 每条可执行语句必须以 `;` 结束。
- 关键字、函数名、逻辑运算符大写；布尔字面量只写小写 `true`、`false`。
- 相等比较写 `==`，不等比较写 `<>`；`=` 只用于私有赋值和绑定，**不能用 `=` 做比较**，不能生成 `!=`。
- 普通花括号名称不能为空，不能包含花括号、反斜杠、换行或普通空格以外的空白，不能以空格开头/结尾。指标/报表/板块路径按 §4.3 单独处理。
- 字符串使用双引号，只使用 `\"`、`\\`、`\n`、`\r`、`\t`、`\uXXXX` 转义。未知转义、未闭合字符串不能生成。字符串转义规则不得套用到花括号路径。
- 数值使用无后缀十进制（`20`、`12.5`），负数用一元 `-`。不得生成科学计数法、千位分隔符或紧随数值的业务单位（`20%`、`200亿` 不能写入字面量）。百分比只用于 Head/Tail/Slice 和 PERCENTILE 的第二参数。
- 日期使用 `"YYYY-MM-DD"`；DateTime 使用带时区偏移的 ISO 8601（如 `"2026-09-14T18:00:00+08:00"`），仍以字符串书写，只在目标位置要求相应类型时解析。
- 列表使用方括号，元素必须是标量且统一类型；空列表元素类型由使用位置确定。

### 1.2 注释语法（实测可用）

- MQL **支持注释**，提交 Execute_MQL 时**无需删除**：实测 `//`（整行/行内尾随）与 `/* */`（块注释）均 `ok=true` 执行通过。可放心在脚本中保留教学注释。
- `reference/mql/` 下的 .mql 模板文件即带注释头与行内注释，可原样复制执行。
- `#` 在 MQL 中用于 Block 编号引用（如 `#1`、`#N.{EM_CODE}`），**不是注释符**，不要与注释混淆。

## 2. 5 类 Block

### 2.1 Block 声明语法

```text
CrossSectionBlock(#<编号>, {EM_CODE});                              ← 截面：每代码一个结果
TimeSeriesBlock(#<编号>, {EM_DATE}, {EM_CODE});                     ← 时序：逐期逐代码结果
GroupBlock(#<编号>, #<上游编号>.{<保留字段>}[, ...]);                ← 分组：对上游按字段聚合
ReportBlock(#<编号>, {<搜索确认的完整报表路径>});                    ← 报表：按报表原始行读取
MergeBlock(#<编号>, #<左侧上游编号>, #<右侧上游编号>);               ← 补列：严格多对一
```

- 编号必须唯一、严格递增的正整数；只能引用编号更小的 Block。
- `{EM_CODE}`、`{EM_DATE}` 是固定结构轴，不是指标、参数或用户字段：不能赋值、改名、作为指标参数或排序键。带来源的 `#N.{EM_CODE}`、`#N.{EM_DATE}` 只能在 SetCodes、GroupBlock、MergeBlock 位置使用。
- 每个 Block 至少定义一个输出列。
- Block 默认隔离：后续 Block 不继承私有列、参数、窗口或全局变量，也不自动继承展示列/预加载结果。跨 Block 只能用 `SetCodes(#N.{EM_CODE})`、GroupBlock、MergeBlock。

### 2.2 Block 类型选择

| 计算目标 | 选择 |
|---------|------|
| 每个代码只需要一个结果位置 | `CrossSectionBlock` |
| 需要时序指标逐期结果，或使用时序函数（MA/DELAY 等） | `TimeSeriesBlock` |
| 对一个上游 Block 按字段分组，或跨日期归约 | `GroupBlock` |
| 按报表原始行读取返回字段、逐行计算或筛选 | `ReportBlock` |
| 按显式业务键把唯一右侧记录补充到左侧结果 | `MergeBlock` |
| 先筛选/排序/截取代码，再对保留代码重新取数 | 新建下游 `CrossSectionBlock`，用 `SetCodes(#N.{EM_CODE})` |

**关键判定**：
- 指标带日期/报告期参数 ≠ 时序指标。指定某一天查截面指标仍用 CrossSectionBlock。
- 是否为时序只看指标的 `indicatorTimeShape`，不能根据参数名、返回点数或路径猜测。
- TimeSeriesBlock 的最终输出至少包含一个随日期变化的列；只要每代码一个值时改用 CrossSectionBlock；需要跨日期归约为每代码一个值时，下游接不保留 `{EM_DATE}` 的 GroupBlock。
- 候选 `type="报表"` 且含 `reportFields` 时按报表处理，用 ReportBlock，不得生成普通指标调用。

### 2.3 财务多期决策树

本节是财务多报告期规划的唯一完整规则；其它文件只引用本节，不另行维护一套决策树。

```text
用户要求多个财务报告期
  -> Search_Context 同时检索实体、财务指标和原始报告期时间表达
  -> 完整检查同语义普通指标候选，不能因报表候选排在前面就停止
  -> 时间分区是否返回完整、成功的日期或区间？
    -> 否：停止并请用户明确报告期，不自行补日期
    -> 是：读取普通指标 indicatorTimeShape
      -> time_series：
        -> 用户明确要求时序、需要 EM_DATE 轴或时序函数：使用 TimeSeriesBlock
        -> 核对累计/单季度、行业财务口径、合并/母公司、调整前后和单位
        -> 按实时参考识别财务报告期序列，使用“季”或“年”窗口
      -> cross_section：不得使用 TimeSeriesBlock
        -> 固定少量期间且需要宽表：同一 CrossSectionBlock 多次调用指标，每次内联不同 {报告期}
        -> 连续区间、期间较多或需要一期一行：优先检索 ReportBlock
          -> 确认 reportStandardCodeSupported
          -> 确认 reportFilterColumns 含可用的报告期加载列
          -> 确认 reportFields 含报告期和目标财务字段
          -> SetReportFilter 限定区间，REPORT_FIELD 输出长表
  -> 两条路线均可用：核对口径并抽样或逐期比对
```

**财务时序候选获取规则**：

- 用户要求“逐季度”“逐年”“财务时间序列”或明确指定时序指标时，`searchIndicator.keys` 应同时包含目标指标和期间口径，例如“营业收入”“单季度营业收入”；“时序/时间序列”可作为召回辅助词，不能代替指标名。
- 必须遍历同语义候选并读取 `type`、`indicatorTimeShape`、`indicatorPath`、`valueType`、`unit` 和完整 `parameters`。只有 `type="指标"` 且 `indicatorTimeShape="time_series"` 的候选可进入 TimeSeriesBlock；报表候选不能冒充时序指标。
- 用户明确要求时序且存在口径匹配候选时，时序路线优先于 ReportBlock。没有匹配候选、时间边界未确认或候选口径冲突时，停止并报告缺口，不得静默退回 ReportBlock。
- 候选路径中的“序列函数”“单季度”等文本仅用于语义核对，不能单独证明 Block 形态或期间口径；最终以本次元数据和实时 MQL 参考为准。

**时间识别规则**：

- `timeRecognition.query` 只传用户原始时间表达，不把模型换写的日期冒充原句提交。
- 模糊表达如“多个期间”“各期”不能形成完整边界时，不得生成日期或部分脚本，必须请用户明确。
- 2026-09-14 实测中，中文财报表达“2024年一季报至2025年年报”以及逐项提交“2024年一季报”“2024年中报”等可识别；`2024Q1至2025Q4` 未识别。该结果是检索输入经验，不是永久解析规则；每次仍以时间分区实际返回为准。
- 季度末、年度末等具体日期只能采用本次时间分区成功返回的值，不能仅凭日历常识填写。

**宽表与长表选择**：

| 目标 | 首选结构 | 输出形态 | 能力与限制 |
|---|---|---|---|
| 少量、明确报告期；每证券一行 | CrossSectionBlock 中重复调用同一 `cross_section` 指标并分别绑定 `{报告期}` | 一期一列的宽表 | 每期一次指标调用；无 `EM_DATE` 轴；不能使用 MA/DELAY 等时序函数 |
| 连续区间、期间较多、需要报告期标签 | 支持报告期过滤及目标返回字段的 ReportBlock | 一期一行的长表 | 一次报表请求可返回多期；不是 TimeSeriesBlock，不能使用时序函数；远端报表仍可能取数失败 |
| 实时元数据明确为 `time_series`；用户要求连续财务序列、`EM_DATE` 或时序函数 | TimeSeriesBlock + SetWindow | 带 `EM_DATE` 的时序表 | 报告期序列与普通时序的周期、日历规则见 §5 |

性能只能用于候选路线之间的辅助选择，不能覆盖口径。2026-09-14 对 8 个归母净利润报告期的实测中，截面重复调用约 10.4 秒，ReportBlock 约 1.3 秒；这是单次样本，不是性能承诺。

**财务口径检查**：生成前逐项确认并只使用本次元数据或业务知识支持的值：

- 归母净利润还是公司整体净利润。
- 年初至报告期末累计值还是单季度值；中报、三季报、年报累计值不得标成单季度值。
- 合并报表还是母公司报表。
- 调整前还是调整后口径。
- 指标 `unit` 及数值刻度。
- 普通指标与报表字段的含义、报告类型和单位是否一致。

两条路线都可执行时，应至少抽样比对；新增通用模板时应逐期比对。结果不一致必须先做口径归因，不能仅因 ReportBlock 更快而采用它。

**报表候选 vs 指标候选（财务数据双路径）**

同一财务目标可能同时命中"报表候选"（含 reportFields + matchedReportFields）与
"指标候选"（type=指标），按以下标准分流，两条路径可在一张底稿内并用：

| 需求 | 选择 | 说明 |
| --- | --- | --- |
| 完整科目明细、与定期报告逐项对齐、行多列宽 | ReportBlock | 三大报表场景（一次取 30+ 科目） |
| 标准化单值指标、需参与 FILTER/Sort/多期内联、对齐研报口径（如 ROE(摊薄)） | CrossSectionBlock 指标内联传参 | 一年内联多次取多报告期 |
| 报表字段存在前缀歧义（如 `营业总收入` vs `营业总收入同比增长率`） | 优先指标路径；或按精确字段名限定 | 避免"无法唯一绑定" |

- 两条路径均可用 `=mql()` 刷新：报表取"科目明细"，指标取"标准单值"，按口径互补。
- 实测参考：比亚迪案例中三大报表走报表、财务比率走指标、周转率回报表，三路并用。

### 2.4 Block 内语句顺序

| Block 类型 | 语句顺序 |
|-----------|---------|
| CrossSectionBlock | 声明 → 一个主输入 → 可选 SetGlobalVar → 可选 SetParams → 私有列和输出列 → 可选 FILTER_ROWS → 可选 Sort → 可选一个截取语句 → 可选 OutputBlock() |
| TimeSeriesBlock | 声明 → 一个主输入 → 一个 SetWindow → 可选 SetGlobalVar → 可选 SetParams → 私有列和输出列 → 可选 FILTER_ROWS → 可选 OutputBlock() |
| GroupBlock | 声明 → 可选 SetGlobalVar → 私有列和输出列 → 可选 FILTER_ROWS → 可选 Sort → 可选一个截取语句 → 可选 OutputBlock() |
| ReportBlock | 声明 → 按 reportStandardCodeSupported 决定的可选证券范围 → 可选 SetReportFilter → 可选 SetGlobalVar → 私有列和输出列 → 可选本地 FILTER_ROWS → 可选 Sort → 可选一个截取语句 → 可选 OutputBlock() |
| MergeBlock | 声明 → 一个 MergeOn → 可选 SetGlobalVar → 私有列和输出列 → 可选 FILTER_ROWS → 按左侧形态决定是否允许 Sort 和截取 → 可选 OutputBlock() |

**Block 职责边界**：
- GroupBlock 不调用指标，不使用 SetParams 或 SetWindow。
- ReportBlock 不调用普通指标，不使用 SetParams、SetWindow、分组/窗口/排名函数（RANK、PERCENT_RANK 也禁止）。
- MergeBlock 不取数，不使用证券范围、指标调用、REPORT_FIELD、SetParams 或 SetWindow。

## 3. 主输入（证券范围）

CrossSectionBlock 和 TimeSeriesBlock 必须且只能有一个证券范围：

```text
SetCodes("<代码一>,<代码二>");
SetCodes(["<代码一>", "<代码二>"]);
SetCodes(#<上游编号>.{EM_CODE});              ← 传递上游过滤/排序/截取后保留的代码
GetSectors({<已确认完整板块路径>});          ← 板块路径来自本次板块分区实际返回的 fullPath
GetSectors({<完整板块路径一>}, {<完整板块路径二>});
```

**关键规则**：
- `SetCodes` 按输入顺序去重；每个代码去首尾空白后非空，逗号字符串不能含空片段。`SetCodes([])` 表示空输入，不能退化为全市场。
- `GetSectors` 每项必须用花括号包裹**本次 Search_Context 返回的完整板块路径**（fullPath 解码后的逻辑值），每个路径边界保持**单个实际反斜杠**，不含 `|`。**禁止使用 publishCode、publishName 或自行拼接路径**。
  - 错误：`GetSectors("国债|617001");`
  - 正确：`GetSectors({板块\债券\东财分类旧(含到期)\国债});`
- `SetCodes(#N.{EM_CODE})` 只传递 #N 经过滤/排序/截取后最终保留的代码及顺序，不传递任何列、EM_DATE 或参数。
- ReportBlock 按报表候选的 `reportStandardCodeSupported` 决定：
  - `true`：优先写一个 SetCodes（直接字符串或字符串列表，**不接受** `#N.{EM_CODE}`）或一个 GetSectors；无法确认可用实体/板块时才省略。ReportBlock 的 GetSectors 当前只接受**一个**本次确认的完整板块路径，不能传多个路径。
  - `false`：禁止写 SetCodes 和 GetSectors；需要按代码过滤时先用 REPORT_FIELD 读出代码列，再用本地 FILTER_ROWS。

## 4. 定义名称和绑定参数

### 4.1 赋值 vs 展示列

- `{名称} = 表达式;` 定义私有列，只供本 Block 后续语句使用，不输出。
- `{名称}: 表达式;` 定义输出列，进入结果，且 `:` 左侧名称也可供本 Block 后续引用。
- 私有列需要被下游 GroupBlock 或 MergeBlock 使用时，必须先定义为输出列。
- `{名称}: {名称};` 是私有名与输出名同名的唯一合法情况，不创建新可引用名称，后续 `{名称}` 仍指向原私有列。
- 已用 `:` 定义的输出列不能再次以同名输出。
- 名称必须先定义后引用，不跨 Block 继承；私有/输出/全局名称分别不得重名。
- 不依赖当前结果记录的常量不能单独赋值为列，需要复用时用 SetGlobalVar。

### 4.2 SetGlobalVar / SetParams

| 绑定位置 | 允许的值 |
|---------|---------|
| SetGlobalVar | 常量表达式（字符串/数值/布尔/NULL/常量列表），或同一列表中此前已定义的全局名称 |
| SetParams | 常量表达式，或当前 Block 已定义的全局名称 |
| 指标调用 | 常量表达式，或当前 Block 已定义的全局名称 |

**SetGlobalVar**（每个 Block 最多一条）：
```mql
SetGlobalVar(
    {查询日期} = "2026-09-11",
    {复权方式} = "不复权"
);
```
- 保存 Block 内复用的无结果轴常量，不自动成为指标参数，必须在 SetParams 或指标调用中显式引用；不跨 Block 继承。

**SetParams**（每个截面/时序 Block 最多一条，`SetParams()` 空参合法）：
```mql
SetGlobalVar({复权方式} = "不复权");
SetParams({复权方式} = {复权方式});
```
- 多个指标需要同名同值条件时写入；只对声明了同名参数的指标生效，未被消费的绑定无效。
- **指标调用中的同名绑定覆盖当前 Block 的 SetParams**。
- 参数既未内联绑定也未在 SetParams 绑定时，使用指标元数据 defaultValue；无默认值则省略，不要臆造。
- TimeSeriesBlock 的 SetParams 不能传递窗口时间、周期或其它 Date/DateTime 值。

### 4.3 指标调用

花括号中的全部内容是完整、不透明的指标路径，按原文精确匹配，必须直接采用本次 `results.Search_Indicator.data.results[].indicatorPath` 解码后的逻辑值；括号、百分号、单位、来源说明都是路径内容，不转义、不改写、不省略任何路径段。

```mql
{债券简称}: {Choice指标\债券\债券全部指标\基本资料\债券资料\债券简称}();

{前收盘价}: {Choice指标\股票\沪深京股票指标\行情指标\日行情\前收盘价}(
    {交易日期} = "2026-09-11",
    {复权方式} = "不复权"
);
```

- 无参数指标仍写 `()`。
- 参数名也属于花括号名称，必须写 `{参数名} = 值`；参数名用指标元数据实际提供的名称（有描述名用描述名，否则用原始名）。
- 只绑定用户问题明确涉及及当前查询结构必需的参数；不因参数定义中有选项/默认值而额外绑定。
- 枚举参数值必须使用元数据声明的枚举原文（如"不复权"/"后复权"/"前复权"）。
- 同一参数列表名称不能重复。
- **数值过滤先读 unit**：按指标 `unit` 的刻度填写无后缀数值。unit 为 `%` 时"20 个点"写 `20` 而非 `0.2`；unit 为 `亿元` 时"200 亿"写 `200`。MQL 的 Number 不携带单位/量级/币种/复权口径，不做隐式换算。
- **指标标准值候选**（`type="指标标准值"`）只表示关联指标的合法枚举取值，用于构造该指标的 FILTER_ROWS 条件，**不能把标准值本身写成指标路径调用**。

### 4.4 报表路径、SetReportFilter 与 REPORT_FIELD

```mql
ReportBlock(#1, {Choice报表\...\限售股解禁时间表\沪深F9_基础资料_限售股解禁时间});
SetCodes(["600519.SH"]);
SetReportFilter(
    {解禁日} >= "2026-09-14"
    AND {解禁日} <= "2026-12-31"
);

{证券代码}: REPORT_FIELD("证券代码");
{可流通日期}: REPORT_FIELD("可流通日期");
```

- 报表路径用 Search_Context 返回的 `indicatorPath` 解码值，路径边界单反斜杠。
- `SetReportFilter` 最多一条，只能引用 `reportFilterColumns[].column_name_cn`（**加载列**）；支持括号、AND/OR、`==`/`<>`/`>`/`>=`/`<`/`<=`/`IN`；值只能是字符串/数值/布尔字面量，IN 列表非空；不支持 NULL、NOT、普通表达式、返回列引用。报表没有 reportFilterColumns 时不写 SetReportFilter，取回后用本地 FILTER_ROWS。
- `REPORT_FIELD("中文名")` 只能精确读取 `reportFields[].column_name_cn`（**返回列**中文名），不要用 column_name 物理代码；加载列与返回列是两个名称空间，不要互相推导。
- 需要在后续表达式/FILTER_ROWS/Sort 中引用报表字段时，必须先用 REPORT_FIELD 定义私有列（=）或输出列（:）。
- ReportBlock 只含 `:` 输出列，不自动带 EM_CODE/EM_DATE，并保留报表原始行顺序和重复行。
- 实测：报表候选即使元数据完备，远端仍可能预检失败（如"报表名称不能为空"），此时换用同次检索的其它报表候选，不要重复冲击同一报表。

## 5. 时序窗口（TimeSeriesBlock）

TimeSeriesBlock 必须且只能有一个 SetWindow。先按本次实时 MQL 参考和 Search_Context 返回的完整指标路径识别报告期时序指标；其它指标均按普通时序处理。不能仅凭中文显示名、参数名、枚举值、路径片段或业务常识推断窗口类型。

### 5.1 财务报告期时序（季/年，不写交易市场）

当前实时参考规定：完整路径最后一个 `|` 后的 `metricId` 以 `_s` 结尾时，按财务报告期序列处理，只生成“季”或“年”窗口，不写 `{市场类型}`，并确认同一 Block 没有普通时序指标。该标识仍须由当次 Search_Context 返回的完整 `indicatorPath` 确认，不能从示例复制。

```mql
TimeSeriesBlock(#1, {EM_DATE}, {EM_CODE});
SetCodes(["300059.SZ"]);
SetWindow(
    {开始时间} = "2023-09-18",
    {结束时间} = "2026-09-18",
    {周期} = "季"
);
```

- 开始、结束时间必须来自本次 `timeRecognition` 或 `eventTimeSearch` 的成功结果；不得自行换算为季度末或年度末。
- “季”返回实际报告期位置；窗口内尚未披露的报告期不会生成伪造值。
- 调用前核对财务指标参数的默认口径；用户明确要求合并/母公司、调整前后或币种时，只使用本次候选返回的合法参数值显式绑定。
- 不得把累计财务指标标成单季度指标。需要每季度独立发生额时，应检索并选择名称、公式或业务知识明确支持“单季度”的时序指标。

### 5.2 普通时序使用自然日历

```mql
TimeSeriesBlock(#1, {EM_DATE}, {EM_CODE});
SetCodes(["600519.SH"]);
SetWindow(
    {开始时间} = "2026-09-01",
    {结束时间} = "2026-09-14",
    {周期} = "日"
);
```

- 普通时序允许“日”“周”“月”“年”，不允许“季”。
- 省略 `{市场类型}` 时使用自然日历。指标 parameters 中是否存在原始 `name="Period"` 不决定是否填写市场类型。
- 使用周/月/年时，Block 内每个普通时序指标都必须支持对应周期。

### 5.3 普通时序使用已确认的交易日历

```mql
TimeSeriesBlock(#1, {EM_DATE}, {EM_CODE});
SetCodes(["600519.SH"]);
SetWindow(
    {开始时间} = "2026-09-01",
    {结束时间} = "2026-09-14",
    {周期} = "日",
    {市场类型} = "上海证券交易所"
);
```

- 只有用户已经明确交易市场，或查询语义明确要求对应交易日历且本次工具确认了合法枚举时，才写 `{市场类型}`。
- `{市场类型}` 只选择窗口日历，不筛选证券；证券范围仍由 SetCodes/GetSectors 决定。
- 不得按证券代码后缀、上市地点、板块、指标参数名或常识推断市场。
- 本地文档不维护静态完整市场枚举；实时信息仍不足时停止并请用户明确。

### 5.4 共通规则

- `{开始时间}`、`{结束时间}`、`{周期}` 必填；日期必须是 Date（不能用 DateTime），结束时间不能早于开始时间。
- `{预加载周期}` 可选，非负整数字面量，**仅在用户明确要求额外历史期数时生成**；正式查询期数与额外期数合计最多 1000。
- `{缺失值填充}` 可选，只能是 `"NULL"`（默认）或 `"0"`；`"0"` 仅当 Block 内全部原始时序指标均为数值型时可用。
- 开始/结束/周期只写在 SetWindow，不要复制到 SetGlobalVar/SetParams；**指标调用中不得直接填写周期参数**（周期由 SetWindow 统一传入）。
- 滚动/延迟函数直接写自身窗口长度，不要换算成预加载周期。实测 MA(X, 5) 在窗口首个日期即有值，执行器会自动预取窗口前数据。
- 早期版本曾对特定含 Period 参数的行情指标强制要求市场类型；该行为只作为历史兼容性证据，不能覆盖当前实时参考。
- 实测：普通时序使用自然日历时，非交易日或盘前当日位置会保留且指标值为 NULL（默认填充）；例如 2026-09-14 盘前查询，9-14 位置收盘价为 NULL，前一交易日 2026-09-11 为最后有值位置。

## 6. 表达式和函数

### 6.1 运算

- 算术：`+`、`-`、`*`、`/`、`MOD`；比较：`==`、`<>`、`<`、`<=`、`>`、`>=`；逻辑：`NOT`、`AND`、`OR`。
- 优先级：括号 > 一元运算 > 乘除/MOD > 加减 > 大小比较 > 相等比较 > AND > OR。混合多类运算用括号明确用户原始语义。
- 一元 `+`/`-` 和算术只接受 Number；`/`/`MOD` 除数为 0 或 NULL 时返回 NULL。
- `NOT` 只接受 Boolean；AND/OR 两个操作数都必须是 Boolean。
- `==`/`<>` 接受同类 Number/String/Boolean/Date/DateTime；`<`/`<=`/`>`/`>=` 不接受 Boolean。
- List 不能参与普通算术、比较或逻辑运算。
- 三值逻辑：`false AND NULL`→`false`，`true AND NULL`→`NULL`，`true OR NULL`→`true`，`false OR NULL`→`NULL`，`NOT NULL`→`NULL`；普通算术/比较任一操作数为 NULL 时返回 NULL。

### 6.2 通用函数（所有 Block 可用）

| 函数 | 用途 |
|------|------|
| `BETWEEN(X, A, B)` | 同类型有序值闭区间判断 |
| `IN(X, options)` | 精确匹配同类型标量列表任一值 |
| `LIKE(X, keyword)` | 字符串包含匹配（区分大小写，无通配符） |
| `LIKE_ANY(X, keywords)` | 字符串包含任一关键词，或字符串列表包含任一完整元素 |
| `STARTS_WITH(X, prefix)` / `ENDS_WITH(X, suffix)` | 前缀/后缀匹配 |
| `IS_NULL(X)` | 判断 X 是否为 MQL NULL |
| `ABS(X)` / `SIGN(X)` / `TRUNC(X, digits)` | 绝对值/符号/向零截断 |
| `ROUND(X, digits, mode)` | 舍入，mode 必须是 `"HALF_UP"`/`"UP"`/`"DOWN"` 字面量 |
| `POWER(X, exponent)` / `EXP(X)` / `LOG(X, base)` | 幂/自然指数/指定底对数 |
| `DATE(year, month, day)` | 构造严格公历日期 |
| `YEAR(X)` / `MONTH(X)` / `DAY(X)` | 提取年月日 |
| `WEEKDAY(X, convention)` | convention 必须是 `"MONDAY_1"` 或 `"SUNDAY_1"` |
| `DATE_DIFF(end, start)` | 自然日差（可为负，非工作日） |

- 表外函数不得生成；`IF` 不在函数表中。
- `IN(X, [])`、`LIKE_ANY(X, [])` 返回 `false`。
- `IS_NULL` 不传播 NULL：X 为 NULL 返回 true，其它值（含 0、空串、false、空列表）返回 false。判非空写 `NOT IS_NULL(X)`。
- `TRUNC`/`ROUND` 的 digits、mode 必须是字面量，不能用变量/列。
- 日期类函数只接受 Date/DateTime，不接受字符串；日期过滤应组合日期函数，不要把 Date 改写成字符串运算。

### 6.3 时序函数（仅 TimeSeriesBlock，N 为正整数字面量）

| 函数 | 结果 |
|------|------|
| `DELAY(X, N)` | 同一代码向前 N 个实际位置的 X |
| `DELTA(X, N)` | `X - DELAY(X, N)` |
| `WINDOW_SUM(X, N)` | 连续 N 期数值和 |
| `MA(X, N)` | 连续 N 期数值均值 |
| `WINDOW_MIN(X, N)` / `WINDOW_MAX(X, N)` | 连续 N 期最小/最大值 |
| `WINDOW_EVERY(X, N)` | 连续 N 期条件全部为 true |
| `WINDOW_COUNT(X, N)` | 连续 N 期条件为 true 的数量 |

- 按每个证券实际返回的日期顺序计算，不自行补出指标未返回的日期；可用期数不足返回 NULL；数值窗口含 NULL 返回 NULL。
- 实测：执行器为滚动计算自动预取窗口前数据，正式窗口起始日 MA 即有值；预加载数据只参与计算，最终结果仍从 SetWindow 开始日期返回。

### 6.4 排名（CrossSectionBlock/TimeSeriesBlock/GroupBlock 可用，Report/Merge 禁止）

```mql
{排名}: RANK({涨跌幅}, "DESC");
{百分比排名}: PERCENT_RANK({买入额});
{分组百分比排名}: PERCENT_RANK({买入额}, {所属行业});
```

- `RANK(X, "ASC"|"DESC")`：X 为 Number/String/Date/DateTime 列；结果含 EM_DATE 时按日期内排名，否则全记录排名；并列同名次、后续跳过；NULL 不参与；不排序、不筛选、不改变记录数。
- `PERCENT_RANK(X[, K])`：只接受 Number；升序百分比排名 `(名次-1)/(非空记录数-1)`，单值返回 0，NULL 不参与。

### 6.5 分组函数（仅 GroupBlock，列参数必须直接写 `#N.{上游输出列}`）

| 函数 | 用途 |
|------|------|
| `SUM(#N.{X})` / `AVG(#N.{X})` | 数值求和/均值 |
| `MIN(#N.{X})` / `MAX(#N.{X})` | 最小/最大值 |
| `EVERY(#N.{X})` | 组内布尔条件全为 true |
| `COUNT(#N.{X})` | 组内布尔条件为 true 的数量 |
| `COUNT(true)` | 组内记录数（唯一允许的标量参数） |
| `SUM_PRODUCT(#N.{X}, #N.{Y})` | 同组同记录两数值列逐行相乘后求和 |
| `GROUP_CONCAT(#N.{X}, separator)` | 按上游稳定顺序拼接组内字符串（separator 必填，可为空串） |
| `VAR_POPULATION(#N.{X})` | 组内总体方差（单元素组返回 0） |
| `PERCENTILE(#N.{X}, P%)` | P 分位值（P 为 0%~100% 百分比字面量，线性插值） |

- #N 必须是当前 GroupBlock 声明的唯一上游；列只能是该上游的输出列，或上游直接提供的 `{EM_CODE}`/`{EM_DATE}`；不能引用私有列，不能嵌套分组函数。
- 类型约束：SUM/AVG/SUM_PRODUCT/VAR_POPULATION/PERCENTILE 只接受 Number；GROUP_CONCAT 只接受 String；MIN/MAX 接受 Number/String/Date/DateTime；EVERY/COUNT(布尔列) 只接受 Boolean。
- SUM/AVG/MIN/MAX/VAR_POPULATION/PERCENTILE 忽略部分 NULL，组内全 NULL 返回 NULL；COUNT(布尔列) 出现 NULL 返回 NULL。

## 7. 分组、过滤、排序、截取与投影

### 7.0 字段可见性矩阵与标准链路

| 字段来源 | 直接下游 GroupBlock | 作为 MergeOn 键 | MergeBlock 列表达式 | 再供下游使用 |
|---|---|---|---|---|
| CrossSection/TimeSeries/Report 的 `:` 普通输出 | 可作保留键或分组函数输入 | 可用 | 左右输入均可读取 | 必须在当前 Merge 用 `:` 再输出 |
| GroupBlock 声明保留的业务键 | 直接下游 Group 可继续保留 | 可用 | Group 在左侧时可读；在右侧时不可读 | 经 Merge 时必须先能在该 Merge 中显式输出；右侧保留键不能直接透传 |
| GroupBlock 的 `:` 聚合输出 | 可作保留键或分组函数输入 | 可用 | 左右输入均可读取 | 必须在当前 Merge 用 `:` 再输出 |
| MergeBlock 的 `:` 显式业务输出 | 可作保留键或分组函数输入 | 可用 | 后续 Merge 可读取 | 每经过一层 Merge 都要重新显式输出 |
| MergeBlock 自动延续的左侧 `{EM_CODE}`/`{EM_DATE}` | 可直接保留或作分组函数输入 | 可用 | 后续 Merge 可读取 | Merge 作为左侧时继续自动延续；不得用 `:` 重复输出 |

**标准结构**：

```text
ReportBlock(#1, {<本次确认的报表路径>});
{分组键}: REPORT_FIELD("<本次确认的返回列>");
{数值}: REPORT_FIELD("<本次确认的返回列>");

GroupBlock(#2, #1.{分组键});
{记录数}: COUNT(true);
{合计}: SUM(#1.{数值});
```

当报表原始行需要作为 Merge 右侧时，若关联键可能重复，先用上述 GroupBlock 聚合到唯一键，再关联：

```text
MergeBlock(#4, #3, #2);
MergeOn(#3.{EM_CODE} == #2.{分组键});
{左侧业务字段}: #3.{左侧业务字段};
{记录数}: #2.{记录数};
{合计}: #2.{合计};
OutputBlock();
```

这里右侧 GroupBlock 声明保留的 `{分组键}` 可用于 `MergeOn`，但不能在 MergeBlock 的列表达式中直接读取；右侧可输出的是 GroupBlock 用 `:` 声明的聚合列。多级 Merge 中，输入为 MergeBlock 时只能读取其自动延续轴和显式输出，不能越级读取更早上游字段。

### 7.1 GroupBlock

```mql
// 正确：{上市地点} 由 GroupBlock 声明保留，自动进入结果
GroupBlock(#2, #1.{上市地点});
{股票只数}: COUNT(true);
Sort({股票只数}, "DESC");
```

- 声明至少保留一个字段，全部来自同一上游：上游 `{EM_CODE}`/`{EM_DATE}`、上游输出列、或上游分组 Block 已保留的业务键；同声明中不重复，保留键不能是 List。
- ReportBlock 或 MergeBlock 均可作为上游。ReportBlock 的分组键和聚合输入必须是其 `:` 公开输出；上游是 MergeBlock 时，只能使用其 `:` 显式业务输出或自动延续的 `{EM_CODE}`/`{EM_DATE}`。
- 保留字段按声明顺序自动进入结果（先返回保留键，再返回 `:` 输出列），**不要再次定义同名输出**。
- 保留 `{EM_DATE}`：按日期分别聚合，仍是时序结果；不保留：跨日期归约为截面结果。
- 未保留的上游输出列不能透传，只能作为分组函数参数。
- 想换名只能新增输出列（会多一列同值列），不能重命名自动保留键。

### 7.2 MergeBlock（严格多对一）

```mql
MergeBlock(#3, #1, #2);
MergeOn(#1.{证券代码} == #2.{EM_CODE});
{证券代码}: #1.{证券代码};
{证券简称}: #2.{证券简称};
```

- 两个输入必须是不同且已完成的上游；参数位置固定左右职责，不写连接模式。
- `MergeOn` 必须且只能一条，至少一个条件；只能用 AND 连接 `==`，每个等式一侧来自左、一侧来自右；禁止 OR、范围、模糊、时点、函数、算术、常量、自动同名键。
- 键两侧必须为相同 Number/String/Boolean/Date/DateTime；List 不能为键；不做字符串/数值、代码后缀等任何隐式转换。
- 右侧每个完整非 NULL 键必须唯一，重复键使整个 MergeBlock 失败（即使该键没匹配左行）；右侧键含 NULL 不匹配也不参与唯一性校验。
- 左记录无匹配时仍保留，右字段补 NULL；合并后保留左侧初始顺序。
- MergeBlock 自动延续左侧 `{EM_CODE}`/`{EM_DATE}`（左侧为 ReportBlock 时没有这两个轴）；其余需要展示或供下游使用的字段都必须用 `:` 在当前 Block 显式声明，上游私有列不可见。
- `{EM_CODE}`/`{EM_DATE}` 不得再次用 `:` 输出。
- 普通列表达式可读取左右输入的公开输出。左输入不是 MergeBlock 时，还可读取其已有轴和 GroupBlock 保留键；右输入还可读取其已有轴，但**不能读取右侧 GroupBlock 仅在声明中保留的业务键**。任一输入本身为 MergeBlock 时，只能读取该输入自动延续的轴和显式输出。
- 左侧含 `{EM_DATE}` 时禁止 Sort/Head/Tail/Slice。
- 实测：报表明细的"证券代码"返回列带后缀（如 `600519.SH`），可直接 `MergeOn(#1.{证券代码} == #2.{EM_CODE})` 与截面 Block 关联成功。

### 7.3 FILTER_ROWS

写在当前 Block 全部输出列之后、Sort 之前；只保留条件为 `true` 的记录。可写多条，但首选把完整逻辑组织在一条中（用括号分组）。

| Block | 条件写法与效果 |
|-------|--------------|
| CrossSectionBlock | 当前记录的 Boolean 条件；true 保留对应证券 |
| TimeSeriesBlock | 条件对同一证券所有日期结果相同（纯截面条件）→ 保留/删除该证券全部日期；条件使用时序列或 `{EM_DATE}`、不同日期结果不同 → 只保留满足条件的日期记录 |
| GroupBlock | 当前分组记录的 Boolean 条件；保留的 `{EM_DATE}`/`{EM_CODE}` 可参与表达式 |
| ReportBlock | 按报表原始行逐行过滤（本地操作，不等于 SetReportFilter） |
| MergeBlock | 按左侧记录过滤 |

- 采用"指标标准值"候选时，用关联指标 + 标准值构造条件；同一行业/概念词若已用于 GetSectors，不得再作为标准值进入 FILTER_ROWS。
- NULL 不会通过普通比较条件；要显式排除空值用 `FILTER_ROWS(NOT IS_NULL({列}));`（实测债券收益率排序场景：含到期国债板块大量已到期券收益率为 NULL，必须先排 NULL）。

### 7.4 排序和截取

```mql
Sort({第一排序列}, "DESC", {第二排序列}, "ASC");
Head(10);
Tail(5);
Slice(0, 10);
```

- 排序键可以是私有列、输出列或 GroupBlock 保留业务键，不能是 `{EM_CODE}`/`{EM_DATE}`；类型为 Number/String/Date/DateTime。
- 方向只写 `"ASC"`/`"DESC"`；多键排序放同一条 Sort，同一排序键不重复；稳定排序，NULL 一律排在非空值之后。
- 一个 Block 最多一个截取语句，在过滤、排序后执行：Head 从起点、Tail 从终点（维持原序）、Slice(offset, length) 从零基 offset 开始。
- 可用于截面结果、ReportBlock 行结果、不保留 EM_DATE 的 GroupBlock、以及左侧形态为截面的 MergeBlock；**时序结果（含 EM_DATE）禁止 Sort/Head/Tail/Slice**。

### 7.5 OutputBlock() 结果投影

- 零参数终止声明，每个 Block 最多一条，必须位于 Block 最后；不是表达式函数。
- 写了一个或多个 OutputBlock()：最终只返回被标记 Block（顺序按源码）；未标记 Block 仍正常取数计算并可作下游输入，只是不投影。
- 完全不写：返回全部 Block。
- 多 Block 脚本（上游明细 + 下游聚合/合并）通常只给最终 Block 加 OutputBlock()，减少返回体；实测带 1 个上游截面 + 1 个 GroupBlock 的脚本，仅标记 GroupBlock 时响应只有 blockId=2 一个结果表。

## 8. 截面简化技巧

> 适用边界：仅截面指标（CrossSectionBlock）。时序指标用 TimeSeriesBlock。

### 8.1 省略中间变量（直接输出）

指标值即最终输出、无需中间计算时，跳过 `{v} = ...; {v}: {v};`，直接：

```mql
{涨跌幅}: {Choice指标\股票\沪深京股票指标\行情指标\日行情\涨跌幅}();
```

本 Skill 示例库全部截面示例均采用该写法（实测返回正常）。

### 8.2 指标内联传参（同一 Block 拉多期）

同一 CrossSectionBlock 内可多次调用同一指标并各自内联传日期/报告期，避免拆 Block：

```mql
{收盘价_当日}: {Choice指标\股票\沪深京股票指标\行情指标\日行情\收盘价}({交易日期} = "2026-09-11");
{收盘价_上周}: {Choice指标\股票\沪深京股票指标\行情指标\日行情\收盘价}({交易日期} = "2026-09-04");
```

### 8.3 参数绑定优先级：指标内联 > SetParams > 指标默认

| 优先级 | 来源 | 写法 |
|---|---|---|
| 高 | 指标内联参数 | `{指标路径}({参数} = "值")` |
| 中 | Block 级 SetParams | `SetParams({参数} = "值");` |
| 低 | 指标 defaultValue | 省略不写 |

用户未提及的参数一律省略走默认值（如行情指标默认"最新"/"不复权"），不要把枚举选项逐个绑定。
