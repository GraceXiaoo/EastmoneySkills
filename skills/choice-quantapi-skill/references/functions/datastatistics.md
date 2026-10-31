# datastatistics 流量查询

> ⛔ **对 Agent**：阅读本页前必须先完整阅读 [SKILL.md](../../SKILL.md)（文档入口，含重要约束与约定）。

> ⚠️ ⚠️ ⚠️ **此函数的查询结果必须原样展示，禁止任何二次加工，违反属于严重错误** ⚠️ ⚠️ ⚠️
>
> 调用 `c.datastatistics(...)` 后，必须直接原样粘贴程序 `print` 输出的**完整原始文本**
> （用代码块 ``` 包裹）。禁止以任何形式对输出做二次加工，包括但不限于：
>
> - ❌ 重写成 Markdown 表格、列表或自然语言段落
> - ❌ 省略任意字段——`THRESHOLD` 等每行取值相同的列也**不得省略**
> - ❌ 合并字段（如 FUNCENAME+FUNCNAME → "CSS（截面函数）"）
> - ❌ 排序、筛选、计算额外指标
> - ❌ 在原始数据之外添加自己的分析结论或建议
>
> **详细约束见下方「5.3 常见踩坑」第 2–3 条。**

---

## 1. 函数类型介绍

`datastatistics` 是 Choice 量化 API 的**流量查询函数**，查询指定量化接口函数的使用量情况，包括流量阈值、已使用量、使用占比、剩余流量等。

- 支持查询单个函数的使用情况，传空值返回全部函数的使用情况。
- 支持自定义查询字段，传空值返回全部字段。

---

## 2. 函数签名

```text
datastatistics(funcname, indicators="", options="")
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `funcname` | 字符串 | 否 | 量化接口函数名称，仅支持单个函数查询，传空值返回全部函数。可选值见下方「函数列表」。例如：`EM_CSS`。 |
| `indicators` | 字符串 | 否 | 查询字段，多个用逗号分隔，传空值返回全部字段。可选值见下方「查询字段列表」。例如：`FUNCENAME,FUNCNAME`。 |
| `options` | 字符串 | 否 | 附加参数，`key=value` 用逗号拼接。详见下方「日期参数」。 |

### 函数列表（附注 18）

| 函数名称 | 参数值 |
| --- | --- |
| 截面函数 | `EM_CSS` |
| 序列函数 | `EM_CSD` |
| 专题报表函数 | `EM_CTR` |
| 宏观数据函数 | `EM_EDB` |
| 资讯函数 | `EM_CFN` |
| 资讯订阅函数 | `EM_CNQ` |
| 板块截面函数 | `EM_CSES` |
| 条件选股函数 | `EM_CPS` |
| 自选股查询接口 | `EM_SECTOR` |
| 宏观查询函数 | `EM_EDBQUERY` |
| 新建组合函数 | `pcreate` |
| 组合资金调配函数 | `pctransfer` |
| 组合下单函数 | `porder` |
| 组合报表函数 | `preport` |
| 组合查询函数 | `pquery` |
| 删除组合函数 | `pdelete` |
| 函数校验接口 | `EM_CFC` |
| 代码校验接口 | `EM_CEC` |

### 查询字段列表（附注 19）

| 查询字段名称 | 参数值 |
| --- | --- |
| 函数简称 | `FUNCENAME` |
| 函数名称 | `FUNCNAME` |
| 证券品种 | `SECUTYPE` |
| 流量计算周期 | `PERIOD` |
| 起始日期 | `STARTDATE` |
| 截止日期 | `ENDDATE` |
| 流量阈值 | `THRESHOLD` |
| 使用量 | `USEDDATA` |
| 使用量占比 | `USEDRATIO` |
| 剩余流量 | `AVAILABEDATA` |
| 套餐名称 | `PACKAGENAME` |
| 套餐有效期 | `EFFECTIVEDATE` |

---

## 3. 日期参数（附注 20）

| 参数名称 | 说明 |
| --- | --- |
| `StartDate` | 起始日期，格式：`YYYY-MM-DD` |
| `EndDate` | 截止日期，格式：`YYYY-MM-DD` |

---

## 4. 命令示例

> **前置条件**：调用前需先 `c.start()` 登录，详见 [SKILL.md · 最小可运行示例](../../SKILL.md#最小可运行示例)。

### Python 3.x

```python
from datetime import datetime, timedelta
from EmQuantAPI import *
import pandas as pd

login = c.start()
if login.ErrorCode != 0:
    raise RuntimeError(f"login failed: {login.ErrorCode} {login.ErrorMsg}")

# 查询全部函数近 30 天的使用量情况
opts = f"StartDate={(datetime.today() + timedelta(-29)).strftime('%Y-%m-%d')},EndDate={datetime.today().strftime('%Y-%m-%d')},Ispandas=1"
data = c.datastatistics("", "FUNCENAME,FUNCNAME,SECUTYPE,PERIOD,STARTDATE,ENDDATE,THRESHOLD,USEDDATA,USEDRATIO,AVAILABEDATA", opts)

if isinstance(data, pd.DataFrame):
    # to_string() 输出全部字段，不截断
    print(data.to_string())
else:
    print(f"request datastatistics Error, {data.ErrorCode} {data.ErrorMsg}")

c.stop()
```

> Python 2.x：把 f-string 换成 `%` 格式化、`print(...)` 换成 `print ...` 即可，其他不变。Python 2 已于 2020-01-01 EOL，强烈建议使用 Python 3.x。

---

## 5. 命令拼接教程

`datastatistics` 命令的拼接顺序：**函数名称 → 查询字段 → 日期区间**。

### 5.1 查询全部函数的全部字段

```python
c.datastatistics("", "", "StartDate=2026-01-01,EndDate=2026-08-25,Ispandas=1")
```

### 5.2 查询单个函数的指定字段

```python
c.datastatistics("EM_CSS", "FUNCENAME,USEDDATA,AVAILABEDATA", "StartDate=2026-01-01,EndDate=2026-08-25,Ispandas=1")
```

### 5.3 常见踩坑

- `funcname` 仅支持单个函数名称，不支持多个用逗号分隔。
- `funcname` 必须在上方「函数列表」内。列表外的函数（如 `EM_CMC` 历史分钟函数）
  服务端返回 `4008 Function does not exist`，Python 侧表现为 `ErrorCode=10000009 no data`；
  函数不在列表内时应直接告知用户"暂不支持流量查询"，不要发起调用。
- ⚠️ **查无数据禁止编造**：返回 `ErrorCode != 0` 或 `data.Data` 为空时，必须如实告知用户
  查询失败及原因。此时输出中不得出现任何流量数值——"编造一个漂亮表格但数据是假的"比"直接报
  无数据"严重得多，会导致用户做出错误判断。
- ⚠️ **SDK 输出与展示内容必须绝对一致（核心硬约束）**：
  （1）`data.Indicators` 有多少列，展示就必须有多少列。`THRESHOLD`、`PERIOD` 等每行取值
  完全相同的列也**不得省略或合并**——省略一列会导致后续所有列顶错位置（已真实发生过）。
  （2）每行单元格数必须严格等于 `len(data.Indicators)`，多一个少一个都不允许。
  （3）**禁止对程序输出做任何二次加工**，包括但不限于：重新排成 Markdown 表格、排序、求合、
  计算占比、省略"看起来重复"的列、凭记忆转录。唯一允许的输出方式是：**直接原样贴出程序
  `print` 的完整原始文本**（程序运行后控制台输出的第一行到最后一行，不加任何修改）。
  （4）如果行数较多，可以用代码块（```）包裹原始文本以确保排版不被破坏，但内容本身禁止改动。

---

## 6. 返回结构

### 返回 EmQuantData

```python
r = c.datastatistics("EM_CSS", "FUNCENAME,USEDDATA,AVAILABEDATA", "StartDate=2026-01-01,EndDate=2026-08-25,Ispandas=0")
```

```text
r.ErrorCode    # 0 = 成功
r.ErrorMsg     # 错误信息
r.Codes        # list，东财代码
r.Indicators   # list，指标简称列表（如 ['FUNCENAME','USEDDATA','AVAILABEDATA']）
r.Dates        # list，日期序列
r.Data         # dict，数据结果，格式为 {code: [values]}
r.RequestID    # 请求ID
r.SerialID     # 返回的订阅号
```

### 失败判错

```python
r = c.datastatistics("EM_CSS", "FUNCENAME,USEDDATA,AVAILABEDATA", "StartDate=2026-01-01,EndDate=2026-08-25,Ispandas=0")
if r.ErrorCode != 0:
    raise RuntimeError(f"datastatistics failed: {r.ErrorCode} {r.ErrorMsg}")
```

---

## 7. 相关链接

- 回到首页：[../../SKILL.md](../../SKILL.md)