# 结构化数据 Schema

## search_raw.json

MCP `mx_finance_search_news` 原始返回（可截断过长字段）：

```json
{
  "tool": "mx_finance_search_news",
  "query": "中央政治局会议 2025 2026",
  "fetched_at": "2026-07-13T10:00:08+08:00",
  "raw": {}
}
```

## conferences.json

HITL 确认后的会议列表：

```json
{
  "search_query": "中央政治局会议 2025 2026",
  "conferences": [
    {"name": "2025年12月中央政治局会议", "sort_order": 1},
    {"name": "2025年7月中央政治局会议", "sort_order": 2},
    {"name": "2025年4月中央政治局会议", "sort_order": 3}
  ],
  "comparison_dimensions": ["工作总基调", "宏观政策", "财政政策", "货币政策"],
  "auto_dimensions": false
}
```

- `sort_order`：1 = 最新（表格最左列）
- `auto_dimensions: true` 时 `comparison_dimensions` 可为空数组

## reports_content.json（可选）

主模型比对前可汇总各报告文本：

```json
{
  "reports": [
    {
      "conference": "2025年12月中央政治局会议",
      "docx_path": "skills/policy-comparison/output/2026-07-13/reports/2025年12月中央政治局会议_1718000000.docx",
      "char_count": 12500,
      "content": "…全文或截断…"
    }
  ]
}
```

## comparison_result.md

最终交付 Markdown，须包含：

1. 标题 `# 政策会议横向比对分析`
2. 元信息（生成时间、会议列表、维度说明）
3. **Markdown 对比表格**（横向表头为会议，纵向为维度）
4. **差异总结**（约 500 字）

格式要求见 [comparison_prompt.md](comparison_prompt.md)。
