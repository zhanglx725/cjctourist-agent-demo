# P3-05 Narration Composition Graph Shadow Handoff

## Scope and status

- Branch: `experiment/agent-orchestration-v2`
- Starting baseline: `683de57 feat: add facts-only narration composer`
- Capability: `narration_composition`
- Default mode: off
- Allowed mode in this step: shadow only
- Read-only active takeover: hard-disabled by integration behavior
- Route/replan/state active takeover: unchanged and disabled
- Status: `implemented_pending_langsmith_verification`

## Graph integration

`stop_guidance_node` keeps `build_stop_guidance()` and its public message as
the sole authoritative path. When and only when the rollout environment is
`shadow` and explicitly includes `narration_composition`, the node passes the
same completed E5 result to an audit observer.

The observer reconstructs immutable `StopProgram`, `GuidancePolicy`,
`NarrationRenderResult`, and Coverage candidates from the legacy result. It
runs P3-03 and P3-04 without a second RAG call, planner call, object selection,
or Coverage submission, then appends one bounded per-thread comparison record
to `narration_composition_evaluations`.

The record contains the candidate public body for Studio review, message
equivalence, candidate/omitted card IDs, remaining budget, warning codes,
display/TTS equivalence, and explicit `active_takeover=false` / empty
`state_writes`. It is audit-only and never becomes the visitor response.

## Fail-closed behavior

- Off mode writes no P3-05 audit.
- `read_only_active` cannot activate the P3 narration path in this step.
- Non-E5 legacy results are rejected without changing the legacy fallback.
- Observer errors are contained by the Graph node and recorded as bounded
  exception classes; the legacy message and Coverage commit continue.
- Normal stop guidance is not an explicit photo request, so proactive photo
  output stays closed in this Graph slice.
- Audit history is bounded to the latest 20 records per thread.

## Shadow configuration

```text
CJC_READ_ONLY_ROLLOUT_MODE=shadow
CJC_READ_ONLY_ROLLOUT_CAPABILITIES=narration_composition
```

This capability may also be included in the comma-separated existing P2
Shadow capability set. It must not be configured as active for acceptance.

## Automated validation

```text
.\.venv\Scripts\python.exe -m unittest -v test_narration_composition_shadow.py test_narration_composer.py test_card_dispatcher.py test_controlled_rollout.py
.\.venv\Scripts\python.exe -m unittest -v test_narration_composition_shadow.py test_p2_gate_3_integration.py test_state_transition_shadow.py test_replan_composite_shadow.py test_agent_stop_guidance.py test_e5_stop_guidance_coverage_integration.py test_visitor_response_boundary.py test_controlled_rollout.py
.\.venv\Scripts\python.exe -m unittest discover -v -b
git diff --check
```

Results:

- P3 narration rollout focused: `23/23` passed.
- P2 Gate/transition/guidance/Coverage related: `39/39` passed.
- Complete discovery after the API thread-context fix: `906/906` passed in
  35.670 seconds.
- `git diff --check`: passed.
- Existing LangGraph annotation warnings remain; no test failed or errored.

## Local API evidence (2026-08-04)

The local LangGraph API was exercised with UTF-8 request bodies against graph
`chen_clan_academy_agent` and assistant
`067143aa-ad3c-5ff0-a987-cd8cfc754135`. LangSmith metadata submission returned
HTTP 204, but no Studio browser was available in this environment, so a Trace
URL/revision has not been visually reviewed and the overall status remains
pending.

- Accepted evidence thread: `019fcbed-10ab-7260-bb39-fb018385beb6`.
- Inputs: `选择定制模式，安排30分钟路线，我对灰塑感兴趣`, then
  `我已到达前院中部，请开始讲解`.
- Result: route `highlights_30`, current stop
  `stop_front_courtyard_center`; legacy Coverage committed craft `灰塑` and
  ornaments `orn_005`, `orn_008`.
- Shadow audit: `validation_status=accepted`, real audit `thread_id` equals the
  API thread ID, `legacy_message_preserved=true`,
  `same_public_message=true`, `display_tts_equal=true`, and `state_writes=[]`.
- Repeating the arrival/guidance event produced a second thread-scoped audit
  while retaining the same Coverage subjects; no P3 audit became a Coverage
  source.
- Excluded diagnostic threads: `019fcbe7-9d6c-77b2-9f9d-9d7c02aaf30f`
  (invalid Chinese request encoding) and
  `019fcbe8-2c64-75f0-bc78-365e22051396` / subsequent pre-fix runs
  (`local_unscoped_thread` audit defect). They are not acceptance evidence.

The real-chain thread-context defect was fixed by using a LangGraph-compatible
`RunnableConfig` node signature and accepting both configurable and API
metadata thread IDs. Automated coverage now exercises all supported locations.

## Required LangSmith acceptance

Use a new thread for each case and retain thread ID, Trace URL/revision, tested
commit, input, path, legacy public message, candidate public message, and
protected-state diff.

1. Classic stop guidance: legacy output unchanged; no proactive research,
   comparison, or photo candidate.
2. Custom detailed stop guidance with an explicit reviewed interest: candidate
   remains public-safe, attributed, budget-bounded, and display/TTS equal.
3. Repeated guidance at the same stop: legacy Coverage remains idempotent and
   no P3 audit value becomes a second Coverage source.
4. Forced observer failure or unavailable optional card: legacy message and
   Coverage continue; audit is rejected/fail-closed.
5. Off and accidental active configuration: no P3 candidate takes over the
   visitor message.

Until those traces are reviewed, P3-05 remains pending and P4 must not start.
