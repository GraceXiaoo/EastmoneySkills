# cses 板块截面函数
<!-- agent only
> ⛔ **对 Agent**：阅读本页前必须先完整阅读 [SKILL.md](../../SKILL.md)（文档入口，含重要约束与约定）。

> **本页默认走 `Ispandas=1` → 返回 `pandas.DataFrame`**（规则源见 [SKILL.md · 默认 Ispandas=1](../../SKILL.md)）。下面的示例、拼接教程、返回结构均按此默认值组织；如需 `EmQuantData`，把 `Ispandas=1` 从 options 去掉即可，访问范式见 §6。


---
-->

> **特殊限制**：cses 板块截面函数仅支持**沪深京股票**和**养老保障**两大类板块。其他板块不支持。
>
> **限制**：不支持多线程调用。

---

## 1. 函数类型介绍

`cses` 是 Choice 量化 API 的**板块截面函数**，用于在**板块维度**计算的截面数据（如板块平均估值、平均现金流等），而不是在单个证券维度。

- 适用板块限制见上方提示。
- 与 `css` 的区别：`css` 传入证券代码，返回每只证券的指标；`cses` 传入板块代码（以 `B_` 开头），返回该板块整体的指标（通常是聚合值）。

---

## 2. 函数结构

```text
cses(blockcodes, indicators, options="", *arga, **argb)
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `blockcodes` | 字符串或序列 | 是 | 东财板块代码，以 `B_` 开头，如 `"B_018005001001"`；多代码以半角逗号分隔，**最多不超过 6 个**。 |
| `indicators` | 字符串或序列 | 是 | 指标简称，多指标以半角逗号分隔，**最多不超过 15 个**。 |
| `options` | 字符串 | 业务必填 | SDK 形参可空，但 cses 业务上必须包含 `IsHistory`；其他参数见下方「公共参数」和指标详情页。 |
| `*arga` / `**argb` | - | - | 预留参数。 |

<!-- agent only
> 板块代码如何获取：请通过 [`sector` 板块函数](./sector.md) 或 Choice 量化接口官网「命令生成」获取板块代码（沪深京股票板块代码可在 sector 函数页查询）。

> 指标如何选取：请查阅 [cses 指标目录主索引](../indicators/cses-indicator-category-index.md)。
-->

---

## 3. 公共参数（附注 8：板块截面函数可选参数列表）

| 中文名称 | 英文名称 | 取值范围 | 说明 |
| --- | --- | --- | --- |
| 是否取最新板块成分 | `IsHistory`（官方写作 `isHistory`） | `0`、`1`，必传 | `0` = 最新；`1` = 历史（注意不是布尔语义）。 |
| 是否输出 pandas 格式 | `Ispandas` | `0`、`1`；SDK 缺省 `0`，**Skill 默认 `1`** | `0` = 非 pandas 格式（EmQuantData）；`1` = pandas 格式（需安装 pandas）。 |
| pandas 索引 | `RowIndex` | `1`、`2`，缺省 `1` | `1` = 证券代码做索引；`2` = 日期做索引。`RowIndex=2` 时 index = `DATES`，`CODES` 仍是普通列；但 cses 的 `Dates` 恒为长度 1（API 处理日期），通常所有板块行都会落到同一个日期索引上，所以几乎无意义。 |
| 空值替换 | `ShowBlank` | 整数 | 例 `ShowBlank=0` 把空值替换为 `0`。 |
| 超时时间设置 | `RECVtimeout` | 正整数 | 单位：秒。 |

<!-- agent only
此外，指标特有参数（如 `PREDICTYEAR`、`StartDate`、`EndDate`、`Payyear`、`ReportDate`、`TradeDate`、`type`、`DelType`、`DataAdjustType` 等）需查阅 [cses 指标目录主索引](../indicators/cses-indicator-category-index.md) 的对应详情页。
-->
---

## 4. 命令示例
<!-- agent only
> **前置条件**：调用前需先 `c.start()` 登录，详见 [SKILL.md · 最小可运行示例](../../SKILL.md#最小可运行示例)。
-->

### Python 3.x

```python
import pandas as pd
from EmQuantAPI import *

login = c.start()
if login.ErrorCode != 0:
    raise RuntimeError(f"login failed: {login.ErrorCode} {login.ErrorMsg}")

df = c.cses(
    "B_001004",
    "CLOSEAVG,CLOSETSWAVG",
    "IsHistory=0,TradeDate=20241231,Ispandas=1"
)
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"cses failed: {df.ErrorCode} {df.ErrorMsg}")
print(df.to_string())

c.stop()
```

> 示例指标参数以对应指标详情页为准；若执行返回空值，先核对 `CLOSEAVG` / `CLOSETSWAVG` 详情页是否还需其他参数。

> Python 2.x：把 f-string 换成 `%` 格式化、`print(...)` 换成 `print ...` 即可，其他不变。Python 2 已于 2020-01-01 EOL，强烈建议使用 Python 3.x。

<!-- agent only
> 想要 `EmQuantData`（`Data[blockcode][i]`）的访问范式，见 [6. 返回结构](#6-返回结构)。
-->

---

## 5. 命令拼接教程

`cses` 命令的拼接顺序：**先确认板块属于沪深京股票或养老保障 → 取板块代码 → 选板块维度指标 → 拼参数**。

### 5.1 确认板块属于允许的两大类

可调用 `cses` 的板块必须属于：

- 沪深京股票板块（如 `B_001004`、`B_001005`、`B_018005001001` 等；板块代码通常以 `B_` 开头，但并非所有 `B_` 板块都支持 cses）
- 养老保障板块

其他板块（如海外指数、债券板块等）需改用其他函数。

### 5.2 取板块代码

板块代码可通过：
<!-- agent only
- [functions/sector.md](./sector.md) 中的「板块清单」段落查询；
-->
- Choice 官网「命令生成 → 板块成分」工具拷贝。

### 5.3 选板块维度指标

<!-- agent only: 打开 [cses 指标目录主索引](../indicators/cses-indicator-category-index.md)，复制目标指标的英文简称与其特有参数说明。-->例如：

- `SECTOPREAVG`（板块平均预测 PE）
- `CFOPSAVG`（板块平均每股经营现金流）

### 5.4 拼接 options

`cses` 必传 `IsHistory`，并在末尾默认追加 `Ispandas=1`（Skill 默认走 DataFrame 路径）：

```text
IsHistory=0,TradeDate=20241231,Ispandas=1
```

若指标详情页要求 `DelType`、`type`、`DataAdjustType`、`PREDICTYEAR`、`Payyear`、`ReportDate` 等额外参数，则按详情页逐项追加；不要照抄无关参数。用户显式要嵌套 dict 时去掉 `,Ispandas=1` 即可。

### 5.5 常见踩坑

- ⚠ `IsHistory` 是 cses 公共必传参数，必须显式写在 `options` 中。
- ⚠ **指标详情页列出的特有参数均为必填**：如某个指标要求 `TradeDate` / `ReportDate` / `Payyear` 等，必须显式传入；漏传时 API 可能不报错但返回 `None` / 空值。
- 指标必须从 cses 专属清单选（如 `CLOSEAVG` / `PEALL` / `TURNAVG`），传 css 指标会 `[10003010] invalid indicator`。
- 板块代码必须以 `B_` 开头；纯数字板块代码（用于 `sector` 函数）不能直接传给 `cses`。
- `blockcodes` 最多 6 个、`indicators` 最多 15 个，超限会报参数错误。

<!-- agent only
> 与"返回类型 / `Ispandas` 行为" 相关的踩坑见 [6. 返回结构](#6-返回结构)。
-->
---

## 6. 返回结构

### SDK 默认：不加 `Ispandas=1` 返回 EmQuantData

```python
r = c.cses("B_001004", "CLOSEAVG,CLOSETSWAVG",
           "TradeDate=20241231,IsHistory=0")
```

```text
r.ErrorCode   # 0 = 成功
r.Codes       # ['B_001004']            板块代码（前缀 B_），按入参顺序
r.Indicators  # ['CLOSEAVG', 'CLOSETSWAVG']
r.Dates       # ['YYYY-MM-DD']          长度恒为 1；为 API 处理日期，不必等于 TradeDate
r.Data        # dict[block_code] -> [指标0值, 指标1值, ...]，顺序与 Indicators 一致
              # {'B_001004': [19.897079, 11.556513]}
```

取值：`r.Data[block_code][r.Indicators.index(name)]`

### 加 `Ispandas=1` 返回 DataFrame

```python
df = c.cses("B_001004", "CLOSEAVG,CLOSETSWAVG",
            "TradeDate=20241231,IsHistory=0,Ispandas=1")
```

```text
              DATES   CLOSEAVG CLOSETSWAVG
CODES                                       ← index 名仍是 CODES，但内容是板块代码
B_001004  YYYY-MM-DD  19.897079   11.556513
```

- index = `CODES`（板块代码），columns = `['DATES', <指标>...]`
- `RowIndex=2` 时：index = `DATES`，`CODES` 仍是普通列；由于 cses 的 `Dates` 通常只有一个 API 处理日期，多个板块会共享同一个日期索引，默认不推荐。
- SDK 的 DataFrame 构造方式通常会让指标列保持 `object`；无论实际 dtype 如何，做算术前一律先转数值（见下）。

#### 取值

```python
df.at[block_code, indicator]     # ✅ RowIndex=1 且 block_code 唯一时为标量
df[indicator]                    # ✅ 整列 Series
df.iloc[i, j]                    # ❌ 一律按列名访问
```

#### 算术前转数值

```python
df["CLOSEAVG"] = pd.to_numeric(df["CLOSEAVG"], errors="coerce")
```

### 非 DataFrame 返回场景 / 判错样板

返回 `EmQuantData`（而非 DataFrame）发生在：没传 `Ispandas=1`、或请求失败（`ErrorCode != 0`）。取数前必须先判断返回类型。

```python
df = c.cses(block_codes, indicators, options + ",Ispandas=1")
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"cses failed: {df.ErrorCode} {df.ErrorMsg}")
if df.empty:
    ...
```

### 注意

- `Ispandas=1` 中 `1` 必须是字符 `"1"`，写 `true` / `True` 会被当成未开启

<!-- agent only

---

## 7. 相关链接

- 取板块代码：[sector 板块函数](./sector.md)
- 同层：[css 截面函数](./css.md) · [csd 序列函数](./csd.md)
- 指标查询：[cses 指标目录主索引](../indicators/cses-indicator-category-index.md)
- 回到首页：[../../SKILL.md](../../SKILL.md)
-->