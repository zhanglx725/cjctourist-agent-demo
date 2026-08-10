# P2-01 多意图原子只读计划 Graph Shadow 归档

## 归档状态

```yaml
branch: experiment/agent-orchestration-v2
tested_commit: fa1e00f25d29481e6fb17777486b77a3bf365102
functional_validation: passed
manual_validation: passed_by_operator
langsmith_trace_status: metadata_unavailable
thread_id: 019fc3b7-67ea-77d2-8131-6a3b93a7fcd3
trace_url: unavailable
trace_revision_id: unavailable
```

Thread ID 来自负责人提供的 Studio 截图；本轮未保存 Trace URL 或 revision ID，不能写成 LangSmith Trace 已验证。

## 实现与范围

- 实现提交：`2c75097`（P2-01 Shadow）、`196e792`（分句兼容）、`fa1e00f`（从末端旧链路后的最近 Human 输入取审计原话）。
- Graph 在旧确定性路径结束后进入 `atomic_read_plan_shadow`；该节点只把候选写入 thread-local `atomic_read_plan_evaluations`，随后结束。
- 仅 `shadow` 生效；`read_only_active` 未为 P2-01 开放。
- 不执行工具，不调用 `tour_interaction`，不调用 `start_tour`，不接入 P2-02/P2-03/P2-04。

## 自动化验证

| 范围 | 结果 |
|---|---|
| P2-01 定向 | 46/46 OK |
| 完整 unittest 回归 | 841/841 OK |
| P0 安全/游客输出矩阵 | 8/8 OK |
| `git diff --check` | OK |

定向测试包含：纯只读双问题候选、英文/中文分句、带控制动作的澄清候选、空/单问题、Shadow 在旧链路追加 AI 正文后仍读取最近 Human 输入。

## 人工 Studio 验收

正向输入：`陈家祠什么时候开始筹建,再团队订单电子发票规则是什么？`

实际节点路径：`semantic_normalization -> direct_rag -> llm_think -> atomic_read_plan_shadow`。

审计结果：

```yaml
decision_kind: atomic_read_plan
reason_codes: []
candidates:
  - intent: fact_question
    requested_capability: single_fact
    evidence_span: 陈家祠什么时候开始筹建
    side_effect_level: read_only
  - intent: service_rule
    requested_capability: controlled_knowledge
    evidence_span: 团队订单电子发票规则是什么？
    side_effect_level: read_only
planner_mode: shadow
```

负责人亦操作了“问答后继续”“到达+问答+下一站”“到达+问答+重规划”“时长+问答+重规划”和危险拍照混合请求；Shadow 仅给出 `clarification` 或空候选，未执行子动作。危险拍照仍走既有 `tour_qa` 确定性安全通道。

## 新旧路径、状态与回退

- 游客正文：仍由旧 `direct_rag -> llm_think` 或既有确定性通道产生；Shadow 不渲染候选正文。
- TourState、VisitorProfile、proposal、StopProgram、NarrationCoverage：P2-01 没有写入代码路径；本轮没有保存可逐字段复核的 Studio `View state` 差异，因此状态 diff 归档为 `metadata_unavailable`，不伪造“人工 diff 为零”。自动化覆盖只读无写入边界。
- Shadow 失败或配置为 `off` 时返回空更新，旧路径不受影响；不会回退为无边界自由执行或状态操作。
- Thread 隔离：审计记录带 thread ID 并存于 Graph checkpoint；自动化覆盖其线程作用域。除上述截图 Thread ID 外，未归档完整 Trace 元数据。

## 限制、回滚与后续

- P2-01 active execution：disabled。
- Gate 2：pending；Gate 3：blocked。
- P2-02 route proposal、P2-03 replan proposal、P2-04 state transition adapter 均未接入 Graph。
- 回滚：将 `CJC_READ_ONLY_ROLLOUT_MODE=off` 或从当前分支回退 `fa1e00f`、`196e792`、`2c75097` 三个 P2-01 提交；旧 Graph 路径仍保留。
