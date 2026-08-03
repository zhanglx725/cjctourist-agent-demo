# P3 Preflight Audit and Sequencing Handoff

## Archive status

```yaml
branch: experiment/agent-orchestration-v2
baseline_commit: 9d744d3e90c2df63b1a1c1c140be1022918c3fc3
remote_sync: already_up_to_date
p2_gate_3: passed_for_shadow_read_only_integration
p2_state_class_active_takeover: disabled
implementation_status: preflight_completed
manual_validation: not_run
langsmith_trace_status: not_run
```

## What was audited

The audit read the current P2 Gate 3 archive and P2 handoffs, the P3 plan,
the controlled-Agent architecture plan, progress/collaboration/learning
records, and the live style/rendering implementation.

P2 remains a bounded control plane: the old Graph owns all route, replan and
state execution; P2 observations are thread-local audits only.  No P3 task may
enable state-class active takeover.

## P3 decomposition

| Step | Deliverable | Dependency | Authority | Current result |
| --- | --- | --- | --- | --- |
| P3-00 | preflight audit and executable sequence | P2 Gate 3 | documentation only | completed by this handoff |
| P3-01 / CA-12 | freeze classic/custom mode ownership and interruption/recovery contract | owner decision recorded 2026-08-03 | product and state-contract decision | implementation in progress; see `p3_01_journey_mode_handoff.md` |
| P3-02 | connect the existing narration-style policy without a second profile | P3-01 only if a selectable product mode changes style lifecycle | pure display policy | already implemented on the E5 legacy rendering path; no duplicate implementation is safe |
| P3-03 / CA-13 | read-only CardDispatcher enhancement candidates | approved P3-01 mode contract, E5 evidence, card eligibility | proposal/read-only only | not started |
| P3-04 | facts-only narration composition and visitor layout | P3-02 equivalence regression and P3-03 output contract | renderer only | not started; P2-07 remains a separate layout-quality acceptance item |
| P3-05 | per-capability Graph rollout | each prior capability's tests and review | existing P2 rollout controls | not started; state-class active takeover remains prohibited |

## Lowest-risk P3 finding

The lowest-risk candidate was P3-02.  It requires no new production code at
this baseline because the single existing chain is already:

```text
GuidancePolicy -> compile_narration_style() -> NarrationStylePolicy
-> render_guidance_evidence() / narration_rendering
```

The policy reads confirmed `GuidancePolicy`, not free text or a copied
`VisitorProfile`; it has the seven approved style IDs, fails closed to
`neutral`, and does not change evidence, source IDs, route, TourState,
VisitorProfile, StopProgram, or NarrationCoverage. Existing style integration
tests cover deterministic selection, fact equivalence, `listen_only`, loader
failure and input immutability. Creating a second Agent tool, style state, or
profile field now would duplicate a protected source of truth rather than
advance P3 safely.

## Planning--implementation conflict

```text
计划要求：P3 继续接入经典/定制模式、卡片调度和讲解组织。
负责人确认后的实施结论：既有 `tour_mode` 继续只表示交互形式
(`chat` / `button_guided` / `continuous`)；同一 interaction/session
control 的独立 `journey_mode` 表示产品模式 (`classic` / `custom`)。
影响范围：P3-01, selectable narration styles, CardDispatcher inputs,
profile collection/resume behaviour, and any future rollout audit.
为什么不能安全自行处理：choosing session control, VisitorProfile or route
snapshot as the authoritative mode changes a product/state contract; choosing
one in code would either create a second profile-like source or silently alter
recovery semantics.
已确认方案：interaction/session control 是每轮产品模式的唯一运行归属；
最终选用模式只复制到不可变路线审计快照，VisitorProfile 不保存模式。
默认 classic；仅游客明确选择时进入 custom；只读问答读取既有恢复目标、
不得在问答期间写入控制状态。
需要负责人决定的选项：accept the recommended ownership, or explicitly select
VisitorProfile / route snapshot and provide migration and recovery semantics.
```

## 已确认后的可执行任务

P3-01 是一个独立任务：仅新增已批准的模式契约和测试。它不得改变 TourState、
创建第二份 VisitorProfile、启用路线/重规划/状态接管，或调度卡片。验收必须
覆盖 classic/custom 默认、不得从语气推断、知识问答
interruption and restoration, per-thread isolation, reset, and rollback.

Only after that task is verified should P3-03 produce read-only card-enhancement
candidates. Candidate generation must use the existing reviewed node,
StopProgram, GuidancePolicy, remaining budget and card runtime eligibility;
it must not insert a card, change an object, or write route/state.
