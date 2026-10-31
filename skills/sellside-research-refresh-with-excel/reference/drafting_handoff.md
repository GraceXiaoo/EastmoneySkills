# 阶段 E：仿写 skill 文件交接

## 目标

阶段 E 只验证宿主与 vendor 内置 `bundle/drafting` 的文件交接、官方 Excel 预检以及 MD/HTML 受控生成，不修改仿写 skill 内部实现，也不替代完整投研与视觉验收。阶段 E 由宿主在阶段 3 handoff `CONFIRMED` 后自动触发，禁止以「是否继续生成新研报」征询用户或停等确认。

## 输入门禁

1. `stage-3-handoff.json` 必须为 `CONFIRMED`。
2. handoff 登记的目标工作簿必须存在，大小和 SHA-256 必须匹配。
3. 参考 PDF 必须存在并登记 SHA-256。
4. `bundle/drafting/SKILL.md` 必须存在且可读取。
5. 官方 `workbook_probe.py scan` 必须证明以下核心 Sheet 可读（B 沿用 A 的 5-Sheet 命名）：
   - `10_研报快照`（事实区）
   - `30_预测框架`（预测区）
   若 `bundle/drafting` 的 `workbook_probe.py` / `check_handoff.py` 缺失，宿主以 openpyxl 做结构扫描降级（仅校验 Sheet 存在性与数值单元格计数），并把「未做完整单元格级 probe」写入 limitations，不硬阻塞。
6. `10_研报快照` 至少包含一个数值单元格。

公式无缓存的辅助 Sheet 可以作为 limitation 保留，但不得把其中数据声明为已验证事实。

## prepare 输出

`prepare_drafting_handoff.py prepare` 生成：

- `work/environment-receipt.json`
- `work/excel-index.json`
- `work/workbook-probe-receipt.json`
- `work/stage-4-request.json`

请求固定阶段 3 handoff、参考 PDF、目标工作簿、目标对象、证券代码、报告期、截止日和交付目录。

## 受控仿写

受控样例必须遵守仿写 skill 的真实契约：

- reference contract 覆盖参考 PDF 页数并登记对象和排除项；
- data map 绑定目标工作簿哈希、Sheet、范围和事实 ID；
- 内部 MD 的声明位于标题之前；
- heading 和 report-block 顺序与 contract 一致；
- 表格物理行列数与 object contract 一致；
- 只使用阶段 D 已验证事实，不生成无证据的预测、评级或目标价；
- 先运行 `report_workflow.mjs workflow.json --check-only`，再实际生成；
- delivery 目录只包含同名 MD 和 HTML。

首次生成的 `NEEDS_VISUAL_REVIEW` 是合法中间状态。浏览器加载和对象可见性检查不能替代完整的逐对象、打印和研究内容复核，因此不得伪造 `COMPLETE`。

## finalize 输出

`prepare_drafting_handoff.py finalize` 校验 MD、HTML、`workflow_state.json` 和 `delivery-notes.json`，并生成 `stage-4-handoff.json`。finalize 同时校验 HTML 内 `<meta name="source-md-sha256">` 指纹存在且与 MD 实算 SHA-256 一致，缺失或不一致即拒绝产出 handoff。

stage-4 handoff 携带两个来源字段（下游交付门禁据此判定产物确由 drafting 引擎产出）：

- `generator`：`{"skill", "script": "prepare_drafting_handoff.py finalize", "version"}`；
- `engine_receipt`：`workflow_state`（path/SHA-256/status）+ `markdown_sha256` / `html_sha256`（finalize 实算）+ `source_md_sha256_meta`。

- 阶段 E 完成状态为 `CONFIRMED`，无需人工确认，可直接进入阶段 F。
- 无缓存公式和未完成视觉验收必须写入 `limitations`。
- 手写 stage-4 handoff（无 generator/engine_receipt）在阶段 F 来源门禁一律判 `STAGE4_BYPASSED`/`FAIL`，本 skill 不存在任何合法的手写路径。
