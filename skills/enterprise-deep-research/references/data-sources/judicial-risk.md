# 司法风险数据源

## 当前正式 MQL 主路径（Runtime 2.6.0）

司法风险四张汇总表当前按以下主路径和报表函数取数。每张表分别查询 `是否历史信息=0` 和 `1`，并在一次查询中使用 `IN(关系类型,["1","2","3","4"])`；若具体报表拒绝集合条件，才拆为四次单值查询。主路径执行失败后，先使用同业务 MQL 候选；被执行人固定使用下列备选路径。

| 数据集 | MQL 路径 | 函数名 |
|---|---|---|
| 失信被执行人 | `Choice报表\\报表指标\\Choice金融终端\\企业F9(发行人+工商企业)\\企业一页纸\\司法风险汇总信息\\失信被执行人汇总|081751076337787` | `RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTIONSINFO` |
| 被执行人 | `Choice报表\\报表指标\\Choice金融终端\\企业F9(发行人+工商企业)\\企业一页纸\\司法风险汇总信息\\被执行人汇总|006194229816016` | `RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTEDPERSONS` |
| 限制高消费 | `Choice报表\\报表指标\\Choice金融终端\\企业F9(发行人+工商企业)\\企业一页纸\\司法风险汇总信息\\限制高消费汇总|868338831875985` | `RPT_CUSTOM_ENT_JUDICIAL_SUM_RESTRICTEDCONSUMER` |
| 终本案件 | `Choice报表\\报表指标\\Choice金融终端\\企业F9(发行人+工商企业)\\企业一页纸\\司法风险汇总信息\\终本案件汇总|349894282139442` | `RPT_CUSTOM_ENT_JUDICIAL_SUM_TERMINATIONCASE` |

被执行人主路径历史上曾返回上游报表服务失败，2026-09-30 本轮复测当前及历史均已通过；备选路径为 `Choice报表\\报表指标\\Choice金融终端\\企业F9\\企业一页纸\\司法风险汇总信息\\被执行人\\被执行人汇总|024220940284594`，函数名仍为 `RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTEDPERSONS`。主路径仍优先，仅本次失败或关键结果不可用时切换，四类关系类型和当前/历史范围保持不变。模板渲染器只生成 MQL，不自动发起查询或回退。

本轮阳光城四张主表及被执行人备选共10次执行均成功（当前/历史各一次）。请求范围为关系类型1/2/3/4，实际各次返回1/3/4三行；“查询覆盖四类”不等于“四类均有返回记录”。类型2未返回不得填零，须在内部登记未返回状态。执行编号及实际类型见 [MQL核验记录](mql-verification.json) 的 `latest_template_checks`。

### 14. 司法风险

状态：按本板块最新配置重做。司法风险板块只使用失信被执行人、被执行人、限制高消费、终本案件四类结构化风险数据；每类以用户确认的司法汇总表为第一候选，汇总表不可用时才使用同业务司法明细 MQL 回退。正式取数必须先通过 MQL MCP；下列公网 REST 规格只允许在该类数据的全部 MQL 候选失败、超时、元数据无法绑定或关键字段缺失时作为本地 Python 兜底，不得把 REST 作为正常主路径。

#### 14.1 MQL 数据包边界

`司法风险` 只形成一个独立的 `block_data_package`，数据包键为 `judicial`，只传入 `references/analysis-prompts/judicial-risk.md` 的 `{{数据}}`。该数据包同时作为正文后的司法风险汇总表唯一数据源。数据包只能包含下列四类风险数据的最终有效结构化结果；最终来源可以是对应汇总表或同业务明细 MQL，但不能同时混用两者，也不能混入信用分析、股东情况、财务、债券或其它板块原始数据：

1. 失信被执行人：`RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTIONSINFO`；
2. 被执行人：`RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTEDPERSONS`；
3. 限制高消费：`RPT_CUSTOM_ENT_JUDICIAL_SUM_RESTRICTEDCONSUMER`；
4. 终本案件：`RPT_CUSTOM_ENT_JUDICIAL_SUM_TERMINATIONCASE`。

用户确认的业务路径如下，检索时同时提交对应路径和函数名：

| 函数名 | 业务路径 |
|---|---|
| `RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTIONSINFO` | `/Choice金融终端/企业F9(发行人+工商企业)/企业一页纸/司法风险汇总信息/失信被执行人汇总` |
| `RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTEDPERSONS` | `/Choice金融终端/企业F9(发行人+工商企业)/企业一页纸/司法风险汇总信息/被执行人汇总` |
| `RPT_CUSTOM_ENT_JUDICIAL_SUM_RESTRICTEDCONSUMER` | `/Choice金融终端/企业F9(发行人+工商企业)/企业一页纸/司法风险汇总信息/限制高消费汇总` |
| `RPT_CUSTOM_ENT_JUDICIAL_SUM_TERMINATIONCASE` | `/Choice金融终端/企业F9(发行人+工商企业)/企业一页纸/司法风险汇总信息/终本案件汇总` |

四张主表均使用上表的完整中文路径和函数名；完整可执行 MQL 路径仍以当次 `Search_Context` 的实际返回为准，不改写历史查询证据。路径确认不代表字段缺陷已修复或当前/历史查询已通过。

每张表必须分别查询当前记录与历史信息，并按 `TYPE` 整理为以下结构：

```text
司法风险
├── 本公司
│   ├── 当前记录
│   └── 历史信息
└── 关联方
    ├── 实控人
    ├── 主要股东
    └── 参股控股子公司
```

关系类型映射固定为：

```text
TYPE="1" → 本公司
TYPE="2" → 关联方/实控人
TYPE="3" → 关联方/主要股东
TYPE="4" → 关联方/参股控股子公司
```

不再加入以下内容：`ORG_HOLD_RATIO>=50` 或其它持股比例过滤、近一年日期窗口、金额上下界、裁判文书、诉讼仲裁、开庭公告、监管处罚、股权冻结以及 `post-loan-risk-analysis` 的其它补充数据。

#### 14.2 MQL 查询与字段规则

MQL 必须先执行 `Get_MQL_Reference → Search_Business_Knowledge → Search_Context`。四张表正式执行前，必须以本次 `Search_Context` 返回的完整报表路径、`reportFields[].column_name_cn` 字段名和 `reportFilterColumns[].column_name_cn` 为准；下表中的中文字段是当前已核对的业务字段映射，若 Runtime 返回的绑定名不同，以 Runtime 实际返回名覆盖：

| 数据集 | 函数名 | MQL 过滤字段 | MQL 结果字段 |
|---|---|---|---|
| 失信被执行人 | `RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTIONSINFO` | `公司代码`、`关系类型`、`是否历史信息` | `关系类型`、当前/历史案件数、当前/历史执行标的（万元） |
| 被执行人 | `RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTEDPERSONS` | `公司代码`、`关系类型`、`是否历史信息` | `关系类型`、当前/历史案件数、当前/历史执行标的（万元） |
| 限制高消费 | `RPT_CUSTOM_ENT_JUDICIAL_SUM_RESTRICTEDCONSUMER` | `公司代码`、`关系类型`、`是否历史信息` | `关系类型`、当前/历史案件数 |
| 终本案件 | `RPT_CUSTOM_ENT_JUDICIAL_SUM_TERMINATIONCASE` | `公司代码`、`关系类型`、`是否历史信息` | `关系类型`、当前/历史案件数、当前/历史执行总金额（万元）、当前/历史未履行总金额（万元）、当前/历史未履行比例（%） |

MQL 的每张表原则上执行两次，分别查询当前与历史信息；每次使用一次关系类型集合过滤：

```text
当前记录：
公司代码 = <目标企业ORG_CODE>
关系类型 = `IN({关系类型}, ["1", "2", "3", "4"])`
是否历史信息 = 0

历史信息：
公司代码 = <目标企业ORG_CODE>
关系类型 = `IN({关系类型}, ["1", "2", "3", "4"])`
是否历史信息 = 1
```

在 MQL Block 中：

- `reportStandardCodeSupported=false` 时，不使用 `SetCodes`、`GetSectors`；
- 使用 `SetReportFilter` 绑定 `公司代码`、`关系类型`、`是否历史信息`，字段名必须是本次 `Search_Context` 实际返回的 MQL Runtime 绑定名称；
- 使用 `REPORT_FIELD()` 取四张表的实际返回字段，不得把 Python REST 字段别名直接写入 MQL；
- 不增加 `对外投资持股比例范围`、日期范围或金额上下界过滤；
- 不按日期字段或无关字段排序；
- 当前与历史是两次独立口径，不能将两次结果相加。

本地整理时将 MQL 字段映射为以下输出名称：

```text
失信被执行人：
  案件数、涉案总金额(万元)
被执行人：
  案件数、执行总金额(万元)
限制高消费：
  案件数
终本案件：
  案件数、执行总金额(万元)、未履行总金额(万元)、未履行比例(%)
```

如果某张表按关系类型返回多行，仅在同一表、同一期间、同一关系类别内整理；金额字段保持原单位“万元”，未履行比例直接使用接口值，不自行换算。任何缺失值保留为空，不用其它表的字段补齐。

司法风险汇总表在文字分析完成后生成。表格按风险类型和关系主体逐行列示，当前与历史分列；仅保留至少有一个有效指标的行，不把空值渲染为 0，不将四张表的金额相加，也不以资讯补造结构化司法指标。

#### 14.2.1 MQL 候选回退与验证边界

指定的四个汇总函数和路径必须保留为第一候选；若某一类汇总候选出现元数据或服务失败，只对该类先使用同业务的“司法风险数据”明细候选，并按当前/历史及关系类型整理为本板块数据包。查询证据见 [MQL核验记录](mql-verification.json)；同一函数的路径仍需以本次 `Search_Context` 返回为准，不能仅凭函数后缀互换。其它风险类别若汇总查询成功，不得因为某一类别发生回退而整体改用明细或 REST。

已找到的同业务 MQL 明细候选包括：

```text
Choice报表\\报表指标\\Choice金融终端\\企业F9\\企业一页纸\\司法风险汇总信息\\被执行人\\被执行人汇总|024220940284594
Choice报表\\报表指标\\Choice金融终端\\企业F9(发行人+工商企业)\\司法风险数据\\被执行人\\被执行人|RPT_CUSTOM_ENT_EXECUTEDPERSONS
Choice报表\\报表指标\\Choice金融终端\\企业F9(发行人+工商企业)\\司法风险数据\\失信被执行人\\失信被执行人|RPT_CUSTOM_ENT_EXECUTIONSINFO
Choice报表\\报表指标\\Choice金融终端\\企业F9(发行人+工商企业)\\司法风险数据\\限制高消费\\限制高消费|RPT_CUSTOM_JUDICIAL_RESTRICTEDCONSUMER
Choice报表\\报表指标\\Choice金融终端\\企业F9(发行人+工商企业)\\司法风险数据\\终本案件\\终本案件|RPT_CUSTOM_ENT_TERMINATIONCASE
```

明细候选使用 `公司代码`、`关系类型`、`是否历史信息` 过滤；运行时若提示关系类型仅支持单选，则必须分别对关系类型 `1`、`2`、`3`、`4` 执行，不得删除关系条件。被执行人明细实际可返回“执行标的(元）”“立案时间”“案号”“执行法院”等字段，可在本地按案件逐条汇总；金额换算为万元仅在本地展示整理时进行。若汇总候选和明细候选均失败，再使用对应 Python REST 兜底。

当前候选验证边界如下：

| 风险类别 | 第一候选 | 第一备选 MQL 路径 | 当前验证状态 |
|---|---|---|---|
| 失信被执行人 | `RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTIONSINFO` | 按本次 Search_Context 返回的同业务候选 | 新主路径；执行时仍须按本次元数据核对字段 |
| 被执行人 | `RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTEDPERSONS` | `Choice报表\\报表指标\\Choice金融终端\\企业F9\\企业一页纸\\司法风险汇总信息\\被执行人\\被执行人汇总|024220940284594` | 主路径失败时固定使用该备选，再回退司法风险明细 |
| 限制高消费 | `RPT_CUSTOM_ENT_JUDICIAL_SUM_RESTRICTEDCONSUMER` | 按本次 Search_Context 返回的同业务候选 | 主路径成功时不切换；失败时不得将失败记为空 |
| 终本案件 | `RPT_CUSTOM_ENT_JUDICIAL_SUM_TERMINATIONCASE` | 按本次 Search_Context 返回的同业务候选 | 新主路径；执行时仍须按本次元数据核对字段 |

已验证的第一备选 MQL 路径不是四张主表的永久替代。每次运行仍先执行对应主路径；仅当“被执行人”主路径失败时，才使用本节固定的 `|024220940284594` 备选。主路径和第一备选均失败后，才执行同业务司法风险明细候选；明细候选成功后，只能使用其自身返回的案件行汇总该风险类别，明细候选失败后才允许使用 Python REST。不能因为备选当前成功，就跳过未来运行中的主路径。

- 失信、被执行人汇总候选可能报 `columns字段不合法：AMOUNT _SUM`；历史字段亦可能存在 `AMOUNT_SUM_ HISTORY`、`NUMBER_SUM_ HISTORY` 空格缺陷。此时不得把错误记为空，应尝试上面的明细候选。
- 终本全字段查询报 `columns字段不合法：AMOUNT_SUM_ HISTORY`。
- 删除异常列后的其它候选路径仍报 `TYPE列不存在`，不能把部分试探或删除关系条件当完整通过。
- 四张主表的新函数名和路径必须成对使用，不得把旧的 `RPT_CUSTOM_JUDICIAL_*_SUM` 名称套用于新路径；备选明细函数仍按上表单独配置。
- MQL 主路径在当前 Runtime 2.6.0 中使用 `IN({关系类型}, ["1", "2", "3", "4"])` 一次查询四类关系；若某个具体报表服务明确拒绝 `IN`，才将该表拆成四次单值查询，不能省略关系类型。Python REST 兜底继续按 `TYPE="1"`、`"2"`、`"3"`、`"4"` 分开查询；不擅加日期、金额或持股阈值。
- 当前/历史均为用户需求；某条汇总查询失败不代表该风险类型为空，必须继续尝试明细候选。只有 MQL 汇总和明细均成功且返回零行，才可登记为 `empty`；查询失败保持 `failed`，不得解释为零司法风险。

#### 14.2.2 历史验证与本轮复测（2026-09-30）

以下保留前次阳光城集团股份有限公司（ORG_CODE=`10005596`）和贵州茅台酒股份有限公司（ORG_CODE=`10002602`）的验证情况；本轮阳光城四张主表及被执行人备选的当前/历史已全部通过，以文件开头及 `latest_template_checks` 为最新状态。每张表仍按 `IS_HISTORY="0"/"1"` 分口径，使用 `IN({关系类型}, ["1", "2", "3", "4"])`，不以请求范围代替实际返回覆盖。

- 失信被执行人、限制高消费、终本案件：新主路径和新函数名使用一次 `IN` 条件即可正常执行。阳光城三张表均返回 `TYPE=1`、`TYPE=3`、`TYPE=4`，`TYPE=2` 在本样例为空；贵州茅台返回空结果，属于成功返回空行，不判定为接口失败。
- 被执行人：前次新主路径在 MQL 数据量预估阶段报“报表服务请求失败”，两企业均曾复现；本轮阳光城当前/历史已成功，历史失败不代表当前仍不可用，也不能解释为无数据。
- 被执行人已验证的 MQL 备选为 `Choice报表\\报表指标\\Choice金融终端\\企业F9\\企业一页纸\\司法风险汇总信息\\被执行人\\被执行人汇总|024220940284594`。该候选使用一次 `IN` 条件即可执行，阳光城返回 `TYPE=1`、`TYPE=3`、`TYPE=4`，`TYPE=2` 在本样例为空；贵州茅台当前查询可执行并返回空行，历史查询返回 `TYPE=1`、`TYPE=3`、`TYPE=4`。

运行时路由固定为：先尝试用户指定的四张主表；MQL 默认按当前/历史各一次、使用 `IN` 查询四类关系。被执行人主表 MQL 服务失败时，仅该风险类别切换到本节已验证的同业务备选；若具体报表拒绝 `IN`，才拆成四个单值 `TYPE` 查询。主候选和备选均失败时，才进入该类别的 Python REST 兜底。其它三个风险类别不因“被执行人”失败而整体切换。

#### 14.3 Python REST 兜底规范

仅当对应风险类别的汇总 MQL、明细 MQL 均失败、超时、元数据无法绑定或关键字段缺失时，才由 `scripts/get_data.py` 通过 Choice REST 兜底。四类风险严格使用以下 reportName，不替换为其它旧版函数名：

```text
RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTIONSINFO
RPT_CUSTOM_ENT_JUDICIAL_SUM_EXECUTEDPERSONS
RPT_CUSTOM_ENT_JUDICIAL_SUM_RESTRICTEDCONSUMER
RPT_CUSTOM_ENT_JUDICIAL_SUM_TERMINATIONCASE
```

每张表各执行当前、历史两次请求：

```text
filter=(ORG_CODE="<ORG_CODE>")(TYPE="1")(IS_HISTORY="0")
filter=(ORG_CODE="<ORG_CODE>")(TYPE="2")(IS_HISTORY="0")
filter=(ORG_CODE="<ORG_CODE>")(TYPE="3")(IS_HISTORY="0")
filter=(ORG_CODE="<ORG_CODE>")(TYPE="4")(IS_HISTORY="0")
filter=(ORG_CODE="<ORG_CODE>")(TYPE="1")(IS_HISTORY="1")
filter=(ORG_CODE="<ORG_CODE>")(TYPE="2")(IS_HISTORY="1")
filter=(ORG_CODE="<ORG_CODE>")(TYPE="3")(IS_HISTORY="1")
filter=(ORG_CODE="<ORG_CODE>")(TYPE="4")(IS_HISTORY="1")

pageNumber=1&pageSize=200&source=choice&client=SW
```

Python 兜底保留四张表各自的案件数、金额和比例字段，并兼容接口可能返回的带空格历史物理列名，例如 `NUMBER_SUM_ HISTORY`、`AMOUNT_SUM_ HISTORY`；兼容只用于本地字段归一，不得反向写入 MQL。整理结果必须包含：

```json
{
  "current": {
    "本公司": {},
    "关联方": {
      "实控人": {},
      "主要股东": {},
      "参股控股子公司": {}
    }
  },
  "history": {
    "本公司": {},
    "关联方": {
      "实控人": {},
      "主要股东": {},
      "参股控股子公司": {}
    }
  },
  "datasets": {
    "dishonest": {},
    "executed": {},
    "restricted": {},
    "termination": {}
  }
}
```

兜底来源必须登记为 `Python REST fallback`，并注明对应 MQL 失败原因。某一风险类别的汇总、明细及其最终 REST 兜底均失败时，该类别保持 failed；四类风险数据均无可用结构化结果时，司法风险 prompt 按其原文规则处理。不得用信用分析、股东情况、司法新闻或其它板块数据替代结构化司法数据。

#### 14.4 资讯来源

`{{资讯}}` 仅使用 `mx-finance-search`，对目标企业执行一条固定 query：

```text
查询<企业全名> 最新司法风险
```

例如：

```text
查询中国民生银行股份有限公司 最新司法风险
```

不得再执行“最新监管处罚” query，也不得把其它板块的资讯传入司法风险 prompt。资讯结果整理为当前板块独立的 `block_news_package`，来源分类、权威度和发布时间排序按 [news-processing.md](../news-processing.md) 执行；每条资讯保留完整内容，并单独记录内部审计状态，编号不进入分析输入或正文。

#### 14.5 分析口径

司法风险 prompt 必须严格区分本公司与关联方，当前记录优先于历史信息；历史信息只能作为历史风险对照，不能与当前记录相加。失信被执行人、被执行人、限制高消费和终本案件四类指标分别使用各自字段，金额不得跨表或跨维度混用，不得擅自换算单位。关联方风险仅在对应 `TYPE` 有数据时分析控制权、资金占用、经营连续性或声誉传导，不把关联方记录直接归属于本公司。结构化数据优先于资讯，资讯只用于补充公开事件和舆情。若结构化数据和资讯均为空，严格按 `judicial-risk.md` 返回 `暂无数据`。

