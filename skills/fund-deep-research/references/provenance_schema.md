# 三层数据隔离与公开溯源

- `report_content`：报告正文，只含中文研究内容和公开业务数据。
- `public_provenance`：仅供HTML用户主动点击查看的脱敏原始数据表，只含中文表名、日期、中文列名、原始返回值和正文引用位置；默认隐藏。
- `internal_audit`：接口名、路径、MQL、过滤条件、执行ID、错误码和失败原因，只留在 `work/`。

公开溯源JSON顶层包含 `version=1.0` 和 `sources`。每个source包含：`source_id`、`title`、`as_of`、`columns`、`rows`、`used_in`。`source_id` 使用“数据表-001”格式。列名使用中文并保留原始返回值，不得包含接口名、报表路径、MQL、内部代码、执行ID、错误或失败诊断。

每个关键数字、数据表和图表绑定至少一个 `source_id`。交付前执行：

```text
python scripts/fund_deep_research.py provenance-validate <公开溯源.json>
python scripts/fund_deep_research.py report-scan <HTML文件> <Word文件> <PDF文件>
```

任一检查返回非0时禁止交付。

## HTML溯源交互

- 关键数字、表格或图表标题旁加入“查看原始数据”，以 `data-source-id` 绑定来源表。
- hover显示中文表名、日期、行列数；click打开可关闭且支持键盘操作的对话框。
- 表头为中文，宽表允许横向滚动；不得显示接口、路径、脚本或错误。
- CSS、JavaScript和溯源JSON内联或本地嵌入，不依赖网络。
- 原始表只能存在于默认关闭的对话框，禁止原始数据附录；打印样式隐藏触发器和对话框。

## Word与PDF

Word和PDF只含研究正文、业务图表、必要数据表与风险提示，不展示溯源编号，不复制HTML隐藏对话框内容。
