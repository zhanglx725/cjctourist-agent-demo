# CURRENT ROLE SHADOW HANDOFF (2026-08-09)

```text
current_validation_date: 2026-08-10
role_narration_budget_quality_gate: passed
role_mode_and_continuity: 16/16 passed
role_targeted_validation: 73/73 passed
p0_matrix: 3/3 passed
full_regression: 1095/1095 passed
18_style_shadow_baseline: pending
active_takeover: disabled
```

## Baseline cleanup boundary

The baseline cleanup is a separate completed change. It updates deterministic
profile parsing and test observability only: no role Shadow implementation,
presentation-content-plan code, Active flag, route-state contract, RAG data,
or Studio launcher is part of it. `visitor_localization` remains in the full
Graph trace; tests must assert semantic-node presence and order rather than a
terminal metric slice. Visitor interests retain input order.

Verification: baseline targeted `57/57`, full regression `1061/1061`.

## Route/opening role-text Shadow boundary

`route_planning` and `route_opening` may append only a separate Shadow audit
record. The candidate contains a reviewed role lead-in plus the full legacy
public message; validation rejects any schema, route/fact/safety, budget,
internal-field or role-boundary drift. Do not connect this candidate to
visitor output or operational state. Verified tests: role-text 22/22, P0 18/18;
full regression remains 1053/1058 with the known five baseline failures.

```text
role_schema: fixed
role_shadow: implemented_and_automated_verified
presentation_content_plan: implemented
presentation_content_plan_shadow: automated_verified
route_opening_shadow: implemented_and_automated_verified
route_opening_shadow_manual: passed_by_operator
role_active: disabled
active_takeover: disabled
role_shadow_targeted_tests: 22/22 passed
presentation_content_plan_targeted_tests: 9/9 passed
route_opening_integration_tests: 19/19 passed
full_regression: 1047/1052
p0_matrix: 10/10 passed
p0_matrix: passed
```

The role Shadow phase now has one deterministic selector for the complete
reviewed style catalog. It may record role selection and generate a candidate for
evaluation, but it must not publish the candidate or write TourState,
VisitorProfile, route, proposal, StopProgram, Coverage, RAG, or tool state.
Unknown and multi-role requests must remain clarification records.

The five known baseline failures are preexisting and remain a separate issue
list; do not change their assertions while finishing role Shadow.

统一 `presentation_content_plan` 当前只作为 Shadow 审计结构，覆盖
`route_planning`、`route_opening`、`stop_guidance`、`navigation` 和
`tour_closing`。它只能描述内容结构、角色表达策略、审核证据要求、
安全要求和场景预算；不得保存内部 ID、RAG 原文、游客最终答案或状态
补丁。旧链仍是唯一游客正文来源，Active 与 takeover 均关闭。

`route_opening` 是首次到站时紧接 `stop_guidance` 的独立展示场景。
它的 Shadow 记录必须在 `tour_opening_node` 生成旧开场正文后立即追加，
不得等待末端 `atomic_read_plan_shadow`，否则会被随后点位讲解覆盖。该记录
只在 `presentation_content_plan` 的 Shadow capability 开启时产生；不得写入
TourState、VisitorProfile、路线、proposal、StopProgram、Coverage 或游客正文。
重复的幂等“开始导游”不应追加第二条开场计划。当前自动化与 Studio 操作员
复测均已通过；开场记录为 `accepted`、`active_takeover=false`、旧正文保留且
`state_writes=[]`。未保存 Trace URL/revision 时必须写 `metadata_unavailable`。

# 陈家祠金牌导游 Agent：多人协作公共说明

## 角色候选 Schema Phase 1 共享边界（2026-08-09）

- `role_narration_generation.py` 的模型 wire object 只允许 `role_narration_candidate_v1` 六个字段；未知字段、缺字段、错误类型、未知角色和未知版本必须失败关闭。
- Graph 中的十字段候选 envelope 也必须严格反序列化，不能通过宽松 parser 绕过模型 Schema；`generation_status=rejected` 时不得携带游客正文。
- 角色模型只能重排审核事实并改变表达策略。`node_id`、路线 ID、对象 ID、来源 ID、TourState、VisitorProfile、Proposal、RAG 原文和最终游客答案不属于角色候选输出。
- LangChain 内容块只允许明确的文本块进入 JSON 解码；禁止用 `str(list)` 将内容块转换为伪 JSON。
- 角色候选失败时沿用旧确定性讲解；Shadow 不接管消息，Active 继续 disabled。任何协作者不得借修复 Schema 顺带接入路线、状态、画像、RAG 或新的 presentation plan。
- 角色 Schema 定向测试 `15/15 OK`；父提交 `28c6d6b` 与当前提交 `ca4b64c` 的完整回归均为 `1031/1036`，4 failure + 1 error 已确认是既有会话/画像—路线/摘要断言基线问题，未修改这些旧断言。`test_agent_graph.py` 不存在，不计入回归。P0 安全/游客输出矩阵 `62/62 OK`；Phase 1 状态为 `partial_due_to_preexisting_failures`。

## P3-01 协作边界（2026-08-03）

`tour_mode` 仍只能表示 `chat` / `button_guided` / `continuous`。产品模式必须使用同一 `tour_interaction_state` 中的 `journey_mode`（`classic` / `custom`）；禁止写入 VisitorProfile、TourState 或创建第二会话状态。默认 classic 必须透明，custom 必须由游客明确选择。custom 只收集时长和兴趣，并仅在讲解时派生为详细策略；不得把此派生值保存为画像、路线或进度事实。任何只读问答只能更新受控恢复标记，不得修改游览事实、路线、StopProgram 或 Coverage。CardDispatcher 与主动卡片内容属于 P3-03，协作者不得提前接入。

本文件面向当前三人协作。目标是让不同知识库可以独立建设，并通过稳定 ID
接入同一 Agent；不要直接修改彼此模块的事实内容或空间主键。

项目整体学习与答辩材料见 `PROJECT_LEARNING_AND_DEFENSE_GUIDE.md`；`PROJECT_PROGRESS_REPORT.md` 仅记录进度与真实状态。自 A1 起，每个子任务的实施报告末尾必须附带基于真实代码与测试结果的“项目学习与答辩说明”，并明确区分已验证、待验证、接口与未来规划。

## 当前模块与负责人边界

| 模块 | 当前状态 | 主要文件 | 可由协作者新增的内容 | 不应直接修改的内容 |
| --- | --- | --- | --- | --- |
| 基础事实 RAG | 已完成 v1 | `data/chen_clan_academy/knowledge/` | 经核验的稳定馆藏事实 | 已有来源 ID、RAG 分块规则、索引产物 |
| 空间与路线 | 已完成 v1 | `data/chen_clan_academy/spatial/`、`routes/` | 经审核的边、点位映射、路线扩展卡 ID | `node_id`、已审核边的含义、路线时间依据 |
| 学术研究摘要卡 | 建设中 | 建议新建 `data/chen_clan_academy/research_cards/` | 论文摘要、观点、方法、争议、来源 | 不把论文观点改写为馆内既定事实 |
| 建筑/工艺比较卡 | 建设中 | 建议新建 `data/chen_clan_academy/comparison_cards/` | 对比对象、维度、异同、证据与适用点位 | 不改变路线空间图或原始装饰位置 |
| 术语卡 | 未开始 | 建议新建 `data/chen_clan_academy/term_cards/` | 术语定义、中文/英文/拼音、适用语境 | 不替代 RAG 的事实证据 |
| 打卡点卡 | 未开始 | 建议新建 `data/chen_clan_academy/photo_spots/` | 构图、秩序、安全、限制与审核日期 | 未审核前不可加入自动路线 |

## 文件中文名与功能

| 文件/目录 | 中文名 | 功能 |
| --- | --- | --- |
| `spatial/marker_inventory_v0.csv` | 空间点位总表 | 唯一 `node_id`、中文名称、类型和地图坐标；所有点位关联以它为准。 |
| `spatial/edges_v0.csv` | 空间通行边表 | 两点可通行关系、双向性、步行秒数、时间依据和审核状态。 |
| `spatial/ornament_spatial_mapping_v1.csv` | 文物—点位正式关联表 | 105 条装饰对应到 `final_node_id` 的人工审核结果。 |
| `routes/route_stop_catalog_v1.csv` | 路线讲解点目录 | 可讲解点的文物数量、工艺数量、主题、讲解焦点和路线资格。 |
| `routes/route_templates_v1.json` | 路线骨架表 | 30/60/90 分钟路线的停留顺序、主题、可选点和体验预算。 |
| `routes/route_policy_v1.json` | 路线规则表 | 可用边状态、前庭/月台互斥、时间缓冲和重规划规则。 |
| `routes/dynamic_route_policy_v1.json` | 动态路线规则表 | 任意时长组合的时长边界、候选门槛、评分权重和人工锚点路线回退规则。 |
| `routes/node_guide_cards_v1.json` | 点位讲解包 | 路线站的文物列表、工艺分布、RAG 查询提示与扩展卡接口。 |
| `research_cards/` | 学术研究摘要卡库 | 建议按“论文一张卡”建设，供深度讲解引用。 |
| `comparison_cards/` | 建筑比较卡库 | 建议按“一个对比问题一张卡”建设，供比较问答和深度路线使用。 |

## 动态路线模块（A0）

| 文件 | 中文名 | 当前功能 | 维护边界 |
| --- | --- | --- | --- |
| `dynamic_route_planner.py` | 动态路线组合器 | 从路线讲解点目录中筛选已审核、至少 4 件文物、可达且未被排除的候选点；按文物密度、工艺多样性、兴趣、主题重复评分，并以“内容价值－到下一站绕路成本”的束搜索选点；再以单点局部替换和 2-opt 消除局部折返。输出完整路径、边、讲解/观察/互动/步行时间拆分。 | 只能使用 `route_stop_catalog_v1.csv` 和已审核空间边；不要让 LLM 自行虚构通路或修改点位事实。 |
| `test_dynamic_route_policy.py` | 动态路线规则测试 | 验证时长范围、锚点路线保留和候选门槛。 | 修改 `dynamic_route_policy_v1.json` 后必须运行。 |
| `test_dynamic_route_planner.py` | 动态路线组合测试 | 验证候选数量、可达性、排除点、前庭/月台互斥、兴趣得分，以及 45 分钟动态路线的时间上限、完整路径与三国故事偏好。 | 修改空间图、路线点目录或动态评分逻辑后必须运行。 |
| `inspect_dynamic_route.py` | 动态路线人工预览器 | 输入时长、兴趣词与可选排除点，展示中文讲解点、完整节点路径、边 ID、时间拆分及每站可解释得分。 | 仅用于审核和调参，不直接修改任何空间数据。 |
| `route_benchmark.py` | 锚点路线基准评估器 | 同时生成动态路线与 30/60/90 人工锚点路线，比较预算、关键停留点覆盖、兴趣得分与站点重合度，给出 `anchor` 或 `dynamic` 建议策略。 | 仅用于 A0-5/A0-6 评估；尚未接入 `agent_graph.py`。 |
| `routes/route_benchmark_cases_v1.json` | 路线基准用例集 | 固定 30、60、90 分钟锚点对照及 45、75 分钟动态组合用例；每个用例的关键人工点必须可追溯。 | 修改路线模板或动态选点规则后必须复跑。 |
| `test_route_benchmark.py` | 路线基准回归测试 | 验证动态路线预算、锚点回退和非锚点时长保持动态组合。 | A0-5 的最低自动验收。 |
| `route_review.py` | A0-6 人工审核报告生成器 | 把基准结果转为可审核记录：自动检查预算、重复讲解点、重复边、主题重复候选；保留人工判断字段。 | 只可填写生成文件中的 `manual_review` 字段；不得修改 `node_id` 或边 ID。 |
| `routes/route_review_results_v1.json` / `.csv` | A0-6 人工审核结果表 | 每个基准用例一条记录；JSON 保留完整可追溯数据，CSV 可直接用 Excel 填写讲解价值、顺序、折返、主题重复和时间真实性。 | 由 `route_review.py` 生成；重新生成前先提交或备份已填写的人工结论。 |
| `test_route_review.py` | A0-6 审核交接测试 | 验证每个基准用例都有待审核项，并且关键自动约束可见。 | 修改评估字段时必须运行。 |

`inspect_dynamic_route.py --exclude <node_id>` 的含义是“不要把此点作为讲解停留点”；它**不是**封路，因为路线仍可经由该已审核节点通行。若将来需要表达临时封闭，应另建“禁用通行边/节点”的空间状态接口，不能复用此参数。

路线的出口区统一为 `stop_front_courtyard_center`（前院中部）。它是完整路径的终点，但回程只算通行时间，**不**作为重复讲解停留点；动态路线选点和人工锚点路线的时间预算均已包含这段回程。

`agent_graph.py` 的 `direct_route` 现已接入 A0：精确 30/60/90 分钟请求优先使用人工审核锚点，45/75 等非锚点时长调用动态路线组合器。两类请求均不让 LLM 自行选点或虚构通路。

## TourState 阶段 A

| 文件 | 中文名 | 当前功能 | 维护边界 |
| --- | --- | --- | --- |
| `tour_state.py` | 游览会话状态纯函数 | 初始化路线会话、记录到达、查询下一站、跳过站点和结束游览；所有点位均校验 `marker_inventory_v0.csv`，输入状态不被原地修改。 | 当前只保存会话内存；不得在这里调用 LLM、RAG、重规划器或修改空间图。 |
| `tour_interaction.py` | A1 统一导游交互适配层 | 唯一公开事件入口；按 `TOUR_INTERACTION_CONTRACT.md` 处理到达、下一站、跳过、改时间、结束、展开讲解占位与确认完成，返回统一结构化响应。 | 不调用 LLM、RAG 或 UI；不得修改空间/路线/知识卡数据。`visited_stop_ids` 只能在 `confirm_stop_complete` 写入。 |
| `test_tour_state.py` | 游览会话状态测试 | 验证初始化、无副作用下一站、跳过、全部跳过后的结束和显式结束；到达/确认语义由交互适配层测试。 | 修改状态字段或转移规则后必须运行。 |
| `test_tour_interaction.py` | A1 交互契约测试 | 验证计划内到达、自主到达、确认完成、幂等、结构化拒绝、跳过、重规划保留当前点和结束。 | 修改事件、错误码、交互状态或返回包后必须运行。 |
| `tour_navigation.py` | 下一站确定性导航器 | 从 TourState 找到下一个剩余讲解点，调用已审核空间图输出节点、边、步行时间与该点 `guide_focus`。 | 不修改 TourState；不调用 LLM、RAG 或重规划器。 |
| `test_tour_navigation.py` | 下一站导航测试 | 验证入口起步、到达后推进、跳过点排除、可达路径和完成路线后的空下一站。 | 修改空间图、讲解点目录或导航输出后必须运行。 |
| `replanning.py` | 有限重规划器 | 仅处理跳过点与剩余时间变化；保留真实已访问记录，从当前点继续，排除跳过点。 | 不引入新讲解点、不调用 LLM；论文/比较卡不参与选点。 |
| `route_planner.py: plan_from_current_position()` | 从当前位置的剩余路线规划 | 依据原路线顺序和时间预算裁剪剩余点，先删 optional、再删低优先级 core，并保留回前院出口区的路径。 | 只使用已审核边与讲解点目录。 |
| `test_replanning.py` | 有限重规划测试 | 验证跳过点排除、20 分钟缩短路线、入口回退和已访问点不回流。 | 修改重规划规则后必须运行。 |

### P1-11 共享边界：显式当前位置的后续路线候选

- `confirm_replan_and_next` 是既有 P1-11 的合法复合节点，不是 P2 状态接管：必须保持 `apply_replan_proposal → next_stop` 的旧链顺序。2026-08-03 已补齐 `semantic_normalization` 条件映射中遗漏的目标 key；定向 54/54、完整 869/869、P0 3/3 均通过，Studio 操作员验证节点可达、候选只应用一次并输出下一站。未保存完整 Thread ID/Trace URL，必须标记 `manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`。P1-11 confirm_replan_and_next Graph reachability: verified；P2-04-B: not started; prerequisite repaired。
- `TourState.current_stop_id` 仍是唯一物理位置事实；`pending_replan_proposal.origin_node_id` 只允许保存创建候选时的只读快照，不能作为第二位置字段。
- `prepare_remaining_route_proposal()` 只生成候选，不得改写正式路线；`apply_replan_proposal` 是唯一可应用候选的 A1 事件，必须验证 current 与 origin 一致、候选未过期，才原子保留 visited/skipped 并替换 remaining/pending。
- 活跃路线中明确自主到达非 pending 审核点位会先进入 `replan_time_confirmation`，要求游客明确本轮剩余分钟数；不得把初始总时长冒充现场剩余时间。收到可解析时间后才准备路线候选并进入 `replan_route_confirmation`。未知/歧义点位、从头重置和混入完成/跳过/知识问答的多意图必须澄清。
- 含“到达/当前位置 + 从这里重排后续路线”的受控复合命令，必须按“唯一审核解析 → A1 `self_arrival` → 清除旧候选 → 新 `replan_time_confirmation`”执行。未解析或歧义位置必须在 `profile_collection` 和 `direct_route` 前以 `unresolved_replan_origin` 失败关闭；不得借用旧 current、pending 或默认入口。
- 候选展示必须分别呈现物理起点、完整空间路径和正式讲解停靠点；展示前验证 `origin_node_id == current_stop_id` 且 `path_node_ids[0] == current_stop_id`，不得把候选停靠点列表误说成游客当前位置。
- `pending_action_kind` 只允许为 `replan_time_confirmation` 或 `replan_route_confirmation`：第一阶段的“确认新路线”仍只能重申剩余时间请求；第二阶段由统一的 pending-action resolver 按“否定 → 疑问/查看 → 候选 freshness → 确认短语”仲裁。仅有效候选可将“确认新路线 / 使用新路线 / 就按新路线走”等归入 `confirm_replan`；“不确认 / 不要使用 / 继续原路线”等清除待确认动作，问句只展示候选。两阶段的 `next_stop` 均必须被拦截，不能调用正式导航或结束路线。
- 修改上述模块时至少运行 `test_explicit_location_replan.py`、`test_agent_explicit_location_replan.py`、`test_tour_intent.py`、`test_replanning.py`、`test_tour_interaction.py`、`test_tour_navigation.py` 与完整回归。
| `agent_graph.py` 的 TourState 节点 | TourState LangGraph 接入 | `direct_route` 初始化状态；`arrive_at_stop`、`next_stop`、`skip_stop`、`replan_time`、`finish_tour` 全部为确定性节点并在同一 thread 内保留状态。 | 不允许 LLM 直接写 `tour_state`；当前点的详细事实讲解仍留待下一阶段 RAG 编排器。 |
| `test_agent_tour_state.py` | TourState Agent 路由测试 | 验证路线初始化、到达、下一站、跳过、改时间和结束均路由至确定性节点。 | 修改 Agent 意图关键词或节点状态写入后必须运行。 |

TourState 首版字段固定为 `selected_route_id`、`route_stop_ids`、`current_stop_id`、`visited_stop_ids`、`skipped_stop_ids`、`remaining_stop_ids`、`started_at`、`available_minutes`、`remaining_minutes`、`interests`、`detail_level`、`route_status`。`last_arrival_kind` 和 `completion_reason` 为可选审计字段。

后续导游交互、游览中 RAG 问答、讲解编排器、用户画像与知识卡接入的阶段边界见 `TOUR_GUIDE_ROADMAP.md`。任何新增论文卡、比较卡、术语卡或打卡点卡都不得绕过该文档和本文件中既定的 `card_id` / `node_id` 规则。

## A1 交互契约（冻结）

`TOUR_INTERACTION_CONTRACT.md` 是 A1-0 已冻结的唯一事件与状态契约。A1-1 的 `tour_interaction.py`、A1-2 的 `agent_graph.py` 文本路由、A1-3 的按钮/连续导游响应都必须引用它，不得各自定义事件名称、错误码或状态写入规则。

关键兼容调整：A1-1 已废止旧的“到达即已访问”语义。现在统一为“到达 → `explaining` → `confirm_stop_complete()` 后才写入 `visited_stop_ids`”；合法但非 `pending_stop_id` 的到达按冻结契约记录为 `self_arrival`，不改变正式路线顺序。空间主键、路线事实字段和旧路线数据不变。

A1-1 已由项目 `.venv\Scripts\python.exe` 完成本地 62 项回归测试并全部通过。后续修改交互适配层、TourState、导航、重规划或 Agent 游览节点时，至少应复跑 `test_tour_state.py`、`test_tour_interaction.py`、`test_tour_navigation.py`、`test_replanning.py`、`test_agent_tour_state.py` 及路线回归测试。

## A1-2 文本导游意图路由（已实现并验证）

| 文件 | 职责 | 边界 |
| --- | --- | --- |
| `tour_intent.py` | 纯确定性识别：将高置信、单一目的的游客文本转换为 `TourIntentDecision`；只从 `marker_inventory_v0.csv` 解析稳定 `node_id`；同名、多点、未知点和多意图一律澄清。 | 不修改 TourState，不调用 LLM/RAG，不修改空间、路线或知识卡数据。 |
| `test_tour_intent.py` | 覆盖到达、自主到达、事实/导航问句、目的表达、跳过、时间、结束、歧义、多意图、非法事件和伪造 ID。 | 不依赖 DeepSeek 网络。 |
| `agent_graph.py` 的 `tour_event` / `clarification` | 前者只将决策交给 `handle_tour_event()`；后者只回复澄清且不返回 TourState 更新。 | 此层不得直接修改 `current_stop_id`、`visited_stop_ids`、`pending_stop_id`、`stop_phase`。 |
| `test_agent_tour_state.py` | 验证 Agent 优先级与适配层是唯一运行期状态写入口。 | 修改 A1-2 路由后必须复跑。 |

优先级固定为：**明确导游事件 → `tour_intent` → `handle_tour_event`；新路线 → `direct_route`；事实/导航问句 → `direct_rag`；开放对话 → `llm_think`；歧义/多意图 → `clarification` 且状态不变。**

### 验收证据分级与 Trace 元数据债务

交接记录必须分开写明：自动化结果、负责人手动/Studio 功能验证、可追溯的 LangSmith Trace 验证及 Trace 元数据待补。负责人提供输入、节点路径、最终正文和状态观察截图时，可记录 `manual_validation: passed_by_operator`；缺少完整 Thread ID、Trace URL 或 revision ID 时必须记录 `langsmith_trace_status: metadata_unavailable`，不得补造字段或写成 Trace 已验证。若当前 commit、工作区、自动化回归和功能观察均明确且没有已确认失败，这项 evidence debt 可允许后续**只验收**闸门开始；它不能自动放宽生产接管、状态写入、路线 proposal 或事件灰度的独立证据要求。

项目负责人已使用 `.venv` 完成 A1-2 核心 38 项测试与完整 90 项回归，结果均为 `OK`。后续修改 `tour_intent.py`、A1 事件路由或 Agent 事件节点时，至少复跑 `test_tour_intent.py`、`test_agent_tour_state.py` 与 A1-1 的交互/导航/重规划回归。

## A1-3 连续导游展示协议（已实现并验证）

| 文件 | 职责 | 边界 |
| --- | --- | --- |
| `tour_presenter.py` | 纯函数：把适配层响应转为 `message / phase / actions`；每个 `actions[].id` 都是冻结事件，前端按 ID 和参数调用，不解析中文文案。 | 不修改 TourState/交互状态，不调用 LLM/RAG，不生成路线。 |
| `tour_interaction.py: explanation_finished` | 生命周期事件：`explaining → awaiting_confirmation`，只改变交互阶段。 | 不把站点写入 visited，不移除 remaining，不改变路线事实。 |
| `test_tour_presenter.py` | 验证前往、计划内到达、自主到达、等待确认、完成、跳过、重规划、结束、错误和澄清的展示协议。 | 不依赖真实前端或网络。 |

`replan_time` 按钮携带 `input_schema.available_minutes`，前端必须收集整数后才能提交；“再停留一会”没有被冻结事件，因此 A1-3 不提供会改变状态的按钮。

项目负责人已使用 `.venv` 完成 A1-3 相关回归，共 101 项测试均为 `OK`。后续修改展示协议、生命周期事件或 Agent 的 `tour_presentation` 时，应至少复跑 `test_tour_presenter.py`、`test_tour_interaction.py`、`test_tour_intent.py`、`test_agent_tour_state.py` 与路线回归。

## A1-4 端到端验收（已实现并验证）

| 文件 | 职责 | 边界 |
| --- | --- | --- |
| `test_tour_interaction_e2e.py` | 离线串联路线初始化、文本意图、Agent 路由、`handle_tour_event()` 与展示协议，验收完整导游状态闭环。 | 不调用真实 LLM、RAG 或前端；不新增事件或修改空间/路线/知识卡数据。 |

该测试覆盖计划内到达、`explanation_finished`、确认完成、最后一站、自主到达、跳过后重规划、歧义/多意图/未知点位拒绝、详情占位和幂等性。项目负责人已完成完整 141 项本机回归，结果均为 `OK`；A1 因此正式完成。A2 的游览中 RAG 问答与导游恢复仍未开始。

## A2 游览中 RAG 问答与上下文恢复（已实现并验证）

| 文件 | 职责 | 边界 |
| --- | --- | --- |
| `tour_qa.py` | 对“当前点/明确点有什么”确定性读取讲解包清单；对工艺、寓意、故事等解释性问题用点位提示调用既有 RAG，随后恢复 A1-3 展示协议。 | 讲解包只证明已审核“文物—点位关联”；文化和工艺解释仍只能来自 RAG evidence。不得修改 TourState。 |
| `test_tour_qa.py` | 验证当前/明确点位清单、点位文物讲解、一般事实、`self_arrival`、无活动路线、无证据、缺包、未知点与检索异常。 | 只使用 mock/注入函数，不调用真实模型或网络。 |
| `test_agent_tour_qa.py` | 验证活动路线走 `tour_qa`、无路线仍走 `direct_rag`、到达仍走事件、问答后可继续 A1。 | 不改路线数据、空间边或知识卡。 |

`agent_graph.py: tour_qa_node` 复用 `chen_clan_academy_rag_search` 处理解释性事实问答；明确点位清单即使无活动路线也可确定性读取已审核讲解包。它不返回 `tour_state` 或 `tour_interaction_state` 更新。A2 不接入论文、比较、术语或打卡卡，也不实现点位讲解编排器。

### A2 当前点工艺特点修复（待本机验证）

“这里/此处/眼前 + 工艺 + 特点”必须走 `tour_qa.answer_current_point_craft_features()`：先由 `current_stop_id` 读取当前卡片的同工艺审核实例，再分别检索工艺总述和每个实例；仅名称命中实例的 evidence 才能作为该实例解释。没有该工艺时返回 `current_craft_absent`，不调用全库 RAG 补造现场实例。全馆问题（如“陈家祠灰塑有什么特点”）不带指代词，保持基础 RAG。此分支仍不返回 TourState 更新。

项目负责人已完成 A2 相关 106 项回归和完整 155 项本机回归，结果均为 `OK`。后续修改点位讲解包读取、`tour_qa.py` 或 Agent RAG 路由时，至少复跑 `test_tour_qa.py`、`test_agent_tour_qa.py`、`test_agent_tour_state.py`、`test_agent_rag.py`、A1 E2E 与 RAG/路线回归。

## B1 点位讲解编排器基础（已实现并验证）

| 文件 | 职责 | 边界 |
| --- | --- | --- |
| `guide_program_planner.py` | 根据审核 `node_id`、预算、兴趣和详略等级确定性产出 `StopProgram`，每件对象带角色、秒数、理由和 `rag_query_hints`。 | 不调用 RAG/LLM，不写 TourState，不改变路线；研究/比较卡字段固定为空。 |
| `test_guide_program_planner.py` | 验证候选合法性、稳定性、兴趣排序、1–3 件限制、未知点、空候选与输入校验。 | 使用讲解包或 mock 卡片，不修改原始数据。 |

`tour_qa.load_guide_cards()` 已提升为可复用只读加载函数，供 A2 和 B 阶段使用。B1 的 `planned_seconds` 是预算的可审计基础分配；观察、互动、内容多样性和更细时间优化属于 B2。

项目负责人已完成 B1 相关 112 项回归和完整 161 项本机回归，结果均为 `OK`。后续修改编排器或讲解包加载接口时，至少复跑 `test_guide_program_planner.py`、A2 测试、路线测试与完整回归。

## B2 StopProgram 时间预算与内容排序（已实现并验证）

| 文件 | 协作职责 | 边界 |
|---|---|---|
| `guide_program_planner.py` | `STOP_PROGRAM_POLICY` 集中配置讲解内容预算阈值、兴趣权重与多样性规则；按已审核候选生成 B2 StopProgram。 | `budget_seconds` 仅是单站讲解内容预算，不读取、不扣减步行时间，不改路线、空间图或知识卡。 |
| `test_guide_program_budget.py` | 覆盖预算边界、兴趣优先、多样性、稳定输出和超时保护。 | 离线 mock 测试，不调用 LLM/RAG。 |

`StopProgram` 新增 `budget_scope`、`allocated_content_seconds`、`unallocated_content_seconds`，用于审计时间：三者明确区分站内讲解内容时间与路线步行时间。后续 B3 只能用已选对象的 `rag_query_hints` 取证；不得扩大候选来源。

项目负责人已于本机运行完整回归：166 项、1.740 秒、结果均为 `OK`。

## B3 StopProgram 取证与 Agent 点位讲解（已实现并验证）

| 文件 | 职责 | 边界 |
|---|---|---|
| `guide_program_evidence.py` | 读取本站内容预算，调用 B1/B2 生成 StopProgram，并按每件对象的 `rag_query_hints` 调用既有 RAG；仅以返回 evidence 编排讲解。 | 不新建索引，不改路线、空间图、知识卡或 TourState。 |
| `agent_graph.py: stop_guidance_node` | 在计划内到达、或 `request_stop_detail` 成功后触发 B3；保存审计用 `active_stop_program` 和展示结果。 | 不返回 `tour_state` / `tour_interaction_state` 更新。 |
| `test_guide_program_evidence.py` / `test_agent_stop_guidance.py` | 覆盖取证、无证据、异常、自主到达拒绝、Agent 路由与详情展开。 | 使用 mock RAG，不访问网络。 |

`request_stop_detail` 的状态语义保持无副作用，返回码由 `detail_placeholder` 更新为 `detail_requested`：适配器成功后才由 B3 产生展开讲解。`explanation_finished` 仍须由游客或 UI 显式触发，B3 绝不自动完成站点。

项目负责人已完成完整 173 项本机回归，耗时 1.775 秒，结果均为 `OK`。

### B3.1 游客讲解渲染（待本机验证）

| 文件 | 职责 | 边界 |
|---|---|---|
| `guide_narration.py` | 将审核 StopProgram 与逐件 RAG evidence 渲染为游客讲解；内部调度字段和完整 evidence 保留在结构化结果。 | 默认确定性输出；可选 narrator 只接收审核对象与 evidence，不合规输出回退。 |
| `test_guide_narration.py` | 验证不泄漏路径/内部字段、详讲不同于标准讲解、无截断句和 LLM 回退。 | 不调用真实 LLM。 |

游客文本只显示简洁 `source_ids`，不显示文件路径、原始 chunk、角色或计划秒数；`guide_program_evidence.py` 仍返回完整 `evidence`、`evidence_by_item`、StopProgram 和来源 ID 供审计、LangSmith 与后续 UI 使用。

## B4 阶段 B 端到端验收（待本机与 LangSmith 验证）

| 文件 | 职责 | 边界 |
|---|---|---|
| `test_stage_b_e2e.py` | 离线串联路线初始化、到达、StopProgram、B3 取证、A2 插入问答、恢复讲解、显式结束讲解和确认完成。 | 使用 mock RAG；不调用真实模型、网络或前端。 |

验收要求：选物不得越出本点审核清单；所有详略等级的分配不超本站内容预算；兴趣只改变 StopProgram 优先级、不改变路线；无 evidence 与空的未来知识卡接口仍可安全完成基础导览。B4 通过本机回归后，仍须在 LangSmith 核对真实节点顺序和状态边界。

人工填写 `route_review_results_v1.csv` 时：`manual_status` 只能填 `approved`、`revise` 或 `rejected`；其余四个判断列填 `yes`、`no` 或 `needs_site_check`。只填写人工列，不改自动生成的路径、时间、点位和边字段。

动态路线 A0 的开发顺序固定为：候选过滤 → 点位评分 → 时间预算组合 → 评估集 → Agent 接入。论文卡、比较卡尚未参与 A0 评分；后续只可通过已审核 `card_id` 增加可解释加分项。

## 新卡片统一接入规则

每张新卡必须有稳定 `card_id`、中文标题、来源、核验日期、适用范围和状态。

```json
{
  "card_id": "research_001",
  "title_zh": "示例中文标题",
  "status": "reviewed",
  "source": {"citation": "作者，年份，题名"},
  "verified_at": "YYYY-MM-DD",
  "applicable_node_ids": ["label_moon_platform"],
  "summary": "可追溯的简要内容"
}
```

关联到点位时，只填 `node_guide_cards_v1.json` 中对应的 ID 数组：

- 学术摘要：`research_summary_card_ids`
- 比较卡：`comparison_card_ids`
- 术语卡：`term_card_ids`
- 打卡点卡：`photo_spot_card_ids`
- 多语言术语：`glossary_ids`

研究、比较、术语和术语表默认只增强讲解，不改变路线。打卡点卡只有在安全、秩序、开放限制、停留时间均审核完成后，才可以设置为路线可选点。

## 更新与交接流程

1. 在各自目录新增卡片文件或数据表，不覆盖他人文件。
2. 为卡片填写 `applicable_node_ids`，只能使用 `marker_inventory_v0.csv` 中已有的 `node_id`。
3. 由路线负责人把已审核 `card_id` 填入 `node_guide_cards_v1.json` 的扩展数组。
4. 新卡片含事实时，补充对应 RAG 评测用例；新卡片只含学术观点时，明确“研究观点”而非馆内事实。
5. 每次合并前运行本模块测试，并在提交信息中说明新增卡片数量和数据来源。

## 当前路线阶段验收命令

```cmd
python -m unittest -v test_spatial_graph.py test_route_planner.py test_node_guide_cards.py test_agent_profile.py
python inspect_route_plan.py highlights_30
python inspect_route_plan.py crafts_60
python inspect_route_plan.py deep_dive_90
```

路线 v1 已能输出 30/60/90 分钟的确定性路线；下一阶段是记录已访问点、当前点位讲解、跳过点和重规划。

## 已审核位置提示（B3.1）

- `ornament_spatial_mapping_v1.csv` 是文物—点位位置关联的审核来源；只有 `mapping_decision=change/add_node` 且 `final_node_id` 一致的数据，才能进入点位讲解包和现场观察提示。
- 运行 `build_node_guide_cards.py` 会把 `raw_location` 与映射审计字段重新生成到 `node_guide_cards_v1.json`；不要手工编辑 JSON 或 CSV。
- `raw_location` 只能生成“请先看向【具体位置】……”式观察提示，不是导航指令；不得据此补充左右、高低、可达性、光线或遮挡等未审核现场事实。
- 位置文本不得进入 StopProgram 评分或排序。若讲解包保留非兴趣工艺对象，必须使用 `role=工艺对照` 与非空 `comparison_reason`，以便展示层说明其对照目的。

## C 阶段游客画像接口（C1/C2/C3/C5 已完成本机验证；C4 待 LangSmith 验证）

- `visitor_profile.py` 是唯一的画像校验与归一化入口。活跃字段为 `available_minutes`、`interests`、`detail_level`；默认仅用于 C1 纯模型，不能被误称为游客明确表达。
- `profile_dialogue.py` 只保存一个 `VisitorProfile` 与“哪些字段已明确解决”的收集元数据；不复制活跃字段，不写 TourState，不调用路线规划或 StopProgram。
- C5 将旧的模糊 `visitor_type` 拆为四项明确的当次参观偏好：`audience_mode`、`knowledge_level`、`explanation_style`、`interaction_mode`。它们均为受限枚举、仅由用户选择/确认；默认值仅表示中性策略，不表示系统识别了游客身份。
- `language`、`photo_preference`、`accessibility_need` 仍是可选接口。当前不得从对话推断、主动追问或参与评分；不得新增年龄、性别、收入、疾病或关系判断等敏感字段。
- `visitor_type` 不再是新建或更新画像的合法字段；读取含它的历史会话快照时仅为兼容而丢弃，不映射为 `family`、`study` 等任何 C5 值。C5 全部数据仅在当前 LangGraph 会话状态中保存，尚不跨会话持久化。
- C5 暂不改变路线、TourState 快照、StopProgram 或讲解生成；C6/C7 才可在明确验收后读取这些字段。
- 项目负责人已完成 C5 目标测试与完整回归，结果均为 `OK`。C5 不需要真实模型调用；C4 的真实多轮 LangSmith 状态检查仍待完成。
- C6 的唯一策略入口是 `guidance_policy.build_guidance_policy(profile)`。它只输出确定性 `GuidancePolicy`，不得读取知识卡、RAG、路线或 AgentState，更不得修改画像。C7 接入时必须遵守 `fact_evidence_required=True` 和 `budget_cap_mode=min_with_stop_budget`。
- 项目负责人已完成 C6 目标测试与完整回归，结果均为 `OK`。当前不得绕过 C7 直接在 Prompt、Agent 或讲解文本中手写同类策略规则。
- C7 只允许 `guide_program_evidence.build_stop_guidance()` 将 C6 策略传给 `plan_stop_program()` 与确定性讲解渲染。每次生成的策略副本保存在 `active_stop_program.guidance_policy` 供审计；它不是第二份画像，也不得写回或修改 TourState。知识卡开关目前仅审计输出，不触发读取。
- 项目负责人已运行 C1/C2 目标测试及完整 226 项回归，结果均为 `OK`。C3 才可将已验证的画像显式复制为 TourState 的本次游览快照；C4 才处理游览中变更。
- C3 中 `direct_route` 只读取已校验的 `visitor_profile`；路线成功初始化时调用 `start_tour(...)`，将同一份 `available_minutes`、`interests`、`detail_level` 固化为 TourState 快照。StopProgram 只能读取该快照，不能回读 `visitor_profile`。项目负责人已完成 C3 目标测试、路线/交互/讲解回归与完整回归，均为 `OK`。
- 兼容旧的直接函数调用时，允许从原有文本提取结果构造一次性默认 `standard` 画像；它不增加第二套持久画像存储。画像或路线初始化失败时不得写入半份 `tour_state` 或 `active_route_plan`。
- C4 的唯一更新适配层是 `profile_update.py`。它复用 C2 的提取规则和 C1 的不可变更新：时间变化先通过 `handle_tour_event(..., "replan_time")`，只有成功后才用 `apply_profile_snapshot()` 同步画像和 TourState；兴趣、详略只同步快照，绝不重置已访问、跳过、当前位置或路线顺序。
- `profile_update_node` 是 Agent 的确定性入口。LLM、RAG、展示层与前端均不得直接写 `visitor_profile` 或 TourState。含到达/跳过/确认等控制操作与偏好更新的同一句输入必须澄清，不得部分执行。
## C8 显式扩展偏好控制（待本机与 LangSmith 验证）

- `extended_profile_control.py` 是扩展画像文本控制的唯一适配层；只能处理明确表达，输出结构化 patch 后复用 `visitor_profile.py` 校验。不要在 Agent、Prompt 或前端手写第二套规则。
- 该控制层不修改路线、空间图、TourState、RAG evidence 或已审核卡片。删除会话偏好时只能清空 `visitor_profile` 与 `profile_collection`，不得清空正在执行的 TourState。
- 显式重讲当前内容只能复用 `active_stop_program` 与 `active_guidance_evidence_by_item`，不得重新选物或补造检索事实。

## C9 会话记忆边界（待本机与 LangSmith 验证）

- `messages` 是对话上下文；`visitor_profile` 是当前会话偏好；`tour_state` 是实际游览进度；`active_route_plan` 和 `active_stop_program` 分别是路线与当前站编排。不要把这些字段写入新知识卡数据。
- 本地 `MemorySaver` 仅按 `thread_id` 隔离会话内状态；它不是持久化数据库。服务重启和新 thread 均不承诺保留画像、路线、讲解包或检索证据。
## D1 异构知识卡注册接口（待本机验证）

- `knowledge_card_contract.py` 是 D 阶段统一只读视图；`knowledge_card_registry.py` 是唯一跨类型注册与资格门控层。原卡的 ID、正文、文件格式和各自 retrieval 模块均不得因 D1 修改。
- 注册表只允许读取，禁止写入 TourState、VisitorProfile、路线、StopProgram 或 RAG index。后续接入必须仍调用本注册表门控，不能因为原卡存在就绕过资格清单。
- 平台观察 `platform_observation` 可保留内部审计记录，但 `visitor_visible=False`，不得出现在游客端查询结果。

## D2 术语卡运行接口（待本机验证）

- `term_card_runtime.py` 是游览中术语型问题的唯一适配层：必须经 D1 注册表取得 `glossary_term`，不得直接绕过运行资格清单读取 YAML。
- `glossary_retrieval.py` 与 `term_stop_associations_v1.json` 只可作为候选排序提示；不得据此声明某术语或文物“眼前一定存在”。术语的现场位置、年代、故事和历史事实仍需基础 RAG 的证据。
- `en_translation` 是独立能力门控。翻译草稿、禁用卡、缺失卡和损坏文件不得输出英文猜测；可安全回退原有基础 RAG，或在英文草稿场景明确拒绝输出。
- 比较、研究、打卡、到达和路线事件不得由 D2 术语识别器抢占。TourState 与 `active_stop_program` 只能由既有确定性事件/编排流程写入。

## D3 研究摘要卡运行接口（待本机验证）

- `research_card_retrieval.py` 必须从 D1 注册表获取研究卡；不得根据原始 JSON 的 `status=reviewed` 直接开放，也不得读取本地 PDF 作为游客端事实来源。
- D3 只处理明确研究意图，优先级高于 D2 术语但低于到达、确认、跳过等游览事件；含比较语义的问题必须留给 D4，不能由 D3 以论文摘要替代比较结论。
- 研究摘要只能以归因观点呈现，并同时展示卡片限制。基础 RAG 仍负责地点、年代、位置、数量和故事等稳定事实；D3 不得写 TourState、VisitorProfile、路线或 StopProgram。

## D4 比较卡运行接口（待本机验证）

- D4 只能调用 `comparison_retrieval.retrieve_gated_comparison()`；它从 D1 注册表取得比较卡，禁止把 `comparison_cards_v0.yaml` 直接作为游客端运行入口。
- 普通比较不允许读取研究专用卡，只能回退基础 RAG；明确研究比较，或 `audience_mode=study` / `knowledge_level=professional` 的明确比较，才可使用一张 `attributed_only` 主卡并保留范围和限制。
- 比较对象必须由当前输入明确给出；“它们”没有可靠对象时只请求澄清。`on_site_observation_prompt` 是观察建议，不是当前位置可见性或导航事实。D4 是只读问答，不写 TourState、StopProgram 或画像。
## D5-B 打卡卡编辑推荐接口（待本机验证）

- `photo_spot_validation.py` 是 D5-B 唯一的轻量候选门控。体验资格清单的 `runtime_status=enabled` 表示可供项目编辑选择，不表示完整现场审核或游客端通用知识卡资格。
- 候选必须具有合法节点、完整姿势/平台/证据引用、非禁用姿势、卡片与姿势安全边界、以及可核对的对象—点位关联；断裂、禁用、缺边界和文件异常一律失败关闭。`partial/pending` 本身不阻断 Demo 推荐，但结果必须附带现场条件提示。
- `query_registered_cards()` 永不返回 `photo_spot_card`、`pose_template`、`platform_observation`。未来 D6 只能通过 `query_available_photo_spots(node_id, audience_mode, themes)` 读取编辑候选；姿势只能由选中打卡卡间接返回，平台观察永远仅内部审计。
- 专用结果只含安全的结构化选择信息、姿势安全边界和限制，不原样输出混合型 `recommended_capture_zh`。`editorial_recommended` 只能称为“项目编辑建议”，不得称热门、最佳、馆方推荐或已现场核验。

## D6 打卡问答接口（待本机验证）

- `photo_spot_runtime.py` 是 D6 的确定性意图、排序与渲染层；它只能调用 D5-B `query_available_photo_spots()`，不直接读取打卡 YAML、姿势 YAML 或平台观察。
- 顶层 A1 控制事件、画像更新与路线请求优先；进入 `tour_qa` 后，明确拍照请求先于比较、研究和术语。拍照与修改路线同句必须澄清，D6 不能新增路线点或写入任何游览状态。
- 专用输出最多三处候选，只返回间接姿势和安全边界；不得输出原始卡 ID、平台观察、混合拍摄草稿、热门/最佳/馆方认证等表述。无可靠当前点的“这里怎么拍”必须要求位置，不得猜测。

## D7 统一验收矩阵与冻结边界（待本机与 LangSmith 验证）

- 统一验收文件为 `data/chen_clan_academy/evaluation/d_stage_acceptance_cases_v1.yaml`，测试入口为 `test_d_stage_acceptance_cases.py`。不得改写既有 `dst_acc_001`--`dst_acc_017` 的含义或编号；新增场景应追加新编号，并说明其对应的 D 子阶段。
- 每条记录必须保留输入、前置 TourState、前置 VisitorProfile、预期路由、预期卡片类型、必须/禁止文本、允许状态变化、预期来源类型和人工审核状态；它不是知识卡正文副本。
- D2--D6 问答案例的 `allowed_state_changes` 必须为空。只有 A1 导游事件案例可声明交互状态变化；到达仍不能直接写 `visited_stop_ids`。

## E1 协作基线（已验证，等待交接提交）

- `D_STAGE_BASELINE.md` 是 D 阶段共同起点的唯一索引。功能提交为 `079a1f1`；项目负责人已确认本机完整回归 `374 / 374 / 0` 与固定 LangSmith 场景全部通过。`handoff_commit` 将由 E1 交接提交写入。
- E1 通过后，两位队友必须从同一 `handoff_commit` 创建 `codex/content-experience` 和 `codex/platform-productization`，不得从各自旧分支继续。开始前须报告本地提交、目标基线提交、工作区状态和未提交修改。

## E4-3 时长解析共享边界

- 所有中文/阿拉伯数字导览时长的识别必须调用 `duration_parser.py` 中的公共函数；禁止在 Agent、画像收集、路线规划、重规划或 UI 层重新复制正则与数字转换规则。
- 解析与业务语境分离：`parse_duration_minutes()` 仅返回显式分钟值或歧义；`has_route_duration_context()` 与 `has_remaining_duration_context()` 决定是否可用于启动路线或更新剩余时间。最终范围校验仍由 `VisitorProfile` 与既有路线策略负责。
- 新增时长表达、上下文或产品范围时，须同时补充解析器单测和路线/游览中集成测试；不得用 LLM 推断不明确的时长。

## E4-3B 路线选择共享边界

- 兴趣覆盖证据只能来自路线实际 `guide_stop_ids` 的点位讲解包对象；对象必须满足 `final_node_id == guide_stop_id` 且 `mapping_decision in {change, add_node}`。路线标题、`themes`、`guide_focus` 和 LLM 推断均不得单独形成兴趣覆盖。
- `node_guide_cards_v1.json` 是两阶段生成文件：`build_node_guide_cards.py` 生成路线评分所需的基础对象投影，`build_term_stop_associations.py` 随后回写术语 `glossary_ids`。修改审核空间映射后，必须重新运行基础构建，并通过“路线对象投影与已提交卡片一致”测试；不得将术语回写字段误作基础构建过期。统一为单一构建流水线是后续技术债。

- `route_selection.py` 是路线初始化时唯一的锚点/动态候选选择器。禁止重新引入“模板标题主题优先”或“精确时长强制锚点”的分支。
- 新路线必须严格满足 `estimated_total_seconds <= available_minutes * 60`。不得以 10% 容忍、显示时四舍五入或模糊警告掩盖超时；无合格候选必须返回可审计的无路线结果。
- 严格预算是候选资格层；`time_utilization` 只负责在合格候选间表达“保留现场余量”的偏好。两者不得把刚好用满预算的合格路线重复惩罚为不可用。

## E4-4B 问答上下文共享边界

- `qa_context` 是单线程、单轮受控追问的检索条件，不是游客真实位置、长期画像或 RAG 证据缓存；不得写入 TourState、VisitorProfile、StopProgram 或知识卡。
- 只有成功的结构化点位回答、或带 RAG evidence 的点位解释可创建 `qa_context`；失败、澄清和无证据解释必须清除它。
- 显式点位只限定该轮/追问的问答范围；“这里/此处/本点”始终以 `TourState.current_stop_id` 为准。
- A1 的 `request_stop_detail` 只展开当前正式讲解点；远程点位问答的展开必须走只读 `qa_follow_up_detail`，不得改变事件契约。
- 兴趣覆盖只能由候选实际停留点的已审核点位—文物—工艺关联派生。不得为路线选择新增独立手工标签库，也不得由 LLM 推断覆盖关系。
- `detail_level` 是选择器和动态每站预算的输入；TourState 的到达、完成、跳过、重规划语义仍完全由 A1 事件层控制。

## E4-5B 知识子路由共享边界

- 比较卡只有在用户本轮明确命中卡片双方审核比较对象时才可使用；单对象、主题或维度命中必须回退基础 RAG，不能拼接或替代缺失对象。
- 研究意图没有 D1 合格的直接匹配卡时必须显示为基础资料回退，并保留 RAG 来源；不得把相关但不精确的研究摘要作为答案。
- 明确点位概览与当前点工艺问答均以对应 `node_guide_card` 为硬范围。显式点位不改变物理位置；“这里”只使用 `TourState.current_stop_id`。
- “危险动作 + 拍照 + 受保护构件”在顶层安全优先处理，不得先执行到达、查询打卡候选或写入游览状态。普通构件事实问题不应误触该拒绝。

## E5-0 证据驱动讲解质量契约（冻结）

- 统一契约见 `E5_NARRATION_CONTRACT.md`。E5 引入的 `NarrationCoverage` 只记录本线程、本次游览中已经成功输出且带 evidence 的工艺/文物介绍；它不是 TourState、VisitorProfile、知识事实或 RAG 原文缓存。
- 首次工艺优先使用 `07_ornament_crafts.md` 的 evidence，首次文物优先使用 `08_ornament_items.md` 的 evidence，并只能连接当前点讲解包中审核关联的对象。预算不足时减少对象数，不减少核心证据链。
- E5-A、E5-B、E5-C 必须从同一 E5-0 提交建立分支；主负责人独占修改本文件、进度报告和学习说明。具体文件所有权、失败关闭规则与 `e5_nar_001`--`e5_nar_008` 验收编号均以契约为准。
## Gate 3 共享边界：P2 Shadow / 只读集成（已验收）

- P2-01、P2-02、P2-03、P2-04-A、P2-04-B 仅可作为 `shadow` 审计；P2-05 仅按其已冻结的受控只读灰度契约运行。不得将其称为、或配置为状态类 active takeover。
- 所有 `*_evaluations` 仅是当前 thread checkpoint 中的有界审计数据。它们不得参与游客渲染，不得作为 TourState、VisitorProfile、正式路线或 proposal 的事实源。
- Shadow 不得重新调用路线选择器、重规划器、`handle_tour_event()` 或工具执行器。旧 Graph/P1-11/A1 是唯一执行权来源；`confirm_replan_and_next` 的合法复合旧序列仍是 `apply_replan_proposal → next_stop`。
- Gate 3 自动化为 66/66 定向、877/877 完整回归、P0 3/3；人工四组功能操作已通过。Trace 元数据未保存时必须记为 `metadata_unavailable`，不得补造链接或 ID。
- 若后续希望启用任何 active 行为，必须先取得独立授权、重新定义能力级准入与回滚方案；Gate 3 不构成该授权。

## P1-12C1 共享边界：到达控制护栏

- `tour_intent.looks_like_arrival_control(text)` 只判断输入是否属于游客位置变化控制形态；它不得生成 `node_id`、不得绑定 pending、不得写任何状态。A1 仍是唯一到达写入口，审核点位仍只由 `resolve_reviewed_node()` 解析。
- 该护栏为真但 `is_safe_arrival_report_text()` 不通过时，入口必须走结构化澄清，禁止回退 `llm_think`、`direct_rag`、`tour_qa` 或 RAG。仅时间条件的知识问句（如“到达月台后能看到什么”）不得被护栏拦截。

## P1-12C4 共享边界：下一站控制

- `request_next_stop` 是闭合控制候选，只能保存原话证据与置信度；不得携带或生成 `node_id`、路线、路径、导航文案或状态修改。实际导航仍由 A1 事件适配器、已应用路线与审核空间图决定。
- `replan_time_confirmation` 与 `replan_route_confirmation` 优先于下一站控制；`explaining` 和 `awaiting_confirmation` 也不得由“下一个”隐式完成站点。无法安全执行的控制表达必须走结构化澄清，禁止回退 `llm_think`／RAG 自由导航。
- 新增下一站同义表达或语义候选时，必须同时覆盖：无活跃路线、两类重规划等待、讲解中、已确认新路线和跨线程隔离；不得改变“只有确认完成才写入 visited”的 A1 契约。

## P1-13/P1-16 共享边界：票务与服务公开渲染

- `controlled_knowledge_query.is_public_visitor_message()` 是 P1-21 的公共游客文本门控。新增游客渲染器必须复用它；文件名、`Sxx`、本地快照/知识库描述、原始 chunk、URL、内部 ID 与检索字段只能保留在结构化 evidence 或 Trace，不能写入 `visitor_message`。
- 无法出示实体身份证但询问入馆时，统一复用 `identity_admission_workaround` 的已审核替代流程；不得从“丢失”字样推导没有替代方式或机械建议电话咨询。没有电子身份证和其他有效证件时只说明需现场核验，不保证可入馆。
- 身份证挂失、补办、补领不是场馆票务事实。它们必须返回公安政务边界说明并跳过场馆 RAG；与入馆同问时澄清先处理哪一项，不能把两类流程混写。

## P1-20 共享边界：对象故事与工艺总述

- `07_ornament_crafts.md` 只能提供工艺层事实，不能支撑命名对象的传说、人物或情节。
- 明确对象故事必须复用对象级身份解析与 `08_ornament_items.md` 严格证据门控；不得在 Agent、RAG 或渲染器各自创建第二套对象匹配规则。
- 游客明确限定“只根据某工艺”时，必须先澄清证据范围不足；不得隐式查询对象资料、调用 LLM 或以其他对象内容补齐。
- 可保留接受/拒绝证据的结构化审计，但游客文本不得展示内部路径、来源编号、对象或节点标识。
- 同名候选可按审核名称、工艺、点位与公开位置分组；只有审核实体关系明确为 canonical/alias 时，才可在构建期归一为一个游客候选。`orn_051/orn_052` 已由项目负责人确认同一物理实体：`orn_051` 为 canonical，`orn_052` 为保留审计的 alias，不投影为运行对象。其他无此审核关系的同字段对象仍必须 `ambiguous_group` 失败关闭。
- P1-20 已于 2026-07-31 标记 `verified_fixed`：LangSmith 新线程验证了木雕 canonical 选择与显式木雕直答；当次 thread/Trace 标识未记录，后续验收必须在运行记录中保存真实标识，不能补写虚构链接。

## P0-03 / CA-00 共享边界：Gate 0 行为冻结

- 当前自动化基线为 `main@56688f7`：完整回归 `770/770`、P0 安全/游客输出矩阵 `59/59`；矩阵事实源为 `data/chen_clan_academy/evaluation/p0_gate_0_behavior_matrix_v1.yaml`。
- 后续 P1 架构工作不得改变 TourState 的 A1 事件写入边界、VisitorProfile 的受控更新边界、审核路线/空间事实源，或让控制语句回落到 `llm_think` / `rag_tool`。
- 游客正文必须继续隐藏内部来源、ID、路径和评分；结构化证据必须保留在审计字段和 Trace。
- 当前 Gate 0 为 `conditional_pass`，不是 `passed`：补齐当前提交的 LangSmith 记录并处理/保持外部数据阻塞后，负责人才能授权进入 AgentDecision、Tool Registry、Policy Gate、Executor 或 Shadow Planner。
# P2-01 Shadow 证据分级

P2-01 `fa1e00f` 已完成功能与自动化验收：定向 46/46、完整 841/841、P0 8/8。负责人 Studio 截图记录了 Thread `019fc3b7-67ea-77d2-8131-6a3b93a7fcd3` 的 `atomic_read_plan` 候选，但未保存 Trace URL/revision 或逐字段状态 diff。因此协作中必须写为 `functional_validation: passed`、`manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`，不得伪造 Trace 或说状态 diff 已被人工完整复核。该 evidence debt 允许后续只读验收继续，不允许开启 P2-01 active、路线 proposal 或状态事件接管。

# P2-02 Shadow 证据分级

P2-02 `d0b61e0`/`44235c3` 已通过定向 55/55、完整 852/852 与 P0 8/8。负责人 Studio 截图记录了 30/60 分钟 accepted 且 `matches_legacy=true`，以及 10 分钟的 `invalid_profile_value` reject；完整 Trace URL/revision 与逐字段状态 diff 未保存。协作中必须记为 `functional_validation: passed`、`manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`。该状态只允许 Shadow 归档与后续只读验收；不允许 P2-02 active、自动确认路线或状态事件接管。

# P2-03 Shadow 证据分级

P2-03 `09a85c8`/`334ea7a` 已通过人工与自动化验收：当前完整回归 860/860、P0 3/3。Studio 显示月台补充 40 分钟后的旧 P1-11 proposal 被 Shadow 审计为 `accepted`、`matches_legacy=true`；未知位置保持旧澄清；取消后为 `legacy_proposal_absent`。未保存完整 Thread ID、Trace URL/revision 或逐字段状态 diff，协作中必须写为 `functional_validation: passed`、`manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`。P2-03 只允许 Shadow 归档；不允许 active、自动应用 proposal 或接入 P2-04 状态写入。

# P2-04-A Normal Event Shadow 证据分级

P2-04-A `92ca888` 已通过定向 24/24、完整 867/867 和 P0 3/3。Shadow 对普通 tour event 只运行纯 dry-run，再将建议与唯一一次旧链执行结果对照；不得调用状态写入器或形成第二份 TourState。负责人 Studio 操作确认 arrive、explanation_finished、confirm_stop_complete、skip、next_stop、finish 均为 accepted，并显示 `legacy_execution_observed=true` 与 `legacy_result_matches_shadow=true`。没有保存完整 Thread ID、Trace URL/revision 或完整状态 diff，因此协作中必须写为 `functional_validation: passed`、`manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`。只允许 Shadow 归档；P2-04-A active disabled，P2-04-B 重规划复合事件审计尚未开始。

# P2-04-B Replan Composite Shadow 证据分级

P2-04-B 只读审计旧 P1-11 的 preparation、proposal、确认、合法 `apply_replan_proposal → next_stop` 复合操作和取消；审计本身不得调用 `handle_tour_event` 或成为第二状态源。自动化为定向 5/5、关联 66/66、完整 874/874、P0 3/3。负责人 Studio 已观察到复合确认 accepted、正式路线变化和 contract match，取消仍保留原路线；完整 Thread ID/Trace URL/revision 未保存，必须写为 `functional_validation: passed`、`manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`。P2-04-B active disabled；Gate 3 等待最终 P2 集成验收。

# P3 前置审计协作边界

P3 从 `experiment/agent-orchestration-v2@9d744d3` 开始，P2 Gate 3 的结论仍仅是 Shadow／只读集成通过；路线、重规划、到达、完成、跳过、下一站和结束的 active takeover 均未获授权。协作者不得因 P2 审计字段存在而将其作为新的状态、路线、proposal 或游客输出事实源。

P3-02 已核实复用现有的 `GuidancePolicy → NarrationStylePolicy → narration_rendering` 单链，不应新建风格状态或复制 VisitorProfile。下一项 P3-01 / CA-12 必须由负责人先冻结 `tour_mode` 的唯一归属、生命周期与问答打断恢复。未获决定前，不实现 CardDispatcher、经典/定制选择或新的 active Graph 接管；完整拆分见 `data/chen_clan_academy/evaluation/handoffs/p3_preflight_audit_handoff.md`。

# 角色讲解预算质量门协作状态（2026-08-10）

角色预算失败注入只允许修改非权威 `NarrationContentPlan` 副本，不得改 E5 审核渲染、路线、TourState、VisitorProfile 或 Coverage。拒绝候选在 Shadow 中应明确记录 `fallback_used=true`，因为游客实际继续看到旧链正文；这不表示发生 Active 接管。

角色自然语言识别仍是确定性、闭合目录匹配：“古风一点”和“适合孩子/小朋友”等审核表达只映射到既有 style ID。多个角色必须按 `style_roles_v2.yaml` 顺序形成 clarification；上一轮已选角色只能作为只读 Shadow 上下文继承，不得写入 VisitorProfile。当前定向 73/73、P0 3/3、完整回归 1095/1095 通过，Active 继续关闭。

# 比赛版角色 Shadow 抽样协作状态（2026-08-10）

18 风格不再执行完整人工矩阵。自动化覆盖通过后，只以七个高风险风格的
审核点位样本作为比赛门槛；当前 `7/7 passed_by_operator`，完整回归
`1101/1101`。未保存 Thread/Trace 的样本必须继续标记
`trace_metadata: unavailable`。候选首次拒绝、随后新线程通过时，两次结果都应
记录；不得把安全 fallback 隐藏成首次成功。该归档只授权进入角色问答
Shadow，不授权任何 Active。
