# 发行概述数据源

### 8. 发行概述

#### 存续债券为空时的路由规则

本板块的发行一览结果同时承担债券存续状态判断。完成跨市场去重、排除同业存单并保留 `到期日期 >= 系统日` 的记录后：

- 查询成功且结果为空，视为本次无可用存续债券。此时不生成“发行概述”和“偿债分析”两个板块；其他已选板块继续按原顺序生成。
- 查询失败、超时、关键字段无法绑定或 MQL 与 Python 兜底均失败时，存续状态为未知，不得当作无债券；路由仍保留这两个板块，具体正文按各板块有效材料处理。
- 到期日等于系统日的债券仍属于有效存续债券。

该状态只用于内部路由，不在正式报告正文中输出“债券已到期”“跳过章节”等技术或过程说明。路由完成后，最终章节编号按实际输出章节重新连续排列。

#### 发行概述表格组件

正文后生成“图表N 发行概述”债券明细表，字段顺序固定为：债券代码、债券简称、债券类型、债券余额、币种、发行日期、到期日期、剩余期限、最新债项评级、最新主体评级、票面利率、信用主体、所属集团。字段对应本文件上述发行一览字段映射，所有列只展示 MQL 实际返回的值；余额、期限、利率依原始单位标注。该表只属于发行概述板块，采用去重后的存续债明细；查询成功但无有效债券时依路由规则跳过表格。

状态：已配置板块口径；正式运行仍必须先经 MQL MCP 的 `Get_MQL_Reference → Search_Business_Knowledge → Search_Context → Execute_MQL` 核对实际可绑定的报表字段名和过滤字段。该板块只形成自己的 `issuance_overview` 数据包，不能把债券原始全量数据直接传给其他板块。

#### 8.1 MQL 主路径与候选报表

用户确认的业务路径为 `/服务端/妙想服务/量化查数/债券/企业F9/发行一览`，对应主报表 `RPT_CUSTOM_BOND_BS_SAMEISSUER`。历史已召回的完整 MQL 路径为 `Choice报表\报表指标\服务端\妙想服务\量化查数\债券\企业F9\发行一览\发行债券|RPT_CUSTOM_BOND_BS_SAMEISSUER`；业务路径用于检索定位，不能自行拼接为可执行路径。

用户确认字段语义：`ISSUE_CODE` 为发行人代码，`ISSUE_NAME` 为发行人名称。主体过滤必须绑定 `ISSUE_CODE` 对应的实际 MQL 字段，以当前企业完整机构代码为值；`ISSUE_NAME` 只作名称核对，不作为代码过滤，不替代“信用主体”字段，也不增加到下方固定 13 个展示字段中。

2026-09-20 加载元数据曾失败：`ISSUE_CODE` 与 `ISSUE_NAME` 都错误映射为 `发行人代码`，报 `REPORT_METADATA_INVALID`，不是存续债为空。再次执行时须确认代码、名称分别绑定到正确的物理字段；若仍重名，按该数据集失败处理并使用同源兜底，不强行使用歧义字段。用户确认语义不代表上游元数据已经修复，历史执行证据见 [精确查询证据](mql-verification.json)。

主报表函数：

```text
RPT_CUSTOM_BOND_BS_SAMEISSUER
```

用户提到的展示路径“/Choice金融终端/企业F9/企业一页纸/信用债发行企业一页纸专项数据”及函数 `RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER` 已通过 MQL 验证，但其真实报表“发行人发行债券类型”只返回债券类型筛选内容，适合用于企业类型判定，不包含本板块所需的债券明细字段。因此它不替代本板块的 `RPT_CUSTOM_BOND_BS_SAMEISSUER` 主表，也不进入发行概述的债券明细兜底主链路。

正式取数时，以 `Search_Context` 返回的实际 `column_name_cn` 字段名为准；下表中的英文名仅作为 REST 字段映射和结果整理参考，不得未经运行时核对直接写入 MQL：

| 输出字段 | REST 字段参考 | 取数要求 |
|---|---|---|
| 债券代码 | `SECUCODE` | 保留市场后缀；跨市场重复债按 `SECUCODE_RN=1` 去重 |
| 债券简称 | `BOND_NAME_ABBR` | 纳入字段白名单 |
| 债券类型 | `SECURITY_TYPE` | 纳入字段白名单；用于二次排除同业存单 |
| 债券余额 | `CURRENT_BALANCE` | 单位按报表实际口径传入，不在 prompt 外擅自换算 |
| 币种 | `CURRENCY` | 纳入字段白名单 |
| 发行日期 | `ISSUE_DATE` | 纳入字段白名单 |
| 到期日期 | `EXPIRE_DATE` | 仅保留系统日当日及以后到期的债券 |
| 剩余期限 | `REMAIN_DAY` | 按报表实际口径传入 |
| 最新债项评级 | `BOND_RATING` | 纳入字段白名单 |
| 最新主体评级 | `CREDIT_RATING` | 纳入字段白名单 |
| 票面利率 | `FXCKLL` | 纳入字段白名单 |
| 信用主体 | `CREDIT_SUBJECT_NAME` | 用户所需字段，但本轮 MQL 元数据未暴露；只能同源补取，不用发行人名称冒充 |
| 所属集团 | `GROUP_NAME` | 纳入字段白名单 |

已确认 MQL 加载名称为 `发行人代码`、`集团系`（字符串0）、`跨市场去重排序`（整数1）、`到期日期`、`债券类型`。返回名称为 `债券代码带后缀、债券简称、证券类别、当前余额(亿)、币种、发行日期、到期日期、剩余期限、债券评级、主体评级、票面利率(发行参考利率)、所属集团`。不能假设过滤列与返回列中文名称一致；债券余额单位为亿。以下语义仍须保留，元数据重名未修复前不能声称完整通过：

MQL 过滤语义必须同时满足：

1. 发行人为当前企业，使用 `ISSUE_CODE` 对应的发行人代码字段过滤完整机构代码 `<ORG_CODE>`；不要因为占位符名为 `ORG_CODE` 就把本表过滤字段写成 `ORG_CODE` 或 `ISSUE_NAME`；
2. 去重跨市场债，优先绑定实际报表中的跨市场去重字段，当前 REST 参考为 `SECUCODE_RN=1`；
3. 仅保留未到期债券，优先绑定实际报表中的到期日期过滤，当前 REST 参考为 `EXPIRE_DATE >= <系统日>`；
4. 排除同业存单。不得只依赖未经核对的 `INTERBANK_DEPO` 枚举值；应以 `Search_Context` 核对该字段语义，并同时按实际返回的债券类型/简称二次确认不包含“同业存单”；
5. 不需要标签字段、行情权限字段、估值字段、发行规模、担保、ABS 标签等本板块未列明字段；
6. 按发行日期由近及远排序，系统日取执行时的系统日期。

#### 8.2 Python REST 兜底

仅当本板块正式 MQL 查询、已登记或动态发现的同业务 MQL 候选均失败、超时、字段元数据不可绑定或关键字段缺失时，才允许使用本地 Python REST 兜底。兜底主表仍为 `RPT_CUSTOM_BOND_BS_SAMEISSUER`，并使用以下同源过滤语义：

```text
reportName=RPT_CUSTOM_BOND_BS_SAMEISSUER
columns=SECUCODE,BOND_NAME_ABBR,SECURITY_TYPE,CURRENT_BALANCE,CURRENCY,ISSUE_DATE,EXPIRE_DATE,REMAIN_DAY,BOND_RATING,CREDIT_RATING,FXCKLL,CREDIT_SUBJECT_NAME,GROUP_NAME,SECUCODE_RN
filter=(SECUCODE_RN=1)(ISSUE_CODE="<ORG_CODE>")(IS_GROUP="0")(EXPIRE_DATE>='<系统日>')
sortColumns=ISSUE_DATE&sortTypes=-1&pageNumber=1&pageSize=100&source=choice&client=SW
```

Python 结果整理时必须：

- 按 `SECUCODE_RN=1` 去重跨市场债；
- 再按 `EXPIRE_DATE >= 系统日` 删除已到期记录；
- 按 `SECURITY_TYPE`、`BOND_NAME_ABBR` 及接口实际可用的同业存单标识排除同业存单；
- 只保留上表 13 个输出字段，删除行情权限、估值、标签及其他无关字段；
- 将结果注册为本板块独立的 `issuance_overview` 数据集，`query_path` 标记为 `Python REST fallback`，并在底稿中保留系统日、过滤语义和失败原因。

`RPT_CUSTOM_BOND_BS_SAMEISSUERFILTER` 虽已完成 MQL 验证，但仅用于企业类型判定；本板块的债券明细仍使用 `RPT_CUSTOM_BOND_BS_SAMEISSUER`，不得把专项报表的 `筛选内容` 当作债券明细传给发行概述 prompt。

#### 8.3 资讯来源

`{{资讯}}` 使用 `mx-finance-search`，query 固定为：

```text
<企业全名> 债券 相关资讯 最新动态
```

例如：

```text
中国民生银行股份有限公司 债券 相关资讯 最新动态
```

