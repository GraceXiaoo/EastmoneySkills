# ctr 专题报表函数

<!-- agent only
> ⛔ **对 Agent**：阅读本页前必须先完整阅读 [SKILL.md](../../SKILL.md)（文档入口，含重要约束与约定）。

> **Skill 调用默认建议走 `Ispandas=1` → 返回 `pandas.DataFrame`**（规则源见 [SKILL.md · 默认 Ispandas=1](../../SKILL.md)）；SDK 自身默认返回 `EmQuantData`。如需 `EmQuantData`，把 `Ispandas=1` 从 options 去掉即可，访问范式见 §6。


---
-->

> `ctr` 用于获取一整张「专题报表」（如 IPO 信息、新股一览、解禁明细等）。报表是一张二维表，列为字段、行为记录；不像 `css`/`csd` 那样按"证券 × 指标"组织。

---

## 1. 函数类型介绍

`ctr` 是 Choice 量化 API 的**专题报表函数**。

- 与 `css` 区别：`css` 输入「证券代码 + 指标」，按证券维度返回；`ctr` 输入「报表名 + 字段」，按报表维度返回。
- 报表名通过 `ctrName` 指定（如 `StockInfo`、`RptNewShareIssue`）；
- 报表字段通过 `indicators` 指定（传空 / 匹配不到时返回报表全部字段）。

---

## 2. 函数结构

```text
ctr(ctrName, indicators="", options="")
```

| 参数 | 类型 | 必填 | 说明                                                                                                                           |
| --- | --- | --- |------------------------------------------------------------------------------------------------------------------------------|
| `ctrName` | 字符串 | 是 | 东财报表名称；<!-- agent only: 完整枚举以[ctr 报表目录主索引](../indicators/ctr-indicator-category-index.md) 和 Choice 量化接口官网「命令生成 → 专题报表」为准。--> |
| `indicators` | 字符串或序列 | 否 | 报表字段简称，多字段以半角逗号分隔；**传空或匹配不到时展示报表全部字段**。                                                                                      |
| `options` | 字符串 | 否 | 报表参数 + 公共参数，`key=value` 用逗号拼接。                                                                                               |

---

## 3. 公共参数（附注 4：专题报表函数可选参数列表）

| 中文名称 | 英文名称 | 取值范围 | 说明 |
| --- | --- | --- | --- |
| 是否输出 pandas 格式 | `Ispandas` | `0` / `1`，**Skill 默认 `1`**（DataFrame，**且不能放 options 首位**），SDK 缺省 `0`（EmQuantData） | `1` = pandas 格式（需安装 pandas）。 |
| 超时时间设置 | `RECVtimeout` | 正整数 | 单位：秒。 |
| 编码类型 | `ENCODE` | `UTF-8` / `GBK` / `GB2312`，默认空（自动判断） | 部分文字无法自动判断编码时，手动指定。 |

报表特有参数（如 `StartDate`、`EndDate`、`SecuCode`、`ReportDate` 等）依报表而异，详见各报表详情页。

<!-- agent only:
> ⚠️ `ctr` 特有：`Ispandas=1` 不能放在 options 首位（SDK 判断与判错细节见 [6. 返回结构](#6-返回结构)）。
-->
---

## 4. 命令示例

<!-- agent only:
> **前置条件**：调用前需先 `c.start()` 登录，详见 [SKILL.md · 最小可运行示例](../../SKILL.md#最小可运行示例)。
-->

### Python 3.x

```python
import pandas as pd
from EmQuantAPI import *

login = c.start()
if login.ErrorCode != 0:
    raise RuntimeError(f"login failed: {login.ErrorCode} {login.ErrorMsg}")

df = c.ctr("StockInfo", "",
           "StartDate=2024-12-30,EndDate=2024-12-31,Ispandas=1")
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"ctr failed: {df.ErrorCode} {df.ErrorMsg}")
print(df.to_string())

c.stop()
```

> Python 2.x：把 f-string 换成 `%` 格式化、`print(...)` 换成 `print ...` 即可，其他不变。Python 2 已于 2020-01-01 EOL，强烈建议使用 Python 3.x。

> `StartDate` / `EndDate` 的含义由报表决定；换报表时必须查看该报表详情页，不要直接复用本示例参数。

<!-- agent only:
> 想要 `EmQuantData`（`Data["0"/"1"/...]`）的访问范式、以及 `Ispandas=1` 首位 bug 详情，见 [6. 返回结构](#6-返回结构)。
-->
---

## 5. 命令拼接教程

`ctr` 命令的拼接顺序：**先选报表 → 再选字段 → 再拼报表参数**。

### 5.1 选报表

<!-- agent only: 打开 [ctr 报表目录主索引](../indicators/ctr-indicator-category-index.md)，-->按业务分类找到目标报表，并进入对应报表详情页。

报表详情页中会给出：

- `ctrName`：传给 `c.ctr()` 的报表名称；
- 字段简称：传给 `indicators`；
- 参数说明：拼接到 `options`。

### 5.2 选字段

在报表详情页查看字段清单，复制需要的字段简称，多个字段用半角逗号拼接。

如果不确定字段，`indicators` 可先传空字符串 `""` 拉取全部字段，再根据返回结果筛选。

### 5.3 拼接 options

把报表参数拼成一个字符串，**末尾默认追加 `Ispandas=1`**（Skill 默认走 DataFrame 路径）：

```text
StartDate=2024-01-01,EndDate=2024-12-31,Ispandas=1
```

`StartDate` / `EndDate` 等参数是否必传、含义如何，看报表详情页对应说明。用户显式要 EmQuantData 时去掉 `,Ispandas=1` 即可。如果报表没有其他业务参数，先放 `RECVtimeout=60`，再追加 `,Ispandas=1`（避免 `Ispandas=1` 落到首位，详见 §6）。

### 5.4 常见踩坑

- 不同报表的"日期参数"含义不同（公告披露日、报告期、生效日……），不要凭直觉对齐。
- 报表参数缺失通常不报错，但会返回空。先用 `indicators=""` 确认报表能拉出数据。
- 中文字段乱码 → 显式传 `ENCODE=UTF-8` 或 `GBK` 试试。

<!-- agent only:
> `Ispandas=1` 首位 bug 与完整判错样板见 [6. 返回结构](#6-返回结构)。
-->
---

## 6. 返回结构

`indicators` 留空 = 返回报表全部字段。

### SDK 默认：不加 `Ispandas=1` 返回 EmQuantData

```python
r = c.ctr("StockInfo", "", "StartDate=2024-12-30,EndDate=2024-12-31")
```

```text
r.ErrorCode   # 0 = 成功
r.Codes       # []                       ← 始终为空，ctr 不使用 Codes 维度
r.Indicators  # ['SECURITYCODE', 'SECURITYSHORTNAME', 'TDATE', ...]   ← 报表字段名
r.Dates       # []                       ← 始终为空
r.Data        # dict[str(row_idx)] -> [字段0值, 字段1值, ...]
              # key 是字符串行号 "0","1",...；value 长度 = len(Indicators)
              # {'0': ['002868.SZ', '科恒股份', '2024-12-30', ...],
              #  '1': ['600590.SH', '泰豪科技', '2024-12-30', ...], ...}
```

取值：`r.Data[str(row_idx)][r.Indicators.index(field)]`

### 加 `Ispandas=1` 返回 DataFrame

```python
df = c.ctr("StockInfo", "", "StartDate=2024-12-30,EndDate=2024-12-31,Ispandas=1")
```

```text
  SECURITYCODE SECURITYSHORTNAME       TDATE  ...
0    002868.SZ              科恒股份  2024-12-30  ...
1    600590.SH              泰豪科技  2024-12-30  ...
...
```

- shape = `(n_rows, n_fields)`
- index = 报表行号（SDK 原始 key 是字符串 `"0"`、`"1"`、...；实际使用时建议先 `print(df.index)` 确认）
- columns = 报表字段名（顺序 = `Indicators`）
- SDK 的 DataFrame 构造方式通常会让字段列保持 `object`；无论实际 dtype 如何，做算术前一律先转数值（见下）。
- 如果触发 DataFrame 路径但环境未安装 pandas，SDK 会在 `import pandas` 处抛异常，而不是返回 `EmQuantData`。

#### 取值 & 重设业务索引

```python
print(df.columns)                                # 先确认当前报表实际返回字段
df.iloc[0]["SECURITYCODE"]                      # ✅ 用位置查看首行字段（以 StockInfo 为例）。仅允许按行位置取首行样例，但字段取值必须使用列名。
df["SECURITYCODE"]                              # ✅ 整列
df = df.set_index("SECURITYCODE")               # 若当前报表存在证券代码字段，可转为按证券代码访问
df.loc["002868.SZ", "SECURITYSHORTNAME"]        # 转索引后按业务键
```

#### 算术前转数值

```python
df["TURNOVER"] = pd.to_numeric(df["TURNOVER"], errors="coerce")
```

### ⚠️ `Ispandas=1` 必须是 options 中的非首位精确片段

这是 `ctr` 函数的 SDK 实现差异：`ctr` 通过 `options.upper().find("ISPANDAS=1") > 0` 判断是否返回 DataFrame（**严格大于 0**），因此 `Ispandas=1` 必须出现在 options 的非首位。`css` / `csd` / `cses` / `sector` 不走这段逻辑。为避免误判，使用时应把 `Ispandas=1` 作为独立逗号分隔参数放在末尾；成功且命中该判断 → DataFrame，否则返回 EmQuantData。

```python
# ❌ 失败：Ispandas=1 在首位 → 返回 EmQuantData
c.ctr("StockInfo", "", "Ispandas=1,StartDate=2024-12-30,EndDate=2024-12-31")

# ✅ 成功：Ispandas=1 在其他参数之后
c.ctr("StockInfo", "", "StartDate=2024-12-30,EndDate=2024-12-31,Ispandas=1")
```

**始终把 `Ispandas=1` 放在 options 字符串末尾**。

### 非 DataFrame 返回场景 / 判错样板

返回 `EmQuantData`（而非 DataFrame）发生在以下任一情况：没传 `Ispandas=1`、`Ispandas=1` 在 options 首位、拼写不匹配、或请求失败（`ErrorCode != 0`）。因此取数前**必须先判断返回类型**。

```python
options = options.strip(",")
options = f"{options},Ispandas=1" if options else "RECVtimeout=60,Ispandas=1"

df = c.ctr(ctrName, indicators, options)
if not isinstance(df, pd.DataFrame):
    raise RuntimeError(f"ctr failed: {df.ErrorCode} {df.ErrorMsg}")
if df.empty:
    ...
```

### 注意

- `Codes` 和 `Dates` 始终为空 list，**别拿来取数**
- DataFrame 默认 index 是字符串行号；若当前报表存在证券代码等业务字段，可 `set_index(...)` 后再按业务键访问（字段因报表而异，先看 `df.columns`，`SECURITYCODE` 只是 `StockInfo` 的示例字段）
- `Ispandas=1` 中 `1` 必须是字符 `"1"`，写 `true` / `True` 会被当成未开启

<!-- agent only:

---

## 7. 相关链接

- 报表索引：[ctr 报表目录主索引](../indicators/ctr-indicator-category-index.md)
- 报表详情：`indicators/ctr/*.md`（经上方主索引浏览或通过文件搜索）
- 同层：[css 截面函数](./css.md) · [csd 序列函数](./csd.md) · [cses 板块截面函数](./cses.md) · [sector 板块函数](./sector.md)
- 回到首页：[../../SKILL.md](../../SKILL.md)
-->