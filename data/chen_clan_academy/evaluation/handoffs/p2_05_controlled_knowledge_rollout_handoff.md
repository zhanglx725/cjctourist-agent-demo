# P2-05 受控知识灰度接入第一阶段

## 范围

本轮只接入游览开始前、已有闭合计划的 `controlled_knowledge` 问答（当前为团队订单电子发票规则）。路线、重规划、到达、完成、跳过和其他控制事件继续走原链，不在本轮改变。

## 配置

`CJC_READ_ONLY_ROLLOUT_MODE`：`off`、`shadow`、`read_only_active`。

`CJC_READ_ONLY_ROLLOUT_CAPABILITIES`：逗号分隔的能力白名单；本轮唯一可启用值为 `controlled_knowledge`。无效模式失败关闭为 `off`。

## 运行语义

- `off`：保持 `direct_rag` 的既有受控知识路径。
- `shadow`：先计算旧链正文，再运行 `AgentDecision → Policy Gate → Executor → reviewed_controlled_knowledge`；游客仍只看到旧链正文。比较记录保存在当前 thread 的 `controlled_rollout_evaluations`。
- `read_only_active`：仅当候选通过 Gate、Executor、evidence 和游客输出校验时采用候选正文；候选失败时使用同一份审核 evidence 的旧受控渲染器。不会向游客暴露检索原文或退回原始 RAG 倾倒。

## 验证

- 定向回归：26 项通过。
- 全量回归：831 项通过，0 failure，0 error，35.528 秒。
- 覆盖：无效模式失败关闭、能力白名单、off 保持旧路由、shadow 差异记录、active 候选采用、候选异常回退旧受控答案、thread ID 隔离、路线请求未接入新链。

## 归档状态与人工实链记录

```yaml
functional_validation: passed
manual_validation: passed_by_operator
langsmith_trace_status: metadata_unavailable
tested_branch: experiment/agent-orchestration-v2
tested_commit: "72e9c92"
worktree_at_validation: clean
thread_id: not_recorded
trace_url: unavailable
trace_revision_id: unavailable
```

上述状态只表示负责人已在 Studio 完成功能操作并提供节点、正文和审计字段截图；它不等同于 `langsmith_verified: true`，也不表示存在可追溯的 Trace URL。不得补造 Thread ID、Trace URL 或 revision ID。

- `shadow` 配置：`CJC_READ_ONLY_ROLLOUT_MODE=shadow`、`CJC_READ_ONLY_ROLLOUT_CAPABILITIES=controlled_knowledge`。负责人测试团队订单电子发票规则的标题式、期限式和开票后修改/退票式问法；路径为 `semantic_normalization → controlled_knowledge_rollout → llm_think`，审计截图为 `candidate_shadow`、`candidate_status=ok`、`legacy_status=ok`、`same_message=true`。
- `read_only_active` 配置：`CJC_READ_ONLY_ROLLOUT_MODE=read_only_active`、`CJC_READ_ONLY_ROLLOUT_CAPABILITIES=controlled_knowledge`。同一受控知识问答路径的审计截图为 `candidate_active`、`candidate_status=ok`、`legacy_status=ok`、`same_message=true`；最终正文与旧链等价，只含审核规则和官方订单页时效提示。
- 边界人工检查：路线请求进入 `profile_collection`、到达语句进入 `tour_event`、普通“陈家祠是什么”进入 `tour_qa`，均未进入 `controlled_knowledge_rollout`；索取原始资料、来源编号和链接时，游客正文未泄露 source ID、文件名、URL、检索字段或原始 evidence。
- 状态观察：负责人报告读操作未改变 `TourState`、`VisitorProfile`、proposal、`StopProgram` 或 `NarrationCoverage`；本轮未保存结构化 state diff 导出，故该观察的追溯元数据为 `metadata_unavailable`，不是可复查的 Trace 断言。
- fallback：自动化回归覆盖候选异常时回退旧受控渲染、不得回退原始 RAG；本轮 Studio 未故意注入故障，故人工故障注入为 `not_run`。
- 自动化：P2-05 定向回归 `26/26` 通过；完整回归 `831/831` 通过（0 failure、0 error，35.528 秒）；P0 定向安全/游客输出矩阵最近记录为 `59/59` 通过。

## Gate 1 准入与证据债务

P2-05 的功能和人工实链操作已完成，当前 commit 与干净工作区已确认，且没有已确认功能失败；因此 **允许开始 Gate 1 的只验收工作**。Trace 元数据缺失不应阻塞 Gate 1，但必须保持为 evidence debt：

- 未记录本轮完整 Thread ID、Trace URL 和 Trace revision ID；
- 后续若能重新定位 Trace，可补充链接，但不得用旧提交的 Trace 代替 `72e9c92` 的证据；
- Gate 1 可做 schema、Registry、Policy Gate、Executor 与旧路径兼容性验收；
- 第二个只读能力可做离线与 shadow 测试；其进入 `read_only_active` 前，应单独记录真实 Trace，或明确标记 `metadata_pending`；
- 路线 proposal、重规划 proposal、到达、完成、跳过和结束事件仍等待 Gate 1 通过。

回滚方式：将 `CJC_READ_ONLY_ROLLOUT_MODE=off`（或从 capability 白名单移除 `controlled_knowledge`）并重启服务，即恢复既有 `direct_rag` 受控知识路径。

临时服务必须按 `run_langgraph_studio.cmd` 的顺序设置 `chcp 65001`、`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8` 并调用 `activate.bat`；否则 LangGraph API 子进程可能按 GBK 读取 OpenAPI 文件而启动失败。临时服务日志不得写入工作区，否则 watchfiles 会重载 in-memory runtime 并清空 thread。

## 尚未完成

Trace 元数据（完整 Thread ID、Trace URL、Trace revision ID）待补采；这是一项 evidence debt，不得写成 LangSmith Trace 已验证。CLI 的完整双 thread 交互仍需在不重载服务的会话中复测；离线回归已覆盖其 `MemorySaver` 配置与 thread-local 审计记录。
