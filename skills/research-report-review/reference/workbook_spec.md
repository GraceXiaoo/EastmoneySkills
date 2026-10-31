# Excel 底稿工作簿规范

## 交付原则

Excel 是默认第一交付物，文件名为 `{标的}_研报底稿抽取.xlsx`。生成器只接收 Phase 0–4 已审计的 UTF-8 JSON，不直接解析 PDF 或查询数据服务。

## JSON 根对象

| 字段 | 类型 | 用途 |
|---|---|---|
| `guide` | object | 导读和表格普查统计 |
| `snapshots` | array | 所有纳入表格的原文快照 |
| `chart_snapshots` | array | 所有纳入图表的原文截图与元数据 |
| `chart_data` | array | 从图表可靠回读的 PDF 来源数据块；写入 `10_研报快照` |
| `excluded_tables` | array | 已排除的声明/披露类表格审计记录 |
| `workpapers` | array | 与表格或图表回读块对应的 MQL 映射块；图表可一对多 |
| `verification` | array | 研报值、已取得核验值、适用时的动态值、差异与原始链接 |
| `forecast` | object | 盈利、目标价、估值和假设框架 |
| `execution_log` | array | 技术溯源，默认隐藏 |

`guide` 必含 `company_name`、`security_code`、`report_title`、`report_date`、`verification_date`、`pdf_page_count`、`census_table_count`、`visual_object_count`。生成器强制检查 `census_table_count == len(snapshots) + len(excluded_tables)` 且 `visual_object_count == len(chart_snapshots)`。视觉对象按“接口图片块 + 视觉上属于图表的表格块”的并集生成，不得因为接口已经解析出表格就省略原文截图。

## `snapshots`：原文快照

```json
{
  "table_id": "p3-t2", "page": 3, "table_name": "表名",
  "parse_origin": "LAYOUT_TABLE_BLOCK",
  "bbox": [0.52, 0.18, 0.96, 0.72], "layout_group": "p3-band1",
  "lane": "right", "reading_order": 2, "unit": "百万元",
  "headers": ["项目", "2025A", "2026F"],
  "header_kinds": ["OTHER", "ACTUAL", "FORECAST"],
  "rows": [["营业收入", "1,234.5", "1,560.0"]],
  "source_row_labels": ["营业收入"],
  "row_bboxes": [[0.53, 0.34, 0.95, 0.39]],
  "source_numeric_tokens_by_row": [["1,234.5", "1,560.0"]],
  "row_numeric_token_counts": [2],
  "source_row_count": 1,
  "source_numeric_token_count": 2,
  "extracted_numeric_token_count": 2,
  "source_row_axis": "FINANCIAL_METRIC",
  "source_column_axis": "REPORTING_PERIOD",
  "source_semantic_type": "FINANCIAL_STATEMENT",
  "source_periods": ["2025A"],
  "layout_contract_reason": "原文为纵向科目、横向报告期",
  "queryable_fields": ["营业收入"],
  "is_visual_object": false, "paired_chart_id": "",
  "source_status": "PASS", "visual_check": "PASS"
}
```

强制规则：`table_id` 唯一；`bbox` 是 0–1 的有效矩形；`headers`、`header_kinds` 等长；每行与 `headers` 等长；`source_row_labels` 与抽取行名序列一致；每个 `row_bboxes` 都落在本表区域内；`source_numeric_tokens_by_row` 与生成器从数据列重新提取的原始数值令牌逐项一致；`row_numeric_token_counts` 与重新计算结果一致；`source_row_count == len(rows)`；源和抽取数值令牌数相等；两个状态均为 `PASS`。单元格优先保留 PDF 原始显示字符串。进入查询前必须填写互不相同的 `source_row_axis/source_column_axis`、来源 `source_semantic_type`、非空 `layout_contract_reason`、去重后的完整 `queryable_fields` 和 `source_periods`。`source_periods` 必须严格等于 `header_kinds=ACTUAL` 的对应表头且保持顺序。视觉上属于图表的表格块必须令 `is_visual_object=true` 并用 `paired_chart_id` 与原文截图双向关联；普通数据表令其为 `false`。

资产负债表、利润/损益表、现金流量表以及结构上为财务科目×报告期的表必须标为 `FINANCIAL_STATEMENT`；财务摘要、主要财务比率和每股指标表必须标为 `FINANCIAL_METRICS`。这些来源的轴只能是 `FINANCIAL_METRIC × REPORTING_PERIOD`，工作底稿不得改标为普通截面语义。

`10_研报快照` 每张表的说明区域中，“页码、单位、空间区域、版面位置、表格审计”的标签和值全部左对齐。“空间区域、版面位置、表格审计”不得自动换行，必须保持单行显示；列宽应足以阅读，说明文字不得通过增高行高展示。

## `chart_snapshots`：图表原文截图

```json
{
  "chart_id": "p8-c1", "chart_no": "图表4", "title": "A股主要指数涨跌情况",
  "source": "资料来源：Choice宏观板块，东方财富证券研究所", "page": 8,
  "bbox_pt": {"minX": 185.0, "maxX": 530.0, "minY": 212.9, "maxY": 408.9},
  "crop_pt": {"top": 403.0, "bottom": 669.0, "left": 179.0, "right": 536.0},
  "snapshot_path": "/absolute/path/chart.png",
  "header_footer_ok": true, "visual_check": "PASS",
  "parsed_table_ids": ["p5-t1"],
  "serial": ["东方财富全A", "上证指数"],
  "coordinate": {"x": "最近一周涨跌幅(%)", "y": "指数", "time_series": false, "data_labels": true},
  "frequency": "非时间序列", "api_block_index": 3, "api_class_type": "image"
}
```

`chart_id` 唯一；页码必须在 PDF 范围内；`bbox_pt/crop_pt` 为合法矩形；`snapshot_path` 必须是存在的 PNG/JPEG 绝对路径；`header_footer_ok=true` 且 `visual_check=PASS` 后才能生成工作簿。`parsed_table_ids` 列出接口为同一原文对象另行生成的独立表格块 `snapshots[].table_id`；每个表格最多归属一张图、必须与图表同页，并标记 `parse_origin=LAYOUT_TABLE_BLOCK`。存在独立表格块时，生成器写入“截图→独立解析表格”，不再重复展示图片块 content 的同一候选表。没有独立表格块时，仍不是“接口无结果”：候选数据来自图片块 `content`，经截图逐项视觉验收后进入 `chart_data`。图片限制显示宽度并保持纵横比，下一对象的起始行按缩放后图片高度计算，禁止覆盖。

## `chart_data`：图表结构化数据

```json
{
  "chart_id": "p8-c1", "data_block_id": "p8-c1-d1", "title": "最近一周涨跌幅",
  "unit": "%", "headers": ["指数", "最近一周涨跌幅(%)"],
  "rows": [["上证指数", 1.2], ["深证成指", -0.8]],
  "extraction_method": "LAYOUT_CONTENT_VERIFIED", "confidence_status": "EXACT",
  "candidate_source": "LAYOUT_IMAGE_CONTENT", "visual_validation": "PASS",
  "visual_corrections": [],
  "source_note": "截图数据标签逐项回读通过",
  "mql_mapping_status": "PARTIAL",
  "mql_mapping_note": "上证指数已映射；深证成指本次未匹配",
  "omitted_metrics": ["深证成指：本次未匹配"]
}
```

- `chart_id` 必须引用 `chart_snapshots`；`data_block_id` 唯一；`headers/rows` 必须为非空矩形。
- `chart_snapshots.coordinate.time_series` 必须显式为布尔值；`chart_data.source_temporal_shape` 必须据此填写 `TIME_SERIES` 或 `CROSS_SECTION`，不得根据查询结果倒推来源形态。
- `extraction_method` 优先使用 `LAYOUT_CONTENT_VERIFIED` 或 `LAYOUT_CONTENT_CORRECTED`：前者表示接口图片块 `content` 的候选表与截图逐项一致，后者表示候选存在错位、漏项、符号或数值错误并已按截图修正。不得把 `chart_data` 描述为脱离接口的纯模型识别。
- `candidate_source` 必须为 `LAYOUT_IMAGE_CONTENT`，`visual_validation` 必须为 `PASS`；`visual_corrections` 必须为数组，无修正时为空，有修正时逐项记录接口候选值、截图确认值和位置。接口文本只是候选，截图仍是最终判据。
- `confidence_status` 允许 `EXACT`、`APPROXIMATE`。`VISUAL_ESTIMATE` 只能是 `APPROXIMATE`；接口带 `~` 的近似值、坐标轴刻度或未经截图回读的数据不得标为 `EXACT`。
- `mql_mapping_status` 允许 `FULL`、`PARTIAL`、`NO_MATCH`、`NOT_APPLICABLE`。`PARTIAL`、`NO_MATCH`、`NOT_APPLICABLE` 必须填写 `mql_mapping_note`；`PARTIAL` 必须列出 `omitted_metrics`。`NO_MATCH` 还必须填写 `mql_failure_category` 和 `mql_failure_evidence`；类别按 `mql_execution_protocol.md` Step 2.5 的标准失败类别判定，本规范不重列；可纠正的代码、板块、日期、语法、参数或路径错误不能终止为 `NO_MATCH`。
- `FULL` 或 `PARTIAL` 必须至少有一个 `source_type=CHART`、引用本 `data_block_id` 且 `execution_status=SUCCESS` 的 MQL `workpapers`。`NO_MATCH` 或 `NOT_APPLICABLE` 不得生成图表 MQL 公式。
- `chart_data.chart_id` 所引用的图表必须没有 `parsed_table_ids`；这是同一候选数据在展示层的去重规则，不代表接口候选通道缺失。
- `10_研报快照` 在对应截图及其接口解析表格之后写入本结构化回读表，仅展示单位、抽取方法、置信状态和来源说明；不得展示 `MQL映射状态`、`MQL映射说明`。映射字段仍保留在 JSON 与执行日志。`20_研报底稿` 不直接写入 `chart_data`，不得以 PDF 回读值、人工整理值或缓存代替 MQL。

## `excluded_tables`：排除审计

每项必含 `table_id`、`page`、`table_name`、`bbox`、`exclude_reason`。`exclude_reason` 只允许 `DISCLAIMER`、`ANALYST_OR_INSTITUTION_DISCLOSURE`、`RATING_DEFINITION`、`CONTACT_INFORMATION`。

## `workpapers`：`20_研报底稿`

```json
{
  "mapping_id": "p8-c1-d1-m1",
  "source_type": "CHART", "source_id": "p8-c1", "source_data_block_id": "p8-c1-d1",
  "table_name": "图表4：A股主要指数涨跌情况",
  "mapping_status": "FULL", "expected_rows": 2, "expected_columns": 3,
  "data_source": "MQL", "query_interface": "通过MQL工具链获取结构化数据",
  "mql_script": "完整 MQL 脚本", "block_selector": "#2",
  "script_sha256": "最终脚本规范化后的SHA-256",
  "script_output_fields": ["营业收入"],
  "unit_contracts": [{"field":"营业收入","value_type":"NUMBER","source_unit":"元","display_unit":"百万元","scale_factor":0.000001,"source_semantics":"ABSOLUTE","display_semantics":"ABSOLUTE","script_transform_token":"/ 1000000"}],
  "execution_status": "SUCCESS", "result_as_of": "2026-09-09T10:00:00+08:00",
  "result_origin": "通过MQL工具链获取结构化数据", "execution_run_id": "本次执行返回的唯一标识",
  "raw_result": [["项目", "2025-12-31", "2026-12-31"], ["营业收入", 1234.5, 1560.0]],
  "last_result": [["项目", "2025-12-31", "2026-12-31"], ["营业收入", 1234.5, 1560.0]],
  "cached_table": [["项目", "2025-12-31", "2026-12-31"], ["营业收入", 1234.5, 1560.0]],
  "covered_metrics": ["上证指数"], "omitted_metrics": [],
  "mql_orientation": 0, "orientation_reason": "原始矩阵已按每行一个指标竖排，无需转置",
  "query_shape": "REPORT_MATRIX", "data_path_type": "INDICATOR", "source_semantic_type": "FINANCIAL_STATEMENT",
  "financial_query_mode": "NATIVE_MULTI_PERIOD",
  "financial_query_mode_evidence": "候选元数据确认该标准指标支持报告期序列参数",
  "target_row_axis": "FINANCIAL_METRIC", "target_column_axis": "REPORTING_PERIOD",
  "row_axis_labels": ["营业收入"], "column_axis_labels": ["2025A", "2026F"],
  "display_label_map": [{"key": "OPERATING_REVENUE", "display_name": "营业收入", "kind": "FINANCIAL_METRIC"}, {"key": "2025-12-31", "display_name": "2025A", "kind": "REPORTING_PERIOD"}, {"key": "2026-12-31", "display_name": "2026F", "kind": "REPORTING_PERIOD"}],
  "source_fields": ["营业收入"], "covered_fields": ["营业收入"], "omitted_fields": [],
  "source_periods": ["2025A"], "covered_periods": ["2025A"], "omitted_periods": [],
  "mapping_note": "口径说明", "raw_source_url": ""
}
```

- `source_type` 允许 `TABLE` 或 `CHART`。`TABLE` 的 `source_id` 引用 `snapshots[].table_id`。`CHART` 的 `source_id` 引用 `chart_snapshots[].chart_id`，并必须填写 `source_data_block_id` 引用 `chart_data[].data_block_id`。
- `mapping_id` 对每个 `workpapers` 唯一。同一表格或图表来源允许因跨市场、不同指标族或不同返回形态拆成多个可刷新锚点，构建器必须把这些锚点连续放在同一个来源区域并分别预留溢出空间。资产负债表、利润表、现金流量表是三个独立来源区块，各自生成一个从 `#1` 开始、覆盖全部报告期的锚点，锚点形态按该表选定的 `financial_query_mode` 决定（整表直取用 `ReportBlock`，财务时序用 `TimeSeriesBlock + SetWindow`）；不得把三表塞进同一锚点，也不得把单张财务表按报告期拆成多个锚点。
- 图表映射必须填写非空 `covered_metrics`；`PARTIAL` 还必须填写 `omitted_metrics`。同一 `chart_data` 的全部成功块合并后，覆盖情况必须与其 `mql_mapping_status` 一致。

- `data_source` 是规范化来源枚举，允许 `MQL` 或 `MX_DS_MCP`；输入兼容服务名形式 `mx-ds-mcp`，构建时统一规范化为 `MX_DS_MCP`。`query_interface` 是实际接口名：MQL 写 `通过MQL工具链获取结构化数据`，MX 数据服务写 `mx-ds-mcp` 或实际暴露的能力名称。二者都必须代表真实 Choice 数据执行；不得使用 `PDF_STATIC`、`PDF原文静态抽取` 或类似值伪装查询结果。MQL 必填 `mql_script`，可填 `block_selector`；`MX_DS_MCP` 不得填写 MQL 脚本或 Block，且不生成动态刷新区。数值型 `MX_DS_MCP` 项还必须填写 `fallback_from_mql=true`、`mql_failure_category` 和非空 `mql_failure_evidence`。`mql_failure_category` 只能取 `mql_execution_protocol.md` Step 2.5 允许兜底的四个标准失败类别，本规范不重列。`raw_source_url` 为返回的原始链接；无链接时可为空。
- `expected_rows` 包含 MQL 返回的字段名行；`expected_columns` 包含行标签列。
- `execution_status` 允许 `SUCCESS` 或 `TABLE_BLOCKED`。对 `SUCCESS` MQL 表，`result_origin` 必须为 `通过MQL工具链获取结构化数据`，`execution_run_id` 必须记录本次真实执行可追溯的返回标识，`result_as_of` 记录该次成功执行时间。禁止把脚本解析结果、字段清单、历史缓存或人工整理矩阵冒充执行结果。
- 成功 MQL 的 `mql_script` 是 Excel 刷新的唯一脚本来源。其规范化 SHA-256 同时写入 `workpapers[].script_sha256` 与同一 `execution_run_id` 的执行日志；两者与批注脚本必须一致。`script_output_fields` 按选中 Block 的输出别名顺序填写，并与 `raw_result` 非技术表头完全一致。
- **声明式报告期结构键**：`target_column_axis=REPORTING_PERIOD` 的 workpaper 中，脚本公开声明的 `{报告期}: ...` 输出列是结构键而非业务字段——它计入 `raw_result`/`last_result` 表头与 `display_label_map` 的 `REPORTING_PERIOD` 映射 `key`，但**不计入** `script_output_fields`、`covered_fields` 与 `unit_contracts` 的业务别名比对；未声明的技术键（`EM_DATE`/`EM_CODE` 等）剔除逻辑不变。引擎只有脚本公开声明 `{报告期}` 才返回期间列，故财务整表脚本必须声明它，校验按结构键处理，业务别名比对仍要求非空。
- `unit_contracts` 必须逐项覆盖 `script_output_fields`。`value_type` 为 `NUMBER`、`IDENTIFIER` 或 `TEXT`；数值字段填写原始/展示单位、原始/展示语义和正数 `scale_factor`。单位、比例语义或缩放发生变化时，`script_transform_token` 必须非空且真实存在于该字段的最终 MQL 表达式中。
- `TABLE_BLOCKED` 只用于整张表没有任何成功可查询指标，或查询整体无法执行的情形。一个或多个指标未匹配、无数据或执行失败时，应省略这些指标并将其余成功结果标记为 `PARTIAL/SUCCESS`，不得阻塞整表。`TABLE_BLOCKED` 必须填写 `block_reason` 和 `mapping_note`，可以保留失败时使用的 `mql_script` 便于排查，也可以为空；但不得携带 `last_result`、`cached_table`、`result_origin` 或 `execution_run_id`。
- `raw_result` 必须保存本次 `通过MQL工具链获取结构化数据` 选定 Block 的原始完整二维矩阵。`mql_orientation=0` 表示保持原矩阵，`1` 表示行列转置；字段省略时有效值按 Choice 加载项默认语义取 `1`。`orientation_reason` 必填，应写明目标行轴、目标列轴，并比较保持/转置两种候选。`last_result` 必须严格等于对 `raw_result` 应用有效方向后的矩阵，包含字段名行，形状严格等于 `expected_rows × expected_columns`；不得只保留部分列、部分行或非空子集。财务多期表通常以科目为行、报告期为列；指数截面通常以指数为行、指标为列。该领域惯例只用于定义目标布局，不能直接决定方向参数，有效方向必须由本次原始矩阵与目标布局的实际匹配结果决定。
- `target_row_axis`、`target_column_axis`、`row_axis_labels`、`column_axis_labels` 是方向的语义证据。应用方向后第一列（不含左上角）必须等于 `row_axis_labels`；第一行（不含左上角）必须等于 `column_axis_labels`，仅当期间列已由 `display_label_map` 的 `REPORTING_PERIOD` 条目逐列给出「取数标签 ↔ 研报标签」映射时，改为等于该映射的 `key` 序列。财务多期表强制为 `FINANCIAL_METRIC × REPORTING_PERIOD`；装配阶段不得统一覆写各表方向。
- `source_type=TABLE` 时，来源快照按原文保留 `source_row_axis/source_column_axis` 与原文标签；查询底稿按本次实际成功结果输出，允许合约长表、品种矩阵、分市场表、分部表与多锚点组合，不要求目标轴等于快照轴，也不要求仅靠转置恢复原表。表头、标准简称或行列排布差异本身不判 `PARTIAL`。财务来源仍强制 `FINANCIAL_METRIC × REPORTING_PERIOD`。唯一例外是非财务截面来源只能部分映射到真实执行成功的 `EdbBlock` 时序：该项必须为 `PARTIAL/SUCCESS`，按 `DATE × SERIES` 输出，并进入独立 `21_EDB_NNN` Sheet；财务来源不得使用此例外。
- `source_type=TABLE` 时，工作底稿 `source_semantic_type` 必须严格继承来源快照。财务来源不得改成 `CROSS_SECTION_TABLE`；财务结果的 `column_axis_labels` 必须等于 `covered_periods`，两者均为研报期间标签；当真实执行返回的期间表头与研报标签不同时，必须由 `display_label_map` 的 `REPORTING_PERIOD` 条目逐列声明对应关系，不得改写 `last_result` 去迎合研报标签。`source_periods/covered_periods/omitted_periods[{period,reason,evidence_ids}]` 在锚点内不重不漏，来源整体按来源级汇总对全部历史实际期间验收。
- **财务来源 OTHER 锚点豁免**：快照语义为 `FINANCIAL_STATEMENT`/`FINANCIAL_METRICS` 时，自该来源拆出的锚点仅当同时满足以下全部条件才允许登记 `source_semantic_type=OTHER`：① 锚点轴不是 `FINANCIAL_METRIC × REPORTING_PERIOD`（如估值截面 `ENTITY × METRIC`、`INDICATOR` 路径）；② 仅为降级方向（财务快照 → `OTHER` 锚点）；`OTHER` 快照升级为财务语义、或轴仍为财务形态的降级，均按原规则拒绝。豁免锚点不进入财务矩阵强制规则（财务查询模式、`column_axis_labels == covered_periods` 等），其余覆盖与刷新契约不变。
- 财务来源必须填写 `financial_query_mode` 和 `financial_query_mode_evidence`。允许值与优先级链以 `generation_contract.md` G2 为唯一权威（整表报表直取优先、个别科目报表兜底），本规范不重列顺序。整张财务报表优先 `REPORT_FULL_TABLE`：报表路径整表直取（参考 `mql_templates/` 对应科目模板），只需 `report_selection_reason`，不要求指标失败证据。`FINANCIAL_TIME_SERIES` 的成功脚本必须使用候选确认的单一 `TimeSeriesBlock + SetWindow` 覆盖全部目标期间；审计元数据优先从脚本和执行结果自动补全。`PERIOD_BLOCK_MERGE` 必须填写 `prior_multi_period_attempt_ids`，引用财务时序/原生多期不可用的执行日志证据；`REPORT_FALLBACK` 用于个别科目兜底，继续遵守单点指标优先的证据规则。
- 每个成功 MQL 块必须在生成查询前建立完整 `display_label_map[{key,display_name,kind}]`。`kind` 允许 `ENTITY`、`CATEGORY`、`METRIC`、`FINANCIAL_METRIC`、`SERIES` 与 `REPORTING_PERIOD`。证券、股票、指数、行业、利率、债券、基金、商品、期货、外汇、宏观序列及其他对象均必须保留技术键和可读简称/名称；技术代码不得成为唯一展示标签。实体或分类为行时，结果至少包含“技术键 + 可读名称 + 数值”，并用 `entity_display_name_field` 指定名称列；指标为行或序列为列时，实际标签必须与映射中的可读名称一致。
- `REPORTING_PERIOD` 条目是期间列标签映射的权威定义：期间条目的 `key` 保存真实执行返回的期取标签（溯源口径用，必须逐列等于应用方向后结果矩阵的期间表头），`display_name` 保存研报期间标签（契约与展示口径用，必须逐列等于 `column_axis_labels`）。期间列存在期间条目映射时，`column_axis_labels`、`covered_periods`、`row_axis_labels` 一律保留研报标签，不得因为取数标签不同而被改写。期间 `display_name` 必须是可识别的期间记号（年份、季度/半年、`FY` 简写均可），行标签使用的“不得为纯技术代码”可读性约束不适用于期间条目；期间 `display_name` 不得与任何行标签 `display_name` 重名。期间条目仅当结果矩阵期间表头与研报标签逐列不同时才必需；两者本就一致时省略即可，省略时结果期间表头必须逐字等于 `column_axis_labels`。
- `data_path_type=INDICATOR` 不得包含 `ReportBlock`。财务数据使用 `REPORT` 时：`REPORT_FULL_TABLE` 只需填写 `report_selection_reason`；`REPORT_FALLBACK` 必须填写 `report_fallback_reason`、`indicator_attempt_ids` 和 `report_selection_reason`，且 `indicator_attempt_ids` 必须引用 `execution_log` 中同来源、`data_path_type=INDICATOR` 且带失败分类的实际尝试。自由文本证据不能单独触发报表兜底。
- 成功 MQL 工作底稿的唯一写入门禁是真实执行通过。含服务端妙想专用路径的脚本执行成功后允许进入 `20_研报底稿`，不再作为禁止项。
- 连续时间图的成功工作底稿必须使用 `query_shape=TIME_SERIES`，并使用与数据领域匹配的连续时序块：证券等实体时序使用 `TimeSeriesBlock`，宏观指标时序允许使用 `EdbBlock`。两者都必须经过真实执行和本地 Choice Excel 加载项兼容性评估，目标轴为 `DATE × SERIES`，并填写来源/查询起止日期、`axis_tick_frequency`、`observation_frequency`、`frequency_evidence`、`expected_min_points` 和有效点数。`CrossSectionBlock`、单个区间累计值或多个截面点不能作为走势图工作底稿。
- 走势展示类时序锚点允许把 `SetWindow` 结束时间写成不带引号的动态记号 `N()`（普通时序自动取到最新日期）；`_s` 报告期时序允许 `MRQ()`（自动停在最新已披露报告期）。启用动态结束时间的工作底稿必须填写 `query_end_date_dynamic`（取值 `N()` 或 `MRQ()`），且 `query_end_date` 记录生成时该记号解析出的快照日期；生成时快照必须与来源图表起止范围完全一致，脚本中同一记号不得以引号包裹。`EDB` 不支持动态记号。`expected_rows`、`temporal_point_count`、`result_as_of` 等形状与取数时间字段均为生成时基线；刷新后的延伸不视为违规。启用动态记号的锚点独占 `22_TS_NNN` Sheet，主底稿仅提供跳转入口。
- 时序工作底稿必须记录应用层窗口策略 `window_policy`：`SOURCE_FIXED`（默认，保留原图事实）、`LATEST_1000_TRADING_DAYS`（以已确认最新交易日为终点、含终点的最近 1000 个交易日；起点必须来自已确认交易日历，不足 1000 时如实填写 `query_window_point_count` 并置 `query_window_truncated=true`；原生滚动未实现，必须置 `rolling_implemented=false`）、`EDB_FIXED_FREQUENCY`（EDB 频率桶，不套交易日历）。`source_start_date/source_end_date` 保留原图事实，`query_start_date/query_end_date` 另存本次窗口；`LATEST_1000_TRADING_DAYS` 允许两者不同。脚本使用可选 `{预加载周期}` 时必须记录 `preload_period_count`，且 `query_window_point_count + preload_period_count ≤ 1000`。普通时序的市场写入 `SetWindow` 的已确认可选 `{市场类型}`；`_s` 报告期时序不得写市场。
- `cached_table` 是从上述完整 `last_result` 建立的生成前校验矩阵，不写入 `20_研报底稿`，不得混入 PDF 原值、人工补值或其他查询批次。新 JSON 落盘前必须逐单元格比较 `last_result` 与 `cached_table`，包括空值位置、文本、数值、行列顺序；仅允许 JSON 数字类型的等值表示差异（如 `1` 与 `1.0`），不得允许字符串数字与数值互换。
- 每个来源只建立一个来源区域，但区域内可以有一个或多个动态结果锚点，不建立 PDF 静态结果区。每个锚点的完整 MQL 脚本以纯文本存入该锚点批注。允许公式形态：`=mql()`、`=mql("#2")`、`=mql("#2",0)`、`=mql("#2",1)`。一段脚本中的数据 Block 必须从 `#1` 开始连续递增，选择器必须引用脚本内真实存在的 Block；禁止截取原脚本的 `#2/#3` 单独作为新脚本而不重新编号。跨市场或异构结果不能安全合成一个 Block 时，为同一来源追加第二、第三个锚点，每个锚点独立预留溢出区。`0` 的表头是指标；`1` 的指标在第一列，表头通常是日期或证券编码。
- 插件按约定从公式下一行开始写标题行和数据。生成文件时该溢出区必须完全为空，不预填表头或数据；刷新成功后仅显示本次 MQL 返回结果。任一结构检查不一致时不得写公式，也不得写入静态替代值。未安装加载项时公式可显示 `#NAME?`，其下方保持空白。`MX_DS_MCP` 不进入本 Sheet。
- 覆盖检查的输入必须是本次 `通过MQL工具链获取结构化数据` 返回的真实 Block，不得通过扫描脚本文本、数输出字段名或人工判断来代替。成功路径固定为：逐指标检索（包括预测值）→ 汇总已匹配指标 → 执行 MQL → 选择 Block → 应用 orientation → 写入完整返回矩阵 `last_result` → 由其建立 `cached_table` → 逐单元格一致性校验 → 保存为新的输入 JSON → `--validate-only` → 生成 `20_研报底稿`。`PARTIAL` 的矩阵只包含成功指标；未匹配或失败指标不得作为空行、静态值或人工补值混入。
- 公式锚点布局必须根据实际执行矩阵计算溢出范围：`spill_rows = 执行矩阵行数`，`spill_columns = 执行矩阵列数`。同一来源的多个锚点按顺序上下排列，每个锚点与后续锚点、合并单元格及其他来源区域做交集检查；存在交集即校验失败。不能仅按缓存表高度预留空间，因为原始宽表经 orientation 转置后可能比缓存表更高。启用动态结束时间（`N()`/`MRQ()`）的锚点不按此规则预留，而是独占 `22_TS_NNN` Sheet，锚点下方与右侧不放置任何内容，为刷新增长留空。
- 可比公司跨市场时，每个市场段分别生成 workpaper。所有段使用相同有序 `market_schema`，且必须等于各自 `script_output_fields`；`market_segment` 包含 `market`、`currency`、`entities`、`codes`，其中 `codes` 与选中 Block 的 `SetCodes` 相同。`market_output_order` 在每段保存相同的研报原始实体顺序；所有段的实体和代码不得重复，合计必须完整覆盖来源实体。
- `20_研报底稿` 的取数时间、映射说明、加载项说明等辅助长文本默认不自动换行；其右侧保持空白，让文本自然向右显示，避免辅助说明撑高行高。数据表自身仍按源表需要设置换行。
- `20_研报底稿` 的蓝底分节标题至少合并 A:H，左对齐、自动换行并按字数设置显式行高，不得依赖 Excel 对合并单元格的自动行高。
- `20_研报底稿` 每张表说明区域中的“页码”标签和值必须左对齐，与 `10_研报快照` 的格式保持一致。
- `00_导读` 已使用区域内的所有单元格统一左对齐，包括标题、字段名、字段值和说明文本。
- 字段覆盖检查必须对每张 `source_type=TABLE` 的表执行，而不限于三大报表或财务类表格。逐表比较“快照 `queryable_fields`”“已成功 MQL 字段”和“省略字段”；不得因为字段多、指标类型杂或查询困难就只查询少数摘要项。每个省略字段必须有未匹配、明确不支持、无数据、口径不可靠或执行失败等理由与证据。
- 每个锚点用 `source_fields`、`covered_fields`、`omitted_fields[{field,reason,evidence_ids}]` 声明并分割**本锚点**的目标字段（`source_fields ⊆ 快照 queryable_fields`），锚点内不重不漏；`FULL` 仅在锚点覆盖其全部目标字段时成立。来源整体是否完整由来源级汇总判定：把该来源全部锚点的 `covered_fields` 合并为 `S`、`omitted_fields` 合并为 `O`，对快照 `queryable_fields`（`E`）要求 `S⊆E`、`O⊆E`、`S∩O=∅`、`S∪O=E`；已在其他锚点成功的字段不得写成本锚点的 `omitted_fields`。可比公司表还必须对 `entities`、`periods`、`metrics` 三个维度分别填写 `source_*`、`covered_*`、`omitted_*`。来源实体涉及 A 股、港股、美股时，必须按市场分别解析代码和执行 MQL，再以统一列结构同表纵向拼接；不得将不同市场代码混在一次未验证查询中，也不得因市场或币种不同直接省略。
- 含报告期的表还必须使用 `source_periods`、`covered_periods`、`omitted_periods[{period,reason,evidence_ids}]`：锚点只声明本锚点目标期间（`source_periods ⊆ 快照 ACTUAL 期间`）并在锚点内不重不漏，来源整体期间覆盖按同样的来源级汇总对快照全部 `ACTUAL` 期间验收。省略期间的 `evidence_ids` 必须引用本次执行日志中的检索或执行失败；“已有最新一期”“为节省时间”或自由文本说明不能省略历史期。
- 对 `TABLE`，锚点级 `FULL` 表示该锚点覆盖了它自己的全部目标字段；来源是否整体 `FULL` 由来源级 `S∪O=E` 汇总判定，版式、表头或标准简称与原文不同不改变该判定。对 `CHART`，`FULL` 表示本 `source_data_block_id` 的可查询指标全部被一个或多个成功块覆盖。`PARTIAL` 只输出成功匹配指标，返回矩阵按实际结果填写，并在 `omitted_metrics` 逐项说明省略原因。
- 需要可刷新快照而 `workpapers` 缺少对应项时，校验失败。

## `verification`：核验数据（不生成 Excel Sheet）

`verification` 字段在 JSON 中仍收集与校验，但不再生成 Excel Sheet。其数据仅保留在 JSON 与 `90_执行日志` 中。

```json
{
  "metric": "营业收入", "period": "2025A", "report_value": 1234.5,
  "unit": "百万元", "choice_value": 1234.4, "difference": -0.1,
  "data_source": "MQL", "query_interface": "通过MQL工具链获取结构化数据",
  "query_script": "完整 MQL 脚本", "source_block": "#2",
  "conclusion": "一致", "attribution": "四舍五入",
  "source_location": "第3页 / p3-t2 / 营业收入 / 2025A",
  "queried_at": "2026-09-09T10:00:00", "raw_source_url": ""
}
```

`choice_value` 为兼容既有输入保留，语义为“已取得核验值”。也可额外写入 `verified_value`，两者同时出现时必须相同。`data_source` 必填，允许规范值 `MQL`、`MX_DS_MCP` 或兼容输入 `mx-ds-mcp`；`query_interface` 必填并填写实际接口名。`raw_source_url` 写入数据服务返回的原始链接。数值指标的 `difference` 若提供，必须在精度内等于核验值减研报值；资讯类可使用文本 `difference` 记录逐项差异说明，并必须填写 `report_excerpt`。

数值型 `MX_DS_MCP` 核验记录必须额外填写 `fallback_from_mql=true`、`mql_failure_category` 和非空 `mql_failure_evidence`。类别按 `mql_execution_protocol.md` Step 2.5 允许兜底的四个标准失败类别取用，本规范不重列；证据记录同指标已完成的 MQL 检索词、候选、已确认实体/板块/日期和真实执行结果。内容型资讯、新闻、公告和研报原文检索不要求这些字段。这样宏观、行业经济、利率、债券、基金、指数、外汇和商品数值不会因分类或可纠正错误而绕过 MQL。

## 固定 Sheet

| Sheet | 内容 |
|---|---|
| `00_导读` | 基本信息、数据边界、普查/纳入/排除数 |
| `10_研报快照` | 所有纳入表格的原文行和值；所有纳入图表的原文截图、元数据及标签/坐标回读表 |
| `20_研报底稿` | 只放表格或图表来源的已验证 `=mql("#Block",0|1)`、纯脚本批注与空白溢出区；不放 PDF 静态数据、图片或 Excel 图表 |
| `21_EDB_NNN` | 每个成功 EDB 时序锚点独占一个扩展 Sheet；只在锚点上方放来源与映射说明，锚点下方不放其他内容，避免刷新增长侵占其他单元格 |
| `22_TS_NNN` | 每个启用动态结束时间（`N()`/`MRQ()`）的时序锚点独占一个扩展 Sheet；除来源与映射说明外还标注动态记号和生成时基线日期，锚点下方不放其他内容，容纳刷新后的时序延伸 |
| `30_预测框架` | 盈利驱动、目标价勾稽、估值参数、一致预期和假设 |
| `90_执行日志` | 技术溯源，默认 hidden |

## 调用与验收

```bash
<workspace-python> scripts/build_workbook.py input.json --validate-only
<workspace-python> scripts/build_workbook.py input.json --output output.xlsx
```

`<workspace-python>` 指当前 Codex 工作区内置依赖返回的 Python 可执行文件。执行前必须加载工作区依赖；不要盲目调用缺少 `openpyxl` 的系统 Python。

必须确认：五个核心 Sheet 齐全；`00_导读` 全部左对齐；快照表数和行数与审计清单一致；图表数、图片数、元数据数和回读表数一致且互不覆盖；`20_研报底稿` 及扩展 `21_EDB_NNN` Sheet 的每个 MQL 锚点符合 `=mql()`、`=mql("#Block")` 或 `=mql("#Block",0|1)`，Block 和方向均与 JSON 语义一致，批注只含完整脚本；`raw_result` 按有效方向变换后与 `last_result/cached_table` 一致；公式下一行按变换后形状预留的溢出矩形为空且彼此不交叠；每个成功 `EdbBlock` 锚点独占一个扩展 Sheet 且锚点下方没有其他内容；每个启用动态结束时间的锚点独占一个 `22_TS_NNN` Sheet，`query_end_date_dynamic` 与脚本内不带引号的记号一致，生成时基线日期与来源结束日期一致；底稿 Sheet 不含 `chart_data` 静态表、图片或图形；执行日志中成功的图表 MQL 必须有对应公式锚点；执行日志隐藏。

`90_执行日志` 的每个成功 MQL 执行必须填写指标/对象、原始 Block、完整路径、执行编号、取数时间、返回形状或摘要、单位、最终脚本 SHA-256 和状态；每个成功 `workpapers.execution_run_id` 必须在日志中唯一对应。只有状态和时间、其余字段为空的记录不得通过校验。
