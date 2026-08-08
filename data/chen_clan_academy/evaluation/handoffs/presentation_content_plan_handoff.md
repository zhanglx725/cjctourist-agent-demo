# Presentation Content Plan Shadow Handoff

Date: 2026-08-09
Branch: `experiment/agent-orchestration-v2`
Base: `08676b1 chore: make studio port configurable`

## Current state

```text
presentation_content_plan: implemented
presentation_content_plan_shadow: automated_verified
route_opening_shadow: implemented_and_automated_verified
route_opening_shadow_manual: pending_operator
presentation_content_plan_targeted_tests: 9/9 passed
route_opening_integration_tests: 19/19 passed
p0_matrix: 10/10 passed
full_regression: 1047/1052
preexisting_failures: 5
automated_validation: partial_due_to_preexisting_failures
role_active: disabled
active_takeover: disabled
```

## What changed

- Added `presentation_content_plan.py` with the strict
  `presentation_content_plan_v1` contract.
- Added closed scene kinds: `route_planning`, `route_opening`,
  `stop_guidance`, `navigation`, and `tour_closing`.
- Added `standard`, `ancient_scholar`, `child`, and `listen_only` plan modes.
- Added strict validation for unknown fields, missing fields, wrong types,
  invalid enums, invalid versions, invalid budgets, internal fields, state
  writes, and unavailable evidence.
- Added the `presentation_content_plan` Shadow capability at the existing
  post-legacy-response Shadow boundary.
- Repaired the automatic first-arrival path: `tour_opening_node` now appends
  exactly one independent `route_opening` Shadow plan after the unchanged
  legacy opening output and before legacy flow continues to `stop_guidance`.
  An idempotent repeated “开始导游” action does not append another opening plan.

## Safety boundary

The plan is non-authoritative. It does not publish or replace the legacy
visitor message and does not modify:

```text
TourState / VisitorProfile / route / proposal / StopProgram
Coverage / RAG evidence / tools / active takeover
```

It contains section labels and approved source categories only. It does not
contain `node_id`, `ornament_id`, `route_id`, `source_ids`, raw RAG chunks,
URLs, file paths, state patches, or a final visitor answer. Missing evidence
or an invalid plan records `rejected`; the old chain remains authoritative.

## Scene-to-source audit

```text
route_planning  -> VisitorProfile, GuidancePolicy, RouteSelection, stop catalog
route_opening   -> RouteSelection, stop catalog, TourOpening evidence
stop_guidance   -> StopProgram, approved guidance evidence, GuidancePolicy
navigation      -> TourState, approved spatial graph, stop catalog
tour_closing    -> VisitSummary, NarrationCoverage, TourState
```

Budgets are read per scene from existing deterministic allocations. Route
planning/opening use the selected route total; stop guidance uses the
StopProgram/render budget; navigation and closing use the existing route
explanation allocation. If an allocation is unavailable, validation fails
closed rather than inventing a budget.

## Verification commands

```cmd
set CJC_READ_ONLY_ROLLOUT_MODE=shadow
set CJC_READ_ONLY_ROLLOUT_CAPABILITIES=presentation_content_plan
py -3 -m unittest -v test_presentation_content_plan.py test_tour_opening_program.py test_agent_stop_guidance.py
py -3 -m unittest -v test_role_mode_shadow.py test_p0_safety_output_gate_matrix.py
py -3 -m unittest -v
git diff --check
```

The route-opening targeted group passed `19/19`; P0 passed `10/10`. Full
regression is `1047/1052`, with the same five parent/current baseline failures
and no new failure from this repair. Their assertions were not modified. No
manual LangSmith Trace URL or revision was supplied for this repair; if
unavailable, record `metadata_unavailable` rather than inventing Trace metadata.

## Next step

Restart Studio in Shadow mode and use a fresh Thread. After planning a route,
arrive at the first stop (for example, `我到前院中部了`). Confirm ordered,
separate records for `route_planning`, `route_opening`, and `stop_guidance`.
The opening record must be `accepted`, non-authoritative, preserve the legacy
message, and have `state_writes=[]`. Keep `read_only_active` and all Active
takeover capabilities off.
