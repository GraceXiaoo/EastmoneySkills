# 阶段 D：新标的底稿生成

## 1. 输入

入口脚本是 `scripts/build_target_workbook.py`：

```text
python scripts/build_target_workbook.py stage-2-handoff.json target_data_evidence.json \
    --output-dir <目录> --replay mql_replay_records.json
```

`stage-2-handoff.json` 必须满足：

- `stage == 2`；
- `status == CONFIRMED`；
- 五个阶段 2 输出存在，且字节数和 SHA-256 与 handoff 一致。

`target_data_evidence.json` 包含：

- `schema_version`，当前固定为 `1`；
- `target_identity`：目标实体稳定 ID、名称和证券代码；
- `writing_payload`：符合 `workbook_input_schema.md` 的工作簿证据输入。

`mql_replay_records.json` 是 **MQL 重放验证门禁**的必需输入（当 `writing_payload.mql_execution_records` 非空时）。其结构为：

```json
{
  "schema_version": 1,
  "replayed_at": "2026-10-08T10:00:00+08:00",
  "records": [
    {
      "request": {"mql": "<与原始执行完全相同的 MQL 脚本>"},
      "response": {"ok": true, "result": {"blocks": [...]}},
      "replay_tool_call_id": "<本次重放的工具调用 ID>"
    }
  ]
}
```

每条 record 必须：
- `request.mql` 与 `target_data_evidence.json` 中某条 `mql_execution_records[].tool_execution.request.mql` 逐字一致；
- `response` 是本次通过 `Execute_MQL` 重新执行的真实返回；
- `replay_tool_call_id` 非空。

`verify_mql_replay.py` 会逐单元格比对原始执行与重放执行的数据矩阵，任一不一致即 FAIL，阶段 D 拒绝生成 Excel。

目标实体必须与 `entity_mapping.json.target_primary` 一致。最终覆盖 ID
必须与已确认的 `coverage_requirements.json` 完全相同，不能静默增加、
删除或改名。

## 2. 证据门禁

阶段 C 的 `planned_mql` 必须在阶段 D 变成以下终态之一：

- `mql_returned`
- `derived_from_mql`
- `model_forecast`
- `mql_unavailable`

阶段 C 的 `not_applicable` 必须保持 `not_applicable`。

`mql_returned` 必须具备：

- 原始工具请求和完整返回；
- 成功执行标识；
- 返回字段、Block 和覆盖 ID 的一一对应关系；
- `source_registry.origin == "mql"`；
- 工作簿事实行的 `来源类型 == "Choice 金融查数"`。

禁止 `source_workbook`、`A_原始底稿` 或“原始研报数值”谱系进入目标
事实行。数值相同本身不是串入判断依据，判断以可验证的数据来源和执行
谱系为准。

## 3. 工作簿与回执

固定 Sheet 及顺序（与 `research-report-review` 生成的格式一致）：

1. `00_导读` — 标的信息、研报信息、刷新说明
2. `10_研报快照` — 本次执行时的静态数据快照（保留数值作为参考）
3. `20_研报底稿` — **只放 `=mql()` 公式、脚本批注和空白溢出区**，不预填数据
4. `30_预测框架` — 盈利驱动、估值参数、研判框架
5. `90_执行日志` — MQL 执行记录、资讯来源、报告映射（默认隐藏）

### `20_研报底稿` 格式规范

每个 MQL 可刷新数据块占一个"锚点区域"：

- 分节标题：合并 A:H 单元格，蓝底（`#D9EAF7`），格式为 `<来源ID> | <标题>`
- 元数据行：来源ID、页码、单位、可刷新锚点数
- 锚点行：`锚点N · <table_id>` + 说明
- 公式单元格：写入 `=mql("#N",0|1)`，MQL 脚本原文存入该单元格**批注**
- 溢出区：公式下方按 `last_result` 形状预留空白单元格，安装 Choice 加载项刷新后填充

输出：

- `B_新标的底稿.xlsx`
- `mql_audit.json`
- `mql_replay_receipt.json`
- `mql_coverage_receipt.json`
- `reference_coverage_receipt.json`
- `workbook_structure_receipt.json`
- `stage-3-handoff.json`

四个回执全部通过后，`stage-3-handoff.json` 写为
`CONFIRMED`，可直接进入阶段 E。
