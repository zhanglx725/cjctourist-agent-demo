# 陈家祠金牌导游 Agent：项目学习与答辩说明

> 用途：学习项目代码、答辩和新人交接。进度只看 `PROJECT_PROGRESS_REPORT.md`，需求只看 `PROJECT_REQUIREMENTS.md`。
>
> 状态标记：**已实现并验证** = 代码与相关测试/人工验收均已通过；**已实现，待本机验证** = 已完成代码但尚待本轮本地测试；**仅保留接口** = 协议/字段已定义但未接入；**未来规划** = 尚未实现。

## 1. 项目定位与能力边界

本项目是陈家祠“金牌导游 Agent”原型。它用本地、可追溯的知识库回答馆内事实；用人工审核的空间节点和边规划路线；用确定性 TourState 记录真实游览进度。

它不是让大模型自由编造景点、路径或游览记录的系统。路线、空间和状态由确定性代码控制；LLM 只负责基于检索证据组织自然语言。

| 能力 | 当前状态 |
| --- | --- |
| 中文事实 RAG、混合检索和离线评测 | **已实现并验证** |
| 空间图、装饰—点位映射、静态/动态路线 | **已实现并经人工审核/测试** |
| TourState：下一站、跳过、有限重规划、结束 | **A 阶段已实现并验证** |
| A1-0 交互事件契约 | **已冻结** |
| A1-1 统一交互适配层 | **已实现并验证** |
| A1-2 文本“确认完成”与导游控制语句识别 | **已实现并验证（核心 38 项；完整回归 90 项）** |
| A1-3 按钮导游与连续导游回复 | **已实现并验证（完整回归 101 项）** |
| 游览中 RAG 问答后恢复导游 | **未来 A2** |
| 论文摘要卡、比较卡、术语卡、打卡点卡 | **建设中，尚未接入** |

## 2. 总体架构

```text
知识 Markdown ─→ 摄取/索引 ─→ 混合 RAG ───────────┐
                                                     ├─ Agent 自然语言回答
用户消息 ─→ LangGraph 路由 ─────────────────────────┤
                                                     ├─ 确定性路线规划
审核节点/边/映射 ─→ 空间图与路线数据 ───────────────┤
                                                     └─ TourState / 交互事件
```

分层职责：

1. **事实层**：回答“陈家祠事实是什么”；
2. **空间层**：回答“哪里能走、步行多久”；
3. **规划层**：回答“去哪里、停多久”；
4. **交互层**：回答“游客真正完成了什么、下一步是什么”。

这种分层避免了把“知识问答”“路线虚构”“状态统计”交给同一个语言模型。

## 3. RAG：本地事实问答如何实现

### 用户问题

游客会问“灰塑是什么”“百鸟朝凤在哪里”“陈家祠何时建成”。系统必须给出可追溯证据，而不是模型记忆中的不确定常识。

### 执行流程

```text
knowledge/*.md
→ rag_ingestion.py：按 H2 标题语义分块，保留 source_ids/日期/类别
→ build_index.py：Chroma 持久化索引
→ rag_retrieval.py：BM25 + 稠密向量检索
→ RRF 融合 → 条件 CrossEncoder 精排
→ RetrievedEvidence → Agent 基于证据回答
```

| 文件 | 实际作用 |
| --- | --- |
| `rag_ingestion.py` | Markdown 变为带来源元数据的 `KnowledgeChunk`。 |
| `rag_retrieval.py` | Chroma、BM25、BGE 向量、RRF、标题快路与条件精排。 |
| `build_index.py` | 知识文件更新后重建本地索引。 |
| `rag_evaluation.py` | 用“目标文档 + 标题”检查 Top-1/Top-3。 |
| `rag_benchmark.py` | 区分模型首次加载与热启动查询耗时。 |

### 为什么采用 BM25 + 稠密检索 + RRF

- BM25 擅长“百鸟朝凤”“梁山聚义”等精确专名；
- 稠密检索擅长“建筑布局有什么特点”等同义表达；
- RRF 不直接混合不同分数尺度，只融合排名，适合稳健默认方案；
- 条件精排只处理歧义问题，降低延迟；
- 专名标题快路让精确条目几乎无需完整检索。

已记录的 8 条代表性评测样本曾达到 Top-1 accuracy 100%、Top-3 recall 100%。答辩中应说“当前固定评测集通过”，不能说“所有问题 100% 正确”。

## 4. Agent 路由与性能边界

```text
用户消息
├─ 明确馆内事实词 → direct_rag → 基于 evidence 的 LLM 回答
├─ 路线/时长请求 → direct_route → 确定性路线
├─ 游览事件 → TourState / 交互适配层
└─ 其他问题 → llm_think → 可选 rag_tool → llm_think
```

`agent_graph.py` 使用 LangGraph。图中多个节点从 `START` 分出，表示“每条新消息按意图选择处理器”；并不表示会话状态丢失。状态由相同 `thread_id` 保存。

真实优化：`should_direct_rag()` 跳过一次无必要的工具选择 LLM；`should_direct_route()` 不让 LLM 编路线；`webapp.py` 预热模型；`agent_profile.py` 拆解节点耗时；LangSmith/Studio 测浏览器端到端体验，而不是替代控制台定位。

## 5. 空间网络与路线规划

### 用户问题

“只有半小时、喜欢灰塑怎么逛”需要真实可走的路线和时间预算，而不是语言模型列点。

```text
官网地图 + 人工审核
→ marker_inventory_v0.csv（稳定 node_id）
→ edges_v0.csv（双向边、秒数、依据）
→ ornament_spatial_mapping_v1.csv（装饰—点位）
→ route_stop_catalog_v1.csv（文物密度与讲解焦点）
→ NetworkX 最短路径 + 路线时间预算
```

| 文件 | 实际作用 |
| --- | --- |
| `spatial_graph.py` | NetworkX 审核无向图、最短路与可达性。 |
| `marker_inventory_v0.csv` | 节点主键、中文名、坐标、审核备注。 |
| `edges_v0.csv` | 可通行关系、步行秒数、时间依据。 |
| `route_planner.py` | 30/60/90 锚点路线、时间拆分、从当前位置裁剪。 |
| `dynamic_route_planner.py` | 45/75 等时长的候选筛选、路径感知选点与局部优化。 |

精确 30/60/90 分钟优先使用人工锚点路线；其他时长使用动态组合。动态评分为：

```text
文物密度 + 工艺多样性 + 兴趣匹配 + 路线角色
− 主题重复 − 到候选点的绕路成本
```

路线时间包含步行、讲解、观察、互动和缓冲。完整路径预留回前院出口区 `stop_front_courtyard_center` 的时间，但它不是重复讲解点。所有步行时间仍是地图估算，待现场复核。

## 6. TourState 与 A1-1 统一交互适配层

### 6.1 A 阶段基础

`tour_state.py` 保存：

```text
selected_route_id / route_stop_ids / current_stop_id
visited_stop_ids / skipped_stop_ids / remaining_stop_ids
available_minutes / remaining_minutes / interests / detail_level / route_status
```

`tour_navigation.py` 用审核图给出下一站、路径、边、步行时间和 `guide_focus`；`replanning.py` 只裁剪未完成路线，不能重新加入已访问或跳过点。

### 6.2 A1-1 解决的用户问题

旧逻辑把“我到月台了”视为“月台已经讲完”。真实游客可能刚到、听讲、拍照、提问或选择跳过。因此 `visited_stop_ids` 会被错误提前写入，后续成就、寄语和路线统计都会失真。

### 修改前后流程

```text
旧：我到月台 → arrive_at_stop → visited 加月台 → remaining 删除月台

新：我到月台 → handle_tour_event(arrive_at_stop)
                 → current_stop_id=月台，phase=explaining
                 → visited 不变、remaining 不变
    确认讲完 → handle_tour_event(confirm_stop_complete)
             → 月台移入 visited，刷新 pending_stop_id
```

### 本次核心代码

| 文件 / 函数 / 字段 | 责任 |
| --- | --- |
| `tour_interaction.py: handle_tour_event()` | A1 游览事件的唯一公开适配入口。 |
| `initialize_interaction()` | 创建独立的 `pending_stop_id`、`tour_mode`、`stop_phase`。 |
| `tour_state.py: _record_arrival()` | 私有底层函数，只记录位置和到达类型。 |
| `tour_state.py: _complete_current_stop()` | 私有底层函数，确认后才移动 remaining → visited。 |
| `_arrive()` | 区分计划内到达与 `self_arrival`。 |
| `_confirm_complete()` | 完成确认、幂等保护、刷新下一 pending。 |
| `_replan_time()` | 当前点未确认时保留一次，防止丢失或重复候选。 |
| `agent_graph.py` | 到达、下一站、跳过、改时间、结束节点改走适配层。 |

### 方案取舍

采用“**TourState 路线事实 + 独立交互状态 + 单一确定性适配层**”：路线事实可供后续成就/寄语统计，交互模式可以变化而不污染事实字段，文本/按钮/连续导游最终调用同一事件协议。

未采用：

| 备选 | 放弃原因 |
| --- | --- |
| 保留到达即完成，同时另写连续模式 | 两套语义会造成双写、统计错误和不可复现状态。 |
| LLM 直接写 TourState JSON | 可能写未知 node_id、漏字段、把提问误记为完成。 |
| 只允许到达 `pending_stop_id` | 与冻结契约冲突，不能记录游客自主到达合法空间。 |

### 如何禁止 LLM 篡改状态

1. `tour_interaction.py` 不导入 LLM、RAG、LangGraph 或 UI；
2. Agent 已有事件节点仅把参数传给 `handle_tour_event()`；
3. 适配层校验事件白名单、node_id、phase、路线状态；
4. 返回 `ok`、`code`、快照和 `idempotent`，失败不静默修改；
5. A1-2 即便用 LLM，也只能生成“事件建议”，仍需适配层验证。

### 关键测试与防错意义

| 测试 | 防止的错误 |
| --- | --- |
| `test_planned_arrival_does_not_mark_visit_until_confirmation` | 到达时误写 visited 或删除 remaining。 |
| `test_confirm_completion_is_the_only_transition_to_visited` | 非确认操作污染真实完成记录。 |
| `test_self_arrival_preserves_formal_route_order_and_counts` | 自主到达打乱路线或被误计为已完成。 |
| `test_next_stop_cannot_bypass_current_confirmation` | 正在讲解时直接推进下一站。 |
| `test_short_time_preserves_current_unconfirmed_stop_once` | 重规划丢失当前讲解点或重复加入候选。 |
| `test_repeated_arrival_and_completion_are_idempotent` | 网络重发/按钮连点导致重复计数。 |

### 本次规划—实现冲突

冲突一：旧 `arrive_at_stop()` 是“到达即已访问”，违背冻结契约。  
冲突二：一度将“当前路线允许到达”理解为只能到达 pending，但冻结契约要求保留 `self_arrival`。

最终语义：

```text
node_id == pending_stop_id → planned arrival → explaining
合法 node_id 且不等于 pending → self_arrival → 记录位置，路线顺序不变
confirm_stop_complete → 唯一写入 visited 的事件
```

这符合真实导游：游客可自由走到合法空间，但听完哪一站必须显式确认。体现了单一事实来源、显式状态机、幂等性、契约优先和风险隔离。

### 对其他模块的影响与未实现能力

- **路线**：不改空间边、模板、动态算法；当前未确认点重规划时保留一次。  
- **RAG**：A1-1 不调用 RAG，尚未自动讲解文物。  
- **TourState**：已访问语义更可靠，后续成就/寄语可以复用。  
- **卡片**：论文/比较/术语/打卡卡没有改动，也尚未参与选点。  
- **待实现**：游览中 RAG 问答恢复导游（A2）、持久化、实时定位、人流避让。

> A1-1 已使用项目 `.venv\Scripts\python.exe` 完成本地回归：62 项 TourState、导航、重规划、Agent、路线与动态路线测试全部通过。答辩可表述为“已实现并完成当前回归验证”；但按钮 UI、A2 RAG 恢复导游等未来能力仍不可表述为已实现。

## 7. 一分钟答辩讲稿（A1-1）

> 我们发现仅有路线规划还不够，因为系统必须知道游客实际完成了哪些讲解。旧版中，游客说“我到月台了”，系统会立刻把月台记为已参观，但游客可能刚到、正在听、想拍照，甚至会跳过。于是我们把“到达”和“确认完成”拆成两个确定性事件。现在到达只更新当前位置和讲解阶段，只有明确确认后才写入 `visited_stop_ids`。我们还保留了自主到达：游客走到路线外的合法空间时，系统能记录真实位置，但不会打乱正式路线或伪造参观记录。实现上，新增 `tour_interaction.py` 作为唯一状态修改入口，LLM 无权直接写状态。这样能让路线、RAG、讲解和游览记录分层管理，为后续中途问答、成就和个性化寄语打下可靠基础。

## 8. 面试追问与参考回答

1. **为什么不用大模型直接规划路线？**  
   路线依赖审核边、步行时间和节点主键；LLM 擅长表达，不适合作为空间事实数据库。我们用确定性规划保证可达和可解释。

2. **为什么 BM25 和向量检索都保留？**  
   专名适合 BM25，口语化同义表达适合稠密检索，RRF 融合降低单一召回器失效风险。

3. **RRF 比直接加权好在哪里？**  
   BM25 和向量相似度尺度不同，RRF 融合排名而非原始分数，较少依赖频繁调参。

4. **如何防止路线幻觉？**  
   路线只读取审核 CSV，在 NetworkX 图上求最短路；测试检查边双向性与入口可达性。

5. **为什么 visited 必须确认后才更新？**  
   到达不等于完成。确认语义能使游览统计、成就和结束寄语基于真实行为。

6. **游客不想输入点位名称怎么办？**  
   底层协议已支持稳定事件和 node_id；A1-3 已完成 UI 中立的按钮/连续展示协议，真实前端页面仍未开发。

7. **中途问“灰塑是什么”会不会打断路线？**  
   当前可作为普通 RAG 问答；“回答后自动恢复当前导游上下文”是未来 A2，尚未实现。

8. **论文卡为何不直接塞入事实库？**  
   馆方事实与学术观点证据等级不同，应以独立 `card_id` 管理，避免把研究观点误说成馆方结论。

## 9. 现场演示：输入—状态—输出

```text
输入：建立 30 分钟路线
状态：pending=前院中部；phase=navigating；visited=[]

输入：arrive_at_stop(前院中部)
输出：code=arrived
状态：current=前院中部；phase=explaining；visited=[]；remaining=[前院中部, 月台, 前东庭]

输入：confirm_stop_complete()
输出：code=stop_completed
状态：visited=[前院中部]；remaining=[月台, 前东庭]；pending=月台；phase=navigating

输入：arrive_at_stop(首进正厅)  # 合法但非 pending
输出：code=self_arrival
状态：current=首进正厅；last_arrival_kind=self_arrival；visited 不增加；remaining 顺序不变
```

## 11. A1-2：文本导游意图识别与安全路由（已实现并验证）

### 11.1 本任务解决的用户问题与执行流程

游客会说“我到月台了”“下一站去哪”“我只剩 20 分钟”，而不是调用函数。A1-2 在这些文本到达状态层之前，先把它们压缩为可测试的结构化决策。

```text
游客文本
  → classify_tour_intent()
  → TourIntentDecision(route_kind, event_type, arguments, confidence, reason_code)
  ├─ tour_event → handle_tour_event() → 新 TourState / 交互状态
  ├─ route_request → direct_route
  ├─ rag_question → direct_rag → 基于证据回答
  ├─ clarification → 只澄清，状态不变
  └─ other → llm_think
```

### 11.2 核心文件、字段与方案取舍

| 文件/对象 | 真实职责 |
| --- | --- |
| `tour_intent.py: TourIntentDecision` | 承载路由类型、事件名、参数、置信度、原因码与澄清标记。 |
| `resolve_reviewed_node()` | 仅读取审核节点表；同名、多点、未知名称均不猜测。 |
| `validate_event_suggestion()` | 校验事件白名单、分钟参数和稳定 ID；为未来可选的 schema 化 LLM 同义表达保留接口。 |
| `route_initial_request()` | 固定事件 → 路线 → RAG → LLM → 澄清的路由优先级。 |
| `tour_event_node()` | 只调用 `handle_tour_event()` 并使用其返回快照；没有直接状态写入。 |
| `clarification_node()` | 只输出澄清回复。 |

我们没有采用“让 LLM 直接写 TourState JSON”或“按相近名称猜节点”。`visited_stop_ids` 将服务于后续成就与寄语，错误事实记录比多问一句更危险。未来模型即使识别同义句，也只能建议固定 schema，仍须经过 `validate_event_suggestion()` 与 `handle_tour_event()` 双重校验。

### 11.3 易误判输入与安全规则

| 输入 | 正确结果 | 原因 |
| --- | --- | --- |
| “月台有什么？” | `rag_question` | 内容提问，不是到达。 |
| “我想去月台看看” | `clarification` | 目的表达不能写入当前位置。 |
| “讲完了，去下一站” | `confirm_stop_complete` | 先确认当前站，不允许 next 绕过确认。 |
| “我到月台了，顺便讲讲月台石雕” | `clarification` | 多意图不部分执行。 |
| “我到首进正厅了” | `arrive_at_stop` | 合法非 pending 到达由 A1-1 记录为 `self_arrival`。 |

### 11.4 至少三个关键测试及其防错意义

1. `test_fact_question_with_node_is_not_arrival` 防止事实问题污染当前位置或已访问记录。
2. `test_self_arrival_can_resolve_non_route_spatial_node` 防止收窄冻结的 `self_arrival` 能力，同时不改变正式路线顺序。
3. `test_multi_intent_arrival_plus_question_is_rejected` 防止复合输入偷偷执行其中一部分。
4. `test_text_confirmation_is_only_path_that_marks_visit_complete` 防止到达、问答或 next 误写 `visited_stop_ids`。
5. `test_fake_node_suggestion_is_rejected_before_execution` 防止解析器或未来模型虚构 `node_id`。

### 11.5 对现有模块的影响、边界和状态声明

- **已实现并验证**：纯分类器、结构化路由、统一适配层执行、澄清不改状态、Agent 集成测试；核心 38 项与完整 90 项本机回归均通过。
- **不受影响**：审核空间边、稳定 node ID、路线模板、动态路线算法、RAG 证据规则与知识卡数据。
- **仅保留接口**：`validate_event_suggestion()`；当前 A1-2 不调用真实 LLM。
- **未来规划**：真实前端页面、A2 问答后恢复导游，阶段 B 点位讲解编排器。
- **风险**：规则首版未覆盖的同义表达会澄清而不冒险执行；这是有意的安全优先取舍。

### 11.6 一分钟答辩讲稿

> A1-2 解决的是游客自然语言如何安全控制导览的问题。我们没有让大模型直接写入游览状态，而是先用纯规则把文本转成包含事件、审核节点 ID、参数和原因码的结构化决策。只有“我到月台了”这种高置信单一命令会进入到达事件；“月台有什么”仍然进入 RAG；“我到月台了，顺便讲石雕”则先澄清，不做部分执行。所有状态变化仍只通过 A1-1 的 `handle_tour_event`，它会校验事件、节点、阶段和幂等性。这样路线、知识问答与游览记录分层管理，后续成就和寄语可以基于可信的真实记录。

### 11.7 面试追问与参考回答

1. **为什么不直接使用 function calling？** 可以作为建议层，但不能代替事件、节点和状态阶段的确定性校验。
2. **为什么 next 不自动完成当前站？** 到达或问路不证明游客已听完、观察完或拍完照。
3. **如何处理同名节点？** 返回 `ambiguous_node_name` 并要求补充方位，不猜稳定 ID。
4. **为什么不顺序执行多意图？** 部分执行难审计，且会混淆 RAG 与状态变更；组合编排留给后续阶段。
5. **规则会不会太死？** 首版用澄清换取状态安全；将来可加 schema 约束模型识别，但不放松适配层。
6. **如何证明没有绕过适配层？** Agent 集成测试 mock 并断言 `handle_tour_event` 被调用，事件节点不直接赋值状态字段。

### 11.8 现场演示

```text
前置：30 分钟路线，pending=前院中部，phase=navigating，visited=[]
输入：我到前院中部了
识别：tour_event / arrive_at_stop(stop_front_courtyard_center)
结果：phase=explaining；visited 仍为 []

输入：讲完了，去下一站
识别：tour_event / confirm_stop_complete
结果：前院中部进入 visited；pending 更新为月台；phase=navigating

输入：月台有什么？
识别：rag_question
结果：进入现有 RAG；TourState 不变（A2 的答后恢复导游尚未实现）
```

## 12. A1-3：连续导游回复与按钮协议（已实现并验证）

### 12.1 用户问题与实现流程

游客不应记住事件名称，更不应由前端根据中文文案猜测下一步。A1-3 将 A1-1 的结构化事件结果转为稳定展示协议，前端未来只展示并按 `actions[].id` 提交事件。

```text
handle_tour_event() 的结构化结果
  → present_tour_event() / present_tour_state() / present_clarification()
  → {message, phase, actions, event, code, ok, idempotent}
  → 前端展示；用户或系统选择 action.id
  → handle_tour_event() 再次校验并修改状态
```

`explanation_finished` 是本次补充的生命周期事件：讲解播放结束时从 `explaining` 进入 `awaiting_confirmation`。它不代表游客已经参观完成，最后一站也必须再由 `confirm_stop_complete` 写入 `visited_stop_ids`。

### 12.2 核心文件、方案与状态安全

| 文件/函数 | 作用 |
| --- | --- |
| `tour_presenter.py` | 纯展示层，提供 `present_tour_event`、`present_tour_state`、`present_clarification` 与按 phase 生成的 `available_actions`。 |
| `tour_interaction.py: _explanation_finished()` | 适配层中唯一可改变讲解生命周期阶段的实现。 |
| `agent_graph.py: tour_presentation` | 将展示协议随 Agent 响应一并保存；状态快照仍只来自适配层。 |
| `test_tour_presenter.py` | 验证不同阶段的文案、稳定 action ID、参数与纯函数无副作用。 |

我们没有把按钮逻辑写进前端、没有按中文按钮文案分支，也没有把“再停留一会”伪造成新事件。`replan_time` 需要分钟数，因此 action 明确携带 `input_schema`，让前端收集参数而不是猜测。LLM/RAG 均不参与 presenter；只有 `handle_tour_event()` 能修改状态。

### 12.3 关键测试防止的错误

1. `test_explanation_finished_changes_only_interaction_phase` 防止讲解播放结束误写 `visited_stop_ids`。
2. `test_last_stop_still_requires_confirm_after_explanation_finished` 防止最后一站因播报结束而自动结束路线。
3. `test_waiting_confirmation_exposes_confirm_not_explanation_finished` 防止前端在等待确认阶段重复展示错误生命周期按钮。
4. `test_error_and_clarification_have_no_actions` 防止错误或歧义状态出现可能被错误执行的按钮。
5. `test_start_route_initializes_session_tour_and_interaction_state` 的扩展断言确保新路线初始化即有稳定的导航动作协议。

### 12.4 已实现、接口与未来边界

- **已实现并验证**：8 个冻结事件中的 `explanation_finished`、纯展示协议、稳定 action ID、A1-3 单元测试和 Agent 响应中的 `tour_presentation`；完整 101 项本机回归均通过。
- **仅保留接口**：`replan_time` 的 `input_schema`；未来前端负责采集整数但不做状态推断。
- **未来规划**：真实 Web/移动端、A2 问答后恢复导游、阶段 B 的讲解内容编排与知识卡接入。
- **不变边界**：空间图、路线模板、动态选点、RAG 规则和知识卡数据均未修改。

### 12.5 一分钟答辩讲稿

> A1-3 解决的是“后端已经知道状态，前端怎样安全展示并推进导览”的问题。我们把展示层做成纯函数：它接收适配层的结果，输出中文提示、当前阶段和带稳定事件 ID 的按钮数组。前端不解析“讲完了，去下一站”这句话，而是提交 `confirm_stop_complete`。为解决讲解结束与游客完成参观不同的问题，我们新增 `explanation_finished`：它只把阶段从 explaining 切到 awaiting_confirmation，不会写入已访问记录。最终仍由统一适配层验证事件、参数和阶段，因此 UI、LLM 和 RAG 都无法直接篡改 TourState。

### 12.6 面试追问与参考回答

1. **为什么要返回 action ID，而不只返回文案？** 文案可本地化和改版，稳定 ID 才能可靠对应冻结事件。
2. **为什么讲解结束不算完成站点？** 游客可能还在观察、拍照或提问；真实完成必须显式确认。
3. **为什么 `replan_time` 有 input schema？** 避免前端自行猜测参数格式，后端仍会再次校验整数分钟数。
4. **为什么 presenter 不调用 RAG？** 展示协议只解释既有事件结果；内容问答和恢复导游属于 A2。
5. **如何避免前端绕过状态机？** 前端只能提交 action ID 与参数，服务端统一进入 `handle_tour_event()` 校验。
6. **为什么不实现“再停留一会”？** 冻结契约没有对应事件；无意义新增状态会破坏可审计性，因此首版不提供状态动作。

### 12.7 现场演示

```text
到达月台 → phase=explaining
actions=[explanation_finished, request_stop_detail, skip_stop, replan_time, finish_tour]

系统播放讲解结束 → explanation_finished
phase=awaiting_confirmation，visited 不变
actions=[confirm_stop_complete, request_stop_detail, skip_stop, replan_time, finish_tour]

游客点击 confirm_stop_complete → 月台进入 visited，pending 更新为下一站，phase=navigating
```

## 13. A1-4：导游交互端到端验收与阶段收尾（已实现并验证）

### 13.1 本任务解决的用户问题

此前 A1-1、A1-2、A1-3 分别验证了状态机、文本路由和展示协议，但尚未证明它们串联时不会丢失状态或绕开适配层。A1-4 新增离线端到端验收，将“游客发一句话”一直验证到稳定的按钮响应，确保游客能安全地到达、听完、确认、继续、跳过或缩短路线。

### 13.2 修改前后流程

```text
修改前：各模块单独单测

修改后：游客文本
  → tour_intent.py（只识别受控事件）
  → agent_graph.py（确定性路由）
  → handle_tour_event()（唯一状态写入口）
  → tour_presenter.py（message / phase / actions）
```

### 13.3 核心文件、函数与字段

| 项目 | 本次职责 |
| --- | --- |
| `test_tour_interaction_e2e.py` | A1 的离线闭环验收；不引入生产业务逻辑。 |
| `tour_state` | 被检查的路线事实：`current_stop_id`、`visited_stop_ids`、`skipped_stop_ids`、`remaining_stop_ids`。 |
| `tour_interaction_state` | 被检查的交互事实：`pending_stop_id`、`stop_phase`。 |
| `tour_presentation` | 被检查的 UI 中立输出：`message`、`phase`、稳定事件 ID 的 `actions`。 |

### 13.4 方案取舍与状态安全

选择离线 E2E，而不是调用真实 DeepSeek 或 LangSmith：验收目标是确定性状态闭环，网络模型会让测试变慢且不稳定。测试通过 `unittest.mock` 观察 Agent 是否调用 `handle_tour_event()`，而不让 LLM、RAG、展示层或测试本身写入 `visited_stop_ids`。这验证了“LLM 只能给事件建议、适配层才可修改状态”的设计，而不是只在文档中声明该原则。

### 13.5 关键测试防止的错误

1. **完整生命周期**：防止“到达即完成”或未确认就推进下一站。
2. **最后一站**：防止讲解结束后自动把路线标记为 `completed`。
3. **自主到达**：防止游客提前走到首进正厅后，系统篡改正式讲解顺序或伪造已访问记录。
4. **跳过 + 重规划**：防止被跳过的点重新回到 `remaining_stop_ids` 或误记为访问。
5. **歧义、多意图、未知点位**：防止识别不确定时发生部分状态修改。
6. **详情占位和幂等**：防止 A1 提前接入 A2 RAG，或重复网络/UI 事件造成重复访问计数。

### 13.6 已实现、接口与未来边界

- **已实现并验证**：离线 E2E 验收文件和 7 个闭环场景；项目负责人已完成完整 141 项本机回归，结果均为 `OK`。
- **未改变**：RAG、空间图、路线算法、稳定 ID、知识卡和真实前端。
- **仅保留接口**：A1-3 的 `actions` 与 `replan_time` 输入 schema，供未来前端使用。
- **未来规划**：A2 游览中 RAG 问答后恢复导游、点位讲解编排器、持久化及实时定位；均尚未实现。

### 13.7 一分钟答辩讲稿

> A1-4 是我们对导游交互状态机的阶段验收。此前我们已把到达、讲解结束、确认完成拆成独立事件，也把文本识别和按钮展示分开。本轮没有增加功能，而是通过离线端到端测试把它们串起来：游客一句“我到前院中部了”先被确定性识别，再由 Agent 路由到唯一状态适配层，最后返回带稳定事件 ID 的展示协议。测试特别检查最后一站不会自动结束、自主到达不会打乱路线、歧义输入不会部分执行。这样后续接入 RAG 问答时，有一个可审计、可回归的导游状态底座。

### 13.8 面试追问与参考回答

1. **为什么 E2E 不调用真实 LLM？** A1 验证的是确定性协议；真实模型属于 A2/性能层，会降低回归测试稳定性。
2. **如何证明 Agent 没绕开状态机？** 测试 mock `agent_graph.handle_tour_event` 并断言文本事件只从该入口执行。
3. **为什么将 `explanation_finished` 和确认完成分开？** 内容播放结束不代表游客看完、拍完或不再提问，只有显式确认才计入真实访问。
4. **自主到达为什么不直接加入路线？** 游客位置事实与正式讲解进度是两类事实；混合会破坏路线统计和成就数据。
5. **歧义输入为什么不猜？** 在导游状态机中错误推进比多问一句风险更高，因此采用澄清优先。
6. **A1 已经能回答文物问题吗？** 现有普通 RAG 仍可回答事实，但“问答后自动恢复当前导游”是 A2，尚未实现。

### 13.9 现场演示示例

```text
输入：我有 30 分钟，帮我规划路线
状态：pending_stop_id=stop_front_courtyard_center，phase=navigating

输入：我到前院中部了
状态：current_stop_id=stop_front_courtyard_center，phase=explaining，visited=[]
输出：actions 包含 explanation_finished

系统事件：explanation_finished
状态：phase=awaiting_confirmation，visited=[]

输入：讲完了，去下一站
状态：visited=[stop_front_courtyard_center]，pending_stop_id=label_moon_platform，phase=navigating
输出：下一站导航和 arrive_at_stop 按钮
```

## 14. A2-1：游览中 RAG 问答与导游上下文恢复（已实现并验证）

### 14.1 解决的用户问题与真实流程

游客到达“前院中部”后问“这里有什么”，原普通 RAG 只检索 Markdown 事实库，不知道人工标注的点位—文物关系，因此不能利用该点已有的 11 件文物候选。A2-1 将请求分层：点位清单由已审核讲解包确定性回答；工艺、寓意、故事与单件文物解释才调用原 RAG，并在回答后恢复导游操作。

```text
“这里有什么 / 月台有哪些装饰”
→ 解析 current_stop_id 或明确 node_id
→ node_guide_cards_v1.json
→ 确定性输出审核关联清单、工艺分布、guide_focus

“这里的石雕有什么特点 / 独角狮讲什么”
→ current_stop_id + 已审核讲解包作为检索提示
→ 既有 chen_clan_academy_rag_search
→ 只用 evidence 生成带来源摘要
→ A1-3 presentation 恢复当前 phase / actions
→ END，TourState 不写入
```

无活动路线仍沿用原路径：`direct_rag → llm_think`。到达语句仍优先走 `tour_event`，不会被 A2 抢走。

### 14.2 核心文件、函数与字段

| 文件 / 函数 | 真实职责 |
| --- | --- |
| `tour_qa.py: resolve_point_context()` / `format_point_inventory()` | 解析当前或明确点位，确定性读取已审核的“文物—点位关联”、工艺分布和 `guide_focus`；不解释文化含义。 |
| `build_tour_qa_query()` | 将当前点信息追加到原问题中，帮助既有 BM25/稠密检索命中对应文物。 |
| `answer_tour_question()` | 接收注入的既有 RAG 调用，捕获异常、解析 evidence、保持输入状态不变。 |
| `format_tour_qa_answer()` | 仅引用 evidence 的文档、标题、`source_ids` 与正文片段；无证据时明确资料不足。 |
| `agent_graph.py: tour_qa_node` | 复用 `chen_clan_academy_rag_search`，返回回答、evidence 和 `tour_presentation`，但故意不返回 TourState 更新。 |

### 14.3 为什么采用此方案

我们没有把人工空间映射重新嵌入向量库。对“哪里有什么”，审核映射本身就是结构化关联的权威项目数据，因此可直接列清单；但它不解释文化含义。对“有什么特点、寓意、故事”，当前方案才把空间映射限定为检索条件，事实仍必须来自已建立、带 `source_ids` 的 RAG evidence。这样既避免第二套索引，也不把人工归类误说成馆方历史解释。

LLM 不会直接篡改状态：活动问答进入确定性 `tour_qa_node`，该节点不调用状态写函数，也不返回 `tour_state`、`tour_interaction_state`；后续仍由 A1 的 `handle_tour_event()` 处理到达、跳过和确认完成。

### 14.4 关键测试说明

1. **当前点位清单**：验证“这里有什么”直接返回前院中部 11 件审核关联文物与工艺分布，且不调用 RAG。
2. **明确点位清单**：验证无活动路线时“月台有哪些装饰”仍可确定性读取月台讲解包。
3. **点位文物解释**：验证“这里的石雕有什么特点”才把石雕候选名称用于 RAG，并返回 `08_ornament_items.md`、`S11` 等来源。
4. **状态快照不变**：深拷贝比较问答前后的 `current_stop_id`、访问/跳过/剩余列表和 phase，防止问答意外推进游览。
5. **self_arrival、缺包与未知点**：验证真实当前位置可被读取；包缺失或未知点时安全拒绝，不猜测。
6. **无证据 / RAG 异常**：验证返回“资料不足”或“检索暂不可用”，不利用点位提示编造解释，也不破坏导览。
7. **Agent 路由与继续导览**：验证清单走 `tour_qa`、一般无路线事实仍走旧 `direct_rag`、“我到月台了”仍走事件，且问答后可确认完成。

### 14.5 已实现、接口与未来边界

- **已实现并验证**：点位感知检索提示、确定性点位清单、证据摘要、A1 操作面板恢复、mock 单元/集成测试；项目负责人已完成 A2 相关 106 项及完整 155 项本机回归，均为 `OK`。
- **保持不变**：向量索引、BM25、稠密检索、RRF、重排器、空间边、路线模板、稳定 node ID。
- **仅保留接口**：点位讲解包中的研究/比较/术语/打卡卡 ID；本任务不读取这些字段。
- **未来规划**：回答后由 LLM 做更自然的长讲解、代表文物动态挑选、论文/比较卡接入、真实前端会话恢复。不能表述为当前已实现。
- **风险**：当前 RAG 默认仅返回有限条 evidence；它会优先给出可证实的代表条目，而不是自动完整枚举一个点位全部文物。完整“本站讲哪几件、讲多久”属于阶段 B 讲解编排器。

### 14.6 一分钟答辩讲稿

> A2-1 解决的是“游客正在某个点位时，系统既要知道这里有哪些东西，又不能把空间归类和文化解释混为一谈”的问题。我们把请求分成两类：问“这里有什么”时，系统确定性读取已审核点位讲解包，输出文物清单、工艺分布和导览焦点；问“石雕有什么特点、独角狮讲什么”时，才用这些名称提示现有混合 RAG，并只依据返回 evidence 解释。回答结束后恢复 A1 的 phase 和按钮操作，A2 节点完全不写 TourState。因此游客可继续确认、跳过或重规划，问答不会污染游览记录。

### 14.7 面试追问与参考回答

1. **为什么不用当前点位过滤掉其他资料？** 游客可在月台问陈家祠建成年份；点位只应增强相关性，不应限制真实问题范围。
2. **人工标注为何不能直接当事实回答？** 它表达导览归类与空间审核，证据等级不同；馆内事实仍需回到有来源编号的知识块。
3. **RAG 没有证据怎么办？** 明确返回资料不足，不通过候选文物名称推断内容。
4. **怎么保证问答不改变进度？** `tour_qa_node` 不调用 `handle_tour_event`，也不返回任何 TourState 更新；测试对快照作严格比较。
5. **self_arrival 有何价值？** 可让检索贴合游客真实位置，同时保留原路线待访问顺序，避免伪造完成记录。
6. **为什么不让 LLM 直接读点位 JSON？** LLM 可能将提示当作证据或遗漏来源；确定性层先约束数据流更可审计。

### 14.8 现场演示示例

```text
状态：current_stop_id=stop_front_courtyard_center，pending_stop_id=stop_front_courtyard_center，phase=explaining
输入：前院中部有什么值得看？
检索提示：前院中部 + 独角狮、福禄寿、功名富贵等候选名称
输出：仅展示 RAG 返回的文物条目、文档名与 source_ids；并返回 explaining 阶段的 explanation_finished / request_stop_detail 等操作
状态后：current/pending/visited/skipped/remaining/phase 均不变
```

## 15. B1：点位讲解编排器基础与确定性选物（已实现并验证）

### 15.1 本任务解决的问题与流程

路线规划只决定游客去哪里和停多久，A2 只能回答问题；它们都没有决定“在月台 5 分钟内究竟讲哪几件”。B1 新增纯 `StopProgram`，把已审核的点位文物清单压缩为可审计的 1–3 件代表对象。

```text
node_id + budget_seconds + interests + detail_level
→ node_guide_cards_v1.json 的当前点审核 ornaments
→ 兴趣匹配分数降序、ornament_id 升序
→ short / standard / deep 对应 1 / 2 / 3 件上限
→ StopProgram（不调用 RAG，不改变 TourState）
```

### 15.2 核心文件与方案取舍

| 文件 / 字段 | 作用 |
| --- | --- |
| `guide_program_planner.py: plan_stop_program()` | B1 唯一入口，校验输入和点位讲解包，产生不可变 `StopProgram`。 |
| `SelectedItem` | 记录 `ornament_id`、角色、秒数、理由与 `rag_query_hints`，供 B3 取证。 |
| `research_summary_card_ids` / `comparison_card_ids` | 预留为空；B1 不读取任何知识卡。 |
| `tour_qa.load_guide_cards()` | A2/B 共用的只读讲解包加载函数，避免两套数据读取规则。 |

没有让 LLM 选文物，也没有按名称“猜”故事。所有候选都来自当前点卡；并列时稳定 ID 打破平局，便于复现、评估和人工审核。B1 只做基础均分，避免提前把 B2 的多样性、互动和观察时间策略混进来。

### 15.3 测试、边界与答辩

- **候选合法性**：月台的选中 ID 必须是月台卡内 ID，防止跨点位串讲。
- **确定性**：相同输入连续调用结果完全相同，防止非确定性导览。
- **兴趣影响**：mock 卡中“灰塑”兴趣会把灰塑对象排到木雕对象前，同时无兴趣时稳定 ID 优先。
- **数量与空候选**：short/standard/deep 分别最多 1/2/3 件；空卡返回 `no_reviewed_candidates` 而不造对象。
- **已实现并验证**：B1 纯规划器和单测；项目负责人已完成 B1 相关 112 项及完整 161 项本机回归，均为 `OK`。未接入 Agent/RAG/最终讲解文本。
- **未来**：B2 时间与多样性，B3 RAG 取证与 Agent 接入，B4 端到端评估。

一分钟答辩：

> B1 解决了路线到站后“讲什么”的可控性问题。我们以审核过的点位讲解包作为唯一候选来源，将游客兴趣和详略等级转为稳定排序，再用 ornament_id 打破并列。输出不是自然语言，而是可审计 StopProgram：每件文物都有角色、时间、选择理由和后续 RAG 查询提示。这样路线、选物、事实取证和生成讲解被拆开，LLM 不会改路线或凭空选文物。后续只需把论文卡等 card_id 插入既有接口，而不需要重建空间网络。

面试追问：

1. **为何不直接讲完所有文物？** 时间有限，代表对象组合更适合真实导览；完整选择策略由 B2 优化。
2. **为何并列用 ID？** ID 是稳定数据主键，保证同输入同输出，便于回归测试。
3. **兴趣分数会不会是事实判断？** 不会，它只排序审核候选；事实解释仍在 B3 由 RAG evidence 提供。
4. **空候选怎么办？** 返回结构化 `no_reviewed_candidates`，不临时借用邻近点文物。
5. **为什么预留 card ID 但不使用？** 允许其他成员并行建库且不阻塞基础导览，审核后再定向接入。

演示：

```text
输入：label_moon_platform，300 秒，兴趣=[石雕]，detail_level=deep
输出：月台卡内至多三件对象；石雕候选优先；三件 planned_seconds 之和为 300；每件带现有 rag_query_hints
状态：TourState、路线和 RAG 均不改变
```

## 16. B2：StopProgram 时间预算与内容排序（已实现并验证）

### 16.1 解决的问题与真实流程

B1 已经能从当前点位的审核文物中选择对象，但把整段预算平均分给所有对象，无法体现“短讲、标准讲、深度讲”的差别，也可能连续选到同类内容。B2 将“本站讲解内容预算”与路线步行时间明确隔离，并把排序与时间分配变成可审计的确定性策略：

```text
node_id + 本站内容预算 + 兴趣 + detail_level
→ 只读当前点审核 ornaments
→ 兴趣相关性排序
→ 仅在相关性接近时补充不同工艺/题材
→ short / standard / deep 的数量与时间模板
→ StopProgram（已分配时间 ≤ 内容预算）
```

### 16.2 核心实现与取舍

| 文件 / 字段 | 真实职责 |
| --- | --- |
| `guide_program_planner.py: STOP_PROGRAM_POLICY` | 唯一集中配置数量阈值、推荐时长、兴趣权重和多样性窗口，避免散落魔法数字。 |
| `_select_diverse_candidates()` | 先保留高相关对象；只有分数在窗口内才为新工艺/题材加分，并以 `ornament_id` 稳定打破平局。 |
| `_allocate_item_seconds()` | 只分配输入的内容预算；不足时按模板确定性缩放，低预算只生成一项简短概览。 |
| `StopProgram.budget_scope` | 固定为 `stop_explanation_content_only`，防止把它误认为包含步行的路线总预算。 |
| `allocated_content_seconds` / `unallocated_content_seconds` | 使每秒时间去向可审计，二者之和等于输入预算。 |

没有采用“让 LLM 根据感受选三件最精彩文物”，因为不可复现且容易越过审核候选；也没有为了多样性牺牲明显更相关的对象。多样性只在相关性接近时作为次级规则。

LLM、RAG、TourState 和路线均不参与 B2：它们既不能选择候选，也不能写入这个纯函数的状态。因此 B2 不会篡改导游进度，也不会占用已审核空间图的步行时间。

### 16.3 测试、影响与边界

1. **预算边界**：验证 60 秒深度请求降级为单项“简短概览”，150/270 秒才分别解锁 2/3 件，防止超时或过度承诺。
2. **兴趣优先**：验证“灰塑”兴趣仍让灰塑对象领先，避免多样性规则抢走核心兴趣。
3. **相关性接近时多样性**：验证无兴趣并列候选会由灰塑补充到木雕，避免同一工艺重复讲三次。
4. **稳定性与全预算防护**：相同输入输出一致；所有详略等级和预算组合都满足已分配时间不超过内容预算。

- **已实现并验证**：B2 代码、离线 mock 测试和协作文档更新；项目负责人已完成完整 166 项本机回归，耗时 1.740 秒，结果为 `OK`。
- **保持不变**：路线规划、步行时间、空间边、审核讲解包、RAG、TourState 与知识卡数据。
- **仅保留接口**：`rag_query_hints`、研究/比较卡 ID 仍未在 B2 使用。
- **未来规划**：B3 对选中对象调用现有 RAG 取证并接入 Agent；观察、互动与真实现场时长也应在后续基于实测数据单独配置，不能被描述为当前已实现。

### 16.4 一分钟答辩讲稿

> B2 解决的是“路线已给本站五分钟，但系统怎样把这五分钟合理分配给代表文物”的问题。我们没有让语言模型即兴决定，而是只从人工审核过的点位文物中选择。策略先按游客兴趣保证相关性，例如喜欢灰塑就优先灰塑；当几个对象相关性接近时，才优先不同工艺或题材，避免连续讲三个重复内容。所有阈值和权重集中在一个策略表，输出中明确记录这是讲解内容预算而非步行时间，并记录已分配与未分配秒数。这样每个选择都能复现、测试和人工调整，B3 再用 RAG 为这些已选对象补充有来源的事实讲解。

### 16.5 面试追问、参考回答与演示

1. **为什么不把全部预算平均分配？** 平均分配忽略详略等级和对象数量；B2 用集中模板让短讲聚焦、深讲扩展，但永不超预算。
2. **多样性会不会降低兴趣匹配？** 不会。只有与当前最高相关性差距在策略窗口内的候选才比较多样性；高相关候选仍优先。
3. **为什么要保留未分配内容时间？** 它使系统不虚构“每一秒都在讲文物”，并为后续经审核的观察、互动安排留下可追溯空间。
4. **如何调参？** 只修改 `STOP_PROGRAM_POLICY`，然后用预算边界、兴趣和多样性回归测试对比，不能在业务函数中临时散落数字。
5. **B2 会不会改变路线？** 不会。它只读 `node_id`、审核候选和单站内容预算；路径、边与 TourState 完全在模块边界外。

现场演示：输入 `label_moon_platform, 150 秒, interests=["石雕"], detail_level="standard"`；输出只含月台审核对象，最多两件，`allocated_content_seconds <= 150`、`budget_scope=stop_explanation_content_only`，并附每件的 `rag_query_hints`。路线节点、步行时间和 TourState 前后不变。

## 17. B3：StopProgram 取证与 Agent 点位讲解（已实现并验证）

### 17.1 用户问题、流程与模块边界

此前系统虽然能选出本站代表文物，却不能把“选物”安全地变成导游词。B3 建立了受控链路：

```text
计划内到达正式站点
→ StopProgram（只决定讲哪些对象）
→ 每件对象的 rag_query_hints 调用既有 RAG
→ 仅依据 evidence 输出讲解与来源
→ 仍停留 explaining
→ 用户/UI 显式 explanation_finished
→ awaiting_confirmation → confirm_stop_complete
```

| 真实文件 / 函数 | 责任 |
| --- | --- |
| `guide_program_evidence.py: build_stop_guidance()` | B3 纯编排入口；校验当前是计划内已到达站点，生成 StopProgram、逐项调用注入的现有 RAG、处理无证据与异常。 |
| `agent_graph.py: stop_guidance_node` | Agent 图中的确定性节点；仅更新消息、证据、展示协议和审计用 `active_stop_program`。 |
| `tour_interaction.py: request_stop_detail` | 仍只处理无副作用生命周期事件；B3 在事件成功后展开讲解。 |

我们没有让 LLM 写导游词后再“补来源”，也没有将全部点位文物塞入一次模糊检索。StopProgram 先约束对象，RAG 再为每项提供证据；没有 evidence 时明确降级。LLM 没有任何 TourState 写入口，`visited_stop_ids` 仍只能经过 `handle_tour_event() → confirm_stop_complete` 改变。

### 17.2 测试、影响、演示与答辩

关键测试包括：

1. **计划内到达取证**：确认每件选中对象都有对应查询，消息包含文档和 `source_ids`，而 TourState 快照不变。
2. **无证据/异常**：确认输出“未检索到可引用事实”，而不是按对象名称补充故事。
3. **自主到达**：确认合法 `self_arrival` 不会被误当作正式站点讲解。
4. **Agent 接线与详情**：确认到达和“再讲详细一点”才进入 `stop_guidance`，详情后仍未完成站点。

- **已实现并验证**：B3 编排层、Agent 节点、无副作用详情事件迁移和离线 mock 测试；项目负责人已完成完整 173 项本机回归，耗时 1.775 秒，结果为 `OK`。
- **保持不变**：路线、步行预算、空间边、A1 状态语义、A2 插入问答、基础 RAG 索引。
- **未接入**：论文卡、比较卡、术语卡、打卡点卡、LLM 长篇讲稿、真实前端与现场定位。

一分钟答辩讲稿：

> B3 把“选什么讲”和“事实依据是什么”分成两层。B1/B2 只在人工审核过的本点文物中选一到三件，并分配本站讲解内容预算；B3 再按每件对象的查询提示调用已有混合 RAG。最终讲解只引用返回的 evidence，检索不到就明确说明资料不足，而不从文物名称推测故事。这个节点只更新展示和审计数据，不更新游览进度；游客必须显式结束讲解并确认完成，才会改变 visited 记录。因此我们同时保证了个性化、可追溯性和导游状态的可靠性。

可能追问：

1. **为何每件对象单独检索？** StopProgram 已缩小到 1–3 件，逐项查询更可审计，也避免一个宽泛结果支撑多件文物。
2. **RAG 无证据怎么办？** 保留已审核“对象在此点”的关联，但不把它升级为文化事实；回复资料不足。
3. **为什么不自动结束讲解？** 讲解播放结束与游客完成观赏不同，A1 契约要求由显式事件分开处理。
4. **`request_stop_detail` 会不会重复写状态？** 不会，它是幂等、无副作用请求；B3 只复用同一确定性 StopProgram。
5. **如何接入论文卡？** 后续只在已审核的 `card_id` 插槽中按意图定向增强，不改变基础 RAG 或空间网络。

现场演示：游客到达前院中部后，系统生成该点的 StopProgram，再检索选中对象并展示 `08_ornament_items.md / S11` 等来源；状态仍为 `explaining`、`visited_stop_ids=[]`。游客点击“本点讲解结束”后才进入 `awaiting_confirmation`，点击“讲完了，去下一站”后才写入 visited。

## 18. 后续实施报告附加规范

每个 A1/A2 子任务完成时，实施报告末尾必须基于真实代码与测试结果说明：用户问题、前后流程、文件/函数/字段、方案取舍、LLM 状态边界、至少三个测试、模块影响、风险、1 分钟讲稿、至少 5 个追问、演示示例，以及“已验证/待验证/接口/未来”状态。若发生规划—实现冲突，还必须记录冲突、最终语义、依据和软件工程原则。
