# EastmoneySkills · 东方财富妙想金融技能库

**简体中文** · [English](./README.en.md)

[![Skills](https://img.shields.io/badge/Skills-47-2563eb)](#-能力目录)
[![Categories](https://img.shields.io/badge/Categories-10-0f766e)](#-能力目录)
[![GitHub Stars](https://img.shields.io/github/stars/GraceXiaoo/EastmoneySkills?style=flat&cacheSeconds=300&v=20261031)](https://github.com/GraceXiaoo/EastmoneySkills/stargazers)

**面向 AI Agent 的金融数据查询与专业研究工作流。**

以东方财富金融数据、Choice 数据能力与妙想研究服务为基础，提供 **47 个 Skill、10 类业务能力**，覆盖股票、基金、ETF、债券、企业、行业、期货、宏观与政策，以及研报复盘和程序化取数。

从“查一个指标”到“完成一份研究报告”，按任务选择所需能力，通过自然语言调用，并按相应流程交付数据表、分析结论或研究文档。

🌐 **官网：[东方财富·妙想 Skills](https://ai.eastmoney.com/skills)**

**快速导航：** [快速开始](#-快速开始) · [支持的 Agent](#-支持的-agent) · [按任务选择](#-从问题选-skill) · [能力目录](#-能力目录) · [安装指南](#-安装与使用) · [服务与依赖](#-服务与依赖) · [常见问题](#-常见问题) · [版权与使用](#-版权与使用)

## 🧭 项目概览

Skill 是一份可复用的任务包：`SKILL.md` 定义使用场景、分析框架、执行步骤和交付要求，配套脚本、参考资料与模板按需提供。

| 能力层次 | 解决的问题 | 典型交付 |
| --- | --- | --- |
| 数据与检索 | 查已知标的、找资讯、筛选候选对象 | 数据表、检索结果、筛选列表 |
| 诊断与研究 | 解释基本面、价格变化、行业驱动与风险 | 专项分析、综合诊断、深度研究 |
| 报告与复盘 | 将研究过程形成文档，核验和更新已有研报 | Markdown、HTML、Excel、Word 或 PDF |

Skill 负责组织任务；MCP 提供连接到客户端的工具；API/SDK 提供具体服务或数据接口。不同 Skill 使用的连接方式与权限要求不同，详见 [服务与依赖](#-服务与依赖)。

## 🚀 快速开始

### 1. npx 下载与安装

准备支持 Skill 加载的 AI 客户端，以及 Node.js 22.20 或更高版本与 npm，先安装与你的任务相关的能力：

```bash
npx skills add GraceXiaoo/EastmoneySkills --skill mx-finance-data stock-diagnosis
```

按安装工具提示选择客户端和安装范围，再阅读对应 Skill 的授权与依赖说明。完成服务连接后，可以直接提问：

```text
查询贵州茅台最近一期营收与净利润，注明报告期并输出数据表。
```

想先浏览可安装能力：

```bash
npx skills add GraceXiaoo/EastmoneySkills --list
```

安装示例使用 [Skills CLI](https://github.com/vercel-labs/skills)。

### 2. 一键开始：让 Agent 帮你安装

在支持安装技能、执行命令或下载文件的 Agent 中，直接发送：

```text
帮我一键安装技能：https://github.com/GraceXiaoo/EastmoneySkills/tree/main
```

Agent 可根据当前客户端环境协助下载和安装。只需要部分能力时，可补充技能名称，例如 `mx-finance-data` 和 `stock-diagnosis`。

此方式仍需 Agent 能访问仓库；遇到 GitHub 或 npm 网络问题时，可让 Agent 从已下载的本地完整目录安装。安装后仍需按所选 Skill 配置数据服务与授权。

## 🤖 支持的 Agent

可通过 Skills CLI 向以下客户端定向安装。表格依据安装工具的 [Agent 支持清单](https://github.com/vercel-labs/skills/blob/main/docs/agents.md)，表示安装工具支持的目标，不等于本仓库已在每个客户端完成全部金融流程测试。

| Agent / 客户端 | 安装参数 | 接入方式 |
| --- | --- | --- |
| Claude Code | `-a claude-code` | 安装完整 Skill，并按需配置服务与 MCP |
| OpenAI Codex | `-a codex` | 安装完整 Skill，并按需配置服务与 MCP |
| Cursor | `-a cursor` | 安装到支持 Skill 的客户端版本，并配置所需工具 |
| OpenClaw | `-a openclaw` | 安装完整 Skill，并配置脚本执行环境和服务连接 |
| Gemini CLI | `-a gemini-cli` | 安装完整 Skill，并配置所需工具与运行环境 |
| Hermes Agent | `-a hermes-agent` | 安装完整 Skill，并配置所需工具与运行环境 |
| OpenCode | `-a opencode` | 安装完整 Skill，并配置所需工具与运行环境 |
| Windsurf | `-a windsurf` | 安装到支持 Skill 的客户端版本，并配置所需工具 |

例如，指定安装到 Claude Code 或 Codex：

```bash
npx skills add GraceXiaoo/EastmoneySkills --skill stock-diagnosis -a claude-code
npx skills add GraceXiaoo/EastmoneySkills --skill stock-diagnosis -a codex
```

**当前验证范围：** 本地 Skills CLI 已识别全部 47 个 Skill；Python 脚本已通过语法检查，部分凭据处理已通过离线检查。尚未逐一完成上述客户端的在线数据调用、MCP 连接和报告生成测试。

**文档核验（2026-10-31）：** 中英文目录描述已与各 Skill 的说明对照；140 个 Python 文件通过语法检查；安装参数和 Node.js 要求已与 Skills CLI 官方文档核对。目录功能表示 Skill 定义的工作流，不代表已完成在线验收。当前没有 SkillCheck 验证报告。

**已知发布问题：** `sellside-research-refresh-with-excel` 缺少 `bundle/review`、`bundle/drafting` 和 `bundle_manifest.json`，且 `SKILL.md` 与运行清单的版本不一致；自带 `check_bundle.py` 返回 `BLOCKED`，当前发布包不能完成完整研报复现。GitHub 来源的 CLI 发现检查因克隆网络错误未完成，本地目录发现已通过。

运行完整工作流时，客户端需能读取配套资源、执行所需脚本或调用指定工具，并具备相应数据权限。工具名、服务配置和交付能力以所选 Skill 与客户端当前环境为准。

## 🎯 从问题选 Skill

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

已明确任务时，优先选择专项 Skill；只需综合回答金融问题时，可从 [金融问答](./skills/mx-financial-assistant/) 开始。

## 📚 能力目录

所有 Skill 平铺在 `skills/` 中，按业务分类提供导航。具体市场、标的数量、时间窗口和交付格式以各目录的 `SKILL.md` 为准。

| 分类 | 数量 | 主要任务 |
| --- | ---: | --- |
| 🧰 [基础金融工具](#基础金融工具) | 8 | 查数据、搜资讯、问答、筛选和自选管理 |
| 📈 [股票研究](#股票研究) | 12 | 综合诊断、专项分析、涨跌归因和公司报告 |
| 🔎 [行业与热点](#行业与热点) | 6 | 行业、板块、专题、跟踪和市场热点 |
| 📊 [基金与 ETF](#基金与-etf) | 6 | 产品诊断、深度研究、经理研究和重仓股压力 |
| 📑 [债券研究](#债券研究) | 7 | 个券研究、利差分析和区域化债 |
| 🌐 [市场与政策](#市场与政策) | 2 | 宏观资金面和政策会议对比 |
| 🛡️ [企业与风险](#企业与风险) | 2 | 企业主体研究、风险与舆情监测 |
| ⚖️ [期货研究](#期货研究) | 1 | 单一期货合约研究 |
| 📝 [研报工作流](#研报工作流) | 2 | 底稿提取、预测复盘和研报复现 |
| 💻 [量化工具](#量化工具) | 1 | Choice API 接口选择与程序化取数 |
| **合计** | **47** | |

### 基础金融工具

查询是“查已知标的”，筛选是“按条件找标的”，自选管理是“操作自己的列表”。MQL 主要为研究流程提供底层取数能力。

| Skill | 用途 |
| --- | --- |
| [金融数据查询 · `mx-finance-data`](./skills/mx-finance-data/) | 查询行情、估值、财务等结构化指标，交付 Excel 与 Markdown |
| [金融资讯检索 · `mx-finance-search`](./skills/mx-finance-search/) | 按明确对象检索公告、研报、新闻和政策 |
| [宏观数据查询 · `mx-macro-data`](./skills/mx-macro-data/) | 查询经济、价格、货币、财政、贸易和产业数据，返回 CSV 与数据说明 |
| [私域知识库检索 · `mx-personal-kb-search`](./skills/mx-personal-kb-search/) | 检索用户明确指定的妙想知识库资料 |
| [金融问答 · `mx-financial-assistant`](./skills/mx-financial-assistant/) | 综合回答金融知识、数据、资讯和分析问题 |
| [条件筛选 · `mx-stocks-screener`](./skills/mx-stocks-screener/) | 按条件或排序筛选股票、基金、ETF、可转债、国内期货及板块等标的，返回 CSV 与数据说明 |
| [自选管理 · `mx-self-select`](./skills/mx-self-select/) | 查询 Choice 与东方财富 App 自选；新增、删除仅支持 Choice 的 A 股、港股、美股自选 |
| [MQL 标准取数 · `mql-query`](./skills/mql-query/) | 查询规范、语法约束、模板复用和 MQL 执行，供研究 Skill 复用 |

### 股票研究

#### 综合与专项诊断

以下 6 个诊断与专项分析 Skill 均面向沪深京 A 股单票；不应据此推断支持港股、美股或批量分析。

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
| [异动复盘 · `stock-price-anomaly-analysis`](./skills/stock-price-anomaly-analysis/) | 生成异动涨跌榜或单票复盘，默认 A 股，也定义了港美等市场的流程；实际可用范围取决于数据工具 |

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
| [市场热点发现 · `stock-market-hotspot-discovery`](./skills/stock-market-hotspot-discovery/) | 发现 A 股市场层面的热门资讯、股票和方向 |

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
| [利率债新券研究 · `primary-bond-deep-research`](./skills/primary-bond-deep-research/) | 分析单只利率债新券的发行定价、上市流动性与活跃券预期 |
| [利率债活跃券研究 · `on-the-run-bond-deep-research`](./skills/on-the-run-bond-deep-research/) | 分析活跃券收益率、资金面、供给和机构行为 |
| [利差分析 · `credit-spread-deep-research`](./skills/credit-spread-deep-research/) | 分析品种、期限、评级、信用、税收和流动性利差 |
| [地方化债研究 · `local-government-debt-analysis`](./skills/local-government-debt-analysis/) | 研究单个地区的经济财政、债务负担和化债进展 |

### 市场与政策

| Skill | 用途 |
| --- | --- |
| [宏观资金面研究 · `market-liquidity-deep-research`](./skills/market-liquidity-deep-research/) | 分析央行操作、银行间流动性和跨季资金面 |
| [政策会议对比 · `meeting-minutes-comparison`](./skills/meeting-minutes-comparison/) | 检索原文，经用户确认会议与维度后由模型比对，脚本生成 Word 文档 |

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
| [研报复现 · `sellside-research-refresh-with-excel`](./skills/sellside-research-refresh-with-excel/) | 定义沿原研报框架生成新研报、Excel 底稿和评测结果的流程；当前缺少必需 bundle，完整执行受阻 |

### 量化工具

| Skill | 用途 |
| --- | --- |
| [Choice API 程序化取数 · `choice-quantapi-skill`](./skills/choice-quantapi-skill/) | 查找 EMQuantAPI 文档、选择接口并生成 Python 取数代码 |

这里的“量化 API”沿用 Choice 产品名称。该 Skill 主要服务于程序化数据获取及策略研究的数据准备，本身不提供独立的交易或回测引擎。

## ⚙️ 安装与使用

### 选择安装范围

以下命令使用 [Skills CLI](https://github.com/vercel-labs/skills)，需要 Node.js 22.20 或更高版本与 npm；首次运行 `npx` 可能提示下载工具。安装源为本仓库 `GraceXiaoo/EastmoneySkills`。

列出可安装的 Skill：

```bash
npx skills add GraceXiaoo/EastmoneySkills --list
```

安装一个 Skill 到当前项目：

```bash
npx skills add GraceXiaoo/EastmoneySkills --skill stock-diagnosis
```

一次选择多个 Skill：

```bash
npx skills add GraceXiaoo/EastmoneySkills --skill mx-finance-data mx-finance-search stock-diagnosis
```

默认使用项目级安装；需要跨项目复用时，增加 `-g` 选择全局安装：

```bash
npx skills add GraceXiaoo/EastmoneySkills --skill stock-diagnosis -g
```

安装目标按工具提示选择。客户端兼容性取决于其 Skill 加载方式、脚本运行环境及所需工具连接，不能仅凭安装成功判断完整流程可用。

### 本地安装

下载完整仓库后，也可以从本地发现和安装：

```bash
git clone https://github.com/GraceXiaoo/EastmoneySkills.git
cd EastmoneySkills
npx skills add . --list
npx skills add . --skill stock-diagnosis
```

也可以按客户端的说明手动安装：将所需 Skill 的完整目录复制到客户端指定的位置，保留 `SKILL.md` 及配套资源，再加载或重启客户端。

### 描述你的研究任务

安装 Skill 之后，按对应说明准备服务授权、MCP 或 SDK，再用自然语言提出任务。例如：

```text
查询贵州茅台和五粮液最近一期营收与净利润，输出完整数据表。
分析宁德时代当前的资金面，并注明数据时间。
分析易方达蓝筹精选混合（005827），生成场外基金深度研究一页纸。
比较两次政治局会议的经济政策表述，引用原文来源。
提取这份研报的图表和数据，核验口径并建立 Excel 底稿。
```

提问时建议说明 **研究对象、时间范围、分析重点和交付形式**。例如：“分析某公司最近一期财报，重点关注利润质量与现金流，输出带来源的 Markdown 点评。”单标的研究应一次聚焦一个对象。

## 🔑 服务与依赖

实际运行需要相应的数据权限、服务连接和软件环境。Skill 安装与数据服务授权是两个步骤。

| 能力类型 | 运行前需要确认 |
| --- | --- |
| 妙想接口类查询、诊断和报告 | 对应服务可访问，按 Skill 内的授权流程完成身份验证；部分流程使用 `EM_API_KEY` |
| MQL 与依赖它的研究流程 | 客户端已连接相应 MQL MCP，并提供该任务所需的查询工具与数据权限 |
| 公告、资讯和研报检索流程 | 已连接 Skill 指定的文本检索服务或 MCP |
| Choice API 程序化取数 | Python、可用的 EMQuantAPI SDK、账号与接口数据权限 |
| 研报底稿抽取与研报复现 | 可访问的 `layoutV2` PDF 解析网关、有效 `EM_API_KEY`，并核对部署占位符或 `EM_BASE_URL` 配置；刷新 Excel 中的 `=mql()` 公式还需可用的 Choice Excel 加载项与权限 |
| HTML、Excel、Word、PDF 等交付 | 按对应 Skill 安装脚本依赖、文档生成与渲染工具 |

官方入口：[妙想 Skills 官网](https://ai.eastmoney.com/skills) · [东方财富·妙想对话](https://ai.eastmoney.com/chat)。具体授权流程、环境变量、工具名称和依赖版本请阅读所选 Skill。不同服务的凭据和数据权限可能分别管理。

密钥应保存在本地环境或服务指定的凭据位置，不提交到 GitHub，也不填写在 Issue 中。

支持扫码授权的 Skill 按内置流程完成授权；要求 `EM_API_KEY` 的脚本需要在运行前设置环境变量。仓库不内置可用密钥，个人密钥不应写回脚本、示例或参考文档。

## 💬 常见问题

### 相近的研究 Skill 怎么选？

| 需求 | 选择方式 |
| --- | --- |
| 快速综合判断股票或基金 | 选择 `stock-diagnosis` 或 `fund-diagnosis` |
| 只分析技术面、资金面等一个维度 | 选择对应股票专项分析 Skill |
| 生成公司、场外基金或 ETF 一页纸 | 选择相应的 `*-deep-research` Skill |
| 通过接口生成首次覆盖、行业或基金报告 | 阅读 `initiation-of-coverage-or-deep-dive`、`industry-research-report` 或 `fund-research` |
| 提取和核验现有研报 | 选择 `research-report-review` |
| 根据原研报框架生成新报告 | `sellside-research-refresh-with-excel` 定义此流程，但当前发布包缺少必需 bundle，需先修复 |

相近 Skill 的触发范围可能重叠。明确指定 Skill 或交付形式，有助于客户端选择正确流程。

### 所有市场和输出格式都支持吗？

不是。部分诊断仅支持 A 股，一页纸研究通常限定单标的，报告形式也可能分别为 Markdown、HTML、Excel、Word 或 PDF。请以各目录的支持范围为准。

### 为什么安装后仍无法运行？

优先检查服务授权、MCP 工具是否可见、数据权限和脚本依赖。仅复制 `SKILL.md` 可能遗漏脚本与模板，应安装完整目录。

### README 分类会影响安装吗？

分类只用于 README 导航。所有 Skill 均位于 `skills/` 下，按目录名独立安装；调整展示分类不会改变安装名称。

## 🗂️ 仓库结构

```text
EastmoneySkills/
├── README.md
├── README.en.md
└── skills/
    ├── mx-finance-data/
    ├── stock-diagnosis/
    ├── stock-deep-research/
    ├── fund-deep-research/
    └── …
```

每个 Skill 目录包含 `SKILL.md`，并按需提供 `scripts/`、`references/`、`reference/`、`assets/` 或示例文件。安装、复制和更新时保留完整目录，避免遗漏配套资源。

## 🤝 维护与反馈

发现问题或希望补充能力，可以通过 [Issues](https://github.com/GraceXiaoo/EastmoneySkills/issues) 反馈。为便于定位，请提供：

- Skill 名称及使用版本；
- 客户端、操作系统与相关运行环境；
- 可复现的任务描述、实际结果和预期结果；
- 脱敏错误信息或必要截图。

维护变更应同步更新 Skill 描述、版本、依赖和 README 导航，并检查目录链接、能力数量及对应执行流程。反馈与提交中不要包含账号密钥、私域资料或未经许可的数据。

## 📄 版权与使用

各 Skill、配套代码、模板和参考资料的权利归相应权利人所有，使用范围以各目录的许可证、版权声明及适用服务条款为准。当前部分 Skill 标注 `license: proprietary`；本仓库未声明统一的开源许可，公开展示不额外授予复制、再分发或商业使用的权利。

东方财富、妙想、Choice 及其他文中提及的产品名称和商标归各自权利人所有。金融数据、研报、公告及检索材料的访问与使用仍受对应来源的授权条款约束。

研究结果用于信息整理与分析辅助，不构成投资建议；涉及决策时，应核验数据时点、来源和计算口径。

### 文档与工具参考

本 README 的内容结合本仓库实际能力独立编写；信息组织参考了社区 Skill 仓库的概览、快速开始和分类导航实践，包括 [claude-skills](https://github.com/alirezarezvani/claude-skills) 与 [AliceMarket](https://github.com/Wind-Alice/AliceMarket)。安装示例使用 [Skills CLI](https://github.com/vercel-labs/skills)。这些项目的代码、文案与许可不自动适用于本仓库。
