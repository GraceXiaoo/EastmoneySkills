# getdate 交易日偏移（偏移 N 天交易日）

> ⛔ **对 Agent**：阅读本页前必须先完整阅读 [SKILL.md](../../SKILL.md)（文档入口，含重要约束与约定）。

---

## 1. 函数类型介绍

`getdate` 是 Choice 量化 API 的**交易日偏移函数**，从指定日期沿指定市场的交易日历**向前或向后推算第 N 个交易日**。

- 与 [`tradedates` 交易日历](./tradedates.md) 的区别：`tradedates` 列出一段区间的全部交易日；`getdate` 只算"前 N 个 / 后 N 个"。
- 与 [`tradedatesnum`](./tradedatesnum.md) 的区别：`getdate` 返回日期；`tradedatesnum` 返回区间内交易日个数。

---

## 2. 函数签名

```text
getdate(tradedate, offday=0, options="", *arga, **argb)
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tradedate` | 字符串/`datetime` | 是 | 基准日期。支持：`YYYYMMDD`、`YYYY/MM/DD`、`YYYY/M/D`、`YYYY-MM-DD`、`YYYY-M-D`。 |
| `offday` | 数字 | 否 | 偏移天数。`N=0` 返回当天；`N>0` 向后取最近第 N 个交易日；`N<0` 向前取最近第 N 个交易日；若基准日期为最新交易日且 `N>0`，则返回最新交易日。 |
| `options` | 字符串 | 否 | 附加参数，见下方「公共参数」。 |
| `*arga` / `**argb` | - | - | 预留参数。 |

---

## 3. 公共参数（附注 15：偏移 N 天函数可选参数列表）

| 中文名称 | 英文名称 | 取值范围 | 说明 |
| --- | --- | --- | --- |
| 市场类型 | `Market` | 见下方市场代码表，缺省 `CNSESH` | 决定按哪个交易所的交易日历推算。 |
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

data = c.getdate("20160426", -3, "Market=CNSESH")
if data.ErrorCode != 0:
    print("request getdate Error, ", data.ErrorMsg)
else:
    print(data.Data)

c.stop()
```

> Python 2.x：把 f-string 换成 `%` 格式化、`print(...)` 换成 `print ...` 即可，其他不变。Python 2 已于 2020-01-01 EOL，强烈建议使用 Python 3.x。

---

## 5. 命令拼接教程

`getdate` 命令的拼接顺序：**基准日 → 偏移量（正/负/零） → 市场类型**。

### 5.1 取基准日往前 5 个交易日（上交所）

```python
c.getdate("2024-12-31", -5, "Market=CNSESH")
```

### 5.2 取基准日往后 1 个交易日（深交所）

```python
c.getdate("2024-12-31", 1, "Market=CNSESZ")
```

### 5.3 取基准日当天（验证该日是否为交易日）

```python
c.getdate("2024-12-31", 0, "Market=CNSESH")
```

### 5.4 配合 `csd` 自动算"近 N 个交易日"

> 日期宏完整说明见 [date-macros.md](../help/date-macros.md)。

```python
# "N" 是 Choice 日期宏，等价于"今天/最新交易日"（详见 ../help/date-macros.md）
end = c.getdate("N", 0, "Market=CNSESH").Data[0]   # 最新交易日
start = c.getdate(end, -19, "Market=CNSESH").Data[0]  # 往前 20 个交易日
c.csd("300059.SZ", "CLOSE", start, end, "Period=1,AdjustFlag=2,Ispandas=1")
```

> 也可以直接在 csd 的 `startdate` 里使用日期宏 `-20TD`，效果一致。

### 5.5 常见踩坑

- `offday=0` 时返回基准日**当天**；若该日不是交易日，返回值可能为空或邻近交易日，按场景核实。
- `offday` 必须是整数；浮点会被截断或报错。
- 跨市场场景下要切换 `Market`，否则可能用了错的日历。
- ℹ️ `getdate` **不受 `Ispandas` 影响**，传 `Ispandas=1` 也仍然返回 `EmQuantData`。详见下文「[6. 返回结构](#6-返回结构)」。

---

## 6. 返回结构

### 返回 EmQuantData（无 Ispandas 支持）

```python
r = c.getdate("2024-12-31", -5, "Market=CNSESH")
```

```text
r.ErrorCode   # 0 = 成功
r.Codes       # ['']                 通常单元素空字符串，不使用
r.Indicators  # ['DATE']             单字段（实测为 DATE）
r.Dates       # ['2024/12/24']       长度恒为 1，是偏移后的结果日期
r.Data        # list（不是 dict！）  长度恒为 1
              # ['2024/12/24']       内容 == r.Dates
```

直接读：`date_str = r.Data[0]`（或 `r.Dates[0]`，内容相同）

### 不支持 `Ispandas=1`

`getdate` 不走 `__tryResolvePandas`，加 `Ispandas=1` 也仍返回 `EmQuantData`。结果就一个日期，不需要 DataFrame。

### 失败判错

```python
r = c.getdate(base_date, offday, "Market=CNSESH")
if r.ErrorCode != 0:
    raise RuntimeError(f"getdate failed: {r.ErrorCode} {r.ErrorMsg}")
date_str = r.Data[0]
```

### 注意

- `offday` 是**交易日数**，不是自然日数（正向后偏移，负向前偏移）
- 日期格式 `YYYY/MM/DD`，月日**不补零**（如 `'2025/1/8'`）——字符串比较前建议 `pd.to_datetime()`

---

## 7. 相关链接

- 同组：[tradedates 交易日历](./tradedates.md) · [tradedatesnum 区间交易日数](./tradedatesnum.md)
- 上游查数：[css](./css.md) · [csd](./csd.md) · [cses](./cses.md) · [ctr](./ctr.md)
- 回到首页：[../../SKILL.md](../../SKILL.md)
