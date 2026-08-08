# `change.md` 实施交接：语义裁决与角色化讲解

## 1. 实施结论

本轮按 `change.md` 完成了 P1–P4 的渐进实现。整体权限边界保持不变：

```text
Agent：提出语义候选、组织审核事实的表达
Workflow：裁决节点、校验状态、提交 Coverage、控制回退
```

路线、TourState、VisitorProfile、结束状态和 Coverage 均未交给模型直接写入。

## 2. P1：语义候选契约与裁决

新增：

- `semantic_intent_contract.py`
- `intent_arbitration.py`
- `test_semantic_intent_contract.py`

实现内容：

- 最多保留 3 个按置信度排序的业务意图候选；
- 意图和参数均使用白名单；
- 证据片段和 target 必须来自游客原文；
- 候选不能返回 Graph 节点作为执行指令；
- 只读阈值为 `0.80`，状态修改阈值为 `0.90`；
- 多个状态修改意图冲突时进入澄清；
- 没有活跃路线时拒绝到达、完成、跳过、结束等事件；
- 确定性高优先级规则始终高于模型候选；
- 旧单候选 JSON 仍兼容，新模型输出可使用最多 3 个候选的 envelope。

新增 State 审计字段：

- `semantic_intent_envelope`
- `intent_arbitration`

这些字段不具有执行权限。

## 3. P2：风格库 V2 角色侧车

新增：

- `data/chen_clan_academy/narration_styles/style_roles_v2.yaml`

现有 `styles_v1.yaml` 继续作为确定性模板 fallback；V2 文件只保存角色表达规则。18 种风格均包含：

- 角色身份；
- 与游客关系；
- 情绪与讲述视角；
- 身份边界；
- 开场、事实顺序、互动频率、修辞、禁止项和收束策略；
- 人工审核示例。

`narration_style_policy.py` 新增 `StyleBrief`，模型只接收当前风格的最小角色卡，不接收完整 YAML。

已改写以下危险表达：

- 全场唯一；
- 岭南工艺天花板；
- 最有价值；
- 别问为什么；
- 不看等于白来。

`listen_only` 额外强制无问号、无任务、无拍照或动作要求。

## 4. P3：角色讲解 Shadow

新增：

- `narration_content_plan.py`
- `role_narration_generation.py`
- `narration_validation.py`

Graph 链路：

```text
stop_guidance
→ narration_content_plan
→ role_narration_generation
→ narration_validation
→ atomic_read_plan_shadow
```

内容计划只读取已经通过 E5 的公开事实段和审核 subject ID，不读取原始 RAG chunk，也不把 `source_ids` 传给模型。

第一版采用“原子事实不可改写”策略：审核事实 statement 必须逐字保留；模型只能调整事实顺序并添加受限的角色化开场、连接和收束。验证器检查：

- style ID 一致；
- used fact IDs 全部属于计划；
- 必选事实正文原样存在；
- 无新增年份、人物归因、典故、寓意、排名或认证；
- 无内部字段；
- 无危险和强迫表达；
- `listen_only` 无互动；
- 不超预算；
- 最终游客输出边界通过。

模型 `self_check` 只用于审计，不参与放行。

## 5. P4：Active、唯一提交和回退

Active 使用两阶段 Coverage 提交：

```text
stop_guidance：暂存 Coverage 候选，不提交
→ validation accepted：narration_commit 唯一提交
→ validation rejected：deterministic_narration_fallback 提交旧模板 Coverage
```

`narration_commit` 使用同一个 AI message ID 替换 legacy 消息，不追加第二条游客消息；同时保留审核过的观察提示、下一步和可选打卡后缀。

Coverage 新增合法写入来源：

- `narration_commit`
- `deterministic_narration_fallback`

其他未知写入来源仍然失败关闭。

## 6. Rollout 配置

默认关闭，不产生额外角色模型调用：

```env
CJC_READ_ONLY_ROLLOUT_MODE=off
```

LangSmith Shadow：

```env
CJC_READ_ONLY_ROLLOUT_MODE=shadow
CJC_READ_ONLY_ROLLOUT_CAPABILITIES=role_narration
```

受控 Active：

```env
CJC_READ_ONLY_ROLLOUT_MODE=read_only_active
CJC_READ_ONLY_ROLLOUT_CAPABILITIES=role_narration
```

建议先只在独立测试环境启用 Active。

## 7. LangSmith 重点字段

- `semantic_intent_envelope`
- `intent_arbitration`
- `narration_content_plan`
- `role_narration_candidate`
- `narration_validation`
- `active_role_narration_audit`
- `role_narration_evaluations`
- `active_role_narration_audit.coverage_commit`

重点验收：

- `state_writes == []`；
- Shadow 下 `active_takeover == false`；
- Active 接管仅发生在 `validation_status == accepted`；
- fallback 时 `legacy_message_preserved == true`；
- Coverage 每个 subject 只提交一次；
- TourState、VisitorProfile 和路线不变；
- 游客正文无内部字段。

## 8. 自动测试结果

本轮新增及相关回归：

- 语义/契约/风格/内容计划/角色验证/讲解 Shadow：73 项通过；
- Active commit/fallback/Coverage：15 项通过；
- 多候选语义回归：29 项通过；
- 全量：1027 项中 1022 项通过，5 项失败。

这 5 项失败已在未包含本轮修改的 Git `HEAD` 临时基线副本中完全复现，因此不是本轮回归：

1. `test_session_memory`：新欢迎/语言强制流程与旧画像入口断言不一致；
2. `test_agent_profile_route_integration`：经典模式 detail 默认契约与旧 `deep` 断言不一致；
3. `test_visit_summary_engine`：兴趣规范顺序与旧顺序断言不一致；
4. `test_visitor_fact_route_acceptance` 两项：欢迎/本地化加入后，旧的最后三节点 metric 断言过期。

这些基线问题没有在本轮擅自修改。

## 9. 环境修复

原 `.venv` 指向的 Python 3.12 已不存在。本轮从 Python 官网恢复了 Python `3.12.10` 到原路径：

```text
C:\Users\muziw\AppData\Local\Programs\Python\Python312\python.exe
```

现有 `.venv` 可继续使用。

## 10. LangSmith 复测修复与角色故障注入

针对角色候选持续出现 `invalid_candidate_schema`，角色讲解调用现改为：

- 使用独立的 `ROLE_NARRATION_MAX_TOKENS`，默认 `1800`，避免完整 JSON 被全局短输出预算截断；
- 请求 JSON object 输出；
- Prompt 内提供与当前 `style_id`、`fact_id` 一致的合法 Schema 示例；
- 首次输出仅在 Schema 不合法时允许一次受控修复，修复仍不可访问工具、RAG 或会话状态；
- 修复仍失败时保持 fail-closed，并走既有确定性讲解回退。

可选配置：

```env
ROLE_NARRATION_MODEL=deepseek-chat
ROLE_NARRATION_MAX_TOKENS=1800
```

角色专用故障注入仅用于独立测试环境，不要修改全局 `DEEPSEEK_API_KEY`：

```env
CJC_ROLE_NARRATION_TEST_FAILURE=timeout
# 或 invalid_json / invalid_schema
```

未设置或留空即正常调用角色模型。该开关只影响角色讲解生成，不影响语义识别、普通问答或其他模型节点。

低置信度完成表达（例如“这个地方好像差不多了吧”）现在确定性进入 `clarification`，不再进入自由 `llm_think/RAG`。确定性路线请求也会写入可审计的 `semantic_intent_envelope.candidates`，但不会因此新增模型调用或直接写 TourState。

本轮扩展回归 116 项全部通过。全量回归共 1031 项，其中 1026 项通过；其余 5 项与上一轮已确认的基线失败完全一致，不是本轮修改引入。

## 11. Phase 1 Schema 复核结果（2026-08-09）

本轮只处理 `invalid_candidate_schema`，没有开启角色 Shadow 接管、Active、路线规划角色化、开场角色化或引路角色化。

- 真实触发位置：`role_narration_generation.validate_candidate_shape()` 的顶层字段集合校验；Studio 展示的是失败后的内部审计 envelope，不是模型原始 JSON。
- 模型 wire object 保持六字段严格 Schema；`role_narration_candidate_from_dict()` 现在对 Graph 内部十字段 envelope 也严格校验，拒绝未知字段、非法状态/类型、负耗时和 rejected 状态游客正文。
- `agent_graph._invoke_role_narration_model()` 现在只接受字符串或明确的文本内容块；不再把内容块列表转换成伪 JSON 字符串。
- 已补充合法候选、缺字段、多余字段、错误类型、未知角色、未知版本、内部 ID/来源/状态/最终文案字段和 envelope 未知字段测试。
- 旧确定性导游正文仍是唯一游客输出；没有修改 TourState、VisitorProfile、正式路线、Proposal、RAG、知识卡、StopProgram 或 Coverage 提交边界。

当前状态必须如实记录：

```text
invalid_candidate_schema: fixed
automated_validation: partial_due_to_preexisting_failures
role_shadow: not started
active: disabled
```

角色定向测试已完成 `15/15 OK`；父提交 `28c6d6b` 与当前提交 `ca4b64c` 的完整回归结果完全一致，均为 `1031 passed, 4 failures, 1 error`。失败项集中在 `test_session_memory`、画像—路线集成、VisitSummary interest 顺序和两项旧路线路径断言，确认属于既有基线问题；未修改这些旧测试断言。`test_agent_graph.py` 不存在，不计入回归结果。P0 安全/游客输出矩阵已完成 `62/62 OK`，因此本阶段满足提交条件。
