# 受控通用知识问答交接与 LangSmith 验收 v1

更新时间：2026-07-30  
状态：离线实现完成，待实际模型 LangSmith 验收

## 目标

让现有知识目录中的问题不再依赖少量固定关键词。游客的自然语言先被归一为一个不含事实的只读计划，再进入现有混合 RAG；最终答案只允许依据检索 evidence 组织。

```text
自然语言
→ semantic_normalization
→ 闭合 domain / question_type / detail_level + 原话 subject_text
→ 代码生成 categories 与 retrieval query
→ 现有向量语义召回 + BM25 + 可选重排
→ 按 evidence 自然组织答案
```

## 受控范围

知识领域：

| domain | 允许检索类别 |
| --- | --- |
| `site_overview` | `basic_info`, `history_architecture` |
| `history_architecture` | `history_architecture` |
| `visit_service` | `visit_service`, `basic_info` |
| `ticketing` | `ticketing_snapshot`, `basic_info` |
| `event_notice` | `event_notice` |
| `ornament_craft` | `ornament_craft` |
| `ornament_item` | `ornament_item` |
| `ornament_location` | `ornament_location`, `ornament_item` |

问题类型包括定义、时间、位置、人物、材料、流程、技法、特点、故事、寓意、功能、组成、列举、数量、原因、规则、资格、方法、可用性和其他。讲解深度只允许 `brief` 或 `detailed`。

## 保留的专项优先级

以下能力不会被通用知识入口覆盖：

- 七种工艺的确定性简要/详细讲解；
- 术语卡；
- 研究卡与比较卡；
- 打卡点与拍摄安全；
- 路线规划、到达、完成、跳过和重规划；
- 审核点位清单与当前点讲解；
- 9 类已有确定性单一事实。

## 安全边界

- 模型不能生成检索类别、检索词、节点 ID、来源或事实。
- `subject_text` 必须是游客原话中的连续片段。
- 只保留计划允许类别内、且正文非空的 evidence。
- 无 evidence 时失败关闭，不使用相邻类别补答案。
- 游客答案不得显示文件名、原始 chunk、来源编号、URL、类别名、节点名或工具调用。
- 票务、服务与公告答案固定追加“以馆方当日公告为准”的时效提示。
- 本功能不读取或修改 `TourState`、`VisitorProfile`、路线、空间图和知识正文。

## 建议 LangSmith 用例

每题分别在“未规划路线”和“导游进行中”测试：

1. 陈家祠为什么又叫书院？
2. 三路三进是什么布局？
3. 馆里哪里可以寄存小件行李？
4. 学生票适用于哪些人？
5. 最近有什么展览公告？
6. 砖雕常用什么材料和技法？
7. 三顾茅庐讲了什么故事？
8. 独角狮一般装饰在哪里？
9. 五伦全图有什么寓意？
10. 陈家祠建筑装饰为什么这么密集？

每个 trace 检查：

- 是否进入 `semantic_normalization`；
- 是否产生正确的闭合 `knowledge_domain`、`question_type` 和 `detail_level`；
- `evidence_text` 是否来自游客原话；
- 游览前是否走 `direct_rag → llm_think`，游览中是否走 `tour_qa`；
- 两种模式的 categories 是否相同；
- 最终回答是否结论优先、连贯且没有内部检索信息；
- 资料不足时是否明确失败关闭。

## 已知限制

这不是“识别无限自然语言且永不出错”。实际模型仍可能对极模糊、多意图、代词缺少上下文或知识库之外的问题给出低置信度/错误分类，因此必须继续通过 LangSmith 扩充验收表达；但新增表达不需要逐个写成关键词，只要能安全归入闭合领域和问题类型即可。知识库没有的事实仍然不能回答。
