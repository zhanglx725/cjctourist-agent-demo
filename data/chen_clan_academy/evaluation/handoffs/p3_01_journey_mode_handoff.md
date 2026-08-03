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
- Custom retains the existing explicit collection order: time, interests, detail level.
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
python -m unittest -q test_p3_01_journey_mode.py
python -m unittest -v test_p3_01_journey_mode.py test_profile_dialogue.py test_agent_profile_collection.py test_agent_profile_route_integration.py test_tour_interaction.py
python -m unittest -q
```

Result: P3-01 contract tests 7/7 passed; the supporting interaction/profile regression and complete discovery regression both passed. Existing LangGraph node type warnings were emitted. Test-run Trace upload was unavailable in the sandboxed environment and is not LangSmith acceptance evidence.

## Next step

P3-03 may design and implement a read-only CardDispatcher. It must use this contract only as eligibility input and follow the approved classic-mode dispatch rules in `plan.md`; it must not introduce a second mode, a second state source, or active state takeover.
