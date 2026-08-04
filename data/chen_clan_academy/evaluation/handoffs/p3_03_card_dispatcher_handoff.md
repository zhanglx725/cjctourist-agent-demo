# P3-03 / CA-13 Read-only CardDispatcher Handoff

## Scope

- Branch: `experiment/agent-orchestration-v2`
- Starting baseline: `433f0f2 docs: accept P3 narration style integration`
- Implementation: `card_dispatcher.py`
- Graph integration: not enabled
- Visitor card rendering: not implemented
- State-class active takeover: disabled
- LangSmith: not run; this layer has no Graph or visitor-text path

## Implemented contract

`dispatch_card_candidates()` accepts the reviewed node, immutable
`StopProgram`, confirmed `GuidancePolicy`, session-owned journey mode, explicit
interests, remaining content budget, and explicit photo/safety signals. It
returns only an immutable ordered `CardDispatchPlan`.

Candidate order is frozen as:

1. reviewed base-object fact marker;
2. eligible term explanation;
3. attributed research summary;
4. attributed comparison;
5. photo-spot editorial candidate.

The base marker contains no new fact payload and leaves object selection under
the existing `StopProgram`. Terms must be enabled, source-backed, directly
associated with both the current node and an object selected in this program.
Research must be mapped to the current node, custom-mode eligible, enabled by
the detailed policy, explicitly matched by a supplied interest, and marked as
requiring attribution. Comparison requires a comparison card ID already bound
to a selected `StopProgram` item; the dispatcher does not infer comparison
objects. Photo candidates require explicit photo intent, an explicit upstream
safety-clearance signal, sufficient budget, and the existing reviewed
photo-point selector to return the same node.

Optional candidates consume one shared remaining-content budget in dispatch
order. Missing, malformed, disabled, unreviewed, unrelated, unsafe, wrong-node,
or over-budget cards fail closed. With no eligible enhancement, base narration
continues normally.

## Protected boundaries

- No card body or visitor message is rendered.
- No LLM or Agent chooses candidates.
- No route, TourState, VisitorProfile, StopProgram, object selection, or
  NarrationCoverage mutation is permitted.
- Classic mode never proactively injects research or comparison cards.
- Research and comparison candidates retain source references and
  `attribution_required=true`; they cannot become project facts.
- Photo candidates cannot bypass the dedicated safety/node gate.

## Validation

```text
.\.venv\Scripts\python.exe -m unittest -v test_card_dispatcher.py
.\.venv\Scripts\python.exe -m unittest -v test_card_dispatcher.py test_card_runtime_eligibility.py test_experience_card_runtime_eligibility.py test_knowledge_card_registry.py
.\.venv\Scripts\python.exe -m unittest discover -v -b
git diff --check
```

Results:

- P3-03 focused: `7/7` passed.
- Card eligibility/registry related: `52/52` passed.
- Complete discovery: `894/894` passed in 30.248 seconds.
- `git diff --check`: passed.
- Existing LangGraph node annotation warnings remain; no test failed or errored.

## Next step

P3-04 may consume `CardDispatchPlan` as read-only composition input. It must
revalidate evidence and budget, omit rather than invent unavailable content,
and keep internal card IDs/source metadata out of visitor text. P3-03 itself
must remain disconnected from active Graph takeover until the later rollout
stage is separately authorized and accepted.
