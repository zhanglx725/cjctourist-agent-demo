# P4-03 TitleAwardPolicy and Blessing Handoff

## Scope

P4-03 consumes only the audited `visit_summary.title_basis`. It deterministically
selects one versioned, playful title and an original short blessing. It never
reads raw chat text for personality inference and never changes TourState,
VisitorProfile, route, opening state, or NarrationCoverage.

## Policy v1

Fixed priority:

1. At least three in-tour questions: `好奇探索家`.
2. At least two exact interest/content matches: `岭南知艺人`.
3. At least five successful craft/topic signals: `百艺巡游者`.
4. Story style plus at least two heard topics: `故事寻踪者`.
5. Completed route with at least two visited stops: `陈家祠行旅完成者`.
6. Neutral fallback: `陈家祠漫游者`.

Every result includes the policy version, stable title ID, auditable reason,
original blessing, basis snapshot, and a statement that the title is a playful
souvenir rather than official certification or visitor rating.

## Graph contract

- Successful `visit_summary` automatically continues to
  `post_visit_title_blessing`.
- After completion, `结束游览`, summary requests, and title/blessing requests
  remain in the post-visit flow and never enter `journey_mode_selection`.
- Repeated requests return the same deterministic result for the same summary.
- Invalid/missing summary fails closed without free LLM generation.

## Approved future candidate-rotation contract

After the manually reviewed title catalog is populated, an explicit visitor
request such as `换一个称号` may advance through approved and enabled
candidates inside the already selected `category_id` only. Candidate order
must be frozen and versioned; a thread-local `variant_cursor` records the
selection so replay is deterministic and auditable. Ordinary repeat/view
requests remain idempotent and return the current candidate.

Rotation must never change `title_basis`, reclassify the visitor, select a
draft/disabled candidate, randomly sample, or ask an API to invent a title.
If the category contains only one approved candidate, the visitor receives a
transparent no-alternative message. Exhaustion behavior (stop or versioned
wraparound) must be fixed before activation and covered by tests.

## Related routing fix

During a navigating phase, the bounded forms `到达`, `我到下一个点位了`, and
`我到下一站了` bind only the one formal pending stop and enter `tour_event`.
They never fall through to LLM/RAG and still do not mark the stop visited until
explicit completion confirmation.
