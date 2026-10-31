# 端到端执行示例（经实测）→ 回归矩阵

> 所有示例均按 5 步流程（Get_MQL_Reference → Search_Business_Knowledge → Search_Context → 生成 MQL → Execute_MQL）实测通过。
> 脚本与正例/反例已内嵌在各 `.mql` 模板（读一个模板即拿齐模式+代码+反例）；本表只保留**回归快照**：结构、关键检索/失败修复、结果与耗时。
> ⚠️ 路径/代码/日期/数值均为历史验证样例，每项新任务必须重新 Search_Context（G2），不得照抄。基线 2026-09-14；财务时序增量 2026-09-18/09-30；主营构成增量 2026-10-10。

## 回归矩阵

| # | 场景 | 结构 | 关键检索/失败修复 | 结果快照 | 耗时 | 脚本 |
|---|------|------|-------------------|---------|---:|------|
| A | 茅台前收盘价 | CrossSectionBlock | 实体 600519.SH；cross_section 前收盘价（默认最新） | 1 行，600519.SH=1285.13 | 6213ms | [.mql](mql/股/个股行情/贵州茅台_前收盘价.mql) |
| B | 全部A股涨跌幅Top10 | CrossSectionBlock+Sort+Head | 板块全部A股；timeRecognition 未识别"最新交易日"→用指标默认值；涨跌幅单位% | 5562 只参与，输出 10 行，榜首燧原科技 179.22% | 13354ms | [.mql](mql/股/TopN排序/全部A股_涨跌幅Top10.mql) |
| C | 按上市地点统计股票数 | CrossSectionBlock+GroupBlock | 上市地点 cross_section 无参；分组键必须 : 输出 | 深2901/沪2318/京343，合计 5562 | 5824ms | [.mql](mql/股/分组聚合/按上市地点统计股票只数.mql) |
| D | 茅台收盘价与5日均线 | TimeSeriesBlock+SetWindow+MA | **失败修复**：v1 缺市场类型→规划失败"SetWindow 必须指定交易市场"；v2 加 {市场类型}=上交所 | 10 日期位置，09-11 收盘1275.16/MA5 1295.296 | 1456ms | [.mql](mql/股/时序行情/贵州茅台_收盘价与5日均线.mql) |
| E | 限售解禁明细+Merge补列 | ReportBlock+CrossSection+MergeBlock | **失败修复**：候选①远端预检失败"报表名称不能为空"→换候选②；报表证券代码带后缀可关联 EM_CODE | 报表4行→过滤2行，Merge 2/2 命中 | 3652ms | [.mql](mql/股/报表明细/贵州茅台_限售解禁_Merge补列.mql) |
| F | 国债到期收益率Top10 | 债券板块+NULL过滤+TopN | varieties=债券；含到期板块大量 NULL→NOT IS_NULL；债券 EM_CODE 纯数字无后缀 | 5467 只→有值 693 只，输出 10 行 | 7002ms | [.mql](mql/债/行情指标/国债_到期收益率Top10.mql) |
| G | 多报告期归母净利润宽表 | CrossSectionBlock 多期内联 | cross_section 财务指标≠时序；8 期内联一行多列；累计口径勿标单季度 | 1 行 8 列（2024Q1–2025Q4） | 7597ms | [.mql](mql/股/财务指标/贵州茅台_多报告期归母净利润_宽表.mql) |
| H | 多报告期归母净利润长表 | ReportBlock+SetReportFilter | reportStandardCodeSupported=true；加载列过滤报告期；非时序不能用时序函数 | 8 行，**与 G 逐期一致** | 699ms | [.mql](mql/股/财务指标/贵州茅台_多报告期归母净利润_长表.mql) |
| I | 限售解禁 Group后Merge补简称 | ReportBlock→GroupBlock→MergeBlock | 报表多行先 Group 聚合为唯一右键再 Merge，避免右键重复 | 聚合 1 行，Merge 1/1 | 1917ms | [.mql](mql/股/报表明细/贵州茅台_限售解禁_Group后Merge简称.mql) |
| J | 东方财富单季度营业收入时序 | TimeSeriesBlock+季窗口 | time_series、_s 结尾；不用 ReportBlock 冒充；累计≠单季度 | 12 季度，report_count=0 | 236ms | [.mql](mql/股/财务指标/东方财富_近三年单季度营业收入_时序.mql) |
| K | 比亚迪资产负债表年度时序 | TimeSeriesBlock+年窗口 | _s 报告期序列用"年"、不写市场；110 条 _s 路径全部有效 | 2 行，40 指标 79 数据点 | 9016ms | [.mql](mql/股/财务指标/比亚迪_近两年资产负债表时序.mql) |
| L | 比亚迪利润表年度时序 | TimeSeriesBlock+年窗口 | 利润表科目+EBIT/EBITDA/扣非衍生可同处一 Block | 2 行，24 指标 44 数据点 | — | [.mql](mql/股/财务指标/比亚迪_近两年利润表时序.mql) |
| M | 比亚迪现金流量表年度时序 | TimeSeriesBlock+年窗口 | 经营/投资/筹资/净增加/补充资料细分层级 | 2 行，22 指标 44 数据点 | — | [.mql](mql/股/财务指标/比亚迪_近两年现金流量表时序.mql) |
| N | 比亚迪每股指标与财务比率时序 | TimeSeriesBlock+年窗口 | 每股(元/股)+比率(小数，显示%乘100)可同处一 Block | 2 行，7+17 指标 | — | [.mql](mql/股/财务指标/比亚迪_近两年每股指标与财务比率时序.mql) |
| O | A股主营构成（按产品/行业/地区） | ReportBlock×3 + 本地 FILTER_ROWS | reportFilterColumns 为空→禁 SetReportFilter；分布类型返回中文词，本地过滤 | 按产品/行业/地区三 Block | — | [.mql](mql/股/财务指标/比亚迪主营构成_按产品_按行业_按地区.mql) |
| P | 港股主营构成（按产品/地区） | ReportBlock×2 + SetReportFilter + 本地 FILTER_ROWS | 有加载列→SetReportFilter 远端过滤（IN 函数式）；分布类型码值 1/2；报告期类型名称剔"单季度" | 按产品/地区两 Block | — | [.mql](mql/股/财务指标/腾讯控股主营构成_按产品_按地区.mql) |
| Q | 美股主营构成（按产品/地区） | ReportBlock×2（两张独立报表） | 按产品/地区是两张报表、无分布类型列；报告期类型=="1" 剔单季度；报告期为美股财季末 | 按产品/地区两 Block | — | [.mql](mql/股/财务指标/AAPL苹果主营构成_按产品_按地区.mql) |

## 实测要点汇总

1. **5 步流程零跳过**：13 场景（含 2 次失败修复）全部先检索后生成，无臆造路径。
2. **两次失败均 ≤2 次修改解决**（D 时序市场类型、E 报表候选更换），未触发 G11。
3. **数据自洽**：A 前收盘价 1285.13 = D 中 2026-09-10 收盘价 = E Merge 补入的前收盘价。
4. **财务多期≠时序**：G 用 cross_section 多期内联、H 用 ReportBlock；只有 J/K/L/M/N 候选为 time_series 才用 TimeSeriesBlock。
5. **OutputBlock**：仅标记最终 Block 时上游照常取数但不投影（见 C 仅返回 blockId=2）。
6. **大结果未触发**（示例均 ≤12 行）；触发时按 SKILL.md Step 5 读 `result_file.path`。
7. **主营构成三市场不可通用**（O/P/Q）：同一业务在 A股/港股/美股是三套报表结构（分布类型中文词/码值/无列、本地/远端过滤），报告期类型含正常+单季度两套行须剔除；详见 [indicator_templates.md §6](indicator_templates.md#6-常用报表清单) 与 [traps.md 陷阱 18/19](traps.md)。

> 每个场景均独立执行四步工具；B 的"最新交易日"未被时间分区识别，按分区结果用指标元数据默认值，未自行写日期。
