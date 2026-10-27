"""Compress a private occupancy belief into a persistent topological graph."""

import json
from collections import deque
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np

from swarm_sar.sim.planning import astar_path
from swarm_sar.world.cells import FREE, RUBBLE


def _neighbours(x: int, y: int, width: int, height: int):
    for nx_, ny_ in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
        if 0 <= nx_ < width and 0 <= ny_ < height:
            yield nx_, ny_


def _mask_clusters(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    clusters: list[list[tuple[int, int]]] = []
    for y, x in np.argwhere(mask):
        if seen[y, x]:
            continue
        seen[y, x] = True
        queue = deque([(int(x), int(y))])
        cluster: list[tuple[int, int]] = []
        while queue:
            cx, cy = queue.popleft()
            cluster.append((cx, cy))
            for nx_, ny_ in _neighbours(cx, cy, width, height):
                if mask[ny_, nx_] and not seen[ny_, nx_]:
                    seen[ny_, nx_] = True
                    queue.append((nx_, ny_))
        clusters.append(cluster)
    return clusters


class AgentTopologicalMap:
    """A graph derived solely from one agent's private occupancy belief."""

    def __init__(self, owner: str) -> None:
        self.owner = owner
        self.graph = nx.Graph(owner=owner)
        self._serial = 0

    def _new_node_id(self, kind: str) -> str:
        self._serial += 1
        return f"{self.owner}:{kind}:{self._serial}"

    def _upsert_spatial_node(
        self,
        kind: str,
        position: tuple[int, int],
        step: int,
        confidence: float,
        *,
        match_radius: int = 2,
        **attributes: Any,
    ) -> str:
        for node_id, data in self.graph.nodes(data=True):
            if data.get("kind") != kind:
                continue
            old_x, old_y = data["position"]
            if abs(old_x - position[0]) + abs(old_y - position[1]) <= match_radius:
                data.update(
                    position=position,
                    confidence=float(confidence),
                    last_update=int(step),
                    **attributes,
                )
                return str(node_id)
        node_id = self._new_node_id(kind)
        self.graph.add_node(
            node_id,
            kind=kind,
            position=position,
            confidence=float(confidence),
            last_update=int(step),
            **attributes,
        )
        return node_id

    def _connect_nodes(
        self,
        belief: np.ndarray,
        node_ids: list[str],
        step: int,
        confidence: float,
        can_cross_rubble: bool,
    ) -> None:
        all_nodes = list(self.graph.nodes)
        for node_id in node_ids:
            if node_id not in self.graph:
                continue
            x, y = self.graph.nodes[node_id]["position"]
            neighbours = sorted(
                (
                    (
                        abs(x - self.graph.nodes[other]["position"][0])
                        + abs(y - self.graph.nodes[other]["position"][1]),
                        other,
                    )
                    for other in all_nodes
                    if other != node_id
                ),
                key=lambda item: item[0],
            )[:3]
            for _, other in neighbours:
                target = tuple(self.graph.nodes[other]["position"])
                path = astar_path(
                    belief,
                    (x, y),
                    target,
                    can_cross_rubble=can_cross_rubble,
                )
                if not path:
                    continue
                rubble = sum(belief[py, px] == RUBBLE for px, py in path)
                self.graph.add_edge(
                    node_id,
                    other,
                    estimated_distance=len(path) - 1,
                    traversability="rubble" if rubble else "clear",
                    observation_confidence=float(confidence),
                    last_update=int(step),
                )

    def update(
        self,
        belief: np.ndarray,
        frontier_candidates: list[dict[str, Any]],
        step: int,
        pose_uncertainty: float,
        *,
        can_cross_rubble: bool,
    ) -> None:
        confidence = 1.0 / (1.0 + max(0.0, float(pose_uncertainty)))
        traversable = (belief == FREE) | (belief == RUBBLE)
        height, width = belief.shape
        degree = np.zeros_like(belief, dtype=np.uint8)
        for y, x in np.argwhere(traversable):
            degree[y, x] = sum(
                traversable[ny, nx]
                for nx, ny in _neighbours(int(x), int(y), width, height)
            )

        updated: list[str] = []
        for cluster in _mask_clusters(traversable & (degree >= 3)):
            center_x = sum(point[0] for point in cluster) / len(cluster)
            center_y = sum(point[1] for point in cluster) / len(cluster)
            position = min(
                cluster,
                key=lambda point: (point[0] - center_x) ** 2 + (point[1] - center_y) ** 2,
            )
            kind = "room" if len(cluster) >= 6 else "junction"
            updated.append(
                self._upsert_spatial_node(
                    kind,
                    position,
                    step,
                    confidence,
                    cell_count=len(cluster),
                )
            )

        stale_frontiers = [
            node_id
            for node_id, data in self.graph.nodes(data=True)
            if data.get("kind") == "frontier"
        ]
        self.graph.remove_nodes_from(stale_frontiers)
        for candidate in frontier_candidates:
            position = tuple(candidate["position"])
            updated.append(
                self._upsert_spatial_node(
                    "frontier",
                    position,
                    step,
                    confidence,
                    match_radius=0,
                    cluster_size=int(candidate["cluster_size"]),
                    estimated_distance=int(candidate["distance"]),
                )
            )
        self._connect_nodes(belief, updated, step, confidence, can_cross_rubble)
        for node_id, data in list(self.graph.nodes(data=True)):
            if str(data.get("kind", "")).startswith("survivor_") and self.graph.degree(node_id) == 0:
                self._connect_marker(
                    str(node_id),
                    step,
                    float(data.get("confidence", confidence)),
                )

    def add_suspected_survivor(
        self, position: tuple[int, int], confidence: float, step: int
    ) -> str:
        node_id = self._upsert_spatial_node(
            "survivor_suspected",
            position,
            step,
            confidence,
            match_radius=3,
        )
        self._connect_marker(node_id, step, confidence)
        return node_id

    def mark_survivor_confirmed(
        self, position: tuple[int, int], confidence: float, step: int
    ) -> str:
        nearby_suspects = [
            node_id
            for node_id, data in self.graph.nodes(data=True)
            if data.get("kind") == "survivor_suspected"
            and abs(data["position"][0] - position[0])
            + abs(data["position"][1] - position[1])
            <= 4
        ]
        self.graph.remove_nodes_from(nearby_suspects)
        node_id = self._upsert_spatial_node(
            "survivor_confirmed",
            position,
            step,
            confidence,
            match_radius=3,
        )
        self._connect_marker(node_id, step, confidence)
        return node_id

    def _connect_marker(self, node_id: str, step: int, confidence: float) -> None:
        if node_id not in self.graph:
            return
        x, y = self.graph.nodes[node_id]["position"]
        candidates = [
            other
            for other, data in self.graph.nodes(data=True)
            if other != node_id and not str(data.get("kind", "")).startswith("survivor_")
        ]
        if not candidates:
            return
        nearest = min(
            candidates,
            key=lambda other: abs(x - self.graph.nodes[other]["position"][0])
            + abs(y - self.graph.nodes[other]["position"][1]),
        )
        nx_, ny_ = self.graph.nodes[nearest]["position"]
        self.graph.add_edge(
            node_id,
            nearest,
            estimated_distance=abs(x - nx_) + abs(y - ny_),
            traversability="estimated",
            observation_confidence=float(confidence),
            last_update=int(step),
        )

    def node_kind_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _, data in self.graph.nodes(data=True):
            kind = str(data["kind"])
            counts[kind] = counts.get(kind, 0) + 1
        return counts

    def shortest_topological_path(self, source: str, target: str) -> list[str]:
        """Use edge distance estimates for graph-level route selection."""
        return nx.shortest_path(
            self.graph,
            source=source,
            target=target,
            weight="estimated_distance",
        )

    def save_json(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = nx.node_link_data(self.graph, edges="edges")
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output
