# research-report-review 调用契约（宿主侧·vendor 模型）

本文档冻结宿主 `sellside-research-refresh-with-excel20` 调用内置（vendor）skill `research-report-review` 的**稳定接口**。
review 的完整逻辑已由 `scripts/build_bundle.py` 整目录 vendor 进 `bundle/review`；运行时不再用 Skill 工具加载外部子 skill。review 升级时，改上游源目录后重跑 `build_bundle.py` 重新编译，只要它仍满足本契约，宿主缝合层无需改动。

> 核心原则：review 作为只读 vendor 代码内置于 `bundle/review`。宿主（AI agent）按 `SKILL.md` §2 **驱动 `bundle/review/scripts/*` 各步**完成 layoutV2 → 取数 → 生成底稿；
> review 的内部错误恢复（如 `LAYOUT_SCHEMA_BLOCKED` → `--layout-mode STRUCTURAL` 回退、`TABLE_BLOCKED` 留痕）由 vendor 脚本自行处理，宿主**不复刻、不重写、不绕过**其内部实现。完成后用 `scripts/run_stage0.py --final` 校验最终双产物存在性与 SHA-256，据此落 handoff。

## 1. 调用方式（vendor 驱动 + 最终产物校验）

review 的完整逻辑 vendor 在 `bundle/review`，宿主按 `SKILL.md` §2.2 的不可跳过顺序驱动各步：

- 宿主（AI agent）依次调用/读取 `bundle/review/scripts/*` 与 `bundle/review/reference/*`（如 `golden_case_manager.py match`、`prepare_workbook_phases.py from-layout`、按 `pdf_layout_api.md` 调 layoutV2、`merge_workbook_phases.py` 合并、`preflight_workbook_input.py` 预检、`research_report_pipeline.py input.json --output result.xlsx`），完成 layoutV2 → 取数 → 生成底稿的全流程（含 `LAYOUT_SCHEMA_BLOCKED` 自动 STRUCTURAL 回退、`TABLE_BLOCKED` 留痕等内部恢复）。
- `bundle/review/scripts/*` 与 `bundle/review/reference/*` 为**只读 vendor 代码**：运行时可调用、可读取，**禁止修改**；确需修复 review 内部，改上游源目录 `D:\git\csskill\研报底稿skill\research-report-review` 后重跑 `scripts/build_bundle.py` 重新编译，不在运行时手改 `bundle/`。
- 宿主只在 review 完成后，用 `scripts/run_stage0.py --final` 校验最终双产物的存在性与 SHA-256，据此落 `stage-0-handoff.json`（CONFIRMED / BLOCKED）。
- 鉴权与 Base URL：layoutV2 地址写占位符 `{em_base_url}/proxy/pdf/layoutV2`，凭据仅从 `EM_API_KEY`/`{em_api_key}` 注入（见 `SKILL.md` §2.2）。

## 2. 最终产物（命名规则）

review 完成"生成研报底稿"后必须在输出目录产出：

| 文件 | 说明 |
|---|---|
| `{标的}_研报底稿抽取.xlsx` | 由 review 底稿流水线生成，固定 5-Sheet 结构；宿主按后缀 `_研报底稿抽取.xlsx` 通配校验，旧名 `A_原始底稿.xlsx` 亦兼容 |
| `{标的}_研报底稿核验报告.md` 或 `{标的}_底稿评测报告.md` | review 面向投研用户的评测报告，说明匹配/不匹配与 `TABLE_BLOCKED` 项；宿主按 `*_底稿评测报告.md` 或 `*_研报底稿核验报告.md` 通配校验，旧名 `A_底稿评测报告.md` 亦兼容 |

文件名以 review 实际交付为准，宿主不硬编码完整文件名：每项产物均精确名优先、后缀通配兜底，同组匹配到多个文件视为歧义并落 `BLOCKED`。宿主阶段 0 的成功判定**仅**依赖这两个文件存在性（及哈希），不依赖 review 的任何中间 JSON。

## 3. 退出码 / 结果语义

- 宿主不读取 review 的退出码或中间 JSON；阶段 0 成功与否**仅**取决于最终双产物是否产出。双产物存在且哈希校验通过 → 阶段 0 置为 `CONFIRMED`；允许底稿 xlsx 内含 `TABLE_BLOCKED` 项，由评测/核验报告说明缺口。
- 双产物缺失 → 阶段 0 置为 `BLOCKED`，向用户报告并请求授权，**不自行重试或复刻 review 内部步骤**。

## 4. 宿主禁止事项（违反即破坏 vendor 边界）

1. 禁止修改 `bundle/review/scripts/*`、`bundle/review/reference/*` 任何源码（只读 vendor 层，见 `SKILL.md` §0）。
2. 禁止写绕过 `bundle/review` 内部脚本的平行脚本（如自建 build_evidence.py、用 openpyxl/layoutV2 手动提取框架替代 review 交付的底稿 xlsx）。
3. 禁止在宿主侧复刻 `--layout-mode STRUCTURAL` 等 review 内部恢复逻辑；恢复是 vendor 脚本的内部责任。
4. 禁止解析 review 的内部错误串（如 `LAYOUT_SCHEMA_BLOCKED`、`TABLE_BLOCKED`、`contentPreview`）以驱动宿主分支；宿主只看最终双产物是否产出。
5. 禁止以静默成功的 handoff 掩盖失败；失败必须如实写 `BLOCKED` 并附原始错误。

## 5. 责任边界

| 关注点 | 归属 |
|---|---|
| PDF 解析、表图普查、`LAYOUT_SCHEMA_BLOCKED` 恢复 | bundle/review（vendor·只读） |
| MQL 映射与取数、`TABLE_BLOCKED` 留痕 | bundle/review（vendor·只读） |
| 生成底稿 xlsx 与评测/核验报告 md（命名规则见第 2 节） | bundle/review（vendor·只读） |
| 驱动 `bundle/review` 各步、`run_stage0.py` 校验产物存在+哈希、写 `stage-0-handoff.json` | 宿主（20·缝合层） |
| 失败时 BLOCKED 与用户授权降级 | 宿主（20·缝合层） |
