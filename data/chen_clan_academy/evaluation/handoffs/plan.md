# 陈家祠受控 Agent 分阶段实施计划

## P3-01 / CA-12 已冻结的模式契约（2026-08-03）

- 保留既有 `tour_mode`：`chat`、`button_guided`、`continuous`；它继续只表达交互形式。
- 在同一份 `tour_interaction_state` 中增加 `journey_mode`：`classic`、`custom`；新路线请求必须由游客明确选择模式，不从默认值、语气、身份或偏好推断。内部缺失/异常状态仍可安全回退为 `classic`，但该兼容回退不得替代游客端模式选择。
- `VisitorProfile`、`TourState` 均不保存 `journey_mode`。路线确认时只在不可变的路线审计快照记录最终采用模式，且该审计字段不参与路线计算。
- 只读问答的恢复目标仅保存在 interaction/session control；问答不得重建或覆盖既有路线、TourState、VisitorProfile、StopProgram 或 NarrationCoverage。
- 经典模式只主动收集游览时长；定制模式只收集游客明确给出的最小偏好（例如兴趣），**不再询问讲解深度**。
- 定制模式的讲解深度固定为“详细讲解”这一产品输出策略；它不写入 `VisitorProfile`，不新增画像字段，也不成为路线计算条件。实际叙述长度、段落和朗读版式仍由后续 P3-04 在预算与证据门控下统一实现。

在经典模式中，调度规则应是：

- 术语卡：可在当前点确有相关工艺、且基础讲解需要解释时主动补充；
- 比较卡：只在有明确、合格的比较对象和证据时补充，不能把比较结论说成基础事实；
- 打卡点卡：仅在游客有明确拍照意图，或产品后续明确批准“低打扰推荐”时使用；必须先过安全与点位门控；
- 研究/学术摘要卡：经典模式一律不主动注入；
- 无合格卡：正常结束基础讲解，不硬塞卡片内容。

“撰写卡片内容且无需关键词就直接讲解输出”不在 P3-01 完成；它属于 P3-03 CardDispatcher 的实现与验收范围。P3-01 只冻结经典/定制模式下哪些卡具备主动调度资格；P3-04 再统一卡片与基础讲解的段落、长度和朗读版式。P3-01 不实现 CardDispatcher 或任何卡片主动输出。

> 文档性质：基于当前工作区、`CONTROLLED_AGENT_ARCHITECTURE_UPGRADE_PLAN.md`、目标架构图和现有问题台账形成的执行拆解。  
> 生成日期：2026-08-01；状态同步：2026-08-02（`experiment/agent-orchestration-v2@1b418dc`）
> 目标文件：`data/chen_clan_academy/evaluation/handoffs/plan.md`  
> 当前结论：先收敛正确性与契约，再迁移受控 Agent；学术、多模态和游后推荐不得抢跑。

## 1. 本次审计基线

### 1.1 实际 Git 状态

- 当前开发分支：`experiment/agent-orchestration-v2`。
- 当前本地 HEAD：`72e9c9268ed16dc34d101819f332325a7f66e72e`（`feat: roll out controlled knowledge in shadow mode`）。
- P2-05 前置核对时，当前分支与 `origin/experiment/agent-orchestration-v2`：同一提交且工作树干净。后续文档归档改动应单独提交；`main` 与 `origin/main` 当前停留在 `9eec98d`，实验分支尚未合并。
- 原审计时列出的架构方案、八天计划和数据文件修改均已纳入历史提交；当前不存在需先认领的未跟踪或未提交文件。
- 负责人于 2026-08-02 在重建的 Python 3.12.7 项目虚拟环境中运行 `python -m unittest discover -v`：P2-05 接入前 `1b418dc` 为 `827/827`；本轮工作树的 P2-05 实现为 `831/831`（0 failure、0 error，35.528 秒）。P0 定向安全/游客输出矩阵最近记录为 `59/59` 通过。P0-03/CA-00 行为矩阵见 `data/chen_clan_academy/evaluation/p0_gate_0_behavior_matrix_v1.yaml`。

Git 同步、工作区归属和当前实验分支自动化基线已完成；Gate 0 仍为 `conditional_pass`：自动化护栏绿色，`1b418dc` 已完成 CA00-SF-01～04 四个安全实链并记录 Thread/Run ID，但 Trace URL 与其余矩阵仍待复核，且 P1-04 仍有外部空间数据阻塞。CA-01～CA-05、Policy Gate、受控只读 Executor、原子多意图只读计划、路线/重规划 proposal、确认后状态迁移适配器和只读灰度契约已经进入实验分支；这些实现尚不能替代 Gate 1～Gate 3 的实链验收。四项证据见 `data/chen_clan_academy/evaluation/handoffs/p0_current_commit_live_safety_evidence_20260802.md`。

### 1.2 本计划读取的主要依据

- `PROJECT_REQUIREMENTS.md`
- `COLLABORATION_GUIDE.md`
- `PROJECT_PROGRESS_REPORT.md`
- `TOUR_GUIDE_ROADMAP.md`
- `POST_D_TEAM_EVALUATION_AND_OPTIMIZATION_STANDARD.md`
- `POST_D_TEAM_EXECUTION_AND_HANDOFF_PLAN_V0.md`
- `CONTROLLED_AGENT_ARCHITECTURE_UPGRADE_PLAN.md`
- `NEXT_STAGE_ISSUE_AND_ROADMAP.md`
- 当前 `agent_graph.py`、TourState、VisitorProfile、路线、RAG、知识卡、讲解和安全模块
- 当前 105 个 `test_*.py` 测试文件
- `outputs/chen_clan_controlled_agent_architecture.png`

本文记录的 `827/827` 来自接入前基线；`72e9c92` 的 P2-05 完整回归为 `831/831`。凡缺少当前 commit、thread ID 或 Trace URL 的 LangSmith 人工结果，应标记为 Trace 元数据待补；若负责人已提供功能操作截图、输入、路径、正文与状态观察，可作为 `functional_validation: passed_by_operator` 进入后续只验收闸门，但不得写成 Trace 已验证。

## 2. 目标产品与不可变边界

### 2.1 最终产品需要完成的三条主旅程

1. **游客问答**：规划前和导游中都能回答；优先使用本地审核知识。导游中插入问答后，继续原导游流程。
2. **导游闭环**：收到“开始导游、规划路线、带我逛”等请求后，收集最少必要条件，生成审核路线；支持到达、讲解、追问、下一站、跳过、完成和受控重规划。
3. **游览结束体验**：根据实际完成和成功讲解记录生成客观总结、七艺覆盖、趣味称号和中性祝福；游客接受后再给有来源、有时效边界的附近景点或餐饮建议。

目标架构还包括独立的学术顾问工作区、多语言、ASR/TTS、动态来源和治理观测。这些属于后续能力，不应与馆内导游正确性同时大改。

### 2.2 必须保持的唯一事实源

| 领域 | 唯一事实源 | 禁止做法 |
|---|---|---|
| 游览进度 | `TourState` + 冻结事件适配 | Planner、LLM 或新工具直接写状态 |
| 游客偏好 | `VisitorProfile` 及验证更新模块 | 新建第二份画像、从语气猜身份 |
| 空间与路线 | 审核节点、空间图、路线规划器 | 模型生成 node ID、猜点位别名 |
| 陈家祠事实 | 审核知识、来源注册和 evidence | 用模型记忆补陈家祠事实 |
| 卡片资格 | 卡片注册表与运行资格表 | 绕过审核状态直接输出 |
| 对象—点位关系 | 审核映射文件 | 为启用内容编造对象或位置 |
| 讲解覆盖 | `NarrationCoverage` | 用“计划经过”冒充“实际讲过” |
| 学术来源 | 研究来源注册、摘要卡、合法全文状态 | 伪造论文、页码、DOI 或共识 |

### 2.3 大模型补充的正确边界

- 可以补充：通用概念解释、表达组织、通用闲聊；必须标明是一般性补充，不能冒充馆方事实。
- 不可以补充：陈家祠年代、人物、对象、位置、工艺实例、开放票务、安全规则、路线、当前附近营业状态等项目事实。
- 本地证据不足时：陈家祠相关问题失败关闭；动态信息转官方当日渠道；不得用相邻 chunk 凑答案。
- 最终游客正文必须经过统一 Renderer；文件名、路径、原始 chunk、内部 ID、来源编号、URL 和工具字段只留在 Trace/审计。

## 3. 当前真实能力盘点

| 能力 | 当前状态 | 主要实现 | 与目标差距 |
|---|---|---|---|
| 本地混合 RAG | 已实现 | `rag_ingestion.py`、`rag_retrieval.py` | 入口仍分散，部分出口待实链确认 |
| 语义候选归一 | 已实现、范围受控 | `semantic_normalization.py`、`agent_graph.py` | 不是通用自然语言理解；控制变体仍需验收 |
| 单事实/服务问答 | 已实现、待 LangSmith 收口 | `single_fact_answer.py`、`controlled_knowledge_query.py` | 规划前后路径不同但应结论等价 |
| 七艺工艺问答 | 已验证 | `craft_knowledge.py` 等 | 应保持专项通道，迁移时防回归 |
| 路线规划与预算 | 已实现 | `route_planner.py`、`route_selection.py`、`dynamic_route_planner.py` | 仍由大图分支直接编排，尚无 proposal 工具层 |
| TourState 状态机 | 已实现 | `tour_state.py`、`tour_interaction.py` | 必须继续作为唯一状态写入口 |
| 到达/完成/下一站/重规划 | 部分已验证 | `tour_intent.py`、`replanning.py`、`tour_navigation.py` | 自然表达和偏航实链仍有待验项；P1-04 阻塞 |
| VisitorProfile | 已实现 | `visitor_profile.py` 及 profile 模块 | 经典/定制模式及最少收集契约未冻结 |
| 点位讲解/E5 | 已实现、部分待验 | `guide_program_*`、`narration_rendering.py`、`narration_coverage.py` | 版式、回退出口、完整矩阵仍待收口 |
| 术语/研究/比较/打卡卡 | 数据、注册和被动问答已实现 | 各卡片 runtime/retrieval | 到点主动调度尚未建立 |
| 安全门控与游客输出边界 | 自动化已通过，实链待收口 | `visit_safety_rules.py`、`photo_spot_runtime.py`、`public_visitor_message_or_fallback` | P0 矩阵 `59/59`、完整回归 `770/770`；当前提交的 LangSmith Trace 待补 |
| 受控 Planner/Gate/Registry/Executor | 未实现 | 仅存在目标方案 | 需要分阶段 shadow → 灰度，不可一次重写 |
| 经典/定制模式 | 未冻结 | 无唯一 `tour_mode` 归属 | 先做契约，不能随意加字段 |
| 游后总结/成就 | 未形成正式产品链 | Coverage 可复用 | 缺统计口径、规则库和输出控制 |
| 附近推荐 | 未实现可信服务 | 需求中有目标 | 缺审核 POI、动态时效和外部来源适配 |
| Academic Advisor | 未实现独立工作区 | 现有 20 张研究卡可作种子 | 缺独立 session、证据矩阵、来源许可和学术治理 |
| ASR/TTS/多语言 | 未实现统一链路 | 有风格与部分术语基础 | 应在文字主链稳定后接入 |
| Graph-assisted Hybrid RAG | 规划中、未开始 | 现有关系数据可派生 | 当前不是最优先瓶颈 |

## 4. 总体优先级与依赖

```text
P0 基线与安全/正确性收口
  ↓
P1 受控 Agent 基础（schema → registry → gate → executor）
  ↓
P2 多意图、路线 proposal、状态 adapter 与 Graph 灰度
  ↓
P3 经典/定制模式、讲解风格、卡片调度与版式
  ↓
P4 游览结束总结、成就、祝福和附近推荐
  ↓
P5 独立 Academic Advisor
  ↓
P6 多语言、语音、可信位置与动态来源
  ↓
P7 图辅助检索、全面评测、旧路由收敛与发布
```

并行原则：同一阶段可并行编写“纯 schema/测试”和“只读数据审计”，但 `agent_graph.py`、TourState、VisitorProfile、公共路由和最终 Renderer 同一时间只允许一个集成人修改。

## 5. P0：先把当前系统变成可信基线

### P0-00 Git 与基线恢复

**目的**：得到可重复、可追溯且不覆盖成员工作的起点。

具体步骤：

1. 已完成：确认并同步原先分叉的成员修改；当前 `main == origin/main == 56688f7`，工作树干净。
2. 已完成：记录当前受控 Agent/八天计划已进入提交历史，不再作为“未认领修改”。
3. 待完成：在可用项目虚拟环境中重新运行完整 `unittest discover -v`，按根因归类 16 个失败与 1 个错误；不能沿用旧的非项目 Python 结果。
4. 待完成：记录实际解释器、依赖锁定方式、索引 manifest、LangGraph CLI、测试命令和执行提交；再判定是否形成绿色功能基线。

完成门槛：工作树干净、本地远端一致、完整测试结果可重复且全部通过或有负责人批准的隔离/阻塞结论。当前仅满足前两项，P0-00 仍未关闭。

### P0-01 关闭安全与游客输出门控的待验项

覆盖：P0-01、P0-02、P1-19、P1-21。

具体步骤：

1. 为危险拍照、商业拍摄、无人机、触摸/倚靠/攀爬、闪光灯、展厅饮食、庭院休息区饮食建立对抗表达集。
2. 在规划前、规划收集中、导游中、重规划 pending 和问答追问五种状态下运行同一安全请求。
3. 确认路径始终先进入安全门控，不先给机位、卡片、路线或普通 RAG。
4. 强制模拟 E5 失败、工具失败和无证据，确认游客文本无内部来源字段，但 Trace 保留 evidence 和失败原因。
5. LangSmith 每类至少保存 thread ID、Trace URL、测试 commit、输入、路径、最终正文和状态 diff。

允许修改：安全匹配、统一 Visitor Response Renderer/边界、测试与局部交接。  
禁止修改：知识事实、安全规则语义、TourState、卡片资格。

完成门槛：非法状态写入、危险建议、游客端内部泄漏均为 0。

### P0-02 收口仍未完成的 P1 正确性

按顺序处理：

1. **P1-04 空间别名阻塞**：空间负责人确认“后西庭/后庭西侧”的权威 node ID、别名和路线资格；未确认前保持澄清，绝不编码猜测。
2. **P1-11 偏航重规划**：从用户确认的新审核点位建立 proposal，保持原路线快照；只有确认后应用。
3. **P1-12 控制同义表达**：补完到达、完成、继续、下一站、剩余时间等实链矩阵；语义层只给候选和原文 span。
4. **P1-13 身份证替代检票**：统一票务和服务证据，处理冲突和替代方式，不扩展为公安业务。
5. **P1-14 多工艺位置**：确认游览前后自然短列表一致，单项缺证据只标该项。
6. **P1-16 团队发票**：确认标题式查询、问句式查询和游览中查询都进入票务通道。
7. **P2-07 版式根因**：对比原始消息、Studio 渲染和不同对象数量，修复嵌套 bullet/缩进，不删事实规避问题。
8. 对 P1-07/08/09 的现有实现完成剩余 LangSmith 矩阵，并更新问题状态。

完成门槛：`NEXT_STAGE_ISSUE_AND_ROADMAP.md` 中除明确外部阻塞项外，不再存在“自动化通过但真实链路失败”未归因问题。

### P0-03 冻结行为矩阵（对应 CA-00）

建立不可变基线用例：

- 游览前/中同一事实问答的结论和 evidence 类别等价。
- 安全意图高于问答、路线、到达和拍照卡。
- 路线预算、审核节点、空间连通和确认语义不变。
- 只读问答不改 TourState、VisitorProfile、路线和 Coverage。
- 只有成功讲解才提交 Coverage。
- 线程互不串状态、上下文和 evidence。
- 工具/模型不可用时失败关闭或退回既有确定性路径。

输出：`data/chen_clan_academy/evaluation/p0_gate_0_behavior_matrix_v1.yaml` 与 `data/chen_clan_academy/evaluation/handoffs/p0_gate_0_behavior_baseline_v1.md`；此步不修改生产路由。当前状态：`conditional_pass_pending_review`。

## 6. P1：建立受控 Agent 基础控制面

### P1-01 AgentDecision schema（CA-01）

新增一个严格闭合的候选协议，至少包含：intent、sub-intents、requested capability、用户原文 span、置信度、确认需求和副作用等级。

实施细节：

- `intent`、capability 和 side-effect 使用枚举。
- 模型不得输出可信 node/ornament/source/card ID；ID 只能由确定性 resolver 生成。
- `target_text`/`evidence_span` 必须是用户原话连续片段。
- 非法字段、额外字段、互斥组合和低置信度默认拒绝或澄清。
- 此阶段只做 schema/validator，不改图路由。

测试：合法/非法 JSON、伪 ID、截断、提示注入、多个意图、否定/假设、低置信度、相同输入稳定验证。

### P1-02 Tool Registry（CA-02）

建立只保存工具元数据的注册表，不复制工具事实。每项记录：

- 名称和版本；
- 输入/输出 schema；
- 允许状态相位；
- evidence 要求；
- side-effect 等级；
- 是否需确认；
- 超时、最大调用次数和失败策略；
- 游客可见字段与仅审计字段。

首批只登记稳定的只读能力：single fact、visit service、controlled knowledge、term、craft、object、point inventory、research、comparison、photo、navigation。

完成门槛：未登记工具默认拒绝；重复名称和不完整 schema 使启动/加载失败关闭。

### P1-03 首批知识工具化（CA-03/CA-04）

按两批接入，避免一次改动所有问答：

1. 术语、单事实、票务/服务、受控知识。
2. 七艺、对象详情、点位 inventory、多工艺位置、研究/比较/打卡。

每个 adapter 只能调用现有后端并返回 Typed Evidence Envelope：类别、来源、版本、有效期、置信等级、游客事实计划和审计元数据。不得把 Markdown 原文直接作为游客答案。

验收：

- 规划前/中结果等价。
- 资格、点位和对象范围不放宽。
- 动态证据检查有效期。
- 无证据失败关闭。
- 七艺 28 个已验证场景不回归。

### P1-04 Shadow Planner（CA-05）

在配置关闭执行权的情况下，让 Planner 只产生 AgentDecision，并与当前真实路由并排记录。

实施细节：

- 设置超时、最多一次候选生成、无模型时静默回退旧路由。
- 不改变最终消息、状态、工具选择和延迟主路径。
- Trace 记录 candidate、validator 结果和与旧路径的差异；不保存 Chain-of-Thought。
- 在 LangSmith 对事实、路线、控制、安全、多意图建立混淆矩阵。

进入下一步门槛：高风险控制和安全候选不得低于冻结规则；候选无法稳定验证时不得启用。

### P1-05 Policy Gate（CA-06）

确定性检查：工具是否注册、当前状态是否允许、参数是否源自用户或审核 resolver、是否有资格/evidence、是否需确认、是否越权。

副作用等级建议：`read_only`、`proposal_only`、`confirmed_state_change`、`prohibited`。

必须拒绝：模型生成 ID、未登记工具、陈家祠事实无 evidence、动态事实过期、自动应用路线、直接写 TourState/Profile、绕过卡片资格。

### P1-06 Tool Executor + Evidence & Result Validator（CA-07）

- 只执行 Gate 批准的调用。
- 单轮最大 3 个调用；同参去重；设置超时和错误类型。
- 验证返回 schema、证据类别、来源有效性、对象/点位 ID、时效和游客字段。
- Renderer 只消费验证后的事实计划；模型不得在 Renderer 后再次改写事实。
- 失败时保留旧安全回退，不调用自由模型补证。

完成门槛：工具超时、空结果、残缺结果、冲突 evidence、重复调用和注入测试全部可审计且不产生事实扩写。

## 7. P2：让受控 Agent 接管组合能力

### P2-01 多意图原子计划与问答恢复（CA-08）

目标场景：

- “先回答灰塑是什么，再继续带我走。”
- “我到了月台，先讲石雕，然后告诉我下一站。”
- “剩 30 分钟，重新规划，但先回答闭馆时间。”
- “推荐拍照点并加入路线。”（不可组合时明确分步，不半执行）

实现要求：

- 拆成有序原子动作，先全量 Gate，再执行。
- 任何状态副作用失败时不得留下部分写入。
- QA interruption 保存原 `profile_collection`、导航/pending action 和正式路线引用；回答后恢复原流程位置。
- 恢复只指向原状态，不复制第二份 TourState/Profile。

### P2-02 路线 proposal 工具（CA-09）

输入只允许：审核入口/当前位置、分钟、明确兴趣、详略、已批准约束。后端继续使用现有确定性规划器。

输出包括：候选 stop IDs、顺序、预算分解、步行估计、选择原因、数据版本；不会自动 `start_tour()`。

测试：30/60/90/120 分钟、少走路、兴趣、详细讲解、无可行路线、伪节点、预算边界、相同输入稳定性。

### P2-03 重规划 proposal 工具（CA-10）

- 起点必须是当前 TourState 已确认点或本轮经审核 resolver 确认的自助到达点。
- proposal 绑定 physical node、visited/skipped 快照、剩余时间和版本。
- 提案过期、位置变化或快照变化时拒绝确认。
- 未审核地点澄清；不得生成默认路线掩盖未知地点。

### P2-04 State Transition Adapter（CA-11）

Planner 只能提交事件请求；adapter 再调用冻结的 `handle_tour_event()`/状态函数。

覆盖：到达、完成、跳过、下一站、结束、确认重规划。所有合法状态变化必须能追溯到事件；非法写入计数为 0。

### P2-05 Graph 灰度接入第一阶段（CA-14 的前半）

配置至少支持：`off`、`shadow`、`read_only_active`。先只让受控知识问答进入新链；控制事件和路线仍走旧链。

门槛：

- 每项能力可单独关闭。
- 新链失败可回退旧受控链，但不能回退原始 RAG 倾倒。
- Studio 与 CLI 的 thread 隔离一致。
- 新旧答案差异有评测记录。

## 8. P3：产品模式、风格与卡片调度

### P3-01 冻结经典/定制模式与恢复协议（CA-12）

负责人已于 2026-08-03 冻结双维 session 模型：既有 `tour_mode` 仍只表示
`chat` / `button_guided` / `continuous` 交互形式；同一 `tour_interaction_state`
的 `journey_mode` 表示 `classic` / `custom` 产品模式。默认 classic，只有游客
明确选择才进入 custom；VisitorProfile 与 TourState 不保存此字段，路线确认后
仅在不可变审计快照记录最终模式且不得参与路线计算。只读问答只读取既有恢复
目标，不得写入控制状态。经典模式只主动收集时长；定制模式不询问讲解深度，
统一按“详细讲解”产品策略输出，且该策略不写入 VisitorProfile 或路线事实。

- 经典模式：只强制收集时间，其他用透明中性默认；不主动插研究/比较/摄影卡。
- 定制模式：最多收集明确兴趣、可选目的/同行情况；不询问讲解深度，统一按详细讲解策略输出。讲解风格仅在游客主动指定时作为既有 P3-02 的独立表达策略使用，不在 P3-01 主动追问；未填保持中性。
- 两种模式都可被事实问答打断并恢复。
- 不根据语气、设备或外貌猜模式。

### P3-02 接入现有 NarrationStylePolicy

复用已完成的七种风格素材，不新建第二画像。首批生产建议：neutral、child、family、student_research、professional、listen_only、mixed_group，未授权或未知风格回退 neutral。

验证同一 evidence 在不同风格下的实体、数字、时间、位置、否定、安全和 source_ids 完全一致；只改变句长、词汇、节奏和互动方式。

### P3-03 CardDispatcher（CA-13）

输入：当前审核 node、StopProgram、GuidancePolicy、模式、明确兴趣、剩余预算、卡片资格。输出只是一组有序增强候选。

顺序：基础对象事实必选 → 可选术语解释 → 可选研究/比较 → 明确摄影意图下的打卡建议。

门控：

- 研究观点必须归因。
- 比较结论不得冒充项目事实。
- 打卡必须先过安全、点位和现场边界。
- 无合格卡时正常完成基础讲解。
- 卡片调度不改路线、TourState 或对象选择。

### P3-04 NarrationComposer 与游客版式

把事实计划组织为“结论/主旨 → 可观察细节 → 必要故事/工艺 → 可选深入 → 过渡”，但不能新增事实。

解决 P2-07：限制嵌套层级、列表长度、对象数量和朗读长度；客户端显示与 TTS 文本采用同一安全正文。

### P3-05 Graph 灰度接入第二阶段

依次开放：知识只读 → 多意图只读 → 路线 proposal → 受确认事件。任何阶段硬门槛失败即退回上一档，不批量删除旧路由。

## 9. P4：完成游览闭环

### P4-01 TourOpeningProgram

路线确认后给一次可跳过、可重播的陈家祠总体介绍；使用独立审核 evidence。问答打断后恢复，重规划不重复播放。

当前实现状态（2026-08-05）：已启动 P4-01。本地工作树已新增独立审核
evidence、确定性 `TourOpeningProgram`、窄控制表达和 Graph 节点。人工
反馈后，契约修正为首个正式点位成功到达时自动执行开场，随后同轮进入
`stop_guidance`；只有游客到站前明确说“跳过总体介绍”才绕过。该程序仅写入
thread-local 开场程序/审计，不写 TourState、VisitorProfile、路线或
NarrationCoverage。待负责人本机完成定向与全量回归后，再进入 LangSmith
五案例验收；未通过前不得开始 P4-02。

### P4-02 VisitSummaryEngine

输入只能来自本轮已确认 TourState 和成功提交的 NarrationCoverage。

当前实现状态（2026-08-05）：已新增确定性 `VisitSummaryEngine` 和 Graph
结束出口。仅统计正式确认完成的 visited stops，以及发生在这些点位、由
`stop_guidance` 成功提交的 Coverage；远程问答、跳过、未确认到达、预览和
失败讲解均排除。对象—工艺关系只读取审核 guide-card 映射；Coverage 异常
时保留点位总结但不报告精确工艺/题材数量。另以新路线为边界记录游客实际
进入 `tour_qa`/`qa_follow_up_detail` 的提问回合数，供 P4-03 称号规则使用；
预路线问题、控制指令和内部调用不计数。`title_basis` 同时提供实际听过的
工艺/题材、内容多样性、显式兴趣及其与实际讲解的精确匹配，以及非中性且
验证通过的讲解风格/互动/知识偏好；默认值、语言、无障碍需求和推断人格不
作为成就信号。待本机回归与 LangSmith 验收。

统计步骤：

1. 确认路线是否完成/提前结束。
2. 统计实际 visited stops，不统计计划但未到达点。
3. 统计成功讲解且用户未跳过的去重 ornament IDs。
4. 由审核对象—工艺映射汇总七艺；多工艺对象按冻结口径处理。
5. 输出“参观几个点、成功讲过哪些工艺/题材”；证据不足时不报精确数量。

远程问答、预览、失败回退和只导航不得计入“看过”。

### P4-03 TitleAwardPolicy 与祝福

建立版本化规则库，称号是趣味展示，不是官方认证或用户评级。

- 条件只能引用 summary 中的可审计计数/集合。
- 相同输入确定性获得同一称号。
- 冲突时有固定优先级和 neutral fallback。
- 不写长期 VisitorProfile。
- 祝福只使用用户明确画像；未知时使用中性文案。
- 不使用未授权歌词；优先原创短祝福或有许可模板。

当前实现状态（2026-08-05）：已新增版本化确定性称号策略和原创祝福节点。
`visit_summary` 成功后自动进入 `post_visit_title_blessing`；结束态重复结束、
查看总结或请求称号/祝福不会回到模式选择。规则仅消费已审计
`title_basis`，固定优先级并提供中性 fallback、理由与“非官方认证”声明，
不写 TourState、VisitorProfile、路线或 Coverage。同期补齐 active route 下
“到达/我到下一个点位了/我到下一站了”的确定性到站解析，禁止回退 LLM/RAG。

### P4-04 NearbyRecommendationService

先建设少量审核 POI 卡，再考虑外部动态查询。

触发条件：游览结束后游客主动询问或接受推荐。输入可包含当前位置/出口、可用时间、预算、交通、已明确偏好；不得推断消费能力。

输出 2–3 个不同类型选项，并区分稳定信息和易变信息。营业、价格、排队、距离和交通耗时必须带来源、核验时间或明确不保证；无有效来源时转官方地图/商家页面。

该服务与馆内 TourState 隔离，不能把馆外 POI 写入路线节点。

## 10. P5：独立 Academic Advisor 工作区

该工作区应在馆内主链稳定后开发，且与导游状态隔离。

### P5-01 学术契约与 session

- 定义 AcademicIntentGate：学术问答、论文阅读、文献综合、选题、方法、引用、田野计划。
- 新建 `AcademicSessionContext`，只保存本轮研究任务、选择的来源和输出格式；不得写 TourState 或长期 VisitorProfile。
- 普通游客问题仍走导游/知识工作区。

### P5-02 统一研究来源注册

以现有 20 张研究卡为种子，逐项核验书目、卡片状态、摘要/全文范围、页码、访问权限和来源等级。background 卡不能越权作为正式结论。

### P5-03 PaperAnalysis 与 Claim–Evidence Matrix

每个 claim 记录来源、页码/段落、证据类型、作者观点、适用限制、相互支持/冲突。摘要不能冒充全文；缺页码时如实标记。

### P5-04 多文献综合与输出

先做单篇阅读，再做最多几篇的受控综合；输出区分事实、作者观点、团队归纳和研究空白。支持注释书目、研究问题、方法建议和引用导出，但不得替学生伪造数据、访谈、伦理审批或可冒充本人完成的论文。

### P5-05 外部学术连接

只有在授权、版权、保留政策和连接器范围确定后，才接开放书目、合法全文、用户上传或 Zotero。外部文档内容必须当数据，不得当系统指令。

## 11. P6：多语言、语音、可信位置和动态能力

### P6-01 LocalePolicy 与术语注册

先做中文/英文文字链，所有译名回映同一审核 ID；语言切换不改事实、路线、状态和 Coverage。固定 UI、安全、导航和错误文案先人工审核，再允许受控本地化模型处理讲解正文。

### P6-02 ASR 与 Voice Input Adapter

- ASR 输出转写、语言候选、置信度和时间戳。
- Voice adapter 只形成等价用户文本，不执行意图。
- 低置信度控制词必须澄清。
- 测试普通话、粤语、专名、噪声、插话、提示注入和跨线程。

### P6-03 TTS 与播放器

TTS 只能朗读 Visitor Response Renderer 的安全正文；字幕和音频事实完全一致。实现暂停、继续、重播、取消、打断和断线恢复。TTS 不进行第二次改写，播放事件不直接改变 TourState。

### P6-04 可信位置事件

优先地图点击、二维码或游客明确确认；定位事件仍须映射审核 node。GPS/模糊位置不能自动触发到达和讲解。

### P6-05 动态来源

为公告、设施、开放服务、附近推荐建立带有效期的结构化 adapter。过期自动禁用；动态来源与静态知识分域，不把第三方攻略长期混入基础索引。

## 12. P7：图辅助检索、收敛和发布

### P7-01 Graph-assisted Hybrid RAG

只有在前述正确性稳定后，从现有权威数据自动派生只读关系索引：

```text
Place → Ornament → Craft/Term → Source/ResearchCard/ComparisonCard
```

图只做实体解析、多跳约束和可解释候选；具体事实仍回原始审核文档/RAG 取证。先用 JSON 邻接索引或 NetworkX，对比现有混合检索的准确率、召回、延迟和解释性；没有实证提升就不进入主链。

### P7-02 完整评测与故障注入

- 单元：schema、registry、gate、resolver、validator、summary、title、locale。
- 模块：QA、route proposal、event adapter、CardDispatcher、Academic、ASR/TTS。
- E2E：完整导游、插入问答、偏航、结束总结、推荐、线程隔离。
- 对抗：注入、伪 ID、无来源、过期动态事实、工具超时、模型不可用、重复/乱序事件。
- LangSmith：记录 commit、thread、Trace、节点路径、evidence 类别、状态 diff、游客输出评分。

### P7-03 旧路由收敛（CA-15）

只有新旧能力差分通过且回滚演练成功，才逐条删除已等价的重复知识边。安全仲裁、TourState 事件层、VisitorProfile 验证、审核 resolver、卡片资格和最终 Renderer 永久保留，不因“Agent 化”删除。

## 13. 建议任务包和可并行边界

| 批次 | 可并行任务 | 串行/集成任务 |
|---|---|---|
| A | Git/基线审计；LangSmith 用例整理；P1-04 数据确认 | 基线 commit 与问题状态更新 |
| B | AgentDecision 单测；Tool Registry 元数据；Typed Evidence schema | schema/registry 冻结 |
| C | 单事实/服务 adapter；对象/工艺 adapter；研究/比较 adapter | Executor/Validator 统一接入 |
| D | Shadow 评测；Policy Gate 单测 | `agent_graph.py` shadow 接入 |
| E | 路线 proposal；重规划 proposal；多意图测试 | State adapter 与 Graph 灰度 |
| F | 模式契约；风格验证；CardDispatcher 数据审计 | 模式/调度接入 |
| G | Summary 规则；称号文案；POI 数据审计 | 游后闭环接入 |
| H | Academic 数据核验；Locale 术语审核 | 学术/多模态主链接入 |

公共文件所有权建议：

- `agent_graph.py`：只由集成人修改。
- TourState/TourInteraction：只由状态负责人修改。
- VisitorProfile：只由画像负责人修改。
- 空间、路线、对象映射和知识事实：内容/数据负责人审核后修改。
- 各工作包优先新增独立模块和独立测试；不要在 `agent_graph.py` 堆叠新分支。

## 14. 每个任务必须使用的执行模板

1. 检查分支、Git 状态、HEAD 和文件所有权。
2. 读取需求、协作指南、问题台账、相关冻结契约、生产代码和测试。
3. 写清目标、允许文件、禁止文件、唯一事实源和副作用等级。
4. 若规划与实现冲突，停止并提交标准冲突报告。
5. 先加失败测试或基线测试，再做最小实现。
6. 运行单元测试 → 模块测试 → 完整回归 → `git diff --check`。
7. 在本地验证通过后，给出 LangSmith 手工用例；未运行不得写“已通过”。
8. 只更新必要 handoff/README，不批量改公共进度文档。
9. 等负责人本机/Studio 验证后再提交和推送。
10. 汇报文件、行为变化、状态不变量、测试、已知限制、commit 和回滚方法。

## 15. 分阶段验收闸门

| 闸门 | 必须满足 |
|---|---|
| Gate 0 | 工作树/基线清楚；P0 安全和泄漏为 0；P1 未决项有状态和证据 |
| Gate 1 | AgentDecision、Registry、Policy、Executor 可独立验证；不影响旧行为 |
| Gate 2 | read-only 新链规划前后等价；无事实扩写；状态变化为 0 |
| Gate 3 | 多意图原子；路线只产 proposal；状态只经 adapter；线程隔离 |
| Gate 4 | 经典/定制归属冻结；风格事实一致；卡片资格零越权 |
| Gate 5 | 总结只统计实际覆盖；称号可审计；推荐有来源和时效 |
| Gate 6 | Academic 与 Tour 状态隔离；引用/版权/诚信硬门槛为 0 |
| Gate 7 | 语音字幕等价；控制误识别安全澄清；动态来源不过期 |
| Release | 完整回归、LangSmith 全矩阵、故障注入、回滚演练和文档交接通过 |

## 16. 立即执行的下一组任务

不要从流程图最上方的 ASR 开始，也不要先开发 Academic Advisor。当前最合适的顺序是：

1. 已完成：本地/远端分叉和未提交文件归属已收敛；当前开发基线为干净且已推送的 `experiment/agent-orchestration-v2@1b418dc`，尚未合并 `main`。
2. 已完成：Python 3.12.7 项目虚拟环境已重建；当前提交完整回归为 `827/827`，P0 安全/游客输出矩阵最近记录为 `59/59`；CA-00 行为矩阵已建立，Gate 0 仍为 `conditional_pass`。
3. 完成 P0-01/P0-02 的 LangSmith 守护矩阵，以及 P1-19/P1-21 的跨出口游客渲染复测；定向安全通过不等于实链通过。
4. 复测并收口 P1-07/08/09/11/12/13/14/16；P1-12C1/C4 的自动化已通过，当前提交仍待 LangSmith；P1-04 继续等待空间负责人决策。
5. 用 CA-00 行为矩阵补齐 `1b418dc` 的 LangSmith 证据，并由负责人审核是否从 `conditional_pass` 提升为 `passed`。
6. 已在实验分支完成：CA-01 AgentDecision schema、CA-02 Tool Registry、CA-03/04 只读 adapter、CA-05 Shadow Planner、Policy Gate、受控只读 Executor、原子多意图只读计划、路线/重规划 proposal、确认后状态迁移适配器和只读灰度契约。
7. 待完成：以独立线程执行 Gate 1～Gate 3 LangSmith 矩阵，核对候选/旧路由差异、游客正文、evidence、状态 diff、proposal 确认边界和线程隔离；未通过前不启用写操作灰度。
8. 待完成：LangSmith 通过并审核后，将实验分支按可回滚边界合并到 `main`，记录合并提交与回滚提交。

### P2-05 Graph 灰度接入第一阶段（CA-14 前半）

当前实验分支已将 `controlled_knowledge` 接到 Graph 的 pre-tour 闭合知识问答入口：`off` 保持原 `direct_rag`；`shadow` 运行候选并保留旧链游客正文；`read_only_active` 仅在 AgentDecision、Policy Gate、Executor 和公开输出校验全部成功时展示候选，否则回退到旧的受控知识渲染，不得回退原始 RAG 文本。配置由 `CJC_READ_ONLY_ROLLOUT_MODE` 与 `CJC_READ_ONLY_ROLLOUT_CAPABILITIES` 控制，候选/旧链差异只写入 thread-local `controlled_rollout_evaluations`。`72e9c92` 的定向 26 项与完整 831 项回归均通过；负责人已在 Studio 对 shadow、active、范围边界和游客输出完成操作验证。当前归档为 `functional_validation: passed`、`manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`：未保存完整 Thread ID/Trace URL，不得伪造或写成 Trace 已验证。该 evidence debt 不阻塞 Gate 1 的只验收工作；路线和控制事件仍不接入本阶段。

### P2-01 Graph Shadow 归档（功能已验收，Trace 元数据待补）

`fa1e00f` 将既有 `atomic_read_plan.py` 接到旧 Graph 末端的审计 Shadow：旧路径完成后，从最近 Human 输入生成闭合只读候选，并仅写入 thread-local `atomic_read_plan_evaluations`。`read_only_active` 未开放，候选不执行、不产生游客正文、不写 TourState、VisitorProfile、proposal、StopProgram 或 NarrationCoverage。定向 46/46、完整 841/841 与 P0 8/8 均通过。负责人 Studio 正向验证记录的 Thread ID 为 `019fc3b7-67ea-77d2-8131-6a3b93a7fcd3`，候选为 `single_fact` + `controlled_knowledge`，且 `decision_kind=atomic_read_plan`；Trace URL/revision 未保存，状态为 `functional_validation: passed`、`manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`。详见 `p2_01_graph_shadow_handoff.md`。Gate 2 仍 pending，Gate 3 仍 blocked；P2-02/P2-03/P2-04 不得因此开启。

### P2-02 Route Proposal Graph Shadow（功能已验收，Trace 元数据待补）

`d0b61e0`/`44235c3` 将同一份旧 `RouteSelection` 包装为审计 proposal，而不重新选择、重新规划或改变旧 `direct_route` 的 `start_tour`/正文/正式状态。accepted 候选只写入 thread-local `route_proposal_evaluations`，并对旧路线记录 `matches_legacy=true`；10 分钟非法画像被记录为 `rejected_reason=invalid_profile_value`，旧的 20–120 分钟提示不变。定向 55/55、完整 852/852、P0 8/8 均通过。负责人 Studio 提供了三个 Thread ID，但未保存 Trace URL/revision；归档为 `functional_validation: passed`、`manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`。P2-02 active disabled，P2-03/P2-04 未开始；详见 `p2_02_route_proposal_shadow_handoff.md`。

### P2-03 Replan Proposal Graph Shadow（功能已验收，Trace 元数据待补）

`09a85c8`/`334ea7a` 将旧 P1-11 已产生的 `pending_replan_proposal` 只读包装为 thread-local `replan_proposal_evaluations`；不重新调用重规划器，不应用或取消 proposal，不改变旧游客正文或正式状态。Studio 人工验证：月台补充 40 分钟后的同一份旧 proposal 为 `accepted` 且 `matches_legacy=true`；未知位置保持旧澄清、不生成默认 proposal；取消后旧 preview 清空，Shadow 如实记录 `legacy_proposal_absent`。当前完整回归 860/860、P0 3/3 与 `git diff --check` 通过。完整 Thread ID、Trace URL/revision 与人工逐字段状态 diff 未保存，因此归档为 `functional_validation: passed`、`manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`。P2-03 active disabled；P2-04 未开始；Gate 3 仍 pending。详见 `p2_03_replan_proposal_shadow_handoff.md`。

### P2-04-A 普通状态事件 Graph Shadow（功能已验收，Trace 元数据待补）

`92ca888` 为普通 `tour_event` 增加纯 dry-run 审计：到达、讲解结束、确认完成、跳过、下一站和结束只读取状态快照；旧 Graph 仍是唯一执行者，且每个事件只调用一次 `handle_tour_event`。thread-local `state_transition_evaluations` 记录预期阶段、拒绝/原因码和与旧链实际结果的比对，不构成第二份 TourState。定向 24/24、完整 867/867、P0 3/3 均通过。Studio 人工操作已看到六类普通事件均为 accepted 且 `legacy_execution_observed=true`、`legacy_result_matches_shadow=true`；完整 Thread/Trace URL/revision 未保存，故归档为 `functional_validation: passed`、`manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`。P2-04-A active disabled；P2-04-B 重规划复合事件审计未开始；Gate 3 仍等待 P2-04-B 与最终验收。详见 `p2_04a_normal_event_shadow_handoff.md`。

### P1-11 confirm_replan_and_next Graph 可达性修复

`route_initial_request()` 已有合法复合目标 `confirm_replan_and_next`，但 `semantic_normalization` 的条件映射曾缺少该 key，导致本地 Studio 抛出 `KeyError`。最小修复仅将既有节点加入映射，保留冻结顺序 `apply_replan_proposal → next_stop`，不属于 P2 active 接管。定向 54/54、完整 869/869、P0 3/3 与 `git diff --check` 通过；负责人手动验证新路线只应用一次并输出下一站导航。未保存完整 Thread ID/Trace URL，状态为 `manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`。P1-11 confirm_replan_and_next Graph reachability: verified；P2-04-B: not started; prerequisite repaired。

### P2-04-B 重规划复合事件 Shadow（功能已验收，Trace 元数据待补）

在不接管旧 P1-11 的前提下，`replan_composite_evaluations` 只记录 preparation、候选生成、确认、合法 `apply_replan_proposal → next_stop` 与取消的旧链前后差异。它不调用事件执行器、状态适配器或路线规划器，也不构成第二份状态。定向 5/5、关联 66/66、完整 874/874、P0 3/3 和 `git diff --check` 通过。负责人 Studio 观察到复合确认 accepted、formal route changed、contract match 和 proposal 清空；取消保留原路线。完整 Thread/Trace URL/revision 未保存，归档为 `functional_validation: passed`、`manual_validation: passed_by_operator`、`langsmith_trace_status: metadata_unavailable`。P2-04-B active disabled；Gate 3 pending final P2 integration acceptance。详见 `p2_04b_replan_composite_shadow_handoff.md`。

这 8 步完成前，不建议开始语音、多语言、附近实时推荐或图数据库。它们依赖稳定的 Renderer、证据包、状态事件和工具权限；过早接入只会放大当前分散路由的问题。

## 17. 完成定义

本项目的“目标架构已实现”不能以流程图中的方框或文件是否存在判断，而应同时满足：

- Planner 只提出候选，所有执行均经过确定性 Gate。
- 陈家祠事实均有合格 evidence；一般模型补充不会越过项目事实边界。
- 所有状态变化经唯一事件/状态适配层，非法写入为 0。
- 规划前/导游中问答能力等价，问答后可恢复原导游流程。
- 路线和重规划只先产生 proposal，确认后才应用。
- 卡片、风格、语言和学术观点不改变基础事实、状态或资格。
- 游后数字来自实际到达和成功讲解记录，称号规则可审计。
- 周边和动态信息有来源、时效和失败关闭。
- 学术工作区不伪造来源、不越权使用全文、不污染导游状态。
- 文字、字幕和语音事实一致，所有内部字段只留在审计。
- 自动测试、LangSmith 实链、故障注入、线程隔离和回滚演练全部通过。

## Gate 3：P2 Shadow / 只读最终集成验收（已通过）

`5ee99ea` 完成 P2 最终 Shadow/只读集成验收：P2-01 原子多意图、P2-02 路线 proposal、P2-03 重规划 proposal、P2-04-A 普通状态事件、P2-04-B 重规划复合操作均保持 Shadow；P2-05 保持其已冻结的受控只读灰度契约。所有审计字段仅存在于当前 thread checkpoint，不能成为第二份 TourState、VisitorProfile、正式路线或 proposal。

Gate 3 定向 66/66、完整回归 877/877、P0 矩阵 3/3 和 `git diff --check` 通过。负责人完成四组 Studio 功能操作：游览中票务问答后继续导游、多意图安全澄清、60 分钟路线与旧选择一致、偏航后的确认新路线并前往下一站。未保存完整 Trace 元数据，统一标记 `manual_validation: passed_by_operator` 与 `langsmith_trace_status: metadata_unavailable`，不得写成 Trace 已验证。

```text
P2 integration functional validation: passed
P2 state-class active takeover: disabled
Gate 3: passed for shadow/read-only integration
```

详见 `p2_gate_3_integration_acceptance.md`。下一阶段在获得独立授权前不得开启任何路线、重规划或状态类 active takeover。

## P3 前置审计与执行顺序（2026-08-03）

以 `experiment/agent-orchestration-v2@9d744d3` 为基线的审计确认：P2 Gate 3 已通过 Shadow／只读集成，但所有状态类 active takeover 仍禁用。P3 必须按 `P3-01 模式契约 → P3-03 只读 CardDispatcher 候选 → P3-04 事实型 NarrationComposer/版式 → P3-05 分能力灰度` 推进，每步独立测试、独立提交和可回滚。

`P3-02` 是风险最低的核查项，但不应重复实现：当前唯一链路已是 `GuidancePolicy → compile_narration_style() → NarrationStylePolicy → narration_rendering`，只读取确认策略、未知/异常失败关闭为 neutral，且不改变证据、路线、TourState、VisitorProfile、StopProgram 或 NarrationCoverage。新建第二风格状态、第二画像或自由文本选风格都会违反既有 E5 契约。

P3-01 / CA-12 的模式归属、生命周期与知识问答恢复语义已由负责人冻结，
当前进入独立实现与测试阶段。它不得写入 VisitorProfile、TourState 或新的会话
事实源；完整审计、实现边界与验收记录见 `p3_preflight_audit_handoff.md` 和
`p3_01_journey_mode_handoff.md`。
