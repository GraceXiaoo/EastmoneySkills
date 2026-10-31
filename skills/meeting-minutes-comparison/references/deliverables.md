# 交付物与落盘规范（AgentLoop）

**所有产物必须写入 workspace 本地文件**，禁止仅在对话中输出 Markdown/JSON 而不落盘。

## 路径约定（Linux 优先）

在 AgentScope workspace 中，skill 位于 `skills/policy-comparison/`。所有路径**相对于 workspace 根目录**：

```
skills/policy-comparison/output/{YYYY-MM-DD}/
```

示例：

```
skills/policy-comparison/output/2026-07-13/manifest.json
skills/policy-comparison/output/2026-07-13/reports/2025年中央经济工作会议_1718000000.docx
skills/policy-comparison/output/2026-07-13/comparison_result.md
```

## 完整目录结构（一次运行必须齐全）

```
skills/policy-comparison/output/{YYYY-MM-DD}/
├── manifest.json              ← 运行清单 + 文件索引
├── timing.json                ← 耗时统计
├── mcp_trace.json             ← MCP 调用明细
├── quality_review.md          ← 质量自检
├── search_raw.json            ← MCP 搜索原始返回
├── conferences.json           ← 经 HITL 确认后的会议列表
├── hitl_config.json           ← 用户确认的会议与维度配置
├── comparison_result.md       ← 最终比对报告（主模型生成）
└── reports/
    ├── {会议名}_{timestamp}.docx
    └── step_data_{会议名}_{timestamp}.json   ← 可选，脚本自动生成
```

## 落盘顺序

| 阶段 | 动作 |
|------|------|
| Step -1 | `scripts/run_py.sh scripts/ensure_env.py --check` |
| Step 0 | Write `manifest.json`（status=running） |
| Step 1 | MCP 搜索 → Write `search_raw.json`；更新 `mcp_trace.json` |
| Step 2 HITL | 向用户确认会议与维度 → Write `hitl_config.json`、`conferences.json` |
| Step 3 | 逐会议调用 `generate_policy_document.py` → docx 落盘 `reports/` |
| Step 4 | `read_docx.py` 或 Read 读取各报告 → Write `reports_content.json`（可选） |
| Step 5 | 主模型按 comparison_prompt 生成比对 → Write `comparison_result.md` |
| Step 6 | Write `timing.json`、`quality_review.md`；更新 `manifest.json`（status=completed） |
| Step 7 | `validate.py --date {date}`；Read `comparison_result.md` 确认落盘 |

## manifest.json 示例

```json
{
  "template_id": "policy_comparison",
  "run_date": "2026-07-13",
  "report_title": "政策会议横向比对分析",
  "mode": "agent_loop",
  "status": "completed",
  "started_at": "2026-07-13T10:00:00+08:00",
  "finished_at": "2026-07-13T10:25:00+08:00",
  "run_dir": "skills/policy-comparison/output/2026-07-13",
  "search_query": "中央政治局会议 2025 2026",
  "conferences": ["2025年12月中央政治局会议", "2025年7月中央政治局会议"],
  "comparison_dimensions": ["工作总基调", "宏观政策", "财政政策", "货币政策"],
  "comparison_path": "skills/policy-comparison/output/2026-07-13/comparison_result.md",
  "files": [
    {"kind": "comparison", "path": "skills/policy-comparison/output/2026-07-13/comparison_result.md"},
    {"kind": "report", "path": "skills/policy-comparison/output/2026-07-13/reports/2025年12月中央政治局会议_1718000000.docx"}
  ]
}
```

详见 [observability.md](observability.md)。
