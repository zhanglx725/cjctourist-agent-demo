"""Deterministic, source-free content planning for role narration.

The planner consumes only the already-approved public E5 sections plus their
reviewed subject identifiers. It never reads raw retrieval chunks or exposes
source identifiers to the role model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


PLAN_SCHEMA_VERSION = "narration_content_plan_v1"
_SECTION = re.compile(r"【([^】]+)】\s*(.*?)(?=\n\s*【|\Z)", re.DOTALL)


@dataclass(frozen=True)
class NarrationFact:
    fact_id: str
    semantic_role: str
    statement: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "semantic_role": self.semantic_role,
            "statement": self.statement,
            "required": self.required,
        }


@dataclass(frozen=True)
class NarrationContentPlan:
    stop_id: str
    style_id: str
    language: str
    budget_seconds: int
    facts: tuple[NarrationFact, ...]
    must_include: tuple[str, ...]
    already_covered: tuple[str, ...]
    must_not_claim: tuple[str, ...]
    interaction_allowed: bool
    # Authoritative duration already allocated by the reviewed E5 renderer.
    # Role realization may spend only the remaining duration on connective
    # prose; approved fact text must not be rejected by a second char-count
    # estimate that disagrees with E5.
    allocated_content_seconds: int = 0
    status: str = "ready"
    reason_codes: tuple[str, ...] = ()
    schema_version: str = PLAN_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "stop_id": self.stop_id,
            "style_id": self.style_id,
            "language": self.language,
            "budget_seconds": self.budget_seconds,
            "facts": [fact.to_dict() for fact in self.facts],
            "must_include": list(self.must_include),
            "already_covered": list(self.already_covered),
            "must_not_claim": list(self.must_not_claim),
            "interaction_allowed": self.interaction_allowed,
            "allocated_content_seconds": self.allocated_content_seconds,
        }


def _clean_statement(value: str) -> str:
    return "\n".join(line.strip() for line in value.splitlines() if line.strip()).strip()


_REVIEWED_LOCATION = re.compile(
    r"它与(?P<location>[^。；]+?)存在审核关联；可结合现场标识观察。"
)
_REVIEWED_OBSERVATION = re.compile(
    r"观察时，可结合(?P<location>[^。；]+?)处的构件位置辨认其造型。"
)


def _naturalize_reviewed_statement(value: str) -> str:
    """Polish known review boilerplate without changing its fact boundary.

    This is deliberately deterministic and narrow.  It only rewrites the two
    public E5 location templates that otherwise make a role narration sound
    like an internal audit report.  The reviewed location stays intact, no
    new claim is introduced, and the resulting text remains the immutable
    statement associated with the same fact ID for generation and validation.
    """

    matched_locations: set[str] = set()

    def replace_location(match: re.Match[str]) -> str:
        location = match.group("location").strip()
        matched_locations.add(location)
        return f"可以先对照现场标识，在{location}寻找它。"

    result = _REVIEWED_LOCATION.sub(replace_location, value)

    def replace_observation(match: re.Match[str]) -> str:
        location = match.group("location").strip()
        if location in matched_locations:
            return "找到位置后，再留意它的造型和细节。"
        return f"可以沿着{location}看过去，重点留意它的造型和细节。"

    return _REVIEWED_OBSERVATION.sub(replace_observation, result)


def _rejected(reason: str, *, stop_id: str = "", style_id: str = "neutral") -> NarrationContentPlan:
    return NarrationContentPlan(
        stop_id=stop_id, style_id=style_id, language="zh",
        budget_seconds=0, facts=(), must_include=(), already_covered=(),
        must_not_claim=(), interaction_allowed=False,
        status="rejected", reason_codes=(reason,),
    )


def build_narration_content_plan(
    *,
    public_message: str,
    stop_program: Mapping[str, Any] | None,
    render_audit: Mapping[str, Any] | None,
    visitor_profile: Mapping[str, Any] | None,
    narration_coverage: Mapping[str, Any] | None,
) -> NarrationContentPlan:
    """Build one immutable role-realization plan or a fail-closed rejection."""
    if not isinstance(stop_program, Mapping) or not isinstance(render_audit, Mapping):
        return _rejected("approved_guidance_unavailable")
    stop_id = str(stop_program.get("node_id") or "")
    style_id = str(render_audit.get("style_id") or "neutral")
    if not stop_id or not public_message.strip():
        return _rejected("approved_guidance_unavailable", stop_id=stop_id, style_id=style_id)
    sections = {title.strip(): _clean_statement(body) for title, body in _SECTION.findall(public_message)}
    items = {
        str(item.get("ornament_id")): str(item.get("name"))
        for item in stop_program.get("selected_items", [])
        if isinstance(item, Mapping) and item.get("ornament_id") and item.get("name")
    }
    facts: list[NarrationFact] = []
    for craft_id in render_audit.get("rendered_craft_ids", []):
        statement = _naturalize_reviewed_statement(
            sections.get(f"工艺背景：{craft_id}", "")
        )
        if not statement:
            return _rejected("craft_section_mismatch", stop_id=stop_id, style_id=style_id)
        facts.append(NarrationFact(f"craft:{craft_id}", "craft_background", statement))
    for ornament_id in render_audit.get("rendered_ornament_ids", []):
        object_name = items.get(str(ornament_id))
        statement = (
            _naturalize_reviewed_statement(
                sections.get(f"观察对象：{object_name}", "")
            )
            if object_name else ""
        )
        if not statement:
            return _rejected("ornament_section_mismatch", stop_id=stop_id, style_id=style_id)
        facts.append(NarrationFact(f"ornament:{ornament_id}", "object_detail", statement))
    if not facts:
        return _rejected("no_approved_facts", stop_id=stop_id, style_id=style_id)
    profile = dict(visitor_profile or {})
    interaction_allowed = style_id != "listen_only"
    introduced = narration_coverage or {}
    already_covered = tuple(
        sorted(
            f"craft:{value}" for value in introduced.get("introduced_craft_ids", [])
        )
        + sorted(
            f"ornament:{value}" for value in introduced.get("introduced_ornament_ids", [])
        )
    )
    return NarrationContentPlan(
        stop_id=stop_id,
        style_id=style_id,
        language=str(profile.get("language") or "zh"),
        budget_seconds=max(0, int(render_audit.get("content_budget_seconds") or 0)),
        facts=tuple(facts),
        must_include=("space_or_object_identity", "approved_observation_detail"),
        already_covered=already_covered,
        must_not_claim=(
            "unreviewed_person", "unreviewed_date", "unreviewed_story",
            "absolute_ranking", "official_certification",
        ),
        interaction_allowed=interaction_allowed,
        allocated_content_seconds=max(
            0, int(render_audit.get("allocated_content_seconds") or 0),
        ),
    )


def narration_content_plan_from_dict(value: Mapping[str, Any] | None) -> NarrationContentPlan | None:
    if not isinstance(value, Mapping) or value.get("schema_version") != PLAN_SCHEMA_VERSION:
        return None
    try:
        facts = tuple(
            NarrationFact(
                fact_id=str(item["fact_id"]), semantic_role=str(item["semantic_role"]),
                statement=str(item["statement"]), required=bool(item.get("required", True)),
            )
            for item in value.get("facts", [])
        )
        return NarrationContentPlan(
            stop_id=str(value.get("stop_id") or ""), style_id=str(value.get("style_id") or "neutral"),
            language=str(value.get("language") or "zh"), budget_seconds=int(value.get("budget_seconds") or 0),
            facts=facts, must_include=tuple(value.get("must_include", [])),
            already_covered=tuple(value.get("already_covered", [])),
            must_not_claim=tuple(value.get("must_not_claim", [])),
            interaction_allowed=bool(value.get("interaction_allowed")),
            allocated_content_seconds=max(
                0, int(value.get("allocated_content_seconds") or 0),
            ),
            status=str(value.get("status") or "rejected"),
            reason_codes=tuple(value.get("reason_codes", [])),
        )
    except (KeyError, TypeError, ValueError):
        return None
