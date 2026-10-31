# MQL 高频陷阱详解

> 本文中的指标/报表路径、错误消息、日期、数值和枚举均为 2026-09-14 基线或 2026-09-18 财务时序增量的历史回归证据，不得作为当前任务事实；每项任务仍须以实时工具 Schema、Get_MQL_Reference 和本次 Search_Context 为准。

## 生成前 14 项强制检查清单

> 来源：`Get_MQL_Reference` 返回的 `mqlReference` 与 globalConstraints，结合实测。生成 MQL 前逐项核对，违反任一项大概率导致 Execute 失败。

| # | 检查项 | 强制 | 常见错误 |
|---|--------|------|---------|
| 1 | 截面/时序 Block 的查询范围来自唯一确认的 SetCodes 或 GetSectors；ReportBlock 按 `reportStandardCodeSupported` 决定写或省略证券范围 | ✅ | 同时写 GetSectors + SetCodes；reportStandardCodeSupported=false 仍写范围 |
| 2 | Block 类型由指标 `indicatorTimeShape` 和计算目标决定，不因交易日期或财务报告期参数误建时序 Block | ✅ | 带报告期参数的截面财务指标用了 TimeSeriesBlock |
| 3 | Block 编号唯一递增，引用只指向更小编号；五类 Block 语句顺序正确 | ✅ | 编号重复/乱序；FILTER_ROWS 写在输出列之前 |
| 4 | 每条语句有分号；名称、字符串、数值、布尔、日期、DateTime、列表、百分比写法合法 | ✅ | 漏分号；布尔写 TRUE；日期写 20260911；比较用 != |
| 5 | 每个 Block 至少一个输出列；TimeSeriesBlock 至少输出一个随日期变化的列 | ✅ | Block 无输出列；时序 Block 只有截面常量列 |
| 6 | 指标路径、返回形态、值类型、参数名和参数值均来自本次已确认信息；报表候选按 type/reportFields 识别；指标标准值不写成路径 | ✅ | 从示例复制路径；把标准值当指标调用；用普通指标取报表 |
| 7 | 每个绑定值符合所在位置允许范围，同一绑定列表无重复名称、无前向引用 | ✅ | SetParams 绑定表达式；绑定名重复；TimeSeriesBlock 用 SetParams 传日期 |
| 8 | 窗口值只在 SetWindow 定义；`_s` 报告期序列按实时参考使用季/年且不写市场；普通时序使用日/周/月/年，仅在已确认需要交易日历时写市场；不在指标调用里填周期参数 | ✅✅ | 把财务季度序列当行情日历；凭参数名或代码/板块猜市场；把 {周期} 复制进 SetParams |
| 9 | GroupBlock 保留字段来自上游输出列或上游已保留业务键；保留键自动进入结果且无同名输出；分组函数只引用上游输出列 | ✅✅ | GroupBlock 调用指标；引用私有列；保留键重复定义输出 |
| 10 | ReportBlock 的 reportStandardCodeSupported、SetReportFilter（只认 reportFilterColumns 加载列）、REPORT_FIELD（只认 reportFields 中文名）使用正确 | ✅ | SetReportFilter 引用返回列；REPORT_FIELD 用物理字段名 |
| 11 | MergeBlock 左右输入、MergeOn 来源、键类型一致、右侧键唯一；除自动延续的轴外其它字段都用 `:` 显式声明 | ✅✅ | 缺 MergeOn；用 OR/范围/LIKE；右键重复；展示字段未声明 |
| 12 | 运算和函数参数类型、结果形态、NULL 语义及所在 Block 合法 | ✅ | GroupBlock 用 RANK；ReportBlock 用 MA；List 参与算术；用 {x} <> NULL 判空 |
| 13 | 过滤、排序、截取作用于正确形态；时序结果（含 EM_DATE）不用 Sort/Head/Tail/Slice；数值过滤按指标 unit 刻度填常量 | ✅✅ | 时序 Block 上 Head；unit=% 时填 0.2 |
| 14 | 不含占位符、未定义名称、虚构条件、未确认默认值、外部工具名和示例遗留（注释除外：MQL 支持 `//`/`/* */`，可保留） | ✅ | 把示例路径/日期直接复制到无关查询；把占位符 `...` 原样提交 |

---

## 失败报错反向索引（Execute_MQL 返回 error.message → 定位陷阱）

> 用法：`Execute_MQL` 失败（`ok=false`）时，用 `error.message` 的关键字在下表定位，再读对应陷阱与 SKILL.md §0.3 阶段分流。
> 下表**只登记本文件已实测出现的真实报错文本**；未登记的报错不要臆造映射，按 SKILL.md §0.3 的阶段（parse/plan/fetch/计算）分流处理。

| error.message 关键字 | 阶段 | 对应陷阱 | 处置 |
|---|---|---|---|
| `指标包含 Period 参数，SetWindow 必须指定交易市场`（明细 `request_name=Period`） | 规划（plan） | 陷阱 1 | ⚠️ 仅为**早期版本历史失败**；当前实时参考已明确：参数是否含原始 `name="Period"` 不决定是否写 `{市场类型}`。先按本次实时参考与用户语义判断，勿把该旧报错当现行生成规则 |
| `报表接口返回失败：报表数据量预检失败：报表名称不能为空` | 取数（fetch） | 陷阱 13 | 语法与元数据无误，属后端报表异常；换用**同次检索返回的其它报表候选**，不反复冲击同一报表 |
| `MQL_TYPE_ERROR: 报表返回列无法唯一绑定` | 语法/计算 | 陷阱 17 | `REPORT_FIELD` 按字段名前缀匹配命中多列（如"证券代码"同时命中带/不带后缀）；改用完整精确字段名，先读该报表候选的 reportFields 清单 |
| `SetReportFilter 缺少受支持的比较操作符` | 规划（plan） | 陷阱 18 | SetReportFilter 的 IN 必须写函数式 `IN({列},["值"])`，中缀 `{列} IN ["值"]` 不被支持 |

> 其余陷阱（2–12、14–16、19）**无固定报错文本**：表现为执行失败、结果静默错误或形态不符，按 SKILL.md §0.3 分流 + 上方 14 项生成前检查清单逐项核对定位。

---

## 陷阱 1: 混淆财务报告期序列与普通行情时序

**问题**：把财务季度序列套用普通行情时序规则，强行要求交易市场；或仅因普通指标包含 `Period` 参数就无依据添加市场类型。

**根因**：TimeSeriesBlock 有两类不同时间轴，必须先按本次实时参考和完整指标元数据分类：

- 财务报告期序列：当前实时参考以完整 `metricId` 的 `_s` 后缀识别，只允许“季”或“年”，不写 `{市场类型}`。
- 普通时序：允许日/周/月/年；只有用户或查询语义明确要求交易日历且市场枚举已确认时才写市场。参数原始 `name=Period` 不决定是否填写市场。

**财务季度序列正确写法**（2026-09-18 实测，12 个数据点，`report_count=0`）：

```mql
TimeSeriesBlock(#1, {EM_DATE}, {EM_CODE});
SetCodes(["300059.SZ"]);
SetWindow(
    {开始时间} = "2023-09-18",
    {结束时间} = "2026-09-18",
    {周期} = "季"
);
{营业收入}: {Choice指标\序列函数\股票\沪深京股票指标\财务报表(全周期)\证券公司\利润表(单季度)\单季度.营业收入|100000000056264_s}();
OutputBlock();
```

上述代码是历史验证样例；新任务必须重新检索实体、时间和指标路径。尤其不能仅凭 `_s` 字符串或“单季度”字样自行构造未返回的路径。

### 普通行情市场要求（历史兼容性案例）

**问题**：TimeSeriesBlock 只写了开始/结束/周期，执行在规划阶段直接失败，消息：

```
指标包含 Period 参数，SetWindow 必须指定交易市场
（失败明细：parameter="计算周期3", period="日", request_name="Period"）
```

**根因**：早期版本的特定股票时序收盘价候选曾要求 SetWindow 指定交易日历。当前实时参考已明确：参数中是否存在原始 `name="Period"` 不决定是否生成 `{市场类型}`。因此该失败只用于诊断旧版本，不能作为当前生成规则。

**规避**：
- 普通时序默认可使用自然日历；周期可为日/周/月/年。
- 仅当用户已经明确交易市场，或查询语义明确要求交易日历且本次工具确认合法枚举时，才增加 `{市场类型}`。
- 市场类型不能按证券代码、上市地点、板块或参数名推断。信息不足时停止并请用户补充。
- 周期不要在指标调用中重复传。

**正确写法**（2026-09-14 回归问句明确指定上海证券交易所，返回正常）：

```mql
TimeSeriesBlock(#1, {EM_DATE}, {EM_CODE});
SetCodes(["600519.SH"]);
SetWindow(
    {开始时间} = "2026-09-01",
    {结束时间} = "2026-09-14",
    {周期} = "日",
    {市场类型} = "上海证券交易所"
);
{收盘价}: {Choice指标\序列函数\股票\沪深京股票\行情指标\收盘价}();
{5日均线}: MA({收盘价}, 5);
OutputBlock();
```

---

## 陷阱 2: Block 类型选错（截面 vs 时序）

**问题**：指标带 `{交易日期}` 或 `{报告期}` 参数就误判为时序指标，用 TimeSeriesBlock，导致失败或形态错误。

**根因**：是否时序只看 `indicatorTimeShape`：`cross_section` 用 CrossSectionBlock（日期参数内联或 SetParams 传），`time_series` 用 TimeSeriesBlock（必须配 SetWindow）。不能根据参数名、返回点数、路径猜测。

**实测对照**：
- `Choice指标\股票\沪深京股票指标\行情指标\日行情\前收盘价`：cross_section，CrossSectionBlock 默认"最新"直接返回单值（1285.13）。
- `Choice指标\序列函数\股票\沪深京股票\行情指标\收盘价`：time_series，必须 TimeSeriesBlock + 完整 SetWindow。

**财务多期特别规则**：财务指标即使有 `{报告期}` 参数，仍必须服从 `indicatorTimeShape`。存在口径匹配的 `time_series` 候选且用户明确要求时序、需要 `EM_DATE` 或时序函数时，使用 TimeSeriesBlock；`cross_section` 财务指标取固定少量期间时，在同一 CrossSectionBlock 中多次调用并分别内联报告期；只有目标仍为 `cross_section` 且需要连续长表或报表字段时，才优先检索 ReportBlock。完整规则只维护在 [syntax.md §2.3](syntax.md#23-财务多期决策树)。

---

## 陷阱 3: GroupBlock 调用指标或引用上游私有列

**问题**：
```mql
// ❌ GroupBlock 中调用指标（GroupBlock 不取数）
GroupBlock(#2, #1.{上市地点});
{证券简称}: {Choice指标\...\股票简称}();

// ❌ 分组函数引用上游私有列（#1 中用 = 定义、未用 : 输出）
GroupBlock(#2, #1.{上市地点});
{只数}: COUNT(true);
{平均收益}: AVG(#1.{到期收益率});   // 若上游只写了 = 私有列则非法
```

**规避**：需要聚合/分组引用的列必须在上游用 `:` 输出；GroupBlock 只写保留键 + 分组函数 + 可选 FILTER_ROWS/Sort/截取，不写 SetParams/SetWindow。

ReportBlock 和 MergeBlock 都可以作为 GroupBlock 上游，但可见性不放宽：ReportBlock 必须先用 `REPORT_FIELD` + `:` 公开键和聚合列；MergeBlock 只能向下游提供自动延续的 `{EM_CODE}`/`{EM_DATE}` 和本层 `:` 显式输出，不能越级读取更早输入的字段。

```mql
// ❌ 报表字段未公开就直接分组
ReportBlock(#1, {<报表路径>});
GroupBlock(#2, #1.{证券代码});

// ✅ 先公开，再分组
ReportBlock(#1, {<报表路径>});
{证券代码}: REPORT_FIELD("证券代码");
{数量}: REPORT_FIELD("数量");
GroupBlock(#2, #1.{证券代码});
{合计}: SUM(#1.{数量});
```

---

## 陷阱 4: ReportBlock 用普通指标或 SetParams/SetWindow

**问题**：
```mql
// ❌ ReportBlock 中调用普通指标
ReportBlock(#1, {Choice报表\...\限售股解禁时间});
{证券简称}: {Choice指标\...\股票简称}();

// ❌ ReportBlock 用 SetWindow / 时序函数 / RANK
```

**规避**：报表数据只能通过 REPORT_FIELD 读取；需要补充普通指标（行情、简称等）时另建 CrossSectionBlock，再用 MergeBlock 关联。示例见 [贵州茅台_限售解禁_Merge补列.mql](mql/股/报表明细/贵州茅台_限售解禁_Merge补列.mql)。

---

## 陷阱 5: MergeBlock 缺 MergeOn、非等值条件或右键重复

**问题**：
```mql
// ❌ 缺 MergeOn
MergeBlock(#3, #1, #2);
// ❌ OR / 模糊 / 范围
MergeOn(#1.{代码} == #2.{代码} OR LIKE(#1.{名称}, #2.{名称});
// ❌ 右侧同一代码多条记录 → 右键不唯一，整个 MergeBlock 失败
```

**规避**：MergeOn 一条且只用 AND 连接跨左右的 `==`；右侧先 GroupBlock 聚合到唯一键再 Merge；除自动延续轴外每个需要的字段都用 `:` 声明，未声明字段不会出现在结果中。

右侧为 GroupBlock 时，声明中保留的业务键可用于 `MergeOn`，但不能在 MergeBlock 的列表达式中直接读取；需要展示的右侧值必须是 GroupBlock 的 `:` 显式输出。输入为前一层 MergeBlock 时，也只能读取其自动轴和显式输出。

```mql
// ❌ 报表同一证券多行，直接放到右侧导致键重复
MergeBlock(#3, #1, #2);
MergeOn(#1.{EM_CODE} == #2.{证券代码});

// ❌ #2 是右侧 GroupBlock，保留键不能作为普通输出表达式读取
{证券代码}: #2.{证券代码};

// ✅ #2 先按证券代码聚合为唯一键；键只用于关联，读取其显式聚合列
MergeOn(#1.{EM_CODE} == #2.{证券代码});
{记录数}: #2.{记录数};
```

ReportBlock 使用 GetSectors 时当前只接受一个完整板块路径；不能照搬 CrossSectionBlock/TimeSeriesBlock 的多路径写法。

---

## 陷阱 6: 裸 {EM_CODE}/{EM_DATE} 当普通名称

**问题**：
```mql
// ❌ 写入指标参数
{开盘价}: {Choice指标\...\开盘价}({EM_CODE} = "600519.SH");
// ❌ 作为排序键
Sort({EM_DATE}, "DESC");
// ❌ TimeSeriesBlock 上 Head
Head(10);
```

**规避**：结构轴只用于固定位置（Block 声明、SetCodes(#N.{EM_CODE})、GroupBlock/MergeBlock 的来源引用）；需要代码/日期展示列时调用对应指标；跨 Block 传代码用 SetCodes(#N.{EM_CODE})。

---

## 陷阱 7: 为 GroupBlock 保留键重复定义同名输出

**问题**：
```mql
// ❌ {上市地点} 已自动进入结果
GroupBlock(#2, #1.{上市地点});
{上市地点}: {上市地点};
{股票只数}: COUNT(true);
```

**正确**：
```mql
GroupBlock(#2, #1.{上市地点});
{股票只数}: COUNT(true);
Sort({股票只数}, "DESC");
```

实测结果列顺序为 `上市地点 | 股票只数`，无需重复声明。

---

## 陷阱 8: 在时序结果上 Sort/Head/Tail/Slice

**问题**：TimeSeriesBlock（含 EM_DATE）或保留 EM_DATE 的 GroupBlock 上排序截取，违反形态约束。

**规避**：先让时序列正常输出，下游接**不保留** EM_DATE 的 GroupBlock 归约为截面，再排序截取；或在时序 Block 内用 RANK 计算名次后下游过滤。需要"窗口内最高收盘价"这类需求，用 `WINDOW_MAX({收盘价}, N)` 等时序函数在时序列内表达。

---

## 陷阱 9: SetReportFilter 引用返回列、REPORT_FIELD 用物理名

**问题**：
```mql
// ❌ 把 REPORT_FIELD 返回列写进 SetReportFilter
SetReportFilter({证券简称} == "贵州茅台");
// ❌ 用 column_name 物理代码
{代码}: REPORT_FIELD("SECURITY_CODE");
```

**规避**：
- SetReportFilter 只认 `reportFilterColumns[].column_name_cn`（加载列），作用于远端取数。
- REPORT_FIELD 只认 `reportFields[].column_name_cn`（中文名返回列）。
- 报表没有 reportFilterColumns 时（实测"限售股解禁时间"报表即如此），不写 SetReportFilter，全量取回后用本地 FILTER_ROWS。

---

## 陷阱 10: 照抄 JSON 里的双反斜杠路径

**问题**：Search_Context 返回 JSON 文本中路径显示为 `"Choice指标\\股票\\行情\\前收盘价"`（外层再嵌一层字符串时可能是四个反斜杠），直接照抄进 MQL 导致路径不匹配。

**根因**：JSON 中 `\\` 是转义表示，解码后逻辑值只有一个反斜杠。MQL 路径**不做字符串转义**，每个路径边界必须是单个实际反斜杠。

**规避**：
- 正确：`{Choice指标\股票\沪深京股票指标\行情指标\日行情\前收盘价}()`
- 板块同理：`GetSectors({板块\沪深京股票\市场类\全部A股});`
- 路径必须整体来自 indicatorPath/fullPath 解码值，不省略、不改写、不拼接。

---

## 陷阱 11: 债券代码无后缀，不能 LIKE 后缀判市场（实测）

**问题**：国债板块返回的 EM_CODE 是纯数字（实测如 `1003940779`、`1000250381`），不含 .IB/.SH 后缀；`LIKE({债券代码}, ".IB")` 永远 0 命中。

**规避**：
- 债券市场口径用 `Choice指标\债券\债券全部指标\基本资料\债券资料\交易场所`（cross_section、无参数，覆盖全部债券 typeCodes）做 LIKE 过滤或 GroupBlock 分组。
- 银行间：`LIKE({交易场所}, "银行间") OR LIKE({交易场所}, "柜台")`；注意 MQL 没有 NOT LIKE，取反写 `NOT (LIKE(...) OR LIKE(...))`。
- 股票代码与报表明细"证券代码"实测带 .SH/.SZ/.BJ 后缀，可直接与 EM_CODE 等值 Merge。

---

## 陷阱 12: 指标路径"推断拼接"违反 G2

**问题**：按 Choice 指标目录的命名规律自行拼接未通过 Search_Indicator 验证的路径。即使偶然命中，也可能指向不同主体（如同名指标归属不同口径），结果静默错误。

**规避**：所有 indicatorPath/报表路径必须经本次 Search_Context 的 searchIndicator 分区召回确认；未命中时换 keys 变体重检索或请用户澄清，禁止拼路径、禁止把本 Skill 或其它示例的路径默认复用到新查询（indicators.md 仅是索引，最终以本次返回为准）。

---

## 陷阱 13: 报表元数据通过但远端取数被拒（实测）

**问题**：报表候选经 Search_Context 确认、语法校验通过，但取数阶段失败：

```
报表接口返回失败：报表数据量预检失败：报表名称不能为空
（subject: 限售解禁_未来解禁列表）
```

**根因**：个别报表的后端服务配置异常，元数据可用但远端拒绝查询，与 MQL 写法无关。

**规避**：
- 同一脚本修改 ≤1 次确认不是语法问题后，不要反复冲击同一报表；
- 回到 Step 3 结果中选择**同次检索返回的其它报表候选**（实测同主题的"沪深F9_基础资料_限售股解禁时间"取数正常），重写 ReportBlock；
- 若同次没有可替代候选，单分区补调 searchIndicator 或向用户报告。

---

## 陷阱 14: 自然日窗口中的非交易日/盘前 NULL（实测）

**现象**：TimeSeriesBlock 自然日窗口返回的位置数可能多于实际交易日；非交易日、盘前当日（业务知识：16:00 前未明确日期时盘口数据可能沿用 T-1，但历史日行情当日位置在收盘前为 NULL）以 NULL 保留。

**实测**：2026-09-14 07:52（盘前）查询窗口 2026-09-01~2026-09-14，返回 10 个日期位置，其中 2026-09-14 收盘价/均线均为 NULL，最后有值位置为 2026-09-11。

**规避**：
- 这是 `{缺失值填充}="NULL"` 的预期行为，不是取数失败；
- 下游计算/排序前按需 `FILTER_ROWS(NOT IS_NULL({收盘价}))`（时序 Block 中用时序列条件会按日期过滤，合法）；
- 需要整券剔除含空值的证券时，把条件写成对所有日期结果一致的截面条件，或下游 GroupBlock 用 EVERY/WINDOW_EVERY 归约。

---

## 陷阱 15: 跳过强制流程、凭记忆写脚本

**规避**：
1. 先调用 Get_MQL_Reference（G0，每次必调），同步最新约束。
2. Search_Business_Knowledge 取 typeCodes → Search_Context 首次全量传 typeCodes 取上下文。
3. 生成前过 14 项检查清单。
4. Execute 失败按 SKILL.md §0.3 分流：语法/规划问题回 Step 4，上下文问题回 Step 3。
5. 累计修改 ≥3 次仍失败，停止重试（G11，本 Skill 自定实操规则），向用户报告诊断。

---

## 陷阱 16: 财务多期口径混用

**问题**：MQL 能成功返回多个期间，但列名或解释把不同财务口径混在一起，例如把年初至报告期末累计净利润称为单季度净利润，或把公司整体净利润称为归母净利润。

**高风险混用**：

- 归母净利润 vs 净利润。
- 累计值 vs 单季度值。
- 合并报表 vs 母公司报表。
- 调整前 vs 调整后。
- 元、万元、亿元等不同 `unit`。

**规避**：

1. 先采用本次 Search_Business_Knowledge 返回的口径知识，再核对指标 parameters、formula、unit 或报表字段定义。
2. 用户要求单季度值时，重新检索明确的单季度指标或报表字段；不得直接把中报、三季报累计值改名为单季度值。
3. 普通指标与 ReportBlock 都能返回时，先核对口径，再抽样比对数值；新增通用模板时逐期比对。
4. 模糊期间或时间分区失败时停止并请用户明确，不按季度末常识自行补日期。
5. ReportBlock 只提供报表行，不具有 `EM_DATE` 时序轴，禁止对其使用 MA、DELAY 等时序函数。

规划选择统一见 [syntax.md §2.3](syntax.md#23-财务多期决策树)。

## 陷阱 17: 报表返回字段"证券代码(带后缀)/(不带后缀)"二义性（实测）

<strong>现象</strong>：对 `RPT_F10_FINANCE_GBALANCE` 执行
`{证券代码}: REPORT_FIELD("证券代码");` 报 `MQL_TYPE_ERROR: 报表返回列无法唯一绑定`，
连续重试其他字段名也会指向同一行报错（先确认报错行号，避免误判字段）。

<strong>根因</strong>：报表 schema 中存在两个前缀相同的字段：
- `证券代码(不带后缀)`（SECURITY_CODE）：交易所公布的实际代码，用于与公告/定期报告原文统一；
- `证券代码(带后缀)`（SECUCODE）：系统内编制规范，后缀（.SH/.SZ/.BJ/.HK 等）区分交易所与交易品种。

`REPORT_FIELD` 按字段名前缀匹配，"证券代码"同时命中两者 → 无法唯一绑定。

<strong>选择规则</strong>：
- 与交易所公布的代码/公告/外部数据对照 → `REPORT_FIELD("证券代码(不带后缀)")`；
- 与系统内 EM_CODE、SetCodes、MergeOn 关联（EM_CODE 本身带后缀）→ `REPORT_FIELD("证券代码(带后缀)")`。

<strong>同类场景</strong>：`交易性金融资产` vs `其中:交易性金融资产`、`营业总收入` vs `营业总收入同比增长率`
等多义前缀字段一律使用完整精确字段名；拿不准时先读该报表候选的 reportFields 清单
（Search_Context → Search_Indicator 报表候选），禁止凭记忆拼字段名。

---

## 陷阱 18: SetReportFilter 的 IN 必须写函数式（实测踩坑）

**问题**：在有加载列（reportFilterColumns）的报表（如港股/美股主营构成）里，SetReportFilter 用中缀写法会报：

```
SetReportFilter 缺少受支持的比较操作符
```

**根因**：SetReportFilter 不支持中缀 `{列} IN ["值"]`，必须用函数式 `IN({列}, ["值"])`。

**规避**：

```mql
// ❌ 中缀写法 → 报错
SetReportFilter({是否最新报告期} == "1" AND {数据类型} IN ["1"]);

// ✅ 函数式写法
SetReportFilter({是否最新报告期} == "1" AND IN({数据类型}, ["1"]));
```

> 仅当报表有 reportFilterColumns 加载列时才写 SetReportFilter；A股沪深F9主营构成**无加载列，禁止写 SetReportFilter**（见陷阱 19、SKILL.md 易错红线第 8 条）。

---

## 陷阱 19: 主营构成三市场结构差异 + 报告期类型双份数据（实测）

**问题**：主营构成（按产品/行业/地区）在 A股/港股/美股是**三套不同报表结构**，照抄一个市场的过滤逻辑到另一个市场必然失败或行数翻倍。

**三市场差异速查**：

| 维度 | A股 | 港股 | 美股 |
|---|---|---|---|
| 报表数量 | 1 张 | 1 张 | 2 张（按产品/地区各一张） |
| 分布类型 | 中文词（产品/行业/地区/销售模式） | 码值（1=产品、2=地区） | 无此列，靠换报表 |
| 过滤方式 | 无加载列→本地 FILTER_ROWS | 有加载列→SetReportFilter 远端 | 有加载列→SetReportFilter 远端 |

**报告期类型双份数据**：港股/美股报表同时返回"正常报告期"和"单季度"两套行，不剔除会行数翻倍。
- 港股：`FILTER_ROWS(({分布类型}=="1") AND ({报告期类型名称}=="正常报告期"))`
- 美股：`FILTER_ROWS({报告期类型}=="1")`

**规避**：
1. 先按市场选对报表（[indicator_templates.md §6](indicator_templates.md#6-常用报表清单) 有完整路径与三市场对比表）；
2. A股禁止 SetReportFilter（无加载列），用本地 FILTER_ROWS 过滤中文分布类型；
3. 港股/美股 SetReportFilter 的 IN 用函数式（陷阱 18），再本地按分布类型/报告期类型分 Block；
4. 报告期类型字段名：港股是「报告期类型名称」（值"正常报告期"），美股是「报告期类型」（值"1"），不要混用。

> 示例脚本：[比亚迪（A股）](mql/股/财务指标/比亚迪主营构成_按产品_按行业_按地区.mql) · [腾讯（港股）](mql/股/财务指标/腾讯控股主营构成_按产品_按地区.mql) · [AAPL（美股）](mql/股/财务指标/AAPL苹果主营构成_按产品_按地区.mql)
