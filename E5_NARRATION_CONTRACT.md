# E5：证据驱动的个性化讲解质量契约

**状态：E5-0 冻结。** 本文件规定 E5 后续模块的接口、事实边界和验收目标。它不改变 A1 事件、TourState、路线选择、知识卡资格或当前生产讲解行为。

## 1. 冻结数据流

```text
VisitorProfile
→ GuidancePolicy
→ StopProgram（审核对象 + 本站内容预算）
→ NarrationCoverage（本会话已成功介绍的对象/工艺）
→ 工艺 / 文物 RAG evidence
→ NarrationStylePolicy
→ 确定性 visitor_message
```

| 层 | 允许负责的事实 | 禁止事项 |
| --- | --- | --- |
| `node_guide_cards_v1.json` | 当前点审核对象、工艺、`raw_location`、点位关联 | 解释故事或技法时替代 RAG 证据 |
| `07_ornament_crafts.md` | 工艺定义、材料、技法、常见部位、整体视觉特点 | 把其他点位对象说成眼前实例 |
| `08_ornament_items.md` | 单件文物的形态、题材、寓意、故事 | 无证据时补写细节 |
| `NarrationStylePolicy` | 词汇、句长、节奏、术语解释、互动形式 | 改对象、事实、来源、路线或状态 |
| `TourState` | 位置、路线进度、事件事实 | 保存知识、RAG 正文或讲解覆盖 |

`NarrationStylePolicy` 是 E5-B 的新纯展示策略，不替代或复制 C6 的 `GuidancePolicy`：前者只将已确认的策略参数编译为文案约束，后者仍是唯一画像到导览策略的事实来源。

## 2. 首次接触与成功讲解

“首次接触”指本次游览会话中，某工艺或文物尚未向游客输出**成功、实质且带有效 evidence**的讲解。

以下都不算介绍成功：路线名称、下一站焦点、对象清单、内部检索命中、无证据降级、澄清或错误回复。只有 `visitor_message` 已成功生成、实际使用至少一条有效证据且通过输出校验后，才可写入覆盖记录。

## 3. NarrationCoverage（E5-A 所有）

它是 AgentState 中线程内的短期状态，不是 TourState、VisitorProfile、知识库或长期用户画像。

```json
{
  "schema_version": "v1",
  "introduced_craft_ids": [],
  "introduced_ornament_ids": [],
  "introduction_records": [
    {
      "subject_kind": "craft",
      "subject_id": "craft:灰塑",
      "source_ids": ["S10"],
      "introduced_by": "stop_guidance",
      "node_id": "stop_front_courtyard_center",
      "turn_id": "thread-local-turn-id"
    }
  ]
}
```

冻结规则：

1. 只保存已成功介绍的 subject ID、来源编号、来源节点和本轮标识；不保存 RAG 原文。
2. 无 evidence、澄清、错误、被拒绝输出或空消息不得更新。
3. 新路线初始化清空；到达、跳过、重规划、确认完成不清空；不同 `thread_id` 天然隔离。
4. 覆盖状态只能影响“首次/后续讲解组织”，不能作为位置、历史、对象、画像或路线事实源。
5. `tour_qa` 的成功讲解可记录 `introduced_by=tour_qa`；普通对象清单、术语纯定义和无证据回答不得自动记录为当前点文物介绍。

## 4. 首次工艺讲解

当 StopProgram 的选中对象包含本会话首次介绍的工艺时，E5-A 必须先取得该工艺的总述 evidence，优先检索 `07_ornament_crafts.md`。

在 evidence 足够时，首次工艺段至少覆盖以下六项中的三项，并随后连接到当前点审核实例：

1. 工艺是什么；
2. 材料或制作方式；
3. 常见技法；
4. 常见建筑位置；
5. 视觉特点；
6. 现场观察方法。

同轮多个对象属于同一工艺时，总述只出现一次。若缺少足够工艺 evidence，必须明确资料不足，不能以模型常识补齐。

建议结构：

```text
工艺名称 → 一句话定义 → 材料/技法 → 常见位置
→ 当前点审核实例 → 观察方法
```

## 5. 后续工艺讲解

已介绍过的工艺只作简短回顾，优先讲当前对象的新细节、不同题材或可证据支持的对照。游客明确追问“是什么”或“再讲详细一点”时允许重新展开；避免重复不能成为省略当前对象必要事实的理由。

## 6. 首次与后续文物讲解

首次实质介绍一件文物，在证据与预算允许时应覆盖：名称、审核观察位置、工艺、可见形态或构图、题材/人物/图案、寓意/故事/文化背景、一个具体观察提示。

最低不可省略组合为：

```text
名称 + raw_location形成的安全位置提示 + 工艺
+ 一项可见细节 + 一项有来源的题材/寓意/故事
```

`raw_location` 只可形成“在哪里看”的观察提示；不得推测左右、高度、通行、遮挡或实时可见性。没有 `08_ornament_items.md` evidence 的字段必须省略并说明资料不足。

同一文物再次被讲解时，简短回顾名称与核心事实，再增加新细节、对照角度或回答游客追问；不得原样重复首次段落，也不得因已介绍而无视游客当前明确问题。

## 7. 时间预算优先级

E5 不改变路线总预算。StopProgram 的本站内容预算是硬边界，叙事层不能用更长文案绕过它。

```text
1. 当前点主题与方位
2. 首次工艺总述
3. 核心文物完整讲解
4. 对照文物
5. 互动任务
6. 可选扩展
```

预算不足时，先减少对象数，再缩短互动与可选扩展，保留首个工艺与核心文物的完整证据链。不得截断句子、删除来源关系或超时。

## 8. 首轮 stop_guidance 结构

```text
到达点位与观察方向
→ 本点主题概述
→ 首次工艺总述（若适用）
→ 核心文物详细讲解
→ 第二对象或工艺对照（若预算允许）
→ 对象主题联系
→ GuidancePolicy 允许的观察提示
→ 讲解结束与确认提示
```

禁止输出文件路径、原始 RAG chunk、内部角色/计划秒数、无来源故事、无事实支撑的“观察周围关系”套话，或影响口语阅读的大段 `source_ids`。

## 9. 个性化和 listen_only

E5-B 的 `NarrationStylePolicy` 只可控制词汇难度、句子长度、叙事节奏、术语解释、互动形式、故事引导和专业术语开放程度。儿童、家庭、研学、专业等只读取已经确认的 `GuidancePolicy`，不从一句自然语言推断身份。

`listen_only` 不降低首次工艺与核心文物的事实深度；它只关闭主动提问、任务和要求回应的互动。允许使用“您可以留意……”等非强制提示。

## 10. 状态不变量与失败关闭

- E5 的讲解生成、RAG 取证、文案风格和覆盖记录不得修改 TourState、VisitorProfile、路线、空间图或知识卡。
- TourState 仍只由 `tour_interaction.handle_tour_event()` 修改；到达不等于完成，只有 `confirm_stop_complete` 写入 visited。
- `qa_context` 仍只管理一轮受控问答追问，不能替代物理位置或 NarrationCoverage。
- 无精确对象、无点位关联、无 evidence、RAG 异常或输出校验失败时，失败关闭：不更新覆盖记录，不补造事实。

## 11. E5 分工与文件所有权

| 子任务 | 负责人产出 | 可修改的主要文件 | 不得修改 |
| --- | --- | --- | --- |
| E5-A 核心讲解与覆盖集成 | `narration_coverage.py`、取证/首讲编排适配、定向测试 | 新模块、`guide_program_evidence.py`、`guide_narration.py`、最小 `agent_graph.py` 接口 | TourState、路线、知识卡正文、共享文档 |
| E5-B 语言风格素材库 | `narration_style_policy.py`、审核风格模板/素材、测试 | 新风格模块与独立素材文件 | 对象选择、RAG evidence、状态写入、共享文档 |
| E5-C 讲解质量评测集 | 评测 YAML、评测脚本、人工审核说明 | `data/.../evaluation/` 与专用测试 | 生产路由、TourState、事实卡、共享文档 |

三方必须从同一个 E5-0 提交创建分支。主负责人独占更新 `COLLABORATION_GUIDE.md`、`PROJECT_PROGRESS_REPORT.md` 与 `PROJECT_LEARNING_AND_DEFENSE_GUIDE.md`。

## 12. 验收案例（冻结编号）

| ID | 输入/前置 | 必须验证 |
| --- | --- | --- |
| `e5_nar_001` | 首次到前院中部，首次灰塑 | 先有 07 工艺 evidence，再关联独角狮等本点对象 |
| `e5_nar_002` | 后续到另一灰塑点 | 不重复完整定义，讲新对象或差异 |
| `e5_nar_003` | 首次介绍独角狮 | 位置、工艺、可见细节及有来源题材/故事，不只简介首句 |
| `e5_nar_004` | 短预算 | 减对象，保留首次工艺与核心文物，不超预算 |
| `e5_nar_005` | 当前点没有木雕但用户喜欢木雕 | 不把别处木雕说成眼前对象 |
| `e5_nar_006` | `listen_only` | 首讲完整，无问题或任务 |
| `e5_nar_007` | 相同输入、不同 thread | NarrationCoverage 互不共享 |
| `e5_nar_008` | 无工艺或文物 evidence | 明确资料不足，覆盖状态不更新 |

## 13. E5-A/B/C 冻结接口

### E5-A 输入 / 输出

```python
plan_evidence_grounded_narration(
    program: StopProgram,
    coverage: NarrationCoverage,
    guidance_policy: GuidancePolicy,
    retrieve: Callable[[str], EvidencePayload],
) -> NarrationPlan
```

`NarrationPlan` 必须输出：按工艺分组的已审核对象、首次/后续标记、使用 evidence、预算内段落计划、待提交覆盖记录；不得输出或修改 TourState。

### E5-B 输入 / 输出

```python
compile_narration_style(policy: GuidancePolicy) -> NarrationStylePolicy
render_narration(plan: NarrationPlan, style: NarrationStylePolicy) -> visitor_message
```

输出只能重新组织 E5-A 已批准事实与证据，不能增加对象或事实。

### E5-C 输入 / 输出

```python
evaluate_narration_case(case, narration_result, state_before, state_after) -> EvaluationResult
```

评测至少覆盖证据、首次覆盖、预算、位置范围、listen_only、线程隔离和状态不变。
