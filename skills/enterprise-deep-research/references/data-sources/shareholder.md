# 股东情况数据源

### 2. 股东情况

状态：主要股东明细以 `RPT_BOND_GQJG_ISHOLDER` 完整路径为 MQL 主路径，已用贵州茅台验证成功；发行人指标和同业务主要股东报表仅作为备选。关联交易 8 字段已返回数据；股东股权摘要 7 字段可用，减持比例受元数据错误阻塞。详见 [MQL核验记录](mql-verification.json) 和 [固化 MQL 查询模板](mql-templates.md)。

主路径使用企业代码 `10002602`、截止日期 `2026-06-30` 返回 11 行，即合计行和十名股东明细；返回字段为 `股东名称`、`持有数量/金额`、`持有比例(%)`、`股东是否为发行人`。

#### `{{数据}}` MQL 主路径

股东情况板块的 `{{数据}}` 必须用 MQL 分别读取以下三组逻辑数据，并整理进同一个当前板块专属 `block_data_package`：股东股权、关联交易、最新报告期的主要股东明细。主要股东明细用于正文后的主要股东表格，不能因为分析 prompt 只要求段落而省略。

### 主要股东明细（主要股东表格）

主要股东表格的 MQL 主路径使用用户确认的 `RPT_BOND_GQJG_ISHOLDER` 完整路径，并按报表实际字段读取前十大股东和接口返回的合计行；若主路径无法召回、字段不能绑定或执行失败，再使用发行人指标路径或同业务主要股东报表备选。结果按持股比例降序整理，剔除排序结果中的合计行后保留前十大股东，最后追加接口返回的合计行。表格固定展示四列：股东名称、持有数量(股)、持有比例(%)、股东是否为发行人。`持有数量/金额`按该报表口径展示为持有数量(股)；`股东是否为发行人` 的返回值 `1` 显示为“是”，空值显示为“-”，不得根据股东名称自行推断。不得自行把十名明细相加替代接口提供的合计值；主路径或备选均未返回合计行时，不补造合计行。

MQL 中的报表路径、过滤字段和 `REPORT_FIELD()` 名称必须以本次 `Search_Context` 实际返回为准；已核对的物理字段及展示映射如下：

| 展示列 | 实际字段 | 口径 |
|---|---|---|
| 股东名称 | `股东名称` | 报表排序后保留明细，合计行显示“合计” |
| 持有数量(股) | `持有数量/金额` | 按报表返回值展示；合计使用接口返回值 |
| 持有比例(%) | `持有比例(%)` | 按报表返回值展示；合计使用接口返回值 |
| 股东是否为发行人 | `股东是否为发行人` | `1` 显示“是”，空值显示“-” |

主路径不使用 `RANK`；`RANK` 仅在 Python REST 兜底读取旧报表时用于内部排序和识别，不展示。图表不展示较上期持股变动数、持股比例变动或名次。

主要股东明细只进入股东情况的数据包和表格组件，不进入其它板块。Python 兜底复用同一份 `fetch_shareholders()` 结果中的 `top_holders`，不要再次用股东股权摘要或资讯补造表格。

主要股东明细的业务路径固定为（MQL 主候选，末级段和报表 ID 必须完整保留）：

```text
Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\股东股权\股东明细\股东明细\主要股东|789604172179402
```

该主候选已用 MQL Runtime 2.6.0 执行成功；固定字段和过滤条件以本文件及 [mql-templates.md](mql-templates.md) 中的样例为准。若本次企业或日期执行失败，才按候选链切换到发行人指标或本文件登记的同业务候选。

股东股权表读取所有信息：

```text
/Choice金融终端/企业F9/企业一页纸/股东股权
```

关联交易表只读取指定字段：

```text
/Choice金融终端/企业F9/企业一页纸/关联交易
```

关联交易传入提示词的展示字段白名单固定为：

```text
公告日期、交易对方、关联交易类型、关联关系、是否存在控制关系、交易金额（万元）、币种、交易简述
```

MQL 执行要求：

- 先通过 `Search_Context` 定位两张逻辑表对应的实际 MQL 报表。当前已核对的实际报表分别为 `Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\股东股权\增减持股东\股东股权` 和 `Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\关联交易\沪深F9_重大事项_关联交易`。执行前仍须以本次 `Search_Context` 返回的同名候选及其 `reportFilterColumns`、`reportFields` 为最终依据。
- `股东股权` 报表的实际主体过滤字段为 `ORG_CODE`，报告期过滤优先使用实际加载字段 `END_DATE`，实际返回字段为 `HOLDER_NAME_DOWN`、`HOLDER_NAME_UP`、`HOLDER_RATIO_ DOWN`、`HOLDER_RATIO_UP`、`ORG_CODE`、`REPORT_DATE`、`SJKZR`、`TOP1_HOLDER_ST`。其中 `HOLDER_RATIO_ DOWN` 含空格是本轮实测的上游元数据缺陷，调用 `减持比例` 会报 `columns字段不合法`。不得擅自去空格猜字段；先保留其余 7 字段，再用同源 Python 补取缺项，仍失败则记录部分缺失。`END_DATE` 仅用于筛选最新报告期，不作为展示字段；`REPORT_DATE` 用于返回和整理时间标签。
- `关联交易` 报表的实际主体及日期过滤字段为 `ORG_CODE`、`NOTICE_DATE`；提示词展示字段对应的实际字段为 `NOTICE_DATE`、`RELATED_PARTY`、`TRADE_WAY`、`RELATED_RELATION`、`IS_CONTROL`、`TRADE_AMT`、`CURRENCY`、`TRADE_PROFILE`。
- `关联交易` 的实际 MQL 报表候选已确认 `NOTICE_DATE` 和 `ORG_CODE` 可作为 `SetReportFilter` 字段，`RELATED_PARTY`、`TRADE_WAY`、`RELATED_RELATION`、`IS_CONTROL`、`TRADE_AMT`、`CURRENCY`、`TRADE_PROFILE` 均来自 `reportFields[].column_name`；MQL 应使用 MQL Runtime 已绑定的中文字段名：公告日期、关联方、关联交易类型、关联关系、是否存在控制关系、交易金额、币种、交易简介；“交易对方”“交易简述”只是本地展示别名。
- `股东股权` 表应读取该表返回的全部实际字段；`关联交易` 表只读取上述 8 个实际字段，不得把其它关联交易字段混入本板块 `{{数据}}`。MQL 的加载列和返回列分别使用元数据中的实际绑定字段名；英文物理列仅用于来源映射。
- `股东股权` 默认取最新可用报告期/日期口径，并在整理后的 `{{数据}}` 中保留时间标签，例如 `股东股权（时间：YYYY-MM-DD）`。
- `关联交易` 默认按公告日期倒序取近一年记录；若 `股东股权` 最新报告期可用，则以该日期为区间终点向前回溯一年；否则以系统日为终点向前回溯一年。若用户另行指定时间范围，以用户指定为准，并在整理后的 `{{数据}}` 中保留区间标签，例如 `关联交易（时间：YYYY-MM-DD至YYYY-MM-DD）`。
- 返回结果整理为适合 `shareholder.md` 中 `{{数据}}` 的 Markdown 表格或键值对。示例结构可为 `## 股东股权（时间：...）` 和 `## 关联交易（时间：...至...）` 两部分。
- 主路径结果中，先按 `持有比例(%)` 降序整理，识别并移除接口返回的“合计”行，再保留有效的十大股东明细，最后追加原始合计行。股东名称、持有数量或持有比例均无具体值的明细行不展示；主路径或备选未返回合计行时不补造合计。

以下为已运行的部分字段模板。股东股权 `截止日期` 传查询系统日，接口返回的 `报告期` 再用于关联交易近一年窗口；不能把输入截止日期当作实际报告期。当前缺失的减持比例必须单独登记，不能将 7 列状态标为全部信息已取得。

主路径的 MQL 一次查询返回十名股东和合计行，不得改写为发行人指标的逐名次查询。主路径样例如下；若主路径失败，发行人指标备选才按“第一名”至“第十名”逐名查询，并另查“前十名”合计值。备选排名名称必须按指标元数据使用，不能自行改写为英文或旧报表字段。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\股东股权\股东明细\股东明细\主要股东|789604172179402});
SetReportFilter({发行人代码} == "<ORG_CODE>" AND {截止日期} == "<END_DATE>");
{股东名称}: REPORT_FIELD("股东名称");
{持有数量/金额}: REPORT_FIELD("持有数量/金额");
{持有比例(%)}: REPORT_FIELD("持有比例(%)");
{股东是否为发行人}: REPORT_FIELD("股东是否为发行人");
Sort({持有比例(%)}, "DESC");
Head(15);
OutputBlock();
```

主路径失败后的发行人指标备选：第一名至第十名逐名查询，并另查前十名合计。

```mql
CrossSectionBlock(#1, {EM_CODE});
SetCodes(["<ORG_CODE>.FXR"]);
{第一名_股东名称}: {Choice指标\发行人\企业全部指标\基本信息\股东信息\十大股东名称|100000000035591}({截止日期} = "最新", {大股东排名1} = "第一名");
{第一名_持股数量}: {Choice指标\发行人\企业全部指标\基本信息\股东信息\十大股东持股数量|100000000035592}({截止日期} = "最新", {大股东排名1} = "第一名");
{第一名_持股比例}: {Choice指标\发行人\企业全部指标\基本信息\股东信息\十大股东持股比例(%)|100000000035593}({截止日期} = "最新", {大股东排名1} = "第一名");
OutputBlock();

# 将上方三个指标中的“第一名”依次替换为“第二名”至“第十名”，分别执行十次，并使用独立输出列名；每次返回整理为一行。
# 合计查询：同样执行名称、数量和比例指标，将排名参数改为“前十名”；仅保留持股数量和持股比例返回值。
CrossSectionBlock(#2, {EM_CODE});
SetCodes(["<ORG_CODE>.FXR"]);
{前十名_股东名称}: {Choice指标\发行人\企业全部指标\基本信息\股东信息\十大股东名称|100000000035591}({截止日期} = "最新", {大股东排名1} = "前十名");
{前十名_持股数量}: {Choice指标\发行人\企业全部指标\基本信息\股东信息\十大股东持股数量|100000000035592}({截止日期} = "最新", {大股东排名1} = "前十名");
{前十名_持股比例}: {Choice指标\发行人\企业全部指标\基本信息\股东信息\十大股东持股比例(%)|100000000035593}({截止日期} = "最新", {大股东排名1} = "前十名");
OutputBlock();

ReportBlock(#3, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\关联交易\沪深F9_重大事项_关联交易});
SetReportFilter(({公司代码} == "<ORG_CODE>") AND ({公告日期} >= "<START_DATE>") AND ({公告日期} <= "<END_DATE>"));
{公告日期}: REPORT_FIELD("公告日期");
{关联方}: REPORT_FIELD("关联方");
{关联交易类型}: REPORT_FIELD("关联交易类型");
{关联关系}: REPORT_FIELD("关联关系");
{是否存在控制关系}: REPORT_FIELD("是否存在控制关系");
{交易金额}: REPORT_FIELD("交易金额");
{币种}: REPORT_FIELD("币种");
{交易简介}: REPORT_FIELD("交易简介");

OutputBlock();
```

`block_data_package` 登记要求：

```json
{
  "block_name": "股东情况",
  "prompt_file": "references/analysis-prompts/shareholder.md",
  "datasets": [
    {
      "dataset": "/Choice金融终端/企业F9/企业一页纸/股东股权/股东明细/股东明细/主要股东",
      "mql_report": "Choice报表\\报表指标\\Choice金融终端\\企业F9\\企业一页纸\\股东股权\\股东明细\\股东明细\\主要股东|789604172179402",
      "query_path": "MQL",
      "fields": [
        "股东名称", "持有数量/金额", "持有比例(%)", "股东是否为发行人"
      ],
      "filter": "发行人代码=<ORG_CODE>；截止日期=<END_DATE>；按持有比例(%)降序；Head(15)",
      "rows": []
    },
    {
      "dataset": "/Choice金融终端/企业F9/企业一页纸/股东股权",
      "mql_report": "Choice报表\\报表指标\\Choice金融终端\\企业F9\\企业一页纸\\股东股权\\增减持股东\\股东股权",
      "query_path": "MQL",
      "fields": [
        "HOLDER_NAME_DOWN", "HOLDER_NAME_UP", "HOLDER_RATIO_ DOWN",
        "HOLDER_RATIO_UP", "ORG_CODE", "REPORT_DATE", "SJKZR",
        "TOP1_HOLDER_ST"
      ],
      "filter": "ORG_CODE=<ORG_CODE>；END_DATE=<系统日 YYYY-MM-DD>；返回 REPORT_DATE",
      "rows": []
    },
    {
      "dataset": "/Choice金融终端/企业F9/企业一页纸/关联交易",
      "mql_report": "Choice报表\\报表指标\\Choice金融终端\\企业F9\\企业一页纸\\关联交易\\沪深F9_重大事项_关联交易",
      "query_path": "MQL",
      "fields": [
        "NOTICE_DATE", "RELATED_PARTY", "TRADE_WAY", "RELATED_RELATION",
        "IS_CONTROL", "TRADE_AMT", "CURRENCY", "TRADE_PROFILE"
      ],
      "display_field_map": {
        "NOTICE_DATE": "公告日期",
        "RELATED_PARTY": "交易对方",
        "TRADE_WAY": "关联交易类型",
        "RELATED_RELATION": "关联关系",
        "IS_CONTROL": "是否存在控制关系",
        "TRADE_AMT": "交易金额（万元）",
        "CURRENCY": "币种",
        "TRADE_PROFILE": "交易简述"
      },
      "filter": "ORG_CODE=<ORG_CODE>；NOTICE_DATE 在 <START_DATE> 至 <END_DATE>",
      "rows": []
    }
  ],
  "sources": [
    {
      "block": "股东情况",
      "placeholder": "{{数据}}",
      "path": "MQL",
      "dataset": "/Choice金融终端/企业F9/企业一页纸/股东股权/股东明细/股东明细",
      "status": "ok"
    },
    {
      "block": "股东情况",
      "placeholder": "{{数据}}",
      "path": "MQL",
      "dataset": "/Choice金融终端/企业F9/企业一页纸/股东股权",
      "status": "ok"
    },
    {
      "block": "股东情况",
      "placeholder": "{{数据}}",
      "path": "MQL",
      "dataset": "/Choice金融终端/企业F9/企业一页纸/关联交易",
      "status": "ok"
    }
  ]
}
```

#### `{{资讯}}` mx-finance-search 查询

股东情况板块的 `{{资讯}}` 必须使用 `mx-finance-search`，query 格式固定为：

```text
<企业全名> 股权 相关资讯 最新动态
```

示例：

```text
中国民生银行股份有限公司 股权 相关资讯 最新动态
```

资讯结果整理为当前板块专属 `block_news_package`，只传入 `shareholder.md` 的 `{{资讯}}`。优先保留与股权结构、股东变化、股权质押、主要股东增减持、关联交易、公司治理相关的公告、研报和新闻；不得将该资讯包传给其它板块。

`block_news_package` 登记要求：

```json
{
  "block_name": "股东情况",
  "prompt_file": "references/analysis-prompts/shareholder.md",
  "news_queries": [
    {
      "query": "<企业全名> 股权 相关资讯 最新动态",
      "tool": "mx-finance-search",
      "purpose": "股权结构、股东变化、股权质押、关联交易与公司治理动态"
    }
  ],
  "sources": [
    {
      "block": "股东情况",
      "placeholder": "{{资讯}}",
      "path": "mx-finance-search",
      "dataset": "<企业全名> 股权 相关资讯 最新动态",
      "status": "ok"
    }
  ]
}
```

#### Python REST 兜底

仅当 `RPT_BOND_GQJG_ISHOLDER` 主候选、发行人指标备选、已登记或动态发现的同业务 MQL 候选均失败、超时或关键字段缺失时，才允许参考 `equity-ownership-analysis` 已验证口径使用下列 REST 查询作为 Python 兜底模板。以下 `RPT_BOND_GQJG_ISHOLDER` 是 Python 兜底调用，不等同于 MQL 主候选：

```text
# 最新报告期
reportName=RPT_BOND_GQJG_ISHOLDER
columns=ISSUE_CODE,END_DATE,END_DATE_ORIG
filter=(ISSUE_CODE="<ORG_CODE>")(IS_SHOW=1)
sortColumns=END_DATE&sortTypes=-1&pageNumber=1&pageSize=1&client=SW

# 十大股东
reportName=RPT_BOND_GQJG_ISHOLDER
columns=ALL
filter=(ISSUE_CODE="<ORG_CODE>")(END_DATE='<最新报告期 yyyy-MM-dd>')(IS_SHOW=1)
pageNumber=1&pageSize=50&client=SW

# 实控人/第一大股东/增减持
reportName=RPT_CUSTOM_ORG_SHAREHOLDER_EQUITY
filter=(ORG_CODE="<ORG_CODE>")(END_DATE='<系统日 yyyy-MM-dd>')
source=CHOICE&client=SW

# 关联交易（补充）
reportName=RPT_RELATED_TRANSACTION
columns=ALL
filter=(ORG_CODE="<ORG_CODE>")(NOTICE_DATE>='<系统日-365 yyyy-MM-dd>')(NOTICE_DATE<='<系统日 yyyy-MM-dd>')
sortColumns=NOTICE_DATE&sortTypes=-1&pageNumber=1&pageSize=50&source=choice&client=SW
```

兜底注意事项：

- `RPT_BOND_GQJG_ISHOLDER` 和 `RPT_RELATED_TRANSACTION` 必须显式传 `columns=ALL`；十大股东需过滤 `RANK=9999` 的“合计”行。
- Python 兜底结果必须拆成股东情况板块自己的 `block_data_package`，`placeholder` 标记为 `{{数据}}`。
- 兜底的关联交易最终传入 prompt 前仍必须裁剪为 `公告日期、交易对方、关联交易类型、关联关系、是否存在控制关系、交易金额（万元）、币种、交易简述` 这 8 个字段，不得把完整 REST 行直接喂给 prompt。

