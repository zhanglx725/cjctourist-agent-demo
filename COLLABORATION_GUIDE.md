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
| `routes/node_guide_cards_v1.json` | 点位讲解包 | 路线站的文物列表、工艺分布、RAG 查询提示与扩展卡接口。 |
| `research_cards/` | 学术研究摘要卡库 | 建议按“论文一张卡”建设，供深度讲解引用。 |
| `comparison_cards/` | 建筑比较卡库 | 建议按“一个对比问题一张卡”建设，供比较问答和深度路线使用。 |

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
