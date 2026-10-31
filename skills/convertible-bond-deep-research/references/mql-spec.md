# MQL 取数规范（按需加载）

> 本文件在执行 MQL 取数步骤时加载，包含：报表路径映射、字段映射表、MQL 语法约束、三类状态的 MQL 脚本模板。

## ⚠️ 报表路径与取数方式（重要）

以下路径和取数方式基于实测验证，**禁止臆造或自行修改**。首次使用时仍建议通过 `Search_Context` 的 `searchIndicator` 搜索"可转债"确认路径未变。

### 可用报表路径

| 用途 | 报表名 | 完整路径 |
|------|--------|---------|
| 个券基本信息（状态判断） | 转债基本信息 | `Choice报表\报表指标\服务端\妙想服务\细分场景\可转债\转债基本信息\转债基本信息\|830272205760536` |
| 存续期全量指标 | 存续可转债 | `Choice报表\报表指标\Choice金融终端\债券F9\专项分析\转债专项数据\存续可转债\存续可转债\|826425973918861` |
| 到期全量指标 | 到期可转债 | `Choice报表\报表指标\Choice金融终端\债券F9\专项分析\转债专项数据\到期可转债\到期可转债\|826425973918861` |
| 新发全量指标 | 新发可转债 | `Choice报表\报表指标\Choice金融终端\债券F9\专项分析\转债专项数据\新发可转债\新发可转债\|826425973918861` |
| 新发可转债（API 变体） | 新发可转债 | `Choice报表\报表指标\Choice金融终端\债券F9\专项分析\转债专项数据\新发可转债\|826425973918861` |

### 取数方式

以上报表均配置了 `reportStandardCodeSupported=true` 且 `reportFilterColumns` 为空，**必须使用 `SetCodes(["代码"])` 指定证券范围，不能使用 `SetReportFilter`**。

### Block 编号规则

**每次 `Execute_MQL` 调用中，Block 编号必须从 `#1` 开始连续递增**，不能跨调用延续（如不能在第二次调用中使用 `#2`）。如需分批取数，每次调用都从 `#1` 重新编号。

### 字段名注意事项

`REPORT_FIELD("...")` 中必须使用返回列的**完整中文名（含括号）**。以下字段名易出错：
- `转债近20日换手率（%）` —— 带 `（%）` 后缀
- `正股20日历史波动率（%）` —— 带 `（%）` 后缀
- `正股行业` 而非 `正股所属行业`（存续可转债报表中）

## ⚠️ 数值精度规范（重要）

**所有数值类字段，在完成「单位转换」后一律统一保留 4 位小数**（`toFixed(4)` 或 MQL 中 `Round` 到 4 位）。原始 MQL 返回为高精度浮点（如转股溢价率 `0.645280843806`、每股净资产 `4.53763137`），不可直接使用过多小数位，也不可随意按 2 位截断，须统一到 4 位以确保跨报告一致可比。

- **4 位小数的适用范围**：所有以 `比例/比率/价格/金额/收益率/波动率/规模（亿元/万元）` 呈现的数值型指标，含元、万元、亿元、%、倍等单位。
- **转换与取值顺序**：先做「单位转换」（如 ×100、÷1e8、÷1e4），再对结果 `四舍五入保留 4 位小数`。如 ROE 原值 0.00358108 → ×100 = 0.358108 → 保留 4 位 = **0.3581**。
- **非数值/字符串字段**（如转债代码、转债简称、行业、区间、条款说明、互动状态量、日期时间等）不做精度处理，原样输出。
- **`-` / 空值**：字段缺失或返回空时，仍按既有规则用 `-` 占位，不因精度规范改变。
- 若个别指标因口径需要调整精度（如是否数、计数天数为整数），可保留为整数并在表格列名注明，除此之外的数值指标一律 4 位小数。

## 字段映射表

### 存续期可转债指标（40+ 字段）

| 指标中文名 | 指标英文名 | 类型 | 单位 | 单位转换逻辑 |
|-----------|-----------|------|------|------------|
| 转债代码 | SECUCODE | string | | |
| 转债简称 | BOND_NAME_ABBR | string | | |
| 正股简称 | CONVERT_SECUNAME | string | | |
| 上市日期 | LISTING_DATE | datetime | | |
| 发行规模 | AISSUEVOL | double | 元 | 除以100000000，转换为亿元，保留4位小数 |
| 剩余规模 | REMAINVOL | double | 元 | 除以100000000，转换为亿元，保留4位小数 |
| 信用评级 | CREDIT_RATING | string | | |
| 剩余年限 | RESIDUAL_EXPIRE_YEAR | double | | 保留4位小数 |
| 转股价 | TRANSFER_PRICE | double | 元 | 保留4位小数 |
| 正股现价 | CONVERT_CLOSE_PRICE | double | 元 | 保留4位小数 |
| 转债现价 | FULL_CLOSE_PRICE | double | 元 | 保留4位小数 |
| 转股价值 | CONV_VALUE | double | 元 | 保留4位小数 |
| 转股溢价率 | CONV_PREMIUM_RATIO | double | 比例未乘100 | 乘以100，保留4位小数 |
| 纯债价值 | BOND_VALUE | double | 元 | 保留4位小数 |
| 纯债溢价率 | BOND_PREMIUM_RATIO | double | 比例已乘100 | 保留4位小数 |
| 到期赎回价 | EXPIRE_REDEEM_PRICE | double | 元 | 保留4位小数 |
| 到期税前收益率 | BOND_YTM | double | 比例已乘100 | 保留4位小数 |
| 强赎计数天数 | REDEEM_CALCULATE_DAYS | double | | 天数为整数可原样输出 |
| 强赎满足天数 | REDEEM_CONTENT_DAYS | double | | 同上，整数原样输出 |
| 强赎触发比例 | REDEEM_TRIGGER_RATIO | double | | 比例已乘100，保留4位小数 |
| 强赎累计达标天数 | CALLDAY | string | | |
| 赎回次数 | INTENSITY | int | | 整数原样输出 |
| 不强赎公告情况 | NO_REDE_INFO | string | | |
| 下修计数天数 | TRANSFER_CALCULATE_DAYS | double | | 天数为整数可原样输出 |
| 下修满足天数 | TRANSFER_CONTENT_DAYS | double | | 同上，整数原样输出 |
| 下修触发比例 | TRANSFER_TRIGGER_RATIO | double | 比例已乘100 | 保留4位小数 |
| 下修累计达标天数 | RIVSEDAY | string | | |
| 下修底限说明 | FLOORDESCHG | string | | |
| 下修次数 | TRANSFER_CALCULATE_CT | double | | 整数原样输出 |
| 回售起始日 | DAT_SDATEPUTS | datetime | | |
| 回售计数天数 | RESALE_CALCULATE_DAYS | double | | 天数为整数可原样输出 |
| 回售满足天数 | RESALE_CONTENT_DAYS | double | | 同上，整数原样输出 |
| 回售触发比例 | RESALE_TRIGGER_RATIO | double | 比例已乘100 | 保留4位小数 |
| 回售价 | RESALE_PRICE | double | | 保留4位小数 |
| 正股行业 | EM_INDUSTRY | string | | |
| PE_TTM | PE_TTM | double | 比例已乘100 | 保留4位小数 |
| PB | PB | double | 比例已乘100 | 保留4位小数 |
| ROE | AVERAGE_ROE | double | 比例未乘100 | 乘以100，保留4位小数 |
| 资产负债率 | DEBT_ASSET_RATIO | double | 比例未乘100 | 乘以100，保留4位小数 |
| 每股净资产 | BVPS | double | | 保留4位小数 |
| 近一年营收增速 | OPERATE_INCOME_YOY | double | 比例未乘100 | 乘以100，保留4位小数 |
| 近一年净利润增速 | NETPROFIT_YOY | double | 比例未乘100 | 乘以100，保留4位小数 |
| 转债近20日日均成交额 | BOND_20D_AMOUNT | double | 元 | 除以10000，转换为万元，保留4位小数 |
| 转债近20日换手率（%） | BOND_20D_TURNOVERRATE | double | 比例已乘100 | 保留4位小数 |
| 正股20日历史波动率（%） | CONVERT_VLATILITY | double | 比例未乘100 | 乘以100，保留4位小数 |
| 大股东近3个月减持股数 | HOLDER_CHANGE_NUM | double | 股 | 保留4位小数 |
| 机构持仓占比 | ORG_HOLD_RATE | double | 比例已乘100 | 保留4位小数 |
| 隐含波动率 | IMPLIED_VOLATILITY | double | 比例已乘100 | 保留4位小数 |

### 到期可转债附加指标

| 指标中文名 | 指标英文名 | 类型 | 单位 | 单位转换逻辑 |
|-----------|-----------|------|------|------------|
| 票面利率（逐年） | COUPON_INTEREST_RATE | string | | |
| 起息日 | VALUE_DATE | datetime | | |
| 到期日 | EXPIRE_DATE | datetime | | |
| 初始转股价 | INITIAL_TRANSFER_PRICE | double | 元 | 保留4位小数 |
| 信用评级历程 | CREDIT_RATING_LC | string | | |
| 是否触发过强赎 | IS_FORCE_REDEEM | string | | |
| 强赎触发日期与结果 | REDEEM_TD_RESULT | string | | |
| 是否发生过下修 | IS_RIVSE | string | | |
| 是否触发过回售 | IS_RESALE | string | | |
| 回售申报规模 | RESALE_VOL | double | 万元 | 除以10000，转换为亿元，保留4位小数 |
| 上市首日价格 | LS_FCLOSE_PRICE | double | 元 | 保留4位小数 |
| 存续期最高价 | HIGH_FCLOSE | double | 元 | 保留4位小数 |
| 存续期最低价 | LOW_FCLOSE | double | 元 | 保留4位小数 |
| 转股溢价率区间 | INTERVAL_CONVP_RATIO | string | | |
| 纯债溢价率区间 | INTERVAL_BONDP_RATIO | string | | |
| 正股存续期涨跌幅 | INTERVAL_CHANGE_RATE | string | | |
| 实际退出方式 | EXIT_WAY | string | | |
| 转股退出金额 | STOCK_AMT | double | 万元 | 保留4位小数 |
| 转股退出比例 | STOCK_RATIO | double | 比例已乘100 | 保留4位小数 |
| 赎回退出金额 | REDE_AMT | double | 万元 | 保留4位小数 |
| 赎回退出比例 | REDE_RATIO | double | 比例已乘100 | 保留4位小数 |
| 回售退出金额 | PUT_AMT | double | 万元 | 保留4位小数 |
| 回售退出比例 | PUT_RATIO | double | 比例已乘100 | 保留4位小数 |
| 同期中证转债指数涨跌幅 | INTERVAL_ZZ_CRATE | string | | |
| 正股存续期最高价 | INTERVAL_HIGH_CLOSE | double | 元 | 保留4位小数 |
| 正股存续期最低价 | INTERVAL_LOW_CLOSE | double | 元 | 保留4位小数 |
| 正股存续期年化波动率 | INTERVAL_ANNU_VOLATILITY | double | 比例已乘100 | 保留4位小数 |
| 正股区间日均换手率 | INTERVAL_TRATE | double | 比例已乘100 | 保留4位小数 |
| 转股稀释比例 | TRANSFER_DILUTION_RATIO | double | 比例已乘100 | 保留4位小数 |

### 新发可转债附加指标（35 字段，实测验证）

| 指标中文名 | 指标英文名 | 类型 | 单位 | 单位转换逻辑 |
|-----------|-----------|------|------|------------|
| 转债代码 | SECUCODE | string | | |
| 转债简称 | BOND_NAME_ABBR | string | | |
| 正股简称 | CONVERT_SECUNAME | string | | |
| 发行规模 | AISSUEVOL | double | 元 | 除以100000000，转换为亿元，保留4位小数 |
| 发行日 | ISSUESDATE | datetime | | |
| 上市日期 | LISTING_DATE | datetime | | |
| 信用评级 | CREDIT_RATING | string | | |
| 债券期限（年） | BOND_EXPIRE | double | 年 | 保留4位小数 |
| 票面利率（逐年） | COUPON_INTEREST_RATE | string | | |
| 转股价（元） | TRANSFER_PRICE | double | 元 | 保留4位小数 |
| 纯债价值（元） | BOND_VALUE | double | 元 | 保留4位小数 |
| 纯债溢价率（%） | BOND_PREMIUM_RATIO | double | 比例已乘100 | 保留4位小数 |
| 到期赎回价（含最后一年利息） | EXPIRE_REDEEM_PRICE | double | 元 | 保留4位小数 |
| 纯债YTM（%） | BOND_YTM | double | 比例已乘100 | 保留4位小数 |
| 初始转股溢价率（%） | INITIAL_TRANSFER_PREMIUM | double | 比例未乘100 | 乘以100，保留4位小数 |
| 所属行业 | EM_INDUSTRY | string | | |
| PE_TTM | PE_TTM | double | 倍 | 直接使用，保留4位小数 |
| PB | PB | double | 倍 | 直接使用，保留4位小数 |
| ROE | AVERAGE_ROE | double | 比例未乘100 | 乘以100，保留4位小数 |
| 每股净资产 | BVPS | double | 元 | 保留4位小数 |
| 资产负债率 | DEBT_ASSET_RATIO | double | 比例未乘100 | 乘以100，保留4位小数 |
| 近一年营收增速 | OPERATE_INCOME_YOY | double | 比例未乘100 | 乘以100，保留4位小数 |
| 近一年净利润增速 | NETPROFIT_YOY | double | 比例未乘100 | 乘以100，保留4位小数 |
| 募集资金用途 | BONDUSE | string | | |
| 强赎条款 | REDEEM_TRIGGER_CONDITION | string | | |
| 下修条款 | TRANSFER_TRIGGER_CONDITION | string | | |
| 回售条款 | RESALE_TRIGGER_CONDITION | string | | |
| 利率补偿说明 | EXPIRE_REDEEM_CLAUSE | string | | |
| 原股东配售比例 | ORIG_PR | double | 比例未乘100 | 乘以100，保留4位小数 |
| 网上申购户数/中签率（若有） | ONLINE_VA_NUM | double | 比例未乘100 | 乘以100，保留4位小数 |
| 是否细分龙头 | IS_DCASSETSRANK | string | | |
| 主营业务 | MAIN_BUSINESS | string | | |
| 核心竞争优势 | YYCONCLUSION | string | | |
| 行业政策与景气度 | INDUSTRY_POLP | string | | |
| 相近行业/评级的转债平均溢价率 | AVG_INRA | double | 比例未乘100 | 乘以100，保留4位小数 |

> 字段名注意：`债券期限（年）`、`票面利率（逐年）`、`转股价（元）`、`纯债价值（元）`、`纯债溢价率（%）`、`到期赎回价（含最后一年利息）`、`纯债YTM（%）`、`初始转股溢价率（%）`、`网上申购户数/中签率（若有）` 均带括号后缀，`REPORT_FIELD` 中必须使用完整中文名，不能用省略写法。

## MQL 语法约束

- `SetReportFilter` 比较运算符必须用 `==`（不是 `=`）；范围用 `>=` / `<=`；多条件之间用 `AND` 连接
- `SetReportFilter` 只能使用「加载列」（输入参数），**不能使用「报表返回列」**（输出参数）
- **转债专项报表无 filter 列，必须用 `SetCodes(["代码"])` 取数**，不能用 `SetReportFilter`
- `in` 运算符**不支持**；如需多值过滤，用 `OR` 连接多个 `==` 条件
- `Limit()` 和 `Top()` **不支持**；如需限制行数，用 `OutputBlock()` 标记输出 Block
- `Sort()` 必须放在所有 `REPORT_FIELD` 声明之后
- `OutputBlock()` 不接受参数，语法为 `OutputBlock();`
- 路径内分隔符用单个反斜杠 `\`
- `REPORT_FIELD("...")` 中必须使用返回列中文名（含括号的全名）
- **每次 `Execute_MQL` 调用中 Block 编号必须从 `#1` 开始连续递增**
- **数值精度**：MQL 返回的原始值为高精度浮点，取回后须在客户端按「单位转换 → 保留 4 位小数」处理（见上文「数值精度规范」），不要在 MQL 层做截断，以保证原始数据完整可取

## MQL 脚本模板

### Step 1：个券状态判断（转债基本信息）

用于获取上市日期，判断个券属于新发/存续/到期。

```text
ReportBlock(#1, {Choice报表\报表指标\服务端\妙想服务\细分场景\可转债\转债基本信息\转债基本信息|830272205760536});
SetCodes(["{转债代码}"]);
{转债代码}: REPORT_FIELD("债券代码");
{转债简称}: REPORT_FIELD("转债简称");
{正股简称}: REPORT_FIELD("正股简称");
{上市日期}: REPORT_FIELD("上市日期");
OutputBlock();
```

### Step 2A：存续期可转债取数（存续可转债报表）

判断为存续期后，分两次调用取数（每次从 #1 开始）。取回的所有数值字段按「数值精度规范」在客户端统一保留 4 位小数。

**第一次调用：核心指标 + 财务指标**

```text
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\专项分析\转债专项数据\存续可转债\存续可转债|826425973918861});
SetCodes(["{转债代码}"]);
{转债代码}: REPORT_FIELD("转债代码");
{转债简称}: REPORT_FIELD("转债简称");
{正股简称}: REPORT_FIELD("正股简称");
{上市日期}: REPORT_FIELD("上市日期");
{发行规模}: REPORT_FIELD("发行规模");
{剩余规模}: REPORT_FIELD("剩余规模");
{信用评级}: REPORT_FIELD("信用评级");
{剩余年限}: REPORT_FIELD("剩余年限");
{转股价}: REPORT_FIELD("转股价");
{正股现价}: REPORT_FIELD("正股现价");
{转债现价}: REPORT_FIELD("转债现价");
{转股价值}: REPORT_FIELD("转股价值");
{转股溢价率}: REPORT_FIELD("转股溢价率");
{纯债价值}: REPORT_FIELD("纯债价值");
{纯债溢价率}: REPORT_FIELD("纯债溢价率");
{到期赎回价}: REPORT_FIELD("到期赎回价");
{到期税前收益率}: REPORT_FIELD("到期税前收益率");
{正股行业}: REPORT_FIELD("正股行业");
{PE_TTM}: REPORT_FIELD("PE_TTM");
{PB}: REPORT_FIELD("PB");
{ROE}: REPORT_FIELD("ROE");
{资产负债率}: REPORT_FIELD("资产负债率");
{每股净资产}: REPORT_FIELD("每股净资产");
{近一年营收增速}: REPORT_FIELD("近一年营收增速");
{近一年净利润增速}: REPORT_FIELD("近一年净利润增速");
{隐含波动率}: REPORT_FIELD("隐含波动率");
{机构持仓占比}: REPORT_FIELD("机构持仓占比");
OutputBlock();
```

**第二次调用：条款博弈 + 流动性指标**

```text
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\专项分析\转债专项数据\存续可转债\存续可转债|826425973918861});
SetCodes(["{转债代码}"]);
{强赎计数天数}: REPORT_FIELD("强赎计数天数");
{强赎满足天数}: REPORT_FIELD("强赎满足天数");
{强赎触发比例}: REPORT_FIELD("强赎触发比例");
{强赎累计达标天数}: REPORT_FIELD("强赎累计达标天数");
{赎回次数}: REPORT_FIELD("赎回次数");
{不强赎公告情况}: REPORT_FIELD("不强赎公告情况");
{下修计数天数}: REPORT_FIELD("下修计数天数");
{下修满足天数}: REPORT_FIELD("下修满足天数");
{下修触发比例}: REPORT_FIELD("下修触发比例");
{下修累计达标天数}: REPORT_FIELD("下修累计达标天数");
{下修底限说明}: REPORT_FIELD("下修底限说明");
{下修次数}: REPORT_FIELD("下修次数");
{回售起始日}: REPORT_FIELD("回售起始日");
{回售计数天数}: REPORT_FIELD("回售计数天数");
{回售满足天数}: REPORT_FIELD("回售满足天数");
{回售触发比例}: REPORT_FIELD("回售触发比例");
{回售价}: REPORT_FIELD("回售价");
{转债近20日日均成交额}: REPORT_FIELD("转债近20日日均成交额");
{转债近20日换手率}: REPORT_FIELD("转债近20日换手率（%）");
{正股20日历史波动率}: REPORT_FIELD("正股20日历史波动率（%）");
{大股东近3个月减持股数}: REPORT_FIELD("大股东近3个月减持股数");
OutputBlock();
```

### Step 2B：到期可转债取数（到期可转债报表）

判断为到期后使用。取回的所有数值字段按「数值精度规范」在客户端统一保留 4 位小数。

```text
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\专项分析\转债专项数据\到期可转债\到期可转债|826425973918861});
SetCodes(["{转债代码}"]);
{转债代码}: REPORT_FIELD("转债代码");
{转债简称}: REPORT_FIELD("转债简称");
{正股简称}: REPORT_FIELD("正股简称");
{发行规模}: REPORT_FIELD("发行规模");
{剩余规模}: REPORT_FIELD("剩余规模");
{票面利率}: REPORT_FIELD("票面利率（逐年）");
{起息日}: REPORT_FIELD("起息日");
{到期日}: REPORT_FIELD("到期日");
{初始转股价}: REPORT_FIELD("初始转股价");
{信用评级历程}: REPORT_FIELD("信用评级历程");
{是否触发过强赎}: REPORT_FIELD("是否触发过强赎");
{强赎触发日期与结果}: REPORT_FIELD("强赎触发日期与结果");
{是否发生过下修}: REPORT_FIELD("是否发生过下修");
{下修次数}: REPORT_FIELD("下修次数");
{是否触发过回售}: REPORT_FIELD("是否触发过回售");
{回售申报规模}: REPORT_FIELD("回售申报规模");
{上市首日价格}: REPORT_FIELD("上市首日价格");
{存续期最高价}: REPORT_FIELD("存续期最高价");
{存续期最低价}: REPORT_FIELD("存续期最低价");
{转股溢价率区间}: REPORT_FIELD("转股溢价率区间");
{纯债溢价率区间}: REPORT_FIELD("纯债溢价率区间");
{正股存续期涨跌幅}: REPORT_FIELD("正股存续期涨跌幅");
{实际退出方式}: REPORT_FIELD("实际退出方式");
{转股退出金额}: REPORT_FIELD("转股退出金额");
{转股退出比例}: REPORT_FIELD("转股退出比例");
{赎回退出金额}: REPORT_FIELD("赎回退出金额");
{赎回退出比例}: REPORT_FIELD("赎回退出比例");
{回售退出金额}: REPORT_FIELD("回售退出金额");
{回售退出比例}: REPORT_FIELD("回售退出比例");
{同期中证转债指数涨跌幅}: REPORT_FIELD("同期中证转债指数涨跌幅");
{正股存续期最高价}: REPORT_FIELD("正股存续期最高价");
{正股存续期最低价}: REPORT_FIELD("正股存续期最低价");
{正股存续期年化波动率}: REPORT_FIELD("正股存续期年化波动率");
{正股区间日均换手率}: REPORT_FIELD("正股区间日均换手率");
{转股稀释比例}: REPORT_FIELD("转股稀释比例");
OutputBlock();
```

### Step 2C：新发可转债取数（新发可转债报表）

判断为新发后使用。已用「新发可转债」报表实测验证（中贝转债 113678.SH，35 字段全部取回），一次调用即可取全。取回的所有数值字段按「数值精度规范」在客户端统一保留 4 位小数。

```text
ReportBlock(#1, {Choice报表\报表指标\Choice金融终端\债券F9\专项分析\转债专项数据\新发可转债\新发可转债|826425973918861});
SetCodes(["{转债代码}"]);
{转债代码}: REPORT_FIELD("转债代码");
{转债简称}: REPORT_FIELD("转债简称");
{正股简称}: REPORT_FIELD("正股简称");
{发行规模}: REPORT_FIELD("发行规模");
{发行日}: REPORT_FIELD("发行日");
{上市日期}: REPORT_FIELD("上市日期");
{信用评级}: REPORT_FIELD("信用评级");
{债券期限}: REPORT_FIELD("债券期限（年）");
{票面利率}: REPORT_FIELD("票面利率（逐年）");
{转股价}: REPORT_FIELD("转股价（元）");
{纯债价值}: REPORT_FIELD("纯债价值（元）");
{纯债溢价率}: REPORT_FIELD("纯债溢价率（%）");
{到期赎回价}: REPORT_FIELD("到期赎回价（含最后一年利息）");
{纯债YTM}: REPORT_FIELD("纯债YTM（%）");
{初始转股溢价率}: REPORT_FIELD("初始转股溢价率（%）");
{所属行业}: REPORT_FIELD("所属行业");
{PE_TTM}: REPORT_FIELD("PE_TTM");
{PB}: REPORT_FIELD("PB");
{ROE}: REPORT_FIELD("ROE");
{每股净资产}: REPORT_FIELD("每股净资产");
{资产负债率}: REPORT_FIELD("资产负债率");
{近一年营收增速}: REPORT_FIELD("近一年营收增速");
{近一年净利润增速}: REPORT_FIELD("近一年净利润增速");
{募集资金用途}: REPORT_FIELD("募集资金用途");
{强赎条款}: REPORT_FIELD("强赎条款");
{下修条款}: REPORT_FIELD("下修条款");
{回售条款}: REPORT_FIELD("回售条款");
{利率补偿说明}: REPORT_FIELD("利率补偿说明");
{原股东配售比例}: REPORT_FIELD("原股东配售比例");
{网上申购户数中签率}: REPORT_FIELD("网上申购户数/中签率（若有）");
{是否细分龙头}: REPORT_FIELD("是否细分龙头");
{主营业务}: REPORT_FIELD("主营业务");
{核心竞争优势}: REPORT_FIELD("核心竞争优势");
{行业政策与景气度}: REPORT_FIELD("行业政策与景气度");
{相近平均溢价率}: REPORT_FIELD("相近行业/评级的转债平均溢价率");
OutputBlock();
```

> 注意：`{变量名}` 仅为结果别名，可任意命名；`REPORT_FIELD` 内必须用报表列的完整中文名（含括号）。若某字段返回空值，不要改字段名，直接保留。
