# P2 Gate 3 Shadow / Read-only Integration Acceptance

## Archive status

```yaml
branch: experiment/agent-orchestration-v2
tested_commit: 5ee99ead7466bcf4e2c807f7812e8f615b9b1174
functional_validation: passed
manual_validation: passed_by_operator
langsmith_trace_status: metadata_unavailable
thread_id: not_recorded
trace_url: unavailable
trace_revision_id: unavailable
gate_3: passed_for_shadow_read_only_integration
p2_state_class_active_takeover: disabled
```

This records functional and operator validation only. No Trace URL, complete
Thread ID, or revision ID was retained, so this is not a claim of LangSmith
trace verification.

## Covered P2 components and boundaries

| Component | Gate 3 status | Execution authority |
| --- | --- | --- |
| P2-01 atomic multi-intent | Shadow | Audit candidate only; old Graph keeps control and safety boundaries. |
| P2-02 route proposal | Shadow | Wraps the already-selected legacy route; never plans a second route. |
| P2-03 replan proposal | Shadow | Wraps the existing P1-11 preview; never applies or cancels it. |
| P2-04-A normal events | Shadow | Pure dry-run compares against one legacy `handle_tour_event()` execution. |
| P2-04-B replan composite | Shadow | Audits legacy P1-11 preparation/confirm/cancel; never executes events. |
| P2-05 controlled knowledge | Frozen read-only rollout | Existing `off`/`shadow`/`read_only_active` contract; no state-class takeover. |

All audit fields (`controlled_rollout_evaluations`, `atomic_read_plan_evaluations`,
`route_proposal_evaluations`, `replan_proposal_evaluations`,
`state_transition_evaluations`, and `replan_composite_evaluations`) are bounded
thread checkpoint observations. They are not a TourState, VisitorProfile, formal
route, or proposal source of truth, and they are not visitor-visible output.

## Automated validation

| Scope | Result |
| --- | --- |
| Gate 3 directed integration and P2/Gate 1 suites | 66/66 OK |
| Full unittest regression | 877/877 OK |
| P0 safety/public-output matrix | 3/3 OK |
| `git diff --check` | OK; only pre-existing CRLF notices for unchanged route JSON files |

The directed coverage confirms fail-closed configuration, unregistered or
invalid decision/gate/executor boundaries, audit-only updates, no duplicate
route selection or event execution, state/proposal isolation, and thread-local
audit records. Visitor-output coverage rejects internal filenames, source IDs,
URLs, node/object IDs, and raw retrieval chunks.

## Operator Studio validation

| Scenario | Result |
| --- | --- |
| Tour invoice question, then next-stop navigation | Controlled invoice answer appeared; old guide navigation continued. |
| `我到月台了，先讲讲石雕，再告诉我下一站。` | Existing clarification handled the compound state/question request; no partial arrival, answer, or navigation executed. |
| 60-minute, grey-sculpture and woodcarving, deep route request | Legacy `profile_collection -> direct_route` created the route; route proposal Shadow matched the legacy selection. |
| Deviate to Rear East Courtyard, supply 40 minutes, then confirm-and-next | P1-11 created a pending proposal, then `confirm_replan_and_next` applied it once and navigated to Front Courtyard Center. |

The last scenario was initially attempted against an old in-memory Studio
process and exposed the previously repaired `confirm_replan_and_next` mapping
gap. It was repeated against the current service: the node was reached,
`crafts_60_replanned` became the selected route, the proposal cleared, and the
visitor received the new next-stop guidance.

## Gate 3 conclusion and limits

```text
P2 integration functional validation: passed
P2 state-class active takeover: disabled
P2 LangSmith trace metadata: unavailable where not recorded
Gate 3: passed for shadow/read-only integration
```

No P2 Shadow component becomes an active route, replan, arrival, completion,
skip, next-stop, or finish handler through this acceptance. The old Graph,
P1-11 confirmation flow, and `handle_tour_event()` remain authoritative.

Rollback remains per-capability: use `CJC_READ_ONLY_ROLLOUT_MODE=off` or remove
the relevant capability from `CJC_READ_ONLY_ROLLOUT_CAPABILITIES`; the old Graph
paths remain intact.
