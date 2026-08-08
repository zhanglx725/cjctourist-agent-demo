# Baseline Regression Cleanup Handoff

## Current baseline

- branch: `experiment/agent-orchestration-v2`
- role_shadow_commit: `563839d feat: add route role narration shadow`
- baseline_fix_commit: pending
- active_takeover: disabled
- role_shadow: unchanged

## Resolved regressions

1. Explicit C8 controls such as child-friendly guidance bypass incomplete
   optional onboarding and update only `VisitorProfile`.
2. Deterministic duration parsing supports `one hour` and numeric English
   hours; it does not guess ambiguous duration wording.
3. Deterministic profile parsing supports `deep explanation` and
   `detailed tour`.
4. Route-profile collection preserves the raw utterance for explicit
   preferences while semantic normalization remains routing-only.
5. Visit-summary interest order remains visitor mention order.
6. Route trace tests assert the real ordering of `semantic_normalization`
   before collection and route selection, while preserving
   `visitor_localization` in the complete Graph trace.

## Verification

```text
baseline_cleanup_targeted_tests: 57/57 passed
role_shadow_targeted_tests: 22/22 passed
full_regression: 1061/1061 passed
git_diff_check: passed
remaining_preexisting_failures: 0
```

## Boundaries retained

- No role Shadow or `presentation_content_plan` changes.
- No Active takeover.
- No changes to TourState contract, route state, RAG, knowledge cards, or
  spatial data.
- `run_langgraph_studio.cmd` is developer-local and excluded from this change.

## Next work

Continue the planned non-authoritative role-text Shadow rollout for
`navigation` and `tour_closing`; retain the legacy visitor text and all
existing fail-closed validation boundaries.
