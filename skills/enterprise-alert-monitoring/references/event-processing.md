# 事件库准备与发酵任务交接

`scripts/build_event_package.py`负责从事件库两接口的原始返回生成候选和标准事件包，`scripts/prepare_inputs.py`的`prepare-fermentation`子命令负责事件包的排序、截止过滤、渲染唯一`risk-fermentation`输入。两者均不联网、不调用接口、不解析凭据、不生成分析。事件材料唯一来源为事件库两接口的原始返回；主体确认信息是内部身份元数据，不进入分析材料。

## 通道契约

事件包`acquisition`为`mx-api-invoke`，与资讯包的`mx-finance-search`严格分离：两通道的items不混装、不复用稳定ID前缀（事件条目`evt_`、资讯条目`news_`）、不互相回填。事件条目的`material_kind`只有两类：`event`（已发生事件）与`future_event`（未来预期事件），由生成器按来源接口写入，不由模型声明。

标准事件包顶层为`acquisition/entity/context/event_queries/items`，没有`events`数组（事件库条目本身就是事件，不需要再建核验事件层）、没有分章blocks。

## 自动生成与人工核验

程序读取原始返回，归一已知字段（标题、摘要、机构、发布时间、URL、事件分类、风险标注等），生成稳定内部ID并建立平面候选池；模型只提交一份`selected_ids`数组；程序回填完整条目。`title/content`来自接口`eventTitle/eventMessage`与`eventDigest/eventMessage`的原文，不改写；`citation`字段留空（接口不提供原生引用标记，不以`code/rankScore`等字段伪造）。URL缺失时保留`infoCode`（信息编码）作为溯源线索，不编造链接。

接口返回的`highLight*`字段（HTML高亮版）不单独入池；`medianame`映射为`source`（来源机构）；`riskLevel/risk`映射为`risk_level/risk_flag`原值。同一`infoCode`的重复条目只保留一次。接口返回的字段缺失不补写、不推测。

## 两阶段生成与小规模选择

```text
<可用Python> -X utf8 "<skill目录>/scripts/build_event_package.py" build --manifest "<工作目录>/event_runs.json" --out "<工作目录>/event_candidates"

# 读取candidate_event_index.md后，按待核验ID查看条目详情
<可用Python> -X utf8 "<skill目录>/scripts/build_event_package.py" inspect --bundle "<工作目录>/event_candidates/event_bundle.json" --ids <条目ID1> <条目ID2>

<可用Python> -X utf8 "<skill目录>/scripts/build_event_package.py" compose --bundle "<工作目录>/event_candidates/event_bundle.json" --selection "<工作目录>/event_review.json" --out "<工作目录>/event_composed"
```

`build`输出`event_bundle.json`、`candidate_event_index.md`及`event_build_audit.json`；索引含条目类型（已发生/未来预期）、标题、时间、主体、事件分类、接口风险标注与V2标签。模型阅读索引并按需`inspect`原文后，只写一份`event_review.json`：

```json
{
  "selected_ids": ["候选已有ID"]
}
```

选择应覆盖：目标企业自身的已发生风险事件与正面事件、发酵判断必需的未来事件节点（到期、兑付、审批、会议）、经资讯证实的关联主体条目。事件主体与目标企业无关且无关联证据的条目不入选。同一事件多阶段条目合并入选，不因重复出现增加权重。

## 发酵任务准备

三章正文冻结后构造发酵输入并运行：

```text
<可用Python> -X utf8 "<skill目录>/scripts/prepare_inputs.py" prepare-fermentation --input "<工作目录>/fermentation_input.json" --out "<工作目录>/fermentation_prepared"
```

`fermentation_input.json`结构（四章正文中前三章为最终冻结正文）：

```json
{
  "entity": {"name": "已确认企业全称", "confirmed": true},
  "analysis_results": {
    "monitoring-overview": "舆情概览最终正文",
    "key-events": "重点事件最终正文",
    "related-environment": "关联主体最终正文"
  },
  "events": {"acquisition": "mx-api-invoke", "entity": {...}, "context": {...}, "event_queries": [...], "items": [...]}
}
```

准备器对事件条目按权威度V2降序、同档发布时间降序排序并执行截止过滤（`publishTime`晚于`data_as_of`的条目剔除，与资讯口径一致）；未来事件的预计发生时间不做截止剔除——晚于期末的预计节点正是分析对象，早于截至时点的预计节点在渲染中标注“须核对实际状态”。事件包`entity`须与本次运行主体一致（名称必须相同，`org_code`同时存在时须一致）；`context`的监测起止日须与运行一致。

渲染后的`prompt`含五个占位符替换结果：企业名称、事件库材料（含条目类型、主体、分类、接口风险标注及其边界说明）、三章正文。事件库材料整体只传入这一次。

## 审计与边界

- `prepare-fermentation`输出`prepared_inputs.json`及`audit.json`（含事件查询记录、保留/剔除条目、两类条目计数、元数据缺口）；审计不进入分析正文。
- 事件条目无URL时，正文引用以信息编码标注，HTML溯源弹窗中如实显示“接口未提供原文链接”，不伪装可点击来源。
- 接口风险标注（正面/中性/负面）在渲染材料中附带边界说明：它是数据源情绪分级，不是企业风险等级或发酵结论。分析时发酵判断独立论证，不受该标注约束。
- 事件包选择修正（增删条目）后重新运行`prepare-fermentation`，三章正文不受影响。
- 离线fixture测试不证明实际接口调用成功；每次实际运行仍须核对原始返回状态与条目真实性。
