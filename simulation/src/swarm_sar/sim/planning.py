"""Frontier extraction and local-map A* path planning."""

from collections import deque
from heapq import heappop, heappush
from typing import Any

import numpy as np

from swarm_sar.world.cells import FREE, RUBBLE, UNKNOWN


def _neighbours(x: int, y: int, width: int, height: int):
    for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
        if 0 <= nx < width and 0 <= ny < height:
            yield nx, ny


def frontier_clusters(belief: np.ndarray) -> list[list[tuple[int, int]]]:
    """Return connected known-free boundaries adjacent to unknown cells."""
    height, width = belief.shape
    traversable = (belief == FREE) | (belief == RUBBLE)
    frontier = np.zeros_like(traversable)
    for y, x in np.argwhere(traversable):
        frontier[y, x] = any(
            belief[ny, nx] == UNKNOWN for nx, ny in _neighbours(int(x), int(y), width, height)
        )

    seen = np.zeros_like(frontier)
    clusters: list[list[tuple[int, int]]] = []
    for y, x in np.argwhere(frontier):
        if seen[y, x]:
            continue
        cluster: list[tuple[int, int]] = []
        queue = deque([(int(x), int(y))])
        seen[y, x] = True
        while queue:
            cx, cy = queue.popleft()
            cluster.append((cx, cy))
            for nx, ny in _neighbours(cx, cy, width, height):
                if frontier[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    queue.append((nx, ny))
        clusters.append(cluster)
    return clusters


def astar_path(
    belief: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
    *,
    can_cross_rubble: bool = True,
) -> list[tuple[int, int]]:
    """Plan only through locally known traversable cells; return [] if unreachable."""
    height, width = belief.shape
    passable = belief == FREE
    if can_cross_rubble:
        passable |= belief == RUBBLE
    sx, sy = start
    gx, gy = goal
    if not (
        0 <= sx < width
        and 0 <= sy < height
        and 0 <= gx < width
        and 0 <= gy < height
        and passable[sy, sx]
        and passable[gy, gx]
    ):
        return []

    frontier: list[tuple[int, int, int, int]] = []
    heappush(frontier, (abs(gx - sx) + abs(gy - sy), 0, sx, sy))
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {(sx, sy): None}
    costs = {(sx, sy): 0}
    while frontier:
        _, cost, x, y = heappop(frontier)
        if (x, y) == goal:
            path: list[tuple[int, int]] = []
            cursor: tuple[int, int] | None = goal
            while cursor is not None:
                path.append(cursor)
                cursor = came_from[cursor]
            return list(reversed(path))
        if cost != costs[(x, y)]:
            continue
        for nx, ny in _neighbours(x, y, width, height):
            if not passable[ny, nx]:
                continue
            step_cost = 2 if belief[ny, nx] == RUBBLE else 1
            next_cost = cost + step_cost
            if next_cost < costs.get((nx, ny), 10**9):
                costs[(nx, ny)] = next_cost
                came_from[(nx, ny)] = (x, y)
                priority = next_cost + abs(gx - nx) + abs(gy - ny)
                heappush(frontier, (priority, next_cost, nx, ny))
    return []


def frontier_candidates(
    belief: np.ndarray,
    start: tuple[int, int],
    *,
    max_candidates: int = 5,
    max_per_cluster: int = 1,
    can_cross_rubble: bool = True,
) -> list[dict[str, Any]]:
    """Return up to N reachable representative frontiers, nearest first."""
    candidates: list[dict[str, Any]] = []
    clusters = frontier_clusters(belief)
    if max_per_cluster <= 1:
        # Preserve the frozen Step 2 controller exactly on its small worlds.
        for cluster in clusters:
            center_x = sum(point[0] for point in cluster) / len(cluster)
            center_y = sum(point[1] for point in cluster) / len(cluster)
            representative = min(
                cluster,
                key=lambda point: (
                    (point[0] - center_x) ** 2 + (point[1] - center_y) ** 2
                ),
            )
            path = astar_path(
                belief,
                start,
                representative,
                can_cross_rubble=can_cross_rubble,
            )
            if path:
                candidates.append(
                    {
                        "position": representative,
                        "cluster_size": len(cluster),
                        "path": path,
                        "distance": max(0, len(path) - 1),
                    }
                )
        candidates.sort(
            key=lambda item: (
                -item["cluster_size"], item["distance"], item["position"]
            )
        )
        return candidates[:max_candidates]

    height, width = belief.shape
    passable = belief == FREE
    if can_cross_rubble:
        passable |= belief == RUBBLE
    if not (
        0 <= start[0] < width
        and 0 <= start[1] < height
        and passable[start[1], start[0]]
    ):
        return []

    # One deterministic Dijkstra pass supplies paths to every sampled frontier.
    # This avoids repeating a whole-grid A* search for each action slot.
    search: list[tuple[int, int, int]] = [(0, start[0], start[1])]
    costs: dict[tuple[int, int], int] = {start: 0}
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    while search:
        cost, x, y = heappop(search)
        if cost != costs[(x, y)]:
            continue
        for nx, ny in _neighbours(x, y, width, height):
            if not passable[ny, nx]:
                continue
            next_cost = cost + (2 if belief[ny, nx] == RUBBLE else 1)
            point = (nx, ny)
            if next_cost < costs.get(point, 1 << 60):
                costs[point] = next_cost
                came_from[point] = (x, y)
                heappush(search, (next_cost, nx, ny))

    candidates_by_cluster: list[list[dict[str, Any]]] = []
    for cluster in clusters:
        # A long room boundary is one connected component but should offer several
        # directions so multiple agents can disperse. Deterministic farthest-point
        # sampling preserves the fixed five-slot interface.
        representative_count = min(
            max_candidates,
            max(1, int(max_per_cluster)),
            max(1, (len(cluster) + 7) // 8),
        )
        representatives = [
            min(
                cluster,
                key=lambda point: (
                    abs(point[0] - start[0]) + abs(point[1] - start[1]),
                    point,
                ),
            )
        ]
        while len(representatives) < representative_count:
            remaining = [point for point in cluster if point not in representatives]
            if not remaining:
                break
            representatives.append(
                max(
                    remaining,
                    key=lambda point: (
                        min(
                            (point[0] - chosen[0]) ** 2 + (point[1] - chosen[1]) ** 2
                            for chosen in representatives
                        ),
                        -point[1],
                        -point[0],
                    ),
                )
            )
        cluster_candidates: list[dict[str, Any]] = []
        for representative in representatives:
            if representative in came_from:
                path: list[tuple[int, int]] = []
                cursor: tuple[int, int] | None = representative
                while cursor is not None:
                    path.append(cursor)
                    cursor = came_from[cursor]
                path.reverse()
                cluster_candidates.append(
                    {
                        "position": representative,
                        "cluster_size": len(cluster),
                        "path": path,
                        "distance": max(0, len(path) - 1),
                    }
                )
        cluster_candidates.sort(key=lambda item: (item["distance"], item["position"]))
        if cluster_candidates:
            candidates_by_cluster.append(cluster_candidates)

    # Do not let several samples from one large room consume every action slot.
    # Round-robin across disconnected frontier clusters first, then expose extra
    # directions within each cluster. This is especially important for narrow
    # side branches in non-convex disaster sites.
    candidates_by_cluster.sort(
        key=lambda group: (
            -group[0]["cluster_size"],
            group[0]["distance"],
            group[0]["position"],
        )
    )
    # Surface distinct branches before adding extra directions from a large
    # boundary. The decentralized controller assigns these branches to peers by
    # rendezvous hashing, so this diversity does not imply a central scheduler.
    selected = [group[0] for group in candidates_by_cluster[:max_candidates]]
    if len(selected) < max_candidates:
        selected_ids = {id(candidate) for candidate in selected}
        extras = [
            candidate
            for group in candidates_by_cluster
            for candidate in group[1:]
            if id(candidate) not in selected_ids
        ]
        extras.sort(
            key=lambda item: (
                -item["cluster_size"], item["distance"], item["position"]
            )
        )
        selected.extend(extras[: max_candidates - len(selected)])
    return selected


def movement_action(start: tuple[int, int], next_cell: tuple[int, int]) -> int:
    delta = (next_cell[0] - start[0], next_cell[1] - start[1])
    return {(0, 0): 0, (0, -1): 1, (0, 1): 2, (-1, 0): 3, (1, 0): 4}[delta]
