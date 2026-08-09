# Role Shadow Risk Sample Handoff

## Baseline

```text
branch: experiment/agent-orchestration-v2
tested_commit: 8d09f53
automated_18_style_validation: passed
manual_risk_sample: 7/7 passed
manual_full_18_style_matrix: waived_due_to_schedule
active_takeover: disabled
trace_metadata: unavailable
```

The competition acceptance replaces the former approximately 25-sample manual
matrix with seven high-risk real-stop samples. The other reviewed styles remain
covered by automated validation.

## Manual risk samples

All samples used a reviewed formal stop. Thread identifiers and Trace URLs were
not retained, so they are recorded as `not_recorded` / `unavailable` rather than
reconstructed.

| style_id | node_id | validation_status | same_fact_boundary | public_message_safe | role_consistent | within_budget | active_takeover | state_writes | manual_result |
|---|---|---|---|---|---|---|---|---|---|
| child | stop_front_courtyard_center | accepted | true | true | true | true | false | [] | passed_by_operator |
| professional | stop_front_courtyard_center | accepted | true | true | true | true | false | [] | passed_by_operator |
| ancient_scholar | stop_front_courtyard_center | accepted | true | true | true | true | false | [] | passed_by_operator |
| listen_only | stop_front_courtyard_center | accepted | true | true | true | true | false | [] | passed_by_operator |
| cantonese_storyteller | stop_front_courtyard_center | accepted | true | true | true | true | false | [] | passed_by_operator |
| exploration_game | stop_front_courtyard_center | accepted | true | true | true | true | false | [] | passed_by_operator |
| photo_guide | stop_front_courtyard_center | accepted | true | true | true | true | false | [] | passed_by_operator |

For every row:

```text
thread_id: not_recorded
trace_metadata: unavailable
legacy_message_preserved: true
fallback_used: false
```

The accepted `listen_only` sample retained the no-interaction boundary. The
accepted Cantonese storyteller, exploration game, and photo guide samples
passed the reviewed fact, public-output, role, budget, and dangerous-expression
gates; no new story claim, unsafe game action, or unsafe photo action was
reported by the operator.

## Fail-closed observations

Before the final accepted samples, one professional candidate and one ancient
scholar candidate were rejected for a fact-boundary difference. Both showed:

```text
active_takeover: false
fallback_used: true
legacy_message_preserved: true
state_writes: []
```

The professional retry passed unchanged safety gates. The ancient scholar case
revealed factual paraphrasing in connector prose. Commit `8d09f53` adds one
bounded connector-only repair while retaining `unapproved_fact_trigger`; a
fresh Thread then passed with `same_fact_boundary=true`. This is evidence for
both successful realization and deterministic fallback, not a relaxation of
the fact boundary.

## Automated evidence

```text
risk_sample_related_targeted_validation: 65/65 passed
p0_matrix: 3/3 passed
full_regression: 1101/1101 passed
git_diff_check: passed_with_preexisting_line_ending_warnings
```

The warnings concern existing route JSON files and the operator-owned local
`run_langgraph_studio.cmd`; none was modified or included in this archive.

## Next competition step

Proceed only with role-aware question Shadow for `tour_qa` and
`qa_follow_up_detail`. Question candidates remain non-authoritative and must
preserve the existing controlled answer. Active takeover remains disabled.
