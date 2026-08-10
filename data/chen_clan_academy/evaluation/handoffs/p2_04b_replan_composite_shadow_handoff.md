# P2-04-B Replan Composite Shadow Handoff

## Archive status

```yaml
branch: experiment/agent-orchestration-v2
tested_commit: pending_commit
functional_validation: passed
manual_validation: passed_by_operator
langsmith_trace_status: metadata_unavailable
thread_id: not_recorded
trace_url: unavailable
trace_revision_id: unavailable
```

The operator supplied Studio screenshots for the composite confirmation and
cancel flows, but did not retain a complete Thread ID, Trace URL, revision ID,
or a complete before/after state export. This is manual functional evidence;
it is not a claim that LangSmith trace metadata was verified.

## Scope and boundary

P2-04-B adds a pure `replan_composite_evaluations` audit record to existing
P1-11 replan operations. It observes only post-legacy inputs/outputs and never
calls `handle_tour_event`, `start_tour`, a state adapter, or a route planner.

- `prepare_replan` records only legacy arrival activity and the time-confirmation boundary.
- `prepare_replan_candidate` records preview creation without formal-route changes.
- `confirm_replan` records the single `apply_replan_proposal` operation.
- `confirm_replan_and_next` records the legal ordered composite
  `apply_replan_proposal → next_stop`.
- `cancel_replan` is explicitly audited as pending-action cleanup, not an A1 event.
- A confirmation without a pending proposal is audited as a safe no-op.

The capability remains `state_transition` in `shadow` mode. P2-04 active
takeover remains disabled; P2-03/P2-02/P2-01 behavior and the P1-11 visitor
flow remain the old chain.

## Automated validation

| Scope | Result |
| --- | --- |
| P2-04-B focused suite | 5/5 OK |
| Related P1-11/P2 transition suite | 66/66 OK |
| Full unittest regression | 874/874 OK |
| P0 safety/visitor-output matrix | 3/3 OK |
| `git diff --check` | OK; only pre-existing CRLF conversion warnings for unchanged route JSON files |

Coverage includes pure-audit non-execution, candidate preparation, single
confirm application, legal confirm-and-next ordering, cancel invariants, and
no-pending confirmation safety.

## Manual validation

| Scenario | Observed result |
| --- | --- |
| Confirm a valid proposal and immediately go to next stop | `confirm_replan_and_next` appeared in Studio; audit showed `mode=shadow`, `operation_kind=confirm_replan_and_next`, `validation_status=accepted`, `formal_route_changed=true`, `matches_expected_contract=true`, proposal cleared, and no rejection. |
| Cancel a pending proposal | Existing `cancel_replan` response said the original route remained unchanged; pending proposal/time confirmation were null. |
| No pending proposal confirmation/cancellation | Operator completed the requested safety scenario; retained screenshots do not preserve the full audit expansion, so detailed field evidence is metadata-unavailable rather than fabricated. |

## Limitations and rollback

- `replan_composite_evaluations` are bounded thread state for audit only; they
  are not TourState, VisitorProfile, or a formal proposal source.
- The displayed audit fallback `local_unscoped_thread` is not a substitute for
  a retained Studio Thread ID. It is recorded here as metadata unavailable.
- Roll back by setting `CJC_READ_ONLY_ROLLOUT_MODE=off`, removing
  `state_transition` from the enabled capabilities, or reverting the pending
  implementation commit. The old P1-11 flow remains authoritative.

## Result

```text
P2-04-B replan composite shadow: functionally verified
P2-04 active takeover: disabled
Gate 3: pending final P2 integration acceptance
```
