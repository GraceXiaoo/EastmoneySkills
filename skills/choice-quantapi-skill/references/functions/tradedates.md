# tradedates 交易日历

> ⛔ **对 Agent**：阅读本页前必须先完整阅读 [SKILL.md](../../SKILL.md)（文档入口，含重要约束与约定）。

---

## 1. 函数类型介绍

`tradedates` 是 Choice 量化 API 的**交易日历函数**，获取指定交易市场、指定时间区间内的**日期序列**（按交易日周期返回）。

- 与 [`getdate` 交易日偏移](./getdate.md) 的区别：`tradedates` 取一段时间内的全部交易日；`getdate` 是从某一天往前/往后偏移 N 天。
- 与 [`tradedatesnum` 区间交易日数](./tradedatesnum.md) 的区别：本函数返回**日期列表**；`tradedatesnum` 返回**数量**。

> 注意：不建议使用未来交易日（接口可能返回不准确的预测交易日）。

---

## 2. 函数签名

```text
tradedates(startdate, enddate, options=None, *arga, **argb)
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `startdate` | 字符串/`datetime` | 否 | 起始日期。缺省取与 `enddate` 同一天。支持：`YYYYMMDD`、`YYYY/MM/DD`、`YYYY/M/D`、`YYYY-MM-DD`、`YYYY-M-D`。 |
| `enddate` | 字符串/`datetime` | 否 | 截止日期。缺省取今天。格式同 `startdate`。 |
| `options` | 字符串 | 否 | 附加参数，`key=value` 用逗号拼接。详见下方「公共参数」。 |
| `*arga` / `**argb` | - | - | 预留参数。 |

---

## 3. 公共参数（附注 14：交易日函数可选参数列表）

| 中文名称 | 英文名称 | 取值范围 | 说明 |
| --- | --- | --- | --- |
| 日期周期 | `Period` | `1`–`5`，缺省 `1` | `1` 日 / `2` 周 / `3` 月 / `4` 年 / `5` 季。注意：与 `csd` 的 `Period` 取值不同（csd 无「季」），`5`=季为本函数特有。 |
| 按日期排序 | `Order` | `1` / `2`，缺省 `1` | `1` 升序 / `2` 降序。 |
| 市场类型 | `Market` | 见下方市场代码表，缺省 `CNSESH` | 决定按哪个交易所的交易日历返回。 |
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

data = c.tradedates("2016-07-01", "2016-07-12")
if data.ErrorCode != 0:
    print("request tradedates Error, ", data.ErrorMsg)
else:
    print("tradedate输出结果======分隔线======")
    for item in data.Data:
        print(item)

c.stop()
```

> Python 2.x：把 f-string 换成 `%` 格式化、`print(...)` 换成 `print ...` 即可，其他不变。Python 2 已于 2020-01-01 EOL，强烈建议使用 Python 3.x。

---

## 5. 命令拼接教程

`tradedates` 命令的拼接顺序：**时间区间 → 市场类型 → 周期/排序**。

### 5.1 取上交所一段区间的全部日线交易日

```python
c.tradedates("2024-01-01", "2024-12-31", "Market=CNSESH,Period=1,Order=1")
```

### 5.2 取美股纳斯达克月度交易日

```python
c.tradedates("2024-01-01", "2024-12-31", "Market=USSEND,Period=3,Order=1")
```

### 5.3 取沪深 300 季末交易日（按上交所日历）

```python
c.tradedates("2023-01-01", "2024-12-31", "Market=CNSESH,Period=5")
```

### 5.4 常见踩坑

- 起始日期晚于截止日期会报 `EQERR_START_BIGTHAN_END`。
- 截止日期超过当前最新交易日时，未来部分不可信，建议显式裁剪。
- 不同市场的交易日历不同，跨境业务记得切换 `Market`。
- ℹ️ `tradedates` **不受 `Ispandas` 影响**，传 `Ispandas=1` 也仍然返回 `EmQuantData`（其 `.Data` 是日期字符串列表）。详见下文「[6. 返回结构](#6-返回结构)」。

---

## 6. 返回结构

### 返回 EmQuantData（无 Ispandas 支持）

```python
r = c.tradedates("2024-12-20", "2024-12-31", "Market=CNSESH")
```

```text
r.ErrorCode   # 0 = 成功
r.Codes       # ['']                  通常单元素空字符串，不使用
r.Indicators  # ['TRADEDATE']         单字段（实测为 TRADEDATE）
r.Dates       # ['2024/12/20','2024/12/23','2024/12/24','2024/12/25',
              #  '2024/12/26','2024/12/27','2024/12/30','2024/12/31']
              # 格式 YYYY/MM/DD
r.Data        # list（不是 dict！）
              # 实测内容与 r.Dates 一致
              # ['2024/12/20','2024/12/23',...,'2024/12/31']
```

实测 `r.Dates` 与 `r.Data` 内容一致，优先读 `r.Dates`。

### 不支持 `Ispandas=1`

`tradedates` 不走 `__tryResolvePandas`，加 `Ispandas=1` 也仍返回 `EmQuantData`（实测验证）。要 DataFrame 自己包：

```python
import pandas as pd
df = pd.DataFrame({"TRADEDATE": pd.to_datetime(r.Dates)})
```

### 失败判错

```python
r = c.tradedates(start, end, "Market=CNSESH")
if r.ErrorCode != 0:
    raise RuntimeError(f"tradedates failed: {r.ErrorCode} {r.ErrorMsg}")
```

### 注意

- 日期格式 `YYYY/MM/DD`，月日**不补零**（如可能为 `'2025/1/8'`）
- `enddate` 缺省 → 今天；`startdate` 缺省 → 同 `enddate`（即"取那一天"，**不是取到今天的区间**）
- 仅需个数用 `tradedatesnum` 更高效

---

## 7. 相关链接

- 同组：[getdate 交易日偏移](./getdate.md) · [tradedatesnum 区间交易日数](./tradedatesnum.md)
- 上游查数：[css](./css.md) · [csd](./csd.md) · [cses](./cses.md) · [ctr](./ctr.md)
- 回到首页：[../../SKILL.md](../../SKILL.md)
