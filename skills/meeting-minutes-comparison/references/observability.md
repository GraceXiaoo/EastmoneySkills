# 可观测性规范

Agent 在运行过程中应维护以下可观测文件。

## timing.json

```json
{
  "started_at": "2026-07-13T10:00:00+08:00",
  "finished_at": "2026-07-13T10:25:00+08:00",
  "total_ms": 1500000,
  "mode": "agent_loop",
  "phases": {
    "env_check_ms": 2000,
    "mcp_search_ms": 8000,
    "hitl_ms": 0,
    "doc_generation_ms": 900000,
    "read_docx_ms": 5000,
    "comparison_ms": 120000,
    "finalize_ms": 3000
  },
  "conferences_count": 3,
  "reports_generated": 3
}
```

- `hitl_ms`：等待用户确认的时间（若同步对话可记 0，异步可估算）
- `doc_generation_ms`：所有 `generate_policy_document.py` 调用累计耗时
- `comparison_ms`：主模型生成比对表格与总结耗时

## mcp_trace.json

```json
{
  "run_date": "2026-07-13",
  "calls": [
    {
      "seq": 1,
      "phase": "search_conferences",
      "tool": "mx_finance_search_news",
      "query": "中央政治局会议 2025 2026 政策",
      "started_at": "2026-07-13T10:00:05+08:00",
      "duration_ms": 4100,
      "ok": true,
      "result_preview": "前 200 字摘要…",
      "error": null
    }
  ]
}
```

- 每次 MCP 调用后：**Read** 已有 `mcp_trace.json` → 合并新 call → **Write** 覆盖
- 覆盖已存在文件前必须先 Read（Write 工具铁律）

## quality_review.md

```markdown
# 质量评审 · 2026-07-13

| 检查项 | 状态 | 说明 |
|--------|------|------|
| MCP 搜索 | ok | 12 条结果 |
| HITL 确认 | ok | 3 场会议，4 个维度 |
| 报告生成 | ok | 3/3 docx |
| 比对报告 | ok | comparison_result.md 含表格 |
| validate.py | ok | 无 errors |

## 缺失与风险
- 无
```

## hitl_config.json

记录用户确认结果，便于审计：

```json
{
  "confirmed_at": "2026-07-13T10:02:00+08:00",
  "user_confirmed": true,
  "search_query": "中央政治局会议 2025 2026",
  "proposed_conferences": ["2025年12月中央政治局会议", "2025年7月中央政治局会议", "2025年4月中央政治局会议"],
  "final_conferences": ["2025年12月中央政治局会议", "2025年7月中央政治局会议", "2025年4月中央政治局会议"],
  "proposed_dimensions": ["工作总基调", "宏观政策", "财政政策", "货币政策"],
  "final_dimensions": ["工作总基调", "宏观政策", "财政政策", "货币政策"],
  "user_message": "使用默认即可"
}
```
