# 陈家祠金牌导游 Agent：后续导游编排路线图

## 已完成的底座

- 静态事实 RAG、混合检索、评估与 Agent 问答。
- 已审核空间网络、30/60/90 分钟人工锚点路线与 45/75 等动态路线。
- TourState 阶段 A：会话内游览状态、到达、下一站、跳过、剩余时间重规划、结束记录。

路线规划目前只决定“去哪里、怎么走、停留预算”。它尚未决定每站具体讲哪几件文物、讲多久、如何按游客类型组织叙事。

## 导游交互模式（A1，进行中）

默认产品不应要求游客记住“我到月台了”这类提示词。TourState 将支持以下入口，底层都调用相同的确定性状态函数：

1. **文本自主模式**：游客说"我到月台了""下一站去哪""跳过这里"，LLM 将其理解为事件后调用状态函数。
2. **按钮引导模式**（默认推荐）：界面发送稳定事件，例如 `arrive_at_stop(node_id)`、`next_stop`、`skip_stop`、`replan_time`，无歧义，适合大多数游客。
3. **连续导游模式**：Agent 完成讲解播报后显示操作面板，游客点击"讲完了，去下一站""再讲详细""跳过此点""我还有 X 分钟"，无需聊天输入。

不得仅按计时自动标记游客已参观完成；现实中可能拍照、提问、停留或受人流影响。应采用"自动播报 + 轻确认"策略：

```text
讲解播放结束
→ 界面提示：本点参观完成了吗？
   [完成，前往下一站]
   [再停留一会]
   [跳过后续讲解]
```

后续状态字段（UI/交互层）：

```text
pending_stop_id              # 当前等待访问的点位
tour_mode                    # chat / button_guided / continuous
stop_phase                   # navigating / explaining / awaiting_confirmation
```

A1-0 已冻结 `TOUR_INTERACTION_CONTRACT.md`，A1-1 已建立 `tour_interaction.py` 作为唯一公开事件适配入口；交互字段不写入 TourState。现已统一为“到达不等于完成”，只有 `confirm_stop_complete()` 才能把正式讲解点写入 `visited_stop_ids`。不同交互模式最终只调用相同的确定性适配事件。

### A1-2：文本导游意图识别与安全路由（已实现并验证）

`tour_intent.py` 会在任何状态写入前先产生可审计的结构化决策：

```text
“我到月台了” → arrive_at_stop(label_moon_platform)
“讲完了，去下一站” → confirm_stop_complete
“我只剩 20 分钟” → replan_time(20)
“月台有什么？” → RAG 问题，不改游览状态
“我到月台了，顺便讲讲石雕” → 多意图澄清，不部分执行
```

识别在 A1-2 是确定性的，不调用 LLM。点位仅从已审核的 `marker_inventory_v0.csv` 解析；合法但非 `pending_stop_id` 的到达仍交由 A1-1 记录为 `self_arrival`，不改变正式路线顺序。A1-3 才增加按钮与连续导游操作面板，A2 才实现游览中 RAG 问答后恢复导游上下文。

已在项目 `.venv` 完成核心 38 项文本/Agent 路由测试，以及完整 90 项回归，均通过。

## A1 阶段状态（已完成并验证）

A1-1 至 A1-3 已实现并完成对应回归；A1-4 已完成离线端到端验收，覆盖从文本意图到展示协议的完整确定性闭环。项目负责人已完成完整 141 项本机回归，结果均为 `OK`，A1 正式完成。A2 尚未开始，不能表述为已具备“问答后自动恢复导游上下文”的能力。

## 游览中问答与继续导游（A2-1 已实现并验证）

首个 A2 实现为 `tour_qa.py` 与 `agent_graph.py: tour_qa_node`：运行中导览的“这里有什么”会确定性读取真实 `current_stop_id` 的已审核点位讲解包；明确点位清单也可在无路线时读取。工艺、寓意、故事和单件文物解释才将点位信息作为提示调用既有本地 RAG，并恢复不改变状态的 A1-3 操作面板。项目负责人已完成 A2 相关 106 项及完整 155 项本机回归，均为 `OK`。论文卡、比较卡、术语卡、打卡点卡、真实前端和讲解编排器均未接入；LangSmith 冒烟验证仍用于检查实际服务链路。

## 阶段 B：点位讲解编排器（B1 已实现并验证）

B1 新增 `guide_program_planner.py`，只决定“到站后从本点审核文物中讲哪 1–3 件”，输出稳定 `StopProgram`；不改变路线。项目负责人已完成 B1 相关 112 项及完整 161 项本机回归，均为 `OK`。B2 再分配更真实的内容、观察与互动时间，B3 才用 `rag_query_hints` 为已选对象取证并接入 Agent。论文、比较、术语和打卡卡不阻塞 B，后续仅通过空的 `card_id` 插槽定向增强。

游客在任何点位都可以插入问题，例如“灰塑是什么”“这幅三国故事讲什么”。处理流程应为：

```text
检查 TourState 中 current_stop_id
→ RAG 检索并回答当前问题
  （可选）若答案引用当前点位的讲解卡，增加信息完整度
→ 回复末尾恢复当前导游上下文：
  "你正在[点位名]。[回答内容]。
   下一步：[按钮或提示]"
```

问答本身**不应自动增加 `visited_stop_ids`**，也不应重置当前路线。只有显式到达、跳过、确认完成或重规划事件可以修改 TourState。这保证了 `visited_stop_ids` 真实反映游客实际到达的点位，而不是提问历史。

## 阶段 B：点位讲解编排器（后续，与 A 并行）

新增建议：

```text
guide_program_planner.py
test_guide_program_planner.py
data/chen_clan_academy/guides/
```

职责：从点位讲解包（`node_guide_cards_v1.json`）的全部已映射文物中，按游客兴趣与时间选择 1–3 件代表对象，生成可审计的 `StopProgram`。示例：

```json
{
  "node_id": "label_moon_platform",
  "budget_seconds": 300,
  "visitor_profile": {"detail_level": "standard", "interests": ["建筑工艺"]},
  "selected_items": [
    {
      "ornament_id": "orn_078",
      "ornament_name": "石雕栏板",
      "role": "核心观察",
      "planned_seconds": 90,
      "rag_query_hints": ["石雕栏板特点", "铁铸通花对比"]
    },
    {
      "topic": "石雕与铁铸通花栏板的对比",
      "role": "工艺比较",
      "planned_seconds": 90,
      "comparison_card_id": "comp_001"
    },
    {
      "topic": "观察任务与提问",
      "role": "互动",
      "planned_seconds": 120
    }（与 B 并行）

新增建议：

```text
visitor_profile.py
test_visitor_profile.py
data/chen_clan_academy/profiles/
```

**首版仅收集三项（追问 + 智能填充）：**

```text
available_minutes      # 可用时间
interests              # 兴趣：灰塑、木雕、三国、建筑、摄影等
detail_level           # short / standard / deep
```

**后续可选字段（不在首版强制）：**

```text
visitor_type           # 首次来访 / 亲子 / 研学 / 工艺爱好 / 摄影爱好
language               # zh / en （多语言后续支持）
photo_preference       # yes / no （是否主动需要拍照建议）
accessibility_need     # 行动便利、视障等特殊需求
```

**兴趣到优先点位的初步映射：**

| 兴趣标签 | 优先讲解点位 | 关键文物类型 | 讲解卡类型 |
| --- | --- | --- | --- |
| 灰塑 | 前庭、前院中部、前东庭、后庭 | 灰塑人物故事、吉祥题材 | 标准 + 工艺比较 |
| 木雕 | 前庭、后庭、后西庭 | 木雕梁架、窗花 | 标准 + 工艺特写 |
| 三国故事 | 后西庭、前院西部靠中 | 灰塑三国人物 | 深度 + 故事扩展 |
| 建筑工艺 | 月台、前院中部、前庭 | 栏板、花脊、梁架 | 深度 + 建筑结构卡 |
| 吉祥题材 | 前院中部、前东庭、前西庭 | 灰塑纹样、寓意 | 标准 + 寓意卡 |
| 摄影 | 前院、月台、后庭（光线与视角优先） | 全类型（视觉焦点） | 标准 + 打卡点卡 |
| 研学 | 月台、后庭、后西庭 | 建筑工艺代表、历史沿革 | 深度 + 论文摘要卡 |

**三人追问策略：**

```text
自我介绍 / 欢迎
→ "您有多少时间参观？(30/45/60/75/90分钟)"
→ "对哪方面最感兴趣？(灰塑/木雕/三国/建筑/吉祥/摄影/研学/不确定)"
  若"不确定"，则根据时长和默认推荐
→ "希望快速了解，还是深入学习？(快速/标准/深入)"
→ 推荐路线 + 询问"我们从月台出发好吗？"
```

**集成到 Agent 流程：**

1. 首次 `direct_route` 被调用时，若缺少 `interests` 或 `detail_level`，转向"用户追问"节点。
2. 后续路线、讲解编排和 RAG 问答都读取同一份 `visitor_profile`。
3. 允许游客中途改变兴趣（"突然想深入了解木雕""没时间了"），触发重规划。
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
