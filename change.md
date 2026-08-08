# 陈家祠导游 Agent 语义路由与角色化讲解改造方案

## 1. 改造目标

本次改造要在保留现有 LangGraph 确定性导游流程的基础上，实现两项核心能力：

1. Agent 能够理解游客的自然表达，提出结构化意图候选，并由 Workflow 根据当前游览状态、安全规则和业务契约决定进入哪个节点。
2. Agent 能够读取游客选择的讲解风格，根据风格库中的角色身份、表达规则、游客画像、当前点位和已审核事实，生成稳定、自然且符合角色身份的讲解。

最终目标链路：

```text
游客输入
→ 确定性高优先级规则
→ 语义意图候选
→ Workflow 状态与权限校验
→ 正式业务节点
→ 审核事实与讲解内容计划
→ 角色化讲解生成
→ 事实/风格/安全/预算校验
→ 游客语言本地化
→ 输出
```

本次改造不把路线、点位推进、游客画像或 Coverage 的最终写权限交给 LLM。Agent 负责理解和表达，Workflow 负责授权和执行。

## 2. 当前基础与主要缺口

### 2.1 已有能力

- 使用 LangGraph `StateGraph` 管理导游流程和 Thread 状态。
- 已有欢迎、语言选择、模式选择、画像收集、路线生成、到站、点位讲解、问答、重规划、总结、称号和祝福节点。
- `route_initial_request()` 已实现确定性优先级和 LLM 最后兜底。
- `semantic_normalization` 已能通过受控模型把部分自然表达规范化为控制意图或知识问题。
- `styles_v1.yaml` 已包含 18 种讲解风格及模板、安全规则和回退配置。
- `stop_guidance` 已基于审核内容生成讲解，并具有 Coverage、预算和 Shadow 审计。
- 已有游客语言本地化链路。

### 2.2 当前缺口

- 语义识别主要输出单个候选，无法充分表达多意图、歧义和置信度差距。
- 路由规则较多，但缺少统一的“Agent 提议、Workflow 裁决”契约。
- 目前风格渲染以 YAML 模板填充为主，只改变局部语气，不是完整角色生成。
- 风格库缺少明确的角色身份、与游客的关系、整段讲解组织策略和人工审核示例。
- 缺少独立的角色讲解生成节点与正式验证节点。
- 缺少“生成失败后回退现有确定性模板”的统一机制。
- 部分角色模板含绝对评价或强迫性表达，可能越过事实和游客体验边界。

## 3. 总体架构原则

### 3.1 权限边界

Agent 可以：

- 理解自然语言并提出一个或多个意图候选；
- 判断话语指代的可能上下文；
- 根据游客画像选择讲解内容的表达顺序；
- 根据已选择角色改变语气、节奏、互动方式和修辞；
- 在审核事实范围内压缩、扩展或重新组织讲解；
- 提出路线调整或服务建议。

Agent 不可以：

- 直接修改正式路线；
- 自动标记游客到达、完成或跳过点位；
- 自动结束游览；
- 在没有游客明确表达时写入画像偏好；
- 直接写入 `TourState`、正式 Coverage 或结束状态；
- 编造人物、年代、典故、排名、象征意义或现场对象；
- 输出文件路径、URL、source ID、节点 ID、原始 chunk 或工具名称；
- 使用风格库之外的角色；
- 绕过人工审核材料生成事实。

### 3.2 推荐占比

- 节点选择：Workflow/规则约 70%，Agent 语义候选约 30%。
- 游客可见讲解：审核事实与内容计划约 40%，角色 Agent 表达约 60%。
- 正式状态写入：Workflow 至少 95%，Agent 只提出建议，不直接提交。

## 4. 第一阶段：建立统一语义候选契约

### 4.1 新增数据结构

建议新增 `semantic_intent_contract.py`，定义：

```python
class IntentCandidate(TypedDict):
    intent: str
    confidence: float
    target: str | None
    arguments: dict[str, object]
    source: str
    requires_confirmation: bool


class SemanticIntentEnvelope(TypedDict):
    schema_version: str
    candidates: list[IntentCandidate]
    ambiguity_reason: str | None
    raw_text_preserved: bool
    model_called: bool
```

`intent` 只能使用白名单，例如：

- `select_language`
- `select_journey_mode`
- `provide_profile_preference`
- `request_route`
- `arrive_at_stop`
- `confirm_stop_complete`
- `skip_stop`
- `request_next_stop`
- `request_stop_detail`
- `finish_tour`
- `request_replan`
- `confirm_replan`
- `cancel_replan`
- `ask_venue_question`
- `ask_follow_up_detail`
- `update_profile`
- `request_summary`
- `request_title_blessing`
- `unknown`

### 4.2 修改语义识别输出

修改 `semantic_normalization.py`：

1. 保留现有确定性候选和安全校验。
2. 模型输出从单候选扩展为最多 3 个候选。
3. 每个候选必须包含置信度、目标、参数和是否需要确认。
4. 严禁模型返回节点名称作为最终执行指令；模型只能返回业务意图。
5. 不允许模型回答游客问题，只允许分类。
6. JSON 解析或字段校验失败时返回空候选，不进入危险动作。
7. 对到达、完成、跳过、结束、确认重规划等状态写入意图执行更严格阈值。

建议阈值：

```text
普通只读意图：
  confidence >= 0.80 可提交 Workflow 裁决

状态修改意图：
  confidence >= 0.90 且参数完整，才可提交 Workflow 裁决

0.60 <= confidence < 执行阈值：
  结合当前状态和确定性解析器再次仲裁

confidence < 0.60：
  clarification
```

### 4.3 新增 Workflow 裁决器

建议新增 `intent_arbitration.py`，职责是：

- 接收确定性解析结果、语义候选和当前 State；
- 按业务优先级选择一个正式能力；
- 检查该意图在当前状态是否允许；
- 检查参数是否完整、点位是否审核、待确认动作是否仍然有效；
- 识别多意图冲突；
- 输出固定 `route_target`，不执行状态写入。

建议结果结构：

```python
class ArbitrationResult(TypedDict):
    status: Literal["accepted", "clarification", "rejected"]
    route_target: str
    intent: str | None
    confidence: float | None
    arguments: dict[str, object]
    reason_code: str
    state_write_allowed: bool
```

### 4.4 保留高优先级确定性规则

以下能力继续优先于语义模型：

1. 安全问题和不安全拍摄请求；
2. 未完成的语言强制选择；
3. 已结束会话的幂等处理；
4. 活跃路线的明确结束；
5. 待确认重规划；
6. 明确到达、完成、跳过和下一站；
7. 明确模式选择和有效时长；
8. 当前画像收集字段的回答；
9. 审核知识专用解析器；
10. 最后才允许通用 LLM/RAG。

### 4.5 多意图处理规则

- 两个只读意图可以按顺序回答，但本轮最多产生一个正式状态写入。
- 一个只读问题加一个明确画像答案，可以先记录合法画像字段，再回答问题，或先回答问题后恢复缺失问题；行为必须固定并测试。
- 两个互相冲突的状态写入意图必须澄清。
- “完成本点并去下一站”可作为唯一审核过的组合操作。
- “确认新路线并去下一站”继续使用现有原子组合节点。
- 未审核的组合意图不能由 Agent 自由拆分执行。

## 5. 第二阶段：把风格库升级为角色库

### 5.1 扩展 YAML Schema

在每个风格条目中增加：

```yaml
persona:
  identity: "角色身份说明"
  relationship_to_visitor: "与游客的交流关系"
  emotional_tone: ["温和", "从容"]
  speaking_perspective: "第一人称导游视角"
  identity_boundaries:
    - "不得冒充历史人物"
    - "不得声称具有官方认证"

generation_policy:
  opening_strategy: "如何进入主题"
  fact_order: ["空间位置", "工艺事实", "观察细节"]
  interaction_frequency: "low"
  rhetorical_devices: ["适量四字表达", "温和设问"]
  avoid: ["虚构典故", "绝对排名", "强迫游客互动"]
  closing_strategy: "如何自然结束"

few_shot_examples:
  - input_facts:
      - "前院中部屋脊可见灰塑"
    preferred_output: "人工审核示例"
```

### 5.2 Schema 兼容策略

- 风格库 schema 建议升级为 `narration_style_library_v2`。
- 单条风格 schema 建议升级为 `narration_style_v2`。
- V1 条目在过渡期可以由加载器补齐中性角色默认值。
- 所有 18 种风格完成角色字段人工审核后再切换 V2 为 Active。
- 未完成审核的风格必须回退 `neutral`，不能静默进入自由生成。

### 5.3 角色安全检查

逐条检查现有角色模板，删除或改写：

- “全场唯一”；
- “岭南工艺天花板”；
- “最有价值”；
- “不看等于白来”；
- “别问为什么”；
- 其他没有证据支持的绝对评价、贬低或强迫性表达。

角色感应通过节奏、称呼、句式和叙事方式实现，不能依赖虚假事实或冒犯性表达。

## 6. 第三阶段：增加角色讲解生成链路

### 6.1 保留现有 `stop_guidance`

`stop_guidance` 继续负责：

- 验证当前点位；
- 读取审核讲解卡；
- 读取游客画像和选择风格；
- 读取 Coverage，排除不应重复的内容；
- 计算讲解时间和内容预算；
- 形成候选事实集合；
- 不直接让 LLM 修改任何正式状态。

### 6.2 新增 `narration_content_plan` 节点

建议新增文件 `narration_content_plan.py`，输出：

```json
{
  "schema_version": "narration_content_plan_v1",
  "stop_id": "front_courtyard_center",
  "style_id": "ancient_scholar",
  "language": "zh",
  "budget_seconds": 180,
  "facts": [
    {
      "fact_id": "fact_gray_sculpture_01",
      "statement": "前院中部屋脊可见灰塑装饰"
    }
  ],
  "must_include": ["空间位置", "观察细节"],
  "already_covered": ["灰塑基本定义"],
  "must_not_claim": ["具体作者", "未经审核年代"],
  "interaction_allowed": true
}
```

内容计划必须是确定性的，只能引用审核事实 ID，不允许包含 LLM 推测事实。

### 6.3 新增 `role_narration_generation` 节点

模型输入仅包含：

- 经过裁剪的角色卡；
- 讲解内容计划；
- 审核事实正文；
- 游客明确画像；
- 已讲内容摘要；
- 目标语言或先生成中文的要求；
- 字数/时间预算；
- 禁止项。

不得传入：

- 完整 AgentState；
- 文件路径；
- URL；
- source IDs；
- 原始 chunk；
- 节点名称；
- 内部工具调用信息；
- 未经游客确认的推测画像。

建议模型输出结构：

```json
{
  "schema_version": "role_narration_candidate_v1",
  "style_id": "ancient_scholar",
  "public_text": "……",
  "used_fact_ids": ["fact_gray_sculpture_01"],
  "omitted_fact_ids": [],
  "self_check": {
    "added_new_facts": false,
    "role_consistent": true,
    "within_budget": true
  }
}
```

模型的 `self_check` 只能作为审计信息，不能代替程序验证。

### 6.4 新增 `narration_validation` 节点

至少验证：

1. `style_id` 与游客已选择风格一致；
2. `used_fact_ids` 全部来自内容计划；
3. 输出未包含未审核的人名、年代、来源或对象；
4. 没有内部字段泄漏；
5. 没有违反角色 `prohibited_patterns`；
6. 没有强迫游客回答、触摸文物或执行危险动作；
7. 没有绝对排名和官方认证暗示；
8. 字数和估算讲解时长不超预算；
9. 与 Coverage 的重复程度在允许范围内；
10. 角色风格特征达到最低要求，但不能为了风格牺牲事实准确性。

验证结果：

```json
{
  "validation_status": "accepted",
  "reason_codes": [],
  "state_writes": [],
  "same_fact_boundary": true,
  "role_consistent": true,
  "within_budget": true
}
```

### 6.5 回退策略

出现以下任一情况时回退现有确定性模板：

- 模型超时或 API 失败；
- JSON 无法解析；
- 风格不存在或未审核；
- 新增了审核事实之外的内容；
- 超过内容预算；
- 含内部字段或危险表达；
- 角色一致性不足；
- 验证器自身异常。

回退后：

- 游客仍能获得正常讲解；
- `style_fallback_used = true`；
- 写入明确 `style_warning_codes`；
- 不重复推进 TourState；
- Coverage 只按最终公开讲解中通过验证的事实提交一次。

## 7. 第四阶段：调整 Graph 节点和边

目标点位讲解链路：

```text
tour_event
→ tour_opening（仅首次需要）
→ stop_guidance
→ narration_content_plan
→ role_narration_generation
→ narration_validation
├─ accepted → narration_commit
└─ rejected → deterministic_narration_fallback
→ atomic_read_plan_shadow
→ visitor_localization
```

建议新增节点：

- `narration_content_plan`
- `role_narration_generation`
- `narration_validation`
- `narration_commit`
- `deterministic_narration_fallback`

`narration_commit` 是唯一允许提交最终讲解 Coverage 的节点。生成节点和验证节点的 `state_writes` 必须为空。

重复讲解和“换一种风格再讲”应复用同一链路，但必须满足：

- 不推进 `current_stop_id`；
- 不重复完成点位；
- Coverage 按事实 ID 幂等；
- 只更新最新讲解审计；
- 风格修改只有游客明确提出时才写入画像。

## 8. 第五阶段：Prompt 设计

### 8.1 语义模型 Prompt

Prompt 只做分类：

- 明确禁止回答游客；
- 明确列出意图白名单；
- 明确当前只读状态摘要；
- 要求保留否定、疑问、条件和多意图；
- 不允许把模糊表达升级为状态写入；
- 只能输出 JSON。

### 8.2 角色讲解 Prompt

系统 Prompt 建议包括：

1. 角色身份和身份边界；
2. 允许使用的审核事实；
3. 内容计划和时间预算；
4. 游客明确偏好；
5. 已覆盖内容；
6. 允许修辞；
7. 禁止模式；
8. 输出 JSON Schema；
9. 明确“不知道的内容不得补充”；
10. 明确“角色化只能改变表达，不能改变事实”。

不要直接把整份 YAML 拼进 Prompt。加载器应只选择当前角色并生成最小角色卡。

## 9. 第六阶段：状态和审计字段

建议在 `AgentState` 增加：

```python
semantic_intent_envelope: dict[str, Any] | None
intent_arbitration: dict[str, Any] | None
narration_content_plan: dict[str, Any] | None
role_narration_candidate: dict[str, Any] | None
narration_validation: dict[str, Any] | None
active_role_narration_audit: dict[str, Any] | None
role_narration_evaluations: list[dict[str, Any]]
```

审计至少记录：

- `capability`
- `mode`
- `model_called`
- `style_id`
- `style_schema_version`
- `candidate_fact_ids`
- `used_fact_ids`
- `omitted_fact_ids`
- `validation_status`
- `reason_codes`
- `fallback_used`
- `state_writes`
- `public_message_safe`
- `within_budget`
- `latency_ms`

不得在游客正文中输出这些字段。

## 10. 第七阶段：测试计划

### 10.1 语义路由单元测试

覆盖：

- 自然表达、简写、错别字、中英文表达；
- 多意图和否定；
- 到达、完成、跳过、结束、重规划；
- 普通知识问题与路线控制的冲突；
- 画像回答与知识问题混合；
- 低置信度进入澄清；
- 模型输出非法 JSON 时安全关闭；
- 状态修改意图不能只凭低置信度执行；
- 确定性安全规则始终高于模型候选。

示例：

```text
“这里看完了，带我去下一个”
→ confirm_stop_complete_and_next 或受控拆分

“这里看完了吗？”
→ 问答/澄清，不得完成点位

“这个不太感兴趣”
→ 记录反馈或询问，不得自动跳过

“只剩20分钟，帮我挑重点”
→ prepare_duration_replan
```

### 10.2 风格库测试

每个角色必须验证：

- Schema 完整；
- `style_id` 唯一；
- fallback 存在；
- 角色身份边界存在；
- 禁止项完整；
- few-shot 示例不包含未审核事实；
- 别名能解析到唯一风格；
- 多风格冲突进入澄清；
- 风格词不会污染 interests；
- 未知风格透明回退。

### 10.3 角色讲解测试

至少对 18 种风格分别验证：

- 同一事实的角色差异明显；
- 不新增审核事实；
- 不改变点位和路线；
- 不超预算；
- 不泄漏内部字段；
- 重复生成仍保持角色；
- API 失败可回退；
- Coverage 幂等；
- 游客更换风格后下一次讲解生效；
- 更换风格不重讲已完成内容，除非游客明确要求。

### 10.4 集成测试

关键完整流程：

```text
欢迎
→ 选择语言
→ 定制模式
→ 兴趣
→ 角色风格
→ 建立路线
→ 到达首站
→ 总体介绍
→ 角色化点位讲解
→ 普通问答
→ 继续原流程
→ 重规划
→ 提前或正常结束
→ 总结和称号
```

### 10.5 LangSmith 人工验收字段

每个案例记录：

- Thread ID；
- Trace URL；
- tested commit；
- 输入消息；
- 节点路径；
- `semantic_intent_envelope`；
- `intent_arbitration`；
- `visitor_profile.explanation_style`；
- `narration_content_plan`；
- `active_role_narration_audit`；
- `role_narration_evaluations`；
- Coverage 前后差异；
- TourState 前后差异；
- 游客可见正文；
- 是否泄漏内部字段；
- 是否出现未审核事实；
- 是否符合角色；
- 是否触发 fallback。

## 11. 第八阶段：渐进上线

### 阶段 A：Shadow

- 角色 Agent 生成候选，但游客继续看到现有模板讲解。
- 记录 `same_fact_boundary`、风格一致性、预算和安全结果。
- 不允许任何状态写入。

退出标准：

- 事实边界通过率达到既定门槛；
- 无内部字段泄漏；
- 18 种角色均完成人工抽检；
- API 失败不影响现有导游流程。

### 阶段 B：小流量 Active

- 先启用 `neutral`、`child`、`professional`、`ancient_scholar` 等少量审核充分的角色。
- 通过环境变量或 rollout 配置控制比例。
- 验证失败自动使用模板回退。

### 阶段 C：全部审核角色 Active

- 所有角色完成内容、安全和多语言测试后逐步启用。
- 继续保留确定性模板作为永久 fallback。
- 监控各角色 fallback 率、游客追问率、重复请求率和提前退出率。

## 12. 实施顺序与交付物

### P1：语义候选契约

交付：

- `semantic_intent_contract.py`
- `intent_arbitration.py`
- 更新 `semantic_normalization.py`
- 更新 `route_initial_request()`
- 单元测试和 LangSmith 案例

### P2：角色库 V2

交付：

- `styles_v2.yaml` 或完成原文件版本升级
- 角色 Schema 加载器
- 18 种角色人工审核内容
- 风格别名和画像映射
- 风格库验证测试

### P3：角色讲解 Shadow

交付：

- `narration_content_plan.py`
- `role_narration_generation.py`
- `narration_validation.py`
- Graph 新节点和审计字段
- Shadow LangSmith 验收报告

### P4：Active 与回退

交付：

- `narration_commit` 与确定性 fallback
- rollout 配置
- Coverage 幂等测试
- 角色讲解正式游客输出
- 运行监控与回滚说明

## 13. 完成标准

以下条件全部满足后，才能认为改造完成：

1. 游客自然表达能够稳定进入正确业务能力，明显状态操作不进入自由 LLM/RAG。
2. 多意图、否定和疑问不会被错误执行为状态修改。
3. 游客选择的 18 种风格能够在实际点位讲解中生效。
4. 角色在整段讲解中保持一致，而非只替换一两句模板。
5. 角色化讲解不增加审核事实之外的内容。
6. 生成失败时游客仍能收到确定性模板讲解。
7. 角色生成、验证和 fallback 不推进路线、不污染画像。
8. Coverage 只对最终通过验证的事实幂等提交一次。
9. 多语言翻译不改变事实、角色意图和内部状态。
10. 游客正文不泄漏内部字段。
11. 正常结束、提前结束、重复结束和重复讲解均保持幂等。
12. 全量自动测试和规定的 LangSmith 人工验收通过。

## 14. 核心决策总结

本次改造不把现有 Workflow 替换成自由 Agent，而是在两个最有价值的位置增加 Agent 能力：

```text
理解阶段：Agent 提出意图，Workflow 决定能否执行。
讲解阶段：Workflow 提供审核事实，Agent 按角色组织表达。
```

路线、状态、事实和安全仍由 Workflow 控制；自然语言理解、个性化表达和角色体验交给 Agent。这样既能提高“像真人导游”的体验，又不会牺牲现有系统已经建立的可审计性、幂等性和安全边界。
