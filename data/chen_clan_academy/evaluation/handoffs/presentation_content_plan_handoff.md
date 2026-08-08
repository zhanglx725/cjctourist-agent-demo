# Presentation Content Plan Shadow Handoff

Date: 2026-08-09
Branch: `experiment/agent-orchestration-v2`
Base: `ac5ceb3 feat: add role mode shadow evaluation`

## Current state

```text
presentation_content_plan: implemented
presentation_content_plan_shadow: automated_verified
presentation_content_plan_targeted_tests: 7/7 passed
role_shadow_and_p0: 10/10 passed
full_regression: 1045/1050
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
py -3 -m unittest -v test_presentation_content_plan.py
py -3 -m unittest -v test_role_mode_shadow.py test_p0_safety_output_gate_matrix.py
py -3 -m unittest -v
git diff --check
```

The full regression still contains the same five parent/current baseline
failures. Their assertions were not modified. No manual LangSmith Trace URL
or revision was supplied for this phase; if unavailable, record
`metadata_unavailable` rather than inventing Trace metadata.

## Next step

Perform three lightweight Shadow manual checks for route planning, child stop
guidance, and listen-only guidance. Confirm the correct scene and role appear
in the audit, the old visitor text is unchanged, and operational state is
unchanged. Keep `read_only_active` and all active takeover capabilities off.
