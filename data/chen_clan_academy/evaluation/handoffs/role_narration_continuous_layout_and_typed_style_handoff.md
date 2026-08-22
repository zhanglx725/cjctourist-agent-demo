# 18 种角色化点位讲解：统一排版与分内容类型风格化交接

## 1. 交接目的

本文交接本轮“18 种角色化点位讲解的统一排版与分内容类型风格化”改造，供后续开发、LangSmith Studio 人工验收和比赛演示准备使用。

本轮只修改点位讲解角色链：

```text
stop_guidance
→ narration_content_plan
→ role_narration_generation
→ narration_validation
→ narration_commit / deterministic_narration_fallback
```

未修改 TourState、路线、审核数据、知识检索、Coverage 业务写入规则，也未把途中普通问答扩展为强制角色化。

## 2. 当前代码基线

```text
branch: experiment/agent-orchestration-v2
parent_commit_before_this_change: 12a0b97
handoff_date: 2026-08-14
local_related_regression: 134/134 passed
git_diff_check: passed
studio_full_18_style_manual_acceptance: pending
remote_langsmith_54_case_rerun: pending
```

交接提交本身请以远程该分支最新提交为准。文档不记录自身提交哈希，避免 amend 后哈希失真。

## 3. 本轮解决的问题

改造前存在以下问题：

1. 不同风格成功发布后的排版不统一，正文可能显示 `【工艺背景】`、`【观察对象】`、`【下一步】`。
2. 旧链栏目正文中夹带的旧风格表达可能被内容计划误当作不可变审核事实，导致 18 种角色共享同一套中段话术。
3. 工艺开场可能有风格，但空间、观察对象、纹样和长讲解中段又退回普通说明。
4. 模型仍可能在事实令牌周围生成自由连接语，带来 `～`、`。。`、内部字段、事实扩写和排版漂移风险。
5. `narration_commit` 会在验证后的候选后面再次拼接旧链 `【下一步】` 后缀，使最终游客正文绕过单一验证门。

## 4. 已完成实现

### 4.1 审核渲染器输出事实单元

`narration_rendering.py` 在原有旧链游客正文之外，新增只用于角色链的 `fact_units` 审计数据：

```text
unit_id
topic_kind: space / craft / ornament
statements: 审核渲染器实际选中的原句
required
```

工艺原句来自 E5 已选中的审核工艺证据；对象原句来自已解析的审核对象详情。原始栏目标题不进入事实单元。

旧链游客正文仍由原渲染器生成，未被改版；因此 fallback 仍有完整兼容文本。

### 4.2 ContentPlan 只接受可审计事实单元

`narration_content_plan.py` 已升级为 `narration_content_plan_v3`：

- 每条事实可计算 `unit_id` 与 `topic_kind`；
- 事实顺序取自审核渲染顺序；
- 一个事实单元中的每个 statement 单独成为不可变事实令牌；
- 显式空间请求只保留空间事实；
- 显式工艺请求保留该工艺的全部审核 statement；
- 显式对象/纹样请求保留对象的全部审核 statement；
- 整站讲解按审核顺序保留多个工艺和对象事实单元。

不再从带风格的旧链栏目正文反向猜测事实。旧 checkpoint 若没有 `fact_units`，ContentPlan 会以 `fact_units_unavailable` 失败关闭，随后发布完全不变的旧链正文。

### 4.3 18 风格 × 3 内容类型组件

`point_narration_components_v1.yaml` 的配置 Schema 已升级为 `point_narration_components_v2`，layout 固定为 `continuous_narration`。

18 个 style_id 均配置以下 12 组组件，每组至少 2 个候选短句：

```text
opening
space_intro / space_observation / space_transition
craft_intro / craft_observation / craft_transition
ornament_intro / ornament_observation / ornament_transition
appreciation
closing
```

加载时严格检查：

- 18 个风格必须完整；
- 12 组组件必须完整且每组至少 2 条；
- 不得包含 source、node、route、URL、年份等事实或内部字段；
- 不得包含栏目标题、Markdown、换行、`～`、连续标点；
- interaction mode 为 none 的角色不得配置问题、拍照或动作请求。

古风书生的空间、工艺和对象段分别使用观照、层递、移目和收笔式表达；奶气学弟分别使用轻快短句承接空间、工艺和对象，但不使用撒娇堆词和波浪号。其余 16 种角色也按词汇、节奏、观察视角和收束方式区分。

### 4.4 模型只提交事实令牌

模型 `public_text` 只允许类似：

```text
[[FACT_000]][[FACT_001]][[FACT_002]]
```

禁止模型生成任何连接语、空格、换行、标点、互动或 Markdown。

以下情况直接拒绝：

- 非法或未知令牌；
- 必需令牌缺失或重复；
- 事实 ID 分区错误；
- 令牌顺序改变；
- 令牌之间或两端混入任何自由文本。

模型调用仍使用现有有限超时保护；不增加重试或无限等待。

### 4.5 服务端确定性交替渲染

通过令牌校验后，服务端按下列顺序生成成功候选：

```text
角色 opening
→ 当前 topic_kind intro
→ 不可变审核事实
→ 同单元 topic observation / 跨单元 topic transition
→ 下一不可变审核事实
→ appreciation
→ closing
```

同一轮按组件索引轮换，避免相邻重复。事实原字、原顺序、原次数不变；角色表达有上限并计入剩余讲解预算，超预算直接回退，不删除事实。

### 4.6 连续游客排版合同

成功进入 `narration_commit` 的角色正文必须：

- 只输出连续自然导览正文；
- 不含 `【……】` 栏目标题；
- 不含 Markdown 标题、列表或编号；
- 不含内部字段；
- 不含换行制造的资料卡片式分块；
- 不含 `～`、`。。`、连续逗号或连续标点；
- 由前端负责视觉自动换行。

`narration_commit` 现在只发布 `narration_validation` 已接受的原候选，不再追加旧链 `【下一步】` 或 `【观察提示】`。这样 commit 不承担第二次隐式渲染，也不会绕过验证。

### 4.7 验证、Trace 与回退

新增或强化的 reason codes 包括：

```text
layout_heading_leak
layout_markdown_leak
layout_spacing_invalid
layout_not_continuous
malformed_punctuation
space_style_coverage_incomplete
craft_style_coverage_incomplete
ornament_style_coverage_incomplete
style_component_topic_mismatch
repeated_style_component
style_coverage_incomplete
approved_statement_order_changed
invalid_fact_token_order
model_connector_text_forbidden
```

Trace 重点字段：

```text
layout_passed
layout_reason_codes
style_quality_passed
style_quality_reason_codes
fact_unit_ids
fact_unit_topic_kinds
commit_decision
fallback_used
active_takeover
state_writes
```

任一事实、排版、风格、预算、内部字段、安全或互动检查失败，均进入 `deterministic_narration_fallback`：

```text
validation_status = rejected
fallback_used = true
commit_decision = legacy_fallback_published
legacy_message_preserved = true
state_writes = []
```

fallback 不去除标题、不清洗标点、不改写旧链，因为它承担的是安全兼容与原文恢复职责。统一排版只约束成功的角色 Active 发布路径。

## 5. 修改文件

核心实现：

- `agent_graph.py`
- `guide_program_evidence.py`
- `narration_rendering.py`
- `narration_content_plan.py`
- `role_narration_generation.py`
- `narration_validation.py`
- `narration_style_policy.py`
- `data/chen_clan_academy/narration_styles/point_narration_components_v1.yaml`

新增或更新测试：

- `test_role_narration_continuous_layout.py`
- `test_narration_content_plan.py`
- `test_role_narration_style_matrix.py`
- `test_role_narration_generation.py`
- `test_role_narration_graph.py`
- `test_role_mode_shadow.py`
- `test_role_narration_langsmith_runner.py`

## 6. 自动化验证结果

相关离线回归：

```text
Ran 134 tests in 26.582s
OK
```

其中包含：

- 18 风格 × space/craft/ornament = 54 条成功发布矩阵；
- 每条 accepted、进入 `narration_commit`、`active_takeover=true`、`fallback_used=false`；
- 事实逐字一次、统一连续排版、内容类型组件匹配；
- ContentPlan 事实单元、作用域筛选和旧 checkpoint 失败关闭；
- 非法令牌、乱序令牌、模型自由连接语回退；
- 标题泄漏、类型错配与风格覆盖 reason code；
- 模型超时、格式错误、事实漂移、内部字段、互动违规、超预算回退；
- Coverage 提交幂等和 fallback 旧链保留；
- LangSmith dataset / fault dataset runner。

额外检查：

```text
python -m py_compile: passed
git diff --check: passed
style_count: 18
component_groups_per_style: 12
all_component_groups_have_at_least_two_phrases: true
```

项目完整自动发现测试曾尝试运行，但当前执行环境无法连接 LangSmith APAC 与 HuggingFace，在线集成用例会指数重试。本轮相关 134 项离线测试不依赖上述网络并已全部通过。

## 7. 下一步工作

### P0：Studio 新线程人工验收

必须使用全新 Thread。旧 checkpoint 没有 `fact_units`，按设计会回退旧链，不能作为新成功路径的验收样本。

先验收古风书生和奶气学弟：

1. 建筑空间；
2. 灰塑、木雕或石雕工艺；
3. 独角狮、福禄寿、杏林春燕等对象/纹样；
4. 30 分钟整站多事实单元长讲解。

游客正文验收：

- 无 `【工艺背景】`、`【观察对象】`、`【下一步】`；
- 无列表、Markdown、多余空行和异常标点；
- 开头、中段、结尾均有人设；
- 空间、工艺和对象段使用对应内容类型组件；
- 审核事实逐字、顺序、次数不变；
- 古风书生文雅但不伪古文、不新增典故；
- 奶气学弟轻快但不幼稚、不使用波浪号。

### P1：补齐 18 风格真实 Trace 矩阵

每个风格至少采集 space、craft、ornament 各 1 条真实 Trace，共 54 条。保存：

- Thread ID；
- Run/Trace URL；
- 游客正文顶部、中段、结尾截图；
- 完整节点路径截图；
- `narration_content_plan` 的 fact/unit/topic；
- `narration_validation` 的 layout/style/fact 字段；
- `narration_commit` 的 takeover/fallback/decision/state_writes。

不要只保存游客正文截图；必须能证明最终正文来自 `narration_commit` 而非 fallback。

### P2：运行远程 LangSmith 数据集

在允许联网且已配置 API Key 的环境中，对现有数据集重新运行新版本：

```text
chen-clan-academy-role-narration-stop-guidance-v1
```

远程验收需把旧的“模型生成角色连接语”预期更新为“模型仅生成事实令牌，服务端确定性生成角色组件”。重点核对 54 条基础样本和故障样本的 commit/fallback 决策。

### P3：根据人工样本微调组件

只允许修改审核表达组件和对应测试，不要修改事实、路线、状态或检索：

- 若人设仍只在开头明显，优先调整该风格的 type observation/transition；
- 若表达机械重复，增加同类型候选短句并保持无事实断言；
- 若长讲解频繁超预算，先缩短组件，不得删除事实；
- 若某风格互动过强，收紧其 interaction contract 和组件措辞。

每次修改后至少重跑 54 条矩阵和 fault fallback 测试。

### P4：人工验收通过后再进入演示素材

当前不要直接修改比赛演示视频或演示文稿。只有当 18 风格 Studio 矩阵、重点长讲解和远程 LangSmith 结果通过后，才更新比赛演示素材和 `competition_scope_and_demo_baseline.md` 的最终基线提交。

## 8. Studio 启动参考

PowerShell 在项目目录执行：

```powershell
$env:CJC_READ_ONLY_ROLLOUT_MODE = "read_only_active"
$env:CJC_READ_ONLY_ROLLOUT_CAPABILITIES = "role_narration"
$env:ROLE_ACTIVE_ENABLED = "true"
$env:ROLE_ACTIVE_STYLES = "neutral,child,family,student_research,professional,listen_only,mixed_group,dominant_ceo,cute_junior,ancient_scholar,warm_sister,bestie_chat,buddy_guide,exploration_game,photo_guide,hostel_scholar,xiguan_young_master,cantonese_storyteller"
$env:ROLE_ACTIVE_SCENES = "route_planning,route_opening,stop_guidance"
& .\.venv\Scripts\langgraph.exe dev
```

如果本机 PowerShell 禁止执行 `Activate.ps1`，无需激活虚拟环境，直接使用 `.venv\Scripts\langgraph.exe` 和 `.venv\Scripts\python.exe`。

## 9. 回滚方式

运行时快速回滚：

```powershell
$env:CJC_READ_ONLY_ROLLOUT_MODE = "off"
```

或从 `CJC_READ_ONLY_ROLLOUT_CAPABILITIES` 移除 `role_narration` 后重启服务。旧链、旧游客正文和 Coverage 提交逻辑仍保留。

代码回滚时应整体回滚本交接对应提交，不要只回滚 validation 或 commit，否则可能造成候选结构、配置 Schema 与验证合同不一致。

## 10. 明确未处理内容

- 未修改和未提交本地视频输出；
- 未修改和未提交 DOCX、PDF；
- 未处理 `tools/_vendor_tts`；
- 未开放普通途中问答的 18 风格强制覆盖；
- 未开始比赛演示素材更新；
- 未宣称 18 风格 Studio 人工验收已完成。
