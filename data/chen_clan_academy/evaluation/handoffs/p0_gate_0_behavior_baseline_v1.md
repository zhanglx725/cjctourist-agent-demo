# P0-03 / CA-00 Gate 0 行为基线交接

## 冻结信息

- 基线提交：`56688f7d9bda505da2b426021553afb54a05c5ce`
- 分支：`main == origin/main`
- 冻结日期：2026-08-02
- 完整回归：770/770 通过，0 failure，0 error。
- P0 安全/游客输出矩阵：59/59 通过，0 failure，0 error。
- 执行解释器：`D:\VScode_Project\codexspace\codex_agent\.venv\Scripts\python.exe`
- 行为矩阵：`data/chen_clan_academy/evaluation/p0_gate_0_behavior_matrix_v1.yaml`

## Gate 0 结论

`conditional_pass`

自动化未发现安全建议、非法 TourState 写入、控制语句回落到自由 LLM/RAG、游客端内部字段泄漏或线程串线。此结论不是 `passed`：本提交尚无新的 LangSmith Trace，且 P1-04 的后西庭/后庭西侧权威空间关系仍由数据负责人外部确认。当前安全行为是澄清，不允许模型猜点位。

## 已冻结的非回归边界

- 到达不等于完成；仅 `confirm_stop_complete` 可写入 `visited_stop_ids`。
- `self_arrival` 记录真实审核位置，但不得推进正式路线；重规划先生成 proposal，确认后才应用。
- 安全规则优先于到达、拍照、路线和普通问答；失败与无证据保持关闭。
- 控制文本走确定性事件或澄清，不得回退自由导航或事实生成。
- 问答、讲解和拍照不写 TourState 或 VisitorProfile；显式点位只限定问答范围。
- 游客文本不显示来源编号、文件名、URL、内部 ID、原始 chunk 或 Trace 字段；结构化审计仍保留证据。
- 线程间隔离 TourState、VisitorProfile、qa_context、NarrationCoverage 与临时 proposal/candidate。
- 到达加问答、完成加问答、到达加重规划加问答当前一律澄清；原子多意图属于 P2。

## 已知项与后续顺序

1. 先执行矩阵中 `pending_for_56688f7` 的 LangSmith 用例并记录 thread、Trace、路径与状态 diff。
2. P1-04 保持 `blocked_external_data_review`，等待空间负责人确认；不得在 Agent 层添加猜测别名。
3. 仅当当前提交的 LangSmith 核心矩阵通过，且无新的阻塞安全/状态问题时，才能把 Gate 0 升级为 `passed`。
4. 在此之前，不开始 CA-01 AgentDecision、CA-02 Tool Registry、Policy Gate、Executor 或 Shadow Planner。
