# P3-04 NarrationComposer and Visitor Layout Handoff

## Scope

- Branch: `experiment/agent-orchestration-v2`
- Starting baseline: `732d381 feat: add read-only card dispatcher`
- Implementation: `narration_composer.py`
- Graph integration: not enabled
- State-class active takeover: disabled
- LangSmith: not run; this layer is not yet on the Graph visitor path

## Implemented contract

`compose_narration()` consumes an immutable reviewed `StopProgram`, the
existing evidence-rendered `NarrationRenderResult`, and the P3-03 read-only
`CardDispatchPlan`. It returns one immutable `ComposedNarration` with the same
safe text in `visitor_message` and `tts_text`.

The composer preserves the existing evidence-rendered base narration and
inserts qualified optional material immediately before the existing
`【下一步】` transition. It does not use an LLM and does not rewrite, infer, or
expand base facts. Flat paragraphs replace Markdown list prefixes; no nested
visitor list is introduced.

## Enhancement rendering

- Term cards use only the reviewed Chinese term and short definition.
- Research cards require reviewed status, source equivalence, explicit
  attribution, a safe takeaway, and a stated limitation.
- Comparison cards require research-only/cautious claim strength, source
  equivalence, explicit research framing, scope, and limitations.
- Photo cards are revalidated through the existing same-node photo selector
  and include their capture wording and safety boundary.

All candidates are revalidated against the live registry. Forged source refs,
wrong types, disabled cards, missing fields, wrong-node photo results, and
budget/length overflow are omitted. Card IDs and source refs remain audit-only.

## Layout and budget limits

- Maximum optional enhancements: 2.
- Maximum public message length: 1800 characters, enforced by the shared
  visitor-output boundary.
- Optional estimated seconds must fit the dispatch plan's single remaining
  budget.
- Base object count remains owned by the existing StopProgram policy.
- Display and TTS consume exactly the same public-safe body.
- If the final text violates the public boundary, it fails closed to the
  existing safe fallback without altering structured audit evidence.

## Protected boundaries

- No route, TourState, VisitorProfile, StopProgram, object selection,
  NarrationCoverage, dispatch plan, or base render mutation.
- No coverage commit is performed by composition.
- No internal card ID, source ID, file path, URL, or raw payload appears in
  visitor text.
- Research/comparison prose cannot be presented as official project facts.
- P2-07 real Studio layout acceptance remains separate until this composer is
  placed on a later controlled Graph path.

## Validation

```text
.\.venv\Scripts\python.exe -m unittest -v test_narration_composer.py
.\.venv\Scripts\python.exe -m unittest -v test_narration_composer.py test_card_dispatcher.py test_e5_narration_rendering.py test_e5_narration_style_integration.py test_visitor_response_boundary.py test_narration_coverage.py test_guidance_policy_integration.py
.\.venv\Scripts\python.exe -m unittest discover -v -b
git diff --check
```

Results:

- P3-04 focused: `7/7` passed.
- Narration/style/boundary/Coverage related: `68/68` passed.
- Complete discovery: `901/901` passed in 29.610 seconds.
- `git diff --check`: passed.
- Existing LangGraph node annotation warnings remain; no test failed or errored.

## Next step

P3-05 may place the P3-03/P3-04 read-only audit path behind the existing
controlled rollout mechanism. It must begin disabled, compare its public body
and audit metadata with the legacy renderer, and retain immediate rollback.
No route, replan, or state-event active takeover is authorized by this handoff.
