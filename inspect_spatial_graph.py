"""Print a reviewed spatial route for manual inspection."""

from __future__ import annotations

import argparse

from spatial_graph import shortest_route, unreachable_guide_stops


parser = argparse.ArgumentParser(description="Inspect reviewed Chen Clan Academy spatial routes.")
parser.add_argument("source", nargs="?", default="entrance_main_outside")
parser.add_argument("target", nargs="?", default="stop_juxian_hall")
args = parser.parse_args()

route = shortest_route(args.source, args.target)
print("路线：" + " → ".join(route.names))
print("节点：" + " → ".join(route.node_ids))
print("边：" + " → ".join(route.edge_ids))
print(
    "预计步行时间："
    + (
        f"约 {route.estimated_walk_seconds} 秒（地图估算，待现场复核）"
        if route.estimated_walk_seconds is not None
        else "待补录"
    )
)
print("时间依据：" + "、".join(sorted(set(route.walk_time_basis))))
unreachable = unreachable_guide_stops()
print("不可达讲解点：" + ("、".join(unreachable) if unreachable else "无"))
