# css 截面函数
<!-- agent only
> ⛔ **对 Agent**：阅读本页前必须先完整阅读 [SKILL.md](../../SKILL.md)（文档入口，含重要约束与约定）。

> **本页默认走 `Ispandas=1` → 返回 `pandas.DataFrame`**（规则源见 [SKILL.md · 默认 Ispandas=1](../../SKILL.md)）。下面的示例、拼接教程、返回结构均按此默认值组织；如需 `EmQuantData`，把 `Ispandas=1` 从 options 去掉即可，访问范式见 §6。
-->

---

## 1. 函数类型介绍

`css` 是 Choice 量化 API 的**截面函数**，用于获取**同一时间点（截面）上**多个证券、多个指标的取值。

- 适用证券品种：股票、指数、基金、期货等单证券或组合。
- 与序列函数 `csd` 的区别：`css` 只取一个时点的横截面，`csd` 取一段时间区间的纵向序列。
- 与板块截面 `cses` 的区别：`css` 接收"证券代码"维度，`cses` 接收"板块代码"维度。

---

## 2. 函数结构

```text
css(codes, indicators, options="", *arga, **argb)
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `codes` | 字符串或序列 | 是 | 东财证券代码，**不支持跨品种证券混合输入**。 |
| `indicators` | 字符串或序列 | 是 | 指标简称，多指标以半角逗号分隔；**单次最多不超过 64 个**。 |
| `options` | 字符串 | 否 | 附加参数，`key=value` 用逗号拼接。详见下方「公共参数」与「指标特有参数」。 |
| `*arga` / `**argb` | - | - | 预留参数，正常使用无需关心。 |

<!-- agent only
> 证券代码如何获取：请先调用 [`sector` 板块函数](./sector.md) 取目标板块的成分代码，再传入 `css`。

> 指标如何选取：请查阅 [css 指标目录主索引](../indicators/css-indicator-category-index.md)，按"目录 → 指标"路径定位；指标特有参数（如 `ReportDate`、`PayYear` 等）在各目录详情页给出。
-->

---

## 3. 公共参数（附注 2：截面函数可选参数列表）

| 中文名称 | 英文名称 | 取值范围 | 说明 |
| --- | --- | --- | --- |
| 是否输出 pandas 格式 | `Ispandas` | `0`、`1`；SDK 缺省 `0`，**Skill 默认 `1`** | `0` = 非 pandas 格式（EmQuantData）；`1` = pandas 格式（需安装 pandas）。 |
| pandas 索引 | `RowIndex` | `1`、`2`，缺省 `1` | `1` = 以证券代码做索引；`2` = 以日期做索引。`RowIndex=2` 时 index = `DATES`，`CODES` 仍是普通列；但 css 的 `Dates` 恒为长度 1，通常所有行都会落到同一个日期索引上，所以几乎无意义。 |
| 空值替换 | `ShowBlank` | 整数 | 对返回数据中的空值做替换，如 `ShowBlank=0` 把所有空值替换为 `0`。 |
| 超时时间设置 | `RECVtimeout` | 正整数 | 单位：秒；如 `RECVtimeout=60` 表示 60 秒超时。 |

此外，**绝大多数指标会附带"指标特有参数"**（如截止日期 `EndDate`、报告期 `ReportDate`、复权方式 `AdjustFlag` 等），这些参数在对应的指标目录详情页里给出。

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

df = c.css("300059.SZ", "TOTALSHARE", "EndDate=20190819,Ispandas=1")
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"css failed: {df.ErrorCode} {df.ErrorMsg}")
print(df.to_string())

c.stop()
```

> Python 2.x：把 f-string 换成 `%` 格式化、`print(...)` 换成 `print ...` 即可，其他不变。Python 2 已于 2020-01-01 EOL，强烈建议使用 Python 3.x。

<!-- agent only
> 想要 `EmQuantData`（嵌套 dict）的访问范式 / 完整字段说明，见 [6. 返回结构](#6-返回结构)。
-->
---

## 5. 命令拼接教程

`css` 命令的拼接顺序：**先定证券范围 → 再定指标 → 再拼参数**。

> 以下拼接片段默认已执行 `import pandas as pd` 和 `from EmQuantAPI import *`。

### 5.1 准备证券代码

```python
# 用 sector 函数取"全部 A 股"成分（板块代码 001004；Skill 默认走 Ispandas=1）
sec_df = c.sector("001004", "2024-12-31", "Ispandas=1")
if not isinstance(sec_df, pd.DataFrame):
    raise RuntimeError(f"sector failed: {sec_df.ErrorCode} {sec_df.ErrorMsg}")
codes = ",".join(sec_df.index.tolist())
```

<!-- agent only
> 板块代码清单与 `sector` 调用方式见 [functions/sector.md](./sector.md)。
-->

### 5.2 准备指标与指标特有参数

<!-- agent only: 打开 [css 指标目录主索引](../indicators/css-indicator-category-index.md)，-->找到<!-- agent only:所需的"目录详情页"，复制-->目标指标的英文简称与其特有参数说明。例如<!-- agent only: 某目录给出-->：

- 指标：`TOTALSHARE`（总股本）
- 特有参数：`EndDate=YYYYMMDD`

### 5.3 拼接 options

把"公共参数 + 指标特有参数"用半角逗号拼成一个字符串，**末尾默认追加 `Ispandas=1`**（Skill 默认走 DataFrame 路径）：

```text
EndDate=20240630,Ispandas=1
```
<!-- agent only
> 用户显式要嵌套 dict 时去掉 `,Ispandas=1` 即可，返回结构变化见 [6. 返回结构](#6-返回结构)。
> -->

### 5.4 调用

```python
df = c.css(codes, "TOTALSHARE,TOTALA", "EndDate=20240630,Ispandas=1")
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"css failed: {df.ErrorCode} {df.ErrorMsg}")
```

### 5.5 常见踩坑

- ⚠ **指标特有参数均为必填**：指标详情页「参数说明」表中列出的参数（`codes` 除外）必须显式传入 `options`，**漏传不报错但值为 `None`**。例如某些财务 / 持仓 / 行情口径指标会要求 `ReportDate` / `EndDate` / `TradeDate` 等，具体以指标详情页「参数说明」为准。
- `indicators` 单次不超过 64 个，否则报 `The number of WaitHandles must be less than or equal to 64`。
- 同一次 `css` 调用不能混合"跨品种证券"（例如同时传股票和期货代码）。
- `RECVtimeout` 不要设得过短，单次大批量查询建议 ≥ 60 秒。
- 频率上限 700 次/分钟，集中调用前自行限流。

<!-- agent only
> 与"返回类型 / `Ispandas` 行为" 相关的踩坑见 [6. 返回结构](#6-返回结构)。
-->
---

## 6. 返回结构

### SDK 默认：不加 `Ispandas=1` 返回 EmQuantData

```python
r = c.css("000001.SZ,600036.SH", "TOTALSHARE,CLOSE",
          "TradeDate=20241231,EndDate=20241231")
```

```text
r.ErrorCode   # 0 = 成功
r.Codes       # ['000001.SZ', '600036.SH']
r.Indicators  # ['TOTALSHARE', 'CLOSE']
r.Dates       # ['2024-12-31']        长度恒为 1
r.Data        # dict[code] -> [指标0值, 指标1值, ...]，顺序与 Indicators 一致
              # {'000001.SZ': [19405918198, 11.7],
              #  '600036.SH': [25219845601, 39.3]}
```

取值：`r.Data[code][r.Indicators.index(name)]`

### 加 `Ispandas=1` 返回 DataFrame

```python
df = c.css("000001.SZ,600036.SH", "TOTALSHARE,CLOSE",
           "TradeDate=20241231,EndDate=20241231,Ispandas=1")
```

```text
              DATES   TOTALSHARE CLOSE
CODES                                  ← index 是 CODES（证券代码）
000001.SZ  2024-12-31  19405918198  11.7
600036.SH  2024-12-31  25219845601  39.3
```

- index = `CODES`，columns = `['DATES', <指标>...]`
- `RowIndex=2` 时：index = `DATES`，`CODES` 仍是普通列；但 css 的 `Dates` 通常只有 1 个值，多个证券会共享同一个日期索引，因此默认不推荐。
- SDK 的 DataFrame 构造方式通常会让指标列保持 `object`；无论实际 dtype 如何，做算术前一律先转数值（见下）。

#### 取值

```python
df.at[code, indicator]      # ✅ 标量
df[indicator]               # ✅ 整列 Series
df.iloc[i, j]               # ❌ 禁止，一律按列名访问
```

#### 算术前先转数值

```python
df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
```

### 非 DataFrame 返回场景 / 判错样板

**不能用 `df.ErrorCode != 0` 判错**（成功时 df 是 DataFrame，没这个属性）。返回 `EmQuantData`（而非 DataFrame）发生在：没传 `Ispandas=1`、或请求失败（`ErrorCode != 0`）。

```python
df = c.css(codes, indicators, options + ",Ispandas=1")
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"css failed: {df.ErrorCode} {df.ErrorMsg}")
if df.empty:
    ...   # 成功但无数据
```

### 注意

- `Ispandas=1` 中 `1` 必须是字符 `"1"`，写 `true` / `True` 会被当成未开启
- 多时点序列用 `csd`，不要循环 css

<!-- agent only

---

## 7. 相关链接

- 上一步：[sector 板块函数](./sector.md)（拿证券代码）
- 同层：[csd 序列函数](./csd.md) · [cses 板块截面函数](./cses.md)
- 指标查询：[css 指标目录主索引](../indicators/css-indicator-category-index.md)
- 回到首页：[../../SKILL.md](../../SKILL.md)
-->