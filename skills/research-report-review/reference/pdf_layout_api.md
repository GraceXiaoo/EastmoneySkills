# PDF 图表解析、定位截图与元数据接口

本规范是 `research-report-review` 的 PDF 入口。使用 `layoutV2` 获得版面块，再从源 PDF 渲染页面并按坐标截图。接口识别文本只作候选信号，最终图表和数值以截图回读或外部数据复核为准。

## 1. 接口

- 地址：`{em_base_url}/proxy/pdf/layoutV2`。`{em_base_url}` 必须原样保留在构建回退值中，由发布/打包过程自动替换为当前正式线或测试线接口网关；运行时也可通过统一的 `EM_BASE_URL` 环境变量注入。占位符哨兵必须用 `"{em" + "_base_url}"` 构造，避免发布替换同时改写哨兵比较而把已注入地址误判为占位符。
- 方法：`POST multipart/form-data`
- 文件字段：`srcFile`
- 鉴权：请求头 `em_api_key: ${EM_API_KEY}`。凭据优先从 `EM_API_KEY` 环境变量注入，构建过程也可替换 `{em_api_key}`；不存在也不得新增 `PDF_LAYOUT_API_KEY` 等专用变量，不接受命令行显式 Key。读取规则固定为 `os.environ.get("EM_API_KEY", "{em_api_key}").strip()`，占位符常量用 `"{em" + "_api_key}"` 避免被误当真实凭据；空值和未替换的 `{em_api_key}` 均不得发送。不得把 Key 写入日志或业务输出。
- 成功：HTTP 200，且响应 `status=0` 或 `code=200`，`message=success`。

```bash
curl --location --request POST \
  '{em_base_url}/proxy/pdf/layoutV2' \
  --header "em_api_key: ${EM_API_KEY}" \
  --form 'srcFile=@/absolute/path/report.pdf' \
  --max-time 180 -o response.json
```

调用入口：

```bash
python scripts/call_pdf_layout.py \
  --pdf /absolute/path/report.pdf \
  --out-dir /absolute/path/output
```

`call_pdf_layout.py` 生成原始响应及归一化 JSON。缺少有效 `EM_API_KEY` 时在发请求前退出 2；网络失败、HTTP/业务失败或 JSON 非法时也退出 2 并如实记录，不得伪造成功结果或静默切换到未指定服务。`env` 中“变量已设置”只证明非空，不证明值有效；是否有效以 `layoutV2` 的实际响应为准。MQL 工具可用也不等于当前脚本进程中的 `EM_API_KEY` 已正确注入。

HTTP 401/403，或 HTTP 200 但业务 `code=401/403`，统一分类为 `AUTH_INVALID`。该错误不是瞬时服务异常，不能换提示词或原样重试：立即将 `pdf_layout` 服务熔断并保存阶段进度，待运行环境重新注入有效 `EM_API_KEY` 后才能显式恢复。错误日志只能记录失败类别和状态码，不得输出 Key、Key 片段、哈希或请求头。

每次调用前必须按 [execution_stability.md](execution_stability.md) 使用 `service_guard.py` 登记 `service=pdf_layout`、PDF 指纹对应的对象 ID 和 `operation=layout_parse`；接口返回后立即结算结果。超时、限流、非法 JSON 或服务错误累计到该服务，但只熔断 `pdf_layout`，不得阻断已取得截图的本地处理或其他独立服务。

## 2. 关键响应字段

`data.textBlocks[]` 的关键字段为 `page`（1 起）、`index`、`classType`、`content`、`minX/maxX/minY/maxY`、`imageUrl` 和 `tableContent`。

- `classType=image`：统计图或图片块；`imageUrl` 可能为 `null`，仍需从源 PDF 截图。
- `classType=table`：文字表格；标题命中 `图表N：` 或 `图N：` 时也纳入图表普查，并关联其表格抽取结果。
- `content`：多模态近似识别，可能包含标题、Markdown 表格和资料来源。带 `~` 的值、坐标轴刻度或未经截图回读的值不可作为精确数据。
- `minX/maxX/minY/maxY`：PDF 点坐标，实测原点在左下角；接口变更时必须以小样实测重新确认。

归一化输出至少保留：调用时间、源 PDF 绝对路径、接口地址、HTTP/业务状态、请求或文档 ID、MD5、页数、每页版面块、原始 `textBlocks` 和 `pageContent`。原始响应不得覆盖。

## 3. 图表枚举

先纳入全部 `classType=image`，再扫描所有块标题：

```python
re.finditer(r"图表?\s*(\d+)[：:]\s*([^\n;|]{2,80})", content)
```

去重键优先使用 `(page, index)`；同标题但不同页或不同块不得误合并。统计图走截图与图表指标流程，`table` 类图表同时走表格四遍抽取流程。

## 4. 坐标转换与截图

目标页按 300dpi 渲染。必须从 PDF 读取该页实际宽高 `W/H`，不得固定为 A4：

```python
scale = dpi / 72.0
top_pt = H - maxY - top_pad
bottom_pt = H - minY + bottom_pad
left_pt = minX - side_pad
right_pt = maxX + side_pad
```

默认四周安全边距为 6pt，并同时受相邻块边界约束。接口 bbox 是首次裁剪的主定位依据；只有视觉验收指出某一侧缺失时才扩大该侧，且不得跨过相邻对象中线。表格与图表统一使用 `extract_pdf_charts.py --include-tables`，保持原始纵横比，不要先把页面强制缩放成 A4。

使用 `scripts/extract_pdf_charts.py` 批量裁剪：

```bash
python scripts/extract_pdf_charts.py \
  --pdf /absolute/path/report.pdf \
  --layout-json /absolute/path/response.json \
  --out-dir /absolute/path/charts \
  --dpi 300
```

脚本输出 PNG 和 `chart_metadata.json`。它负责确定性坐标裁剪和结构字段抽取；`header_footer_ok` 与 `visual_check` 初始为待视觉复核，只有实际查看截图后才能改为通过。`chart_id` 采用 `p{page}-c{order}`，`order` 为页内图序（每页从 1 重新计数，仅图对象占号；数据表裁图不占号），与 `prepare_workbook_phases.py` 同一口径；`chart_no` 只记录原文真实图号，标题未识别时为空，不做序号臆造（规则见 [ingestion_rules.md](ingestion_rules.md)）。

## 5. 双通道验收

结构通道检查 `content` 是否含完整标题和 `资料来源/数据来源`；视觉通道逐图检查：

1. 顶部标题完整；
2. 底部资料来源完整；
3. X/Y 轴、图例、曲线/柱体和数据标签完整；
4. 截图没有相邻图表或正文造成歧义。

任一项失败，调整对应扩边并重新裁剪，最多 3 次。最终逐图验收，不得只抽样。纯扫描件仍可截图，但没有可靠文字层时，指标抽取需明确降级或阻断。

## 6. 元数据与数值边界

每图记录 `chart_id/chart_no/title/source/page/bbox_pt/crop_pt/snapshot_path/serial/coordinate/frequency/api_block_index/api_class_type/header_footer_ok/visual_check`。

- 标题与来源：优先解析 `content`，缺失时从截图补读。
- 序列名：来自图例、表头或类别轴。
- 坐标语义：记录 X/Y 含义、是否时间序列、是否有数据标签。
- 频率：按数据点稠密度结合文字说明判断，不可只看稀疏的 X 轴刻度。
- 精确值：只接受截图中可逐项回读的数据标签/表格值，或外部接口复核值。
- 近似值：曲线位置、柱高或带 `~` 的识别值只能标为 `APPROXIMATE`，不得用于准确度结论。

实测 ZIP 中的具体图号、页码、标题和指标仅是回归样例，不是通用默认值。
