"""Deterministic service units appended after accepted point narration.

The role model never sees or rewrites these units.  They are derived from the
current TourState and already-reviewed optional photo guidance, validated as
one freshness-bound presentation, and only then consumed by narration_commit.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from controlled_knowledge_query import public_visitor_message_or_fallback
from tour_navigation import (
    TourNavigationError,
    format_next_stop_navigation,
    next_stop_navigation,
)


SERVICE_TAIL_SCHEMA_VERSION = "stop_service_tail_v1"
COMPLETION_PROMPT = "讲解结束后，您可确认是否完成本点参观。"
_HEADING = re.compile(r"【[^】]+】")
_MARKDOWN = re.compile(r"(?m)^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)、]\s+)")
_MALFORMED_PUNCTUATION = re.compile(r"(?:[。！？]{2,}|[，、]{2,}|～)")
_INTERNAL = re.compile(
    r"(?:https?://|file://|[A-Za-z]:\\|source[_ ]?ids?|node[_ ]?id|raw[_ ]?chunk)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PointServiceUnit:
    unit_id: str
    service_kind: str
    public_text: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "service_kind": self.service_kind,
            "public_text": self.public_text,
            "required": self.required,
        }


@dataclass(frozen=True)
class StopServiceTail:
    stop_id: str
    route_id: str
    next_stop_id: str | None
    photo_spot_id: str | None
    route_fingerprint: str
    photo_plan_fingerprint: str | None
    units: tuple[PointServiceUnit, ...]
    status: str = "ready"
    reason_codes: tuple[str, ...] = ()
    schema_version: str = SERVICE_TAIL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "stop_id": self.stop_id,
            "route_id": self.route_id,
            "next_stop_id": self.next_stop_id,
            "photo_spot_id": self.photo_spot_id,
            "route_fingerprint": self.route_fingerprint,
            "photo_plan_fingerprint": self.photo_plan_fingerprint,
            "units": [unit.to_dict() for unit in self.units],
        }


@dataclass(frozen=True)
class StopServiceTailValidation:
    validation_status: str
    reason_codes: tuple[str, ...]
    public_text: str
    service_unit_kinds: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_status": self.validation_status,
            "reason_codes": list(self.reason_codes),
            "public_text": self.public_text,
            "service_unit_kinds": list(self.service_unit_kinds),
        }


def _future_stop_id(tour_state: Mapping[str, Any]) -> str | None:
    current = str(tour_state.get("current_stop_id") or "")
    for value in tour_state.get("remaining_stop_ids", ()):
        stop_id = str(value or "")
        if stop_id and stop_id != current:
            return stop_id
    return None


def _fingerprint(value: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    payload = {key: value.get(key) for key in keys}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _route_fingerprint(tour_state: Mapping[str, Any]) -> str:
    return _fingerprint(
        tour_state,
        ("selected_route_id", "route_stop_ids", "current_stop_id", "remaining_stop_ids"),
    )


def _photo_plan_fingerprint(photo_plan: Mapping[str, Any] | None) -> str | None:
    if not isinstance(photo_plan, Mapping):
        return None
    return _fingerprint(
        photo_plan,
        ("schema_version", "route_id", "planned_stop_ids", "triggered_stop_ids"),
    )


def _continuous(value: str) -> str:
    return " ".join(part.strip() for part in str(value or "").splitlines() if part.strip())


def _photo_text(value: str) -> str:
    lines = [part.strip() for part in str(value or "").splitlines() if part.strip()]
    if not lines:
        return ""
    lines[0] = re.sub(r"^【打卡姿势建议】\s*", "", lines[0]).strip()
    return " ".join(part for part in lines if part)


def build_stop_service_tail(
    *,
    tour_state: Mapping[str, Any] | None,
    photo_guidance_message: str | None = None,
    photo_spot_id: str | None = None,
    photo_plan: Mapping[str, Any] | None = None,
) -> StopServiceTail:
    """Build service units from current deterministic business outputs."""
    tour = dict(tour_state or {})
    stop_id = str(tour.get("current_stop_id") or "")
    route_id = str(tour.get("selected_route_id") or "")
    if not stop_id or not route_id:
        return StopServiceTail(
            stop_id=stop_id,
            route_id=route_id,
            next_stop_id=None,
            photo_spot_id=None,
            route_fingerprint=_route_fingerprint(tour),
            photo_plan_fingerprint=None,
            units=(),
            status="rejected",
            reason_codes=("service_freshness_unavailable",),
        )

    next_stop_id = _future_stop_id(tour)
    try:
        navigation = (
            next_stop_navigation(tour, target_stop_id=next_stop_id)
            if next_stop_id is not None
            else None
        )
        navigation_text = _continuous(format_next_stop_navigation(navigation))
    except (TourNavigationError, KeyError, TypeError, ValueError):
        return StopServiceTail(
            stop_id=stop_id,
            route_id=route_id,
            next_stop_id=next_stop_id,
            photo_spot_id=None,
            route_fingerprint=_route_fingerprint(tour),
            photo_plan_fingerprint=None,
            units=(),
            status="rejected",
            reason_codes=("next_stop_guidance_unavailable",),
        )

    units = [
        PointServiceUnit(
            unit_id="service:completion_prompt",
            service_kind="completion_prompt",
            public_text=COMPLETION_PROMPT,
        ),
        PointServiceUnit(
            unit_id="service:next_stop",
            service_kind="next_stop",
            public_text=f"完成本点后，{navigation_text}",
        ),
    ]
    normalized_photo = _photo_text(photo_guidance_message or "")
    if normalized_photo:
        units.append(PointServiceUnit(
            unit_id="service:photo_guidance",
            service_kind="photo_guidance",
            public_text=normalized_photo,
            required=False,
        ))
    return StopServiceTail(
        stop_id=stop_id,
        route_id=route_id,
        next_stop_id=next_stop_id,
        photo_spot_id=str(photo_spot_id or "") or None,
        route_fingerprint=_route_fingerprint(tour),
        photo_plan_fingerprint=(
            _photo_plan_fingerprint(photo_plan) if normalized_photo else None
        ),
        units=tuple(units),
    )


def stop_service_tail_from_dict(value: Mapping[str, Any] | None) -> StopServiceTail | None:
    if (
        not isinstance(value, Mapping)
        or value.get("schema_version") != SERVICE_TAIL_SCHEMA_VERSION
        or not isinstance(value.get("units"), list)
    ):
        return None
    try:
        units = tuple(
            PointServiceUnit(
                unit_id=str(item["unit_id"]),
                service_kind=str(item["service_kind"]),
                public_text=str(item["public_text"]),
                required=bool(item.get("required", True)),
            )
            for item in value["units"]
        )
        return StopServiceTail(
            stop_id=str(value.get("stop_id") or ""),
            route_id=str(value.get("route_id") or ""),
            next_stop_id=(str(value["next_stop_id"]) if value.get("next_stop_id") else None),
            photo_spot_id=(str(value["photo_spot_id"]) if value.get("photo_spot_id") else None),
            route_fingerprint=str(value.get("route_fingerprint") or ""),
            photo_plan_fingerprint=(
                str(value["photo_plan_fingerprint"])
                if value.get("photo_plan_fingerprint") else None
            ),
            units=units,
            status=str(value.get("status") or "rejected"),
            reason_codes=tuple(str(item) for item in value.get("reason_codes", ())),
        )
    except (KeyError, TypeError, ValueError):
        return None


def validate_stop_service_tail(
    tail: StopServiceTail | None,
    *,
    tour_state: Mapping[str, Any] | None,
    photo_plan: Mapping[str, Any] | None,
    publish: bool,
) -> StopServiceTailValidation:
    """Validate exact service content and freshness before commit."""
    if not publish:
        return StopServiceTailValidation("accepted", (), "", ())
    if tail is None:
        return StopServiceTailValidation("rejected", ("service_tail_missing",), "", ())
    reasons = list(tail.reason_codes)
    if tail.status != "ready":
        reasons.append("service_tail_not_ready")
    tour = dict(tour_state or {})
    if (
        tail.stop_id != str(tour.get("current_stop_id") or "")
        or tail.route_id != str(tour.get("selected_route_id") or "")
        or tail.next_stop_id != _future_stop_id(tour)
        or tail.route_fingerprint != _route_fingerprint(tour)
    ):
        reasons.append("service_tail_stale")
    kinds = tuple(unit.service_kind for unit in tail.units)
    if kinds[:2] != ("completion_prompt", "next_stop"):
        reasons.append("service_unit_order_invalid")
    if len(kinds) != len(set(kinds)):
        reasons.append("service_unit_duplicate")
    completion = next(
        (unit for unit in tail.units if unit.service_kind == "completion_prompt"), None
    )
    if completion is None or completion.public_text != COMPLETION_PROMPT:
        reasons.append("completion_prompt_invalid")
    photo = next((unit for unit in tail.units if unit.service_kind == "photo_guidance"), None)
    if photo is not None:
        plan = dict(photo_plan or {})
        if (
            plan.get("route_id") != tail.route_id
            or tail.stop_id not in plan.get("triggered_stop_ids", ())
            or not tail.photo_spot_id
            or tail.photo_plan_fingerprint != _photo_plan_fingerprint(plan)
        ):
            reasons.append("photo_guidance_stale")
    elif tail.photo_spot_id:
        reasons.append("photo_guidance_missing")

    texts = [unit.public_text.strip() for unit in tail.units]
    for text in texts:
        if (
            not text
            or "\n" in text
            or _HEADING.search(text)
            or _MARKDOWN.search(text)
            or _MALFORMED_PUNCTUATION.search(text)
            or _INTERNAL.search(text)
            or public_visitor_message_or_fallback(text) != text
        ):
            reasons.append("service_public_text_invalid")
            break
    public_text = " ".join(texts)
    return StopServiceTailValidation(
        "accepted" if not reasons else "rejected",
        tuple(dict.fromkeys(reasons)),
        public_text if not reasons else "",
        kinds,
    )


def compose_stop_presentation(narration_text: str, service_text: str) -> str:
    """Compose the already-validated visitor response without adding prose."""
    return " ".join(value.strip() for value in (narration_text, service_text) if value.strip())
