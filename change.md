# CURRENT ROLE SHADOW STATUS (2026-08-09)

```text
role_schema: fixed
role_shadow: implemented_and_automated_verified
presentation_content_plan: implemented
presentation_content_plan_shadow: automated_verified
route_opening_shadow: implemented_and_automated_verified
route_opening_shadow_manual: passed_by_operator
role_active: disabled
active_takeover: disabled
automated_validation: partial_due_to_preexisting_failures
role_shadow_targeted_tests: 22/22 passed
presentation_content_plan_targeted_tests: 9/9 passed
route_opening_integration_tests: 19/19 passed
full_regression: 1047/1052
p0_matrix: 10/10 passed
```

The current implementation adds a deterministic, read-only role-mode shadow
selector for `ancient_scholar`, `child`, and `listen_only`. Explicit requests
and already-validated profile signals create an audit record; conflicts and
unknown roles fail closed. The selected role only changes the non-authoritative
Shadow content plan used by role narration generation. The legacy visitor
message, TourState, VisitorProfile, route, proposal, StopProgram, Coverage,
RAG evidence, and tools remain outside this phase.

The five known baseline failures remain a separate preexisting issue list and
must not be changed in this phase:

```text
test_same_thread_retains_profile_but_new_thread_isolated
test_english_minute_route_input_starts_same_thirty_minute_route
test_title_basis_combines_heard_topics_questions_and_explicit_profile
test_two_hour_woodcarving_deep_request_uses_route_planner
test_two_hour_woodcarving_request_replans_from_active_tour
```

The unified `presentation_content_plan` is now a strict Shadow audit object
for `route_planning`, `route_opening`, `stop_guidance`, `navigation`, and
`tour_closing`. It records content sections, role strategy, evidence and
safety requirements, and a scene-specific budget. It does not replace the
legacy visitor message or write operational state. Missing evidence, invalid
enums, unknown fields, internal fields, and invalid budgets fail closed to
`legacy_chain`.

# 陈家祠导游 Agent：语义路由与全流程角色化讲解改造方案

## 0. 文档目的

本方案用于指导当前项目从“确定性 Workflow + 局部角色讲解 Shadow”升级为：

~~~text
自然语言理解
→ 受控意图裁决
→ 确定性路线与状态执行
→ 统一角色化表达
→ 事实、路线、安全、预算验证
→ Active 接管或确定性回退
~~~

最终目标不是让 LLM 自由控制导游流程，而是让同一个角色贯穿：

~~~text
路线规划说明
→ 路线开场白
→ 点位讲解
→ 点位之间的引路说明
→ 游客追问
→ 游览结束总结、称号和祝福
~~~

核心原则：

~~~text
Agent 决定怎么理解、怎么组织和怎么表达
Workflow 决定能不能执行、写入什么状态
Validator 决定最终输出是否安全
~~~

## 1. 当前真实状态与未完成问题

### 1.1 已经具备的能力

- LangGraph StateGraph 管理 Thread、TourState 和游客画像；
- semantic_normalization、semantic_intent_envelope 和 intent_arbitration 已接入；
- 路线规划、到达、完成、跳过、重规划和问答由确定性节点控制；
- route_planner.py 和 guide_program_planner.py 已能生成审核路线与点位内容计划；
- style_roles_v2.yaml 已提供角色库；
- StyleBrief 已能向角色模型提供最小审核角色卡；
- narration_content_plan、role_narration_generation、narration_validation 已接入点位讲解链路；
- Shadow、Active、fallback 和 Coverage 提交边界已经具备；
- styles_v1.yaml 仍可作为确定性安全回退。

### 1.2 当前已发现的问题

1. 既有实现已加入 JSON object、独立 token 预算和一次受控修复，但现场仍出现 invalid_candidate_schema；因此本阶段还要冻结模型线与 Graph 内部 envelope 的双层 Schema，并完成真实回归验证。
2. 当前角色链路主要覆盖 stop_guidance，不能覆盖路线规划、路线开场和引路正文。
3. direct_route_node 仍直接拼接路线规划正文。
4. tour_opening_node 仍直接输出确定性开场正文。
5. next_stop_navigation 和重规划提示尚未统一经过角色表达和路线事实校验。
6. 角色风格可能只出现在点位讲解中，无法保证同一 Thread 全流程角色一致。
7. 低置信度表达、路线边界和游客端内部字段仍需继续进行 LangSmith 验收。

### 1.3 当前阶段结论

当前不能宣称“全流程角色化已经完成”。准确状态是：

~~~text
语义候选与裁决：已实现，继续验收
角色库 V2：已实现
点位角色 Shadow：已实现；候选 Schema 修复已补强，等待自动化环境恢复和 LangSmith 复测
路线规划角色化：未完成
路线开场角色化：未完成
引路输出角色化：未完成
全流程角色一致性：未完成
~~~

## 2. 权限和事实边界

### 2.1 Agent 可以做什么

- 理解自然语言并提出受控意图候选；
- 识别语言、时长、兴趣、风格和讲解模式；
- 在审核事实范围内重组内容顺序；
- 根据角色改变称呼、句式、节奏、修辞和互动方式；
- 根据已生成的审核路线表达路线概览和引路说明；
- 对低置信度、冲突和混合请求提出澄清。

### 2.2 Agent 不可以做什么

- 直接修改正式路线、TourState、VisitorProfile 或 Coverage；
- 自行生成新的点位、方向、距离、步行时间或空间关系；
- 添加未经审核的年代、人物、故事、寓意、排名或绝对评价；
- 读取并展示 source ID、文件路径、URL、RAG chunk、工具名或内部节点名；
- 以角色口吻强迫游客触摸、拍摄、移动或完成任务；
- 因风格表达而改变安全规定、路线边界或用户选择。

## 3. 目标总体架构

~~~text
用户输入
  ↓
pre_semantic_arbitration
  ↓
semantic_normalization
  ↓
intent_arbitration
  ↓
Workflow 确定性节点
  ├─ profile / route / tour_event / replan / QA
  └─ 生成 canonical facts
          ↓
  presentation_content_plan
          ↓
  role_narration_generation
          ↓
  narration_validation
      ├─ accepted → presentation_commit
      └─ rejected → deterministic_fallback
          ↓
  visitor_localization
          ↓
  游客正文
~~~

角色化表达必须覆盖五种 presentation_type：

~~~text
route_plan
tour_opening
stop_guidance
navigation
tour_closing
~~~

点位讲解继续使用现有内容计划；路线规划、开场、引路和结束语使用同一个角色生成/验证框架，但使用不同的类型化事实计划。

## 4. 第一阶段：修复并冻结语义契约

### 4.1 目标

让自然语言只产生业务意图候选，不直接产生 Graph 节点命令。

### 4.2 统一数据结构

~~~python
class IntentCandidate(TypedDict):
    intent: str
    confidence: float
    target: str | None
    arguments: dict[str, object]
    evidence_span: str
    requires_confirmation: bool
    side_effect_level: Literal["read_only", "state_change"]


class SemanticIntentEnvelope(TypedDict):
    schema_version: str
    candidates: list[IntentCandidate]
    ambiguity_reason: str | None
    raw_text_preserved: bool
    model_called: bool
~~~

### 4.3 裁决规则

- 普通只读意图最低置信度为 0.80；
- 状态修改意图最低置信度为 0.90，且参数必须完整；
- 到达、完成、跳过、结束和重规划必须通过确定性状态校验；
- 多个互相冲突的状态意图必须进入 clarification；
- 低置信度表达不能进入 llm_think/RAG 执行状态操作；
- 最多保留三个候选，但每轮最多执行一个正式状态动作；
- 候选只能表达业务意图，不能返回 Graph 节点名作为执行指令。

### 4.4 验收

至少覆盖：

- “这里已经看完了吗？”不能完成点位；
- “这个地方好像差不多了吧？”必须澄清；
- “完成本点，但也跳过本点”必须澄清；
- “我只有30分钟，想少走路”进入画像和路线流程；
- “把附近奶茶店加入馆内路线”必须说明边界，不得修改路线。

### 4.5 当前 Schema 修复边界

本阶段只处理角色候选的序列化、解码和校验边界，不扩展角色能力范围：

- 模型线只接受 `role_narration_candidate_v1` 的六个字段；缺字段、多余字段、错误类型、未知角色和未知版本均失败关闭；
- Graph 内部保存的候选 envelope 使用独立的严格字段集合，不能因为内部反序列化而重新接受未知字段；
- LangChain 返回文本内容块时只拼接明确的 text block，不能将 Python list 表示直接当作 JSON；非文本内容继续失败关闭；
- 候选仍只能重组审核事实和改变表达策略，不能生成节点、路线、来源、状态补丁、画像字段或最终游客答案；
- 修复失败仍保留 `invalid_candidate_schema` / `invalid_candidate_fields` 等拒绝分支，Shadow 继续不接管旧正文；
- 任何 `TourState`、`VisitorProfile`、路线、Proposal、StopProgram 和 Coverage 写入均不属于本阶段。

## 5. 第二阶段：角色库和角色一致性

### 5.1 角色卡要求

每个角色必须包含：

~~~yaml
style_id: ancient_scholar
persona:
  identity: "角色身份"
  relationship_to_visitor: "与游客的关系"
  emotional_tone: ["从容", "雅致"]
  speaking_perspective: "第一人称同行讲解"
  identity_boundaries: []
generation_policy:
  opening_strategy: "开场方式"
  fact_order: ["路线目的", "空间位置", "审核事实", "观察提示"]
  interaction_frequency: "low"
  rhetorical_devices: ["适量比喻", "对照", "节奏变化"]
  avoid: ["虚构典故", "绝对评价", "强迫互动"]
  closing_strategy: "收束方式"
few_shot_examples: []
~~~

### 5.2 角色表达原则

角色感通过称呼、句子长度、叙事视角、事实组织顺序、情绪节奏以及开场、转场和收束方式产生。

角色不得通过编造历史或绝对评价产生吸引力。

### 5.3 首批 Active 角色

先只启用经过充分测试的：

~~~text
neutral
child
professional
ancient_scholar
dominant_ceo
~~~

其他角色保持 Shadow 或 neutral fallback，不能因为角色库存在就自动 Active。

## 6. 第三阶段：统一角色表达计划

### 6.1 通用计划结构

建议新增或扩展 presentation_content_plan.py：

~~~python
class PresentationContentPlan(TypedDict):
    schema_version: str
    presentation_type: Literal[
        "route_plan", "tour_opening", "stop_guidance",
        "navigation", "tour_closing"
    ]
    style_id: str
    language: str
    budget_seconds: int
    facts: list[dict[str, Any]]
    must_include: list[str]
    already_covered: list[str]
    must_not_claim: list[str]
    interaction_allowed: bool
    canonical_constraints: dict[str, Any]
~~~

### 6.2 路线规划计划

事实由 RoutePlan 产生，至少包含：

- 路线名称；
- 可用时间；
- 点位顺序；
- 预计讲解时间；
- 预计步行时间；
- 少走路约束；
- 时间估算和现场变化提示。

角色只能改变路线说明方式，不得改变 stop_ids、路径、时间或约束。

### 6.3 路线开场计划

由 tour_opening_program 产生事实，角色化表达：

- 欢迎语；
- 本次路线概览；
- 路线时长；
- 第一站提示；
- 选择权和跳过规则。

tour_opening_program 继续由 Workflow 写入，角色节点不得修改它。

### 6.4 点位讲解计划

继续使用现有 narration_content_plan，必须包含：

- 审核事实 ID；
- 审核事实原文；
- 当前点位；
- 已讲 Coverage；
- 内容预算；
- 是否允许互动；
- 禁止新增的事实类型。

### 6.5 引路计划

由审核路线和空间图生成：

~~~json
{
  "presentation_type": "navigation",
  "from_stop_id": "front_courtyard",
  "to_stop_id": "platform",
  "approved_direction": "沿审核通道前行",
  "estimated_walk_seconds": 45,
  "walk_time_basis": ["approved_graph", "map_estimate"],
  "must_not_claim": ["未经审核的左转右转", "精确现场拥堵", "不存在的通道"]
}
~~~

角色可以说“跟随我”“不妨先往前走”，但不能新增方向事实。

### 6.6 结束语计划

由 visit_summary、Coverage 和 post_visit_award 产生，角色化表达：

- 完成情况；
- 已讲工艺和主题；
- 称号与祝福；
- 下一步服务询问。

不得新增游客没有完成的点位或事实。

## 7. 第四阶段：角色生成与验证

### 7.1 角色模型输入

角色模型只能收到：

- 当前角色 StyleBrief；
- 一个 PresentationContentPlan；
- 已审核事实正文；
- 语言和预算；
- 明确的禁止项。

不得传入完整 AgentState、原始 RAG chunk、source ID、URL、文件路径、工具名、Graph 节点名或未审核空间推断。

### 7.2 统一候选结构

~~~json
{
  "schema_version": "role_narration_candidate_v1",
  "presentation_type": "stop_guidance",
  "style_id": "ancient_scholar",
  "public_text": "角色化游客正文",
  "used_fact_ids": ["fact_001"],
  "omitted_fact_ids": [],
  "self_check": {
    "added_new_facts": false,
    "role_consistent": true,
    "within_budget": true
  }
}
~~~

模型必须输出严格 JSON object。Schema 错误时允许一次受控修复；修复失败必须回退。

### 7.3 验证内容

至少检查：

1. style_id 与游客画像一致；
2. 所有 used_fact_ids 来自当前计划；
3. 必须事实原文或安全等价表达存在；
4. 没有新增人物、年代、故事、寓意、排名或认证；
5. 没有内部字段泄漏；
6. 没有违反角色禁止项；
7. listen_only 不包含问题、任务、拍照或动作要求；
8. 路线输出保留点位顺序、方向、距离和时间；
9. 不超过内容预算；
10. 游客输出边界通过；
11. 生成节点和验证节点的 state_writes 为空。

## 8. 第五阶段：Graph 接入顺序

### 8.1 当前点位链路

~~~text
stop_guidance
→ narration_content_plan
→ role_narration_generation
→ narration_validation
→ accepted: narration_commit
→ rejected: deterministic_narration_fallback
~~~

### 8.2 路线规划链路

~~~text
direct_route
→ route_presentation_content_plan
→ role_narration_generation
→ route_presentation_validation
→ route_presentation_commit / fallback
~~~

路线状态必须在确定性 direct_route 中完成；角色只处理公开说明。

### 8.3 路线开场链路

~~~text
tour_opening
→ opening_presentation_content_plan
→ role_narration_generation
→ presentation_validation
→ opening_commit / fallback
~~~

开场程序的 status、play_count 和审计仍由 tour_opening_node 控制。

### 8.4 引路链路

~~~text
next_stop_navigation / replan presentation
→ navigation_content_plan
→ role_narration_generation
→ navigation_validation
→ navigation_commit / fallback
~~~

引路验证必须比普通角色验证更严格：方向、起点、终点和时间不能改变。

### 8.5 结束链路

~~~text
visit_summary
→ closing_content_plan
→ role_narration_generation
→ closing_validation
→ closing_commit / fallback
~~~

## 9. 角色连续性

同一个 Thread 中，所有角色化输出必须使用同一个有效风格：

~~~text
route_plan.style_id == tour_opening.style_id
tour_opening.style_id == stop_guidance.style_id
stop_guidance.style_id == navigation.style_id
navigation.style_id == tour_closing.style_id
~~~

游客明确更换风格时：

- 只影响后续表达；
- 不重写已完成 Coverage；
- 不重复完成点位；
- 不修改路线；
- 不改变已审核事实。

## 10. Rollout 配置

### 10.1 默认关闭

~~~env
CJC_READ_ONLY_ROLLOUT_MODE=off
~~~

### 10.2 Shadow

~~~env
CJC_READ_ONLY_ROLLOUT_MODE=shadow
CJC_READ_ONLY_ROLLOUT_CAPABILITIES=role_narration
~~~

Shadow 要求：

- 生成角色候选但不接管游客正文；
- active_takeover == false；
- legacy_message_preserved == true；
- 生成、验证节点不写正式状态；
- 记录不同 presentation_type 的候选稳定性。

### 10.3 Active

~~~env
CJC_READ_ONLY_ROLLOUT_MODE=read_only_active
CJC_READ_ONLY_ROLLOUT_CAPABILITIES=role_narration
~~~

只有满足以下条件后才可 Active：

- 正常角色候选不再出现 invalid_candidate_schema；
- 五类输出均通过事实和角色验证；
- 失败时能稳定 fallback；
- Coverage 只提交一次；
- 路线、TourState 和 VisitorProfile 不被角色节点修改；
- 同一 Thread 的角色连续性通过。

### 10.4 角色专用故障注入

不得修改全局 DEEPSEEK_API_KEY 测试失败。应增加仅作用于角色生成的测试开关：

~~~env
CJC_ROLE_NARRATION_TEST_FAILURE=off
~~~

支持：

~~~env
CJC_ROLE_NARRATION_TEST_FAILURE=invalid_json
CJC_ROLE_NARRATION_TEST_FAILURE=invalid_schema
CJC_ROLE_NARRATION_TEST_FAILURE=unapproved_fact
CJC_ROLE_NARRATION_TEST_FAILURE=internal_field_leak
CJC_ROLE_NARRATION_TEST_FAILURE=budget_exceeded
~~~

该开关不得影响语义识别、路线规划、普通问答或其他模型调用。

## 11. 测试与验收矩阵

### 11.1 语义路由

- 普通自然表达、错别字、中英文混合；
- 多意图和冲突状态；
- 低置信度表达；
- 路线请求与知识问答冲突；
- 周边商户与馆内路线边界；
- 疑问句不得执行完成事件。

### 11.2 角色表达

每个首批角色至少验证：

- 路线规划说明；
- 路线开场；
- 一个点位讲解；
- 一条引路说明；
- 一个游客追问；
- 结束语和祝福。

### 11.3 失败回退

- 非法 JSON；
- 非法 Schema；
- 伪造新事实；
- 内部字段泄漏；
- 预算超限；
- 风格不一致；
- listen_only 违反互动边界。

### 11.4 LangSmith 必备字段

~~~text
semantic_intent_envelope
intent_arbitration
presentation_content_plan
role_narration_candidate
narration_validation
active_role_narration_audit
role_narration_evaluations
active_role_narration_audit.coverage_commit
tour_state
visitor_profile
narration_coverage
~~~

## 12. 下一步执行顺序

### 第一步：修复角色候选 Schema

负责人：角色生成链路维护者。

检查和修改：

- role_narration_prompt；
- ROLE_NARRATION_MAX_TOKENS；
- JSON object 输出约束；
- validate_candidate_shape；
- 非法 JSON 和多余字段处理；
- 一次受控修复和 fail-closed fallback。

当前实现：已补强模型内容块解码与 Graph envelope 严格反序列化；自动化验证因本机 `.venv` 指向不存在的 Python 解释器而待执行。

完成标准：古风书生、儿童友好、静听模式的 Shadow 候选均能生成并通过验证；非法 JSON、缺字段、未知字段、错误类型、未知枚举、未知版本和内部字段均失败关闭。

### 第二步：完成点位角色 Shadow

只测试：

~~~text
ancient_scholar
child
listen_only
professional
~~~

完成标准：

- generation_status == generated；
- validation_status == accepted；
- Shadow 不接管正文；
- 事实、角色、预算和互动边界通过。

### 第三步：增加统一 presentation plan

新增：

~~~text
presentation_content_plan.py
~~~

先支持：

~~~text
route_plan
tour_opening
navigation
tour_closing
~~~

点位继续复用现有 narration_content_plan。

### 第四步：接入路线规划和开场

修改范围：

- direct_route_node；
- tour_opening_node；
- 路线公开正文生成位置。

目标：路线事实仍由 Workflow 生成，公开表达由角色层生成。

### 第五步：接入引路和重规划说明

修改范围：

- next_stop_navigation；
- prepare_replan 公开提示；
- show_replan；
- show_replan_time；
- 相关路线表达验证器。

### 第六步：加入全流程角色一致性验证

至少验证：

~~~text
route_plan → tour_opening → stop_guidance → navigation → closing
~~~

所有输出的 style_id 必须一致，除非游客明确切换风格。

### 第七步：Active 小范围接管

只先启用：

~~~text
ancient_scholar
child
professional
~~~

先覆盖一条路线和两个点位，确认成功后再扩大角色和路线范围。

## 13. 完成标准

只有以下条件全部满足，才能认为全流程角色化完成：

1. 语义候选和 Workflow 裁决稳定；
2. 正常角色候选不再持续出现 invalid_candidate_schema；
3. 路线规划、开场、点位、引路和结束语全部有对应角色化链路；
4. 同一 Thread 中角色保持一致；
5. 角色输出不增加未经审核事实；
6. 路线方向、点位、时间和空间关系不被改写；
7. listen_only 不产生互动要求；
8. 角色生成失败时游客仍得到确定性安全正文；
9. Coverage 每个事实只提交一次；
10. TourState、路线和 VisitorProfile 不被生成或验证节点污染；
11. 游客正文不泄漏内部字段；
12. Shadow、Active 和 fallback 均有 LangSmith 证据；
13. 至少一个角色完成完整路线的人工验收。

## 14. 核心决策

本项目继续采用混合 Agent 架构：

~~~text
语义理解：Agent 提议，Workflow 裁决
路线和状态：Workflow 计算和提交
内容组织：审核事实计划决定
角色表达：Agent 生成候选
公开输出：Validator 验证后提交
失败处理：确定性 fallback
~~~

本次改造不是把导游变成自由聊天机器人，而是让它在事实、路线和安全不变的前提下，具备稳定、连续、有趣的角色化导游体验。
## 15. 当前交付状态

~~~text
invalid_candidate_schema: fixed
automated_validation: partial_due_to_preexisting_failures
role_shadow: implemented_and_automated_verified
presentation_content_plan: implemented
presentation_content_plan_shadow: automated_verified
route_opening_shadow: implemented_and_automated_verified
route_opening_shadow_manual: passed_by_operator
role_active: disabled
active_takeover: disabled
full_regression: 1047/1052
p0_matrix: 10/10 passed
~~~

在自动化定向测试、完整回归和 P0 安全/游客输出测试完成前，不得把本阶段写成已通过，也不得开启 `read_only_active`。
