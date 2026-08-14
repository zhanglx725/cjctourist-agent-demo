"""Deterministic, source-free content planning for role narration.

The planner consumes only fact units emitted by the reviewed E5 renderer.  It
never infers facts from styled legacy prose, reads raw retrieval chunks, or
exposes source identifiers to the role model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


PLAN_SCHEMA_VERSION = "narration_content_plan_v3"


@dataclass(frozen=True)
class NarrationFact:
    fact_id: str
    semantic_role: str
    statement: str
    required: bool = True

    @property
    def unit_id(self) -> str:
        return self.fact_id.rsplit(":", 1)[0] if self.fact_id.rsplit(":", 1)[-1].isdigit() else self.fact_id

    @property
    def topic_kind(self) -> str:
        if self.semantic_role.startswith("space") or self.fact_id.startswith("space:"):
            return "space"
        if self.semantic_role.startswith("craft") or self.fact_id.startswith("craft:"):
            return "craft"
        return "ornament"

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "semantic_role": self.semantic_role,
            "statement": self.statement,
            "required": self.required,
            "unit_id": self.unit_id,
            "topic_kind": self.topic_kind,
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
    requested_scope: str = "whole_stop"
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
            "requested_scope": self.requested_scope,
            "allocated_content_seconds": self.allocated_content_seconds,
        }


def _rejected(
    reason: str, *, stop_id: str = "", style_id: str = "neutral", requested_scope: str = "whole_stop",
) -> NarrationContentPlan:
    return NarrationContentPlan(
        stop_id=stop_id, style_id=style_id, language="zh",
        budget_seconds=0, facts=(), must_include=(), already_covered=(),
        must_not_claim=(), interaction_allowed=False, requested_scope=requested_scope,
        status="rejected", reason_codes=(reason,),
    )


def build_narration_content_plan(
    *,
    public_message: str,
    stop_program: Mapping[str, Any] | None,
    render_audit: Mapping[str, Any] | None,
    visitor_profile: Mapping[str, Any] | None,
    narration_coverage: Mapping[str, Any] | None,
    request_text: str = "",
) -> NarrationContentPlan:
    """Build one immutable role-realization plan or a fail-closed rejection."""
    if not isinstance(stop_program, Mapping) or not isinstance(render_audit, Mapping):
        return _rejected("approved_guidance_unavailable")
    stop_id = str(stop_program.get("node_id") or "")
    style_id = str(render_audit.get("style_id") or "neutral")
    if not stop_id or not public_message.strip():
        return _rejected("approved_guidance_unavailable", stop_id=stop_id, style_id=style_id)
    request = str(request_text or "")
    asks_craft = any(token in request for token in ("工艺", "灰塑", "石雕", "木雕", "陶塑", "砖雕"))
    asks_ornament = any(token in request for token in ("纹样", "图案", "装饰", "独角狮", "福运", "花卉"))
    asks_space = any(token in request for token in ("建筑空间", "空间", "院落", "布局", "建筑"))
    requested_scope = (
        "craft" if asks_craft and not asks_ornament else
        "ornament" if asks_ornament and not asks_craft else
        "space" if asks_space and not (asks_craft or asks_ornament) else
        "whole_stop"
    )

    facts: list[NarrationFact] = []
    if requested_scope == "space":
        # Stop identity is already authoritative tour state.  It permits a
        # bounded answer to an architecture-space request without inventing
        # structural, historical, or visual details that were not reviewed.
        display_name = str(stop_program.get("display_name") or "当前点位").strip()
        facts.append(NarrationFact(
            f"space:{stop_id}", "space_identity", f"当前讲解点位为{display_name}。",
        ))
    audited_units = render_audit.get("fact_units")
    if isinstance(audited_units, list) and audited_units:
        expected_unit_ids = {
            *(f"craft:{value}" for value in render_audit.get("rendered_craft_ids", [])),
            *(f"ornament:{value}" for value in render_audit.get("rendered_ornament_ids", [])),
        }
        for raw_unit in audited_units:
            if not isinstance(raw_unit, Mapping):
                return _rejected("invalid_fact_unit", stop_id=stop_id, style_id=style_id)
            unit_id = str(raw_unit.get("unit_id") or "")
            topic_kind = str(raw_unit.get("topic_kind") or "")
            statements = raw_unit.get("statements")
            if (
                topic_kind not in {"space", "craft", "ornament"}
                or not unit_id
                or not isinstance(statements, list)
                or not statements
                or not all(isinstance(value, str) and value.strip() for value in statements)
            ):
                return _rejected("invalid_fact_unit", stop_id=stop_id, style_id=style_id)
            if topic_kind != "space" and unit_id not in expected_unit_ids:
                return _rejected("fact_unit_subject_mismatch", stop_id=stop_id, style_id=style_id)
            if requested_scope not in {"whole_stop", topic_kind}:
                continue
            selected = statements
            semantic_role = {
                "space": "space_identity",
                "craft": "craft_background",
                "ornament": "object_detail",
            }[topic_kind]
            for index, statement in enumerate(selected):
                # These strings were emitted from the reviewed deterministic
                # renderer.  Do not naturalize, trim internally, or otherwise
                # rewrite them at the role boundary.
                facts.append(NarrationFact(
                    f"{unit_id}:{index:03d}", semantic_role, statement,
                    bool(raw_unit.get("required", True)),
                ))
    else:
        # Older checkpoints do not carry an auditable fact-unit boundary.
        # Never guess that boundary from styled legacy prose: fail closed so
        # deterministic_narration_fallback republishes that prose unchanged.
        return _rejected(
            "fact_units_unavailable", stop_id=stop_id, style_id=style_id,
            requested_scope=requested_scope,
        )
    if not facts:
        return _rejected("requested_scope_unavailable", stop_id=stop_id, style_id=style_id, requested_scope=requested_scope)
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
        requested_scope=requested_scope,
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
            requested_scope=str(value.get("requested_scope") or "whole_stop"),
            allocated_content_seconds=max(
                0, int(value.get("allocated_content_seconds") or 0),
            ),
            status=str(value.get("status") or "rejected"),
            reason_codes=tuple(value.get("reason_codes", [])),
        )
    except (KeyError, TypeError, ValueError):
        return None
