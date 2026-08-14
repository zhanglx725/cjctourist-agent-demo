"""Expression-only LLM judge for role-narration evaluation results.

This evaluator never decides factual truth, route correctness, state safety or
Active eligibility.  Those remain deterministic assertions.  It judges only
whether the already-validated expression feels like the selected role.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping

from langchain_deepseek import ChatDeepSeek

from narration_style_policy import compile_style_brief


QUALITY_SCHEMA_VERSION = "role_narration_style_judge_v1"
_FIELDS = frozenset({"role_fit", "naturalness", "distinctiveness", "readability", "rationale"})


@dataclass(frozen=True)
class StyleQualityJudgment:
    role_fit: int
    naturalness: int
    distinctiveness: int
    readability: int
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": QUALITY_SCHEMA_VERSION,
            "role_fit": self.role_fit,
            "naturalness": self.naturalness,
            "distinctiveness": self.distinctiveness,
            "readability": self.readability,
            "rationale": self.rationale,
            "average_score": round(
                (self.role_fit + self.naturalness + self.distinctiveness + self.readability) / 4,
                2,
            ),
        }


def style_quality_prompt(*, style_id: str, public_text: str) -> str:
    brief = compile_style_brief(style_id)
    payload = {
        "style_id": style_id,
        "persona": brief.persona,
        "generation_policy": brief.generation_policy,
        "acceptance_profile": brief.acceptance_profile,
        "public_text": public_text,
    }
    return """你是角色导游表达质量评审，只评价表达，不评价或补充历史事实。
候选中的审核事实已由确定性系统验证；不得根据任何外部知识判断其真假，
不得建议补充人物、年代、典故、寓意、路线或来源。

按 0–2 整数评分：
- role_fit：是否贴合指定人设、语气和互动边界；
- naturalness：是否自然，不是机械堆叠关键词；
- distinctiveness：与中性导游及其他常见角色是否有可辨认差异；
- readability：游客是否易读、连贯、不过分晦涩。
0=失败，1=部分满足，2=完全满足。rationale 最多 80 个中文字符，只说明表达问题。
输出严格 JSON，仅含 role_fit、naturalness、distinctiveness、readability、rationale。
输入如下：\n""" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _decode(content: Any) -> Mapping[str, Any] | None:
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content.strip())
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def evaluate_role_narration_style(*, style_id: str, public_text: str) -> dict[str, Any]:
    """Return a judge record; errors are explicit and never change publication."""
    if not os.getenv("DEEPSEEK_API_KEY"):
        return {"status": "unavailable", "reason": "DEEPSEEK_API_KEY is not set"}
    model = ChatDeepSeek(
        model=os.getenv("ROLE_NARRATION_JUDGE_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")),
        temperature=0,
        max_tokens=512,
        extra_body={"thinking": {"type": "disabled"}, "response_format": {"type": "json_object"}},
    )
    try:
        response = model.invoke(style_quality_prompt(style_id=style_id, public_text=public_text))
        value = _decode(response.content)
        if (
            not isinstance(value, Mapping)
            or frozenset(value) != _FIELDS
            or any(not isinstance(value[key], int) or value[key] not in {0, 1, 2}
                   for key in ("role_fit", "naturalness", "distinctiveness", "readability"))
            or not isinstance(value["rationale"], str)
            or len(value["rationale"]) > 80
        ):
            return {"status": "unavailable", "reason": "invalid_judge_schema"}
        return {"status": "scored", **StyleQualityJudgment(**value).to_dict()}
    except Exception as exc:
        return {"status": "unavailable", "reason": f"judge_error:{type(exc).__name__}"}
