"""Build and optionally upload the 18-style stop-guidance LangSmith dataset.

The local JSONL is the reviewable source artifact.  Upload is deliberately
opt-in so an unconfigured workstation never claims a remote dataset exists.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

DATASET_NAME = "chen-clan-academy-role-narration-stop-guidance-v1"
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from narration_style_policy import approved_style_ids, compile_style_brief


OUTPUT = ROOT / "data" / "chen_clan_academy" / "evaluation" / "langsmith" / "role_narration_stop_guidance_v1.jsonl"

POINT_TEMPLATES = (
    {
        "point_type": "building",
        "fact_id": "space:front_courtyard_roof",
        "approved_fact": "审核事实：屋脊位于前院中部。",
        "safety_boundaries": ["不得新增路线、空间定位或现场对象", "不得泄露内部字段"],
    },
    {
        "point_type": "craft",
        "fact_id": "craft:灰塑",
        "approved_fact": "审核事实：该构件采用灰塑工艺。",
        "safety_boundaries": ["不得新增年代、人物、传说或认证", "不得改写审核事实"],
    },
    {
        "point_type": "ornament",
        "fact_id": "ornament:orn_005",
        "approved_fact": "审核事实：栏板可见花卉纹样。",
        "safety_boundaries": ["不得触摸、攀爬、跨越护栏或阻塞通道", "不得新增未经审核的寓意"],
    },
)


def load_project_env(path: Path = ROOT / ".env") -> None:
    """Load local dotenv values without overriding explicit shell settings."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def _example(style_id: str, template: dict[str, Any]) -> dict[str, Any]:
    brief = compile_style_brief(style_id)
    profile = brief.acceptance_profile
    interaction = dict(profile["interaction_contract"])
    interaction_allowed = interaction["mode"] != "none"
    boundaries = [*template["safety_boundaries"]]
    if not interaction_allowed:
        boundaries.append("不得提问、布置任务、要求拍照或动作")
    if interaction["mode"] == "safe_optional_photo":
        boundaries.append("仅允许安全位置的可选观察或构图提示")
    if interaction["mode"] == "optional_clue":
        boundaries.append("线索仅可基于审核事实，不得设置强制闯关、奖惩或虚构谜底")
    return {
        "inputs": {
            "case_id": f"role_stop_v1_{style_id}_{template['point_type']}",
            "style_id": style_id,
            "scene_kind": "stop_guidance",
            "point_type": template["point_type"],
            "fact_id": template["fact_id"],
            "approved_fact": template["approved_fact"],
            "interaction_allowed": interaction_allowed,
            "interaction_contract": interaction,
            "required_style_markers": list(profile["required_markers"]),
            "forbidden_style_markers": list(profile["forbidden_markers"]),
            "rhythm": dict(profile["rhythm"]),
            "point_narration_strategy": list(profile["point_narration_strategy"]),
            "safety_boundaries": boundaries,
        },
        "outputs": {
            "expected_scene_kind": "stop_guidance",
            "expected_fact_ids": [template["fact_id"]],
            "required_fact_verbatim": [template["approved_fact"]],
            "expected_active_eligible": True,
            "expected_state_writes": [],
            # Space-only fixtures have no reviewed introduction subject. Craft
            # and ornament fixtures exercise the real single-submit path.
            "expected_coverage_commit_count": 0 if template["point_type"] == "building" else 1,
            "expected_fallback_on_validation_failure": True,
        },
        "metadata": {
            "dataset_version": "v1",
            "style_display_name": brief.display_name,
            "evaluation_scope": "role_narration_stop_guidance",
            "source": "reviewed_role_acceptance_profile",
        },
    }


def build_examples() -> list[dict[str, Any]]:
    return [
        _example(style_id, template)
        for style_id in approved_style_ids()
        for template in POINT_TEMPLATES
    ]


def write_local_dataset(examples: list[dict[str, Any]], output: Path = OUTPUT) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in examples),
        encoding="utf-8",
    )
    return output


def upload_dataset(examples: list[dict[str, Any]]) -> str:
    if not (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")):
        raise RuntimeError("LANGSMITH_API_KEY or LANGCHAIN_API_KEY is required for --upload")
    try:
        from langsmith import Client
    except ImportError as exc:
        raise RuntimeError("Install the langsmith package before using --upload") from exc
    client = Client()
    try:
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
    except Exception:  # Dataset may not exist; create it once with a description.
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="18 styles × 3 reviewed stop-guidance point types; generated from reviewed role contracts.",
        )
    existing = list(client.list_examples(dataset_id=dataset.id))
    if existing:
        raise RuntimeError(f"Dataset already contains {len(existing)} examples; refusing duplicate upload")
    client.create_examples(
        inputs=[item["inputs"] for item in examples],
        outputs=[item["outputs"] for item in examples],
        metadata=[item["metadata"] for item in examples],
        dataset_id=dataset.id,
    )
    return str(dataset.id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload", action="store_true", help="Create the remote LangSmith dataset after writing JSONL")
    args = parser.parse_args()
    load_project_env()
    examples = build_examples()
    if len(examples) != 54:
        raise RuntimeError(f"Expected 54 examples, got {len(examples)}")
    output = write_local_dataset(examples)
    print(f"local_dataset={output}")
    print(f"dataset_name={DATASET_NAME}")
    print(f"example_count={len(examples)}")
    if args.upload:
        print(f"remote_dataset_id={upload_dataset(examples)}")
    else:
        print("remote_dataset_status=not_uploaded")


if __name__ == "__main__":
    main()
