# 逐接口执行审计规范

## 目的

审计矩阵把“逐接口执行”从文本要求变成可检验的流程条件。每个计划接口只有一条记录；每次元数据检索、入参判定和实际执行后立即更新，禁止任务结束时凭记忆补录。

## 状态

- `待发现`：尚未完成元数据发现。
- `元数据未发现`：定向检索和允许的补检均未找到可用元数据，属于终态。
- `入参缺失`：元数据已确认，但条件接口没有提供必需入参，属于终态。
- `前置条件不满足`：接口规定的业务前置条件不成立，属于终态。
- `待执行`：元数据已发现、入参齐备、前置条件成立，必须实际执行。
- `执行成功且有数据`：实际调用成功且返回行数大于0，属于终态。
- `执行成功但为空`：实际调用成功且返回0行，属于终态。
- `执行失败`：发生了实际调用，但在规定重试范围内未成功，属于终态。

只有后三个执行终态计为“实际执行”。检索到元数据不计为执行；其他接口的多 Block 覆盖相同数据也不计为该接口执行。

## 合法转换

```text
待发现 -> 元数据未发现
待发现 -> 入参缺失
待发现 -> 前置条件不满足
待发现 -> 待执行
待执行 -> 执行成功且有数据
待执行 -> 执行成功但为空
待执行 -> 执行失败
```

终态不可覆盖。若记录有误，保留原审计文件并重新初始化新文件，不得直接篡改历史。

## 覆盖率

应执行接口是同时满足以下三项的接口：

1. `metadata_found=true`
2. `inputs_ready=true`
3. `prerequisite_met=true`

实际执行接口必须处于三个执行终态之一，且 `attempt_count >= 1`。

```text
执行覆盖率 = 实际执行接口数 / 应执行接口数 × 100%
```

写作前覆盖率必须为100%，并且不得存在`待发现`、`待执行`或“应执行但未执行”的接口。

## 主要字段

- `order`：计划顺序。
- `interface`：接口标识。
- `chapter`：所属章节；条件接口单列为“条件接口”。
- `state`：当前状态。
- `metadata_found`：是否确认完整报表路径、过滤列和返回字段。
- `report_path`：当次元数据确认的完整报表路径。
- `inputs_ready`：必需入参是否齐备。
- `prerequisite_met`：业务前置条件是否成立。
- `attempt_count`：该接口实际执行次数，不含元数据检索。
- `row_count`：成功执行后的返回行数。
- `execution_id`：可用时记录执行标识。
- `error_code`：失败时记录原始错误类别。
- `reason`：未发现、缺参、前置不成立或失败的简明原因。
- `history`：带时间戳的不可省略状态变化记录。

## 命令示例

```text
python scripts/etf_one_page.py audit-init work/condition.json work/audit.json
python scripts/etf_one_page.py audit-update work/audit.json RPT_F9_POFD_INFO --state 待执行 --metadata-found --report-path "完整报表路径" --inputs-ready true --prerequisite-met true
python scripts/etf_one_page.py audit-update work/audit.json RPT_F9_POFD_INFO --state 执行成功且有数据 --attempts 1 --row-count 1 --execution-id "执行标识"
python scripts/etf_one_page.py audit-checkpoint work/audit.json --chapter "基金概况"
python scripts/etf_one_page.py audit-finalize work/audit.json
```
