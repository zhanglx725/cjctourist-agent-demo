# 陈家祠金牌导游 Agent：后续导游编排路线图

## 已完成的底座

- 静态事实 RAG、混合检索、评估与 Agent 问答。
- 已审核空间网络、30/60/90 分钟人工锚点路线与 45/75 等动态路线。
- TourState 阶段 A：会话内游览状态、到达、下一站、跳过、剩余时间重规划、结束记录。

路线规划目前只决定“去哪里、怎么走、停留预算”。它尚未决定每站具体讲哪几件文物、讲多久、如何按游客类型组织叙事。

## 导游交互模式（A1，后续）

默认产品不应要求游客记住“我到月台了”这类提示词。TourState 将支持以下入口，底层都调用相同的确定性状态函数：

1. 文本自主模式：游客说“我到月台了”“下一站去哪”“跳过这里”。
2. 按钮引导模式：界面发送稳定事件，例如 `arrive_at_stop(node_id)`、`next_stop`、`skip_stop`、`replan_time`。
3. 连续导游模式：播报结束后展示“完成，前往下一站”“再讲详细”“跳过”“我还有 X 分钟”等按钮，等待游客确认。

不得仅按计时自动标记游客已参观完成；现实中可能拍照、提问、停留或受人流影响。后续可增加：

```text
tour_mode: chat / button_guided / continuous
pending_stop_id
stop_phase: navigating / explaining / awaiting_confirmation
```

## 游览中问答与继续导游（A2，后续）

游客在任何点位都可以插入问题，例如“灰塑是什么”“这幅三国故事讲什么”。处理流程应为：

```text
TourState 保持不变
→ RAG 检索并回答当前问题
→ 回复末尾恢复当前导游上下文：当前点、下一操作按钮或下一站提示
```

问答本身不应自动增加 `visited_stop_ids`，也不应重置当前路线。只有显式到达、跳过、确认完成或重规划事件可以修改 TourState。

## 阶段 B：点位讲解编排器

新增建议：

```text
guide_program_planner.py
test_guide_program_planner.py
```

职责：从点位讲解包的全部已映射文物中，按游客兴趣与时间选择 1–3 件代表对象，生成可审计的 `StopProgram`。示例：

```json
{
  "node_id": "label_moon_platform",
  "budget_seconds": 300,
  "selected_items": [
    {"ornament_id": "orn_078", "role": "核心观察", "planned_seconds": 90},
    {"topic": "石雕与铁铸通花栏板的对比", "role": "工艺比较", "planned_seconds": 90},
    {"topic": "观察任务与提问", "role": "互动", "planned_seconds": 120}
  ]
}
```

`StopProgram` 的时间应回写进路线预算。路线规划与讲解编排必须保持分层：前者决定走法与点位，后者决定讲解对象、叙事方式与时间分配。

讲解深度规则：

| detail_level | 内容 |
| --- | --- |
| `short` | 一件代表文物 + 一句观察提示 |
| `standard` | 代表文物 + 工艺或寓意 |
| `deep` | 代表文物 + 工艺比较 + 历史故事或研究延伸 |

生成讲解时，先用 RAG/知识卡为已选对象取证，再由导游生成器组织自然语言；不得让生成模型先决定空间路径。

## 阶段 C：最小用户画像与个性化

先只收集或追问：

```text
available_minutes
interests
detail_level
```

后续可选字段：

```text
visitor_type, language, photo_preference, accessibility_need,
current_stop_id, visited_stop_ids, skipped_stop_ids
```

兴趣映射初稿：

| 兴趣 | 优先点位或内容 |
| --- | --- |
| 灰塑 | 前庭、前院中部、前东庭、后庭 |
| 木雕 | 前庭、后庭、后西庭 |
| 三国故事 | 后西庭、前院西部靠中 |
| 建筑工艺 | 月台、前院中部、前庭 |
| 吉祥题材 | 前院中部、前东庭、前西庭 |
| 研学 | 月台、后庭、后西庭；允许研究卡增益 |

同一份画像应被路线选择与讲解编排共同读取，但不应允许画像绕过已审核空间边。

## 阶段 D：知识卡接入

论文卡、比较卡、术语卡、多语言术语和打卡点卡继续独立建设。它们不进入基础事实 RAG，也不阻塞路线执行。经审核后通过点位讲解包预留字段接入：

```text
research_summary_card_ids
comparison_card_ids
term_card_ids
photo_spot_card_ids
glossary_ids
```

| 知识卡 | 优先接入时机 |
| --- | --- |
| 论文研究摘要卡 | `deep`、研学、追问“学界如何看” |
| 建筑/工艺比较卡 | 比较问题、深度路线 |
| 术语卡 | 首次出现专业术语 |
| 多语言术语表 | 外语导览开始前 |
| 打卡点卡 | 主动拍照需求且现场规则审核后 |
| 成就/寄语 | TourState 的真实记录足够完整后 |

## 当前三人并行边界

| 负责人 | 可并行内容 | 不应直接修改 |
| --- | --- | --- |
| 路线负责人 | A1/A2、讲解编排器、用户画像接入 | 其他成员的知识卡内容 |
| 成员 2 | 论文摘要卡、术语卡 | `agent_graph.py`、空间边、`node_id` |
| 成员 3 | 比较卡、打卡点数据规范 | `route_planner.py`、空间边、`node_id` |
| 统一合并负责人 | 已审核卡 ID 接入、项目报告 | 不覆盖成员原始数据文件 |

汇总层 `agent_graph.py`、`route_planner.py`、`node_guide_cards_v1.json`、`PROJECT_PROGRESS_REPORT.md` 应由一人统一合并。
