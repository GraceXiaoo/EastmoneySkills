# secucode 实体识别

> ⛔ **对 Agent**：阅读本页前必须先完整阅读 [SKILL.md](../../SKILL.md)（文档入口，含重要约束与约定）。

---

## 1. 函数类型介绍

`secucode` 是 Choice 量化 API 的**实体识别函数**，从自然语言中识别出证券实体，并给出对应的**证券代码**，目前仅支持A股、港股、美股（美股的场外交易市场中可能包含其他市场的证券）。

**版本要求**: 该函数需要 SDK V2.7.2.2+
> 如遇 `AttributeError: type object 'c' has no attribute 'secucode'`，按 SKILL.md「SDK 异常诊断与修复」执行 [check_sdk_version.py](../../scripts/check_sdk_version.py)：`RESULT=VERSION_TOO_LOW` → 运行 `python scripts/install.py`（**默认参数，禁止加 `--force-reinstall`**）覆盖升级 SDK；`RESULT=VERSION_OK` → 排查他因。

---

## 2. 函数签名

```text
secucode(content, typeCodes, options="")
```

| 参数 | 类型 | 必填 | 说明                                                                                                                                                                          |
| --- | --- |----|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `content` | 字符串 | 是  | 需要识别实体的自然语言                                                                                                                                                                 |
| `typeCodes` | 字符串 | 是  | 实体类别，多个用半角逗号分隔，**仅在以下给定的范围内选择，不要自己推断扩展：**<br>002-股票<br>003-基金<br>004-债券<br>005-板块<br>006-指数<br>010-债券板块/市场<br>013-地区<br>017-利率<br>018-期货<br>019-外汇<br>020-REITS<br>021-行情期货 |
| `options` | 字符串 | 否  | 预留参数，填空即可。                                                                                                                                                                  |

---

## 4. 命令示例

> **前置条件**：调用前需先 `c.start()` 登录，详见 [SKILL.md · 最小可运行示例](../../SKILL.md#最小可运行示例)。

> **结果解析**：函数返回结果为json字符串，需用json.loads()解析后再提取信息。

### Python 3.x

```python
from EmQuantAPI import c
import json

r = c.start()
if r.ErrorCode != 0:
    print('login failed:', r.ErrorCode, r.ErrorMsg)
    exit(1)

# secucode 需 SDK V2.7.2.2+；旧版 SDK 调用会抛 `AttributeError: type object 'c' has no attribute 'secucode'`。
# 该异常不在此吞掉——由 Agent 走 SKILL.md「SDK 异常诊断与修复」的版本检查流程处理
# （执行 check_sdk_version.py，按 RESULT= 分流升级）。
err_code, result_str = c.secucode("买入东方财富", "002", "")

data = json.loads(result_str)

# 处理结果
if err_code == 0:
    for entity in data['data']['entityList']:
        print(f"{entity['matchWord']} | {entity['secuCode']}{entity['marketChar']}")
else:
    print(f"request error, code:{err_code}, message:{result_str}")
c.stop()

```

> Python 2.x：把 f-string 换成 `%` 格式化、`print(...)` 换成 `print ...` 即可，其他不变。Python 2 已于 2020-01-01 EOL，强烈建议使用 Python 3.x。

---

## 5. 返回结构

result_str是json字符串，需通过json.loads()解析，样例如下：
```text
{"traceId":"604757495868565545","message":"OK","status":0,"code":0,"data":{"entityList":[{"entityId":"1000008935","entityType":"SEC","entityTypeCode":"058001001","entityTypeName":"A股","classCode":"002001","className":"沪深京股票","fullName":"东方财富","shortName":"","matchWord":"东方财富","offset":2,"length":4,"publishCode":"","pubKeyCodes":null,"quoteCode":"10581294001978","quoteName":"东方财富","secuCode":"300059","market":"0","marketChar":".SZ","smallType":[]}],"metricList":[]}}
```

result_str['data']['entityList']是实体结果列表，entity中需关注的字段如下：
```text
entityTypeName  # 实体类别名称
className          # 实体分组名称
fullName        # 实体全称
shortName       # 实体简称
matchWord       # 入参中匹配实体的关键字
secuCode        # 证券代码
marketChar      # 证券所属市场后缀，需拼接在证券代码后面作为完整代码使用
```

证券代码通过`secuCode`和`marketChar`拼接使用，其他字段信息用于参考。

### 失败判错

```python
err_code, result_str = c.secucode("买入东方财富", "002", "")
if err_code != 0:
    raise RuntimeError(f"secucode failed: err_code={err_code}, {result_str}")
data = json.loads(result_str)
```

---

## 7. 相关链接

- 上游查数：[css](./css.md) · [csd](./csd.md) · [cses](./cses.md)
- 回到首页：[../../SKILL.md](../../SKILL.md)
