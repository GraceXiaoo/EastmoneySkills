# 研报复现 3.0 编排契约（vendor 模型）

## 1. 组件与角色

| 组件 | 角色 |
|---|---|
| `sellside-research-refresh-with-excel` | 提供框架适配、取数、底稿与校验逻辑的复用基线 |
| `research-report-review` | 生成原始研报 Excel 底稿及面向投研用户的评测报告 |
| `periodic-report-drafting` | 根据原始 PDF 与新标的 Excel 底稿生成 MD/HTML |
| `sellside-research-refresh-with-excel20` | 宿主编排、框架提取、目标适配、目标底稿及交付汇总 |

宿主不指定、不检查依赖 skill 的版本号。依赖 skill 上游源逻辑变化时，须改上游源目录后重跑 `scripts/build_bundle.py` 重新 vendor，并重新验证其直接参与的 handoff 及下游阶段。

## 2. 编排模型

1. 宿主负责按阶段驱动 vendor 内置的 `bundle/review`、`bundle/drafting` 与自有缝合层脚本；两个 vendor 子 skill 不互相读取、导入或调用。
2. 阶段间唯一正式边界是已落盘的输入、产物和 `stage-N-handoff.json`。
3. vendor 模型下，review 与 drafting 整目录内置于 `bundle/*`，运行时直接调 `bundle/*/scripts/*`，不再用 Skill 工具加载外部子 skill，也不依赖外部子 skill 目录。
4. 只有状态为 `CONFIRMED` 且输入、输出哈希未变化的阶段可以被下游复用。
5. 每个阶段完成验证后直接写为 `CONFIRMED`，无需人工确认，可一次性连续跑完所有阶段。

handoff 的机器可读字段由 [orchestration_contract.schema.json](orchestration_contract.schema.json) 定义。

## 3. 通用 handoff 信封

每个 `stage-N-handoff.json` 必须包含：

- `schema_version`：当前固定为 `1`。
- `task_id`：同一次运行全程不变。
- `stage`：`0` 至 `5`。
- `status`：状态机中的合法值。
- `producer`：产出该阶段的 skill 名称、版本和执行模式。
- `inputs`、`outputs`：每项包含绝对路径、SHA-256、字节数和媒体类型。
- `started_at`、`completed_at`：带时区的 ISO 8601 时间。
- `validation`：实际运行的验证项、结果和回执路径。
- `limitations`：已知限制；无则为空数组。
- `error`：失败时的类别、消息、最后成功检查点和唯一建议下一步。
- `resume`：续跑所需阶段、前置状态和输入哈希。

禁止以空输出、默认值或成功形态 handoff 表示失败。`BLOCKED` 必须填写 `error`；`CONFIRMED` 必须具有非空输出及通过的验证记录。

## 4. 阶段契约

### 阶段 0：原始研报底稿

**执行者**：宿主按 `SKILL.md` §2 驱动 vendor 内置 `bundle/review`（“生成研报底稿”流程）。

**输入**：

- 原始研报 PDF。
- 本次任务输出目录。

**输出**：

- 底稿 xlsx（review 交付名 `{标的}_研报底稿抽取.xlsx`，兼容旧名 `A_原始底稿.xlsx`，宿主按后缀 `_研报底稿抽取.xlsx` 通配校验）：至少包含 `00_导读`、`10_研报快照`、`20_研报底稿`、`30_预测框架`、`90_执行日志`，并允许 `21_EDB_NNN` 等扩展 Sheet。
- 评测报告 md（review 交付名 `{标的}_研报底稿核验报告.md` 或 `{标的}_底稿评测报告.md`，兼容旧名 `A_底稿评测报告.md`，宿主按 `*_底稿评测报告.md` 或 `*_研报底稿核验报告.md` 通配校验）：底稿 skill 产出的、面向投研用户的评测报告。
- `stage-0-handoff.json`。

**完成条件**：底稿 skill 自身完成门禁通过；两个交付物存在且哈希已记录。失败时保持 `BLOCKED`，不得自动降级到 1.0 的本地解析流程。

### 阶段 1：完整框架提取

**执行者**：2.0。

**输入**：阶段 0 的 Excel、handoff 和原始 PDF 定位信息。

**输出**：

- `metric_framework.json`。
- `framework_extracted.md`。
- `stage-1-handoff.json`。

**完成条件**：以 `10_研报快照` 的全部纳入表图为覆盖全集，合并成功 MQL 锚点、执行日志中的失败/无法映射记录、预测框架和扩展 Sheet。取数失败只能改变状态，不能删除框架项。

### 阶段 2：目标适配与取数计划

**执行者**：2.0。

**输入**：阶段 1 的框架、用户指定目标实体和目标期间。

**输出**：

- `entity_mapping.json`。
- `period_mapping.json`。
- `coverage_requirements.json`。
- `target_table_mapping.json`。
- `information_rows.json`。
- `stage-2-handoff.json`。

**完成条件**：主标的、可比公司、行业/板块、指数/基准、宏观对象和外部事件主体均有角色动作；年度/季度/月周日、单期/累计、同比/环比、实际/预测及交易日语义均有明确映射。无法唯一映射时必须 `BLOCKED` 并等待用户决定。

资讯去重键固定为“目标实体规范标识 + 规范化标题 + 发布日期 + 来源链接”。结构化指标不得进入资讯替换流程。

### 阶段 3：新标的 Excel 底稿

**执行者**：2.0。

**输入**：阶段 2 的映射和取数计划、真实 MQL/mx-ds-mcp 执行证据、MQL 重放记录（`mql_replay_records.json`）。

**输出**：

- `B_新标的底稿.xlsx`。
- `mql_audit.json`。
- `mql_replay_receipt.json`、`mql_coverage_receipt.json`、`reference_coverage_receipt.json` 和 `workbook_structure_receipt.json`。
- `stage-3-handoff.json`。

**工作簿契约**：固定 Sheet 为 `00_导读`、`10_研报快照`、`20_研报底稿`、`30_预测框架`、`90_执行日志`，与 `research-report-review` 生成的格式一致。`20_研报底稿` 只放 `=mql()` 公式、脚本批注和空白溢出区。

**完成条件**：B 的所有目标事实来自本次真实取数，A 的数值不得进入 B 的事实或预测行。阶段 2 handoff 必须已确认且哈希匹配；每条 MQL 脚本必须经重放验证（原始执行与重放执行的数据矩阵逐单元格一致），四个校验回执必须全部通过。

### 阶段 4：新研报

**执行者**：宿主驱动 vendor 内置 `bundle/drafting` 完整流程。阶段 3 handoff 为 `CONFIRMED` 后必须自动衔接执行，不得询问用户是否继续，也不得停等确认。

**输入**：

- 原始研报 PDF。
- `B_新标的底稿.xlsx`。
- 目标对象、报告期、截止日和输出目录。

**输出**：

- `B_新研报.md`。
- `B_新研报.html`。
- `delivery-notes.json`。
- `stage-4-handoff.json`。

**完成条件**：先运行 `workbook_probe.py scan`；核心事实区 `10_研报快照` 与预测区 `30_预测框架` 可读（B 沿用 A 的 5-Sheet 命名）。若官方 probe 缺失，宿主以结构扫描降级并记入 limitations，不硬阻塞。仿写 skill 优先消费已有底稿，缺项才补查。核心区不可读时必须暂停，不能交付成功形态报告。

### 阶段 5：评测与交付汇总

**执行者**：2.0。

**输入**：阶段 0 至 4 的已确认 handoff。

**输出**：

- `delivery-manifest.json`。
- 最终交付清单。
- 可选的新标的复现评测报告。
- `stage-5-handoff.json`。

**最低交付物**：原始研报 Excel 底稿、原始研报底稿 skill 面向投研用户的评测报告、新标的 Excel 底稿、新研报 MD 和 HTML。

## 5. 路径、哈希和错误规则

- handoff 保存绝对路径；skill 包内文档链接使用相对路径。
- SHA-256 针对实际交付文件字节计算；目录不得用单个伪哈希代替。
- 路径必须位于本次任务输出目录或明确登记的只读输入目录。
- 输入文件变化时，将该阶段及所有下游阶段重置为 `PENDING`；无关上游阶段保持 `CONFIRMED`。
- 不捕获并吞掉子 skill 错误。错误类别、原始消息、回执路径和唯一建议下一步必须进入 handoff。

## 6. 发布边界

阶段 A 只冻结契约和依赖，不提供完整运行能力。`bundle/review`、`bundle/drafting` 未经 `scripts/build_bundle.py` 编译产出前，`SKILL.md` 必须保留未完成声明，不得发布为完整 3.0 skill。
