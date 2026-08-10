# P3-02 NarrationStylePolicy Integration Acceptance

## Scope and baseline

- Branch: `experiment/agent-orchestration-v2`
- Audit baseline: `a1cf93e feat: default custom tours to detailed narration`
- Result: accepted by code and contract audit; no duplicate production implementation required.
- State-class active takeover: disabled.
- LangSmith: not run for this acceptance step.

## Accepted single chain

```text
VisitorProfile (validated input only)
  -> GuidancePolicy
  -> compile_narration_style()
  -> NarrationStylePolicy
  -> render_guidance_evidence()
```

The production path already exposes the seven approved styles: `neutral`,
`child`, `family`, `student_research`, `professional`, `listen_only`, and
`mixed_group`. Selection reads the immutable `GuidancePolicy`; it does not
read or copy `VisitorProfile` inside the style compiler and does not create a
second profile, session state, or route fact.

Unknown named styles fall back to `neutral`. A missing or malformed style
library also fails closed to the original neutral renderer while preserving
the factual result. `listen_only` suppresses questions and interaction tasks.

## Fact-preservation contract

Style selection may change only presentation framing, vocabulary, sentence
length, pacing, and optional observation wording. It cannot change the
selected crafts or objects, evidence packets, source IDs, content budget,
omitted objects, coverage candidates, route, `TourState`, `VisitorProfile`,
`StopProgram`, or `NarrationCoverage`.

The existing integration regression covers deterministic mapping of all seven
styles, fact/source/candidate/budget equivalence against neutral, input
immutability, `listen_only`, and style-library failure closure. Schema tests
also reject factual/source-bearing templates and illegal placeholders.

## Validation status

The acceptance audit reviewed:

- `narration_style_policy.py`
- `data/chen_clan_academy/narration_styles/styles_v1.yaml`
- `narration_rendering.py`
- `test_narration_style_policy.py`
- `test_e5_narration_style_integration.py`

The broken Windows Python/MSI state was repaired, Python 3.12.7 was restored,
and the project `.venv` was rebuilt from `requirements.txt`. Validation then
completed with these actual commands:

```text
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest -v test_narration_style_policy.py test_e5_narration_style_integration.py test_guidance_policy_integration.py
.\.venv\Scripts\python.exe -m unittest discover -v -b
git diff --check
```

Result: dependency validation passed with no broken requirements; P3-02
targeted regression passed `33/33`; complete discovery passed `887/887` in
30.912 seconds. Existing LangGraph node annotation warnings were emitted; no
test failed or errored. No LangSmith trace was run for this acceptance.

## Completion decision

```text
P3-02 implementation: already present on the single E5 rendering path
P3-02 code/contract audit: passed
P3-02 fresh local regression: passed (33/33 targeted; 887/887 complete)
P3-02 LangSmith trace status: not_run
P3-03 readiness: allowed
```

P3-03 must consume the existing style decision only as read-only presentation
context. It must not add a second style selector, profile field, session fact,
or active Graph takeover.
