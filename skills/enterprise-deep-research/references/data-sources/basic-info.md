# 基本情况数据源

状态：已固化为 `basic_noid_cn`，只替换 `ORG_CODE`。2026-09-30 使用渲染后的原样 MQL 复测民生银行成功，返回1行、19列，执行编号 `b4704b03-6547-484d-b730-7b5b315908d5`。证据见 [MQL核验记录](mql-verification.json)。MQL 使用 Runtime 实际绑定字段名；英文物理列名只用于来源映射和 REST。

## 数据来源

用户路径：`/Choice金融终端/企业F9/企业一页纸/基本信息`。实际报表为下方模板的工商信息报表。按实体识别返回的完整机构代码过滤，不限制 8 位；不使用 `SetCodes`。

该路径在当前 Runtime 不带 `|RPT_COP_ORG_INFO` 后缀才能正确绑定。过滤名称为 `公司代码`；不能把英文物理名 `ORG_CODE` 直接写入 MQL。

读取该表全部实际返回字段，当前共 19 列；若本次元数据新增列，应一并读取。不把此查询缩减为机构表中的少量评级或标签字段。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\智能发行人\工商信息\工商信息});
SetReportFilter(({公司代码} == "<ORG_CODE>"));
{第一大竞争对手}: REPORT_FIELD("第一大竞争对手");
{成立日期}: REPORT_FIELD("成立日期");
{行业}: REPORT_FIELD("行业");
{是否属于城投平台}: REPORT_FIELD("是否属于城投平台");
{是否上市公司}: REPORT_FIELD("是否上市公司");
{集团主公司名称}: REPORT_FIELD("集团主公司名称");
{公司代码}: REPORT_FIELD("公司代码");
{公司代码带后缀}: REPORT_FIELD("公司代码带后缀");
{企业性质(全部)}: REPORT_FIELD("企业性质(全部)");
{公司名称}: REPORT_FIELD("公司名称");
{公司简介}: REPORT_FIELD("公司简介");
{省份}: REPORT_FIELD("省份");
{注册地址}: REPORT_FIELD("注册地址");
{注册资本(万元)}: REPORT_FIELD("注册资本(万元)");
{经营范围}: REPORT_FIELD("经营范围");
{实际控制人}: REPORT_FIELD("实际控制人");
{统一社会信用代码}: REPORT_FIELD("统一社会信用代码");
{发行股票}: REPORT_FIELD("发行股票");
{第一大股东(持股比例)}: REPORT_FIELD("第一大股东(持股比例)");

OutputBlock();
```

## 整理与隔离

形成基本情况独立 `block_data_package`，只传给 `references/analysis-prompts/basic-info.md` 的 `{{数据}}`。保留主体、抓取日期、原始字段和单位，例如 `注册资本(万元)`。结果整理为键值表，不擅自改变金额单位。所处行业可复用同源查询，但必须另建只含行业、省份的字段子集，不能传入整表。

#### `{{资讯}}` mx-finance-search 查询

基本情况板块的 `{{资讯}}` 必须使用 `mx-finance-search`，query 格式固定为：

```text
<企业全名> 相关资讯 最新动态
```

示例：

```text
中国民生银行股份有限公司 相关资讯 最新动态
```

资讯结果整理为当前板块专属 `block_news_package`，只传入 `basic-info.md` 的 `{{资讯}}`。优先保留资讯类型、标题、发布时间、来源、权威度和正文/摘要；不得将该资讯包传给其它板块。

`block_news_package` 登记要求：

```json
{
  "block_name": "基本情况",
  "prompt_file": "references/analysis-prompts/basic-info.md",
  "news_queries": [
    {
      "query": "<企业全名> 相关资讯 最新动态",
      "tool": "mx-finance-search",
      "purpose": "企业最新动态、公告、研报和相关新闻补充"
    }
  ],
  "sources": [
    {
      "block": "基本情况",
      "placeholder": "{{资讯}}",
      "path": "mx-finance-search",
      "dataset": "<企业全名> 相关资讯 最新动态",
      "status": "ok"
    }
  ]
}
```

#### Python REST 兜底

仅当基本情况板块正式 MQL 路径、已登记或动态发现的同业务 MQL 候选均失败、超时或关键字段缺失时，才允许使用下方已验证通用企业画像表作为 Python REST 兜底模板：

```text
reportName=RPT_COP_ORG_INFO
columns=ORG_CODE,ORG_NAME,SOCIAL_CREDIT_CODE,FOUND_DATE,REG_ADDRESS,REG_CAPITAL,ORG_FORM_1LEVEL,GBGI_INDUSTRY,SCOPE,ORG_PROFILE,COMPETITOR,IS_LISCOM,STOCKGLANCE_NEW,SJKZR,TOP1_HOLDER_ST,IS_LFP,MAIN_ORG_NAME,IS_ST,IS_ZJTX,IS_DJSQY,PROVINCE_NAME,PROVINCE_CODE,ORG_INNER_CODE
filter=(ORG_CODE="<ORG_CODE>")
pageNumber=1&pageSize=&sortTypes=1&sortColumns=ORG_CODE&source=CHOICE&client=SW
```

兜底常用字段：`ORG_NAME`、`SOCIAL_CREDIT_CODE`、`FOUND_DATE`、`REG_ADDRESS`、`REG_CAPITAL`、`ORG_FORM_1LEVEL`、`GBGI_INDUSTRY`、`SCOPE`、`ORG_PROFILE`、`IS_LISCOM`、`IS_LFP`、`SJKZR`、`TOP1_HOLDER_ST`、`PROVINCE_NAME`。Python 兜底结果也必须拆成基本情况板块自己的 `block_data_package`，`placeholder` 标记为 `{{数据}}`，不得直接把全局 JSON 底稿传入 prompt。

