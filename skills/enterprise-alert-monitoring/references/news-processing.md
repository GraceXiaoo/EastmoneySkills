# 资讯准备、事件归并与输入交接

`scripts/build_news_package.py`负责从已经取得的原始返回自动生成候选和标准资讯包，`scripts/prepare_inputs.py`负责标准包的排序、截止过滤、完整资讯及来源绑定、提示词渲染。两者均不联网、不调用接口、不解析凭据、不生成分析。资讯分析材料唯一来源为`mx-finance-search`（事件库材料的获取与处理见[事件库获取](event-acquisition.md)与[事件库处理](event-processing.md)，两通道不混装）；主体确认信息和机构代码是内部身份元数据，不进入分析材料。`acquisition`是上游采集通道声明，不是脚本对真实调用的独立证明，上游必须保留真实检索底稿。

报告为五个展示模块，但资讯执行只有一个共享任务：一份标准包在同一次模型任务中生成舆情概览、重点事件、关联主体。风险发酵链路章单独交接三章最终正文加标准事件包（见[事件库处理](event-processing.md)）；第五章重点关注单独交接四章最终正文，详见下文“重点关注正文交接”。`build/compose/prepare`不接收重点关注正文，`prepare-concerns`不接收资讯包。三个前序章节键只用于结果标识及汇总槽位，不再代表三个搜索、候选子池、标准子包或模型调用。

## 自动生成与人工核验

原始返回文件和检索清单是生成器入口；模型不构造含全文的标准包。程序读取一次综合检索及必要定向补查原始文件，归一字段、生成稳定内部ID并建立一个平面候选池；模型只提交一份入选ID数组及必要最小已核验事件数组；最后程序回填标题、全文、URL、citation及元信息，组装一个标准输入包。

相关性筛选和事实归并需要阅读材料；字段复制、ID生成、元信息映射、原文回填和来源绑定由脚本执行。模型不得重抄资讯原文、URL、引用，不为每篇资讯生成冗长`claims/developments`，也不把内部ID拼成工具引用。`citation`缺失时留空；原始分类与权威度保持原值，由`scripts/source_authority.py`另行确定五档权威度V2及依据，不依机构印象或标题正文赋级。自动归一、来源存在和JSON格式通过均不等于事实已经核验。

全部检索结果回到同一个池，统一筛选一次，不按章分配或重复选择ID。逐条原始返回按实际条目保留；明确支持的文本格式可以解析，聚合回答不能按句子或段落虚构独立新闻。缺字段或格式不支持时记录缺口，不让模型补写原文或造来源以凑齐标准包。

### 原始文件与检索清单

将原始业务返回保存为文件，使用下列`search_runs.json`交接。它只记录任务和文件位置，正文不嵌入清单，也不是搜索API请求参数。相对`raw_result_path`按清单所在目录解析。默认只有一条综合检索；有明确缺口才追加补查，结果合入同池，不提供`block_keys`等分章路由。

```json
{
  "entity": {"name": "已确认企业全称", "confirmed": true},
  "context": {
    "start_date": "2026-10-01",
    "end_date": "2026-10-13",
    "data_as_of": "2026-10-13T18:00:00+08:00",
    "scope": "企业自身及资讯中明确涉及的关联事项"
  },
  "searches": [
    {
      "query": "实际执行且含具体期间的企业综合舆情检索问句",
      "kind": "initial",
      "raw_result_path": "raw/initial.json",
      "status": "success",
      "elapsed_seconds": 12.3
    }
  ]
}
```

以上为虚构格式示例。`status`使用实际`success/empty/failed/need_auth`；`elapsed_seconds`可省略，不进入分析。首条默认`kind=initial`，其后默认`supplement`且必须有非空`reason`说明具体缺口；只允许一条initial。必要补查记录形如`{"query":"含具体起止日及事项的补查问句","kind":"supplement","reason":"已命中事项缺少公司回应原文","raw_result_path":"raw/supplement.json","status":"success"}`。不能预设三章配额、按章搜索或用空泛理由机械补查。`success`不保证相关性或全量覆盖；空结果、失败与待授权不说明企业无风险。

原始文件优先使用搜索程序入口已有的原始业务返回；兼容提取文本时只按明确支持的稳定格式解析，不由模型重写。纯聚合回答保持一份`search_summary`材料，`material_kind`标明汇总性质；当只能使用材料标签时，`title_origin="material_label"`明确其不是原始新闻标题。标记用于保留事实边界，不能把汇总当成逐条新闻统计或声称其来源已核验。字段和溯源不足时保留待核验状态，不进入需要真实来源支持的正式报告。

支持的原始业务返回包括包裹在`raw/data/result`及`llmSearchResponse`内的逐条数组、已有`items/articles/newsList`等条目数组，以及明确的汇总文本。2026-10-14实测返回的数组路径为`raw.data.llmSearchResponse.data`，生成器直接读取各条`title/content`，将`date`保留为`published_at`、`jumpUrl`保留为`url`、`informationType/authorityLevel`复制到归一字段。原始时间可为`YYYY-MM-DD HH:MM:SS`，解析时按真实时区或上海时区处理，值不改写。不同URL路径或同一URL下不同正文片段分别保留；只有归一业务字段完全一致的记录才复用稳定ID，并在`origins`保留全部实际检索出处。

`code/recallIndex/rankScore`不是原生引用，不能转换成`citation`。实测返回未提供原生引用时保留空值及真实URL；来源名、分类或权威度缺失时不补写原始字段。诸如`L1/L2/L3`、`L1-3/L2-1`及“高/低”的完整权威度原值仍保留，它们不单独决定本技能的V2等级，也不根据后缀自行创造等级。V2只采用下述有据来源规则；例如真实`NOTICE`可派生“公司公告或官方网站等／较高”，但不能据此把原始`source_category`改成该类别。该边界不影响原文与URL搬运。

### 两阶段生成与小规模选择

使用当前平台Python 3.10及以上解释器：

```text
<可用Python> -X utf8 "<skill目录>/scripts/build_news_package.py" build --manifest "<工作目录>/search_runs.json" --out "<工作目录>/candidates"

# 读取candidate_index.md后，按待核验ID查看原文；不打印整包再让模型搬运
<可用Python> -X utf8 "<skill目录>/scripts/build_news_package.py" inspect --bundle "<工作目录>/candidates/candidate_bundle.json" --ids <资讯ID1> <资讯ID2>

<可用Python> -X utf8 "<skill目录>/scripts/build_news_package.py" compose --bundle "<工作目录>/candidates/candidate_bundle.json" --selection "<工作目录>/review.json" --out "<工作目录>/composed"

<可用Python> -X utf8 "<skill目录>/scripts/prepare_inputs.py" prepare --input "<工作目录>/composed/news_package.json" --out "<工作目录>/prepared"
```

`build`输出`candidate_bundle.json`、`candidate_index.md`及`build_audit.json`。候选包包含统一`catalog`、平面`candidate_ids`数组、实际检索`queries`列表及逐ID的`origins`，没有分章候选映射；索引含V2标签，审计记录实际来源与计数。`compose`输出一个`news_package.json`及`compose_audit.json`。两阶段输出使用新的任务目录，不覆盖原始文件。生成器不联网、不请求授权，检索执行仍由资讯技能负责。

模型读取索引并按需查看原文后，只写一份`review.json`，用一个平面数组选择相关材料。应兼顾总体舆情、正中负事项、重要进展及有据关系，不只保留最负面的热点。下面ID为虚构示意，应换成候选已有ID，不生成新ID：

```json
{
  "selected_ids": ["候选已有ID"],
  "events": []
}
```

`events`可省略，确需事件时提供平面最小核验事件数组，字段契约见“可选事件契约”。它只记录已核验主体、事项键、简明标题及支持ID，不复制资讯全文或元数据。未知ID或事件引用未入选支持ID报错。不接受按章映射的`selected_ids/events`，不登记跨章复用，也不建立三份相同items。

选择清单、候选索引和生成器审计均为内部材料，不塞进`{{资讯}}`或交付附件；正式分析只使用准备器唯一`shared-analysis`任务的`prompt`。前三章规则都在该模板内，资讯带入一次并生成三章。URL真实可访问性及其是否支持事实仍须核验。

生成器对每条候选的内容与来源字段生成稳定指纹，派生`source_assessment`不参与指纹计算；更新分类规则不会改写原材料或使其稳定ID变化。`compose`会复核指纹，禁止修改原文、URL或引用后继续沿用旧ID；需要更新时从新的原始返回重新生成。`compose`与`prepare`都从原始元数据重新计算评估，不信任候选包或选择清单提交的派生结果。组成标准包的标题、正文和来源来自候选目录，选择清单不能提供替换的`items`全文。审计记录选择清单字符量、候选正文字符量和脚本阶段耗时，不把脚本耗时当作完整报告耗时，也不将缺少历史基准的测量宣称为整体提速比例。

## 标准输入包（生成器产物）

下面的JSON描述`build_news_package.py`生成、交给`prepare_inputs.py`的产物契约，不是要求模型逐条填入原文的模板。模型只编写体量较小的选择和必要核验结果；正文与元数据均由程序回填。

顶层必需：`acquisition: "mx-finance-search"`、`entity`、`context`、`news_queries`、`items`；`events`可省略并默认为空数组。不存在分章`blocks`。不接受`mql/datasets/generated_analysis/analysis_results/block_data_packages`业务包或旧分章结构；条目声明其它`acquisition`也拒绝。

```json
{
  "acquisition": "mx-finance-search",
  "entity": {
    "name": "已明确确认的企业全称",
    "confirmed": true,
    "org_code": "10000069733"
  },
  "context": {
    "start_date": "2026-10-01",
    "end_date": "2026-10-13",
    "data_as_of": "2026-10-13T18:00:00+08:00",
    "scope": "企业自身及资讯中明确涉及的关联事项"
  },
  "news_queries": [{"query": "实际综合检索问句", "kind": "initial", "status": "success", "returned_count": 1}],
  "items": [
        {
          "id": "news-a",
          "title": "原始资讯标题",
          "content": "原始资讯正文或检索返回的有效摘要",
          "source": "原始来源机构",
          "published_at": "2026-10-10",
          "url": "https://example.invalid/news-a",
          "citation": "[source:原始工具引用标记]",
          "source_category": "announcement",
          "authority_level": "L1",
          "information_type": "NOTICE",
          "source_assessment": {
            "source_category_v2": "公司公告或官方网站等",
            "authority_v2": "较高",
            "priority": 1,
            "basis": "explicit_source_category"
          }
        }
  ],
  "events": []
}
```

以上是虚构版式样例，`example.invalid` 不是真实资讯来源。脚本只校验 URL 的 HTTP(S) 格式和无凭据，不访问链接，也不声明验证了网页或资讯真实性。

### 主体和期间

- `entity.name` 非空且 `confirmed` 必须为布尔值 `true`。同名/简称候选不能自动选中；应由上游结合用户信息明确实体。
- 已确认全称可在代码缺失时继续；`org_code` 缺省、空串或 `null` 不生成替代代码。若提供，必须是完整数字字符串（8–32位，可带 `.FXR`）；原样保留，不截断、不转整数、不用6位股票代码代替。格式通过并不证明代码和名称匹配，主体核对仍由上游负责。
- `data_as_of` 必填，使用客户端确定的截至日/时间，不从主机日期猜测。可用 ISO 日期或带 `T` 的 ISO 时间，建议带 `+08:00`；无时区时间按 Asia/Shanghai 解释。
- `start_date/end_date` 为真实 `YYYY-MM-DD`，且 `start <= end <= data_as_of` 的上海日期；两端均包含。主流程先按 [时间范围识别](time-resolution.md) 从问句解析并显式传入。仅当任务未指定期间时，`end=data_as_of` 日期、`start` 为 `end` 回溯1个日历月的同日（不存在该日时取目标月末），即默认近一月，并明确写入资讯投影。它不固定为30天，也不替代对原问句的解析。
- 业务`context`严格只投影`start_date/end_date/data_as_of/scope`；查询、身份代码、audit及其他未知字段不投喂。逐条原始材料的`id`只为词云标签来源绑定保留在输入内，不能当作引用或报告文字。不能把内部状态的通用键名递归删除后当作业务投影。

### 共享资讯记录

`news_queries/items`均为顶层数组，可空；`events`为顶层数组，可省略。事件支持ID必须存在于统一`items`。全部资讯统一去重核验、排序、截止过滤及来源绑定，完整保留有效资讯和核验事件；三个输出章节共用同一保留集合，不再分别选择、复制或绑定材料子包。一次检索不保证全量声量，最终统计只据真实保留样本。

条目必需`id/title/content`，标题与内容非空；由生成器直接复制`source/published_at/url/citation/source_category/authority_level/information_type`等可用元数据。元数据缺失可留空，不能补造；`published_at`无法解析时保留原值并后置，不替换成抓取日。原始URL、citation、来源机构至少有一项可用；没有URL或引用标记但原始机构明确时，允许保留标题正文用于内部核验，内部分析只能写真实文字归属，不能编造链接/引用。正式正文、词云与HTML冻结前仍须核实真实原始URL，不能把输入可用等同于交付溯源合格。连原始出处也无时拒绝。citation逐字保留、不重编号。URL、标题、机构和原始时间随内容保留。

## 资讯条目字段归一

归一由生成器整理共享池的原始返回，不重写正文、追加模型摘要或补造来源元数据。以下是本技能本地JSON字段，不是搜索API字段声明：

| 归一字段 | 保留内容 | 处理规则 |
|---|---|---|
| `title` | 完整原始标题；汇总无原标题时为明确标记的材料标签 | 不改写成模型观点，材料标签必须带`title_origin="material_label"`边界 |
| `content` | 完整原始正文或搜索实际返回摘要 | 非空；已有正文时不临时生成短摘要替代 |
| `source` | 原始机构或来源名称 | 原值保留，不由标题猜测 |
| `source_category` | 原始来源分类 | 缺失为空，保留原值；已识别类别作为V2依据 |
| `authority_level` | 原始权威度文本或等级 | 原始`authorityLevel`提供时优先沿用其值；不作为V2排序键、不推测编码 |
| `information_type` | 原始资讯类型，如`NOTICE/REPORT/NEWS/LAW/BOND` | 原始`informationType`提供时优先沿用其值；未知类型原样保留，缺失为空 |
| `source_assessment` | 派生V2分类、权威度、优先级与依据 | 脚本从原始元数据计算的`{source_category_v2,authority_v2,priority,basis}`，不覆盖原始字段、不由模型填写 |
| `published_at` | 原始发布时间 | 不以抓取日、系统日、事件发生日替代 |
| `url` | 真实原文URL | 不拼造地址；正式交付前仍核实可访问性 |
| `citation` | 工具实际返回的原始引用 | 原样保留与材料绑定，不用本地编号替代 |

聚合返回可另保留`material_kind/title_origin`边界标记，使后续分析能够区分原始新闻、搜索汇总和程序生成的材料标签；这些标记不改变原文、来源优先级或引用，不将材料标签冒充新闻标题。

`id`由生成器按原始记录生成并在重复读取时保持稳定，用于一次统一选择、本地事件绑定、词云标签来源绑定与审计。共享prompt逐条提供该ID供填写内部标签文件，但它不是citation，不能作为正式来源引用或报告内容。`information_type`与`source_category`是两个独立原始字段，缺失不补写，缺口登记内部审计。真实`NOTICE/REPORT`可作为下述派生V2依据，不能改写原始分类。

## 来源分类与权威度V2

来源分类与权威度采用以下固定对应，`priority`越小越优先：

| `priority` | `source_category_v2` | `authority_v2` |
|---:|---|---|
| 0 | 专业数据库数据 | 最高 |
| 1 | 公司公告或官方网站等 | 较高 |
| 2 | 研报或权威新闻媒体等 | 中等 |
| 3 | 互联网检索资讯 | 较低 |
| 4 | 其它社区或自媒体消息 | 极低 |

无法识别时记录分类与权威度“未知”、`priority=5`，放在已识别来源之后；未知是缺少依据的后置状态，不是第六档。保留原始`source_category/authority_level`，另外记录`source_assessment={source_category_v2,authority_v2,priority,basis}`。不再使用旧的“专业数据库／其它信源”二分类叠加独立七级权威度排序。

分类程序按以下顺序取第一个有依据的结果，明确别名、媒体名单和域名列表集中维护在`scripts/source_authority.py`，模型不临时扩展名单：

1. 原始`source_category`与已配置的明确分类或别名匹配时，直接采用其五档V2。只为匹配去除前后空白、统一英文大小写，原始值不改写；仅明确专业数据库分类及其已配置别名可进入最高档。
2. 没有可识别显式分类的`search_summary`直接未知，不按聚合包上的某一个类型、机构或URL给全部底层事实赋级。
3. 对逐条原始材料，真实`information_type=NOTICE`归公告／较高，`REPORT`归研报／中等；两者均不能归专业数据库。
4. 原始`source`精确匹配已配置权威媒体名称时归中等；这一步先于微信等分发类型，因此权威媒体的微信号保留媒体归属。
5. 原始URL的实际主机严格匹配已配置官方域名或其真实子域名时归较高，再匹配已配置媒体域名时归中等；不使用URL文本包含匹配，仿冒后缀不算匹配。官方域名规则当前覆盖`gov.cn/sse.com.cn/szse.cn/bse.cn/cninfo.com.cn`及其真实子域名，未配置的企业官网不能仅凭名称印象赋级。
6. 未被上述更强依据识别的`WECHAT/SOCIAL/FORUM/SELF_MEDIA`归其它社区或自媒体／极低；`INV_NEWS`归互联网检索资讯／较低。
7. 其余来源未知；`NEWS/LAW/BOND`以及原始权威度文本或编码本身不能单独决定V2。无法识别的显式分类仍保留原值，再以实际类型、已配置来源或域名继续判定；都无依据才未知。

不因`mx-finance-search`基于数据库、来源名称含“数据库”或原始权威度为`L1`而归为专业数据库。所有分析材料仍只由`mx-finance-search`取得，此规则不引入结构化取数通道。V2用于信息来源优先级，不是企业风险等级，不自动裁决相互冲突的事实。

## V2与发布时间排序

唯一等级排序键为重新计算的`source_assessment.priority`，原始`authority_level`不另行排序。最终稳定排序为“权威度由高至低（V2优先级由小到大）→ 同档发布时间由近及远 → 并列保持原输入顺序”。未知权威度置于已识别档位之后，同档缺失或无法解析的发布时间后置，保留原值；时间按真实时区比较，同一时点保持原输入顺序，不能用抓取时间、报告日或事件发生日补造发布时间。相同标题、相似文本和转载不自动触发事件合并，原始信源及其引用保留。

## 截至快照

截至快照先排除**截至后才公开**且发布时间可解析的完整条目，相关事件缺任何支持源也整体剔除。发布时间未知/不可解析的条目可以保留，但明确标注“披露日期未核验，不能证明截至时点已知”，不参与截至状态判断。脚本不猜原文语义；上游须核验披露时间，历史报告不得用未知日期材料证明当时已知。

## 可选事件契约

`events`允许为空。仅当同一事项归并、阶段区分、关系证明或跨章一致性确有需要时，由模型阅读材料核验后显式给出最小事件；不可由脚本按近似标题猜测，不要求每条资讯建立一个事件，也不为了完整schema重复摘抄长篇原文。默认优先使用下列最小结构；日期、阶段、关系、claims及developments仅在核验确有需要时补充：

```json
{
  "verified": true,
  "subject": "事项实际发生主体全称",
  "event_key": "稳定案号或模型核验后的固定事项键",
  "title": "事项名称",
  "source_ids": ["候选已有且在共享items入选的ID"]
}
```

- 事件必需`verified/subject/event_key/title/source_ids`；`claims/developments`默认空，日期未知用空串。`verified=true`是模型阅读原文后明确给出的核验声明，生成器不自动填真；缺少明确核验的事件不能进入正式标准包。脚本不能代替事实核验。
- 所有`source_ids`必须存在于共享`items`；每条claim、progress、关系声明的引用须是该事件`source_ids`的非空子集。仅存在ID并不证明引用内容支持断言，上游须逐事实核验。
- `relationship`如给出，必须附`relationship_source_ids`。归并后兼容保留字符串数组`relationships_disclosed`，另以`relationship_evidence:[{text,sources}]`逐关系保留直接支持出处，不能用事件总体出处代替关系事实的直接出处。不同主体同一key绝不合并；子公司、股东或区域关联风险不自动归为目标企业自身风险。代码不查询关系图谱。
- 自动归并仅针对**完全一致的`subject + event_key`**。相同事实合并其支持引用；不同事实、不同金额保留，绝不求和。可选`fact_key`配`as_of`帮助检测同一事实位置的矛盾；没有该键仍保留不同原始事实，不声称自动找全矛盾。
- `amount/currency/unit`均为原文对应的字符串，不做币种转换、单位猜测或数值累加。业务投影不含`fact_key/event_key/source_ids`，其引用改为原始标题、URL、citation等信源对象。
- 进展按提供日期保留；发生日期冲突和未知不按发布时间推断新增。旧事项有本期明确进展时列为“历史事项，本期有已核验进展”；旧事新转载不等于新事件。
- 明示状态允许`unknown/planned/approved/received/ongoing/clarified/released/resolved/withdrawn`。只有明确日期且不晚于截至时点的披露可参与最新状态；同一最新时点状态冲突则不选择。无状态日期不得用发布时间代替。
- event/claim/progress可附`statement: "fact" | "plan"`，默认`fact`。截至后才发生/完成的顶层事件整体剔除；未来完成进展和标明未来`as_of`的事实在输入副本剔除并审计。截至前已公开、明确为`plan`或`status=planned`的未来计划/到期节点可保留并注明不是已发生/完成。到账、澄清、解除、处置、撤回等完成状态不能伪装为计划保留。原始信源正文不切片，上游必须先核验其事实时间语义。
- 计划/获批不等于到账；澄清不自动等于解除；解除/处置/撤回仅适用于原文明确事项，不清除其他风险。持续、已澄清、已解除等是事件进展，不是企业总风险分档。

## 完整材料与来源绑定

一条完整资讯是一个信源单元，包含标题、原始正文/返回摘要、必要元数据、URL和引用。筛选与截止过滤作用于送入分析的副本，原始返回、完整归一包及审计分别留档，不覆盖原材料。

唯一`shared-analysis`完整prompt包含固定模板、企业名称、context、完整有效信源、正文、核验事件及引用。该执行模板仅有`{{企业名称}}/{{资讯}}`，各出现一次；缺少、重复或存在其他占位符报错，只替换一遍，原文花括号不触发第二轮。

按上述稳定排序完整传入有效信源记录，保留原文、URL及原始引用。核验事件与直接支持源绑定，全部支持源必须仍在有效集合中；截至过滤或来源核验导致支持源缺失时，相关事件同步移除，避免残留无来源的事实或状态。

有效材料为空时共享任务状态为`empty`，允许准备成功，但不等于企业无风险。三个资讯章节共用同一有效集合；发酵链路章另用事件包。样本或来源变化后重核概览统计及相关判断，再重新交接后续章节与重点关注。审计保留真实查询状态和过滤情况，不能把“没搜到”解释成全面排除风险。

## 资讯输出与CLI

使用当前平台的Python 3.10及以上解释器，按实际位置替换以下路径：

```text
<可用Python> -X utf8 "<skill目录>/scripts/prepare_inputs.py" prepare --input "<工作目录>/news_package.json" --out "<工作目录>/prepared"

# 可选：使用另一个包含shared-analysis.md的模板目录
# --prompts-dir "<目录>"

# 只呈现已有候选；不取数、不自动确认，输入为 {"candidates":[{"name":"...","org_code":"..."}]}
<可用Python> -X utf8 "<skill目录>/scripts/prepare_inputs.py" resolve-candidates --input "<工作目录>/candidates.json"
```

默认模板目录`references/analysis-prompts/`，`prepare`只加载`shared-analysis.md`并生成一个模型输入。`--out`为输出目录，写两个UTF-8 JSON；目标已存在或会覆盖输入时拒绝，不修改原资讯包。成功退出0，输入/模板/输出错误退出2。

`prepared_inputs.json`结构：

```text
schema_version: "1.0"
entity: {name}                              # 不含身份代码
context: {start_date,end_date,data_as_of,scope}
blocks: [
  {
    key: "shared-analysis",
    output_blocks: ["monitoring-overview","key-events","related-environment"],
    status: "ready" | "empty",
    prompt_data: {
      context,
      items: [{id,title,content,source,published_at,url,citation,source_category,authority_level,information_type,source_assessment,
               material_kind?,title_origin?}],
      events: [{subject,titles,event_dates,attribution,relationships_disclosed,relationship_evidence,
                period_assessment,latest_dated_status,status_observations,
                claims,developments,sources,conflict_note?,status_note?}]
    },
    news_text,                             # 实際替换{{资讯}}的完整材料
    prompt,                                # 实际分析输入
    prompt_length
  }
]
```

事件的`claims/developments/status_observations`以`sources`列示支持原文；每个信源对象精确为`{title,source,published_at,url,citation}`。供渲染器核对引用与事件事实，不拼入内部ID。

### 实际传入提示词的资讯文本

输入JSON用于本地准备和留档，不能把含查询状态、审计及其他内部字段的整个顶层包塞入`{{资讯}}`。适配器将统一保留集合投影为一份`news_text`，只保留词云绑定所需的逐条材料ID，并仅替换一次`shared-analysis.md`的`{{资讯}}`；唯一`prompt`才是送入同一次前三章分析任务的完整字符串。文本结构如下（仅示意，尖括号须由真实材料替换）：

```text
监测期间：<起始日> 至 <截止日>（含两端）
资讯截至：<统一截止时点>
范围说明：<本次业务范围>
<材料范围及不得从空结果推导无风险的固定约束>

资讯原始信源
材料ID（仅供词云标签绑定，不作来源引用、不写报告）：<该条已有ID>
标题：<完整原始标题；无原标题的汇总明确为材料标签>
<material_kind/title_origin提供时保留其材料性质和标题边界说明>
来源机构：<原始机构>
发布时间：<原始发布时间>
日期核验：<实际解析状态>
原文URL：<真实原文地址>
原始引用：<工具返回引用>
来源类别原值：<原始分类>
权威度原值：<原始权威度>
资讯类型原值：<原始informationType或information_type>
来源分类（V2）：<脚本派生的五档分类或未知>
权威度（V2）：<脚本派生的权威度或未知>
正文：<完整原文或搜索实际返回摘要>

<按最终排序重复完整信源单元>

已经显式核验并归并的事项（仅依赖上述原始信源）
<入选事件的业务JSON及其直接来源对象；没有事件时不输出这一段>
```

缺少非必需元数据时，适配器仅在内部输入标明其缺失或日期核验边界，不伪造字段；这些状态不写进正式报告。V2类别与权威度作为材料标签传入分析，分类依据`basis`及优先级数字`priority`留在本地结构和审计，不投喂正文。完整保留信源标题、元数据、正文、事件业务JSON和原始引用。事件业务JSON中的`sources`是实际原文绑定，与`audit.json`的查询/内部ID记录有别；不得移除真实引用，也不得把审计对象当作业务来源。

`audit.json`保存唯一共享任务的查询状态、排序与保留ID、`prompt_length`、V2及依据、缺失元数据、截至后公开材料、未来事实及事件归并/过滤记录。查询记录保留实际query、initial/supplement、补查理由及执行状态，不复制凭据、请求头或未知包装字段。底稿位置只指向已剥离凭据的业务返回；事件审计不证明事实已经核验。审计不进入分析prompt或正式报告。

## 重点关注正文交接

重点关注不从资讯检索生成，只读前四模块（含风险发酵链路）已完成并经来源核验的最终分析正文及其随文有效原始引用。运行时/程序从已保存的四章结果直接交接以下结构，不要求模型再次重抄完整正文JSON，也不为每点或每章创建资讯items。每个槽位直接保存对应章最终正文及随文引用；无有效正文的章节、内部“暂无数据”或“暂无数据。”统一置空。发酵链路正文按[事件库处理](event-processing.md)经`prepare-fermentation`生成后并入本交接。

```json
{
  "entity": {"name": "已确认企业全称", "confirmed": true},
  "analysis_results": {
    "monitoring-overview": "",
    "key-events": "",
    "related-environment": "",
    "risk-fermentation": ""
  }
}
```

顶层只允许`entity/analysis_results`；`entity`与资讯流程使用同一已确认主体，可选保留原完整机构代码。`analysis_results`必须恰好上述四个字符串槽位，按报告顺序固定，对应`{{舆情概览内容}} / {{重点事件内容}} / {{关联主体内容}} / {{风险发酵链路内容}}`。重点关注提示词只接受这四种占位符与`{{企业名称}}`，不接受`{{资讯}}`和`{{事件库}}`。以对应章最终正文原文交接，不在准备阶段摘要、重新分析、修改数值或换金额单位；原始引用与真实原文URL逐句保留，章节名或生成正文不替代原始来源。

```text
<可用Python> -X utf8 "<skill目录>/scripts/prepare_inputs.py" prepare-concerns --input "<工作目录>/analysis_results.json" --out "<工作目录>/concerns-prepared"

# 可选 --prompts-dir "<目录>"，其中提供key-concerns.md
```

完整重点关注input包含固定提示词、企业名、四章有效正文（含风险发酵链路）、随文引用及分隔文本。按固定四槽位报告顺序完整交接，保持原正文和引用，不对生成正文重新标记信源分类或V2权威度。四槽位都为空时状态为`empty`，内部输出“暂无数据”，最终报告略去本章；不以缺失推断企业无风险。

产出与普通准备器同名的`prepared_inputs.json/audit.json`，使用新的输出目录且不覆盖输入。准备结果含单个`key-concerns`块：

```text
schema_version: "1.0"
entity: {name,confirmed,org_code?}
blocks: [{
  key: "key-concerns",
  status: "ready" | "empty",
  prompt_data: {
    analysis_results: {三个固定键: 完整有效正文或空字符串},
    prompt_inputs: {企业名称,舆情概览内容,重点事件内容,关联主体内容},
    active_blocks: [实际保留的章节key],
    empty_blocks: [无有效正文的章节key]
  },
  prompt,
  prompt_length
}]
```

只有`prompt`用于模型汇总，`prompt_data`供本地核对；`audit.json`记录有效章节`kept_keys`、原始空槽位`original_empty_keys`、各槽位字符量`input_lengths`及`prompt_length`，不进入分析。原始交接包和三章完整底稿仍保留。模型依据[重点关注执行提示词](analysis-prompts/key-concerns.md)提炼、合并及排序观点，继承支持各观点的逐句原始引用；分析与正文写作规范在该提示词内维护。

前三章事实或来源需修正时，回到共享池核验并同步修正受影响正文与概览统计；若需补查，注明具体缺口后回同池。再重新交接并生成重点关注，报告采用修正后的最终正文与来源。汇总流程自身不新增mx查询、不读原始材料补事实，也不将总结反向作为前序资讯，从而避免循环。

## 词云内部交接

共享分析另外保存最小事件类型标签文件，材料ID仅在此绑定原始条目；不抄写原文、URL或citation，标签独立留档。标签格式、原包与标签文件的CLI、计数边界及图片复用统一见[词云与图文衔接](visual-assets.md)。词云不另取资讯，使用同一最终有效集合，原始包及审计仍分别留档。

## 本地验证

时间入口的解析与查询约束也由self_test验证：用户三个例句、日历月回溯、近30天、本周/上周、历史期末截至、月末/闰年、时区及无法解析时不退回默认。具体规则与辅助器入口见 [时间范围识别](time-resolution.md)。

输入准备允许保留仅有真实机构/标题/时间而缺少URL的材料供内部核验；这不代表其满足正式HTML的可查看溯源条件。词云绘制及正文冻结前，须按[输出与验收](report-output.md)通过同一资讯渠道核实真实原始链接，将最终事实与有效来源绑定。无法有效溯源的事实及依赖内容从两端共用内容同步移除；有其它充分有效来源时仅移除无效引用。输入脚本的格式验证不证明URL可访问，也不生成“来源”图标或弹窗。

运行`python scripts/self_test.py`、`python scripts/test_build_news_package.py`及`python scripts/test_key_concerns.py`。离线行为验证使用虚构材料，覆盖单一综合检索记录与有理由补查、平面候选/选择/事件引用、旧分章结构拒绝、原文与来源保真、V2重算及稳定排序、客户端期间、截至快照、未来计划与完成区分、完整资讯与核验事件保留、一个共享prompt生成三章、三最终正文及引用完整交接、CLI不覆盖等。具体测试数量以实际运行结果为准。离线验证不执行真实取数，不证明资讯真实性、平台绘图或HTML附件卡片成功；实际输出仍按[输出与验收](report-output.md)核验。
