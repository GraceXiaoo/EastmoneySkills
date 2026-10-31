# 所处行业数据源

状态：MQL 指定两字段已执行成功（2026-09-20）。执行编号及边界见 [MQL核验记录](mql-verification.json)。本文件中的 MQL 使用 MQL Runtime 实际绑定字段名；英文物理列名只用于来源映射和 REST。

## 数据来源

用户路径：`/Choice金融终端/企业F9/企业一页纸/基本信息`。实际报表与基本情况相同；使用无函数后缀路径。
过滤使用 `公司代码`，输出严格限定为 `行业`（物理列 `GBGI_INDUSTRY`）与 `省份`（`PROVINCE_NAME`）。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\智能发行人\工商信息\工商信息});
SetReportFilter(({公司代码} == "<ORG_CODE>"));
{行业}: REPORT_FIELD("行业");
{省份}: REPORT_FIELD("省份");

OutputBlock();
```

## 整理与隔离

独立形成所处行业的 `block_data_package`，只传给 `references/analysis-prompts/industry.md`。展示时将 `行业` 写为“国民经济行业”或“所属行业”，不把此展示别名反写进 MQL。不得传入完整基本信息、公司简介或经营范围。无报告期的静态信息记录实际抓取日期。

#### `{{资讯}}` mx-finance-search 查询

所处行业板块的 `{{资讯}}` 必须使用 `mx-finance-search`，query 格式固定为：

```text
<企业全名> 相关资讯 最新动态
```

示例：

```text
中国民生银行股份有限公司 相关资讯 最新动态
```

资讯结果整理为当前板块专属 `block_news_package`，只传入 `industry.md` 的 `{{资讯}}`。优先保留与企业所处行业、行业政策、区域环境、经营动态和近期舆情相关的公告、研报和新闻；不得将该资讯包传给其它板块。

`block_news_package` 登记要求：

```json
{
  "block_name": "所处行业",
  "prompt_file": "references/analysis-prompts/industry.md",
  "news_queries": [
    {
      "query": "<企业全名> 相关资讯 最新动态",
      "tool": "mx-finance-search",
      "purpose": "行业背景、区域环境、近期动态和舆情补充"
    }
  ],
  "sources": [
    {
      "block": "所处行业",
      "placeholder": "{{资讯}}",
      "path": "mx-finance-search",
      "dataset": "<企业全名> 相关资讯 最新动态",
      "status": "ok"
    }
  ]
}
```

#### Python REST 兜底

仅当所处行业板块正式 MQL 路径、已登记或动态发现的同业务 MQL 候选均失败、超时或关键字段缺失时，才允许使用下方企业画像表作为 Python REST 兜底模板：

```text
reportName=RPT_COP_ORG_INFO
columns=ORG_CODE,ORG_NAME,GBGI_INDUSTRY,PROVINCE_NAME,PROVINCE_CODE,AREA
filter=(ORG_CODE="<ORG_CODE>")
pageNumber=1&pageSize=1&sortTypes=1&sortColumns=ORG_CODE&source=CHOICE&client=SW
```

兜底字段映射：

| REST 字段 | 传入 `industry.md` 的字段 |
|---|---|
| `GBGI_INDUSTRY` | `国民经济行业` / `所属行业` |
| `PROVINCE_NAME` | `省份` |
| `AREA` | 仅当 `PROVINCE_NAME` 为空时，用作省份/区域补充 |

Python 兜底结果必须裁剪为所处行业板块自己的 `block_data_package`，`placeholder` 标记为 `{{数据}}`，最终只包含行业和省份相关字段；不得把 `RPT_COP_ORG_INFO` 的完整行、公司简介、经营范围或其它基本情况字段传入 `industry.md`。

