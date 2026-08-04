# P4-01 TourOpeningProgram Handoff

## Scope

P4-01 adds one deterministic, optional opening program per newly initialized
route. It is separate from TourState, VisitorProfile, StopProgram, and
NarrationCoverage.

## Contract

- A successful new route initializes `tour_opening_program.status=pending`.
- The route response offers `开始介绍` and `跳过介绍`.
- Explicit play renders only approved facts from
  `tour_opening_evidence_v1.json` and changes the status to `played`.
- Explicit skip changes the status to `skipped` without loading or claiming
  narration coverage.
- Explicit replay is allowed after either play or skip and increments only the
  opening `play_count`.
- Ordinary QA does not match the narrow opening vocabulary, so a QA
  interruption leaves the opening state unchanged and the visitor may resume
  it afterward.
- Replanning does not initialize or overwrite the opening program, preventing
  automatic duplicate playback.
- Source IDs and fact IDs remain in `tour_opening_evaluations`; they never
  appear in the visitor body.

## Failure behavior

Missing, malformed, empty, or unapproved opening evidence fails closed with a
public-safe availability message. The established route remains usable and no
other state is written.

## Automated verification

Run:

```text
python -m unittest -v test_tour_opening_program.py test_agent_profile_route_integration.py test_p3_01_journey_mode.py
python -m unittest discover -v
git diff --check
```

The Codex filesystem sandbox could not launch the user's system Python, so the
operator must run these commands in the working local `.venv` before commit.

## LangSmith acceptance

Use a new thread for each case and retain tested commit, Thread ID, Trace URL,
node path, final opening program, audit, protected-state diff, and visitor body.

1. Establish a route, then `开始介绍`: path reaches `tour_opening`, status is
   `played`, play count is 1, and no protected state changes.
2. Establish a route, then `跳过介绍`: status is `skipped`, Coverage stays
   empty, and navigation remains available.
3. After play or skip, `重播开场`: same approved body, play count increments,
   and no Coverage is submitted.
4. While pending, ask an ordinary venue question, then `开始介绍`: QA uses its
   controlled route, opening remains pending during QA, and resumes afterward.
5. Play once, perform an accepted replan, then continue: replan does not reset
   or automatically replay the opening.

