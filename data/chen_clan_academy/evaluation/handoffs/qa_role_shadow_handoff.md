# QA Role Shadow Handoff

## Scope

- `tour_qa` and `qa_follow_up_detail` build a bounded `qa_content_plan` from the already-approved public answer.
- The role layer receives no raw retrieval chunks, source IDs, route data, or mutable state.
- Role candidates are validated and recorded in Shadow only; the legacy QA answer remains visitor-visible.

## Verified behavior

- Child, professional, and listen-only manual samples were accepted.
- Follow-up detail inherits the selected role and the immediately preceding validated QA scope.
- Listen-only plans set `interaction_allowed=false`.
- Invalid candidates fail closed while preserving the legacy answer.
- Agent Server checkpoint recovery uses only graph-authored, schema-validated bounded QA metadata.

## Boundaries

- `active_takeover=false`
- `legacy_message_preserved=true`
- `state_writes=[]`
- No changes to TourState, VisitorProfile, route, proposal, Coverage, RAG, or knowledge cards.
- QA Active is outside the competition freeze scope.

## Validation evidence

- QA/context targeted suite: `23/23 passed_by_operator`
- Earlier phase P0 matrix: `3/3 passed_by_operator`
- Earlier phase full regression: `1099/1099 passed_by_operator`
- Trace metadata: `unavailable` where not recorded.

