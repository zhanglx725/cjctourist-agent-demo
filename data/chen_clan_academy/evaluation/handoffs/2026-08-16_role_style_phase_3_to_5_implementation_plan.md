# 18 风格贯穿式讲解与后续产品阶段实施方案

## 1. 文档目的

本文用于交接和持续更新以下工作：

1. 18 种风格的点位讲解在“工艺背景”和“观察对象/纹样”中都贯穿人设；
2. 游客确认风格后，普通问题和追问继承同一风格；
3. 游览前、游览中和复合指令中都能安全切换风格；
4. 为阶段 3 收口、阶段 4 实施和阶段 5 以后的长期路线提供统一任务基线。

本文是实施计划，不代表其中所有项目已完成。状态只能依据代码、自动化测试和已保存的 LangSmith 人工验收证据更新。

---

## 2. 当前基线与验收结论

### 2.1 当前工作区基线

```text
branch: experiment/agent-orchestration-v2
local_full_regression: 1227/1227 OK
git_diff_check: passed with existing CRLF warnings only
commit_or_push_for_current_local_changes: not performed
```

当前本地已包含：

- 复合引导输入可以一次生成路线，不再只返回角色确认；
- QA Active 已支持保留旧审核答案的自然分段，不再被点位“全文禁止换行”规则误伤；
- QA 候选通过时已有 `active_takeover=true`、`fallback_used=false` 的真实 Trace；
- 角色切换不修改当前路线和游览进度。

### 2.2 阶段 3A 人工验收结论与新增缺口

2026-08-16 的新 Thread 已证明点位角色链真实运行：

```text
mode: active
style_id: child / dominant_ceo
generation_status: generated
model_called: true
validation_status: accepted
layout_passed: true
style_quality_passed: true
same_fact_boundary: true
within_budget: true
```

游客正文已显示无栏目标题的连续角色化讲解，LangSmith Waterfall 也进入
`narration_commit`。阶段 3A 由用户人工验收通过。注意：验证节点中的
`active_takeover=false` 只表示该节点本身不负责发布；最终发布证据应查看
`narration_commit.active_takeover=true` 与 `fallback_used=false`，后续归档截图应优先保存提交节点。

本次成功路径同时暴露两个阶段 3 收口缺口：

1. 成功角色候选只发布了点位事实正文，旧链原有的“确认完成”“下一点位”和
   “打卡/拍照建议”没有进入最终游客回复；
2. 当前 compact 渲染主要使用开场、内容类型引入和收束。不可变事实本身在
   18 风格间保持相同是正确行为，但中段缺少足够的已审核微型承接组件，导致
   游客感知仍接近“只有首句和尾句不同”。

第一个问题不是补知识库，而是补“点位发布完整性合同”；第二个问题也不是扩写
审核事实，而是补“18 风格紧凑型表达组件库”和按事实单元分配的中段表达预算。

### 2.3 当前产品结论

| 能力 | 当前结论 | 是否可标记 verified |
|---|---|---|
| 路线生成时确认角色 | 已通过现场复测 | 可记录单项通过 |
| QA 自然分段与 Active commit | child 基础样本通过 | 不可，尚缺 18 风格和追问矩阵 |
| 18 风格点位 Active | child、dominant_ceo 真实 Active 样本通过，尚缺 18 风格矩阵 | 不可整体标记 verified |
| 工艺/对象段贯穿风格 | 候选已成功发布，但 compact 中段辨识度仍不足 | 不可 |
| 点位回复发布完整性 | 成功角色路径丢失完成确认、下一点位、打卡建议 | 不可 |
| 切换后点位 + QA 连续性 | 基础切换已有，全链验收未完成 | 不可 |

---

## 3. 统一设计原则

### 3.1 不可变事实与可变表达必须分层

任何场景的角色化输出都拆成：

```text
已审核事实单元（immutable）
+
已审核角色组件（fact-free expression）
```

事实单元必须保持：

- 原字；
- 原顺序；
- 原次数；
- 原对象和审核关联；
- 原有的未知/不确定边界。

角色组件只能承担：

- 开场；
- 引入；
- 观察视角；
- 承接和转场；
- 有上限的感受性语句；
- 收束。

角色组件不得新增年份、人物、故事、寓意、评价、排名、路线、位置、现场状态或官方背书。

### 3.2 模型只决定事实令牌，服务端决定表达

模型输出只允许：

```json
{
  "schema_version": "role_narration_candidate_v1",
  "style_id": "child",
  "public_text": "[[FACT_000]][[FACT_001]]",
  "used_fact_ids": ["..."],
  "omitted_fact_ids": [],
  "self_check": {
    "added_new_facts": false,
    "role_consistent": true,
    "within_budget": true
  }
}
```

模型不能生成连接语、标题、换行、标点、Markdown 或互动指令。服务端在令牌、事实边界和预算通过后，使用已审核配置确定性渲染。

### 3.3 场景合同必须隔离

| 场景 | 核心约束 |
|---|---|
| `stop_guidance` | space/craft/ornament 类型覆盖，成功正文使用连续导览排版 |
| `tour_qa` | 只包装已公开安全答案，不重新检索原始 chunk |
| `qa_follow_up_detail` | 继承原问题主题和事实范围，不开放新故事 |
| `navigation` | 只表达已审核路径，不新增方向与捷径 |
| `tour_closing` | 只总结真实访问和真实 Coverage |
| `replan_presentation` | 只解释已生成或已确认 Proposal，不写路线 |

### 3.4 失败时保留旧链

任一模型异常、超时、Schema 错误、事实漂移、风格不合格、预算超限、安全或互动越界都必须：

```text
validation_status = rejected
active_takeover = false
fallback_used = true
legacy_message_preserved = true
state_writes = []
```

fallback 正文不做标题移除、标点清洗或风格重写，否则将破坏兼容与安全边界。

---

## 4. 阶段 3 收口工作包

总路线仍保持“阶段 3：角色化问答 Active”。为了不遗漏点位基线验收，收口时拆成 3A～3F。

### 4.1 阶段 3A：运行配置与真实 Active 基线

目标：先证明候选链真正运行，避免把 Shadow/fallback 正文当作新实现评价。

工作：

1. Streamlit 启动进程同时开启 `role_narration,role_qa`；
2. 产品场景至少包含 `route_planning,route_opening,stop_guidance,tour_qa,qa_follow_up_detail`；
3. 全部参与测试的 style ID 进入产品 allowlist；
4. 启动时记录不含密钥的配置审计；
5. 每次改变配置后重启服务并使用新 Thread。

验收门：

```text
mode = active
generation_status = generated
model_called = true
validation_status = accepted
active_takeover = true
fallback_used = false
```

### 4.2 阶段 3B：工艺与观察对象事实单元化

目标：将旧正文中的工艺与对象内容变为可逐单元验证、可交替插入风格组件的内部结构。

内部结构：

```python
NarrationFactUnit(
    unit_id="craft:stucco",
    topic_kind="craft",
    statements=("...", "..."),
    required=True,
)

NarrationFactUnit(
    unit_id="ornament:unicorn_lion",
    topic_kind="ornament",
    statements=("...", "..."),
    required=True,
)
```

实施要求：

1. 栏目名只用于内部识别，不进入成功游客正文；
2. 工艺定义、材料制作、展现实例保持原始顺序；
3. 观察对象的造型、关联、审核故事、位置提示保持原始顺序；
4. 用户只问工艺时不强制带入无关对象；
5. 用户只问某对象时不扩展到其他未问工艺；
6. 整点讲解按审核顺序包含多个单元。

#### 3B.1 点位发布完整性与服务尾部单元

成功 `narration_commit` 不能只替换核心讲解正文而丢失旧链已经确定的服务信息。
需要把以下内容建模为独立的、确定性来源的展示单元：

```python
PointServiceUnit(
    unit_id="service:completion_prompt",
    service_kind="completion_prompt",  # completion_prompt / next_stop / photo_guidance
    public_text="已有业务节点生成并审核通过的原文",
    required=True,
    route_revision="...",
    stop_id="...",
)
```

来源和边界：

1. `completion_prompt` 只来自当前点位既有完成确认合同；
2. `next_stop` 只来自已确认路线、当前点位和现有下一站导航结果；
3. `photo_guidance` 只来自现有安全审核后的打卡/拍照计划，未触发时不得伪造；
4. 三类服务文本不得交给角色模型改写，不得被当作新的文化事实；
5. 成功路径可由 Streamlit 以独立展示块呈现，或在正文后按固定顺序呈现，但不得
   泄露内部标题和字段；
6. fallback 继续逐字保留旧链完整游客文本，不对旧链拆分或清洗；
7. 路线、点位或拍照计划 revision 变化后，旧服务单元必须失效。

推荐成功发布包：

```python
StopNarrationPresentation(
    narration_text="已验证角色化连续正文",
    completion_prompt="已有完成确认文本",
    next_stop_guidance="已有下一点位文本",
    photo_guidance="已有安全打卡建议或 None",
)
```

这属于阶段 3 的点位回复完整性修复。阶段 4 的“角色化引路 Active”是在不改变
已审核路线事实的前提下，为真正的引路表达增加角色层，两者不能混为一项。

### 4.3 阶段 3C：18 风格 × 内容类型表达库

每个风格至少配置：

```text
opening
craft_intro / craft_observation / craft_transition
ornament_intro / ornament_observation / ornament_transition
space_intro / space_observation / space_transition
qa_definition / qa_process / qa_object / qa_comparison
qa_follow_up / qa_uncertainty
appreciation
closing
prohibited_patterns
rhythm
interaction_contract
```

每个组件组至少两个已审核候选短句。同一轮按确定性索引轮换，相邻不得重复。

#### 紧凑型贯穿表达组件库

当前完整组件库虽已包含 opening、intro、observation、transition 和 closing，
但 compact 模式为了预算通常只保留 opening、每单元 intro 与 closing。要解决
“除首尾外都一样”，需为 18 风格分别补充短而可审计的微型组件：

```text
compact_opening
space_micro_observation / space_micro_transition
craft_micro_observation / craft_micro_transition
ornament_micro_observation / ornament_micro_transition
definition_bridge / process_bridge / object_bridge / story_bridge
compact_appreciation
compact_closing
```

每组至少 3 条候选，且必须满足：

- 不含任何文化事实、路线事实、位置判断或现场断言；
- 只承担观察视角、句式节奏、承接和收束；
- 同一轮确定性轮换，相邻不重复；
- 不同 style 在词汇、句长、节奏和观察方式上可区分；
- `listen_only` 与 interaction mode=`none` 不得出现问句、任务或动作要求；
- 组件加载时检查空列表、禁用表达、异常标点、内部字段和事实触发词，失败关闭。

不应为了让风格更明显而改写事实句。18 风格中间的审核事实逐字相同是安全合同；
差异应来自分布在事实句之间的已审核短连接语。

#### 18 风格工艺/对象表达目标矩阵

| style_id | 工艺背景表达方向 | 观察对象表达方向 | 关键边界 |
|---|---|---|---|
| `neutral` | 直接界定工艺与制作信息 | 按造型、细部、构件顺序观察 | 不渲染情绪 |
| `child` | 用短句说“它是怎么做出来的” | 引导找形状和细部 | 不幼稚化、不凭空比喻 |
| `family` | 适合家庭共同理解的分步承接 | 邀请大家共同留意对象细部 | 不假定家庭成员年龄 |
| `student_research` | 按材料、技法、呈现层次梳理 | 按图像、构件和审核关联观察 | 不伪造引文和研究结论 |
| `professional` | 先界定术语，再展开已审核工艺信息 | 以构件、造型、技法为观察视角 | 不添加鉴定和权威背书 |
| `listen_only` | 平稳陈述工艺信息 | 平稳陈述对象信息 | 无问号、任务、拍照或动作请求 |
| `mixed_group` | 先给共同重点，再展开工艺信息 | 用通用观察语句兼容不同游客 | 不假定团体构成 |
| `dominant_ceo` | 结论先行，提取工艺关键信息 | 聚焦对象最核心的已审核特征 | 不下命令、不进行价值排名 |
| `cute_junior` | 自然轻快地承接工艺做法 | 用短句轻松引向对象形态 | 不用波浪号、失控语气词或撒娇堆词 |
| `ancient_scholar` | 使用“且观其工”式文雅层递 | 使用“继而移目”式观照承接 | 不伪古文、不杜撰古人和典故 |
| `warm_sister` | 温和地分步展开工艺信息 | 提醒慢慢留意造型和细部 | 不过度亲密、不替游客下感受结论 |
| `bestie_chat` | 口语化地承接“先看它怎么做” | 使用轻松但克制的细节提示 | 不使用私密称呼或夸张网络语 |
| `buddy_guide` | 简洁说清工艺脉络 | 直接提示值得留意的已审核细节 | 不催促、不冒险、不强制互动 |
| `exploration_game` | 把工艺信息组织成可选“线索” | 把对象细部组织成可选观察点 | 不虚构奖励、过关结果或现场任务 |
| `photo_guide` | 先说清工艺，再承接到视觉细节 | 引导看造型、纹理和所在构件 | 只允许审核的拍照建议，安全规则优先 |
| `hostel_scholar` | 从手艺脉络平实说起 | 从图像和细节展开已审核内容 | 不杜撰文献、旅居经历或历史判断 |
| `xiguan_young_master` | 以克制、利落的岭南口吻说工艺门道 | 承接到对象造型与构件细部 | 不写未审核粤语俗语和身份故事 |
| `cantonese_storyteller` | 用“讲到这门工艺”式叙述承接 | 用“再讲眼前这一处”式转入对象 | 只能讲审核故事，不自行补全情节 |

注：表中是表达方向，不是可直接添加的新事实。正式短句必须进入严格配置并经加载校验。

### 4.4 阶段 3D：确定性交替渲染与质量门

点位成功正文结构：

```text
opening
→ craft_intro
→ 工艺事实单元 1
→ craft_observation
→ 工艺事实单元 2
→ craft_transition
→ ornament_intro
→ 对象事实单元 1
→ ornament_observation
→ 对象事实单元 2
→ appreciation
→ closing
```

compact 模式的最低风格覆盖合同不得退化为“只有开场和结尾”：

```text
opening
→ 当前类型 intro
→ 不可变事实
→ 至少一个当前类型 micro observation
→ 单元间 micro transition
→ 下一不可变事实
→ compact closing
```

最低覆盖要求：

1. 每个事实单元至少命中一个与 `topic_kind` 匹配的 intro 或 micro observation；
2. 多事实单元讲解至少有一个中段 transition；
3. 开头、中段、结尾必须来自同一 style 的已审核组件；
4. 预算按事实单元分配，而不是只设置整篇极低总预算；
5. 长事实无法在单轮容纳最低覆盖时，优先使用已存在 continuation 分轮发布；
6. 仍无法满足时回退旧链，不删除、不概括、不改写事实。

最终提交应原子组合：

```text
已验证角色化 narration_text
→ completion_prompt
→ next_stop_guidance
→ 可选 photo_guidance
```

`narration_validation` 同时验证核心正文和服务尾部的来源、顺序、freshness 与完整性；
`narration_commit` 只消费验证结果，不自行补写或重算业务内容。

质量门必须逐单元检查：

- 事实原字、顺序、次数；
- craft 单元必须命中 craft 组件；
- ornament 单元必须命中 ornament 组件；
- 开头、中段、结尾均有已审核风格组件；
- 相邻组件不重复；
- 不出现 `【……】`、Markdown、异常空行和异常标点；
- 互动次数与类型符合当前风格合同；
- 角色连接语不压过事实主体；
- 超预算时分轮或回退，不删事实。

### 4.5 阶段 3E：确认风格后的问答贯穿

当前 QA 将整个旧审核答案视为一个不可变块，因此风格往往只能出现在首尾。为了在不改写事实的前提下让风格贯穿，需升级为 QA 事实单元。

建议内部结构：

```python
QaFactUnit(
    unit_id="qa:approved_answer:000",
    answer_kind="definition",  # definition/process/object/comparison/evidence
    statements=("...",),
    required=True,
)
```

分单元规则：

1. 只按旧审核答案中已有句子或自然段分割；
2. 不改句子内容，不改顺序，不重复；
3. 原空白只作排版元数据，不作为新事实；
4. 定义问题使用 `qa_definition`；
5. 制作方法使用 `qa_process`；
6. 对象/纹样使用 `qa_object`；
7. 比较问题使用 `qa_comparison`；
8. 证据不足使用 `qa_uncertainty`；
9. “再详细一点”使用 `qa_follow_up`，但不扩大原 QAContext 范围。

渲染结构：

```text
style opening
→ question-kind direct answer
→ immutable QA fact unit 1
→ style-specific QA transition
→ immutable QA fact unit 2
→ bounded follow-up/closing
```

问答专属验证：

- 旧审核答案的事实文字全部保留；
- 只检查角色新增连接语的标题、Markdown、换行和标点；
- 旧答案已有自然分段允许保留；
- 新增连接语不得出现新事实触发词；
- `listen_only` 无问号、任务和追问邀请；
- QA 层始终 `state_writes=[]`。

### 4.6 阶段 3F：风格切换与旧候选失效

#### 切换语义

支持：

- 游览前：“使用古风书生”；
- 游览中：“切换成儿童友好”；
- 问答后：“接下来用专业风格”；
- 复合指令：“切换成古风书生，继续讲灰塑”。

独立切换只修改角色偏好，不修改：

- 路线；
- TourState；
- 当前点位；
- 进度；
- Coverage；
- 已确认 Proposal。

#### 版本与 freshness

为角色状态增加单调递增的 `role_revision`。所有候选必须保存：

```text
style_id
style_schema_version
role_revision
route_revision
stop_id / qa_context_id / proposal_id
```

切换成功后必须使旧内容失效：

- `pending_role_narration_commit`；
- `role_narration_candidate`；
- `qa_role_narration_candidate`；
- `pending_narration_continuation`；
- 旧引路/结束语/重规划表达候选；
- 阶段 5 中尚未播放的 TTS 队列。

复合指令执行顺序：

```text
确定性解析风格
→ 写入新 role_revision
→ 使旧候选失效
→ 在新快照下生成后续讲解/QA
→ 验证
→ 单一 commit
```

含糊、未知或同时命中多个风格时，进入澄清，不改角色、路线或进度。

---

## 5. 阶段 3 测试与 LangSmith 验收

### 5.1 自动化矩阵

#### 点位成功矩阵

```text
18 风格 × craft × 1
18 风格 × ornament × 1
18 风格 × space × 1
= 54 条基础成功样本
```

每条必须断言：

```text
validation_status = accepted
active_takeover = true
fallback_used = false
state_writes = []
layout_passed = true
style_quality_passed = true
same_fact_boundary = true
```

同时断言：

- 不含 `【工艺背景】`、`【观察对象】`、`【下一步】`；
- 工艺与对象使用不同类型组件；
- 事实逐字、顺序、次数不变；
- 开头、中段、结尾均有当前风格；
- 相邻角色组件不重复。

#### 点位发布完整性矩阵

对 18 风格的整点讲解至少验证：

- 完成确认始终可见且与当前点位一致；
- 有下一站时下一点位信息可见，无下一站时不伪造；
- 打卡建议触发时可见，未触发时不出现；
- 角色正文切换为 Active 后三类服务内容不丢失、不重复；
- 服务单元不得被角色模型改写；
- 路线 revision、stop_id 或拍照计划过期时拒绝旧候选并走旧链；
- 最终 `state_writes=[]`，角色表达层不改变路线或进度。

#### 紧凑型风格覆盖矩阵

- 18 风格 × craft/ornament/space 均命中对应 micro 组件；
- 单元数量为 1、2、3 和长讲解时均有开头、中段、结尾覆盖；
- 不同风格在相同事实下至少命中不同的已审核组件组；
- compact 与 full 的事实原字、顺序、次数完全一致；
- 预算不足时 continuation 或 fallback，不得静默退化为首尾风格；
- 相邻组件重复、类型错配、异常标点或组件库缺失均拒绝。

#### QA 矩阵

- 18 风格各 1 条定义问题；
- child、professional、ancient_scholar、listen_only 各覆盖定义、制作、对象、追问；
- 至少 1 条证据不足问题；
- 至少 1 条包含自然分段的旧审核答案；
- 每条保留 QAContext、原事实范围和 `state_writes=[]`。

#### 切换矩阵

- 18 种风格别名均可确定性映射；
- 游览前切换；
- 游览中切换；
- QA 后切换；
- 切换 + 继续讲解的复合指令；
- 切换后旧候选、continuation 和未播放表达不得发布；
- 切换不改变路线、当前点和进度；
- 含糊切换失败关闭。

#### 故障矩阵

以下任一情况必须回退：

- rollout off / Shadow；
- 模型超时；
- 非法 JSON/Schema；
- 事实令牌缺失、重复或乱序；
- 新增年份、人物、故事、寓意或位置；
- 类型组件错配；
- 首句有风格但中段/结尾缺失；
- 异常标点、标题、Markdown 或内部字段；
- 超预算；
- `listen_only` 或 `interaction mode=none` 中出现互动请求；
- 角色或路线 revision 过期。

### 5.2 LangSmith 人工验收证据

每个人工样本保存：

1. Thread ID 与 Trace URL；
2. 游客输入；
3. 游客正文开头、中段、结尾截图；
4. `narration_content_plan`/`qa_content_plan` 中的单元和类型；
5. generation 的 style、status、model_called 和 reason；
6. validation 的 fact/layout/style/budget/safety 字段；
7. commit/fallback 的 takeover、decision、legacy 与 state writes；
8. 如有切换，保存切换前后 style ID 与 role revision。

不允许只保存游客正文截图，因为 fallback 也可能显示完整可读文本。

### 5.3 阶段 3 完成定义

全部满足后才能标记 verified：

- 54 条点位自动化矩阵通过；
- 18 风格 QA 基础矩阵通过；
- 重点风格的多轮 QA 通过；
- 切换与 freshness 矩阵通过；
- 全部 fault fallback 通过；
- 完整回归通过；
- LangSmith 真实 Active 证据齐全；
- 无 API Key、原始 chunk、内部路径或节点字段泄漏。

---

## 6. 阶段 4：角色化引路、结束语与重规划说明 Active

阶段 4 只能在阶段 3 verified 后进入。

### 6.1 角色化引路 Active

输入必须是已确定的 `NavigationPresentationPlan`，至少包含：

```text
from_stop_id
to_stop_id
approved_path
approved_direction_phrases
walking_seconds
safety_disclaimer
route_revision
```

角色层只能调整称呼、节奏和承接，不得：

- 新增左转、右转、直行距离；
- 推荐捷径；
- 引导进入非开放区域；
- 把未审核的现场通行状态当成事实。

位置、路线或 route revision 改变后，旧引路候选失效。

### 6.2 角色化结束语 Active

输入必须是 `ClosingPresentationPlan`，事实来源仅限：

- 实际 TourState；
- 实际已发布 Coverage；
- 实际获得称号；
- 已审核服务信息。

结束语不得：

- 总结未参观点位；
- 总结未向游客讲过的工艺或对象；
- 把跳过点当成完成点；
- 在 `listen_only` 中主动提问。

### 6.3 角色化重规划说明 Active

输入必须是 `ReplanPresentationPlan`，并绑定：

```text
proposal_id
proposal_status
route_revision_before
route_revision_after
changed_stops
unchanged_constraints
freshness_token
```

关键边界：

- 角色只能表达已确定的路线或 Proposal；
- 未确认 Proposal 不得应用；
- 拒绝或取消后保留原路线；
- 路线变化后旧候选必须失效；
- 角色表达节点不得直接写 TourState 或路线。

### 6.4 阶段 4 验收矩阵

- 18 风格 × 引路至少 1 条；
- 18 风格 × 结束语至少 1 条；
- 18 风格 × 重规划说明至少 1 条；
- 正常导航、未知位置、走错、跳过、结束、重规划提议、确认、拒绝、过期 Proposal；
- 任一方向、路线、Coverage 或 Proposal 漂移都回退；
- fallback 不丢失当前角色偏好。

阶段 4 完成后，以下场景形成完整受控角色链：

```text
路线规划
→ 路线开场
→ 引路
→ 点位讲解
→ QA/追问
→ 重规划说明
→ 结束语
```

---

## 7. 阶段 5 以后的长期产品路线

### 7.1 阶段 5：全流程角色连续性与语音导游

目标：将已验证正文扩展为可播放、可暂停、可插话和可恢复的语音旅程。

核心工作：

1. 统一风格选择、继承、切换和冲突澄清；
2. fallback 不清除角色，新 Thread 不继承旧 Thread 角色；
3. TTS 只朗读已验证并已 commit 的游客正文；
4. 支持播放、暂停、继续、语速、快进和锁屏播放；
5. 游客插话时暂停音频，QA 结束后按有效 continuation 恢复；
6. 离开点位、路线或角色变化时停止旧音频；
7. ASR 转写仍进入语义仲裁，不能直接触发状态写入；
8. 用正文哈希保证文本和音频一致。

### 7.2 阶段 6：二维码/NFC 定位与可视化地图

- 二维码深链提交到达候选；
- NFC 作为可选的低操作成本定位；
- 可选 BLE 只提供位置候选；
- SVG/GeoJSON 场馆地图与 NetworkX 审核路径一致；
- 位置置信度不足时由游客确认；
- 任何感知结果都不直接改 TourState。

### 7.3 阶段 7：AI 识物镜与审核对象绑定

- 识别结果只是对象候选；
- 必须映射到已审核对象注册表；
- 低置信度、多对象冲突或未注册对象需要澄清；
- 视觉模型不直接生成文化事实；
- 最终讲解仍走审核事实和角色验证链。

### 7.4 阶段 8：数字游览护照、摄影导演、亲子研学

- 数字护照只绑定真实 TourState 和 Coverage；
- 摄影导演只使用已审核站位和安全约束；
- 亲子研学支持多人但不混合未成年人隐私；
- 任务、称号和奖励必须由真实行为触发；
- 游客可选择关闭收集、摄影或研学任务。

### 7.5 阶段 9：场馆 CMS 与审核后台

- 内容草稿、复核、发布、下架和回滚；
- 事实单元、对象、路线、安全和风格组件版本化；
- 审批记录、差异比较和发布审计；
- 回滚后旧候选和缓存失效；
- 运营人员不能越权修改不属于自己的场馆。

### 7.6 阶段 10：多场馆、多租户

- 将当前陈家祠单场馆数据抽象为 tenant/venue/content release；
- 租户数据、向量库、Trace、密钥和计费隔离；
- 以第二场馆验证快速接入能力；
- 不允许跨场馆检索、路线或对象泄漏。

### 7.7 阶段 11：商业化、渠道与计费

- 场馆授权、个人增值和渠道套餐；
- 模型、TTS、存储和检索成本归集；
- 订单、退款、发票和对账；
- 隐私合规的转化和留存分析；
- 通过真实试点验证付费与续费。

### 7.8 阶段 12：无障碍、多语言、隐私安全

- WCAG 与键盘/读屏器可用性；
- 轮椅、听障、视障和安静游览旅程；
- 中英粤及术语表、事实对齐和语音一致；
- 数据最小化、保留期、导出、删除和同意；
- 密钥、租户、工具权限、输入注入和内部字段泄漏防护。

### 7.9 阶段 13：生产部署与规模验证

- CI/CD、分环境配置、数据迁移和回滚；
- 日志、Trace、指标、告警和故障演练；
- 模型超时、检索故障、TTS 故障和地图故障降级；
- 压测、峰值并发、单游客成本和容量计划；
- 真实场馆灰度、用户反馈和可量化续费信号。

---

## 8. 建议修改文件边界

阶段 3 预计只修改与以下职责直接相关的文件：

```text
agent_graph.py
narration_content_plan.py
narration_rendering.py
narration_style_policy.py
narration_validation.py
qa_role_shadow.py
role_mode_shadow.py
role_narration_generation.py
data/chen_clan_academy/narration_styles/point_narration_components_v1.yaml
相关 test_*.py
相关 LangSmith dataset/runner
```

不应修改：

- TourState Schema；
- 审核知识事实；
- 审核路线；
- RAG 原始数据；
- 旧链 fallback 正文；
- DOCX、PDF、视频或 vendor 输出。

---

## 9. 任务更新格式

队友每完成一个工作包，在本节追加一条记录，不得用“基本完成”替代证据。

```text
日期：
工作包：3A / 3B / 3C / 3D / 3E / 3F / 4.x / 5+
状态：planned / implemented / shadow / active / verified / blocked
修改文件：
测试命令：
测试结果：
LangSmith Thread/Trace：
游客可见结果：
fallback 证据：
未完成项：
下一执行人：
```

### 当前任务记录

```text
日期：2026-08-16
工作包：阶段 3A 运行配置与真实 Active 基线
状态：verified（用户已完成 LangSmith 新 Thread 与 Streamlit 人工验收）
修改文件：demo/streamlit_app.py、demo/README_DEPLOY.md、README.md、narration_budget.py、role_narration_generation.py、test_demo_public_adapter.py、test_streamlit_rollout_startup.py、test_narration_budget.py
实现内容：同时读取 role_narration + role_qa 产品配置；PowerShell 显式 rollout 优先于旧 Streamlit Secrets；18 风格入口；不含密钥的启动审计；不完整配置失败关闭；预算预检与最终确定性骨架使用同一组件选择和 transition 计数规则；compact 决策会真正传入生成器；同类型多事实单元选中相同 intro 时轮换到下一条审核组件，不再删除该单元的风格覆盖
定向测试：71/71 OK
完整回归：1231/1231 OK
LangSmith 证据：点位 child 新 Thread 已证明 mode=active、generation_status=generated、model_called=true、validation_status=accepted、layout/style/fact/budget 全部通过；Waterfall 进入 narration_commit，游客看到连续角色化正文；dominant_ceo 也已生成 Active 候选
预算修复验证：child 12 条事实 / 3 个单元会选择 compact，预检与渲染连接语秒数一致，两个 ornament 单元均有不同 intro，完整 validation=accepted；核心定向 64/64 OK；角色化相关 229/229 OK；py_compile 与 git diff --check 通过
当前验收发现：成功角色路径丢失完成确认、下一点位与打卡建议；compact 中段风格组件不足，除首尾外辨识度偏低
下一步：先完成 3B.1 点位发布完整性，再补 3C 紧凑型组件库和 3D 最低覆盖/预算/continuation 合同，然后执行 18 风格矩阵
```

```text
日期：2026-08-16
工作包：阶段 3B.1 点位发布完整性与服务尾部单元
状态：verified（代码、自动回归、Streamlit 游客正文与 LangSmith Active 提交证据均已验收通过）
修改文件：narration_service_tail.py、narration_rendering.py、agent_graph.py、role_narration_langsmith_runner.py、test_narration_service_tail.py、test_role_narration_graph.py、test_role_narration_style_matrix.py、test_narration_continuation_commit.py、test_role_narration_langsmith_runner.py
实现内容：将 completion_prompt、next_stop、可选 photo_guidance 建模为确定性 PointServiceUnit；成功角色正文与已验证服务尾部合成为单一 validated_public_message；提交节点只发布该验证结果，不再追加或重算服务文本；路线状态与拍照计划指纹变化会使旧尾部失效；标题、Markdown、异常标点、内部字段或安全边界失败时继续完整回退旧链正文
续讲合同：分段讲解的中间段不发布服务尾部，只在最终段发布，避免重复“完成本点/下一点”
定向测试：56/56 OK
完整回归：1239/1239 OK（LANGSMITH_TRACING=false、HF_HUB_OFFLINE=1）
LangSmith Thread/Trace：2026-08-16 Streamlit 新 Thread（thread_id 前缀 streamlit-demo-4ef96e7f-7c27-4321-ba4，Turn 3）已确认 stop_guidance → narration_content_plan → role_narration_generation → narration_validation → narration_commit；commit_decision=role_candidate_published、commit_validation_status=accepted、validation_status=accepted、active_takeover=true、legacy_message_preserved=false
服务尾部证据：service_tail_passed=true、service_tail_reason_codes=[]、service_unit_kinds=[completion_prompt,next_stop,photo_guidance]、state_writes=[]；public_message_safe=true、same_fact_boundary=true、role_consistent=true、style_quality_passed=true、within_budget=true
游客可见结果：成功 narration_commit 连续显示角色化正文、完成确认、下一点“月台”导航和已触发的安全拍照建议；没有显示【下一步】/【打卡姿势建议】标题，摄影安全限制完整保留
fallback 证据：服务尾部缺失、过期、顺序错误、公开文本越界或整体验证失败均进入 deterministic_narration_fallback，legacy_message_preserved=true，state_writes=[]
验收边界：真实 Streamlit/LangSmith 已覆盖正常点位、拍照触发与成功 Active commit；分段续讲只在最终段发布尾部、故障时完整回退旧链由自动测试覆盖，本轮未额外执行人工故障注入
未完成项：3B.1 无阻断项；正文中段角色辨识度与 18 风格组件扩充转入阶段 3C，最低覆盖、预算和 continuation 联合合同转入阶段 3D
下一执行人：继续实施 3C 紧凑型贯穿表达组件库，再进入 3D 最低中段覆盖与预算合同
```

```text
日期：2026-08-16
工作包：阶段 3C 紧凑型贯穿表达组件库（三角色试点）
状态：implemented（定向测试与兼容性回归通过，等待游客可见文本验收）
修改文件：point_narration_components_v1.yaml、narration_style_policy.py、role_narration_generation.py、narration_budget.py、narration_validation.py、test_compact_role_components.py
实现内容：为 child、ancient_scholar、dominant_ceo 增加完整 compact 组件组，每组至少 3 个审核候选；compact 渲染改为使用专用开场/收束，在每个事实单元末尾插入同类型 micro observation，并在单元切换处插入 micro transition；预算预检与校验使用相同的确定性选择、位置和轮换规则；未配置新组件的其余 15 风格保持旧 compact 合同
安全边界：组件加载拒绝部分配置、空候选、内部引用、年份断言、标题、Markdown、换行和异常标点；模型仍只输出事实令牌，所有新增表达由服务端确定性渲染
静态检查：git diff --check 通过，仅保留既有 CRLF 提示
定向测试：44/44 OK（test_compact_role_components、test_narration_budget、test_role_narration_generation，由操作者执行）
兼容性回归：31/31 OK（test_role_narration_style_matrix、test_role_narration_continuity、test_narration_continuation_commit，由操作者执行）
下一步：人工比较三角色 compact 多单元正文，再决定扩展全部 18 风格或先调整组件文案
```

```text
日期：2026-08-16
工作包：阶段 3C 自然话语试点（事实锚点 + 受限连接语）
状态：implemented（合同测试通过，等待 Graph 兼容性回归和 LangSmith 人工验收）
修改文件：role_discourse.py、role_narration_generation.py、narration_validation.py、agent_graph.py、test_role_discourse.py
实现内容：新增 RoleDiscoursePlan，将事实间关系标注为 same_unit_continuation、same_topic_new_unit 或 topic_transition；模型只生成 opening、逐槽 bridge 和 closing，服务端按原字、原序、原次数插入审核事实；三角色 compact 由 PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED 显式开关控制，默认关闭；自然候选失败或模型异常时丢弃模型文本并使用确定性 compact 组件 fallback
安全校验：严格 JSON Schema、bridge ID 和顺序、连接语预算、事实复述、事实触发词、内部字段、危险表达、布局、禁用表达、互动边界、自检和角色最低标记；最终正文继续经过原有事实边界、公共消息、预算和服务尾部验证
去重记忆：成功 Active commit 后只保存最多 12 条纯表达片段，不保存事实、游客问题、路线或资料；模型提示会收到 recent_expressions_to_avoid，原样复用会失败关闭
定向测试：9/9 OK（test_role_discourse，由操作者执行）
兼容性回归：104/104 OK；另行复测角色连续性 9/9 OK（接口兼容修复后，由操作者执行）
运行配置：PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED 已接入 Streamlit 环境/Secrets 与无密钥启动审计；默认关闭，仅人工试点时开启
下一步：验证 Streamlit 启动配置，再开启试点开关执行真实模型和 LangSmith 人工验收
```

```text
日期：2026-08-17
工作包：child 点位讲解 Active 收尾与现状同步
状态：active（stop_guidance 已有真实发布证据；儿童全链路尚未完成）
修改文件：narration_rendering.py、role_discourse.py、role_narration_generation.py、data/chen_clan_academy/narration_styles/point_narration_components_v1.yaml、相关定向测试
已解决：此前 child 候选因 repeated_role_expression 被 narration_validation 拒绝并回退旧链；当前新的 LangSmith Thread 已记录 validation_status=accepted，narration_commit.commit_decision=role_candidate_published，narration_commit.active_takeover=true，fallback_used=false。儿童与古风书生现共用“事实呈现 → ContentPlan → generation → validation → commit/fallback”主链；儿童只作为受控摘要呈现策略，且与所有风格一样保留 source_statements 审计边界，不另建发布链。
已验证：role_narration_generation 的 model_called=true；事实边界与公共消息安全通过；首次到站 proactive_photo_triggered=false，未自动拼接拍照卡；visitor_localization 的 api_called=false 属于 source_already_target（原文已是简体中文），不是角色模型未调用。
当前本机配置：PRODUCT_ROLE_ACTIVE_STYLES=child，PRODUCT_ROLE_ACTIVE_SCENES=stop_guidance，CJC_READ_ONLY_ROLLOUT_CAPABILITIES=role_narration。因此本轮证据只覆盖 child 的点位讲解，不覆盖 route_planning、route_opening、tour_qa 或 qa_follow_up_detail。
未完成项：1) 在最新去重与儿童事实组织改动后重新运行角色相关 unittest；2) 复测 full、compact、split/continuation 的多事实单元，确认不再出现 repeated_role_expression；3) 在新 Thread 中启用并验收 child 的 route_planning、route_opening、tour_qa、qa_follow_up_detail；4) 对模型异常/校验失败执行一次儿童 fallback 人工证据；5) 决定并文档化儿童“受控摘要/比喻”与本计划第 3.1 节“事实原字”合同的兼容规则；6) child 完成前，不把 18 风格整体或阶段 3 标记为 verified。
整体进度：3A 与 3B.1 保持既有 verified 记录；3C 仍为三角色试点加本次 child 修复，尚未扩展为 18 风格验收；3D（最低中段覆盖、预算与 continuation 联合合同）、3E（QA 事实单元贯穿）、3F（role_revision 与旧候选失效）未完成；阶段 4 的 navigation、tour_closing、replan_presentation 仍保持 Shadow/计划状态。
下一步：先完成 child 剩余五项并以 ancient_scholar 主线做回归；随后按 3C→3D→3E→3F 的顺序扩展，不直接开放 18 风格全场景 Active。
```

```text
日期：2026-08-17
工作包：18 风格 stop_guidance 快速 Active 试运行
状态：active（已扩展本地白名单；待自动矩阵与游客正文快速审阅）
配置：PRODUCT_ROLE_ACTIVE_STYLES 已改为全部 18 个审核 style_id；PRODUCT_ROLE_ACTIVE_SCENES 仍严格限定为 stop_guidance，PRODUCT_ROLE_VALIDATION_LEVEL=strict、100% 灰度、kill switch=false 保持不变。
边界：不使用“默认通过”。每种风格仍必须经过相同事实、布局、风格、安全、预算与服务尾部校验；失败自动显示旧链 fallback。人工验收只审阅最终游客正文，不要求逐条展开 LangSmith 节点。
待执行：在可用项目 .venv 中运行 test_role_narration_style_matrix.py 与当前角色定向回归；重启 LangGraph 后，以每种风格各一条到站输入快速审阅游客可见正文；发现不自然、重复、后台术语或回退时记录该 style_id，再做定向修复。
不包含：route_planning、route_opening、tour_qa、qa_follow_up_detail、navigation、tour_closing、replan_presentation 的 18 风格 Active 扩张。
```

```text
日期：2026-08-17
工作包：18 风格全场景 Active 探索性扩张
状态：active（本地人工测试开关；不等同于阶段 3/4 verified）
配置变更：CJC_READ_ONLY_ROLLOUT_CAPABILITIES=role_narration,role_qa；PRODUCT_ROLE_ACTIVE_SCENES=route_planning,route_opening,stop_guidance,tour_qa,qa_follow_up_detail,navigation,tour_closing,replan_presentation；全部 18 个 style_id 继续保留在产品白名单。
安全边界：严格 validation、事实边界、预算、服务尾部、freshness、状态零写入与 legacy fallback 保持启用；未通过的单一场景必须回退旧链，不得因测试配置默认发布。
验收方式：重启服务并使用新 Thread；按完整游客流程观察最终正文，先不要求逐节点人工审计。若某场景风格缺失、出现后台术语、路线/状态错误或明显回退，记录“style_id + 场景 + 最终正文”后定向修复；正式 verified 状态仍须补自动回归和必要的 Active 证据。
```

---

## 10. 推荐执行顺序

1. 阶段 3A 已验收通过，保留提交节点与游客正文证据；
2. 阶段 3B.1 已通过自动回归和 Streamlit/LangSmith 人工发布完整性验收，保持 verified；
3. 补充 3C 紧凑型贯穿表达组件库，先审核 child/ancient_scholar/dominant_ceo，再扩展全部 18 风格；
4. 实施 3D 按事实单元预算、最低中段覆盖、continuation 与服务尾部联合验证；
5. 实施 3E，使 QA 由“整块首尾风格”升级为“事实单元间风格”；
6. 实施 3F，为所有候选补齐 role revision 和失效规则；
7. 运行定向测试、54 条矩阵、发布完整性矩阵、compact 覆盖矩阵、fault 矩阵和完整回归；
8. 完成 LangSmith 18 风格真实人工验收并更新状态矩阵；
9. 阶段 3 verified 后开始阶段 4；
10. 阶段 4 verified 后开始阶段 5 语音和完整角色连续性。

## 11. 完成与回滚原则

- 未完成 LangSmith Active 证据前，不得把阶段 3 标记 verified；
- 阶段 3 未 verified 前，不将阶段 4 候选改为 Active；
- 任一新 Active 能力必须有 kill switch 和旧链 fallback；
- 回滚时优先关闭对应 capability/scene，不删除旧链；
- 不提交 API Key、临时截图、本地视频、DOCX/PDF 或 vendor 目录；
- 文档和状态更新不得超前于真实代码和验收结果。
