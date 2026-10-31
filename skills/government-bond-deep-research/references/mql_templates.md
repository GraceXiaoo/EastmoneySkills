# MQL 取数模板（地方债skill）

本文件收录【地方债skill】的全部已验证 MQL 取数模板与已知卡点。所有模板均通过 MQL MCP 的 `Execute_MQL` 实测。

## 一、已验证的真实债券样本

| 债券代码 | 债券简称 | 标签 | 存续状态 |
|---|---|---|---|
| 2605149.IB | 26湖北债19 | 地方政府债 | 存续 |
| 104501.IB | 19海南债01 | 地方政府债 | 到期 |
| 199333.IB | 25广东债41 | 地方政府债 | 存续 |
| 102680471.IB | 26长沙城投MTN001 | 城投债 | 存续（发行人代码 10078059.FXR） |
| 2620007.IB | 26苏州银行01 | 银行金融机构债 | 存续 |
| 1620007.IB | 16泉州银行二级 | 银行金融机构债 | 到期（发行人 泉州银行，ORG_CODE 10058582，发行 2016-01-28，到期 2021-01-29） |
| 137514.SH | 22华福G4 | 非银金融机构债 | 存续 |
| 115067.SH | 交筑YK01 | 科创债 | 到期 |
| 222500006.IB | 25渤海银行绿债01 | 银行+绿色（双标签） | 存续（发行人 渤海银行，ORG_CODE 10068138） |
| 1620036.IB | 16江西银行绿色金融04 | 银行+绿色（双标签） | 到期 |
| 112799.SZ | 18苏宁06 | 无标签（全否） | — |

## 二、MQL 调用前置规则

1. 首次检索前必须先调用 `Get_MQL_Reference`（一次即可）。
2. 再调用 `Search_Business_Knowledge`（传 varieties=["债券"]、user_query、keywords、query_rewrites）。
3. 首次 `Search_Context` 必须全量传入上一步返回的全部 typeCodes。
4. 后续 `Search_Context` 补调可直接基于前序结果，用 `searchIndicator.keys` 精确检索报表。
5. 最终用 `Execute_MQL` 执行。

## 三、报表取数通用结构（ReportBlock）

```mql
ReportBlock(#1, {报表路径});
SetCodes("{债券代码}");            // 仅当 reportStandardCodeSupported=true，必须且只能写一个
SetReportFilter( {中文列名} == "值" );  // 仅当 reportStandardCodeSupported=false，用 filterColumns 中文名，位于输出列之前
{输出别名}: REPORT_FIELD("报表字段中文名");  // 每句末尾必须有分号
```

- `reportStandardCodeSupported=true`：只能写 SetCodes，禁止再写代码列的 SetReportFilter。
- `reportStandardCodeSupported=false`：禁止 SetCodes，改用 SetReportFilter。
- 日期 filter 值用 `"yyyy-MM-dd"` 字符串。
- **债券标签、AI研究员搜索报表一次 SetCodes 多只只返回第一只，必须逐只循环调用。**

## 四、标签判定模板

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\债券标签\债券标签});
SetCodes("{债券代码}");
{是否地方政府债}: REPORT_FIELD("是否地方政府债(AI用)");
{是否银行}: REPORT_FIELD("是否银行金融机构债(AI用)");
{是否非银}: REPORT_FIELD("是否非银金融机构债(AI用)");
{是否城投}: REPORT_FIELD("是否城投债(东财口径)(AI用)");
{是否科创}: REPORT_FIELD("是否科创债(AI用)");
{是否绿色}: REPORT_FIELD("是否绿色债(AI用)");
{是否存续}: REPORT_FIELD("是否存续");
{省市}: REPORT_FIELD("省市(计划单列市）");
{省市代码}: REPORT_FIELD("省市代码(计划单列市）");
```

## 五、各标签核心报表模板

### 5.1 存续地方债（跳过 发行期限(年)）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\地方债\存续地方债\存续地方债});
SetCodes("{债券代码}");
{债券简称}: REPORT_FIELD("债券简称");
{债券代码}: REPORT_FIELD("债券代码");
{票面利率}: REPORT_FIELD("票面利率(当期参考)");
{最新估价收益率}: REPORT_FIELD("最新估价收益率");
{剩余期限}: REPORT_FIELD("剩余期限(年)");
{与国债利差}: REPORT_FIELD("与国债利差(BP)");
{与国开债利差}: REPORT_FIELD("与国开债利差(BP)");
{同期限国债收益率}: REPORT_FIELD("同期限国债收益率");
{同期限国开债收益率}: REPORT_FIELD("同期限国开债收益率");
{募集资金用途}: REPORT_FIELD("募集资金用途");
{GDP}: REPORT_FIELD("GDP");
{CPI}: REPORT_FIELD("CPI");
{PMI}: REPORT_FIELD("PMI");
{最新OMO利率}: REPORT_FIELD("最新OMO利率");
{MLF利率}: REPORT_FIELD("1年期MLF利率");
```

### 5.2 到期地方债（跳过 发行期限(年)）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\地方债\到期地方债\到期地方债});
SetCodes("{债券代码}");
{债券简称}: REPORT_FIELD("债券简称");
{债券代码}: REPORT_FIELD("债券代码");
{发行人全称}: REPORT_FIELD("发行人全称");
{票面利率}: REPORT_FIELD("票面利率(发行参考)");
{发行规模}: REPORT_FIELD("发行规模(亿元)");
{发行起始日期}: REPORT_FIELD("发行起始日期");
{实际到期日}: REPORT_FIELD("实际到期日");
{持有期年化回报率}: REPORT_FIELD("持有期年化回报率(%)");
{持有期累计票息}: REPORT_FIELD("持有期累计票息收入（每百元）");
{最终估价全价}: REPORT_FIELD("最终估价全价");
{全场倍数}: REPORT_FIELD("全场倍数");
{认购倍数}: REPORT_FIELD("认购倍数");
{实际兑付情况}: REPORT_FIELD("实际兑付情况");
{还本付息方式}: REPORT_FIELD("还本付息方式");
{存续期最高收益率}: REPORT_FIELD("存续期间估值收益率最高值");
{存续期最低收益率}: REPORT_FIELD("存续期间估值收益率最低值");
```

### 5.13 到期地方债区域财政经济数据（STD=false）

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\债券一页纸\地方债\到期地方债\到期地方债区域财政经济数据});
SetReportFilter(
    {地区编码} == "{省市代码}"
);
{地区编码}: REPORT_FIELD("地区编码");
{报告期}: REPORT_FIELD("报告期");
{GDP}: REPORT_FIELD("GDP(亿元)");
{一般公共预算收入}: REPORT_FIELD("一般公共预算收入(亿元)");
{政府基金性收入}: REPORT_FIELD("政府基金性收入");
{地方政府债务余额}: REPORT_FIELD("地方政府债务余额(亿元)");
{负债率}: REPORT_FIELD("负债率(%)");
```

## 六、RAG 文本搜索示例

```text
mx_finance_search_news:
  query = "{发行人名称} {债券简称} {标签特征} 近30天 新闻 研报 评级观点 市场讨论"

mx_finance_search_notice:
  query = "{发行人名称} {债券简称} 募集说明书 发行公告 评级报告 兑付公告 {年份}"
```

返回结构化表格：标题、摘要、发布时间、来源、跳转链接。

## 七、已知卡点速查

| 报表 | 状态 | 处理 |
|---|---|---|
| 存续/到期地方债 | 可用 | 跳过字段「发行期限(年)」 |
| 到期地方债区域财政经济数据 | STD=false | SetReportFilter 传 地区编码(省市代码)，多期取最新报告期 |
