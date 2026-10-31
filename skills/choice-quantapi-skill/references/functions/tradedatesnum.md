# tradedatesnum 区间交易日数

> ⛔ **对 Agent**：阅读本页前必须先完整阅读 [SKILL.md](../../SKILL.md)（文档入口，含重要约束与约定）。

---

## 1. 函数类型介绍

`tradedatesnum` 是 Choice 量化 API 的**区间交易日数函数**，获取指定交易市场在指定时间区间内的**交易日个数**。

- 与 [`tradedates` 交易日历](./tradedates.md) 的区别：本函数返回**数量**；`tradedates` 返回**日期列表**。
- 与 [`getdate` 交易日偏移](./getdate.md) 的区别：本函数计算"区间内有几个交易日"；`getdate` 是"从某日偏移 N 个交易日是哪一天"。

---

## 2. 函数签名

```text
tradedatesnum(startdate, enddate, options="")
```

> 与其他函数页不同，本函数**没有 `*arga/**argb` 预留参数**（SDK 真实签名如此，与 `ctr` 一样）。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `startdate` | 字符串/`datetime` | 否 | 起始日期。缺省取今天。支持：`YYYYMMDD`、`YYYY/MM/DD`、`YYYY/M/D`、`YYYY-MM-DD`、`YYYY-M-D`。 |
| `enddate` | 字符串/`datetime` | 否 | 截止日期。缺省取今天。格式同 `startdate`。 |
| `options` | 字符串 | 否 | 附加参数，见下方「公共参数」（与 [getdate](./getdate.md) 共用附注 15）。 |

---

## 3. 公共参数

| 中文名称 | 英文名称 | 取值范围 | 说明 |
| --- | --- | --- | --- |
| 市场类型 | `Market` | 见下方市场代码表，缺省 `CNSESH` | 决定按哪个交易所的交易日历计数。 |
| 超时时间设置 | `RECVtimeout` | 正整数 | 单位：秒。 |

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

> **前置条件**：调用前需先 `c.start()` 登录，详见 [SKILL.md · 最小可运行示例](../../SKILL.md#最小可运行示例)。

### Python 3.x

```python
from EmQuantAPI import *

login = c.start()
if login.ErrorCode != 0:
    raise RuntimeError(f"login failed: {login.ErrorCode} {login.ErrorMsg}")

data = c.tradedatesnum("2018-01-01", "2018-09-15")
if data.ErrorCode != 0:
    print("request tradedatesnum Error, ", data.ErrorMsg)
else:
    print("tradedatesnum======分割线======")
    print(data.Data)

c.stop()
```

> Python 2.x：把 f-string 换成 `%` 格式化、`print(...)` 换成 `print ...` 即可，其他不变。Python 2 已于 2020-01-01 EOL，强烈建议使用 Python 3.x。

---

## 5. 命令拼接教程

`tradedatesnum` 命令的拼接顺序：**时间区间 → 市场类型**。

### 5.1 计算一个季度的交易日个数

```python
c.tradedatesnum("2024-01-01", "2024-03-31", "Market=CNSESH")
```

### 5.2 计算最近一年的交易日个数（搭配 `getdate`）

> 日期宏完整说明见 [date-macros.md](../help/date-macros.md)。

```python
# "N" 是 Choice 日期宏：今天/最新交易日（详见 ../help/date-macros.md）
end = c.getdate("N", 0, "Market=CNSESH").Data[0]
start = c.getdate(end, -250, "Market=CNSESH").Data[0]
c.tradedatesnum(start, end, "Market=CNSESH")
```

### 5.3 跨市场对比（同一区间在不同市场的交易日个数）

```python
opts_a = "Market=CNSESH"   # 上交所
opts_b = "Market=USSEND"   # 纳斯达克
print(c.tradedatesnum("2024-01-01", "2024-12-31", opts_a).Data)
print(c.tradedatesnum("2024-01-01", "2024-12-31", opts_b).Data)
```

### 5.4 常见踩坑

- ⚠ **失败时 `r.Data` 不是 `0`，而是 `__init__` 默认值 `dict()`**——直接当 int 用会 `TypeError`。**必须先判 `ErrorCode != 0`**（判错样板见 [6. 返回结构](#6-返回结构)）。
- 起始日期晚于截止日期会报 `EQERR_START_BIGTHAN_END`。
- 起止日**含端点**，请按是否包含端点的语义自行 ±1。
- 不同市场的休市日不同，跨境业务务必传 `Market`。
- ℹ️ `tradedatesnum` **不受 `Ispandas` 影响**，传 `Ispandas=1` 也仍然返回 `EmQuantData`。详见下文「[6. 返回结构](#6-返回结构)」。

---

## 6. 返回结构

### 返回 EmQuantData（无 Ispandas 支持）

```python
r = c.tradedatesnum("2024-12-01", "2024-12-31", "Market=CNSESH")
```

```text
r.ErrorCode   # 0 = 成功
r.Codes       # []
r.Indicators  # []
r.Dates       # []
r.Data        # int（不是 list 不是 dict！）   ← 唯一一个 Data 不是容器的函数
              # 22
```

直接读：`n = r.Data`

### 失败判错（必须先判错）

```python
r = c.tradedatesnum(start, end, "Market=CNSESH")
if r.ErrorCode != 0:
    raise RuntimeError(f"tradedatesnum failed: {r.ErrorCode} {r.ErrorMsg}")
n = r.Data   # 此时才能安全当 int 用（失败时 .Data 不是 int，详见 §5.4 踩坑）
```

### 注意

- 不支持 `Ispandas=1`（也没意义——返回值是单个整数）
- 仅取个数；要日期列表用 `tradedates`

---

## 7. 相关链接

- 同组：[tradedates 交易日历](./tradedates.md) · [getdate 交易日偏移](./getdate.md)
- 上游查数：[css](./css.md) · [csd](./csd.md) · [cses](./cses.md) · [ctr](./ctr.md)
- 回到首页：[../../SKILL.md](../../SKILL.md)
