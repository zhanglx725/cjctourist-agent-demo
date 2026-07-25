"""Print one deterministic reviewed route plan for human audit."""

from __future__ import annotations

import argparse

from route_planner import plan_template


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("route_id", nargs="?", default="highlights_30")
    args = parser.parse_args()
    plan = plan_template(args.route_id)
    print(f"路线：{plan.display_name}（目标 {plan.target_minutes} 分钟）")
    print("讲解停留：" + " → ".join(plan.stop_ids))
    print("完整节点：" + " → ".join(plan.full_path_node_ids))
    print("边：" + " → ".join(plan.edge_ids))
    print(f"预计步行：{plan.estimated_walk_seconds} 秒")
    print(f"预计讲解：{plan.estimated_explanation_seconds} 秒")
    print(f"预计观察：{plan.estimated_observation_seconds} 秒")
    print(f"预计互动：{plan.estimated_interaction_seconds} 秒")
    print(f"预计缓冲：{plan.estimated_buffer_seconds} 秒")
    print(f"预计总时长：{plan.estimated_total_seconds} 秒")
    print(f"预算达标：{plan.within_time_budget}")
    print("时间依据：" + "、".join(plan.walk_time_basis))
    for warning in plan.warnings:
        print("提示：" + warning)


if __name__ == "__main__":
    main()
