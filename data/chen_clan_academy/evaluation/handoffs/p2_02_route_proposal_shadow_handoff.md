# P2-02 路线 Proposal Graph Shadow 归档

## 归档状态

```yaml
branch: experiment/agent-orchestration-v2
implementation_commit: d0b61e0fc18ba2ee81a7e56eebcc71a0fbc5ce01
rejection_audit_commit: 44235c3d8a27906d6d147f6cef55f4a6bac677d5
functional_validation: passed
manual_validation: passed_by_operator
langsmith_trace_status: metadata_unavailable
trace_url: unavailable
trace_revision_id: unavailable
```

Thread IDs were visible in the responsible operator's Studio screenshots, but Trace URLs and revision IDs were not saved. This archive must not be read as LangSmith Trace verification.

## Implementation boundary

- `route_proposal.py` wraps the single, already-produced `RouteSelection`; it does not call `recommend_route()` or `plan_template()` again.
- The envelope contains the selected strategy, selected route ID, reviewed guide-stop order, total/walking/budget estimates, selection reason, deterministic route-data versions, input snapshot, and validation status.
- Graph order is `direct_route -> route_proposal_shadow -> atomic_read_plan_shadow`.
- The old `direct_route` still owns selection, `start_tour`, official route state, and visitor text. The Shadow node only appends thread-local `route_proposal_evaluations`.
- Only `off` and `shadow` are used. P2-02 active is disabled; it does not create a formal confirmation proposal or call P2-03/P2-04/state adapters.

## Automated validation

| Scope | Result |
|---|---|
| P2-02 focused suite | 55/55 OK |
| Full unittest regression | 852/852 OK |
| P0 safety/public-output matrix | 8/8 OK |
| `git diff --check` | OK |

Coverage includes anchor and dynamic wrapping, 30/60/90-minute inputs, one selector invocation, disabled Shadow, wrapper failure, preservation of formal route state, thread-local audit history, and invalid-time rejection auditing.

## Manual Studio smoke evidence

| Input | Thread ID | Shadow result | Legacy behavior observed |
|---|---|---|---|
| 我有30分钟，喜欢灰塑，标准讲解，帮我规划路线。 | `019fc626-dc2d-7040-beb5-aae84354d296` | `accepted`, `matches_legacy=true` | Existing route path completed; no Shadow visitor text was shown. |
| 我有60分钟，喜欢灰塑和木雕，深入讲解，帮我规划路线。 | `019fc627-e686-75c1-afab-e1b6b6c5eab5` | `accepted`, `matches_legacy=true` | Existing `profile_collection -> direct_route` path completed; no Shadow visitor text was shown. |
| 我只有10分钟，帮我规划一条路线。 | `019fc62c-e860-7123-af71-098190370634` | `rejected`, `invalid_profile_value`, `proposal=null` | Existing profile validation said that available minutes must be 20–120; no formal route was created. |

For the accepted cases, the audit showed `planner_mode=shadow`, `rejected_reason=null`, and a proposal matching the old selected route. The global P2-01 Shadow also recorded a clarification candidate on route requests; it did not execute an action and did not change the P2-02 result.

## State, fallback, and evidence debt

- Formal route/TourState/VisitorProfile behavior remains owned by the old Graph. The operator observed no extra visitor output or state action from the Shadow; detailed field-by-field Studio state snapshots were not retained, so manual state diff is `metadata_unavailable` rather than fabricated as zero.
- Invalid time fails closed: the old profile message remains visitor-visible and the P2-02 audit records `invalid_profile_value` without a proposal.
- Wrapper failure records rejection and leaves the legacy route start intact, as covered by automated tests.
- Thread isolation is covered by automated tests. Manual Thread IDs above are not paired with saved Trace URLs.

## Limits and next steps

- P2-02 Graph Shadow: functionally verified.
- P2-02 active: disabled.
- P2-03/P2-04: not started in Graph.
- Gate 2 remains pending; Gate 3 remains blocked.
- Roll back by setting `CJC_READ_ONLY_ROLLOUT_MODE=off`, or by reverting `44235c3` and `d0b61e0`; the old route Graph path remains intact.
