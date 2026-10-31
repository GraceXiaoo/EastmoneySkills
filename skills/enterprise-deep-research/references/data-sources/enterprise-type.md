# 企业类型判定数据源

## 企业类型判定数据源

2026-09-20 已重新执行基础标签、ESG、城投专项及发债人非空到期日分支。状态与执行编号见 [MQL核验记录](mql-verification.json)。字段英文名用于规则解释，实际 MQL 使用下方中文运行时绑定字段名。

以下四类判断决定报告板块路径。规则已配置的判断项必须严格按本文执行；规则未配置前不得自行推断。

| 判断项 | 状态 | 判定口径 |
|---|---|---|
| 是否 ESG 范围 | MQL 主路径已配置；Python REST 兜底已配置 | MQL 查询中诚信绿金 ESG 评分指标，评分非空；REST 兜底查询 `RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS.ESG_SCORE` 非空 |
| 是否城投企业 | MQL 双条件已验证；Python REST 兜底已配置 | 两个条件必须同时满足：`TAG_CODE` 任一标签代码以 `003005` 开头，且“发行人发行债券类型”专项报表在 `信用主体代码=当前企业`、`筛选类型编码=1`、`是否剔除同业存单=1`、`到期日期>=系统日` 条件下返回有效 `筛选内容`；`IS_LFP` 仅作校验字段 |
| 是否科创企业 | MQL 主路径已配置；Python REST 兜底已配置 | 非城投路径下，MQL 实际字段 `TAG_CODE` 任一标签代码以 `003002` 开头；`TECH_FIELD`、`TECH_TITLE` 仅作补充字段 |
| 是否发债人 | MQL 非空到期日分支已实测；完整日期条件使用 Python REST 兜底 | 非城投路径下，先满足通用条件：MQL 实际字段 `SECUCODE_BJN` 非空且 `TAG_CODE` 不存在以 `003001` 或 `003005` 开头的标签；若专项报表存在白名单债券类型，还必须命中白名单；若全部类型均不在白名单内，则跳过专项限制并沿用通用条件 |

### MQL 判定执行流程（强制）

生成任何板块前，先执行企业类型判定 MQL 数据集。判定流程如下：

1. 用 `Search_Context` 识别企业实体，优先选发行人实体（typeCode 248，代码形如 `<机构代码>.FXR`），仅去除 .FXR 后缀，保留完整数字部分作为 `ORG_CODE`；若同时识别到股票/债券证券代码，记录为 ESG 候选证券代码。
2. 用 `Search_Context` 定位并优先使用 MQL 报表 `Choice报表\报表指标\Choice金融终端\企业F9\表头\企业F9_机构基本信息`，再用 `Execute_MQL` 按实际过滤字段 `公司代码 == <ORG_CODE>` 取回 `TAG_CODE`、`TAG_NAME`、`SECUCODE_BJN`、`SECUCODE_BJNZ`、`SECUCODE_BJNZ_ISSUER`、`SECUCODE_AS`、`SECUCODE_HKS`、`SECUCODE_USS`、`SECUCODE_BS`、`SECUCODE_ND`、`SECUCODE_BJW`、`SECUCODE_FD`、`IS_LFP`、`TECH_FIELD`、`TECH_TITLE`、`IS_ISSUE_OB`。
3. 执行已经验证的 `RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER` MQL 报表，实际路径为：
   `Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\信用债发行企业一页纸专项数据\发行人发行债券类型|RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER`。
   使用报表实际绑定字段 `信用主体代码`、`筛选类型编码`、`是否剔除同业存单`、`到期日期` 过滤，并读取 `筛选内容`。过滤条件为当前企业代码、`筛选类型编码=1`、`是否剔除同业存单=1`、`到期日期>=系统日`。返回的 `筛选内容` 必须非空且不能为 `-`、`NULL` 等占位符，才满足城投新增条件。该专项报表不追加未经运行验证的 `IS_GROUP` 条件，也不把 `到期日期`作为必须输出列。
4. 城投企业只有 `TAG_CODE` 命中 `003005` 且上述专项筛选结果非空时才判定为是；任一条件不满足均判定为否。科创和发债人判断必须使用这个最终城投标记。
5. 基于 MQL 实体识别结果和 `企业F9_机构基本信息` MQL 返回的证券代码字段，生成去重后的 ESG 候选代码列表；对股票代码查询股票口径中诚信绿金 ESG 评分指标，对 `<ORG_CODE>.FXR` 查询发行人口径中诚信绿金 ESG 评分指标。任一口径评分非空即判定 `is_esg_scope=true`。
6. 对非城投企业，再执行下方“发债人专项筛选”查询，使用发行人视角的 `发行人代码`，不要替换成城投查询的 `信用主体代码`。先执行正式 MQL 及其它同业务 MQL 候选；当前 Runtime 不能表达日期空值分支时，在这些候选均无法完整满足“到期日大于系统日或为空”的条件后，才对该专项数据集使用完整条件的 Python REST 兜底。到期日必须严格大于系统日或为空，当日到期不纳入。
7. 在查询完整且成功的前提下，按下方 12 类白名单精确匹配。命中一类即应用专项条件，并要求通用条件同时成立；全部类型不命中（或成功返回零行）则沿用通用条件。接口报错、日期分支不完整、字段缺失不能视为“全部不命中”；兜底仍失败时标为未完成，停止完整报告生成。
8. 将 MQL 判定结果整理为统一对象后再执行板块路由；不得让后续 prompt 在成文时重新判断企业类型。

企业类型判定输出对象建议固定为：

```json
{
  "judgement_path": "MQL",
  "org_code": "<机构代码>",
  "org_name": "<企业全称>",
  "tag_codes": ["..."],
  "secucode_bjn_values": ["..."],
  "urban_tag_match": true,
  "urban_bond_filter_match": true,
  "urban_bond_filter_rows": 1,
  "esg_secucode_candidates": ["..."],
  "esg_org": "中诚信绿金",
  "is_esg_scope": true,
  "is_urban_investment": false,
  "is_sci_tech": false,
  "is_bond_issuer": true,
  "sources": {
    "org_info_source_id": 1,
    "esg_source_id": 2
  }
}
```

若企业类型正式 MQL 路径、已验证候选和动态发现的同业务候选均失败，才允许运行 `scripts/get_data.py fetch --org <ORG_CODE>`。使用兜底结果时，将 `judgement_path` 记为 `Python REST fallback`，来源状态记为 `fallback`，并继续沿用本节同一套字段判定规则。

以下查询语义分别用于 ESG 范围判定和企业标签判定；MQL 执行时应先由 `Search_Context` 确认实际报表路径、字段名和过滤语法，再交给 `Execute_MQL` 执行。

### MQL 主路径速查（实测可用）

#### 城投、科创、发债人判定 MQL 模板

优先使用 Search_Context 已核对的 MQL 报表：
`Choice报表\报表指标\Choice金融终端\企业F9\表头\企业F9_机构基本信息`。
该报表加载列为 `公司代码`，主要返回列为 `概念标签代码`（TAG_CODE）、`概念标签名称`（TAG_NAME）、`最新发行债券(境内)`（SECUCODE_BJN）、`最新股票代码(A股)`（SECUCODE_AS）。`是否属于城投平台`、`科创称号`仅作辅助。下方为本次实际执行字段子集；其它证券候选及辅助字段按元数据返回的中文绑定字段名后追加。城投新增条件仍须单独执行专项筛选。

```mql
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\企业F9\表头\企业F9_机构基本信息});
SetReportFilter({公司代码} == "<ORG_CODE>");
{公司代码}: REPORT_FIELD("公司代码");
{公司名称}: REPORT_FIELD("公司名称");
{概念标签代码}: REPORT_FIELD("概念标签代码");
{概念标签名称}: REPORT_FIELD("概念标签名称");
{最新发行债券(境内)}: REPORT_FIELD("最新发行债券(境内)");
{最新股票代码(A股)}: REPORT_FIELD("最新股票代码(A股)");
{是否属于城投平台}: REPORT_FIELD("是否属于城投平台");
{科创称号}: REPORT_FIELD("科创称号");
{省份编码}: REPORT_FIELD("省份编码");
{省份}: REPORT_FIELD("省份");
{合合机构ID}: REPORT_FIELD("合合机构ID");

OutputBlock();
```

#### 城投新增专项筛选 MQL 查询（已验证）

`RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER` 是城投判定的第二个必要条件。用户截图中的
`/Choice金融终端/企业F9/企业一页纸/信用债发行企业一页纸专项数据` 是界面展示路径；
本项目已通过 MQL Runtime 验证的完整报表路径是：

```text
Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\信用债发行企业一页纸专项数据\发行人发行债券类型|RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER
```

当前已确认可用于过滤的运行时绑定字段为 `信用主体代码`、`筛选类型编码`、`是否剔除同业存单`、`到期日期`，已确认可读取的判定字段为 `筛选内容`。过滤字段不等同于返回列，不能把隐藏过滤字段强行写成 `REPORT_FIELD()` 输出列。

该查询使用以下字段：

| 逻辑字段 | 用途 |
|---|---|
| `信用主体代码` | 当前企业主体过滤 |
| `筛选内容` | 保留专项筛选内容，便于审计判定依据 |
| `筛选类型编码` | 固定筛选 `1` |
| `是否剔除同业存单` | 固定筛选 `1` |
| `到期日期` | 固定筛选系统日及以后 |

查询结构如下，系统日替换为执行当天的实际日期：

```mql
ReportBlock(#2, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\信用债发行企业一页纸专项数据\发行人发行债券类型|RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER});
SetReportFilter(
    ({信用主体代码} == "<ORG_CODE>")
    AND ({筛选类型编码} == "1")
    AND ({是否剔除同业存单} == "1")
    AND ({到期日期} >= "<系统日 YYYY-MM-DD>")
);
{筛选内容}: REPORT_FIELD("筛选内容");
OutputBlock();
```

该脚本已在 `ORG_CODE=10000158441`、系统日 `2026-09-20` 的运行中返回 3 条有效 `筛选内容`。`到期日期`用于过滤即可，不要将它作为 `REPORT_FIELD()` 输出列。MQL 返回零行，或返回内容为空、`-`、`NULL` 等占位符时，均视为新增条件不满足。

字段判定关系：

| 本地标记 | MQL 主判定字段 | 判定规则 | 辅助/校验字段 |
|---|---|---|---|
| `is_urban_investment` | `TAG_CODE` + “发行人发行债券类型”专项筛选结果 | `TAG_CODE` 命中 `003005` 且专项报表在 `信用主体代码=当前企业`、`筛选类型编码=1`、`是否剔除同业存单=1`、`到期日期>=系统日` 后返回有效 `筛选内容` 时才为 `true`；任一条件不满足则为 `false` | `IS_LFP` 仅作校验，不覆盖双条件主判定 |
| `is_sci_tech` | `TAG_CODE` | 非城投路径下，任一代码以 `003002` 开头则为 `true` | `TECH_FIELD`、`TECH_TITLE` 可进入科创能力板块底稿 |
| `is_bond_issuer` | `SECUCODE_BJN` + `TAG_CODE` + 发债人专项报表 | 非城投路径下，先满足 `SECUCODE_BJN` 非空且标签代码不存在 `003001`、`003005` 前缀；若专项报表存在白名单债券类型，则还必须有白名单精确命中；若全部类型均不在白名单内，则专项逻辑不适用，直接沿用通用条件 | `SECUCODE_BJNZ`、`SECUCODE_BJNZ_ISSUER`、`IS_ISSUE_OB` 作交叉校验 |

若 `TAG_CODE` 与辅助字段方向冲突，应以 `TAG_CODE` 和专项筛选结果的双条件主判定为准，并在来源登记 `notes` 中记录冲突字段；不得临时改用 `IS_LFP` 或其它辅助字段覆盖路由。

#### 发债人专项筛选（2026-09-20 实测）

报表路径与城投专项相同，但过滤口径不同。该报表元数据的 `typeCodes=[]`；若按发行人类型 `248` 检索不到，补调不限定类型的 `Search_Context`，检索 `发行人发行债券类型`、`筛选内容`，不要猜测字段。

| 用途 | MQL 实际名称 | REST 字段 |
|---|---|---|
| 当前发行人过滤 | 发行人代码 | ORG_CODE |
| 不展示集团债券 | 集团系，固定字符串 `0` | IS_GROUP |
| 债券类型筛选 | 筛选类型编码，固定字符串 `1` | FILTER_TYPE_CODE |
| 剔除同业存单 | 是否剔除同业存单，固定字符串 `1` | INTERBANK_DEPO |
| 存续条件 | 到期日期，严格大于系统日或为空 | EXPIRE_DATE |
| 返回债券类型 | 筛选内容 | FILTER_CONTENT |
| 返回主体（可选） | 公司代码 | ORG_CODE |

`发行人代码`是过滤名称，不能写成 `REPORT_FIELD("发行人代码")`；隐藏过滤字段也不能强行输出。MQL 非空到期日分支已执行成功：

```mql
ReportBlock(#3, {Choice报表\报表指标\Choice金融终端\企业F9\企业一页纸\信用债发行企业一页纸专项数据\发行人发行债券类型|RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER});
SetReportFilter(
    ({发行人代码} == "<ORG_CODE>")
    AND ({集团系} == "0")
    AND ({筛选类型编码} == "1")
    AND ({是否剔除同业存单} == "1")
    AND ({到期日期} > "<系统日 YYYY-MM-DD>")
);
{筛选内容}: REPORT_FIELD("筛选内容");
OutputBlock();
```

白名单：短期融资券、超短期融资券、中期票据、集合票据、项目收益票据、定向工具(PPN)、一般公司债、项目收益专项债、私募公司债、一般企业债、项目收益债、中小企业集合债。精确匹配，任一命中即可；不通过模糊包含匹配扩充范围。

当前 Runtime 为 `2.5.0`，MQL 工具要求 `2.6.0`，建议升级后复测。已实测 `SetReportFilter` 不接受 `== NULL`，`== "NULL"` 也因日期类型不匹配失败；而该报表不返回到期日期，不能在 MQL 返回后补筛空日期。不得删除日期条件后把历史债券类型当作存续债券，亦不得把以上部分查询标为完整判定。当前应在正式 MQL 和其它同业务 MQL 候选尝试后，仅对本专项使用以下已实测的完整 REST 条件兜底：

```text
reportName=RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER
columns=ORG_CODE,FILTER_CONTENT
filter=(ORG_CODE="<ORG_CODE>")(IS_GROUP="0")(FILTER_TYPE_CODE="1")(INTERBANK_DEPO="1")((EXPIRE_DATE>'<系统日 YYYY-MM-DD>')(|EXPIRE_DATE="NULL"))
pageNumber=1&pageSize=200&source=CHOICE&client=SW
```

REST 日期值用单引号；OR 写在第二个条件括号内。通过结构化参数编码 URL。仅请求两个真实返回字段，其他字段仅作过滤；日期过滤必须在接口聚合债券类型前完成。接口业务码 `9201` 表示正常无数据；`9501` 等参数错误或请求失败必须标记失败，不能按空结果回退通用判断。

实测系统日 `2026-09-20`，MQL 执行编号 `59d3cf62-8afa-4c8d-9cbb-1de13c1cb67f`：

| 企业 | MQL 非空到期日分支返回 | 专项结论 |
|---|---|---|
| 中国石油天然气集团有限公司（10010954） | 海外债、中期票据、一般公司债、一般企业债 | 3 类命中，混合类型仍命中专项 |
| 中国民生银行股份有限公司（10002264） | 永续债、信贷ABS、二级资本债、商业银行普通债 | 全部不命中，完整查询成功后沿用通用判断 |

本地 Python 兜底脚本以完整 REST 条件实测：中石油返回 4 类、白名单命中 3 类；民生银行返回 4 类、白名单命中 0 类，与上述 MQL 非空到期日分支一致。编译、skill 格式校验及 11 项判定/过滤检查通过，覆盖混合类型、全部不命中、标签排除、正常空结果、当日到期排除及接口失败阻止路由。该记录验证专项取数与白名单匹配，不替代 `TAG_CODE`、`SECUCODE_BJN` 等通用条件核验；真实空到期日命中样本尚未取得。

本轮基础标签核验：民生银行虽有境内债券代码，但 `TAG_CODE` 含 `003001` 前缀，按用户通用规则不进入一般发债人路径；专项全不命中不能覆盖标签排除。茅台 `TAG_CODE=0030020004`，按用户规则属于科创路径，不按行业印象推翻标签。

#### ESG 范围判定 MQL 模板

MQL 主路径优先查询中诚信绿金 ESG 评分指标。股票代码存在时先查股票口径；发行人代码存在时同时查发行人口径。两个口径任一返回非空评分，即判定在 ESG 范围内。

```mql
CrossSectionBlock(#1, {EM_CODE});
SetCodes(["<股票代码，如 600519.SH>"]);
{证券代码}: {Choice指标\股票\沪深京股票指标\基本资料\证券资料\股票代码}();
{证券简称}: {Choice指标\股票\沪深京股票指标\基本资料\证券资料\股票简称}();
{中诚信绿金ESG评分}: {Choice指标\股票\沪深京股票指标\ESG\中诚信绿金ESG评分}();
{中诚信绿金ESG评级}: {Choice指标\股票\沪深京股票指标\ESG\中诚信绿金ESG评级}();
OutputBlock();

CrossSectionBlock(#2, {EM_CODE});
SetCodes(["<ORG_CODE>.FXR"]);
{中诚信绿金ESG评分}: {Choice指标\发行人\企业全部指标\评级分析\ESG评级\中诚信绿金ESG评分}();
{中诚信绿金ESG评级}: {Choice指标\发行人\企业全部指标\评级分析\ESG评级\中诚信绿金ESG评级}();
OutputBlock();
```

ESG 判定关系：

| 本地标记 | MQL 主判定指标 | 判定规则 | REST 兜底字段 |
|---|---|---|---|
| `is_esg_scope` | `中诚信绿金ESG评分` | 股票口径或发行人口径任一评分非空则为 `true`；`0` 是有效值 | `RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS.ESG_SCORE` |

2026-09-20 复测茅台股票与发行人两种口径，均返回中诚信绿金评分 76.68，执行编号 `504f392a-d633-402f-b30c-e092694868a8`。评分指标为空但明细可取时，可按 [ESG数据源](esg.md) 的固定机构明细查询核验；不能将接口失败当作无评分。

### ESG 范围判定查询

ESG 范围判断主路径必须用 MQL MCP 执行，优先使用上方中诚信绿金 ESG 评分指标。下方 REST 参数仅作为 Python 兜底模板，不得在 MQL 可用时跳过 MQL 直接拼 REST URL。

该判断使用用户提供的 `RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS` 接口。该接口为多表关联查询，`columns` 中必须保留关联字段写法 `SNAME,@ORG_CODE;@ORG_CODE,ORG_NAME`，不要改成普通单表字段列表。

候选证券代码来源：

- 优先使用 MQL 实体识别返回的目标企业证券代码；若识别到发行人实体代码形如 `<机构代码>.FXR`，可直接作为 ESG 查询的 `SECUCODE` 候选。
- 补充使用 `企业F9_机构基本信息` 的 MQL 返回字段：`优先证券代码`、`最新股票代码(A股)`、`最新股票代码(港股)`、`最新股票代码(美股)`、`最新股票代码(B股)`、`最新股票代码(新三板)`、`最新发行债券(境内)`、`最新发行债券(境外)`、`最新发行债券`、`最新债券(补充发行人)`、`重要基金代码`。
- Python 兜底时从 `RPT_COP_ORG_INFO` 读取 `SECUCODE_PRI`、`SECUCODE_AS`、`SECUCODE_HKS`、`SECUCODE_USS`、`SECUCODE_BS`、`SECUCODE_ND`、`SECUCODE_BJN`、`SECUCODE_BJW`、`SECUCODE_BJNZ`、`SECUCODE_BJNZ_ISSUER`、`SECUCODE_FD` 等字段，并补充 `<ORG_CODE>.FXR` 作为发行人候选。
- 多个候选按去重后的顺序逐一查询，评级机构名称固定传 `中诚信绿金`；任一候选命中非空 `ESG_SCORE` 即判定在 ESG 范围中。

规范化查询：

```text
reportName=RPT_ESG_IS_SECUINDU;RPT_ESG_IS_DETAILS
columns=SECUCODE,SECURITY_CODE,SNAME,@ORG_CODE;@ORG_CODE,ORG_NAME,USCC,INDUSTRY,INDUSTRY_CODE,INDUSTRY_TYPE,INDUSTRY_TYPE_CODE,ESG_ORG,UPDATEDATE,ESG_STDSCORE,ESG_SCORE,ESG_RATING,E_SCORE,E_RATING,S_SCORE,S_RATING,G_SCORE,G_RATING,ESG_MANAGE_SCORE,ESG_RA_SCORE,SOURCE_TYPE,SECUCODE2,ESG_RATING_T
filter=(SECUCODE="<SECUCODE>");(ORG_CODE="")(UPDATEDATE>='1900-01-01')(UPDATEDATE<='<系统日 yyyy-MM-dd>')(INDUSTRY_TYPE_CODE="0203")(ESG_ORG="中诚信绿金")
sortColumns=UPDATEDATE&sortTypes=-1&pageNumber=1&pageSize=1&client=SW&source=choice
```

判定细则：

- `ESG_ORG` 固定为 `中诚信绿金`，不得为了命中数据自动切换为其它评级机构。
- `ESG_SCORE` 是 ESG 范围判断的主判定字段。字段存在且去除空白后非空时，即视为有 ESG 评分，判定为在 ESG 范围中；`0` 是有效值，不得按空值处理。
- 仅返回空行，或 `ESG_SCORE` 为 `null`/空字符串时，不自动进入 ESG 板块，应记录为 ESG 明细不完整。`ESG_STDSCORE` 可作为 ESG 分析板块的补充字段，但不再作为是否进入 ESG 范围的主判定字段。
- 命中 ESG 范围后，ESG 分析板块可使用同一条最新记录中的 `ESG_SCORE`、`ESG_STDSCORE`、`ESG_RATING`、`E_SCORE`、`S_SCORE`、`G_SCORE`、`ESG_MANAGE_SCORE`、`ESG_RA_SCORE`、`UPDATEDATE`、`ESG_ORG`、行业排名/均值等字段成文。
- 若多个候选证券代码都返回有效评分，优先采用 `UPDATEDATE` 最新的记录；日期相同则优先采用 MQL 识别的目标证券代码，其次 `<ORG_CODE>.FXR`，再其次 `企业F9_机构基本信息` 中的证券代码字段顺序。

### REST 兜底：企业类型判定通用查询

城投、科创、发债人三类判断主路径必须用 MQL MCP 查询 `企业F9_机构基本信息`；城投还必须查询
`RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER` 对应的 MQL 报表。下方 REST 参数仅作为 Python REST
兜底模板，不得在 MQL 可用时跳过 MQL 直接拼 REST URL。

用户提供的参考 URL 中，`columns` 后多出的引号会形成错误参数 `"eColumns`，末尾的 `TAG_CODE='003005%'`、`TAG_CODE='003002%'`、`SECUCODE_BJN 不为空` 是人工批注，不应原样拼接进 URL，也不应原样写入 MQL 过滤条件。规范化后的查询应先按机构代码取回 `RPT_COP_ORG_INFO`，再基于 MQL 返回字段做前缀判断：

```text
reportName=RPT_COP_ORG_INFO
columns=ORG_CODE,ORG_NAME,TAG_CODE,TAG_NAME,SECUCODE_BJN,SECUCODE_BJNZ,SECUCODE_BJNZ_ISSUER,SECUCODE_PRI,SECUCODE_AS,SECUCODE_HKS,SECUCODE_USS,SECUCODE_BS,SECUCODE_ND,SECUCODE_BJW,SECUCODE_FD
filter=(ORG_CODE="<ORG_CODE>")
pageNumber=1&pageSize=200&sortTypes=&sortColumns=
```

城投新增专项筛选的 Python 兜底模板如下。该接口实际稳定返回 `ORG_CODE` 和 `FILTER_CONTENT`，隐藏过滤字段可能不出现在响应中；因此 Python 兜底只把固定过滤条件写入请求，并要求返回有效 `FILTER_CONTENT`：

```text
reportName=RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER
columns=ORG_CODE,FILTER_CONTENT,FILTER_TYPE_CODE,INTERBANK_DEPO
filter=(ORG_CODE="<ORG_CODE>")(FILTER_TYPE_CODE="1")(INTERBANK_DEPO="1")
sortColumns=&sortTypes=&pageNumber=1&pageSize=200&source=choice&client=SW
```

上方城投兜底模板保持原口径，不追加 `IS_GROUP`、`EXPIRE_DATE` 或未经验证的中文过滤字段。若接口实际返回可解析的 `EXPIRE_DATE`，才在本地删除早于系统日的记录；若未返回该字段，则以有效 `FILTER_CONTENT` 作为专项条件结果，不自行推断到期日期。这一限制不适用于发债人专项；发债人必须使用前文已验证的完整发行人过滤条件。

REST 兜底路径中，接口已验证支持 `SECUCODE_BJN<>''`，但不支持 `TAG_CODE like '003005%'`，`TAG_CODE='003005%'` 也不是合法前缀查询。因此标签类判断统一采用“通过 MQL 或 REST 取回 `TAG_CODE` 后按前缀判断”的方式，不把 `%` 条件写入 MQL 或 REST 过滤。

判定细则：

- 城投企业：先将 `TAG_CODE` 按逗号、分号、顿号、竖线、空白等分隔为标签代码列表；只有标签代码任一以 `003005` 开头，且专项报表按 `FILTER_TYPE_CODE=1`、`INTERBANK_DEPO=1` 取回后存在有效 `FILTER_CONTENT` 时，才判定为是。`FILTER_CONTENT` 为空、`-`、`NULL` 等占位符时不算命中。任一条件不满足则为否。
- 科创企业：仅在非城投路径判断；任一 `TAG_CODE` 以 `003002` 开头则为是，否则为否。
- 发债人：仅在非城投路径判断；先要求 `SECUCODE_BJN` 去空白后非空且 `TAG_CODE` 中没有以 `003001` 或 `003005` 开头的代码。若专项报表返回至少一条白名单债券类型，还必须存在白名单精确命中；若返回结果全部不属于白名单，则忽略专项限制并沿用通用条件。一只债券命中白名单即可，不要求全部债券命中。
- `TAG_CODE` 字段存在但值为 `null` 或空字符串时，视为未命中上述标签；若字段本身缺失、`ORG_CODE` 不匹配或查询失败，则该判断不可用，应先用正式 MQL 和同业务候选补取；全部 MQL 候选仍失败时再用 Python REST 兜底；兜底仍失败则停止完整报告生成。

