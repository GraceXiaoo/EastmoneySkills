# 企业深度研究数据源说明

数据源规则已按通用规则、企业类型判定和分析板块拆分到 `references/data-sources/`，本文件作为稳定入口保留。

## 使用顺序

1. 读取 [data-sources/README.md](data-sources/README.md) 了解目录和板块映射。
2. 所有任务读取 [data-sources/common.md](data-sources/common.md)。
3. 企业类型判定读取 [data-sources/enterprise-type.md](data-sources/enterprise-type.md)。
4. 生成前 14 个板块时，只读取对应的数据源文件，例如基本情况读取 [data-sources/basic-info.md](data-sources/basic-info.md)，司法风险读取 [data-sources/judicial-risk.md](data-sources/judicial-risk.md)。
5. 重点关注读取 [data-sources/key-concerns.md](data-sources/key-concerns.md)，只接收前 14 个板块已生成的分析正文。

## 核心不变规则

- 前 14 个原始数据板块主路径必须使用 MQL；正式路径失败后先尝试已登记或动态发现的同业务 MQL 候选，全部候选失败时才使用当前板块的 Python REST 兜底。
- 每个板块的数据和资讯必须分别取数、分别登记、分别传入对应 prompt，不得跨板块混传。
- MQL 字段名、过滤字段和指标参数必须以当前 Runtime 实际可绑定名称为准。
- `重点关注`不取原始 MQL 数据、不取资讯，只使用前 14 个板块的已生成分析结果。

详细规则见 [data-sources/README.md](data-sources/README.md)。
