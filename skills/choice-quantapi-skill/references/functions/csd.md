# csd 序列函数

<!-- agent only
> ⛔ **对 Agent**：阅读本页前必须先完整阅读 [SKILL.md](../../SKILL.md)（文档入口，含重要约束与约定）。

> **本页默认走 `Ispandas=1` → 返回 `pandas.DataFrame`**（规则源见 [SKILL.md · 默认 Ispandas=1](../../SKILL.md)）。下面的示例、拼接教程、返回结构均按此默认值组织；如需 `EmQuantData`，把 `Ispandas=1` 从 options 去掉即可，访问范式见 §6。

-->
---

## 1. 函数类型介绍

`csd` 是 Choice 量化 API 的**时间序列函数**，用于获取股票、指数、基金、期货等证券或组合在**一段日期区间内**的指标取值。

- 与 `css` 的区别：`css` 取单一时点的横截面，`csd` 取一段时间的纵向序列。
- 与 `edb` 宏观函数的区别：`csd` 接收"证券代码"，`edb` 接收"宏观指标 ID"（如 `EMM00087117`）。

---

## 2. 函数结构

```text
csd(codes, indicators, startdate, enddate, options="", *arga, **argb)
```

| 参数 | 类型 | 必填 | 说明                                                                                     |
| --- | --- | --- |----------------------------------------------------------------------------------------|
| `codes` | 字符串或序列 | 是 | 东财证券代码，多代码以半角逗号分隔。                                                    |
| `indicators` | 字符串或序列 | 是 | 指标简称，多指标以半角逗号分隔；**单次最多不超过 64 个**。                                                      |
| `startdate` | 字符串/`datetime` | 否 | 起始日期。缺省取与 `enddate` 同一天。支持：`YYYYMMDD`、`YYYY/MM/DD`、`YYYY/M/D`、`YYYY-MM-DD`、`YYYY-M-D`。 |
| `enddate` | 字符串/`datetime` | 否 | 截止日期。缺省取今天。格式同 `startdate`。                                                            |
| `options` | 字符串 | 否 | 附加参数，`key=value` 用逗号拼接。详见下方「公共参数」。                                                     |
| `*arga` / `**argb` | - | - | 预留参数。                                                                                  |

<!-- agent only
> 证券代码如何获取：请先调用 [`sector` 板块函数](./sector.md) 取目标板块的成分代码，再传入 `csd`。

> 指标如何选取：请查阅 [csd 指标目录主索引](../indicators/csd-indicator-category-index.md)。
-->

---

## 3. 公共参数（序列函数公共参数列表）

`Ispandas` 的 **Skill 默认值** 与 SDK、官方缺省值不同：Skill 默认追加 `Ispandas=1` 以获取 DataFrame；不追加时 SDK 和官方缺省为 `0`，返回 `EmQuantData`。

| 中文名称 | 英文名称 | 取值范围 | 说明                                                                                   |
| --- | --- | --- |--------------------------------------------------------------------------------------|
| 是否输出 pandas 格式 | `Ispandas` | `0`、`1`；官方缺省 `0`，**Skill 默认 `1`** | `0` = 非 pandas 格式（EmQuantData）；`1` = pandas 格式（需安装 pandas）。                          |
| pandas 索引 | `RowIndex` | `1`、`2`，缺省 `1` | `1` = 以证券代码做索引；`2` = 以日期做索引。                                                         |
| 日期周期 | `Period` | `1`–`4`，缺省 `1` | `1` 日；`2` 周；`3` 月；`4` 年。                                                             |
| 复权方式 | `AdjustFlag` | `1`–`3`，缺省 `1` | `1` 不复权；`2` 后复权；`3` 前复权。                                                             |
| 币种 | `CurType` | `1`–`4`，缺省 `1` | `1` 原始币种；`2` 人民币；`3` 美元；`4` 港元（仅适用于港美股指标）。                                           |
| 按日期排序 | `Order` | `1`、`2`，缺省 `1` | `1` 升序；`2` 降序。                                                                       |
| 市场类型 | `Market` | 见下方市场代码表，缺省 `CNSESH` | 决定按哪个交易所的交易日历返回；<!-- agent only: [`TD` 日期宏](../help/date-macros.md) 也会按该市场交易日历计算。--> |
| 空值替换 | `ShowBlank` | 整数 | 对返回数据中的空值做特殊处理；例 `ShowBlank=0` 表示所有空值替换为 `0`。                                        |
| 沿用之前数据 | `FillData`（官方写作 `filldata`） | `0`、`1`，缺省 `0` | `0` 不沿用；`1` 沿用之前数据。                                                                  |
| 超时时间设置 | `RECVtimeout` | 正整数 | 单位：秒；如 `RECVtimeout=60` 表示 60 秒超时。                                                   |

### 市场代码表（`Market` 取值）

| 代码 | 含义 |
| --- | --- |
| `CNSESH` | 上海证券交易所 |
| `CNSESZ` | 深圳证券交易所 |
| `HKSE00` | 香港证券交易所 |
| `USSE00` | 美国证券交易所 |
| `USSEND` | 美国纳斯达克市场 |
| `USSENY` | 纽约证券交易所 |
| `CNFEBC` | 渤海商品交易所 |
| `CNFEDC` | 大连商品交易所 |
| `CNFESF` | 上海期货交易所 |
| `CNFEZC` | 郑州商品交易所 |
| `INE000` | 上海国际能源交易中心 |
| `CNGCSH` | 上海黄金交易所 |
| `HKME00` | 香港商品交易所 |
| `0` | 自然日 |
| `1` | 全部交易日 |
| `CNSH00` / `CNSHHK` | 沪股通 / 沪港股通交易日 |
| `CNSZ00` / `CNSZHK` | 深股通 / 深港股通交易日 |
| `NYMEX0` | 纽约商业期货交易所 |
| `USFENY` | 纽约商品交易所 |
| `CME000` | 芝加哥商业交易所 |
| `LDMETL` | 伦敦金属交易所 |
| `LDEXCH` | 伦敦证券交易所 |
| `SGSE00` | 新加坡交易所 |

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

df = c.csd("300059.SZ,600425.SH", "TOTALSHARE",
           "20160701", "20160706",
           "Period=1,AdjustFlag=2,Order=1,Ispandas=1")
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"csd failed: {df.ErrorCode} {df.ErrorMsg}")
print(df.to_string())

c.stop()
```

> Python 2.x：把 f-string 换成 `%` 格式化、`print(...)` 换成 `print ...` 即可，其他不变。Python 2 已于 2020-01-01 EOL，强烈建议使用 Python 3.x。

> 想要 `EmQuantData`（嵌套 dict `Data[code][i][j]`）的访问范式，见 [6. 返回结构](#6-返回结构)。

---

## 5. 命令拼接教程

`csd` 命令的拼接顺序：**证券范围 → 指标 → 时间区间 → 拼参数**。

> 以下拼接片段默认已执行 `import pandas as pd` 和 `from EmQuantAPI import *`。

### 5.1 准备证券代码

```python
# 例：取沪深 300 指数（009006195）成分（Skill 默认走 Ispandas=1）
sec_df = c.sector("009006195", "2024-12-31", "Ispandas=1")
if not isinstance(sec_df, pd.DataFrame):
    raise RuntimeError(f"sector failed: {sec_df.ErrorCode} {sec_df.ErrorMsg}")
codes = ",".join(sec_df.index.tolist())
```
<!-- agent only
> 板块代码清单与 `sector` 调用方式见 [functions/sector.md](./sector.md)。
-->

### 5.2 准备指标

<!-- agent only: 在 [csd 指标目录主索引](../indicators/csd-indicator-category-index.md) 中 -->选定指标。例如：

- `OPEN`（开盘价）、`CLOSE`（收盘价）、`HIGH`（最高价）、`LOW`（最低价）。

### 5.3 选定时间区间与公共参数

把"公共参数 + 指标特有参数"用半角逗号拼成一个字符串，**末尾默认追加 `Ispandas=1`**（Skill 默认走 DataFrame 路径）：

```text
Period=1,AdjustFlag=2,Order=1,Ispandas=1
```

含义：日线、后复权、按日期升序、返回 pandas DataFrame。用户显式要嵌套 dict 时去掉 `,Ispandas=1` 即可。

### 5.4 调用

```python
df = c.csd(codes, "OPEN,CLOSE,HIGH,LOW",
           "2024-01-01", "2024-12-31",
           "Period=1,AdjustFlag=2,Order=1,Ispandas=1")
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"csd failed: {df.ErrorCode} {df.ErrorMsg}")
```

### 5.5 用日期宏简化区间

`csd` 支持<!-- agent only: [日期宏](../help/date-macros.md) -->做相对/绝对日期计算，常用：

- `N` = 最新日期 / 今天（具体口径以接口返回为准）
- `-5TD` = 从最新日期往前 5 个交易日（`TD` = Trade Day，按 `Market` 市场日历计算）
<!-- agent only: - 完整宏列表见 [date-macros.md](../help/date-macros.md) -->

```python
# 从最新日期往前 5 个交易日至最新日期的区间
# 注意：区间函数通常包含端点；如需精确条数，先用 tradedates 验证日期列表
c.csd(codes, "CLOSE", "-5TD", "N", "Period=1,Ispandas=1")
```

<!-- agent only

### 5.6 常见踩坑

- ⚠ **指标详情页列出的特有参数均为必填**：如某个指标详情页要求 `ReportDate` / `TradeDate` / `EndDate` 等，必须显式传入；漏传时 API 可能不报错但返回 `None` / 空值。
- `Period` / `AdjustFlag` / `Order` 等是 CSD 公共参数，缺省值见 §3；为避免口径歧义，查询行情序列时仍建议显式传入。
- `indicators` 单次不超过 64 个。
- 历史数据返回为空时，确认 `startdate <= enddate`；起始日期晚于截止日期会报 `EQERR_START_BIGTHAN_END`。
- 市场类型没有想要的市场时，可以用 `Market=0`（自然日），再自行过滤。
- 频率上限 700 次/分钟。

> 与"返回类型 / `Ispandas` 行为" 相关的踩坑见 [6. 返回结构](#6-返回结构)。

---
-->

## 6. 返回结构

### SDK 默认：不加 `Ispandas=1` 返回 EmQuantData

```python
r = c.csd("000001.SZ,600036.SH", "CLOSE,VOLUME",
          "2024-12-23", "2024-12-27",
          "Period=1,AdjustFlag=2,Order=1")
```

```text
r.ErrorCode   # 0 = 成功
r.Codes       # ['000001.SZ', '600036.SH']                       按入参顺序
r.Indicators  # ['CLOSE', 'VOLUME']                              按入参顺序
r.Dates       # ['2024/12/23','2024/12/24','2024/12/25','2024/12/26','2024/12/27']
              # 格式 YYYY/MM/DD（与 css 的 YYYY-MM-DD 不同）
r.Data        # dict[code] -> [[指标0的各日值], [指标1的各日值], ...]
              # 外层按 Indicators 顺序，内层按 Dates 顺序
              # {'000001.SZ': [[1346.9, 1361.8, 1368.7, 1361.8, 1358.4],            # CLOSE × 5
              #                [165940476, 135083691, 147528294, 100007470, 129001228]],  # VOLUME × 5
              #  '600036.SH': [...]}
```

取值：`r.Data[code][r.Indicators.index(ind)][r.Dates.index(date)]`

### 加 `Ispandas=1` 返回 DataFrame

```python
df = c.csd("000001.SZ,600036.SH", "CLOSE,VOLUME",
           "2024-12-23", "2024-12-27",
           "Period=1,AdjustFlag=2,Order=1,Ispandas=1")
```

```text
              DATES        CLOSE     VOLUME
CODES                                          ← index 是 CODES（有重复！）
000001.SZ  2024/12/23   1346.90728  165940476
000001.SZ  2024/12/24  1361.834642  135083691
...
600036.SH  2024/12/27   205.460797   70031955
```

- shape = `(n_codes × n_dates, 1 + n_indicators)`，**长表**，每行一对 `(code, date)`
- index = `CODES`，**重复**（每个 code 连续 n_dates 行）
- columns = `['DATES', <指标>...]`
- `RowIndex=2` 时：index = `DATES`（重复），`CODES` 仍是普通列；适合按日期切片后再看多证券。默认建议 `RowIndex=1`，再用 `pivot(index="DATES", columns="CODES", values=...)` 转宽表。

  ```python
  # RowIndex=2 时
  df.loc["2024/12/23"]           # 该日期下所有 code 的行
  df.loc["2024/12/23", "CLOSE"]  # 该日期下所有 code 的 CLOSE（Series）
  ```
- **多数情况下指标列 dtype 都是 `object`**——只要列里出现缺失值（`None`）或字符串值（如 `'--'`），pandas 就会把整列推断成 `object`；做算术前一律先转数值（见下）。

#### 取值

```python
df.loc[code]                  # ✅ 该 code 所有日期切片（DataFrame）
df.loc[code, "CLOSE"]         # ✅ 该 code 各日的 CLOSE（Series）
df["CLOSE"]                   # ✅ 全部 code×date 的 CLOSE 列
df.at[code, "CLOSE"]          # ❌ CODES 索引重复，同一 code 对应多日期；用 .loc 或 pivot
df.iloc[i, j]                 # ❌ 一律按列名访问

# 透视为宽表（每列一只 code）
wide = df.pivot(index="DATES", columns="CODES", values="CLOSE")
```

#### 算术前转数值

```python
df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
```

### 非 DataFrame 返回场景 / 判错样板

返回 `EmQuantData`（而非 DataFrame）发生在：没传 `Ispandas=1`、或请求失败（`ErrorCode != 0`）。取数前必须先判断返回类型。

```python
df = c.csd(codes, indicators, start, end, options + ",Ispandas=1")
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"csd failed: {df.ErrorCode} {df.ErrorMsg}")
if df.empty:
    ...   # 成功但无数据
```

### 注意

- `Ispandas=1` 中 `1` 必须是字符 `"1"`，写 `true` / `True` 会被当成未开启
- 单时点截面用 `css`，不要给 csd 传相同起止日

---

<!-- agent only
## 7. 相关链接

- 上一步：[sector 板块函数](./sector.md)
- 同层：[css 截面函数](./css.md) · [cses 板块截面函数](./cses.md)
- 指标查询：[csd 指标目录主索引](../indicators/csd-indicator-category-index.md)
- 回到首页：[../../SKILL.md](../../SKILL.md)
-->