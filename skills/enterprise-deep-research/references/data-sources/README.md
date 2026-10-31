# 企业深度研究数据源索引

本目录将企业深度研究的数据源规则按用途和分析板块拆分维护。原有业务规则、MQL 字段约束、过滤条件、资讯 query、Python 兜底口径均已按原文迁移，未改变业务含义。

## 验证入口

[固化 MQL 查询模板](mql-templates.md) 是运行时优先读取的模板索引，包含可替换变量、完整 MQL 样例和模板键。模板只替换企业代码、证券代码和日期，不重新生成路径、字段或过滤结构。

[MQL核验记录](mql-verification.json) 是模板状态和动态候选的核验记录；优先按键查看 `latest_template_checks` 本轮执行证据和 `current_blockers` 剩余问题，`queries`、`fixed_template_checks`、`rest_checks` 保留历史。不要整份加载。`ok=true` 只表示该条查询执行成功，不能推导整个板块完整通过；须结合实际返回类型、非空字段、主体和日期口径判断。

## 加载规则

- 先读取本文件，了解目录结构和统一执行要求。
- 所有任务都需要读取 `common.md`。
- 企业类型判定和板块路由前置取数读取 `enterprise-type.md`。
- 生成前 14 个原始数据板块时，只读取当前板块对应的数据源文件，不读取其它板块数据源文件。
- `重点关注`不取 MQL 原始数据，也不取资讯；读取 `key-concerns.md`，接收前 14 个板块已经生成的分析正文。
- 正文所有固定表格/图表统一按 [visual-assets.md](../visual-assets.md) 从对应独立数据包组装，不新增跨板块取数；组件只随其对应且最终保留的分析模块展示，未分析/未输出模块的组件也必须省略。一个组件内包含的多张图表/表格与独立编号组件按该文件区分。
- MQL、Python 兜底、内部审计、数据包边界和资讯处理的通用规则以 `common.md` 为准。
- 以下全部 15 个分析板块统一适用 [信源排序与模块输入截断](../news-processing.md)：最终完整 input 上限 16000 字符，按完整信源顺序截断；重点关注以完整前序模块分析结果为单元。无需在各板块 prompt 中重复或修改规则。

## 统一执行要求

固定模板已存在时，前 14 个原始数据板块的正式取数按以下顺序执行：

```text
识别变量 → render_mql_template.py → JSON 解码 → Execute_MQL
```

模板不存在、执行失败或字段版本变化时，才执行动态 MQL 工作流：

```text
Get_MQL_Reference → Search_Business_Knowledge → Search_Context → Execute_MQL
```

只有对应板块的正式 MQL 路径、已登记的同业务 MQL 候选和本次动态发现并验证的同业务 MQL 候选均失败、超时或关键字段缺失时，才允许使用该板块配置的 Python REST 兜底。`data-sources` 目录中的 REST 报表、URL 和字段列表，除非明确标注为 MQL 路径，否则只作为字段语义参考或兜底模板。

每个板块都必须形成独立的 `block_data_package` 和 `block_news_package`，只传入对应 prompt；板块之间不得混传。MQL 报表字段、过滤字段和指标参数必须以当前 `Search_Context` 与 Runtime 实际暴露的可绑定名称为准。

## 文件映射

| 用途/板块 | 文件 |
|---|---|
| 通用规则、输入包、内部审计、兜底要求 | `common.md` |
| 企业类型判定 | `enterprise-type.md` |
| 基本情况 | `basic-info.md` |
| 股东情况 | `shareholder.md` |
| 所处行业 | `industry.md` |
| 经营状况 | `operation.md` |
| ESG分析 | `esg.md` |
| 财务状况 | `financial-general.md` |
| 财务状况（债券发行人） | `financial-bond-issuer.md` |
| 发行概述 | `issuance-overview.md` |
| 定价分析（债券发行人） | `pricing-bond-issuer.md` |
| 定价分析（城投） | `pricing-urban-investment.md` |
| 科创能力 | `sci-tech-capability.md` |
| 偿债分析 | `solvency.md` |
| 信用分析 | `credit-analysis.md` |
| 司法风险 | `judicial-risk.md` |
| 重点关注 | `key-concerns.md` |

## 数据源章节状态

- `basic-info.md` 至 `judicial-risk.md`：前 14 个原始数据板块，按路由结果选择并逐板块取数、检索资讯、成文。
- `key-concerns.md`：固定收尾板块，只接收前 14 个板块的已生成分析结果，不创建新的 MQL 或资讯来源。
