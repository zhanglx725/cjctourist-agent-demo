# Role Mode Shadow Handoff

Date: 2026-08-09
Branch: `experiment/agent-orchestration-v2`
Base: `68c37de fix: repair role candidate schema validation`

## Current state

```text
role_schema: fixed
role_shadow: implemented_and_automated_verified
active: disabled
automated_validation: partial_due_to_preexisting_failures
role_shadow_targeted_tests: 22/22 passed
full_regression: 1038/1043
p0_matrix: passed
```

The five known full-regression failures are preexisting. The parent commit and
the role Schema commit produced the same 4 failures plus 1 error. Do not alter
their assertions in this phase:

```text
test_same_thread_retains_profile_but_new_thread_isolated
test_english_minute_route_input_starts_same_thirty_minute_route
test_title_basis_combines_heard_topics_questions_and_explicit_profile
test_two_hour_woodcarving_deep_request_uses_route_planner
test_two_hour_woodcarving_request_replans_from_active_tour
```

## What changed

- Added `role_mode_shadow.py` as a deterministic selector for:
  - `ancient_scholar`
  - `child`
  - `listen_only`
- Added `role_mode_shadow` and bounded evaluation history to `AgentState`.
- `semantic_normalization_node` records explicit/profile role signals without
  changing semantic routing or operational state.
- `role_narration_generation_node` applies a selected role only to its local,
  non-authoritative narration plan before generating a Shadow candidate.
- `narration_validation_node` records role selection, applicability,
  presentation strategy, budget/evidence validation, and legacy/candidate
  difference metadata.
- Unknown roles, conflicting role requests, and conflicting profile roles fail
  closed without a model call or visitor-facing clarification mutation.

## Safety boundary

Shadow does not publish candidate text and does not modify:

```text
messages / TourState / VisitorProfile / route / proposal / StopProgram
Coverage / RAG evidence / tools / active takeover
```

The old deterministic chain remains the only visitor output path. Active must
remain disabled until automated tests and manual Studio checks pass.

## Required verification

Run with the project interpreter:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_role_mode_shadow.py test_role_narration_generation.py test_role_narration_graph.py
.\.venv\Scripts\python.exe -m unittest -v test_role_narration_generation.py test_role_narration_graph.py test_narration_style_policy.py test_narration_content_plan.py
.\.venv\Scripts\python.exe -m unittest -v test_p0_safety_output_gate_matrix.py
git diff --check
```

Manual inputs, each in a new Thread while `CJC_READ_ONLY_ROLLOUT_MODE=shadow`:

```text
我喜欢古风一点的讲解，帮我规划路线。
请用适合孩子理解的方式讲灰塑。
我只想安静听讲，不要频繁提问。
```

Expected: the old response remains unchanged; the trace contains the matching
role mode and a legal candidate; no state or tool operation is attributed to
the role layer. If Trace metadata is not saved, record
`metadata_unavailable`; never invent a Trace URL or revision.

## Verification result

The role Shadow target set passed `22/22`. The P0 matrix passed `3/3` in this
run; the earlier full P0 matrix result was `62/62`. Full regression is
`1038/1043`, with the same five parent/current baseline failures listed above.
No new role Shadow failure was introduced.

## Next phase

The next phase has added the separate typed `presentation_content_plan`
Shadow contract. See
`data/chen_clan_academy/evaluation/handoffs/presentation_content_plan_handoff.md`.
Do not enable `read_only_active` as part of either handoff.
