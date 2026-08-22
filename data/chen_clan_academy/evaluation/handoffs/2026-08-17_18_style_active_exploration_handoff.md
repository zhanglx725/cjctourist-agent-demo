# 18 种角色全场景 Active 试运行交接文档

日期：2026-08-17  
工作分支：`experiment/agent-orchestration-v2`  
工作目录：`D:\VScode_Project\codexspace\codex_agent`

## 1. 本轮目的

以古风书生的成熟主线为基线，开启 18 种审核角色在已接入场景中的 Active 试运行。

本轮不是取消安全校验，更不是“默认通过”。每个角色候选仍必须通过事实边界、风格、布局、预算、服务尾部和公共输出安全校验；不通过时自动保留旧链正文。

本轮人工验收以“游客最终正文是否自然、是否符合风格”为主，不要求逐条展开 LangSmith 节点。出现异常时再按本文第 7 节补充定位。

## 2. 当前 Active 配置

本地 `.env` 当前用于试运行的配置为：

```env
CJC_READ_ONLY_ROLLOUT_MODE=read_only_active
CJC_READ_ONLY_ROLLOUT_CAPABILITIES=role_narration,role_qa

PRODUCT_ROLE_ACTIVE_ENABLED=true
PRODUCT_ROLE_ACTIVE_STYLES=neutral,child,family,student_research,professional,listen_only,mixed_group,dominant_ceo,cute_junior,ancient_scholar,warm_sister,bestie_chat,buddy_guide,exploration_game,photo_guide,hostel_scholar,xiguan_young_master,cantonese_storyteller
PRODUCT_ROLE_ACTIVE_SCENES=route_planning,route_opening,stop_guidance,tour_qa,qa_follow_up_detail,navigation,tour_closing,replan_presentation
PRODUCT_ROLE_ROLLOUT_PERCENTAGE=100
PRODUCT_ROLE_KILL_SWITCH=false
PRODUCT_ROLE_VALIDATION_LEVEL=strict
PRODUCT_ROLE_FALLBACK_POLICY=legacy
PRODUCT_ROLE_NATURAL_DISCOURSE_ENABLED=true
```

修改配置后必须重启 LangGraph，并使用新的 Thread。不得把真实 API Key 写入本文或提交到仓库。

## 3. 18 种已加入白名单的角色

```text
neutral
child
family
student_research
professional
listen_only
mixed_group
dominant_ceo
cute_junior
ancient_scholar
warm_sister
bestie_chat
buddy_guide
exploration_game
photo_guide
hostel_scholar
xiguan_young_master
cantonese_storyteller
```

## 4. 当前实现与证据状态

| 范围 | 当前状态 | 说明 |
|---|---|---|
| 古风书生主线 | 成熟基线 | 路线规划、路线开场、点位讲解均为既有主展示 Active 范围；后续确定性服务链保持稳定。 |
| 儿童点位讲解 | 已有真实 Active 发布证据 | 已确认 `validation_status=accepted`、`commit_decision=role_candidate_published`、`active_takeover=true`、`fallback_used=false`。 |
| 儿童重复表达 | 已修复，待最新回归 | 旧问题是 `repeated_role_expression` 导致回退；现已为组件轮换和重复句检测增加修复。 |
| 儿童事实呈现 | 已统一到通用架构 | 所有风格共用“事实呈现 → ContentPlan → generation → validation → commit/fallback”；儿童仅使用受控摘要策略，保留 `source_statements` 审计边界。 |
| 18 风格点位讲解 | 已开启试运行 | 已有 18 风格 × 空间/工艺/对象的 54 条离线基础矩阵；本轮需要真实最终正文快速审阅。 |
| 路线规划、路线开场 | 已开启试运行 | 已有角色候选与 Active 接管路径；需以真实 Thread 观察最终正文。 |
| 普通问答、追问 | 已开启试运行 | 角色问答 Active 链已接入；child 有历史真实 Active 样本，其余风格待本轮试运行。 |
| 引路、结束语 | 已开启试运行 | 已有候选、校验与 Active 接管路径；表达以安全包装既有确定性路径/总结正文为主。 |
| 重规划说明 | 未真正实现角色化发布 | 虽已放入产品场景配置，但当前没有独立的角色候选、校验和提交节点；配置本身不会让该场景变成角色化 Active。 |

## 5. 架构边界

### 5.1 统一主链

```text
审核事实/确定性业务正文
→ 风格化事实呈现
→ ContentPlan
→ 角色候选生成
→ 事实、风格、布局、安全、预算校验
→ Active commit 或 legacy fallback
```

儿童与古风书生不再拥有两套发布架构：

- 古风书生和多数风格采用“审核事实逐字呈现”策略；
- 儿童采用“受控摘要 + 审核来源追踪”策略；
- 两者都走相同的生成、校验、提交和回退链。

儿童允许温和比喻、探索感和轻度拟人，但不得新增真实人物、年份、事件、用途、空间关系或传说细节；传说必须保留“传说里 / 人们说”等不确定性标记。

### 5.2 不得放开的边界

不得修改或绕开：

- TourState、路线、Coverage 和状态写入合同；
- 审核知识、对象注册表和审核路线；
- 严格 validation 与 legacy fallback；
- 路线方向、行走时间、安全提示和已完成内容的确定性来源。

## 6. 启动与自动化测试

### 6.1 启动

在项目根目录运行：

```cmd
cd /d D:\VScode_Project\codexspace\codex_agent
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
.\.venv\Scripts\langgraph.exe dev --port 2037
```

若服务此前已经启动，必须先停止，再启动；随后在 Studio/LangSmith 中新建 Thread。

### 6.2 必跑自动化测试

```cmd
.\.venv\Scripts\python.exe -m unittest test_role_narration_style_matrix.py test_e5_narration_rendering.py test_narration_content_plan.py test_role_narration_generation.py test_role_discourse.py test_role_narration_graph.py
```

预期：全部通过。当前 Codex 受限环境中的 `.venv` 启动器指向失效的 Windows Store Python，无法代跑；必须以操作者本机 VS Code 终端结果为准。

## 7. 快速人工验收：只看最终正文

### 7.1 推荐抽样风格

第一轮只快速观察下列 6 种代表风格：

```text
ancient_scholar
child
professional
listen_only
exploration_game
cantonese_storyteller
```

若六种均正常，再按其余 12 种逐一轮换。不要在同一 Thread 连续切换大量风格后判断点位效果；优先每个风格使用新 Thread，避免 Coverage、路线进度或旧候选影响观察。

### 7.2 完整主线输入

每种风格执行一次以下流程。风格选择可使用前端入口或项目已支持的风格切换表达。

```text
我有30分钟，使用【目标风格】，帮我安排参观路线
开始导游
我到了
灰塑是什么？
再详细一点
完成本点，前往下一站
结束游览
```

### 7.3 只需检查的游客可见结果

| 场景 | 看什么 | 合格表现 |
|---|---|---|
| 路线规划 | 开头与路线说明 | 风格存在；站点、时间、顺序和安全提示仍准确。 |
| 路线开场 | 开场人格与第一站衔接 | 风格连续，不重复口头禅，不丢失到站说明。 |
| 点位讲解 | 开头、中段、结尾 | 有该风格的节奏；事实清楚；无栏目标题、后台术语和成人资料卡堆砌。 |
| 问答与追问 | 回答风格与事实范围 | 风格延续；不扩写未问内容；不伪造知识。 |
| 引路 | 下一站路径提示 | 方向、路径、时间和安全提醒不变；角色表达不压过行动信息。 |
| 结束语 | 实际游览总结 | 只总结真实完成内容，不把跳过点说成完成。 |

`listen_only` 额外要求：没有问号、任务、拍照要求或强制互动。  
`child` 额外要求：有故事/观察感，但不堆“小线索”“新朋友”，不出现审核/证据/关联等后台口吻。  
`photo_guide` 额外要求：首次到站不自动插入拍照建议；用户明确询问拍照时才走拍照链。  
`cantonese_storyteller` 额外要求：传说与事实语气分明，不自行补剧情或伪造粤语俗语。

### 7.4 异常记录格式

发现问题时，不必先展开节点。直接记录：

```text
日期：
style_id：
场景：route_planning / route_opening / stop_guidance / tour_qa / qa_follow_up_detail / navigation / tour_closing
游客输入：
最终正文：
问题类型：风格缺失 / 重复表达 / 成人化 / 后台术语 / 事实错误 / 路线错误 / 明显回退 / 其他
截图：
```

收到“style_id + 场景 + 最终正文”即可定向修复，避免对 18 种风格同时修改。

## 8. 出现异常时的最小定位

只有在最终正文明显不对时，才展开对应场景的审计：

```text
路线规划/开场/引路/结束语：route_role_narration_evaluations
点位讲解：narration_validation → narration_commit
问答/追问：qa_role_narration_validation → qa_role_narration_commit
```

重点只看：

```text
validation_status
reason_codes
active_takeover
fallback_used
commit_decision
```

不需要检查 `visitor_localization.api_called`；当输入本来是简体中文时，`source_already_target + api_called=false` 是正常的翻译跳过行为。角色模型是否调用应查看相应 generation 节点的 `model_called`。

## 9. 后续优先级

1. 运行第 6.2 节测试，确认最新儿童架构统一改动不回归；
2. 完成第 7 节六种代表风格的完整主线快速审阅；
3. 对异常风格逐个修复，不改变古风书生基线；
4. 再补齐其余 12 种风格的最终正文审阅；
5. 单独实现并测试 `replan_presentation` 的候选、验证、提交和回退链；
6. 在有足够真实 Active 证据后，更新阶段 3/阶段 4 的 verified 状态。

## 10. 当前工作区注意事项

当前存在尚未提交的代码与文档修改，包括儿童表达、事实呈现统一、组件去重和相关测试。未执行提交或推送。工作区还有未跟踪的嵌套目录 `cjctourist_agent/`，提交时不得使用 `git add .`，应逐文件暂存。
