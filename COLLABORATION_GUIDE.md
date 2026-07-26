# 陈家祠金牌导游 Agent：多人协作公共说明

本文件面向当前三人协作。目标是让不同知识库可以独立建设，并通过稳定 ID
接入同一 Agent；不要直接修改彼此模块的事实内容或空间主键。

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
| `test_tour_state.py` | 游览会话状态测试 | 验证初始化、到达、下一站、跳过、重复到达、完成与未知点位拒绝。 | 修改状态字段或转移规则后必须运行。 |
| `tour_navigation.py` | 下一站确定性导航器 | 从 TourState 找到下一个剩余讲解点，调用已审核空间图输出节点、边、步行时间与该点 `guide_focus`。 | 不修改 TourState；不调用 LLM、RAG 或重规划器。 |
| `test_tour_navigation.py` | 下一站导航测试 | 验证入口起步、到达后推进、跳过点排除、可达路径和完成路线后的空下一站。 | 修改空间图、讲解点目录或导航输出后必须运行。 |
| `replanning.py` | 有限重规划器 | 仅处理跳过点与剩余时间变化；保留真实已访问记录，从当前点继续，排除跳过点。 | 不引入新讲解点、不调用 LLM；论文/比较卡不参与选点。 |
| `route_planner.py: plan_from_current_position()` | 从当前位置的剩余路线规划 | 依据原路线顺序和时间预算裁剪剩余点，先删 optional、再删低优先级 core，并保留回前院出口区的路径。 | 只使用已审核边与讲解点目录。 |
| `test_replanning.py` | 有限重规划测试 | 验证跳过点排除、20 分钟缩短路线、入口回退和已访问点不回流。 | 修改重规划规则后必须运行。 |
| `agent_graph.py` 的 TourState 节点 | TourState LangGraph 接入 | `direct_route` 初始化状态；`arrive_at_stop`、`next_stop`、`skip_stop`、`replan_time`、`finish_tour` 全部为确定性节点并在同一 thread 内保留状态。 | 不允许 LLM 直接写 `tour_state`；当前点的详细事实讲解仍留待下一阶段 RAG 编排器。 |
| `test_agent_tour_state.py` | TourState Agent 路由测试 | 验证路线初始化、到达、下一站、跳过、改时间和结束均路由至确定性节点。 | 修改 Agent 意图关键词或节点状态写入后必须运行。 |

TourState 首版字段固定为 `selected_route_id`、`route_stop_ids`、`current_stop_id`、`visited_stop_ids`、`skipped_stop_ids`、`remaining_stop_ids`、`started_at`、`available_minutes`、`remaining_minutes`、`interests`、`detail_level`、`route_status`。`last_arrival_kind` 和 `completion_reason` 为可选审计字段。

后续导游交互、游览中 RAG 问答、讲解编排器、用户画像与知识卡接入的阶段边界见 `TOUR_GUIDE_ROADMAP.md`。任何新增论文卡、比较卡、术语卡或打卡点卡都不得绕过该文档和本文件中既定的 `card_id` / `node_id` 规则。

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
