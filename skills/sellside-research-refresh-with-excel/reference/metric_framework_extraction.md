# 原始底稿指标框架提取规范

## 1. 输入

唯一入口为阶段 0 的 `stage-0-handoff.json`。提取前必须验证：

1. handoff 状态为 `CONFIRMED`。
2. producer 为 `research-report-review`，版本为三段式版本号。
3. Excel 底稿和面向投研用户的评测报告均存在，文件大小和 SHA-256 与 handoff 一致。
4. Excel 至少包含 `00_导读`、`10_研报快照`、`20_研报底稿`、`30_预测框架`、`90_执行日志`。

任何检查失败都必须显式报错，不生成空的 `metric_framework.json`。

## 2. 数据源优先级

| 来源 | 用途 |
|---|---|
| `10_研报快照` | 确定纳入表、图、图表回读块和全部非空指标行，是覆盖全集 |
| `20_研报底稿` | 确定来源级 MQL 锚点、成功/阻塞状态、映射说明和 EDB 扩展入口 |
| `21_EDB_NNN` | 确定 EDB 时序锚点、映射状态、说明和公式存在性 |
| `30_预测框架` | 补充盈利驱动、目标价、估值、市场预期及假设 |
| `90_执行日志` | 逐指标补充成功、失败、无法映射、不适用、指标路径、期间、单位和原因 |

不能仅根据 `20_研报底稿` 的成功锚点建立清单。快照中的指标即使查询失败、无法映射或不适用，也必须保留。

## 3. 状态归一化

输出指标状态固定为：

- `SUCCESS`：存在逐指标成功日志，或来源有成功 MQL/EDB 锚点且没有更具体的失败证据。
- `FAILED`：实际执行失败、底稿来源阻塞或日志记录执行错误。
- `UNMAPPED`：无成功映射，或日志为 `NO_MATCH`、无候选、无法映射。
- `NOT_APPLICABLE`：日志、状态或映射说明明确为不适用。

逐指标日志优先于来源级锚点状态。来源级成功只能作为对象级证据，`status_scope` 必须标记为 `OBJECT`；逐指标匹配时标记为 `METRIC`。没有任何映射证据的快照指标为 `UNMAPPED`，不得推测成功。

## 4. 输出

`metric_framework.json` 至少包含：

- 源 handoff、工作簿路径、哈希及 Sheet 清单。
- `objects`：每个纳入表、图、图表数据块和预测区段。
- `metrics`：每个非空指标行或图表序列一条记录。
- `workpapers` 和 `execution_log` 的结构化摘要。
- 按状态、对象类型和来源 Sheet 统计的 coverage。
- completeness 结果。

机器可读字段约束见 [metric_framework.schema.json](metric_framework.schema.json)。

提取器同时生成 `stage-1-handoff.json`，状态为
`CONFIRMED`。阶段 C 可直接读取其中的 `metric_framework.json`。

每条 metric 至少包含：

- `framework_id`、`object_id`、`object_type`、`object_title`。
- `metric_name`、`periods`、`frequency`、`actual_forecast`、`unit`。
- `source_location`、`status`、`status_scope`、`status_evidence`。
- `indicator_path`、`mapping_note`。

`framework_extracted.md` 只汇总提取结果、状态和缺口，不把原始研报结论改写为新标的结论。

## 5. 完整性门禁

1. `10_研报快照` 中每个识别出的纳入对象必须进入 `objects`。
2. 每个数据表或图表回读块的非空首列指标行必须进入 `metrics`。
3. 图表元数据中的非空序列必须进入 `metrics`。
4. `30_预测框架` 的非空项目必须进入 `metrics`。
5. `21_EDB_NNN` 必须在对应对象的 workpaper 证据中出现。
6. 指标失败只改变状态，不能删除记录。

门禁失败时抛出错误并列出缺失来源位置。
