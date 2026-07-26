"""CLI preview for deterministic dynamic route composition."""

import argparse

from dynamic_route_planner import eligible_dynamic_stops, plan_dynamic_route


parser = argparse.ArgumentParser()
parser.add_argument("minutes", type=int, help="available visit minutes (20-120)")
parser.add_argument("interests", nargs="*", help="e.g. 灰塑 三国 工艺")
parser.add_argument(
    "--exclude",
    action="append",
    default=[],
    help="guide-stop node_id not to select; it may still be used as a transit node; repeatable",
)
args = parser.parse_args()

route = plan_dynamic_route(args.minutes, args.interests, excluded_stop_ids=args.exclude)
names = {item.node_id: item.display_name for item in eligible_dynamic_stops()}
print("讲解点：" + " → ".join(names[node_id] for node_id in route.stop_ids))
print("讲解点 ID：" + " → ".join(route.stop_ids))
print("完整路径：" + " → ".join(route.full_path_node_ids))
print("边：" + " → ".join(route.edge_ids))
print(f"预计步行：{route.estimated_walk_seconds} 秒")
print(f"其中回到前院出口区：{route.estimated_exit_return_seconds} 秒（终点：{route.exit_node_id}）")
print(f"预计讲解：{route.estimated_guide_seconds} 秒")
print(f"预计观察：{route.estimated_observation_seconds} 秒")
print(f"预计互动：{route.estimated_interaction_seconds} 秒")
print(f"预计总时长：{route.estimated_total_seconds} 秒")
print(f"允许上限：{route.allowed_total_seconds} 秒")
print("提示：" + route.time_basis_warning)
if args.exclude:
    print("排除说明：--exclude 仅排除讲解停留点，不封锁该节点作为已审核通行路径。")
for score in route.selected_scores:
    print(score.node_id, round(score.total, 1), score.components)
