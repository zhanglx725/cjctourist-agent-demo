# 受控 Agent 架构升级方案

```yaml
document_status: proposed_pending_owner_approval
baseline_commit: e03c0920f6c66d9a1eb78feec78b39aa1f8295f9
branch: main
created_at: 2026-08-01
updated_at: 2026-08-01
requirements_source: data/chen_clan_academy/evaluation/handoffs/NEXT_STAGE_ISSUE_AND_ROADMAP.md
owner: pending_owner_confirmation
implementation_status: not_started
langsmith_status: not_run
```

> 本文是架构设计与迁移计划，不代表生产 Agent 已完成升级。本次交付不改变任何运行行为；未经负责人确认，不得执行 Phase 1。

## 1. 升级背景

### 1.1 当前真实形态

当前项目是“确定性 Workflow + 局部 Agent”的混合系统：

- `agent_graph.py` 使用 LangGraph `StateGraph` 固定节点、固定边和 `route_initial_request()` 等条件路由。
- `llm_think → rag_tool → llm_think` 已具备局部 ReAct 工具循环；当前模型绑定的核心工具是 `chen_clan_academy_rag_search`，循环上限为 3。
- 到达、完成、下一站、跳过、路线确认、重规划确认等控制意图，由 `tour_intent.py`、`pre_semantic_arbitration.py`、`semantic_normalization.py` 和 `tour_interaction.py` 的确定性链路治理。
- `TourState`、`VisitorProfile`、正式路线、空间节点、`NarrationCoverage` 分属不同契约，不允许模型直接写入。
- 普通知识、术语、对象、点位 inventory、工艺位置、研究、比较、拍照、安全规则和若干 RAG 回退已形成多条受控能力，但入口与格式化位置仍较分散。
- Studio 运行时由平台托管持久化；CLI 图使用 `MemorySaver`。两种环境都依赖 `thread_id` 隔离会话。

### 1.2 当前问题

1. `route_initial_request()` 累积了大量关键词、优先级和状态分支，自然表达覆盖需要持续补词。
2. 相同知识问题可能因是否已有路线而进入 `direct_rag` 或 `tour_qa`，能力入口不完全统一。
3. 多意图通常只能选择一个路由；混合控制操作需要大量专门澄清逻辑。
4. 工具能力尚无集中注册表，资格、证据、副作用、失败策略和游客可见字段缺少统一声明。
5. 模型决策、政策校验和状态变更权限尚未形成统一协议。
6. 虽已存在游客输出门控，历史上不同出口曾各自拼接来源或原始检索内容，说明最终边界仍需架构级保证。
7. P1 控制层尚有未完成或待实链复测事项；在这些问题关闭前，不能用新 Agent 编排掩盖旧链路缺陷。
8. 经典/定制模式尚无统一产品协议，规划收集被知识问答打断后的恢复规则也未冻结。
9. 术语、比较、研究和打卡卡已有注册与资格，但缺少按当前审核点位、明确兴趣、模式和预算执行的确定性调度层。
10. 点位 inventory、动态服务事实及不同问答出口仍需统一精选、时效和游客渲染边界。

### 1.3 为什么不能直接改为自由 ReAct

直接使用无约束 `create_react_agent()` 会把控制意图、事实检索和状态副作用放进同一个自由循环，带来状态越权、伪造 ID、部分执行、证据绕过、路线自动应用和循环失控。陈家祠导览需要审核点位、对象、路线、服务事实与来源的强约束，因此模型只能提出候选决策，不能成为事实源、权限源或状态机。

## 2. 升级目标

- 提高自然语言单意图识别和多意图分解能力。
- 规划前后共享同一能力入口和同一游客输出边界。
- 让模型只生成结构化候选决策，不直接生成事实、审核 ID 或状态变化。
- 统一工具注册、运行资格、证据要求、副作用等级和失败策略。
- 保留确定性状态机、路线规划器、证据门控、安全规则和确认流程。
- 保留 `thread_id` 隔离、结构化审计字段与 LangSmith 可观测性。
- 支持按能力灰度启用、随时回退、逐阶段迁移，不一次性重写图。
- 保证游客在规划前和导游过程中均可提问；导游中的只读问答不得破坏当前路线、点位和进度，回答后可从原状态继续。
- 将“开始导游/规划路线”稳定归入画像收集与确定性路线规划，而非普通 RAG；自然时长、少走路和明确偏好作为受控参数保留。
- 冻结经典/定制双模式协议：经典模式以时间生成代表性路线，定制模式仅收集游客明确选择的最小偏好。
- 在 E5 和模式契约稳定后，以确定性 CardDispatcher 将合格卡片作为可选增强内容，而非默认事实或强制插播。
- 对当前需求文档中的 P0/P1 问题实行“先关闭或明确阻塞，再迁移对应能力”的门槛。

### 2.1 当前需求对架构迁移的约束

| 需求层级 | 当前要求 | 对本方案的约束 |
|---|---|---|
| P0 | 安全结论优先，商业拍摄、无人机、闪光灯、触摸、饮食地点等不得被拍照/到达/路线流程抢占 | Input Guard 永久位于 Planner 前；安全能力不能灰度放宽 |
| P1 | 路线、状态、空间、问答证据、游客渲染和自然同义表达先稳定 | 对应能力未自动回归且未完成 LangSmith 复测时，只能 shadow，不得替换旧权威路径 |
| P2 | 经典/定制模式、收集中断恢复和卡片调度 | 先冻结模式契约，再实现 CardDispatcher；不通过聊天语气推断画像 |
| P3 | 地图、扫码、定位等可信位置事件 | 暂不属于本次架构迁移的前置能力，保留接口位但不实现 |
| P4 | GPS、蓝牙、图像识别、长期画像与推荐 | 明确延期，不作为当前 Demo 或受控 Agent 上线门槛 |

本方案不把需求文档中标为 `verified_fixed` 的问题重新包装成待开发功能；它们进入 CA-00 回归基线。标为 `implemented_pending_*`、`partial_*` 或 `blocked_*` 的问题必须保留真实状态，不能仅因架构设计存在就宣称解决。

### 2.2 进入迁移前的真实问题门槛

| 问题组 | 当前需求文档状态 | 架构处理 |
|---|---|---|
| P0-01/P0-02 安全门控 | 已实现、仍需 LangSmith 守护复测 | 固化为 Input Guard 硬门槛，任何新能力不得绕过 |
| P1-04 空间别名/反向导航 | `blocked_pending_owner_confirmation` | 不自建别名或节点；空间负责人确认前，相关 Agent 能力保持关闭 |
| P1-11 偏航后重规划 | `partial_langsmith_verification` | 只包装现有 proposal/确认链；未知点与未确认点失败关闭 |
| P1-12 自然同义表达 | 本机/LangSmith 待继续验证 | Planner 只能产受控候选，最终仍经现有解析器、审核点位和状态相位校验 |
| P1-13/P1-14/P1-16 | 身份替代、多工艺位置、团队发票存在局部或出口问题 | Phase 1 先统一能力与游客渲染，不由通用 RAG 或模型补写 |
| P1-19/P1-21 | 内部字段泄漏修复待 LangSmith 复测 | Visitor Response Renderer 作为所有出口硬门槛，结构化 evidence 仍保留内部 |
| P2-01 至 P2-03 | 模式及恢复协议 `open` | CA-12 契约先行；未批准前不写 `tour_mode` |
| P2-04 至 P2-07 | 卡片调度和点位表达待实现/分诊 | CA-13 在 E5、模式、资格和长度预算满足后实施 |

## 3. 非目标

本升级不包括：

- 删除 LangGraph 或将系统改成完全自由的 ReAct Agent。
- 让 LLM 自由生成路线、空间节点、对象、来源或文化事实。
- 让 LLM 直接修改 `TourState`、`VisitorProfile`、正式路线或 `NarrationCoverage`。
- 新建第二套 `VisitorProfile`、TourState、路线或知识事实源。
- 用模型记忆补充文物故事、题材、寓意或位置。
- 让模型在本地证据缺失时补写陈家祠专属历史、对象、位置、工艺、服务、安全或动态开放事实。
- 绕过卡片运行资格、审核映射、证据门控和来源登记。
- 修改知识库事实，或用 Agent 代替所有确定性校验。
- 一次性重写 `agent_graph.py` 或删除全部旧路由。
- 在本阶段实现 GPS、蓝牙、二维码、图像识别、长期画像或无证据的周边推荐。
- 在经典模式中默认收集偏好，或在定制模式中根据聊天语气猜测年龄、身份、同行人或研究目的。

## 4. 当前代码审计结论

### 4.1 当前调用链

| 场景 | 当前入口与主要链路 | 当前性质 |
|---|---|---|
| 普通知识 | `semantic_normalization → route_initial_request → direct_rag/tour_qa/llm_think` | 状态相关的分散入口 |
| 通用 RAG | `direct_rag → llm_think → rag_tool → llm_think` | 局部 ReAct，最多 3 轮 |
| 到达/完成/下一站 | `pre_semantic_arbitration/semantic_normalization → tour_intent → tour_event → handle_tour_event` | 确定性控制 |
| 路线规划 | `profile_collection → direct_route → route_selection/route_planner` | 确定性候选与状态初始化 |
| 重规划 | `prepare_replan → time confirmation → candidate → confirm_replan` | proposal 后确认应用 |
| 术语 | `tour_qa → term_card_runtime/术语审核资料` | 资格受控只读能力 |
| 对象讲解 | `tour_qa` 对象解析，或 `stop_guidance` 的 E5 证据包与渲染 | 审核映射和证据门控 |
| 点位 inventory | `tour_qa` + `node_guide_cards_v1.json` | 只读完整白名单 |
| 研究/比较 | `research_card_retrieval` / `comparison_retrieval` | 意图与卡片状态受控 |
| 拍照/安全 | `photo_spot_runtime` / `visit_safety_rules` | 高优先级安全门控 |
| E5 成功讲解 | `guide_program_evidence → guidance_evidence_bundle → narration_rendering → coverage` | 成功且有证据后记录覆盖 |
| E5 失败回退 | B3/安全关闭，继续受游客输出边界约束 | 不得补造事实 |
| 最终游客消息 | 多节点构造 `AIMessage`，现有 `public_visitor_message_or_fallback` 提供公共门控 | 已有可复用兜底 |
| 经典/定制模式 | 尚无冻结产品协议 | P2-01 至 P2-03，待契约先行 |
| 到点卡片增强 | 卡片已注册且有资格门控，`StopProgram` 插槽尚未调度 | P2-04 至 P2-06，待 E5/模式契约 |

### 4.2 唯一事实源

| 领域 | 唯一事实源/契约 |
|---|---|
| 游览进度 | `TourState`，只能经 `handle_tour_event()` 等冻结适配层变化 |
| 游客偏好 | `VisitorProfile` 及其验证/更新模块 |
| 路线与空间 | 审核路线、空间图、节点注册和确定性规划器 |
| 普通知识 | 本地审核知识文件经 `rag_retrieval.py` 返回的 `RetrievedEvidence` |
| 卡片能力 | 卡片注册表、运行资格清单和各卡片检索器 |
| 对象—点位 | `node_guide_cards_v1.json` 等审核映射 |
| 讲解覆盖 | `NarrationCoverage`，与 TourState/Profile 独立 |
| 来源 | source registry 与 evidence 内部字段 |

`tour_mode` 尚未有已批准的唯一归属，不能在本方案中擅自写入 `VisitorProfile`、TourState 或新建会话状态。Phase 0 必须先决定它属于 VisitorProfile、路线快照还是会话控制，并冻结迁移/兼容规则。

### 4.3 必须永久确定性的机制

- 安全请求优先级、输入防护和提示注入防护。
- 审核 node/ornament/card/source ID 解析与白名单复核。
- `TourState` 事件应用、完成/跳过/到达语义和路线状态变化。
- `VisitorProfile` 验证与更新语义。
- 路线预算、空间连通性、候选计算及确认后应用。
- E5 evidence 校验、失败关闭和 Coverage 写入条件。
- 卡片运行资格、研究归因、英文资格与动态事实有效期。
- 最终游客输出边界和审计信息分离。
- 经典/定制模式选择、默认值及最小偏好收集规则。
- CardDispatcher 的输入白名单、资格、预算、点位和主动触发条件。

### 4.4 可逐步 Agent 化的部分

- 自然语言意图候选与多意图分解。
- 在已注册只读工具之间选择能力。
- 缺少参数时生成澄清建议。
- 组织只读工具调用顺序和回答结构。
- 路线/重规划“候选请求”的参数收集，但不能应用候选。
- 向确定性控制面提出 `TourEvent` 请求，但不能直接写状态。
- 识别知识问答对导游流程的临时打断，并在只读回答后提出“恢复到原收集项/原导航状态”的候选；恢复本身不得重建路线或覆盖已确认偏好。

### 4.5 可复用基础

现有 `@tool`/`bind_tools`、受控知识计划、`RetrievedEvidence`、卡片资格、对象审核映射、E5 evidence bundle、`NarrationCoverage`、游客输出门控、性能指标、消息元数据和 LangSmith Trace 均可复用。无需新建第二套事实或状态模型。

未发现阻止“方案设计”本身的冻结契约冲突，但存在会阻止具体能力实施的未决事项：P1-04 空间节点/别名需负责人确认，`tour_mode` 的唯一归属尚未批准，E5 与部分 P1 出口仍待本机或 LangSmith 验证。部分历史交接材料早于当前生产实现；后续实现必须以任务开始时的真实代码、冻结契约、审核数据和最新需求状态为准，不能用本文或历史描述覆盖当前事实。

## 5. 架构原则

1. Agent 只产生候选决策，不能直接执行副作用。
2. Policy Gate 对候选意图、参数、资格、证据和状态进行确定性校验。
3. 工具只读取或调用已有受控能力，不成为第二事实源。
4. 状态机是游览状态变化的唯一入口。
5. 审核数据是点位、对象、路线与文化事实的唯一来源。
6. 副作用操作必须明确分级，proposal 不得自动应用。
7. 无证据、证据冲突或证据过期时失败关闭。
8. 游客正文与内部 evidence/Trace 严格分离。
9. 多意图先原子化计划；任何状态副作用失败时不得留下部分状态。
10. Agent 决策、策略拒绝、工具输入输出和状态适配必须可审计，但不保存 Chain-of-Thought。

## 6. 目标架构

```mermaid
flowchart TD
    U["User"] --> IG["Input Guard"]
    IG -->|"安全拒绝"| VR["Visitor Response Renderer"]
    IG --> DC["Deterministic Control Arbitration"]
    DC -->|"已确认控制意图"| ST["State Transition Adapter"]
    DC -->|"需澄清"| CL["Clarification"]
    DC -->|"知识/复合候选"| AP["Agent Planner"]
    AP --> PG["Policy Gate"]
    PG -->|"拒绝/低置信度"| CL
    PG -->|"允许只读"| TR["Tool Registry"]
    PG -->|"允许候选"| TR
    TR --> TE["Tool Executor"]
    TE --> EV["Evidence & Result Validator"]
    EV -->|"只读知识结果"| VR
    EV -->|"恢复原导游上下文"| RS["Resume Adapter"]
    EV -->|"路线/重规划 proposal"| VR
    EV -->|"已确认状态请求"| ST
    EV -->|"无证据/失败"| CL
    ST -->|"普通控制结果"| VR
    ST -->|"到达审核点"| CD["Card Dispatcher"]
    CD -->|"合格可选增强"| VR
    CD -->|"无合格增强"| VR
    RS --> VR
    CL --> VR
    VR --> END["END"]

    RO["只读知识通道"] -.-> TR
    RP["路线候选通道"] -.-> TR
    SC["状态控制通道"] -.-> ST
    AU["Trace / Audit Metadata"] -.-> AP
    AU -.-> PG
    AU -.-> TE
    AU -.-> EV
    VR -. "只显示安全正文" .-> END
```

不可绕过边界：Input Guard、Policy Gate、审核 ID 解析、Evidence Validator、State Transition Adapter、Card Dispatcher 资格/预算门控、Visitor Response Renderer。Agent Planner 不得直接连接状态、数据库、文件系统或最终游客消息。Resume Adapter 只能读取并恢复既有流程位置，不得新建第二份 Profile、路线或游览状态。

## 7. 当前模块到目标架构的映射

| 当前模块 | 当前职责 | 目标职责 | 保留 | 工具化 | 副作用 | 阶段 | 风险/测试 |
|---|---|---|---|---|---|---|---|
| `agent_graph.py` | 图、状态、路由、节点 | 保留图骨架，新增受控 planner/gate/executor 节点 | 是 | 否 | 编排 | 2–7 | 图回归、循环上限 |
| `pre_semantic_arbitration.py` | 模型前控制仲裁 | Deterministic Control Arbitration | 是 | 否 | 无 | 0–2 | 控制优先级 |
| `tour_intent.py` | 控制意图与审核点位解析 | 控制候选校验器 | 是 | 可包装请求 | 无 | 5 | 同义词、伪 ID |
| `semantic_normalization.py` | 闭合语义候选 | AgentDecision 输入适配/回退 | 是 | 否 | 无 | 2 | schema/低置信度 |
| `tour_interaction.py` | 唯一事件适配 | State Transition Adapter | 是 | 仅受控 adapter | 有 | 5 | 状态非法写入=0 |
| `tour_state.py` | 纯状态函数 | 继续作为状态事实源 | 是 | 禁止直接暴露 | 有 | 全程 | 状态机测试 |
| `visitor_profile.py` 等 | 偏好模型与更新 | 继续经验证器更新 | 是 | 仅受控 proposal | 有 | 4–5 | 第二事实源=0 |
| `route_planner.py`/`route_selection.py` | 路线计算与选择 | route proposal 工具后端 | 是 | 是 | proposal | 4 | 预算/空间/确认 |
| `replanning.py` | 重规划候选 | replan proposal 工具后端 | 是 | 是 | proposal | 4 | 原点/快照/确认 |
| `tour_navigation.py` | 下一段导航 | 只读导航工具后端 | 是 | 是 | read_only | 1/4 | 不改状态 |
| `tour_qa.py` | 多类知识出口 | 拆为注册能力适配，保留旧回退 | 过渡保留 | 是 | read_only | 1–7 | 规划前后等价 |
| `controlled_knowledge_query.py` | 受控知识计划与渲染 | fact/service/craft 工具与结果校验 | 是 | 是 | read_only | 1 | 类别与输出边界 |
| `single_fact_answer.py` | 单一事实 | single_fact 工具后端 | 是 | 是 | read_only | 1 | 时间口径/无证据 |
| `term_card_runtime.py` | 术语资格 | term 工具后端 | 是 | 是 | read_only | 1 | 英文/实例资格 |
| `research_card_retrieval.py` | 研究卡 | research 工具后端 | 是 | 是 | read_only | 1 | 归因与限制 |
| `comparison_retrieval.py` | 比较卡 | comparison 工具后端 | 是 | 是 | read_only | 1 | 不冒充事实 |
| `photo_spot_runtime.py` | 拍照点 | photo 工具后端 | 是 | 是 | read_only | 1 | 安全姿势优先 |
| `visit_safety_rules.py` | 安全规则 | Input Guard/安全工具 | 是 | 可只读 | read_only | 0–1 | 安全优先 |
| E5 evidence/render/coverage | 讲解证据与覆盖 | narration 工具后端及 validator | 是 | 是 | read_only/受控覆盖 | 1–3 | 证据/覆盖语义 |
| `guidance_policy.py` / `narration_style.py` | 讲解策略与表达风格 | 模式契约确认后的只读策略输入 | 是 | 否 | 无 | 0/6 | 不建立第二画像判断 |
| `StopProgram` 卡片插槽及卡片资格表 | 可选讲解素材与运行资格 | 确定性 CardDispatcher 输入 | 是 | 否 | read_only | 6 | 点位/模式/兴趣/预算/资格 |
| `rag_retrieval.py` | 混合检索 | 受控 RAG 工具后端 | 是 | 是 | read_only | 1 | 类别/时效/串线 |
| 游客输出门控 | 隐藏内部字段 | Visitor Response Renderer | 是 | 否 | 无 | 0–2 | 泄漏率=0 |
| `langgraph.json` | Studio 图声明 | 保持导出目标，灰度配置外置 | 是 | 否 | 无 | 2–7 | Studio/CLI 一致性 |

## 8. Agent 决策协议

建议定义严格校验的 `AgentDecision`，模型只能输出候选：

```yaml
decision_id: "runtime-generated-opaque-id"
intent: fact_question
sub_intents: []
requested_capability: single_fact
target_text: "用户原话连续片段"
reviewed_node_id: null
reviewed_ornament_id: null
requires_clarification: false
requires_confirmation: false
side_effect_level: read_only
confidence: 0.0
evidence_span: "用户原话连续片段"
```

受控 `intent`：`tour_control`、`route_planning`、`replanning`、`tour_mode_selection`、`resume_tour_flow`、`term_question`、`ornament_question`、`stop_inventory`、`craft_location`、`fact_question`、`service_rule`、`research`、`comparison`、`photo`、`safety`、`clarification`、`small_talk`。

受控 `side_effect_level`：`read_only`、`proposal`、`confirmed_state_change`、`prohibited`。

校验规则：

- `decision_id` 由运行时生成，不信任模型提供值。
- `target_text`/`evidence_span` 必须是本轮用户原话的连续片段。
- 模型给出的 node/ornament ID 仅是提示；系统必须从原话重新调用审核解析器，且不接受自造 ID。
- `confidence` 只影响澄清，不得绕过资格、证据或权限校验。
- 多意图输出必须包含有序 `sub_intents`、依赖关系、原子组和失败策略。
- 任何包含状态副作用的计划都必须经 Policy Gate 和冻结事件适配器；未确认只能产生 proposal。
- `tour_mode_selection` 只接受游客明确选择；在 Phase 0 未冻结字段归属前一律不可写入状态。
- `resume_tour_flow` 只能恢复打断前已存在且仍有效的收集项、导航或讲解上下文；不得凭模型重算下一站。

## 9. Tool Registry 设计

注册项统一格式：

```yaml
tool_name: reviewed_single_fact
capability: single_fact
input_schema: {}
output_schema: {}
side_effect_level: read_only
allowed_states: [pre_tour, touring, explaining, awaiting_confirmation]
requires_confirmation: false
evidence_requirements: [reviewed_category, registered_source]
runtime_eligibility: controlled
timeout_policy: fail_closed
failure_policy: clarification_or_safe_unavailable
audit_fields: [tool_name, decision_id, source_ids, evidence_ids, latency_ms]
visitor_visible_fields: [answer_text]
```

首批注册类别：

| 能力 | 后端 | 等级 | 关键门控 |
|---|---|---|---|
| 术语解释 | `term_card_runtime.py` | read_only | runtime eligibility/英文资格 |
| 明确对象讲解 | 对象审核映射 + E5 evidence | read_only | node/object/evidence 同源 |
| 点位精选 | `tour_qa` inventory 数据 | read_only | 审核白名单、长度预算 |
| 多工艺位置 | `controlled_knowledge_query`/位置审核资料 | read_only | 多实体逐项证据 |
| 单一事实 | `single_fact_answer.py` | read_only | 事实类别与时间口径 |
| 服务规则 | 受控知识模块 | read_only | 动态有效期/安全关闭 |
| 研究卡 | `research_card_retrieval.py` | read_only | 研究意图与归因 |
| 比较卡 | `comparison_retrieval.py` | read_only | research-only 边界 |
| 拍照与安全姿势 | `photo_spot_runtime.py` + safety | read_only | 安全优先 |
| 路线候选 | 现有 route planner | proposal | 预算/空间/画像验证 |
| 重规划候选 | `replanning.py` | proposal | 当前位置快照/确认 |
| 导航 | `tour_navigation.py` | read_only | 当前正式路线 |
| TourEvent 请求 | `tour_intent` + `handle_tour_event` | confirmed_state_change | 明确事件/确认/状态相位 |
| E5 站点讲解 | E5 模块 | read_only + 受控 coverage | evidence 后渲染 |
| 受控 RAG 回退 | `rag_retrieval.py` | read_only | 类别、来源、时效、输出边界 |
| 导游流程恢复 | 现有 `profile_collection`/路线/导航上下文 | read_only | 只恢复已有流程位置，不覆盖已确认字段 |
| 卡片增强候选 | StopProgram + GuidancePolicy + 卡片资格/关联 | read_only | 当前审核 node、明确模式/兴趣、预算、资格 |

禁止向 Agent 暴露自由 SQL、自由文件读取、任意代码执行、任意网络搜索或状态字典写入工具。动态营业信息将来如接入网络，只能通过单独注册的官方来源查询工具，并具有域名、有效期、超时和失败关闭策略。

## 10. 权限与副作用治理

| 等级 | 含义 | 执行规则 |
|---|---|---|
| `read_only` | 术语、事实、对象、点位等查询 | Agent 可选择；仍需资格、参数和 evidence 校验 |
| `proposal` | 路线/重规划候选 | 可生成和展示，绝不能自动应用 |
| `confirmed_state_change` | 到达、完成、跳过、应用候选等 | 必须有明确用户输入，并经冻结适配层 |
| `prohibited` | 直接写状态/数据、绕过门控 | 永不注册、永不执行 |

永久禁止：直接写 `tour_state`；直接改 VisitorProfile 原始字典；直接修改正式路线、空间图、知识库、卡片和来源；自造点位/对象/来源；绕过安全或确认；任意执行代码/文件操作。

CardDispatcher 不是 Agent 自由选材工具：它接收当前审核 `node_id`、StopProgram、GuidancePolicy、已冻结的模式值、游客已明确偏好、剩余预算和资格注册表，输出可审计候选。基础对象事实优先；术语、比较、研究和打卡只能作为可选增强。经典模式默认不主动插入拍照；研究观点必须归因；比较不能冒充唯一事实；打卡必须有摄影意图并继续服从现场安全限制。

## 11. 多意图处理

| 用户输入 | 子意图 | 处理与原子性 |
|---|---|---|
| 我到月台了，顺便讲讲石雕。 | 到达 + 工艺讲解 | 先确定性解析月台并验证是否允许到达；到达成功后只读讲解。若到达不合法，整体澄清，不先写状态；允许在状态成功后返回知识结果。 |
| 我到月台了，讲截江夺阿斗，再帮我重排。 | 到达 + 对象讲解 + 重规划 | 原子控制组：先验证到达和对象—点位；再展示讲解；重规划只生成 proposal。任何位置/对象歧义时不应用状态。 |
| 我只有30分钟，喜欢灰塑，先规划再告诉我第一站。 | 偏好更新 + 路线候选 + 首站说明 | 验证 Profile 输入，确定性规划器生成路线；若产品契约仍允许初始路线直接建立，复用现有入口，否则展示 proposal。第一站来自正式/候选结构，不由模型自造。 |
| 我还在去前东庭的路上，先讲一下那里有什么。 | 途中状态 + 点位只读问答 | “还在路上”禁止转为到达；不改状态。可对审核前东庭做远程只读简介，并使用“审核关联、以现场为准”措辞。 |
| 收集到时长后，游客先问“周二开放吗”。 | 规划收集打断 + 服务问答 + 恢复 | 保留已确认时长；先以受控服务证据回答，再只提示模式或下一项缺失字段，不重复询问时长。 |
| 导航途中问“灰塑是什么”，回答后继续。 | 只读工艺问答 + 导游恢复 | 问答不修改 TourState/Profile/正式路线；回答结束后从原 `pending_stop_id` 和导航相位继续，不由模型选择新站。 |

多意图原则：先划分只读与副作用；副作用组成原子组；只读结果不得掩盖副作用失败；需要澄清时不进行部分状态修改；proposal 可以展示但不能自动应用。

## 12. 状态治理

- 长期线程状态：`TourState`、`VisitorProfile`、`NarrationCoverage`、正式路线、已确认的交互状态、`qa_context`、pending replan/clarification；由现有契约持久化。
- 当前轮临时决策：AgentDecision、候选工具计划、参数校验结果、原子执行计划；完成后只保留必要审计摘要。
- 审计信息：decision/tool/policy/result IDs、source/evidence IDs、拒绝原因、延迟、版本、thread_id；不进入游客正文。
- 不可持久化：模型 Chain-of-Thought、自由草稿、未经验证 ID、未经审核事实。
- `NarrationCoverage` 保持独立语义；`qa_context` 不成为对象事实源；pending 状态必须线程隔离并具有消费/过期规则。
- 模式选择不得形成第二套画像；在归属契约冻结后，只能通过该唯一字段及现有验证器更新。定制模式未填写项保持中性默认。
- 规划收集被只读问答打断时，已确认字段和唯一待收集字段必须保存在线程内现有交互状态；回答完成后恢复，不重建 Profile 草稿。
- 不创建第二套状态，也不把 Agent memory 当成事实源。

## 13. 证据治理

| 内容 | 真实来源与限制 |
|---|---|
| 术语 | 术语卡、资格清单、关联表；草稿英文不得输出 |
| 工艺 | `07_ornament_crafts.md` 提供总述，不替代单件对象事实 |
| 对象 | `08_ornament_items.md` + 同一 ornament_id 审核证据 |
| 位置 | `09_ornament_locations.md`、空间/点位卡；映射只证明审核关联，不保证眼前可见 |
| 路线 | 审核空间图、路线数据和确定性规划器 |
| 服务事实 | 对应审核资料；动态事实必须检查有效期 |
| 研究/比较 | 资格合格卡片，保留“研究认为”等归因 |
| 通用闲聊 | 可由已接入 LLM 组织，不得携带或补写陈家祠专属事实 |

`source_ids`、document/chunk 标识只保留内部。陈家祠专属事实无证据时安全关闭；证据冲突时拒绝合并并记录 finding；证据过期时不得作为当前结论；来源未登记时不得使用。Agent 不能再次调用 LLM 补齐 evidence 空槽。

LLM 回退边界采用两级策略：

1. 对陈家祠历史、建筑、对象、位置、工艺、票务、开放、安全、路线、卡片和“当前/今日/附近”等动态或项目事实，只能使用审核 evidence 或受控实时来源；缺失时明确资料不足或引导官方渠道。
2. 对与陈家祠事实无关的通用闲聊或一般性知识，可由已接入 LLM 回答，但必须标记为通用说明，不能伪装成本馆资料、不能写状态、不能影响路线，并经过统一游客输出门控。

动态营业信息必须记录来源有效期；过期公告只能作为历史记录，不得回答当前事实。点位 inventory 的完整白名单仅供内部选择，游客端默认输出代表对象、分层说明和长度预算，不能直接倾倒全量清单。

## 14. 最终游客输出治理

所有出口必须经过统一 Visitor Response Renderer。游客文本禁止文件名/路径、Sxx、`source_ids`、URL、原始 chunk、node/ornament/card ID、本地快照、资料日期、工具字段、内部状态和系统工作过程。内部 Trace、evidence、Coverage 依据保持完整。

Renderer 是最后兜底，不能代替生产出口的结构化分离；若移除内部包装后正文不足，应返回非空、无事实扩写的安全说明，不得调用 LLM 二次改写。

## 15. LangGraph 目标图

目标节点：`input_guard`、`deterministic_control`、`agent_planner`、`policy_gate`、`tool_executor`、`result_validator`、`state_transition`、`resume_adapter`、`card_dispatcher`、`clarification`、`visitor_renderer`。

- 保留现有 `tour_event`、路线、重规划、E5、QA 后端节点；初期通过 adapter 包装，不立即删除。
- 将大量知识条件边逐步收敛为 planner → gate → executor；安全和状态控制边始终在 planner 之前。
- Agent 每轮最多 3 次工具调用、最多 1 次重规划；同一工具同参不得重复。
- 工具失败后仅允许一次受控替代或澄清；不得回退到无约束 LLM。
- 通用闲聊 LLM 与项目事实工具必须是两个明确能力：前者不能回答陈家祠专属事实，后者缺证据时不能转交前者补写。
- CLI 继续使用显式 checkpointer；Studio 继续由平台管理，不在图中重复注入 checkpointer。
- 所有 pending、decision 和 audit 以 `thread_id` 隔离；跨线程复用一律禁止。

### 15.1 后续 Graph-assisted Hybrid RAG 边界

需求文档将图辅助检索标为 `planned_not_started`。它不是当前 P1 修复或受控 Agent 迁移的替代方案，也不在 CA-00 至 CA-15 的必做范围内。若后续启动，只能从现有权威 JSON、CSV、空间图和卡片注册表自动派生只读关系索引，例如 `Place → Ornament → Craft/Term → Source/Card`，用于实体消歧、当前点实例查询和多跳候选约束；具体事实仍须回到原始审核资料和混合 RAG evidence。该索引不得成为第二份人工维护的事实源，不得替代 TourState、路线空间图、审核对象映射或来源登记，接入前必须与现有混合 RAG 在同一评测集和 LangSmith 场景中对照。

## 16. 分阶段迁移计划

| 阶段 | 目标/输入输出 | 允许与禁止 | 自动测试 / LangSmith | 门槛、回滚、依赖、负责人 |
|---|---|---|---|---|
| Phase 0 契约、P1 门槛与基线冻结 | 冻结现状矩阵、事实源、模式归属、P1 状态和基线报告 | 允许加 schema/测试/配置草案；禁止改生产路由 | 以当前完整回归实际数量为准；LangSmith 保存 P0/P1、规划前后、打断恢复场景 | 未关闭 P1 只能保留旧权威或 shadow；依赖负责人确认；owner: architecture_owner + QA |
| Phase 1 只读知识工具化 | 术语、事实、服务、对象、点位精选、多工艺统一为工具结果 | 允许 adapters/registry；禁止状态副作用 | 每工具 schema/资格/evidence/输出测试；LangSmith 规划前后等价 | 只读状态误写 0；单能力开关回滚；依赖 Phase 0；owner: knowledge_runtime_owner |
| Phase 2 Planner + Policy Gate | 结构化候选、低置信度澄清、旧路由回退 | 允许 shadow planner/gate；禁止直接执行副作用 | schema、防伪造、策略、工具选择；LangSmith 自然变体 | shadow 一致率达标且安全错误 0；关闭开关回滚；owner: agent_orchestration_owner |
| Phase 3 多意图、追问与导游恢复 | 原子多意图、`qa_context`、当前点追问、问答后恢复原流程 | 允许只读组合及澄清；禁止部分状态写入或重建路线 | 原子性、失败回滚、上下文串线、收集/导航恢复；LangSmith 混合输入 | 部分状态修改 0、重复询问 0；依赖 Phase 2；owner: interaction_owner |
| Phase 4 路线/重规划候选工具化 | 只生成 proposal，确认后沿旧适配层应用 | 允许调用现有规划器；禁止 Agent 自选点/写路线 | 预算、空间、快照、确认；LangSmith 规划/偏航/取消 | 越权应用 0、预算超限 0；关闭 proposal 工具；owner: route_owner |
| Phase 5 控制事件适配 | Agent 只能提出 TourEvent 请求，确定性适配执行 | 允许受控事件 adapter；禁止直接写 TourState | 到达/完成/跳过/下一站、否定/途中/第三人称；LangSmith 控制变体 | 非法写入 0；回退现有控制路由；依赖交互契约；owner: state_owner |
| Phase 6 双模式与卡片调度 | 冻结经典/定制模式并实现确定性 CardDispatcher | 允许模式契约、最小偏好流程、调度器和测试；禁止猜测画像或放宽卡片资格 | 模式、打断恢复、预算/点位/资格、卡片归因；LangSmith 到点矩阵 | 未冻结模式归属或 E5 未达标则不启用主动调度；owner: product_contract_owner + card_runtime_owner |
| Phase 7 灰度与旧路由收敛 | 新旧并行评测，按能力删减重复知识边 | 允许按能力切换；禁止批量删除 | 全量回归、差分与负载；LangSmith 全矩阵 | 达标能力才删除旧边；任何硬门槛失败立即回滚；owner: release_owner |

各阶段公共回滚条件：状态/路线越权、跨线程串线、对象越界、内部字段泄漏、无证据文化事实、不可恢复循环或 p95 超过批准阈值。

### 16.1 阶段执行卡

#### Phase 0：契约与基线冻结

- 输入：当前图、冻结契约、审核数据注册、现有自动测试及已记录 LangSmith 场景。
- 输出：行为基线矩阵、事实源/状态源清单、P1 状态矩阵、`tour_mode` 唯一归属决定、硬门槛和灰度配置契约。
- 允许修改：新增架构 schema、基线测试和本阶段局部交接；禁止修改生产路由与运行行为。
- 自动测试：完整回归、状态/路线/证据/输出边界基线；LangSmith：保存规划前后、控制、知识、E5 代表场景。
- 验收门槛：基线可重复、所有事实源有唯一归属；P0 安全回归必须为 0 失败；未完成 P1 能力必须明确为旧路径权威、shadow 或 blocked，不能假装已关闭。
- 回滚条件：新增测试改变生产行为或无法稳定复现基线；依赖：负责人批准本文；建议负责人：architecture_owner、QA_owner。

#### Phase 1：只读知识工具化

- 输入：已审核术语、事实、服务、对象、点位、工艺能力及各自资格/证据接口。
- 输出：无状态副作用的注册工具结果和统一 audit envelope。
- 允许修改：Tool Registry、只读 adapter、模块测试；禁止修改 TourState/Profile/路线和知识正文。
- 自动测试：schema、资格、证据、超时、无证据关闭、游客边界、规划前后等价；LangSmith：同问法双模式与自然变体。
- 验收门槛：只读状态误写 0、内部泄漏 0、事实/来源零负回归。
- 回滚条件：任一工具不能复用真实事实源或产生状态变化；依赖：Phase 0；建议负责人：knowledge_runtime_owner。

#### Phase 2：Agent Planner 与 Policy Gate

- 输入：用户原话、只读状态快照、能力注册表；输出：经校验但默认不执行的 AgentDecision/ToolPlan。
- 允许修改：planner、policy、shadow 配置和审计；禁止删除旧路由或开放状态工具。
- 自动测试：闭合 schema、伪造 ID、置信度、权限、工具选择和最大循环；LangSmith：自然表达、低置信度、提示注入。
- 验收门槛：shadow 安全错误 0，工具选择达到批准阈值，所有拒绝可审计。
- 回滚条件：planner 可绕过 gate、不可重复决策或显著超出延迟预算；依赖：Phase 1；建议负责人：agent_orchestration_owner。

#### Phase 3：多意图、上下文追问与导游恢复

- 输入：已校验子意图、`qa_context`、打断前流程位置和只读状态快照；输出：有序原子计划、澄清、纯只读组合结果或恢复原流程提示。
- 允许修改：多意图计划器、上下文 adapter 和测试；禁止直接写状态或在失败后保留部分副作用。
- 自动测试：四类组合、顺序、依赖、失败回滚、thread 隔离、画像收集/导航问答后恢复；LangSmith：到达+讲解、到达+重排、途中+问答、收集打断等。
- 验收门槛：部分状态写入 0、错误组合 0、不可组合场景澄清正确。
- 回滚条件：原子性不能证明或 qa_context 串线；依赖：Phase 2；建议负责人：interaction_owner。

#### Phase 4：路线和重规划候选工具化

- 输入：已验证 Profile、当前位置、剩余预算和正式路线快照；输出：不可直接应用的 route/replan proposal。
- 允许修改：现有规划器 adapter、proposal schema 与确认测试；禁止模型自选节点或自动应用路线。
- 自动测试：预算、空间、快照、候选过期、取消、确认；LangSmith：初始规划、偏航重排、未知地点和混合请求。
- 验收门槛：预算超限 0、路线越权应用 0、未知位置创建路线 0。
- 回滚条件：候选无法由现有规划器重算验证或确认边界失效；依赖：Phase 3/路线契约；建议负责人：route_owner。

#### Phase 5：控制事件适配

- 输入：原话证据、审核位置、当前交互相位和已确认动作；输出：冻结 `TourEvent` 结果或澄清。
- 允许修改：请求 adapter、策略映射和状态测试；禁止暴露 TourState 纯函数或状态字典写入工具。
- 自动测试：到达、完成、跳过、下一站、否定、途中、假设、第三人称；LangSmith：自然控制变体与状态前后核验。
- 验收门槛：非法写入 0、误到达 0、未确认完成/路线应用 0。
- 回滚条件：事件请求绕过 `handle_tour_event()` 或冻结语义发生漂移；依赖：Phase 4/交互契约；建议负责人：state_owner。

#### Phase 6：经典/定制模式与卡片调度

- 输入：已冻结 `tour_mode` 契约、现有 VisitorProfile、StopProgram、GuidancePolicy、审核点位、明确兴趣、剩余预算及卡片资格表；输出：模式适配后的路线收集流程和可审计卡片增强候选。
- 允许修改：模式契约/验证器、最小偏好收集、CardDispatcher、局部测试；禁止新建第二套画像/状态、猜测身份、修改卡片正文或资格、让模型自由挑卡。
- 自动测试：经典模式只问时长、定制模式最小偏好、问答打断恢复、当前点/预算/资格筛选、研究归因、比较边界、摄影意图与安全；LangSmith：经典/定制到点矩阵。
- 验收门槛：模式只能来自明确选择；经典模式默认不推摄影；无合格卡时不插播；基础对象事实不被增强卡替代；E5 evidence 与游客边界零回归。
- 回滚条件：`tour_mode` 唯一归属未批准、E5-A/C 未达标、卡片资格不能闭合或调度引起预算/安全越界；依赖：Phase 0 模式契约及 Phase 1–5 对应能力；建议负责人：product_contract_owner、card_runtime_owner。

#### Phase 7：灰度切换与旧路由收敛

- 输入：每个能力的新旧自动差分、LangSmith 结论和性能指标；输出：逐能力启用/保留/回滚决定。
- 允许修改：配置开关、已验收重复知识边和发布文档；禁止批量删除未验收旧路径。
- 自动测试：全回归、差分、负载、故障注入；LangSmith：完整能力矩阵与 Trace 审计。
- 验收门槛：全部硬门槛为 0，准确率、工具选择、人工评分和 p95 达批准值。
- 回滚条件：任一硬门槛失败或新链路低于旧链路；依赖：Phase 1–6 分能力通过；建议负责人：release_owner。

## 17. 后续 Codex 小步任务

| task_id | 目标 | 读取/允许修改 | 禁止修改 | 测试与完成标准 | 冲突停止条件 / 提交信息 |
|---|---|---|---|---|---|
| CA-00 | 冻结架构契约与行为基线 | 读取冻结契约、图、全测试；仅新增架构 schema/基线测试文档 | 生产路由/状态 | 基线回归与场景矩阵通过 | 契约不一致即停；`test: freeze controlled agent baseline` |
| CA-01 | 定义 AgentDecision schema | 新 schema + 单测 | agent_graph 行为 | 枚举、原话 span、伪 ID、低置信度测试 | 无法映射现有意图即停；`feat: add controlled agent decision schema` |
| CA-02 | 建立 Tool Registry 元数据 | registry/adapters + 单测 | 工具业务事实 | 注册完整性、重复能力、visitor 字段测试 | 现有能力无稳定接口即停；`feat: add controlled tool registry` |
| CA-03 | 工具化术语/单事实/服务规则 | 对应只读模块与 adapter | 状态/路线 | 规划前后等价、资格、无证据关闭 | 事实源冲突即停；`feat: expose reviewed fact tools` |
| CA-04 | 工具化对象/点位/工艺位置 | 对象/点位/位置 adapters | 知识正文/映射 | ID、白名单、同名消歧、精选测试 | 数据映射异常即停；`feat: add reviewed ornament tools` |
| CA-05 | shadow Agent Planner | planner、配置、审计、单测 | 旧路由删除 | 只产候选、不执行；工具选择离线评测 | 候选不可确定性验证即停；`feat: add shadow agent planner` |
| CA-06 | Policy Gate | gate、权限策略、单测 | 状态机语义 | 资格、证据、副作用、prohibited 测试 | 权限无法闭合即停；`feat: enforce agent policy gate` |
| CA-07 | 只读工具执行与结果验证 | executor/validator、相关测试 | 状态事件 | 超时、失败、evidence、循环上限 | 陈家祠事实需要自由 LLM 补证即停；`feat: execute controlled read tools` |
| CA-08 | 多意图原子计划 | planner/gate/qa context 测试 | 状态直接写入 | 四场景、无部分状态、澄清测试 | 原子性不能保证即停；`feat: add atomic multi-intent plans` |
| CA-09 | 路线候选工具 | route adapter + 测试 | 正式路线直接写入 | 预算、空间、proposal 不应用 | 规划器输出不可验证即停；`feat: expose route proposal tool` |
| CA-10 | 重规划候选工具 | replanning adapter + 测试 | 自动确认 | 原点快照、取消、过期、线程隔离 | pending 契约冲突即停；`feat: expose replan proposal tool` |
| CA-11 | TourEvent 请求适配 | control adapter + 状态测试 | TourState 直接写入 | 同义词/负例/确认/状态不变量 | 冻结事件缺口即停；`feat: gate agent tour event requests` |
| CA-12 | 冻结经典/定制模式及恢复协议 | 模式契约、验证器、收集/恢复测试 | 第二画像事实源、卡片调度 | 明确选择、最小偏好、问答打断恢复 | `tour_mode` 归属未确认即停；`feat: define tour mode contract` |
| CA-13 | 确定性卡片调度 | CardDispatcher、资格/预算/点位测试 | 卡片正文、自由模型选卡 | 基础事实优先、资格和安全零绕过 | E5/模式契约未通过即停；`feat: dispatch eligible tour cards` |
| CA-14 | 图接入与按能力灰度 | agent_graph、配置、E2E | 一次性删除旧边 | shadow/active/fallback 三模式，全回归 | 完整回归或硬门槛失败即停；`feat: integrate controlled agent graph` |
| CA-15 | LangSmith 对照与旧边收敛 | 评测/局部路由 | 未达标能力旧路由 | 人工矩阵和差分指标达标 | 任一硬门槛失败不删除；`refactor: converge verified agent routes` |

建议第一项：CA-00。执行顺序为 CA-00 至 CA-12 契约冻结，再在 E5/模式/资格条件满足后执行 CA-13，最后执行 CA-14/CA-15。每个任务只处理一个可验收能力，并在开始前重新确认当前 HEAD、工作区和契约。

### 17.1 任务执行卡

以下每项均须先读 `PROJECT_REQUIREMENTS.md`、`COLLABORATION_GUIDE.md`、相关冻结契约、`agent_graph.py`、对应生产模块和现有测试；共同禁止修改知识库事实、空间/路线审核数据、卡片正文与来源登记。各项实际文件范围必须在只读审计后收敛，不能仅凭本文猜测。

#### CA-00 — 冻结基线

- 目标：冻结当前行为、事实源、状态源和硬门槛；允许修改：新增基线测试/局部交接；禁止修改：生产代码和路由。
- 新增测试：双模式能力矩阵、状态/证据/输出不变量；回归：完整 unittest；LangSmith：记录当前代表链路，不宣称新能力。
- 完成标准：基线可重复且差异可解释；冲突停止：契约与代码的唯一状态/事实源不一致；提交：`test: freeze controlled agent baseline`。

#### CA-01 — AgentDecision schema

- 目标：实现闭合候选协议；允许修改：新 schema/validator 及单测；禁止修改：图路由和执行节点。
- 新增测试：枚举、原话 span、伪 ID、低置信度、非法组合；回归：semantic/tour intent；LangSmith：不执行，仅准备案例。
- 完成标准：任何模型输出可确定性接受或拒绝；冲突停止：现有意图无法无损映射；提交：`feat: add controlled agent decision schema`。

#### CA-02 — Tool Registry

- 目标：集中声明能力、资格、证据和副作用；允许修改：registry 元数据/adapter；禁止修改：工具后端事实。
- 新增测试：重复名称、schema、状态资格、visitor/audit 字段；回归：各能力现有单测；LangSmith：不启用工具选择。
- 完成标准：首批只读能力全登记且默认拒绝未登记工具；冲突停止：能力没有稳定输入输出；提交：`feat: add controlled tool registry`。

#### CA-03 — 术语/单事实/服务工具

- 目标：接入首批只读工具；允许修改：对应 runtime adapter 与测试；禁止修改：术语卡、服务事实和状态。
- 新增测试：资格、英文门控、时间口径、动态事实、无证据；回归：glossary/single fact/controlled knowledge；LangSmith：规划前后等价。
- 完成标准：事实集不变、内部泄漏 0、状态不变；冲突停止：来源或资格冲突；提交：`feat: expose reviewed fact tools`。

#### CA-04 — 对象/点位/工艺工具

- 目标：统一审核对象详情、精选 inventory 和多工艺位置；允许修改：只读 adapter/renderer；禁止修改：对象映射与知识正文。
- 新增测试：ID、白名单、同名消歧、证据等级、长度预算；回归：ornament/tour_qa/E5；LangSmith：四点位与自然多工艺。
- 完成标准：对象越界 0、无证据关闭、规划前后等价；冲突停止：审核映射异常；提交：`feat: add reviewed ornament tools`。

#### CA-05 — Shadow Planner

- 目标：仅记录 AgentDecision，不改变现有执行；允许修改：planner、prompt/schema、审计、开关；禁止修改：旧路由执行权。
- 新增测试：候选确定性、超时、模型不可用、循环上限；回归：全路由；LangSmith：比较 shadow 候选与实际路径。
- 完成标准：shadow 不改变消息/状态且工具选择达基线；冲突停止：模型输出不能安全验证；提交：`feat: add shadow agent planner`。

#### CA-06 — Policy Gate

- 目标：执行权限、资格和证据预检；允许修改：policy 模块/测试；禁止修改：冻结状态语义。
- 新增测试：四副作用等级、确认、prohibited、状态相位、伪 ID；回归：route/replan/tour event；LangSmith：诱导越权案例。
- 完成标准：所有未登记/越权计划失败关闭；冲突停止：权限无法闭合表达；提交：`feat: enforce agent policy gate`。

#### CA-07 — Executor/Validator

- 目标：执行已批准只读工具并验证结果；允许修改：executor/validator/审计；禁止修改：TourEvent 和正式路线。
- 新增测试：超时、同参重复、evidence 缺失、残缺输出；回归：只读工具和游客边界；LangSmith：工具失败/无证据。
- 完成标准：最大 3 调用、失败无项目事实扩写、审计完整；冲突停止：陈家祠事实必须依赖自由 LLM 补证；提交：`feat: execute controlled read tools`。

#### CA-08 — 多意图原子计划

- 目标：有序分解、验证和原子处理；允许修改：plan schema、gate、qa context adapter；禁止修改：直接状态写入。
- 新增测试：四个指定场景、失败回滚、澄清、跨 thread；回归：控制/知识/重排；LangSmith：混合请求矩阵。
- 完成标准：部分状态写入 0、不可组合请求不半执行；冲突停止：现有事件无法事务化；提交：`feat: add atomic multi-intent plans`。

#### CA-09 — 路线 proposal 工具

- 目标：调用现有规划器生成候选；允许修改：route adapter/proposal schema；禁止修改：正式路线自动应用。
- 新增测试：时间、兴趣、深度、预算、空间、候选不可变；回归：route planner/selection/profile；LangSmith：30/60/90 分钟。
- 完成标准：所有节点来自审核规划器、超限 0；冲突停止：候选不能重算验证；提交：`feat: expose route proposal tool`。

#### CA-10 — 重规划 proposal 工具

- 目标：以已确认当前位置和正式快照生成重排候选；允许修改：replan adapter/pending 测试；禁止修改：自动确认。
- 新增测试：未知地点、偏航、快照过期、取消、一次性确认；回归：replanning/tour interaction；LangSmith：月台/后西庭/未知小院。
- 完成标准：未知地点不建路线、proposal 不自动应用；冲突停止：pending 契约不一致；提交：`feat: expose replan proposal tool`。

#### CA-11 — TourEvent adapter

- 目标：将获批请求交给冻结事件层；允许修改：event request adapter/测试；禁止修改：TourState 直接写入及事件语义。
- 新增测试：到达/完成/跳过/下一站及全部负例；回归：tour intent/state/interaction/E2E；LangSmith：自然同义表达。
- 完成标准：所有变化可追溯到 `handle_tour_event()`；冲突停止：冻结事件不足以表达合法请求；提交：`feat: gate agent tour event requests`。

#### CA-12 — 经典/定制模式与恢复协议

- 目标：冻结 `tour_mode` 唯一归属及经典/定制最小收集、问答打断和恢复语义；允许修改：新契约/验证器、收集 adapter 和测试；禁止修改：VisitorProfile/TourState 既有字段语义或新建第二状态源。
- 新增测试：经典模式只需时间、定制模式最多三类明确偏好、默认中性、已确认字段不重复询问、规划收集和导航中的只读问答后恢复；LangSmith：两模式多轮对照。
- 完成标准：模式不由语气推断，恢复不改路线/进度且不丢字段；冲突停止：负责人未确认模式归属或现有交互状态无法表达恢复；提交：`feat: define tour mode contract`。

#### CA-13 — CardDispatcher

- 目标：按当前审核点位、StopProgram、GuidancePolicy、模式、明确兴趣、预算和资格表生成可审计增强候选；允许修改：调度器和局部测试；禁止修改：卡片正文/资格、对象选择、来源和 E5 事实数量。
- 新增测试：无合格卡、经典默认、定制偏好、研究归因、比较边界、摄影意图、安全禁令、预算不足和 thread 隔离；LangSmith：多点位到达矩阵。
- 完成标准：基础对象事实优先、未授权卡不输出、无候选时正常讲解；冲突停止：E5 或模式契约未通过、卡片关联无法确定；提交：`feat: dispatch eligible tour cards`。

#### CA-14 — Graph 灰度接入

- 目标：接入 planner/gate/executor/renderer 并保留旧回退；允许修改：`agent_graph.py`、配置和 E2E；禁止批量删除旧节点。
- 新增测试：shadow/active/off、循环、故障回退、checkpointer；回归：完整 unittest；LangSmith：新旧对照。
- 完成标准：每能力可独立开关、Studio/CLI 状态隔离；冲突停止：完整回归或硬门槛失败；提交：`feat: integrate controlled agent graph`。

#### CA-15 — 验收与旧边收敛

- 目标：只删除已等价验收的重复知识边；允许修改：已批准路由、评测、交接；禁止修改：控制优先级和未验收能力。
- 新增测试：删除后差分/回滚；回归：完整测试、负载、故障注入；LangSmith：全矩阵人工评分。
- 完成标准：自动和人工门槛均达标、回滚演练通过；冲突停止：任一硬门槛非 0；提交：`refactor: converge verified agent routes`。

## 18. 测试体系

### 18.1 单元测试

- AgentDecision schema、受控枚举、原话 span、参数类型。
- 工具注册完整性、资格、超时和失败策略。
- Policy Gate、副作用等级、确认条件和禁止能力。
- 模型自造 node/ornament/source ID 的拒绝。
- 多意图依赖、原子性和失败不部分执行。
- 游客输出边界与内部审计保留。
- 无证据、冲突、过期证据失败关闭。
- 经典/定制模式只接受明确选择，未填写偏好保持中性默认。
- 规划收集和导航被只读问答打断后，已确认字段、正式路线和 pending 点不变。
- CardDispatcher 的点位、模式、兴趣、预算、资格和摄影安全门控。

### 18.2 模块与状态测试

覆盖普通知识、术语、对象、点位、工艺位置、服务规则、研究、比较、拍照、路线候选、重规划候选、TourEvent、E5、B3、双模式和卡片调度。验证：

- 只读工具不改 TourState/VisitorProfile。
- proposal 不自动应用；失败工具不产生部分状态。
- `thread_id`、pending、qa_context、Coverage 不串线。
- NarrationCoverage 仍只在成功且有 evidence 后写入。
- 同一事实问题在规划前/导游中使用等价能力和证据；只读回答后导游可从原状态继续。
- 点位游客答案经过精选、分层和长度预算；内部完整 inventory 不直接输出。
- 动态服务事实的当前结论必须来自有效期内证据；过期时失败关闭并引导官方渠道。

### 18.3 对抗测试

- 自造 ID/source、跨点位对象、提示注入索要内部资料。
- 多意图诱导先执行状态后失败。
- 要求跳过确认直接改路线。
- 危险拍照、无证据故事扩写、过期动态事实。
- 重复工具调用、无限循环、超时结果和残缺输出。

### 18.4 LangSmith 人工测试

覆盖自然语言变体、多意图、当前点问答、规划前后等价、问答后继续导游、规划收集打断恢复、经典/定制模式、到点卡片候选、低置信度澄清、无证据关闭、状态不变、内部来源仅 Trace 可见，以及工具选择是否符合 Policy Gate。每次记录 tested_commit、thread_id/Trace（实际存在时）、输入、路径、状态前后和结果；自动测试不得替代人工结论。

## 19. 验收指标

| 指标 | 定义/门槛 |
|---|---|
| 意图路由正确率 | 与冻结集对照，阶段目标由 QA 基线批准 |
| 工具选择正确率 | 正确 capability/全部可执行案例 |
| 多意图澄清正确率 | 不可组合案例必须澄清 |
| 无证据安全关闭率 | 100% |
| TourState 非法写入 | **0** |
| VisitorProfile 非法写入 | **0** |
| 路线自动越权应用 | **0** |
| 对象—点位越界 | **0** |
| 内部字段泄漏 | **0** |
| 无证据文化事实生成 | **0** |
| 跨 thread 串线 | **0** |
| 路线预算超限 | **0** |
| 来源可追溯率 | 合格事实 100% 有内部证据 |
| Agent 平均工具循环 | 监控；不得用循环掩盖低质量决策 |
| p95 响应耗时 | 不超过负责人批准的阶段阈值 |
| LangSmith 人工评分 | grounding/state safety/route correctness 均达批准阈值 |
| 与旧 Workflow 差异 | 安全与事实零负回归；体验差异逐项批准 |
| 问答后导游恢复正确率 | 合格只读问答案例 100% 保留路线、进度和待办状态 |
| 模式来源合法率 | 100% 来自游客明确选择或已批准透明默认，不由模型猜测 |
| 非法卡片主动插入 | **0** |
| 过期动态事实作为当前结论 | **0** |

## 20. 灰度、回滚与兼容

- 使用配置开关按 capability 启用，例如 `controlled_agent.shadow`、`controlled_agent.term`，具体名称在 CA-00 冻结；不开设第二套状态。
- shadow 模式只记录候选，不改变现有路由；active 模式仅启用已验收工具。
- 新 Agent 失败回退到现有确定性安全路径，不得进入无约束 LLM。
- 每个能力可独立关闭；pending 状态必须能由旧路径继续消费或安全取消。
- 旧路由仅在自动等价测试与 LangSmith 验收完成后删除。
- 不允许同一能力同时维护两套路由事实；并行期只有一个执行权威，另一个仅 shadow。
- 禁止一次性批量迁移、批量删除或重写全部图。

## 21. 风险清单

| 风险 | 等级/触发 | 检测 | 防护 | 回滚/负责人建议 |
|---|---|---|---|---|
| Agent 抢占控制意图 | 高；控制语句进入 planner | 控制路由对抗集 | deterministic control 在前 | 关闭 planner；interaction_owner |
| 多意图部分执行 | 高；后续子意图失败 | 状态前后快照 | 原子组、先验证后执行 | 澄清/恢复快照；state_owner |
| 工具参数/ID 伪造 | 高；模型输出 ID | 审核解析审计 | 从原话重解析、白名单 | 拒绝工具；data_owner |
| 状态越权 | 严重；工具写字典 | 状态写入探针 | 唯一 transition adapter | 禁用工具；state_owner |
| 检索证据串线 | 高；跨 thread/对象 | evidence/thread 测试 | thread 与对象作用域 | 关闭相关能力；knowledge_owner |
| 当前点错误 | 高；错误 node context | 点位白名单测试 | 审核映射、现场限定 | 澄清；spatial_owner |
| 规划前后不一致 | 中高；不同入口 | 双模式差分集 | 统一 capability | 回退旧受控问答；QA owner |
| 循环调用 | 中高；重复工具 | 循环计数/同参检测 | 最大 3 次、禁止同参重复 | 安全关闭；orchestration_owner |
| 延迟/成本上升 | 中；多工具/模型 | p95/调用数 | 能力预算、缓存审核索引 | 关闭复杂组合；release_owner |
| 输出边界绕过 | 严重；新出口直发 | 泄漏扫描 | 统一 renderer + 出口分离 | 返回安全说明；security_owner |
| 动态事实过期 | 高；公告失效 | 有效期测试 | 时效 gate | 不给当前结论；knowledge_owner |
| 测试锁文案不锁结构 | 中；表面通过 | 测试审查 | 验证 ID/evidence/state | 补结构断言；QA owner |

## 22. 完成定义

本文档完成仅表示：

- 当前混合架构、事实源和冻结边界已被审计并形成目标设计。
- 后续迁移被拆成 8 个阶段、16 个小步任务和明确测试门槛。
- 生产 Agent 尚未升级，`implementation_status` 仍为 `not_started`。
- 未执行 LangSmith，`langsmith_status` 仍为 `not_run`。
- 本步不改变生产行为，不修改生产代码、测试、数据、台账或既有公共文档。
- 后续必须逐阶段实现、自动测试、差分评测和 LangSmith 人工验收。
- 未经负责人确认，不得执行 Phase 1。
