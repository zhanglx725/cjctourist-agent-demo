# P3-01 / CA-12 Journey Mode Handoff

## Scope and baseline

- Branch: `experiment/agent-orchestration-v2`
- Starting baseline: `30e2bda docs: add P3 preflight audit`
- Product decision: retain the legacy interaction-form `tour_mode`; add the separate session-owned product field `journey_mode`.
- LangSmith: not run in this implementation step.

## Implemented contract

`tour_interaction_state` is the only runtime owner of `journey_mode`.

- `tour_mode` remains `chat`, `button_guided`, or `continuous`.
- `journey_mode` is `classic` or `custom`; missing/unknown session state safely defaults to classic, and only narrow explicit mode choices may select custom.
- Classic requires only `available_minutes`. Explicit interests or detail values remain usable when supplied, but the system does not prompt for them.
- Custom collects explicit time and interests, then offers two skippable
  questions for explanation style and narration language; it never asks for a
  narration-depth choice.
- `journey_mode == custom` derives the existing deep/detailed `GuidancePolicy` only while organising stop narration. This is not persisted to VisitorProfile, TourState, StopProgram route facts, or route-calculation inputs. Classic retains the existing neutral profile default.
- Neither `TourState` nor `VisitorProfile` stores `journey_mode`.
- A selected route receives `journey_mode_audit` only after the deterministic planner has selected it. The audit declares `used_for_route_calculation: false`.
- The session control records its recoverable stage when collection or guided-tour control is entered. Read-only fact answers only inspect that target; they do not write `tour_interaction_state`, any product fact, or any state transition.
- Completing a tour clears the live session value to classic. The historic chosen value remains only on the route snapshot audit.

## Intentionally not implemented

- P3-03 / CA-13 CardDispatcher.
- Any proactive term, comparison, photo, or research card output.
- P3-04 narration composition or visitor layout changes.
- State-class active takeover, including route, replan, arrival, completion, skip, next-stop, and finish delegation.

## Validation

Actual regression commands:

```text
.\\.venv\\Scripts\\python.exe -m unittest -v test_p3_01_journey_mode.py test_guidance_policy_integration.py
.\\.venv\\Scripts\\python.exe -m unittest -v test_profile_dialogue.py test_agent_profile_collection.py test_agent_profile_route_integration.py test_tour_interaction.py test_guidance_policy.py test_guide_program_evidence.py test_e5_narration_rendering.py
.\\.venv\\Scripts\\python.exe -m unittest discover -v -b
git diff --check
```

Result: the P3-01 custom-detail contract and policy tests passed 14/14; the supporting interaction/profile/E5 regression passed 66/66; complete discovery passed 887/887. `git diff --check` passed. Existing LangGraph node type warnings were emitted. Test-run Trace upload was unavailable in the sandboxed environment and is not LangSmith acceptance evidence.

## P3-01 supplement: custom detailed strategy

- Documentation baseline commit: `d3d38da docs: freeze custom detailed narration policy`.
- Custom's required collection fields are now only `available_minutes` and `interests`; the former depth question is disabled for this product mode.
- The session-owned custom mode derives detailed guidance only at narration time. It remains subject to reviewed evidence, StopProgram budget, no-evidence failure closure, visitor-text boundary, and `listen_only` constraints.
- This supplement does not implement P3-03 CardDispatcher, proactive card output, P3-04 paragraph/length/read-aloud composition, or any state-class active takeover.
- LangSmith: not run for this supplement.

## P3-01 supplement: optional style and language collection

- Custom collection order is time, interests, explanation style, language.
- Style and language are explicitly skippable. `跳过`, `默认`, `都可以`,
  `无所谓`, and `没有偏好` resolve only the question currently being asked.
- Style accepts typed controlled choices: standard, story, technical,
  interactive, or expert, with reviewed Chinese aliases.
- Language accepts reviewed aliases for Chinese, English, Korean, Japanese,
  Cantonese, French, German, and Spanish. While the language question is
  active, a short typed language name such as `泰语` is also retained.
- Skipped style keeps the neutral `standard` default; skipped language remains
  absent. Classic mode still asks only for available time.
- This step collects and persists the requested narration language. End-to-end
  translation/TTS voice generation remains a separate multilingual delivery
  capability and is not claimed by this supplement.

### Studio feedback and follow-up

- Case 1 (45 minutes, woodcarving and grey sculpture, interactive style,
  Korean) was reported as passed: `journey_mode=custom`, style `interactive`,
  language `ko`, ready collection, and no interest contamination or visitor
  boundary leak. Thread/Trace identifiers were not included in the report.
- Case 2 exposed a real routing defect: bare `跳过` at the optional style
  question was classified as a stop-skip control and returned clarification.
- The follow-up fix gives a bare skip to `profile_collection` only while its
  current missing field is `explanation_style` or `language`. Outside that
  narrow active context, existing stop-skip behavior is unchanged.
- Offline regression covers both optional skips through `ready`, absence of a
  skipped language value, and preservation of normal skip clarification. The
  original Studio Case 2 must be rerun on the follow-up commit.
- Case 4 exposed a separate one-turn field-isolation defect: `故事风格` was
  correctly stored as style `story` but its `故事` token was also copied into
  interests. The follow-up parser now recognizes explicit style phrases,
  removes only those phrase spans before interest extraction, and still keeps
  a genuine `三国故事` interest when no style phrase is present. Offline tests
  cover all five supported explanation styles plus the reported full input;
  Studio Case 4 must be rerun on the new follow-up commit.

## Next step

P3-03 may design and implement a read-only CardDispatcher. It must use this contract only as eligibility input and follow the approved classic-mode dispatch rules in `plan.md`; it must not introduce a second mode, a second state source, or active state takeover.
