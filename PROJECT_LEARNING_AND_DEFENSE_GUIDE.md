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
| 按钮导游、文本“确认完成”识别 | **仅保留契约，待 A1-2/A1-3** |
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
- **待实现**：文本“我讲完了”意图（A1-2）、按钮与连续导游回复（A1-3）、游览中 RAG 问答恢复导游（A2）、持久化、实时定位、人流避让。

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
   底层协议已支持稳定事件和 node_id；按钮/连续模式在 A1-3 实现，当前尚未上线。

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

## 10. 后续实施报告附加规范

每个 A1/A2 子任务完成时，实施报告末尾必须基于真实代码与测试结果说明：用户问题、前后流程、文件/函数/字段、方案取舍、LLM 状态边界、至少三个测试、模块影响、风险、1 分钟讲稿、至少 5 个追问、演示示例，以及“已验证/待验证/接口/未来”状态。若发生规划—实现冲突，还必须记录冲突、最终语义、依据和软件工程原则。
