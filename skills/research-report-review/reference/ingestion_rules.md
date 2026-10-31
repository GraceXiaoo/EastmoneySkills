# PDF 摄取、全表格与全图表保真规则

## 目标

完整抽取研报中所有有内容的研究表格和统计图表，不含文末免责声明、利益冲突/信息披露、评级定义和联系信息对象。表格完整性指表数、表头、行数、行序、单元格数、文本和数值均与页面图像一致；图表完整性指图数、标题、主体、图例/坐标轴、资料来源、截图和可可靠读取的指标均可回查。PDF 文本层、接口多模态识别、OCR 和 Markdown 均仅为候选信号；页面渲染图与最终裁剪图是最终视觉判据。

## T0：页面盘点与排除区域

1. 使用 [pdf_layout_api.md](pdf_layout_api.md) 规定的 `layoutV2` 接口取得 `textBlocks`，记录 PDF 总页数，为每页保存页码、实际页面尺寸、300dpi 页面图像和文本索引。任一页缺失则 `I1` 失败。
2. 逐页分为：研究正文、研究附表、免责声明、利益/机构信息披露、评级定义、联系信息、混合页。混合页必须以坐标矩形分区，不得整页排除。
3. 只允许排除完全落在非研究区域内的表格。页码靠后、标题含“附录”或版式相似都不是排除依据。
4. 对排除表登记 `table_id`、页码、`bbox`、标题/首行和 `exclude_reason`。

## T1：先普查表格与图表，后抽取

转录任何数值前，遍历全部页面。每张可见表格唯一编号为 `p{page}-t{order}`，记录：起止页、标题、单位、脚注、数据来源、归一化 `bbox=[x0,y0,x1,y1]`、`layout_group`、`lane`、`reading_order`、表头行数、数据行数、列数、是否跨页续表、`include` 和排除理由。

普查完成前不得开始指标挑选。严禁只抽取“重要”、“与核验有关”或“可被数据库覆盖”的表格。

同时建立图表普查表。候选对象是全部 `classType=image` 块与视觉上属于图表的 `table` 块的并集；后者既包括标题命中 `图表N：`、`图N：` 的对象，也包括带坐标轴、图例、曲线、柱体或图表资料来源但标题识别不完整的对象。每个对象唯一编号为 `p{page}-c{order}`，其中 `order` 是**页内图序（每页从 1 重新计数，仅图对象占号）**：`classType=image` 一律为图；`classType=table` 仅当内容开头即图题（`图N：`/`图表N：`）才算图版式图表；数据表裁图不占图号。不得使用跨页累计的全局序号；该口径须与 `prepare_workbook_phases.py` 完全一致。`chart_no` 只记录原文中真实出现的图号（如 `图1`），标题未识别时留空，**不得按序号臆造图号**。每条记录接口页内 `index`、`classType`、标题、资料来源、PDF 点坐标 `bbox_pt`、是否纳入、排除理由和关联表格 ID（如有）。对被接口同时表示为图片块与表格块的同一视觉对象，只建一条图表记录，并让表格的 `paired_chart_id` 与图表的 `parsed_table_ids` 双向对应。接口解析表格是截图旁的结构化证据，不能替代原文截图。不得把 `imageUrl=null` 解释为没有图表；接口只提供位置，截图必须由源 PDF 渲染后裁切。

普查结束时立即写入 `guide.visual_object_count`，其值等于纳入的视觉对象数。每个纳入视觉对象在任何 MQL 规划开始前都必须已经有截图任务；禁止等工作簿装配阶段再从 `classType` 推断是否需要截图。

## T2：空间分区和串表防护

1. 先按水平带分页，再按垂直栏分每个带。表格区域只包含其标题、表头、数据行、单位和直接脚注。
2. 同一水平带有两张及以上表格时，必须为每张表创建独立裁切图并分别识别。不得用整页 OCR 的行序代替任一表的行序。
3. 每个单元格保存来源区域或可回查的行/列位置。来源位置越出所属 `bbox` 则 `I10` 失败。
4. 跨页续表只在表名/语义、列数、列顺序和重复表头一致时合并。续页重复表头不计入数据行。
5. 水印只从工作副本隐藏，不修改原页。若与数值重叠，对照文本层、相邻行形式和高分辨率裁切；仍不可辨认则阻断该表。

## T3：每张表四遍抽取

1. **结构遍**：只记录表名、单位、多级表头、列边界、数据行边界、合并单元格和脚注，不转录数值。
2. **标签遍**：按视觉行序转录每个非空数据行的行名，保留缩进、子项、重复行名、序号和合计/小计。不得根据常识补行、合并行或改名。
3. **数值遍**：逐单元格转录，保留负号、括号、百分号、小数位、倍数、千分位、破折号和空白。空白与 `0`、`-`、`N/A` 不等价。
4. **全量回读遍**：从末行倒序回读至首行，再正序核对数值。每行校验行名、单元格数、数值令牌数、符号、小数位和单位。

多级表头需保留层级。写入 Excel 时可展平为单行唯一列名，但必须同时保留原表头结构。

## T4：单表硬校验

| 检查 | 通过标准 |
|---|---|
| 表头完整 | 源列数 = 抽取列数；展平后列名唯一且顺序一致 |
| 行数完整 | 源物理非空数据行数 = 抽取行数；合计、小计、备注数据行不得丢失 |
| 矩形完整 | 每行单元格数与列数一致；合并单元格展开规则有记录 |
| 行序保真 | 行标签序列与页面一致；不存在无源定位的行 |
| 数值指纹 | 每行和整表的数值令牌个数、顺序、正负号、百分号和小数位与页面一致 |
| 空间隔离 | 所有单元格来源位置落在本表 `bbox` 内；无来自相邻表的行或数值 |
| 年度性质 | 所有时间列保留原标签，并标记 `ACTUAL` / `FORECAST` / `OTHER` |
| 单位与脚注 | 单位和改变口径的脚注已记录；不得默默换算或删除 |

勾稽关系、合计公式、同比增速等只是辅助告警，不得用计算值替换页面显示值。

## T5：全局门禁

| ID | 检查 | 失败处理 |
|---|---|---|
| I1 | PDF、页面图像与页码索引完整 | 补齐后重跑 |
| I2 | 水印未伤及表格文本 | 恢复原页重跑 |
| I3 | 全页表格普查完成 | 继续扫描 |
| I4 | 普查数 = 纳入数 + 排除数 | 定位未决对象 |
| I5 | 每个排除对象有空间位置和合法理由 | 恢复误排除表 |
| I6 | 每张纳入表完成独立区域抽取 | 重建裁切区域 |
| I7 | 表头、行数和矩形全通过 | 回退结构/标签遍 |
| I8 | 数值指纹全通过 | 回退数值遍 |
| I9 | 行序和无伪行全通过 | 回退标签遍 |
| I10 | 并排表空间隔离全通过 | 拆分区域后重跑 |
| I11 | 所有纳入表逐行逐值回读通过 | 不允许以抽样代替 |
| I12 | 时间列性质、单位和口径脚注完整 | 补齐后重验 |
| I13 | 图表普查数 = 纳入数 + 排除数 + 未决数 | 定位遗漏或重复对象 |
| I14 | 每张纳入图表有唯一截图且标题、footer、图形主体完整 | 调整扩边后重裁 |
| I15 | 图表指标均有序列/坐标语义、抽取方法和置信状态 | 补齐或标记不可可靠抽取 |
| I16 | 图表截图与后续 Excel 区域无重叠 | 按图片高度重新计算锚点 |

任一纳入表失败时，只重跑该表及其空间相邻表，最多 3 次。仍失败则标记 `TABLE_BLOCKED`，停止“完整底稿抽取”交付。

## 交接字段

每张纳入表必须含：`table_id`、`page`、`table_name`、`bbox`、`layout_group`、`lane`、`reading_order`、`headers`、`rows`、`source_row_labels`、`row_bboxes`、`source_numeric_tokens_by_row`、`row_numeric_token_counts`、`source_row_count`、`source_numeric_token_count`、`extracted_numeric_token_count`、`source_semantic_type`、`source_row_axis`、`source_column_axis`、`source_periods`、`layout_contract_reason`、`queryable_fields`、`is_visual_object`、`paired_chart_id`、`source_status=PASS`、`visual_check=PASS`。`source_row_labels` 和 `source_numeric_tokens_by_row` 必须在全量回读遍从页面图像独立记录；后者保留逗号、正负号、括号、小数位和百分号。`row_bboxes` 为每行的归一化坐标，不得越出本表区域。`queryable_fields` 必须在查询前从完整快照生成并保持原顺序，不得根据后来找到的指标反向缩减；`source_row_axis/source_column_axis` 按原表视觉方向确定，不能由 MQL 默认方向决定。`source_periods` 按 `header_kinds=ACTUAL` 的表头原顺序生成；普通无期间表为空数组。

财务语义在本阶段锁定：资产负债表、利润/损益表、现金流量表标为 `FINANCIAL_STATEMENT`，财务摘要、主要财务比率和每股指标标为 `FINANCIAL_METRICS`。若名称识别不完整，但行标签为财务科目且列头为报告期，也按上述结构归类。财务表必须使用 `FINANCIAL_METRIC × REPORTING_PERIOD`，进入查询阶段后不得降级成普通截面表。

排除表存入 `excluded_tables`，至少含 `table_id`、`page`、`bbox`、`table_name`和 `exclude_reason`。

## C0–C3：图表截图与指标抽取

### C0 坐标截图

1. 使用 PDF 页面的实际宽高，不得假定所有页面均为 A4。`layoutV2` 坐标原点按实测为左下角，裁剪图像原点为左上角，因此必须执行 y 反转：`top = page_height - maxY - top_pad`，`bottom = page_height - minY + bottom_pad`。
2. 首次裁剪使用接口 bbox，四周只保留 6pt 安全边距，并以同页、水平重叠的相邻块边界作为硬上限，避免带入上一段正文、下一张表标题或相邻栏。只有视觉验收明确指出标题、图例或来源缺失时，才定向扩大对应一侧；不得四边同时扩大，也不得越过相邻对象中线。使用 `extract_pdf_charts.py --include-tables` 统一裁剪表格和图表，不得临时另写宽边距裁图脚本。
3. 页面按 300dpi 渲染，同页多图复用页面图。截图文件名固定使用 `p{page}-i{api_block_index}.png`，标题只写元数据，不进入文件名；不得依赖长标题、被截断的工具输出或接口返回的空 `imageUrl` 寻址。

### C1 双通道完整性校验

- 结构通道：接口 `content` 首行应识别标题，正文中应识别 `资料来源` 或 `数据来源`；缺失时登记结构告警。
- 视觉通道：逐图确认标题无截断、资料来源完整、坐标轴/图例/曲线或柱体完整。任一项失败必须调整扩边重裁，最多 3 次；仍失败则 `visual_check=BLOCKED`，不得作为已完成截图写入 Excel。
- 最终验收必须逐对象记录结论，但远程 Vision 调用按页面或相同版式批量提交并返回 `object_id → 结论`；不得把逐对象验收误解为每张截图必须单独调用一次服务。首批已经 `PASS` 的对象写入检查点并永久复用，后续只重新提交裁剪失败或结论缺失的对象，禁止为了核对行数再次调用已经通过的整页截图。
- Vision 调用按 [execution_stability.md](execution_stability.md) 的外部服务保护协议，以 `service=vision` 和页面/版式批次计数；批次返回中每个 `chart_id/table_id` 仍分别记录结论。提示词改写、整图改半图或切片不会绕过同一批次的 3 次上限；连续两次服务型失败后只熔断 Vision，PDF 解析、MQL 等其他服务仍可继续。接口候选、OCR 或文本层不得替代视觉 `PASS`，但应随阶段进度保存。

### C2 元数据与指标

每张图的 `chart_snapshots` 至少包含：`chart_id`、`chart_no`、`title`、`source`、`page`、`bbox_pt`、`crop_pt`、`snapshot_path`、`header_footer_ok`、`visual_check`、`serial`、`coordinate`、`frequency`、`api_block_index`、`api_class_type`。

图表指标写入 `chart_data`，至少含 `chart_id`、`data_block_id`、`headers`、`rows`、`unit`、`extraction_method`、`confidence_status`、`source_note`、`mql_mapping_status` 和 `mql_mapping_note`。允许的方法为：

- `LAYOUT_CONTENT_VERIFIED`：接口图片块 content 候选表与裁剪截图逐项一致；
- `LAYOUT_CONTENT_CORRECTED`：接口图片块 content 候选表存在错位、漏项、符号或数值错误，按截图逐项修正并记录差异；
- `EXTERNAL_VERIFIED`：通过 MQL 或 `mx-ds-mcp` 取得并与图表口径对应的值；
- `VISUAL_ESTIMATE`：只能按曲线/柱高估读的值，仅作参考，必须标记 `APPROXIMATE`。

`confidence_status=EXACT` 只允许前三类且已完成截图回读或外部复核。接口 content 中带 `~` 的数字、坐标轴刻度、OCR 猜测和曲线估读不得标记 `EXACT`；若无法可靠抽取，保留截图和元数据并记录 `IMAGE_UNPARSED`，不得编造数据行。

### C3 Excel 交接

- `10_研报快照` 插入 `snapshot_path` 指向的原文裁剪图；图前写标题、页码、资料来源、bbox、频率和校验状态。插图宽度受工作表可读区域限制，保持纵横比，并按缩放后的像素高度折算占用行数。每张图之后紧接其 `chart_data` 回读表，作为 PDF 原文证据；不得把回读表移动到 `20_研报底稿`。
- 每个 `chart_data` 块都逐指标执行 MQL 映射。`mql_mapping_status` 允许 `FULL`、`PARTIAL`、`NO_MATCH`、`NOT_APPLICABLE`；前两者必须存在引用该 `data_block_id` 的成功 MQL `workpapers`，后两者必须说明不可映射原因。
- `20_研报底稿` 对表格和图表来源都只写成功 MQL 公式、纯脚本批注和空白溢出区，不写 `chart_data` 静态表、不插图、不生成 Excel 图表。图表中未映射或仅能由 `mx-ds-mcp` 取得的指标保留在快照、JSON 与执行日志，不得作为静态替代值进入底稿。
- 一张图表跨多个实体类型、品种或查询口径时，可拆为多个 `workpapers`，每个使用唯一 `mapping_id`，并通过 `covered_metrics`、`omitted_metrics` 说明覆盖范围；多个公式的溢出矩形不得相交。
- 源截图与工作簿放在不同目录时，JSON 中使用可解析的绝对路径；生成器嵌入后工作簿不依赖该外部文件才能显示，但仍在执行日志保留来源路径。
