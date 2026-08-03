# P2-04-A Normal Event Transition Shadow Handoff

## Archive status

```yaml
branch: experiment/agent-orchestration-v2
tested_commit: "92ca888"
functional_validation: passed
manual_validation: passed_by_operator
langsmith_trace_status: metadata_unavailable
thread_id: not_recorded
trace_url: unavailable
trace_revision_id: unavailable
```

## Scope delivered

P2-04-A adds a pure, shadow-only audit for the ordinary `tour_event` path:
`arrive_at_stop`, `explanation_finished`, `confirm_stop_complete`, `skip_stop`,
`next_stop`, and `finish_tour`.

The shadow preflight reads a copied state snapshot and never calls
`handle_tour_event`, `start_tour`, or a state writer.  The legacy graph remains
the sole executor and invokes `handle_tour_event` once.  The resulting
thread-local `state_transition_evaluations` compare the dry-run suggestion with
the observed legacy result.

P2-04-B is deliberately out of scope: replan preparation, confirmation,
composite confirmation-and-next, and cancellation retain their existing P1-11
flows and require a separate snapshot-based audit.

## Verification

Automated results on `92ca888`:

- P2-04-A focused tests: 24/24 passed.
- Full unittest regression: 867/867 passed.
- P0 safety/visitor-output matrix: 3/3 passed.
- `git diff --check`: passed (Git printed pre-existing CRLF conversion warnings
  for two route JSON files; neither file was changed).

Manual Studio validation was performed by the operator with shadow mode and
the `state_transition` capability enabled.  No complete trace URL/revision or
complete Thread ID was retained.

| Scenario | Observed shadow result | Legacy comparison | Manual result |
|---|---|---|---|
| Arrive at Front Courtyard Center | `arrive_at_stop`, accepted, expected phase `explaining`, reason `arrived` | executed once; phase/result match | passed |
| Finish explanation | `explanation_finished`, accepted, expected phase `awaiting_confirmation` | executed once; phase/result match | passed |
| Confirm completion | `confirm_stop_complete`, accepted, reason `stop_completed` | executed once; phase/result match | passed |
| Skip current stop | `skip_stop`, accepted, reason `skipped` | executed once; phase/result match | passed |
| Next-stop navigation | `next_stop`, accepted, expected phase `navigating`, reason `next_stop_ready` | executed once; phase/result match | passed |
| Finish twice | first `tour_finished`, then `tour_already_finished`, both accepted | legacy behavior matched on both calls | passed |

The visual checks confirmed that arrival did not prematurely mark a stop as
visited, explanation completion moved to confirmation, completion occurred
only after confirmation, and the ordinary old flow remained responsible for
the visitor response.  A complete field-by-field Studio state diff was not
saved, so it is not claimed as independently trace-verified evidence.

## Known limitation and boundary

- The legacy literal wording `下一站。` may still take its older non-event path.
  Manual verification used the existing supported wording `下一站怎么走？`.
  P2-04-A does not alter legacy intent recognition.
- `state_transition_evaluations` are audit data only, scoped to the current
  thread.  They are not a second TourState and cannot control execution.
- Active state takeover remains disabled.

## Rollback

Set the read-only rollout mode to `off`, or remove `state_transition` from its
enabled capabilities.  The ordinary legacy `tour_event` behavior remains in
place.  Code rollback target is the parent of `92ca888`.
