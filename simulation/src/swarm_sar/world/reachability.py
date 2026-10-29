"""Reachability and map cleanup utilities."""

from collections import deque

import numpy as np

from swarm_sar.world.cells import WALL


def bfs_distances(grid: np.ndarray, start: tuple[int, int]) -> np.ndarray:
    """Return 4-neighbour distances from ``(x, y)``, or -1 if unreachable."""
    height, width = grid.shape
    sx, sy = start
    distances = np.full((height, width), -1, dtype=np.int32)
    if not (0 <= sx < width and 0 <= sy < height) or grid[sy, sx] == WALL:
        return distances

    distances[sy, sx] = 0
    queue: deque[tuple[int, int]] = deque([(sx, sy)])
    while queue:
        x, y = queue.popleft()
        next_distance = distances[y, x] + 1
        for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if (
                0 <= nx < width
                and 0 <= ny < height
                and distances[ny, nx] < 0
                and grid[ny, nx] != WALL
            ):
                distances[ny, nx] = next_distance
                queue.append((nx, ny))
    return distances


def close_unreachable(
    grid: np.ndarray, start: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray]:
    """Turn unreachable traversable cells into walls and return distances."""
    cleaned = grid.copy()
    distances = bfs_distances(cleaned, start)
    cleaned[(cleaned != WALL) & (distances < 0)] = WALL
    return cleaned, bfs_distances(cleaned, start)
