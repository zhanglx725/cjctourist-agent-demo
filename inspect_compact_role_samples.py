"""Print deterministic Phase 3C compact narration samples for human review."""
from __future__ import annotations

from narration_content_plan import NarrationContentPlan, NarrationFact
from narration_style_policy import compile_style_brief
from narration_validation import validate_stop_guidance_role_narration
from role_narration_generation import RoleNarrationCandidate, apply_point_narration_scaffold


STYLES = ("child", "ancient_scholar", "dominant_ceo")
FACTS = (
    NarrationFact(
        "craft:stucco:000", "craft_background",
        "灰塑是以石灰为主料塑造并施彩的建筑装饰工艺。",
    ),
    NarrationFact(
        "craft:stucco:001", "craft_detail",
        "制作时先用草筋灰塑造造型，再用纸筋灰细塑表面。",
    ),
    NarrationFact(
        "ornament:pine_crane:000", "object_detail",
        "前院中部的灰塑可见松与鹤的组合。",
    ),
)


def build_plan(style_id: str) -> NarrationContentPlan:
    return NarrationContentPlan(
        stop_id="stop_front_courtyard_center",
        style_id=style_id,
        language="zh",
        budget_seconds=60,
        allocated_content_seconds=40,
        facts=FACTS,
        must_include=(),
        already_covered=(),
        must_not_claim=(),
        interaction_allowed=True,
        scaffold_mode="compact",
    )


def main() -> None:
    for style_id in STYLES:
        plan = build_plan(style_id)
        brief = compile_style_brief(style_id)
        raw = RoleNarrationCandidate(
            style_id=style_id,
            public_text="".join(fact.statement for fact in FACTS),
            used_fact_ids=tuple(fact.fact_id for fact in FACTS),
            omitted_fact_ids=(),
            self_check={
                "added_new_facts": False,
                "role_consistent": True,
                "within_budget": True,
            },
            model_called=False,
            latency_ms=0,
        )
        candidate = apply_point_narration_scaffold(raw, plan, brief, compact=True)
        validation = validate_stop_guidance_role_narration(
            candidate, plan, brief, compact=True,
        )
        print(f"\n=== {style_id} | {validation.validation_status} ===")
        print(candidate.public_text)
        print(f"reason_codes={list(validation.reason_codes)}")


if __name__ == "__main__":
    main()
