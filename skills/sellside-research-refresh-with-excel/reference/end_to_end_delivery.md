# 阶段 F：端到端编排与交付验收

## 目标

阶段 F 复用已确认的阶段 0–4 handoff，验证路径、大小、SHA-256、阶段连续性和最低交付集合，生成最终交付清单。它不得重新运行已确认阶段，也不得把不同任务的样例拼接冒充真实端到端运行。

## 严格模式

默认严格模式要求：

1. 阶段 0–4 各有且只有一个 handoff。
2. 每个 handoff 状态均为 `CONFIRMED`。
3. 所有阶段使用同一个 `task_id`。
4. 阶段 N 的 inputs 精确绑定阶段 N-1 handoff 的绝对路径和 SHA-256。
5. 所有 input/output 工件的路径、大小和 SHA-256 匹配。
6. 每个阶段的 validation 均为 `PASS`。
7. **stage-4 来源门禁**：交付物必须确由 drafting 引擎产出，任何一项失败即 `FAIL`：
   - stage-4 handoff 必须含 `generator` 且 `script == "prepare_drafting_handoff.py finalize"`；
   - 必须含 `engine_receipt`，其 `workflow_state.json` 在 outputs 登记、哈希一致，且状态属于合法交付三态 `COMPLETE` / `COMPLETE_WITH_OMISSIONS` / `COMPLETE_WITH_UNVERIFIED_LAYOUT`；
   - 交付 MD/HTML 的 SHA-256 与 `engine_receipt.markdown_sha256` / `html_sha256` 一致；
   - 交付 HTML 含 `<meta name="source-md-sha256">` 且与交付 MD 实算 SHA-256 一致；
   - MD 首个非空行以「非原机构正式报告」声明开头并含写作日期；MD 不含 `[source:N]` 内部标记，不含 `](#reference-` 未解析锚点。

任何失败都返回首个需要续跑的阶段及已可复用阶段，不从头重跑。

## 交付判定与失败路径

- 全部门禁通过：`delivery-manifest.status=PASS`、`stage-5-handoff.status=CONFIRMED`、退出码 0。
- `COMPLETE_WITH_UNVERIFIED_LAYOUT` 是合法降级状态：manifest 自动追加「版式未渲染审计」限制并在交付清单标注，不假填视觉 PASS。
- 来源门禁任一失败：`delivery-manifest.status=FAIL`（附 `failure_reasons`）、`stage-5-handoff.status=FAILED`（`error.category=STAGE4_BYPASSED`）、交付清单顶部标注 FAIL、退出码 1。失败产物不得写入 limitations 放行，也不得作为正式成果使用。

## 受控夹具模式

`--controlled-fixture` 仅用于汇总分阶段实现期间形成的已确认样例。该模式仍校验每个 handoff 和全部工件，但允许任务 ID 和阶段连续绑定不同，并强制把这一事实写入 limitations。该产物不能作为一次真实端到端执行的证据。

## 最低交付集合

`delivery-manifest.json` 必须登记：

- `source_workbook`：原始研报 Excel 底稿；
- `source_review_report`：底稿 skill 面向投研用户的评测报告；
- `target_workbook`：新标的 Excel 底稿；
- `target_report_markdown`：新研报 MD；
- `target_report_html`：新研报 HTML。

每项记录绝对路径、SHA-256、字节数、媒体类型、来源阶段和验收状态。

## 阻塞和限制

- 部分 MQL 失败只有在上游已按契约显式处理并确认后才可作为 limitation 传递，不能被阶段 F 隐藏。
- 扩展 Sheet 不应被固定 Sheet 列表误拒绝。
- 实体或期间歧义导致阶段 2 阻塞时，从阶段 2 续跑。
- 底稿或仿写子 skill 阻塞时，从其对应阶段续跑。
- 任一已确认工件发生变化时，从首个受影响阶段续跑。

## 输出

- `delivery-manifest.json`
- `final-delivery-list.md`
- `stage-5-handoff.json`

阶段 F 验证通过后直接写为 `CONFIRMED`，无需人工确认。
