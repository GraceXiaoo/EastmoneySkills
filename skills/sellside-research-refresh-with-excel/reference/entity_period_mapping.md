# 阶段 C：实体、期间和资讯适配规范

## 1. 目标

把阶段 1 的指标框架（来自原始研报底稿）适配到**用户指定的目标实体和目标期间**，产出取数计划。本阶段只做"目标是什么、要查哪些指标、用什么期间"，不做真实取数（真实取数与重放校验在阶段 D）。

实现入口为 `scripts/adapt_target_framework.py`。机器可读字段约束见 [target_adaptation.schema.json](target_adaptation.schema.json)。

## 2. 输入

- 阶段 1 已确认的 `stage-1-handoff.json`（必须 `stage==1` 且 `status==CONFIRMED`，且含 `metric_framework.json`）。
- 用户的适配请求：目标主标的、可比公司、行业/板块、指数/基准、宏观对象、目标期间、资讯主体与截止范围。

## 3. 实体角色与动作

框架中的每个来源实体都必须映射到目标实体并赋予角色与动作：

| 角色 | 说明 |
|---|---|
| 主标的（target_primary） | 用户指定的唯一核心对象，是 B 底稿与新研报的主角 |
| 可比公司 | 与主标的对比的同行，跨市场时按市场分段 |
| 行业/板块 | 主标的所属或对照的行业板块 |
| 指数/基准 | 相对比较的指数或基准 |
| 宏观对象 | 宏观经济指标主体 |
| 外部事件主体 | 资讯与事件引用的机构/主体 |

每个实体映射必须声明 `action`：保留（preserve）、替换（adapt/replace）或省略（omit）。无法唯一判定时必须登记 `blocker` 并将阶段置为 `BLOCKED`，等待用户决定，**不得猜测**。

## 4. 期间语义

来源期间到目标期间的映射必须显式记录语义，禁止静默换期：

- 粒度：年度 / 季度 / 月 / 周 / 日。
- 形态：单期 / 累计；同比 / 环比；实际 / 预测。
- 交易日语义：涉及行情、收益率、区间涨跌幅时必须使用交易日，不得用自然日替代。

映射方法（`method`）至少区分：
- `EXPLICIT`：用户明确指定目标期间，语义保持。
- `ANNUAL_SHIFT`：按年度平移（如 2024 年报 → 2025 年报），语义保持。

`semantics_preserved=false` 时必须说明口径变化，并据此决定是否阻塞。来源期有值但目标期无法解析时，该覆盖行进入 `blockers`（`COVERAGE_PERIOD_UNRESOLVED`）。

## 5. 覆盖需求（coverage_requirements）

每个来源指标 × 目标实体 × 目标期间生成一条覆盖需求，含 `coverage_id`。`disposition` 固定二选一：

- `planned_mql`：需在阶段 D 真实执行 MQL 取数。
- `not_applicable`：来源指标对目标明确不适用（须给 `reason`），不进入取数。

阶段 C 的 `planned_mql` 在阶段 D 必须收敛为 `mql_returned / derived_from_mql / model_forecast / mql_unavailable` 之一；`not_applicable` 保持不变。

## 6. 目标表映射（target_table_mapping）

按来源对象（表/图）聚合其覆盖需求，决定该对象在 B 底稿中的处理动作：

- `adapt`：用目标事实重构来源结构。
- `preserve`：保留来源结构与取值（须有依据）。
- `omit_with_reason`：该对象全部指标均不适用，整体省略并说明理由。

## 7. 资讯去重

资讯行（`information_rows`）用于替换原报告中的新闻/事件引用。去重键固定为：

> **目标实体规范标识 + 规范化标题 + 发布日期 + 来源链接**

结构化指标**不得**进入资讯替换流程；资讯也不得冒充结构化指标事实。

## 8. 阻塞规则

出现以下任一情况，阶段 2 必须 `BLOCKED` 并附 `error.category` 与唯一建议下一步，不得静默降级：

- 实体无法唯一映射（`ENTITY_REVIEW_REQUIRED`）。
- 来源期有值但目标期无法解析（`COVERAGE_PERIOD_UNRESOLVED`）。
- 主标的缺失或不明确。

阻塞时仍落盘已确定的中间产物，但 `stage-2-handoff.json` 状态为 `BLOCKED`、`validation` 含 `FAIL`，下游阶段 D 不得启动。

## 9. 输出

- `entity_mapping.json`、`period_mapping.json`、`coverage_requirements.json`、`target_table_mapping.json`、`information_rows.json`
- `stage-2-handoff.json`（`CONFIRMED` 或 `BLOCKED`，含各产物的绝对路径、SHA-256 与字节数）
