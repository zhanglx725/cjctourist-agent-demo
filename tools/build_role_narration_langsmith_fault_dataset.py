"""Build and optionally upload high-risk fallback cases for role narration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from narration_style_policy import compile_style_brief
from tools.build_role_narration_langsmith_dataset import load_project_env, upload_dataset


DATASET_NAME = "chen-clan-academy-role-narration-stop-guidance-fallback-v1"
OUTPUT = ROOT / "data" / "chen_clan_academy" / "evaluation" / "langsmith" / "role_narration_stop_guidance_fallback_v1.jsonl"
FACT = "栏板可见花卉纹样。"

CASES = (
    ("ancient_scholar", "fact_drift", "unapproved_fact_trigger", "候选连接语新增未经审核的年代、人物、传说、寓意或排名。"),
    ("cantonese_storyteller", "fact_drift", "unapproved_fact_trigger", "候选连接语补编未经审核的讲古情节。"),
    ("ancient_scholar", "style_forbidden", "style_forbidden_marker", "候选连接语命中该风格禁用表达。"),
    ("bestie_chat", "style_forbidden", "style_forbidden_marker", "候选连接语使用过度网络梗或虚构八卦。"),
    ("listen_only", "interaction_violation", "style_interaction_contract_violation", "静听模式出现问题、任务、拍照或动作要求。"),
    ("photo_guide", "interaction_violation", "unsafe_or_coercive_expression", "摄影表达引导攀爬、阻塞通道或承诺出片。"),
    ("exploration_game", "interaction_violation", "style_interaction_contract_violation", "闯关表达设置强制任务、奖惩或虚构谜底。"),
    ("dominant_ceo", "model_failure", "model_unavailable", "模型超时或不可用。"),
    ("cute_junior", "model_failure", "invalid_candidate_schema", "模型返回非法 JSON 或越界字段。"),
    ("professional", "budget_exceeded", "budget_exceeded", "候选连接语超过角色表达预算。"),
    ("hostel_scholar", "budget_exceeded", "candidate_budget_exceeded", "候选整体超过 ContentPlan 预算。"),
    ("xiguan_young_master", "internal_leak", "internal_field_leak", "候选泄露 source_ids、节点或文件路径等内部字段。"),
)


def build_examples() -> list[dict]:
    examples = []
    for style_id, failure_type, reason, description in CASES:
        brief = compile_style_brief(style_id)
        profile = brief.acceptance_profile
        examples.append({
            "inputs": {
                "case_id": f"role_fallback_v1_{style_id}_{failure_type}",
                "style_id": style_id,
                "scene_kind": "stop_guidance",
                "fact_id": "ornament:orn_005",
                "approved_fact": FACT,
                "failure_type": failure_type,
                "injected_or_expected_reason": reason,
                "failure_description": description,
                "interaction_allowed": style_id != "listen_only",
                "interaction_contract": profile["interaction_contract"],
                "safety_boundaries": ["审核事实不得改写", "不得写入 TourState、路线或画像"],
            },
            "outputs": {
                "expected_active_takeover": False,
                "expected_fallback_used": True,
                "expected_commit_decision": "legacy_fallback_published",
                "expected_reason_code": reason,
                "expected_legacy_message_preserved": True,
                "expected_state_writes": [],
                "expected_coverage_commit_count": 1,
            },
            "metadata": {
                "dataset_version": "v1", "evaluation_scope": "role_narration_fallback",
                "style_display_name": brief.display_name,
            },
        })
    return examples


def write_local(examples: list[dict]) -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in examples), encoding="utf-8")
    return OUTPUT


def upload(examples: list[dict]) -> str:
    # Reuse the guarded upload implementation with this dataset's name.
    import tools.build_role_narration_langsmith_dataset as base
    original = base.DATASET_NAME
    base.DATASET_NAME = DATASET_NAME
    try:
        return upload_dataset(examples)
    finally:
        base.DATASET_NAME = original


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    load_project_env()
    examples = build_examples()
    if len(examples) != 12:
        raise RuntimeError(f"Expected 12 fallback examples, got {len(examples)}")
    print(f"local_dataset={write_local(examples)}")
    print(f"dataset_name={DATASET_NAME}")
    print(f"example_count={len(examples)}")
    print(f"remote_dataset_id={upload(examples)}" if args.upload else "remote_dataset_status=not_uploaded")


if __name__ == "__main__":
    main()
