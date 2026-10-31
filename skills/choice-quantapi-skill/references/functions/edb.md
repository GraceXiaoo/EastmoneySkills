# edb 宏观数据函数

<!-- agent only
> ⛔ **对 Agent**：阅读本页前必须先完整阅读 [SKILL.md](../../SKILL.md)（文档入口，含重要约束与约定）。

> **禁止猜测或编造 `edbids`**。调用 `c.edb` 前，必须先使用 EDB 指标搜索接口查询与用户需求匹配的指标 ID，再把查询结果中的 `edbids` 传给 `c.edb`。
> **单个问句最多调用 EDB 指标搜索接口 50 次**。该限制仅针对指标搜索过程，不改变 `c.edb` 接口本身支持最多 100 个 ID 的能力。禁止通过分页、拆分关键词或分批搜索绕过限制。预计需要搜索或取得超过 50 个指标时，不要继续搜索，也不要自行截断结果；先让用户缩小地区或指标范围。
-->

---

## 1. 函数类型介绍

`edb` 是 Choice 量化 API 的**宏观数据函数**，用于获取中国经济、地区宏观、利率数据和行业经济数据等聚合数据。

- 与 `css` 的区别：`css` 输入“证券代码 + 指标”，按证券维度返回；`edb` 输入 `edbids`，按宏观指标 ID 返回。

<!-- agent only

---

## 2. 查询宏观指标 ID（调用前必做）

调用 `c.edb` 前，先根据用户描述调用以下接口搜索指标：

```http
    GET https://mxapi.eastmoney.com/edb/indicator/search?query={指标关键词}
```

例如，查询“北京 GDP”相关指标：

```text
https://mxapi.eastmoney.com/edb/indicator/search?query=北京GDP
```

### 响应结构

| 字段 | 类型 | 必须 | 说明 |
| --- | --- | --- | --- |
| `code` | number | 是 | 第三方接口状态码，`200` 表示正常。 |
| `message` | string | 是 | 第三方接口状态信息。 |
| `data` | object[] | 否 | 指标列表，每一项的字段见下表。 |

响应的 `data` 项字段：

| 字段 | 类型 | 必须 | 说明 |
| --- | --- | --- | --- |
| `EndDate` | string | 否 | 结束日期，前端展示用。 |
| `StartDate` | string | 否 | 开始日期，前端展示用。 |
| `TableName` | string | 否 | 表名。 |
| `UpdateTime` | string | 否 | 更新时间，前端展示用。 |
| `currency` | string | 否 | 币种。 |
| `logicId` | string | 否 | 指标 ID；调用 `c.edb` 时优先使用该字段作为 `edbids`。 |
| `name` | string | 否 | 带高亮标签的指标名称。 |
| `path` | string | 否 | 路径名称。 |
| `region` | string | 否 | 地区。 |
| `singleName` | string | 否 | 指标名称。 |
| `source` | string | 否 | 发布方。 |
| `typeName` | string | 否 | 分类名称。 |
| `updateFreq` | string | 否 | 频率。 |
| `updateFrequencyCN` | string | 否 | 中文频率。 |
| `unit` | string | 否 | 单位。 |
| `baseUnit` | string | 否 | 基础单位。 |
| `magnitude` | string | 否 | 当前量级。 |
| `indicatorType` | string | 否 | 指标分类。 |

从响应的 `data` 中选择名称、地区、频率、单位等信息与用户需求相符的指标，并取得其宏观指标 ID。若返回多个相近指标且无法判断，应向用户确认；若没有匹配结果，应调整关键词后重新搜索。**不得凭经验构造指标 ID。**

完整调用顺序：

1. 从用户需求中提取指标关键词。
2. 调用 `/edb/indicator/search` 搜索指标，预计需要搜索或取得超过 50 个指标时，不要继续搜索，也不要自行截断结果；先让用户缩小地区或指标范围。
3. 从返回结果中确认目标指标并取得 `edbids`；多个指标以半角逗号连接，最多 100 个。
4. 将 `edbids` 传入 `c.edb(edbids, options)` 查询宏观数据。

---

-->

## 3. 函数结构

```text
edb(edbids, options)
```

| 参数名 | 简称 | 定义 | 描述 |
| --- | --- | --- | --- |
| `edbids` | 宏观指标 ID | 字符串 | 必须先通过 `/edb/indicator/search` 查询获得；支持多代码输入，最多不超过 100 个，以半角逗号分隔。 |
| `options` | 可选参数 | 字符串 | 附加参数，可填””；多个附加字段以半角逗号分隔，详见下方“公共参数”。 |

---

## 4. 公共参数

| 中文名称 | 英文名称 | 取值范围 | 说明 |
| --- | --- | --- | --- |
| 是否输出 pandas 格式 | `Ispandas` | `0`、`1`；SDK 缺省 `0`，**Skill 默认 `1`** | `0` = 非 pandas 格式（EmQuantData）；`1` = pandas 格式（需安装 pandas）。 |
| pandas 索引 | `RowIndex` | `1`、`2`；缺省 `0` | `1` = 宏观指标 ID；`2` = 日期。 |
| 起始日期 | `StartDate` | `YYYYMMDD`、`YYYY/MM/DD`、`YYYY/M/D`、`YYYY-MM-DD`、`YYYY-M-D` | 不传时从第一条数据开始返回；若 `EndDate` 不传，则返回至最新一条数据；若两者都不传，则输出全部数据。 |
| 截止日期 | `EndDate` | 格式同 `StartDate` | 不传时返回至最新一条数据；若 `StartDate` 和 `EndDate` 都不传，则输出全部数据。 |
| 最新一条数据 | `IsLatest` | `0`、`1`；缺省 `0` | `0` = 返回选定日期范围内的数据；`1` = 仅返回最新一条数据。 |
| 请求指标真实发布日期 | `IsPublishDate` | `0`、`1`；缺省 `0` | `0` = 不请求 `publishdate`；`1` = 请求 `publishdate`。仅部分 EDB 指标有发布日期。 |
| 超时时间设置 | `RECVtimeout` | 正整数 | 单位：秒；如 `RECVtimeout=60` 表示 60 秒超时。 |
| 调整返回日期 | `FixDate` | `0`、`1`；缺省 `0` | `0` = 按原始日期返回，不调整；`1` = 将日期调整为每个周期对应的最后一个自然日，例如年频指标返回当年的 12 月 31 日。 |

---

## 5. 命令示例

<!-- agent only
> **前置条件**：调用前需先执行 `c.start()` 登录，详见 [SKILL.md · 最小可运行示例](../../SKILL.md#最小可运行示例)。
-->

### Python 3.x

```python
import pandas as pd
from EmQuantAPI import *

login = c.start()
if login.ErrorCode != 0:
    raise RuntimeError(f"login failed: {login.ErrorCode} {login.ErrorMsg}")

df = c.edb("EMM00087117", "IsPublishDate=1,RowIndex=1,Ispandas=1")
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"edb failed: {df.ErrorCode} {df.ErrorMsg}")
print(df.to_string())

c.stop()
```

<!-- agent only

---

## 6. 相关链接

- 对比函数：[css 截面函数](./css.md) · [csd 序列函数](./csd.md)
- 回到首页：[../../SKILL.md](../../SKILL.md)
-->
