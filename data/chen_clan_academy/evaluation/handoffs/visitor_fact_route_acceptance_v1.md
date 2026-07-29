# 游客事实问答与路线路由验收记录 v1

更新时间：2026-07-30

状态：实现完成，待 LangSmith 双模式人工复测

## 实现边界

- 游览前事实问答保持冻结节点路径 `semantic_normalization → direct_rag → llm_think`，但 `llm_think` 只读取受控事实结果，不再调用模型改写或补写事实。
- 游览中事实问答使用 `semantic_normalization → tour_qa`。
- 两种模式共享同一意图识别、类别范围、规范检索词、逐类别检索、证据筛选和结论优先渲染器。
- 固定词表未覆盖但语义明确的表达，可以由受控语义归一层映射到下表已有事实类型；模型只提交“闭合枚举 + 原话证据 + 置信度”，不能生成检索词、类别、事实或游客答案。
- 路线规划在两种模式下均使用 `semantic_normalization → profile_collection → direct_route`；已有路线时会用本轮明确给出的画像约束重新规划。
- 七种传统工艺继续走已有工艺专用通道，本次未改变其事实源和字段策略。
- 文件名、资料标题、原始 chunk、内部来源编号、URL、节点 ID、检索类别等只保留在内部审计，不进入游客答案。

## 十二项双模式回归

| # | 问题 | 受控意图 | 游览前实际路径 | 游览中实际路径 | evidence 类别 | 确定性计算 | 游客结论 |
|---:|---|---|---|---|---|---|---|
| 1 | 陈家祠在哪一年建成？ | `construction_completion` | `semantic_normalization → direct_rag → llm_think` | `semantic_normalization → tour_qa` | `history_architecture` | 否 | 1888 年开始筹建；落成/建成年份存在 1893 与 1894 两种公开资料口径 |
| 2 | 陈家祠是什么时候建成的？ | `construction_completion` | 同上 | 同上 | `history_architecture` | 否 | 同第 1 项 |
| 3 | 陈家祠何时落成？ | `construction_completion` | 同上 | 同上 | `history_architecture` | 否 | 同第 1 项 |
| 4 | 陈家祠哪一年开始筹建？ | `construction_start` | 同上 | 同上 | `history_architecture` | 否 | 1888 年开始筹建，并明确这不是落成年份 |
| 5 | 陈家祠从筹建到落成大约经历了多久？ | `construction_duration` | 同上 | 同上 | `history_architecture` | 是，`time_difference` | 按 1893 年口径约 5 年；按 1894 年口径约 6 年 |
| 6 | 陈家祠在哪里？ | `site_address` | 同上 | 同上 | `basic_info` | 否 | 广州市荔湾区中山七路恩龙里 34 号 |
| 7 | 陈家祠闭馆时间是什么时候？ | `closing_time` | 同上 | 同上 | `basic_info`、`ticketing_snapshot` | 否 | 常规开放到 17:30；延时开放资料记载闭馆延至 18:00；停止入场不等于正式闭馆 |
| 8 | 陈家祠周二开放吗？ | `closed_day` | 同上 | 同上 | `basic_info`、`visit_service`、`ticketing_snapshot` | 否 | 常规周二闭馆，法定节假日除外 |
| 9 | 陈家祠几点停止入场？ | `last_admission` | 同上 | 同上 | `basic_info`、`visit_service`、`ticketing_snapshot` | 否 | 常规 17:00 停止入场；延时开放期下午检票和售票截止延至 17:30；不把它表述为闭馆时间 |
| 10 | 陈家祠下午场检票到几点？ | `afternoon_entry_cutoff` | 同上 | 同上 | `ticketing_snapshot` | 否 | 常规到 17:00；延时开放期到 17:30 |
| 11 | 给我规划两小时路线，喜欢木雕，详细讲解。 | `route_request` | `semantic_normalization → profile_collection → direct_route` | `semantic_normalization → profile_collection → direct_route` | 路线与已审核站点数据，不走通用 RAG | 否 | 提取 120 分钟、木雕、详细讲解，输出有序路线、每站停留时间和木雕重点 |
| 12 | 陈家祠由谁设计、在哪一天奠基？ | `designer_and_foundation_date` | `semantic_normalization → direct_rag → llm_think` | `semantic_normalization → tour_qa` | `history_architecture` | 否 | 现有资料不足；倡议人不能等同于设计者，不作推测 |

访问服务类答案统一附带：“开放安排可能调整，请以官方当日公告为准。”

## 固定词表外的事实同义表达

| 问题 | 固定解析结果 | 语义候选 | 规范事实类型 | 固定检索类别 | 双模式路径 | 结果 |
|---|---|---|---|---|---|---|
| 陈家祠最晚什么时候还能进入？ | 未命中 | `fact_last_admission` | `last_admission` | `basic_info`、`visit_service`、`ticketing_snapshot` | 游览前 `semantic_normalization → direct_rag → llm_think`；游览中 `semantic_normalization → tour_qa` | 两种模式使用同一固定检索改写并回答 17:00 常规停止入场及必要限定 |
| 陈家祠一般哪天歇着？ | 未命中 | `fact_closed_day` | `closed_day` | `basic_info`、`visit_service`、`ticketing_snapshot` | 同上 | 两种模式使用同一固定检索改写并回答常规周二闭馆、法定节假日除外 |

以上用例不把新说法加入手工同义词表，目的是验证语义候选确实能进入既有受控事实通道。低置信度、非法 schema、额外检索字段、非原文证据片段或模型不可用时一律不建立事实候选。

## 受控派生计算

`controlled_derivation.py` 提供不依赖模型的三个受控操作：

- `time_difference`
- `quantity_difference`
- `chronological_order`

调用方必须先从审核 evidence 中提取所有操作数，并为每个操作数提供 evidence 索引。缺少任一操作数、证据为空、数据类型错误或时间/数量方向矛盾时失败关闭。当前游客端已接入“筹建到落成的年份差”；数量差和先后关系已具备确定性基础能力，后续只能为明确审核过的问法和操作数逐项开放。

## 自动化测试

定向命令：

```text
python -m unittest -v test_semantic_normalization.py test_single_fact_answer.py test_agent_tour_qa.py test_visitor_fact_route_acceptance.py test_tour_qa.py
```

结果：56 项通过。

完整回归命令：

```text
python -m unittest discover -v
```

结果：578 项通过。

## 待人工复测

在 LangSmith 中分别建立新线程和已有路线线程，逐项复测上表 12 个问题。重点确认：

- 两种模式的事实结论等价；
- 游客界面不出现文件名、原始段落、来源编号、URL、节点名和内部类别；
- 路线请求不会落入普通 RAG；
- 开放时间相关答案没有混淆闭馆日、停止入场、检票截止、售票截止和正式闭馆时间。
- 未写入固定词表的事实同义表达，在两种模式下均先由 `semantic_normalization` 产生闭合候选，再进入既有固定类别检索和确定性答案；低置信度时不得强行归类。
