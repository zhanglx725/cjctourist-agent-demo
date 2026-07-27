"""D1 internal, read-only contract for heterogeneous knowledge cards.

The contract is intentionally narrower than every source schema.  It keeps
the original payload for specialist modules and exposes only eligibility-gated
metadata for later D-stage orchestration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


RUNTIME_ORDER = {"enabled": 0, "attributed_only": 1, "disabled": 2}


def stricter_status(*statuses: str | None) -> str:
    """Return the fail-closed status when source and manifest disagree."""
    known = [status for status in statuses if status in RUNTIME_ORDER]
    return max(known, key=lambda status: RUNTIME_ORDER[status]) if known else "disabled"


@dataclass(frozen=True)
class KnowledgeCard:
    card_id: str
    card_type: str
    runtime_status: str
    allowed_capabilities: tuple[str, ...]
    allowed_scenarios: tuple[str, ...]
    source_refs: tuple[str, ...]
    applicable_node_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    raw_payload: dict[str, Any]
    visitor_visible: bool = True
    validation_errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("allowed_capabilities", "allowed_scenarios", "source_refs", "applicable_node_ids", "limitations", "validation_errors"):
            result[key] = list(result[key])
        return result
