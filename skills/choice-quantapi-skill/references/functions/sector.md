# sector 板块函数

> ⛔ **对 Agent**：阅读本页前必须先完整阅读 [SKILL.md](../../SKILL.md)（文档入口，含重要约束与约定）。

> **Skill 调用默认建议走 `Ispandas=1` → 返回 `pandas.DataFrame`**（规则源见 [SKILL.md · 默认 Ispandas=1](../../SKILL.md)）；SDK 自身默认返回 `EmQuantData`（扁平 list）。如需 `EmQuantData`，把 `Ispandas=1` 从 options 去掉即可，访问范式见 §7。


---

> **典型用法**：当你只知道板块、不知道成分代码时，先用 `sector` 取板块成分代码，再喂给 `css`/`csd`/`cses`。如果已有证券代码，可直接调用查询函数，无需 `sector`。

> **注意**：`sector`仅用于获取板块的成分列表，不可用于获取板块名称，名称需使用`cses`查询。

---

## 1. 函数类型介绍

`sector` 取 Choice 金融终端指定**系统板块**的证券代码成分列表。

- 历史成分：目前只支持沪深股票、上交所期权的历史成分查询；
- 其他板块：只能取最新成分。

---

## 2. 函数签名

```text
sector(pukeycode, tradedate, options="", *arga, **argb)
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `pukeycode` | 字符串 | 是 | 板块代码。可在 Choice 量化接口官网「命令生成 → 板块成分」获取；常用代码见下方「板块清单」。selfblock 查询时传空串 `""`。 |
| `tradedate` | 字符串/`datetime` | 是 | 板块成分快照日期。支持：`YYYYMMDD`、`YYYY/MM/DD`、`YYYY/M/D`、`YYYY-MM-DD`、`YYYY-M-D`。省略/传 None 时默认取当天；selfblock 查询时传空串 `""`。 |
| `options` | 字符串 | 否 | 附加参数，见下方「公共参数」。 |
| `*arga` / `**argb` | - | - | 预留参数。 |

---

## 3. 公共参数（附注 13：板块函数可选参数列表）

| 中文名称 | 英文名称 | 取值范围 | 说明 |
| --- | --- | --- | --- |
| 自选股板块查询 | `selfblock` | `1` | `selfblock=1` 取本账号最新的全部自选股板块代码与名称，调用方式：`sector("", "", "selfblock=1,Ispandas=1")`，板块代码与日期均传空。 |
| 是否输出 pandas 格式 | `Ispandas` | `0` / `1`，**Skill 默认 `1`**（DataFrame），SDK 缺省 `0`（EmQuantData，扁平 list） | `1` = pandas 格式（需安装 pandas）。 |
| pandas 索引 | `RowIndex` | `1` / `2`，缺省 `1` | `1` 证券代码 / `2` 日期。**对 sector 几乎无意义**——`Dates` 恒为长度 1（即 `tradedate`），`RowIndex=2` 会让所有成分行落到同一个日期索引上。 |
| 超时时间设置 | `RECVtimeout` | 正整数 | 单位：秒。 |

---

## 4. 命令示例

> **前置条件**：调用前需先 `c.start()` 登录，详见 [SKILL.md · 最小可运行示例](../../SKILL.md#最小可运行示例)。

### Python 3.x

```python
import pandas as pd
from EmQuantAPI import *

login = c.start()
if login.ErrorCode != 0:
    raise RuntimeError(f"login failed: {login.ErrorCode} {login.ErrorMsg}")

df = c.sector("001004", "2016-04-26", "Ispandas=1")
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"sector failed: {df.ErrorCode} {df.ErrorMsg}")
print(df.to_string())

c.stop()
```

> Python 2.x：把 f-string 换成 `%` 格式化、`print(...)` 换成 `print ...` 即可，其他不变。Python 2 已于 2020-01-01 EOL，强烈建议使用 Python 3.x。

> `df.index.tolist()` 即可拿到成分证券代码列表，直接 `",".join(...)` 喂给 css/csd/cses。

> 想要 `EmQuantData`（扁平 `Data = [code, name, code, name, ...]`）的访问范式，见 [7. 返回结构](#7-返回结构)。

---

## 5. 命令拼接教程

`sector` 命令的拼接顺序：**确认板块代码 → 选定截止日 → 拼参数**。

### 5.1 选板块代码

在下方「板块清单」复制目标板块代码。比如「沪深 A 股」是 `001004`，「沪深 300 成份」是 `009006195`。

### 5.2 选截止日

```python
c.sector("001004", "2024-12-31", "Ispandas=1")    # Skill 默认带 Ispandas=1
```

### 5.3 自选股快捷取法

```python
c.sector("", "", "selfblock=1,Ispandas=1")
```

### 5.4 拿到代码后传给查询函数

```python
sec_df = c.sector("009006195", "2024-12-31", "Ispandas=1")   # 沪深 300 成份
if not isinstance(sec_df, pd.DataFrame):
    raise RuntimeError(f"sector failed: {sec_df.ErrorCode} {sec_df.ErrorMsg}")
codes = ",".join(sec_df.index.tolist())
c.css(codes, "TOTALSHARE", "EndDate=20241231,Ispandas=1")
```

> ⚠ 默认带 `Ispandas=1` 时用 `sec_df.index.tolist()` 取代码；不带 `Ispandas=1` 时退回 EmQuantData，优先用 `r.Codes`（已是成分代码列表，详见 [7. 返回结构](#7-返回结构)）。

---

## 6. 板块清单（附注 9：常见板块代码）

> 完整板块清单以 Choice 官网「命令生成 → 板块成分」为准；以下为常用板块。

### 6.1 全市场板块

| 板块代码 | 板块名称                 |
| --- |----------------------|
| `001004` | 沪深 A 股               |
| `001005` | 上证 A 股               |
| `001006` | 深证 A 股               |
| `001011` | 全部 B 股               |
| `001012` | 上证 B 股               |
| `001013` | 深证 B 股               |
| `001008` | 深证主板                 |
| `001007` | 深证主板 A 股             |
| `001033` | 深证主板 B 股             |
| `001031` | 深证主板 A 股（含 ST, ST\*） |
| `001009` | 中小板                  |
| `001032` | 中小板（含 ST, ST\*）      |
| `001010` | 创业板                  |
| `001044` | 全部 A 股（非金融石油石化）      |

### 6.2 风险与状态板块

| 板块代码 | 板块名称 |
| --- | --- |
| `001017` | ST |
| `001018` | \*ST |
| `001023` | 风险警示股票 |
| `001024` | 风险警示股票（上交所） |
| `001025` | 风险警示股票（深交所） |
| `001019` | 正在发行的股票 |
| `001020` | 已发行待上市股票 |

### 6.3 互联互通板块

| 板块代码 | 板块名称 |
| --- | --- |
| `001038` | 沪股通 |
| `001041` | 深股通 |
| `001047` | 沪深股通 |

### 6.4 标的池

| 板块代码 | 板块名称 |
| --- | --- |
| `001045` | 融资融券标的 |
| `001046` | 可转债标的 |

### 6.5 指数成份

| 板块代码 | 板块名称 |
| --- | --- |
| `009007063` | 上证 50 指数成份 |
| `009007060` | 上证 180 指数成份 |
| `009006195` | 沪深 300 成份 |
| `009006062` | 中证 500 成份 |
| `009007552` | 中证 1000 成份 |
| `009007104` | 上证综合指数成份 |
| `009007251` | 深证综合指数成份 |
| `009007124` | 中小板指成份 |
| `009007125` | 中小板综成份 |
| `009007144` | 创业板指成份 |
| `009007145` | 创业板综成份 |

### 6.6 概念/主题板块

| 板块代码 | 板块名称 |
| --- | --- |
| `007230` | MSCI 中国（概念类） |
| `007053` | 预亏预减 |
| `007054` | 预盈预增 |

> 调用 `sector` 时，部分代码（如 `001004`）可直接用；而 `cses` 板块截面函数则要在前面加 `B_` 前缀，如 `B_001004`。

---

## 7. 返回结构

### SDK 默认：不加 `Ispandas=1` 返回 EmQuantData

```python
r = c.sector("001004", "2024-12-31")        # 001004 = 沪深 A 股
```

```text
r.ErrorCode   # 0 = 成功
r.Codes       # ['000001.SZ', '000002.SZ', ...]    板块全部成分代码
r.Indicators  # ['SECUCODE', 'SECURITYSHORTNAME']  通常两列：代码 + 简称
r.Dates       # ['2024-12-31']                     长度恒为 1
r.Data        # list（不是 dict！）                扁平，长度 = n_codes × n_indicators
              # 顺序：code0_secucode, code0_name, code1_secucode, code1_name, ...
              # ['000001.SZ', '平安银行', '000002.SZ', '万科A', '000004.SZ', '*ST国华', ...]
```

取值：`r.Data[code_index * len(r.Indicators) + r.Indicators.index(name)]`

获取成分代码列表的最简写法：`codes = ",".join(r.Codes)`

### 加 `Ispandas=1` 返回 DataFrame

```python
df = c.sector("001004", "2024-12-31", "Ispandas=1")
```

```text
              DATES   SECUCODE SECURITYSHORTNAME
CODES                                            ← index 是 CODES
000001.SZ  2024-12-31  000001.SZ              平安银行
000002.SZ  2024-12-31  000002.SZ               万科A
...
```

- shape = `(n_codes, 3)`
- index = `CODES`（证券代码）
- columns = `['DATES', 'SECUCODE', 'SECURITYSHORTNAME']`
- `SECUCODE` 列与 index 完全重复（信息冗余）
- DataFrame 已按 `CODES` 排序，顺序可能与扁平 `r.Data` 的原始顺序不一致；不要把 `df` 的行序和 `r.Data` 的下标混用。
- **多数情况下列 dtype 都是 `object`**——只要列里出现缺失值（`None`），pandas 就会把整列推断成 `object`。
- 如果触发 DataFrame 路径但环境未安装 pandas，SDK 会在 `import pandas` 处抛异常，而不是返回 `EmQuantData`。

#### 取值

```python
df.at[code, "SECURITYSHORTNAME"]    # ✅ 标量
df.index.tolist()                   # ✅ 所有成分代码
df.iloc[i, j]                       # ❌ 一律按列名访问
```

### 非 DataFrame 返回场景 / 判错样板

返回 `EmQuantData`（而非 DataFrame）发生在：没传 `Ispandas=1`、或请求失败（`ErrorCode != 0`）。取数前必须先判断返回类型。

```python
df = c.sector(pukeycode, tradedate, "Ispandas=1")
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"sector failed: {df.ErrorCode} {df.ErrorMsg}")
```

### 注意

- 原始 `r.Data` 是**扁平 list 不是 dict**——和 css/csd/cses 不同，注意访问公式
- `r.Codes` 已经是成分代码列表，可直接 `",".join(r.Codes)` 喂给 css/csd
- 历史日期的板块成分可能与今日不同（指数调样、退市）——`tradedate` 决定成分快照
- `Ispandas=1` 中 `1` 必须是字符 `"1"`，写 `true` / `True` 会被当成未开启

---

## 8. 相关链接

- 上游用法：所有查询函数都需要先取板块成分代码 → [css](./css.md) / [csd](./csd.md) / [cses](./cses.md)
- 资讯板块查询：见 `cfnquery()`（资讯函数和资讯订阅函数支持的板块），不同于本函数返回的"系统板块成分"
- 板块导航：[sector 指标目录主索引](../indicators/sector-indicator-category-index.md)
- 回到首页：[../../SKILL.md](../../SKILL.md)
