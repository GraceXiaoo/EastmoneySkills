# MQL 取数配方（可直接执行）

> 配套 `SKILL.md` 第 5 节「MQL 硬规则」。所有脚本均为**独立执行**，`ReportBlock` 编号各自从 `#1` 起。
> 路径已实测校准（2026-10-02）；字段中文名与 `reference/reports.md` 一致。

## 0. 检索链路（只做一次）

```
1. Get_MQL_Reference()                                   # 先调用，同步最新约束
2. Search_Business_Knowledge(varieties=["板块","指数","沪深股票"], user_query=<原句>,
       keywords=[...], query_rewrites=[2~3条标准化改写])   # 记录返回的全部 typeCodes
3. Search_Context(typeCodes=<首次原样全量>, searchIndicator.keys=[报表中文名], ...)
4. Execute_MQL(mql=<下方脚本>)
```

补调规则：只传需要补调的分区（含 typeCodes），不重传已确认分区；检索工作流只获取一次生成参考。

---

## 1. Step 2：产业搜索（市场主题 / 标准产业）

两条独立 MQL，各从 `#1` 起。**必须用 `329428787766940` 路径**（可用「产业类型」做加载列过滤）。

```mql
// 搜索市场主题（独立执行）
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\产业链\产业深度分析AI一页纸\产业深度分析\产业链首页_企业搜索|329428787766940});
SetReportFilter({产业类型} == "市场主题");
{产业代码}: REPORT_FIELD("产业代码");
{产业名称}: REPORT_FIELD("产业名称");
{产业所属路径}: REPORT_FIELD("产品所属路径(首页)");
FILTER_ROWS(LIKE({产业名称}, "{{TOPIC}}"));
OutputBlock();
```

```mql
// 搜索标准产业（独立执行）
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\产业链\产业深度分析AI一页纸\产业深度分析\产业链首页_企业搜索|329428787766940});
SetReportFilter({产业类型} == "标准产业");
{产业代码}: REPORT_FIELD("产业代码");
{产业名称}: REPORT_FIELD("产业名称");
{产业所属路径}: REPORT_FIELD("产品所属路径(首页)");
FILTER_ROWS(LIKE({产业名称}, "{{TOPIC}}"));
OutputBlock();
```

要点：
- 该报表是**公司×节点级明细**（实测全表 12,062 行；具身智能过滤后 292 行且大量重复），必须用 `FILTER_ROWS(LIKE({产业名称}, "<关键词>"))` 收窄，并对结果**去重**后再做相关性判断。
- `LIKE` 为字符串包含匹配，`{{TOPIC}}` 直接作子串。
- 若确要用旧路径 `...\A股专题\产业链\产业链首页_企业搜索|564217624877789`（加载列只有公司名称/证券简称），**禁止** `SetReportFilter({产业类型})`；改为 `{产业类型}: REPORT_FIELD("产业类型");` + `FILTER_ROWS({产业类型} == "市场主题")`。

**相关性判断**（模型判断，禁止把原始候选直接给用户）：高相关=同义词/别名、业务等价的直接上下位、去通用后缀后词干一致；中相关=同大行业不同细分/紧密上下游/宽泛主题与具体细分；低相关=跨行业大类/无业务交集。比较前剔除「产业链、产业、行业、主题、概念、板块、指数」及空格特殊符号。未提交候选视为低相关并丢弃。

**分支**：有高相关产业链 → 唯一则直接生成（路线 A），多个则让用户选编号；无高相关 → 保存中相关作回退，进入 Step 2b。

---

## 2. Step 2b：产业指数识别

```text
1. Search_Business_Knowledge(varieties=["指数","板块"], keywords=["产业指数","指数","概念",...])
2. Search_Context(typeCodes=上一步全部, searchEntity.words=[{{TOPIC}}, 变体],
       searchSector.words=[{{TOPIC}}+"概念", {{TOPIC}}+"指数"],
       searchIndicator.keys=[{{TOPIC}}+"指数", "相关指数"])
```

从返回候选筛出「产业类股票指数」（SECUCODE 形如 `8870432.EI`、`CI009133R.IDX`、`801014.SWI`），按同一高/中/低相关规则判断。

**分支**：有高相关指数 → 路线 B（多个同等高相关取返回顺序第一个）；无高相关指数 → 回退中相关产业链（空→提示「未找到与 {关键词} 相关的分析。」；唯一→直接生成；多个→展示候选编号）；指数列表为空且无中相关产业链 → 同上提示。

---

## 3. 路线 A：产业链报告数据

### 3.1 产业结构

```mql
// 市场主题图谱（独立执行）
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\产业链\产业深度分析AI一页纸\产业深度分析\公司一页纸_产业深度分析_市场主题图谱|010679682450425});
SetReportFilter({产业代码} == "{{TYPE_CODE}}");
{产业位置}: REPORT_FIELD("产业位置");
{一级节点名称}: REPORT_FIELD("一级节点名称");
{二级节点名称}: REPORT_FIELD("二级节点名称");
{二级节点公司}: REPORT_FIELD("二级节点公司");
{三级节点名称}: REPORT_FIELD("三级节点名称");
{三级节点公司}: REPORT_FIELD("三级节点公司");
{四级节点名称}: REPORT_FIELD("四级节点名称");
{产业代码}: REPORT_FIELD("产业代码");
{产业名称}: REPORT_FIELD("产业名称");
OutputBlock();
```

```mql
// 标准产业中游（独立执行）
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\产业链\产业深度分析AI一页纸\产业深度分析\公司一页纸_产业深度分析_标准产业图谱(中游)|196487813508749});
SetReportFilter({标准产业代码} == "{{TYPE_CODE}}");
{细分产品名称}: REPORT_FIELD("细分产品名称");
{产品下公司}: REPORT_FIELD("产品下公司");
{标准产业代码}: REPORT_FIELD("标准产业代码");
{标准产业名称}: REPORT_FIELD("标准产业名称");
OutputBlock();
```

```mql
// 标准产业上下游（独立执行）
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\产业链\产业深度分析AI一页纸\产业深度分析\公司一页纸_产业深度分析_标准产业图谱(上下游)|617118297459170});
SetReportFilter({产业代码} == "{{TYPE_CODE}}");
{产业位置}: REPORT_FIELD("产业位置");
{产业节点名称}: REPORT_FIELD("产业节点名称");
{产业节点下公司}: REPORT_FIELD("产业节点下公司");
{细分产品名称}: REPORT_FIELD("细分产品名称");
{节点关系}: REPORT_FIELD("节点关系");
{归类节点名称}: REPORT_FIELD("归类节点名称");
OutputBlock();
```

按 `产业位置`（上游/中游/下游）分组，存入 `{{theme_industry_*_structure}}` / `{{standard_industry_*_structure}}`。

### 3.2 指数信息与业绩（4 个指数）

指数代码恒为 `{{TYPE_CODE}}.EI`（整体）、`{{TYPE_CODE}}+1.EI`、`+2.EI`、`+3.EI`。

> ⚠️ **必须先跑下面这段「指数基本信息」，用返回的「指数名称」判定哪个是上游/中游/下游——后缀序号与环节的对应关系不固定。**
> 实测反例：具身智能 8880781 → 782=上游、783=中游、784=下游；**标准产业「光电器件」8870531 → 782=上游、783=下游、784=中游**（与前者相反）。
> 另：`SAMPLE_NUM`（成分股数量）是官方口径；「成分股详情」的实际行数常与之不等（部分成分股当交易日无有效总市值），取数时以详情行数为计算基数、以 `SAMPLE_NUM` 作为登记口径并注明差异。

```mql
// 指数基本信息（独立执行）
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\指数F9\一页纸\指数基本信息|292749174710315});
SetCodes(["{{TYPE_CODE}}.EI", "{{TYPE_CODE+1}}.EI", "{{TYPE_CODE+2}}.EI", "{{TYPE_CODE+3}}.EI"]);
{指数代码}: REPORT_FIELD("指数代码");
{指数名称}: REPORT_FIELD("指数名称");
{指数简称}: REPORT_FIELD("指数简称");
{指数简介}: REPORT_FIELD("指数简介");
{成分股数量}: REPORT_FIELD("成分股数量");
OutputBlock();
```

```mql
// 估值通道周频——务必限定窗口，避免整表回传（单指数约 346 行）
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\指数F9\一页纸\指数F9_估值通道_周频|505321336674530});
SetCodes(["{{TYPE_CODE}}.EI", "{{TYPE_CODE+1}}.EI", "{{TYPE_CODE+2}}.EI", "{{TYPE_CODE+3}}.EI"]);
{证券代码}: REPORT_FIELD("证券代码(带后缀)");
{周交易日}: REPORT_FIELD("周交易日");
{收盘价}: REPORT_FIELD("收盘价");
{市盈率}: REPORT_FIELD("市盈率(TTM)");
{市净率}: REPORT_FIELD("市净率(MRQ)");
{市销率}: REPORT_FIELD("市销率(TTM)");
Sort({周交易日}, "DESC");
Head(120);          // 4 指数 × 近 5 年季末/月末观测 ≈ 100~130 行，控制在 1000 单元内
OutputBlock();
```

按环节分组存入 `{{industry_index_total/upstream/midstream/downstream_performance}}`。

### 3.3 成分股（一次性聚合，不要拉明细）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\指数F9\一页纸\指数F9_成分数据_成分股详情(综合)|676193052396478});
SetCodes(["{{TYPE_CODE}}.EI", "{{TYPE_CODE+1}}.EI", "{{TYPE_CODE+2}}.EI", "{{TYPE_CODE+3}}.EI"]);
SetReportFilter({交易日期} >= "{{最新成分交易日}}");
{指数代码}: REPORT_FIELD("指数代码");     // 多指数必须引用，否则无法按环节分组
{行业}: REPORT_FIELD("行业");
{总市值}: REPORT_FIELD("总市值(亿元)");
{权重}: REPORT_FIELD("权重");
{涨跌幅}: REPORT_FIELD("涨跌幅");
{档1} = ({总市值} >= 0) AND ({总市值} < 50);
{档2} = ({总市值} >= 50) AND ({总市值} < 200);
{档3} = ({总市值} >= 200) AND ({总市值} < 500);
{档4} = ({总市值} >= 500) AND ({总市值} < 1000);
{档5} = ({总市值} >= 1000) AND ({总市值} < 5000);
{档6} = ({总市值} >= 5000) AND ({总市值} < 10000);
{档7} = ({总市值} >= 10000);
{档1}: {档1}; {档2}: {档2}; {档3}: {档3}; {档4}: {档4};
{档5}: {档5}; {档6}: {档6}; {档7}: {档7};

GroupBlock(#2, #1.{指数代码});
{成分股总数}: COUNT(true);
{总市值合计}: SUM(#1.{总市值});
{权重合计}: SUM(#1.{权重});
{平均涨跌幅}: AVG(#1.{涨跌幅});
{档1_50亿以下}: COUNT(#1.{档1});
{档2_50至200亿}: COUNT(#1.{档2});
{档3_200至500亿}: COUNT(#1.{档3});
{档4_500至1000亿}: COUNT(#1.{档4});
{档5_1000至5000亿}: COUNT(#1.{档5});
{档6_5000至1万亿}: COUNT(#1.{档6});
{档7_1万亿以上}: COUNT(#1.{档7});
OutputBlock();

GroupBlock(#3, #1.{指数代码}, #1.{行业});
{行业成分数}: COUNT(true);
OutputBlock();
```

要点：
- 私有列必须先以 `:` 公开才能被下游 `GroupBlock` 引用。
- `OutputBlock()` 只标记**聚合块**，明细块不回传。
- 实测效果：222 行成分明细 → 聚合后仅 `4 行 × 9 列 + 35 行 × 3 列`。
- 若报告需要「前 N 大市值股」清单，另起一条 MQL 取明细并 `Sort({总市值},"DESC"); Head(10);`，**不要**在同一脚本里既回传明细又聚合。

### 3.4 妙想搜索（可选，可降级）

`mx_finance_search_news` 搜资讯/研报、`mx_finance_search_notice` 搜公告/政策；结果存入 `{{search_chunks_report}}` / `{{search_chunks_news}}` / `{{search_chunks_notice}}`。

Query 构造：

| CHAIN_TYPE | Query |
|---|---|
| 市场主题 | `{{TYPE_NAME}}产业 上游 <一级节点> 中游 <一级节点> 下游 <一级节点>` |
| 标准产业 | `{{TYPE_NAME}}产业 <细分产品名称，用「、」隔开>` |

---

## 4. 路线 B：产业指数报告数据

指数代码 `{{INDEX_CODE}}`（SECUCODE，单个）。

```mql
// 4.1 指数基本信息
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\指数F9\一页纸\指数基本信息|292749174710315});
SetCodes(["{{INDEX_CODE}}"]);
{指数代码}: REPORT_FIELD("指数代码");
{指数名称}: REPORT_FIELD("指数名称");
{指数简称}: REPORT_FIELD("指数简称");
{指数简介}: REPORT_FIELD("指数简介");
{成分股数量}: REPORT_FIELD("成分股数量");
OutputBlock();
```
→ `{{index_profile}}`（简介，空则不注入后续 prompt）、`{{index_name}}`、`{{index_abbr}}`。

```mql
// 4.2 产业业绩表现（近五年）
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\指数F9\一页纸\指数F9_估值通道_周频|505321336674530});
SetCodes(["{{INDEX_CODE}}"]);
{证券代码}: REPORT_FIELD("证券代码(带后缀)");
{周交易日}: REPORT_FIELD("周交易日");
{收盘价}: REPORT_FIELD("收盘价");
{市盈率}: REPORT_FIELD("市盈率(TTM)");
{市净率}: REPORT_FIELD("市净率(MRQ)");
{市销率}: REPORT_FIELD("市销率(TTM)");
Sort({周交易日}, "DESC");
Head(300);          // 单指数近 5 年周频约 260 行
OutputBlock();
```
仅保留 `周交易日 ≥ 当前日期-5年`；数值保留 4 位小数；表格按交易日降序。→ `{{industry_index_performance}}`（列：指数代码、指数简称、交易日、指数收盘点位、指数滚动市盈率、指数最新市净率、指数滚动市销率）。

```mql
// 4.3 成分股详情（必须带交易日期过滤）
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\指数F9\一页纸\指数F9_成分数据_成分股详情(综合)|676193052396478});
SetCodes(["{{INDEX_CODE}}"]);
SetReportFilter({交易日期} >= "{{最新成分交易日}}");
{证券代码}: REPORT_FIELD("证券代码");
{证券简称}: REPORT_FIELD("证券简称");
{总市值}: REPORT_FIELD("总市值(亿元)");
{权重}: REPORT_FIELD("权重");
{涨跌幅}: REPORT_FIELD("涨跌幅");
{行业}: REPORT_FIELD("行业");
{交易日期}: REPORT_FIELD("交易日期");
OutputBlock();
```
→ `{{industry_index_stock}}`（列：指数代码、指数简称、股票代码、股票简称、股票总市值(亿元)、所属申万一级行业）。
> 单个产业指数成分通常在 20~150 只量级（实测具身智能 106 只），直接回传可控；若某指数成分 > 800 只，改用 3.3 的聚合范式只取汇总口径。

**4.4 成分竞争格局（衍生，不额外调接口）** — 基于 `{{industry_index_stock}}` 计算 `{{competitive_landscape}}`：成分股数、总市值（亿元）、CR1、CR3、CR5。CR1=第一名市值/总市值，CR3=前三合计/总市值，CR5=前五合计/总市值。**股票简称重复时保留市值较大的一条**，分母同样处理。

---

## 4.5 竞争分析章节（6.1~6.4）所需的两项取数

第 6 章要求**每个环节各自的 CR1/CR3/CR5** 与**行业市值分布（xx亿）**，需要额外两次取数（不要试图从「行业成分数」推市值）：

**(a) 行业市值分布 + 成分数（一次聚合，4 个环节一次取齐）**

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\指数F9\一页纸\指数F9_成分数据_成分股详情(综合)|676193052396478});
SetCodes(["{{TYPE_CODE}}.EI", "{{TYPE_CODE+1}}.EI", "{{TYPE_CODE+2}}.EI", "{{TYPE_CODE+3}}.EI"]);
SetReportFilter({交易日期} >= "{{最新成分交易日}}");
{指数代码}: REPORT_FIELD("指数代码");
{行业}: REPORT_FIELD("行业");
{总市值}: REPORT_FIELD("总市值(亿元)");
GroupBlock(#2, #1.{指数代码}, #1.{行业});
{行业市值合计}: SUM(#1.{总市值});
{行业成分数}: COUNT(true);
Sort({行业市值合计}, "DESC");
OutputBlock();
```
实测输出 35 行 × 4 列（4 环节 × 8~13 个行业），完全在 1,000 单元内。

**(b) 各环节 Top5 市值（算 CR 用）**

`GroupBlock` 不支持组内 TopN，因此**按环节分别取一次**（4 次小查询，各 5 行）：

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\指数F9\一页纸\指数F9_成分数据_成分股详情(综合)|676193052396478});
SetCodes(["{{某环节指数代码}}.EI"]);
SetReportFilter({交易日期} >= "{{最新成分交易日}}");
{证券简称}: REPORT_FIELD("证券简称");
{总市值}: REPORT_FIELD("总市值(亿元)");
Sort({总市值}, "DESC");
Head(5);
OutputBlock();
```

**替代方案（更省调用）**：一次取「指数代码 / 证券简称 / 总市值」3 列共 222 行（≈666 单元），本地按 `指数代码` 分组求 Top5 与合计——ETF/产业指数成分一般 ≤250 只时推荐此法。

CR 校验口径：`SUM(各环节总市值合计)` 会大于整体指数总市值（同一公司可能归属多个环节），**每个环节的 CR 分母必须用该环节自身的总市值合计**，不得用整体。

**4.5 成分行业分布 → 默认走兜底**

`指数F9成分行业|828709189779714` 实测 6 组参数均 0 行，**不要在此耗预算**。直接聚合：

> 从 `{{industry_index_stock}}` 的「行业」字段按二级细分聚合，倒序取前 15，格式如 `电子-半导体86个，电子-电子化学品Ⅱ14个，…`，存入 `{{industry_sample_num}}`。

**4.6 妙想搜索（可选）** — `mx_finance_search_report` / `mx_finance_search_news`（10 篇）、`mx_finance_search_notice`（5 篇）；Query = `{{INDEX_ABBR}}相关产业的` + 对应章节标题。

---

## 5. 数据格式化（注入 prompt 前必做）

**严禁把原始 MQL 返回 JSON 直接注入 prompt。** 按下列格式改写：

```
# 指数表现（产业链，4 环节）
产业整体（8880781.EI）最新数据：交易日=2026-09-30, 收盘=2601.7559, PE(TTM)=25.6676, PB(MRQ)=..., PS(TTM)=...
历史数据（按日期降序）：2026-09-30 收盘=2601.76 PE=25.67 | 2026-09-24 ... | ...

# 指数表现（产业指数，单指数）
指数代码 指数简称 交易日 指数收盘点位 指数滚动市盈率 指数最新市净率 指数滚动市销率
CI009133R.IDX 国金水泥20 2026-06-18 3125.5164 51.5452 3.4373 1.8577
*指数简介：国金水泥20指数为...

# 成分股
产业上游共80只成分股，总市值43107.73亿元。前10大市值股：
1. 宁德时代(300750.SZ) 市值18419亿 所属行业：电力设备

# 成分行业分布（产业指数）
电子-半导体86个，电子-电子化学品Ⅱ14个，…（倒序前15个）
```

数值必须带口径（报告期/交易日、单位、复权方式）；缺失项留空并标注，不得用推断值填充。