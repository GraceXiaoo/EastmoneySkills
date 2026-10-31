# 东方财富·妙想金融 Skills

连接东方财富金融数据与妙想研究能力，让 AI Agent 从金融问题出发，完成数据查询、专项分析和研究报告。

本仓库收录 **47 个 Skill，覆盖 10 类能力**：从查行情、搜公告和筛选标的，到股票、基金、债券、企业、行业与期货研究，以及研报底稿复盘和 Choice API 程序化取数。

每个 Skill 以 `SKILL.md` 描述使用场景、执行步骤和交付要求，并按需配备脚本、模板与参考资料。你可以按任务选择安装，无需一次加载全部能力。

**导航：** [从问题选 Skill](#从问题选-skill) · [能力目录](#能力目录) · [安装与使用](#安装与使用) · [服务与依赖](#服务与依赖) · [常见问题](#常见问题) · [版权与使用](#版权与使用)

## 从问题选 Skill

| 你想完成的任务 | 建议从这里开始 |
| --- | --- |
| 查询已知公司的行情、估值或财务指标 | [金融数据查询](./skills/mx-finance-data/) |
| 找公告、研报或某个事件的财经资讯 | [金融资讯检索](./skills/mx-finance-search/) |
| 按财务、技术或其他条件筛选标的 | [条件筛选](./skills/mx-stocks-screener/) |
| 快速了解一只 A 股的整体情况 | [股票综合诊断](./skills/stock-diagnosis/) |
| 系统研究一家上市公司，生成一页纸报告 | [公司深度研究](./skills/stock-deep-research/) |
| 分析一只基金的收益、风险和持仓 | [基金综合诊断](./skills/fund-diagnosis/)；需要一页纸时选 [基金深度研究](./skills/fund-deep-research/) |
| 对现有研报提取数据、核验口径或复盘预测 | [研报底稿抽取与复盘](./skills/research-report-review/) |
| 用 Python 批量、重复获取 Choice 数据 | [Choice API 程序化取数](./skills/choice-quantapi-skill/) |

一般可以沿着 **查数据 → 做分析 → 出报告** 选择能力。已明确任务时，优先使用对应的专项 Skill；只需回答金融问题时，可从 [金融问答](./skills/mx-financial-assistant/) 开始。

## 能力目录

分类用于阅读导航，各 Skill 目录保持平铺。下表的范围是能力概览；具体市场、标的数量、时间窗口和交付格式以对应 `SKILL.md` 为准。

| 分类 | 数量 | 主要任务 |
| --- | ---: | --- |
| [基础金融工具](#基础金融工具) | 8 | 查数据、搜资讯、问答、筛选和自选管理 |
| [股票研究](#股票研究) | 12 | 综合诊断、专项分析、涨跌归因和公司报告 |
| [行业与热点](#行业与热点) | 6 | 行业、板块、专题、跟踪和市场热点 |
| [基金与 ETF](#基金与-etf) | 6 | 产品诊断、深度研究、经理研究和重仓股压力 |
| [债券研究](#债券研究) | 7 | 个券研究、利差分析和区域化债 |
| [市场与政策](#市场与政策) | 2 | 宏观资金面和政策会议对比 |
| [企业与风险](#企业与风险) | 2 | 企业主体研究、风险与舆情监测 |
| [期货研究](#期货研究) | 1 | 单一期货合约研究 |
| [研报工作流](#研报工作流) | 2 | 底稿提取、预测复盘和研报复现 |
| [量化工具](#量化工具) | 1 | Choice API 接口选择与程序化取数 |
| **合计** | **47** | |

### 基础金融工具

查询是“查已知标的”，筛选是“按条件找标的”，自选管理是“操作自己的列表”。MQL 主要为研究流程提供底层取数能力。

| Skill | 用途 |
| --- | --- |
| [金融数据查询 · `mx-finance-data`](./skills/mx-finance-data/) | 查询行情、估值、财务等结构化指标，交付 Excel 与 Markdown |
| [金融资讯检索 · `mx-finance-search`](./skills/mx-finance-search/) | 按明确对象检索公告、研报、新闻和政策 |
| [宏观数据查询 · `mx-macro-data`](./skills/mx-macro-data/) | 查询经济、价格、货币、财政、贸易和产业数据 |
| [私域知识库检索 · `mx-personal-kb-search`](./skills/mx-personal-kb-search/) | 检索用户明确指定的妙想知识库资料 |
| [金融问答 · `mx-financial-assistant`](./skills/mx-financial-assistant/) | 综合回答金融知识、数据、资讯和分析问题 |
| [条件筛选 · `mx-stocks-screener`](./skills/mx-stocks-screener/) | 按条件或排序筛选股票、基金、ETF、债券、期货及板块等标的 |
| [自选管理 · `mx-self-select`](./skills/mx-self-select/) | 查询、新增或删除 Choice 与东方财富 App 自选证券 |
| [MQL 标准取数 · `mql-query`](./skills/mql-query/) | 查询规范、语法约束、模板复用和 MQL 执行，供研究 Skill 复用 |

### 股票研究

#### 综合与专项诊断

| Skill | 用途 |
| --- | --- |
| [综合诊股 · `stock-diagnosis`](./skills/stock-diagnosis/) | 对 A 股单票进行整体诊断 |
| [基本面分析 · `stock-fundamental-analysis`](./skills/stock-fundamental-analysis/) | 分析财务质量、盈利成长、经营状况和估值 |
| [技术面分析 · `stock-technical-analysis`](./skills/stock-technical-analysis/) | 分析趋势、量价、K 线、技术指标和支撑压力 |
| [资金面分析 · `stock-capital-analysis`](./skills/stock-capital-analysis/) | 分析资金流向、成交活跃度和筹码行为 |
| [消息面分析 · `stock-news-analysis`](./skills/stock-news-analysis/) | 解读公告、新闻、政策和事件的潜在影响 |
| [机构观点 · `stock-institutional-opinion`](./skills/stock-institutional-opinion/) | 梳理评级、目标价、盈利预测及机构共识与分歧 |

#### 涨跌与异动归因

| Skill | 用途 |
| --- | --- |
| [涨跌分析 · `stock-price-movement-analysis`](./skills/stock-price-movement-analysis/) | 分析 A 股单票最近一个月内明确上涨或下跌的原因 |
| [异动复盘 · `stock-price-anomaly-analysis`](./skills/stock-price-anomaly-analysis/) | 发现异动标的，围绕事件、资金与证据进行单票复盘 |

#### 公司报告与比较

| Skill | 用途 |
| --- | --- |
| [公司深度研究 · `stock-deep-research`](./skills/stock-deep-research/) | 生成上市公司深度研究与公司一页纸 |
| [首次覆盖与深度报告 · `initiation-of-coverage-or-deep-dive`](./skills/initiation-of-coverage-or-deep-dive/) | 通过接口生成首次覆盖或公司深度研究报告 |
| [业绩点评 · `stock-earnings-review`](./skills/stock-earnings-review/) | 分析季报、半年报、年报和盈利表现 |
| [可比公司分析 · `comparable-company-analysis`](./skills/comparable-company-analysis/) | 比较 A 股公司与同业的经营、财务和估值，生成 Excel 报告 |

### 行业与热点

| Skill | 用途 |
| --- | --- |
| [产业深度研究 · `industry-deep-research`](./skills/industry-deep-research/) | 研究产业、行业、市场主题及产业类股票指数 |
| [行业研究报告 · `industry-research-report`](./skills/industry-research-report/) | 通过接口生成指定行业的研究报告 |
| [行业板块分析 · `industry-sector-analysis`](./skills/industry-sector-analysis/) | 分析 A 股行业与概念板块的景气度、产业链和驱动因素 |
| [行业与个股跟踪 · `industry-stock-tracker`](./skills/industry-stock-tracker/) | 生成日报、周报、月报或近况跟踪报告 |
| [专题研究 · `topic-research-report`](./skills/topic-research-report/) | 研究政策、事件、趋势等跨行业议题 |
| [市场热点发现 · `stock-market-hotspot-discovery`](./skills/stock-market-hotspot-discovery/) | 发现市场层面的热门资讯、股票和方向 |

### 基金与 ETF

| Skill | 用途 |
| --- | --- |
| [基金综合诊断 · `fund-diagnosis`](./skills/fund-diagnosis/) | 快速分析单只公募基金的收益、风险与持有关注点 |
| [基金研究报告 · `fund-research`](./skills/fund-research/) | 通过接口生成基金深度报告和 Markdown 底稿 |
| [基金深度研究 · `fund-deep-research`](./skills/fund-deep-research/) | 生成单只非 ETF 公募场外基金的深度研究与一页纸 |
| [基金经理研究 · `fund-manager-research`](./skills/fund-manager-research/) | 研究单名基金经理的管理经历、风格与表现 |
| [ETF 深度研究 · `etf-deep-research`](./skills/etf-deep-research/) | 分析单只 ETF 的规模、流动性、业绩风险和持仓 |
| [重仓股压力透视 · `top-holdings-pressure-insight`](./skills/top-holdings-pressure-insight/) | 分析基金重仓股潜在买卖压力及短长周期变化 |

### 债券研究

| Skill | 用途 |
| --- | --- |
| [信用债研究 · `credit-bond-deep-research`](./skills/credit-bond-deep-research/) | 分析单只信用债的信用资质、财务、利差与风险 |
| [可转债研究 · `convertible-bond-deep-research`](./skills/convertible-bond-deep-research/) | 分析估值、债底、条款博弈和正股联动 |
| [地方政府债研究 · `government-bond-deep-research`](./skills/government-bond-deep-research/) | 分析单只地方政府债的发行、估值、区域财政和债务 |
| [利率债新券研究 · `primary-bond-deep-research`](./skills/primary-bond-deep-research/) | 分析发行定价、上市流动性与活跃券预期 |
| [利率债活跃券研究 · `on-the-run-bond-deep-research`](./skills/on-the-run-bond-deep-research/) | 分析活跃券收益率、资金面、供给和机构行为 |
| [利差分析 · `credit-spread-deep-research`](./skills/credit-spread-deep-research/) | 分析品种、期限、评级、信用、税收和流动性利差 |
| [地方化债研究 · `local-government-debt-analysis`](./skills/local-government-debt-analysis/) | 研究单个地区的经济财政、债务负担和化债进展 |

### 市场与政策

| Skill | 用途 |
| --- | --- |
| [宏观资金面研究 · `market-liquidity-deep-research`](./skills/market-liquidity-deep-research/) | 分析央行操作、银行间流动性和跨季资金面 |
| [政策会议对比 · `meeting-minutes-comparison`](./skills/meeting-minutes-comparison/) | 比较政策会议的表述、维度及政策变化 |

### 企业与风险

企业研究面向主体尽调，范围不局限于上市公司股票。

| Skill | 用途 |
| --- | --- |
| [企业深度研究 · `enterprise-deep-research`](./skills/enterprise-deep-research/) | 分析治理、经营、财务、偿债、信用及司法风险 |
| [企业预警监测 · `enterprise-alert-monitoring`](./skills/enterprise-alert-monitoring/) | 跟踪舆情、重点事件、关联主体及风险发酵链路 |

### 期货研究

| Skill | 用途 |
| --- | --- |
| [期货合约研究 · `futures-deep-research`](./skills/futures-deep-research/) | 围绕单一期货合约分析量仓、基差、期限结构、库存和供需 |

### 研报工作流

| Skill | 用途 |
| --- | --- |
| [研报底稿抽取与复盘 · `research-report-review`](./skills/research-report-review/) | 抽取研报表格与图表、核验数据、建立可刷新底稿和复盘预测 |
| [研报复现 · `sellside-research-refresh-with-excel`](./skills/sellside-research-refresh-with-excel/) | 沿原研报框架，为新标的或新时间生成研报、Excel 底稿和评测结果 |

### 量化工具

| Skill | 用途 |
| --- | --- |
| [Choice API 程序化取数 · `choice-quantapi-skill`](./skills/choice-quantapi-skill/) | 查找 EMQuantAPI 文档、选择接口并生成 Python 取数代码 |

这里的“量化 API”沿用 Choice 产品名称。该 Skill 主要服务于程序化数据获取及策略研究的数据准备，本身不提供独立的交易或回测引擎。

## 安装与使用

### 选择安装范围

以下命令使用 [Skills CLI](https://github.com/vercel-labs/skills)，需要 Node.js 与 npm；首次运行 `npx` 可能提示下载工具。安装源为本仓库 `GraceXiaoo/miaoxiang-skills`。

列出可安装的 Skill：

```bash
npx skills add GraceXiaoo/miaoxiang-skills --list
```

安装一个 Skill 到当前项目：

```bash
npx skills add GraceXiaoo/miaoxiang-skills --skill stock-diagnosis
```

一次选择多个 Skill：

```bash
npx skills add GraceXiaoo/miaoxiang-skills --skill mx-finance-data mx-finance-search stock-diagnosis
```

需要全局安装时，为命令增加 `-g`；具体安装目标按工具提示选择。安装位置和可用范围取决于客户端及安装工具，不代表所有 Agent 都已验证兼容。

如已将仓库下载到本地，可以在仓库根目录把上述安装源替换为 `.`。

也可以按客户端的说明手动安装：将所需 Skill 的完整目录复制到客户端指定的位置，保留 `SKILL.md` 及配套资源，再加载或重启客户端。

### 准备服务后提问

安装 Skill 之后，按对应说明准备服务授权、MCP 或 SDK，再用自然语言提出任务。例如：

```text
查询贵州茅台和五粮液最近一期营收与净利润，输出完整数据表。
分析宁德时代当前的资金面，并注明数据时间。
为一只指定的场外公募基金生成深度研究一页纸。
比较两次政治局会议的经济政策表述，引用原文来源。
提取这份研报的图表和数据，核验口径并建立 Excel 底稿。
```

建议提供标的名称或代码、分析期间和交付要求。单标的研究 Skill 通常需要一次聚焦一个对象；不同 Skill 的限制以各自说明为准。

## 服务与依赖

**安装 Skill 不等于开通数据服务。** 实际运行需要相应的数据权限、服务连接和软件环境。

| 能力类型 | 运行前需要确认 |
| --- | --- |
| 妙想接口类查询、诊断和报告 | 对应服务可访问，按 Skill 内的授权流程完成身份验证；部分流程使用 `EM_API_KEY` |
| MQL 与依赖它的研究流程 | 客户端已连接相应 MQL MCP，并提供该任务所需的查询工具与数据权限 |
| 公告、资讯和研报检索流程 | 已连接 Skill 指定的文本检索服务或 MCP |
| Choice API 程序化取数 | Python、可用的 EMQuantAPI SDK、账号与接口数据权限 |
| HTML、Excel、Word、PDF 等交付 | 按对应 Skill 安装脚本依赖、文档生成与渲染工具 |

入口可参考 [妙想](https://ai.eastmoney.com/chat)。具体开通方式、环境变量和依赖版本请阅读所选 Skill；本仓库不承诺所有 Skill 共用一个授权方式或一个 API Key。

密钥应保存在本地环境或服务指定的凭据位置，不提交到 GitHub，也不填写在 Issue 中。

仓库不内置可用 API Key。支持扫码授权的 Skill 按内置流程完成授权；要求 `EM_API_KEY` 的脚本需要在运行前设置环境变量。不要将个人密钥写回脚本、示例或参考文档。

## 常见问题

### 相近的研究 Skill 怎么选？

| 需求 | 选择方式 |
| --- | --- |
| 快速综合判断股票或基金 | 选择 `stock-diagnosis` 或 `fund-diagnosis` |
| 只分析技术面、资金面等一个维度 | 选择对应股票专项分析 Skill |
| 生成公司、场外基金或 ETF 一页纸 | 选择相应的 `*-deep-research` Skill |
| 通过接口生成首次覆盖、行业或基金报告 | 阅读 `initiation-of-coverage-or-deep-dive`、`industry-research-report` 或 `fund-research` |
| 提取和核验现有研报 | 选择 `research-report-review` |
| 根据原研报框架生成新报告 | 选择 `sellside-research-refresh-with-excel` |

相近 Skill 的触发范围可能重叠。明确指定 Skill 或交付形式，有助于客户端选择正确流程。

### 所有市场和输出格式都支持吗？

不是。部分诊断仅支持 A 股，一页纸研究通常限定单标的，报告形式也可能分别为 Markdown、HTML、Excel、Word 或 PDF。请以各目录的支持范围为准。

### 为什么安装后仍无法运行？

优先检查服务授权、MCP 工具是否可见、数据权限和脚本依赖。仅复制 `SKILL.md` 可能遗漏脚本与模板，应安装完整目录。

### README 分类会影响安装吗？

分类是导航方式，不改变 Skill 名称。当前 Skill 目录直接平铺在仓库根部，目录链接与本地安装示例均对应这一结构。

## 目录约定与维护

每个目录是一份完整 Skill 包，入口文件名为 `SKILL.md`。脚本、参考资料、模板等配套目录因 Skill 而异。

维护时同步更新 Skill 描述、版本、依赖和本 README 的导航。目录重命名或新增、移除能力后，应核对链接与数量。

反馈问题时，请提供 Skill 名称、客户端与系统、复现步骤、脱敏错误信息和预期结果。不要上传账号密钥、私域资料或未经许可的数据。

## 版权与使用

本 README 为本项目原创编写。目录导航、功能表格和安装说明属于通用文档组织方式；本文未复制其他金融 Skill 仓库的品牌文案或专有内容。

各 Skill、配套代码、模板和参考资料的权利归相应权利人所有，使用范围以各目录的许可证、版权声明及适用服务条款为准。当前部分 Skill 标注 `license: proprietary`；公开展示不等于授予开源许可。本 README 不替代许可证，也不额外授予复制、再分发或商业使用的权利。

东方财富、妙想、Choice 及其他文中提及的产品名称和商标归各自权利人所有。金融数据、研报、公告及检索材料的访问与使用仍受对应来源的授权条款约束。

研究结果用于信息整理与分析辅助，不构成投资建议；涉及决策时，应核验数据时点、来源和计算口径。
