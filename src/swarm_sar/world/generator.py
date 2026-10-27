"""Seeded cave and optional maze generation."""

from typing import Any

import numpy as np

from swarm_sar.world.cells import FREE, RUBBLE, WALL
from swarm_sar.world.reachability import close_unreachable


def spawn_center(config: dict[str, Any]) -> tuple[int, int]:
    x, y = map(int, config["spawn_origin"])
    size = int(config["spawn_size"])
    return x + size // 2, y + size // 2


def _spawn_mask(config: dict[str, Any]) -> np.ndarray:
    height, width = int(config["height"]), int(config["width"])
    mask = np.zeros((height, width), dtype=bool)
    x, y = map(int, config["spawn_origin"])
    size = int(config["spawn_size"])
    if x < 0 or y < 0 or x + size > width or y + size > height:
        raise ValueError("Spawn square lies outside the map")
    mask[y : y + size, x : x + size] = True
    return mask


def _smooth(grid: np.ndarray) -> np.ndarray:
    padded = np.pad(grid == WALL, 1, constant_values=True)
    neighbours = np.zeros(grid.shape, dtype=np.uint8)
    for dy in range(3):
        for dx in range(3):
            if dx == 1 and dy == 1:
                continue
            neighbours += padded[dy : dy + grid.shape[0], dx : dx + grid.shape[1]]
    return np.where(neighbours >= 5, WALL, FREE).astype(np.int8)


def _cave(config: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    height, width = int(config["height"]), int(config["width"])
    grid = np.where(rng.random((height, width)) < float(config["wall_fill"]), WALL, FREE)
    grid = grid.astype(np.int8)
    for _ in range(int(config["smoothing_steps"])):
        grid = _smooth(grid)
    return grid


def _maze(config: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    """Generate a recursive-backtracker maze with a few loops."""
    height, width = int(config["height"]), int(config["width"])
    grid = np.full((height, width), WALL, dtype=np.int8)
    start = (1, 1)
    grid[start[1], start[0]] = FREE
    stack = [start]
    while stack:
        x, y = stack[-1]
        choices = []
        for dx, dy in ((0, -2), (2, 0), (0, 2), (-2, 0)):
            nx, ny = x + dx, y + dy
            if 1 <= nx < width - 1 and 1 <= ny < height - 1 and grid[ny, nx] == WALL:
                choices.append((nx, ny, x + dx // 2, y + dy // 2))
        if choices:
            nx, ny, wx, wy = choices[int(rng.integers(len(choices)))]
            grid[wy, wx] = grid[ny, nx] = FREE
            stack.append((nx, ny))
        else:
            stack.pop()
    interior_walls = np.argwhere(grid[1:-1, 1:-1] == WALL) + 1
    if len(interior_walls):
        count = max(1, int(len(interior_walls) * 0.05))
        for y, x in interior_walls[rng.choice(len(interior_walls), count, replace=False)]:
            grid[y, x] = FREE
    return grid


def _carve_corridor(
    grid: np.ndarray,
    start: tuple[int, int],
    end: tuple[int, int],
    horizontal_first: bool,
) -> None:
    """Carve an L-shaped one-cell corridor between two room centers."""
    x0, y0 = start
    x1, y1 = end
    if horizontal_first:
        grid[y0, min(x0, x1) : max(x0, x1) + 1] = FREE
        grid[min(y0, y1) : max(y0, y1) + 1, x1] = FREE
    else:
        grid[min(y0, y1) : max(y0, y1) + 1, x0] = FREE
        grid[y1, min(x0, x1) : max(x0, x1) + 1] = FREE


def _rooms(config: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    """Generate irregular rooms joined by corridors and a few alternate routes."""
    height, width = int(config["height"]), int(config["width"])
    grid = np.full((height, width), WALL, dtype=np.int8)
    room_low, room_high = map(int, config.get("num_rooms", [8, 12]))
    size_low, size_high = map(int, config.get("room_size", [3, 7]))
    target_count = int(rng.integers(room_low, room_high + 1))
    sx, sy = map(int, config["spawn_origin"])
    spawn_size = int(config["spawn_size"])
    grid[sy : sy + spawn_size, sx : sx + spawn_size] = FREE
    centers: list[tuple[int, int]] = [(sx + spawn_size // 2, sy + spawn_size // 2)]
    rectangles: list[tuple[int, int, int, int]] = [
        (sx, sy, sx + spawn_size - 1, sy + spawn_size - 1)
    ]

    for _ in range(target_count * 30):
        if len(centers) >= target_count + 1:
            break
        room_width = int(rng.integers(size_low, min(size_high, width - 3) + 1))
        room_height = int(rng.integers(size_low, min(size_high, height - 3) + 1))
        x = int(rng.integers(1, width - room_width))
        y = int(rng.integers(1, height - room_height))
        rectangle = (x, y, x + room_width - 1, y + room_height - 1)
        overlaps = any(
            not (
                rectangle[2] < old[0]
                or rectangle[0] > old[2]
                or rectangle[3] < old[1]
                or rectangle[1] > old[3]
            )
            for old in rectangles
        )
        if overlaps:
            continue
        center = (x + room_width // 2, y + room_height // 2)
        nearest = min(
            centers,
            key=lambda point: abs(point[0] - center[0]) + abs(point[1] - center[1]),
        )
        grid[y : y + room_height, x : x + room_width] = FREE
        _carve_corridor(grid, nearest, center, bool(rng.integers(2)))
        centers.append(center)
        rectangles.append(rectangle)

    # Extra connections make alternate paths and reduce single-corridor bottlenecks.
    if len(centers) >= 4:
        for _ in range(max(1, len(centers) // 4)):
            first, second = rng.choice(len(centers), 2, replace=False)
            _carve_corridor(
                grid,
                centers[int(first)],
                centers[int(second)],
                bool(rng.integers(2)),
            )
    return grid


def _force_border(grid: np.ndarray) -> None:
    grid[0, :] = WALL
    grid[-1, :] = WALL
    grid[:, 0] = WALL
    grid[:, -1] = WALL


def _add_rubble(
    grid: np.ndarray,
    config: dict[str, Any],
    rng: np.random.Generator,
    spawn_mask: np.ndarray,
) -> None:
    low, high = map(int, config["rubble_patch_radius"])
    for _ in range(int(config["rubble_patches"])):
        candidates = np.argwhere((grid == FREE) & ~spawn_mask)
        if len(candidates) == 0:
            return
        cy, cx = candidates[int(rng.integers(len(candidates)))]
        radius = int(rng.integers(low, high + 1))
        y0, y1 = max(0, cy - radius), min(grid.shape[0], cy + radius + 1)
        x0, x1 = max(0, cx - radius), min(grid.shape[1], cx + radius + 1)
        yy, xx = np.ogrid[y0:y1, x0:x1]
        disk = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius**2
        region = grid[y0:y1, x0:x1]
        allowed = disk & (region == FREE) & ~spawn_mask[y0:y1, x0:x1]
        region[allowed] = RUBBLE


def generate_candidate(
    config: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray, float]:
    """Generate and clean one candidate, including rubble."""
    layout = str(config.get("layout", "cave")).lower()
    if layout == "cave":
        grid = _cave(config, rng)
    elif layout == "maze":
        grid = _maze(config, rng)
    elif layout == "rooms":
        grid = _rooms(config, rng)
    else:
        raise ValueError(f"Unknown layout: {layout}")

    spawn_mask = _spawn_mask(config)
    if bool(config.get("border_walls", True)):
        _force_border(grid)
    grid[spawn_mask] = FREE
    if bool(config.get("border_walls", True)):
        _force_border(grid)
    _add_rubble(grid, config, rng, spawn_mask)
    grid, distances = close_unreachable(grid, spawn_center(config))
    reachable_ratio = float(np.count_nonzero(distances >= 0) / grid.size)
    return grid, distances, reachable_ratio


def generate_world(
    config: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a valid world, retrying closed maps deterministically."""
    retries = int(config["max_generation_retries"])
    minimum = float(config["min_free_ratio"])
    for _ in range(retries):
        grid, distances, ratio = generate_candidate(config, rng)
        if ratio >= minimum:
            return grid, distances
    raise RuntimeError(
        f"Could not generate a map with reachable ratio >= {minimum} in {retries} attempts"
    )


generate_map = generate_world
