"""Verified-map graph helpers for Chen Clan Academy route planning.

This module deliberately plans only over the human-reviewed node/edge CSVs.  It
does not infer passages from image distance or claim indoor positioning.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SPATIAL_DIR = Path("data/chen_clan_academy/spatial")
NODES_FILE = SPATIAL_DIR / "marker_inventory_v0.csv"
EDGES_FILE = SPATIAL_DIR / "edges_v0.csv"


@dataclass(frozen=True)
class SpatialRoute:
    """A route expressed as reviewed node IDs and human-facing names."""

    node_ids: tuple[str, ...]
    names: tuple[str, ...]
    edge_ids: tuple[str, ...]
    estimated_walk_seconds: int | None
    walk_time_basis: tuple[str, ...]


class SpatialGraphError(ValueError):
    """Raised when spatial source data is invalid or a requested route is absent."""


def _dependencies():
    try:
        import networkx as nx
    except ImportError as exc:
        raise RuntimeError(
            "缺少空间路线依赖。请在虚拟环境运行：pip install -r requirements.txt"
        ) from exc
    return nx


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SpatialGraphError(f"空间数据文件不存在：{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_spatial_graph(
    nodes_file: Path = NODES_FILE, edges_file: Path = EDGES_FILE
) -> Any:
    """Build an undirected NetworkX graph from reviewed bidirectional edges.

    Edges with blank walking time receive a neutral cost of one hop.  Time
    estimates are explicitly labelled in the CSV and are never presented as
    on-site measurements.
    """
    nx = _dependencies()
    graph = nx.Graph()
    nodes = _read_csv(nodes_file)
    edges = _read_csv(edges_file)
    for node in nodes:
        node_id = node["node_id"].strip()
        if not node_id:
            raise SpatialGraphError(f"节点缺少 node_id：{node}")
        graph.add_node(node_id, **node)
    for edge in edges:
        edge_id = edge["edge_id"].strip()
        start = edge["from_node_id"].strip()
        end = edge["to_node_id"].strip()
        if start not in graph or end not in graph:
            raise SpatialGraphError(f"边 {edge_id} 引用了不存在的节点：{start} → {end}")
        if edge["direction"].strip() != "both":
            raise SpatialGraphError(f"当前 v0 仅接受双向边：{edge_id}")
        raw_seconds = edge["walk_seconds"].strip()
        seconds = int(raw_seconds) if raw_seconds else None
        edge_attributes = dict(edge)
        edge_attributes.update(
            edge_id=edge_id,
            walk_seconds=seconds,
            route_cost=seconds if seconds is not None else 1,
        )
        graph.add_edge(start, end, **edge_attributes)
    return graph


def shortest_route(
    source_id: str, target_id: str, graph: Any | None = None
) -> SpatialRoute:
    """Return the least-cost reviewed route with its recorded time basis."""
    nx = _dependencies()
    graph = graph or build_spatial_graph()
    if source_id not in graph:
        raise SpatialGraphError(f"未知起点：{source_id}")
    if target_id not in graph:
        raise SpatialGraphError(f"未知终点：{target_id}")
    try:
        node_ids = nx.shortest_path(graph, source_id, target_id, weight="route_cost")
    except nx.NetworkXNoPath as exc:
        raise SpatialGraphError(f"不存在可用路径：{source_id} → {target_id}") from exc
    edge_data = [graph.get_edge_data(start, end) for start, end in zip(node_ids, node_ids[1:])]
    raw_times = [item["walk_seconds"] for item in edge_data]
    return SpatialRoute(
        node_ids=tuple(node_ids),
        names=tuple(graph.nodes[node_id]["name"] for node_id in node_ids),
        edge_ids=tuple(item["edge_id"] for item in edge_data),
        estimated_walk_seconds=(
            sum(raw_times) if all(value is not None for value in raw_times) else None
        ),
        walk_time_basis=tuple(item.get("time_basis", "unknown") for item in edge_data),
    )


def unreachable_guide_stops(
    source_id: str = "entrance_main_outside", graph: Any | None = None
) -> list[str]:
    """Return guide-stop IDs not connected to the main entrance."""
    nx = _dependencies()
    graph = graph or build_spatial_graph()
    if source_id not in graph:
        raise SpatialGraphError(f"未知起点：{source_id}")
    reachable = nx.node_connected_component(graph, source_id)
    return sorted(
        node_id
        for node_id, data in graph.nodes(data=True)
        if data.get("node_type") == "guide_stop" and node_id not in reachable
    )
