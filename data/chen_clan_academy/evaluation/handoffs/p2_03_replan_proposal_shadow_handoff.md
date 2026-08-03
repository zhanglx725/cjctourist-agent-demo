# P2-03 Replan Proposal Graph Shadow archive

## Archive status

```yaml
branch: experiment/agent-orchestration-v2
implementation_commit: 09a85c8
diagnostic_commit: 334ea7a
functional_validation: passed
manual_validation: passed_by_operator
langsmith_trace_status: metadata_unavailable
thread_id: not_recorded
trace_url: unavailable
trace_revision_id: unavailable
```

Studio screenshots showed a thread ID, but the complete ID, Trace URL, and revision ID were not retained. This is functional/manual evidence only; it is not a claim of trace verification.

## Boundary and implementation

- The old P1-11 nodes still create, view, confirm, or cancel the official `pending_replan_proposal`.
- `replan_proposal_shadow` only reads that same preview plus the current TourState snapshot and appends thread-local `replan_proposal_evaluations`.
- It never reruns `prepare_remaining_route_proposal`, calls `tour_interaction` or `state_transition_adapter`, applies/cancels a formal proposal, or changes visitor text, TourState, VisitorProfile, route, or coverage.
- Graph order is the relevant old P1-11 node, then `replan_proposal_shadow`, then the existing P2-01 shadow tail.
- `off` writes nothing. In `shadow`, an unavailable capability is explicitly recorded as `capability_not_enabled`, rather than silently looking like a successful audit.

## Automated validation

| Scope | Result |
|---|---|
| P2-03 focused suite | 57/57 OK before diagnostic fix; diagnostic suite 6/6 OK |
| Full unittest regression at `334ea7a` | 860/860 OK |
| P0 safety/public-output matrix at `334ea7a` | 3/3 OK |
| `git diff --check` | OK |

Coverage includes same-preview wrapping, stale snapshot rejection, disabled Shadow, explicit shadow-capability mismatch, no replan-planner/state-adapter call, state preservation, and thread-local audit separation. Existing P1-11, P2-01, P2-02, and P2-05 coverage is included in the full regression.

## Manual Studio smoke evidence

| Scenario | Shadow result | Legacy behavior observed |
|---|---|---|
| Plan 30 minutes, arrive at Moon Platform, request replan, then provide 40 minutes | First audit rejected `legacy_proposal_absent` while old flow asked for time; second audit `accepted`, `matches_legacy=true`, `origin_node=label_moon_platform`, `remaining_minutes=40`, route version `v1` | Existing P1-11 preview remained awaiting confirmation; formal route was not replaced. |
| Arrive at an unnamed courtyard and request replan | No proposal; old graph used `clarification` | No guessed position, default proposal, or formal-route change. |
| Cancel the pending new route | `rejected`, `legacy_proposal_absent`, `proposal=null` after the old cancel node cleared the preview | Existing `cancel_replan` message confirmed the original route remained unchanged. |

The accepted audit showed `capability=replan_proposal`, `mode=shadow`, empty visited/skipped snapshots, non-empty candidate stop IDs and proposal, and `rejected_reason=null`. No active execution was enabled.

## State, fallback, limits, and rollback

- Manual screenshots establish expected route/proposal behavior, but no complete before/after state export was retained; detailed manual state diff is `metadata_unavailable`, not fabricated as zero.
- Missing preview, stale origin/snapshots, invalid remaining time, and capability mismatch fail closed and leave the old P1-11 path responsible for visitor output.
- P2-03 Graph Shadow is functionally verified; active is disabled.
- P2-04 remains not started. Gate 3 remains pending P2-04; Gate 2 is not closed by this archive.
- Roll back by setting `CJC_READ_ONLY_ROLLOUT_MODE=off`, or by reverting `334ea7a` and `09a85c8`. The old P1-11 Graph path remains available.
