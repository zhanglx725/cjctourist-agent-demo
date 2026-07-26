# 陈家祠路线数据 v1

本目录是“自动规划路线”的结构化输入层。路线规划器只读取本目录和
`../spatial/` 中已审核的空间图；不会要求语言模型从地图图片猜测路径。

## 文件职责

| 文件 | 维护内容 | 当前状态 |
| --- | --- | --- |
| `route_stop_catalog_v1.csv` | 可作为讲解停留站的候选点、推荐停留时间、主题和优先级 | 候选待审核 |
| `route_templates_v1.json` | 人工认可的路线叙事骨架 | 数据契约已建立，尚未启用模板 |
| `route_policy_v1.json` | 预算、超时、折返、边状态等全局规划规则 | 首版默认策略 |
| `route_evaluation_cases_v1.json` | 路线规划器的离线验收用例 | 骨架待补充 |
| `dynamic_route_policy_v1.json` | 任意时长动态组合的规则、权重、体验时间与边界 | A0-4b 已完成；只允许使用已审核讲解点和空间边 |
| `dynamic_route_planner.py`（项目根目录） | 动态路线组合器 | 使用束搜索选择下一站，并以 2-opt 减少局部折返；输出完整路径和步行/讲解/观察/互动时间拆分 |
| `inspect_dynamic_route.py`（项目根目录） | 动态路线命令行预览器 | 人工核验任意时长、兴趣和排除点条件下的路线结果 |
| `route_benchmark_cases_v1.json` | 动态路线与人工锚点的基准用例集 | 固定 30/60/90 对照与 45/75 动态路线的验收场景 |
| `route_benchmark.py`（项目根目录） | 锚点基准评估器 | 输出动态/锚点的预算、关键点覆盖、兴趣得分与推荐策略，供 A0-6 人工审核 |
| `route_review.py`（项目根目录） | A0-6 审核报告生成器 | 输出含自动检查与人工审核字段的 `route_review_results_v1.json` |
| `term_stop_associations_v1.json` | 术语—点位关联 | 由 `build_term_stop_associations.py` 从已审核文物映射生成；只关联工艺和明确命名的构件语境 |

## 关键边界

1. `route_stop_catalog_v1.csv` 的首要筛选依据是已人工标注的
   `mapped_ornament_count`。官方路线只能作为“可经过”的证据，不能单独使一个
   零讲解内容的空间成为停留站。
2. `review_status=approved` 的记录才可进入正式自动路线；`candidate` 仅供人工
   审核，不会被规划器使用。
3. 空间图中的 `junction`、`entrance`、`gate` 可以经过，但默认不作为讲解停留站。
3. 路线模板只保存叙事顺序和核心停靠站；实际走法必须由空间图逐段求得。
4. 当前所有时间均可能来自官网地图估算。对外输出必须保留
   `estimated_from_map_and_official_route`，直到完成现场实测。
5. 具体文物事实仍由 RAG 提供证据；路线数据只规定“在哪里停、围绕什么讲”。

## 点位讲解包的扩展接口

`node_guide_cards_v1.json` 的每个点位均预留以下空数组：

- `research_summary_card_ids`：学术研究摘要卡；
- `comparison_card_ids`：建筑、时代或工艺比较卡；
- `term_card_ids`：专业术语卡；
- `photo_spot_card_ids`：经审核的打卡点卡；
- `glossary_ids`：多语言术语表。

研究、比较、术语和多语言卡只增强讲解，不改变路线。打卡点卡只有在包含
安全、秩序、开放限制和 `route_optional` 审核信息后，才可以作为可选短暂停留加入路线。

`glossary_ids` 由 `build_term_stop_associations.py` 回写。其关联状态为
`derived_from_approved_ornament_mapping`，表示可用作当前点位的讲解线索，但不能被
表述为精确室内定位或现场可见性的绝对保证。

## 审核顺序

先审核候选停留站，再确认每条模板的必到点和可选点，最后才实现寻路算法。
首版建议：`core` 为至少 9 件关联文物的高密度讲解站；`optional` 为 4–7 件
关联文物的补充讲解站；没有关联文物的空间仅作为通行节点，除非后续补入稳定的
建筑讲解卡并重新审核。
