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

## 本地实链记录

- `shadow`：thread `019fc2f8-4095-7e72-aa81-d4e66faa930a`。节点为 `semantic_normalization → controlled_knowledge_rollout → llm_think`；审计为 `candidate_shadow`、`candidate_status=ok`、`same_message=true`；`TourState`、`VisitorProfile` 均为 null。
- `read_only_active`：thread `019fc2fa-24e4-7c83-9552-a42ef1da1c3a`。同一节点链；审计为 `candidate_active`、`candidate_status=ok`、`same_message=true`；`TourState`、`VisitorProfile` 均为 null。
- 两项都使用“团队订单电子发票规则”，最终正文只含审核规则与官方订单页时效提示，不含 source ID、文件名、检索字段或原始 evidence。

临时服务必须按 `run_langgraph_studio.cmd` 的顺序设置 `chcp 65001`、`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8` 并调用 `activate.bat`；否则 LangGraph API 子进程可能按 GBK 读取 OpenAPI 文件而启动失败。临时服务日志不得写入工作区，否则 watchfiles 会重载 in-memory runtime 并清空 thread。

## 尚未完成

须在 LangSmith UI 中按上述 Thread ID 关联并归档 Trace URL。CLI 的完整双 thread 交互仍需在不重载服务的会话中复测；离线回归已覆盖其 `MemorySaver` 配置与 thread-local 审计记录。
