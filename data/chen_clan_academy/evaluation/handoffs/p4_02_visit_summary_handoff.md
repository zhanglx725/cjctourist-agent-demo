# P4-02 VisitSummaryEngine Handoff

## Scope

P4-02 adds a deterministic end-of-tour summary. Its only factual inputs are
the completed `TourState`, successful `NarrationCoverage`, and the reviewed
node-guide-card object/craft mapping.

## Frozen counting contract

- Count only unique `visited_stop_ids`; planned, remaining, merely arrived,
  and skipped stops do not count as visited.
- Count only Coverage records produced by `stop_guidance` whose `node_id` is
  also in `visited_stop_ids`.
- `tour_qa`, preview, opening, navigation, failed rendering, and remote-point
  Coverage do not count.
- Ornament IDs are deduplicated by NarrationCoverage and accepted only when
  their reviewed object mapping agrees with the completed stop.
- Craft coverage comes from accepted successful craft records and the reviewed
  ornament-to-craft mapping; no alias or malformed craft is invented.
- A malformed Coverage snapshot does not block the visited-stop summary, but
  exact craft/ornament counts are omitted and marked `coverage_status=unavailable`.
- Natural completion and explicit early finish are distinguished.
- Count one question for each visitor turn that reaches `tour_qa` or
  `qa_follow_up_detail` after route initialization. Pre-route questions,
  navigation/control turns, opening controls, and internal model/tool calls do
  not count. A new route clears the bounded question audit.
- The summary exposes `question_count` for P4-03 title rules. An invalid or
  cross-route audit fails closed to `question_count_status=unavailable` rather
  than guessing an exact count.
- `title_basis` also exposes successfully heard craft/topic labels, content
  diversity, explicit session interests, exact interest-to-heard-content
  matches, and non-neutral validated style/interaction/knowledge preferences.
  It does not award a title in P4-02.
- Neutral profile defaults are not treated as visitor choices. Language,
  accessibility, inferred identity/personality, spending power, raw chat text,
  skipped content, and unverified profile values are not achievement signals.

## Graph integration

Successful `confirm_stop_complete`, `skip_stop`, or `finish_tour` events whose
resulting TourState is completed route to `visit_summary`. The node writes only
`visit_summary`, bounded `visit_summary_evaluations`, metrics, and the public
message. It never rewrites TourState, VisitorProfile, route, opening state, or
NarrationCoverage. A new route clears the prior derived summary.

## Automated verification

```text
python -m unittest -v test_visit_summary_engine.py test_agent_tour_state.py test_stage_b_e2e.py test_e5_stop_guidance_coverage_integration.py
python -m unittest discover -v
git diff --check
```

## LangSmith acceptance

Retain tested commit, Thread ID/Trace URL when available, input sequence, node
path, final TourState, NarrationCoverage, `visit_summary`, last evaluation,
protected-state diff, and public body.

1. Complete every stop: summary reports only confirmed visited stops and
   accepted successful point narration.
2. Finish early after one confirmed stop: marks `finished_early`, excludes all
   remaining stops.
3. Skip a narrated-but-unconfirmed stop: the stop and its Coverage subjects do
   not appear in the summary.
4. Ask remote QA about an unvisited point: `tour_qa` Coverage does not count.
5. Repeat guidance: subjects remain deduplicated.
6. Force malformed/missing Coverage: visited count remains available while
   exact craft/ornament reporting fails closed.
7. Ask two in-tour questions including one bounded follow-up: question count is
   2; route/profile/Coverage remain unchanged. Pre-tour questions do not count.
8. Use explicit interests and story style, then successfully hear one matching
   craft/topic: `title_basis` records only the exact match and non-neutral
   explicit preference; it does not infer demographic or personality traits.
