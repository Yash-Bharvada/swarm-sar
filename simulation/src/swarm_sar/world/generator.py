"""Seeded cave and optional maze generation."""

from collections import deque
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


def _paint_ellipse(
    mask: np.ndarray,
    center: tuple[int, int],
    radii: tuple[int, int],
) -> None:
    """Paint a clipped ellipse into a boolean mask."""
    height, width = mask.shape
    cx, cy = center
    rx, ry = radii
    x0, x1 = max(1, cx - rx), min(width - 1, cx + rx + 1)
    y0, y1 = max(1, cy - ry), min(height - 1, cy + ry + 1)
    yy, xx = np.ogrid[y0:y1, x0:x1]
    mask[y0:y1, x0:x1] |= (
        ((xx - cx) / max(1, rx)) ** 2 + ((yy - cy) / max(1, ry)) ** 2 <= 1.0
    )


def _paint_segment(
    mask: np.ndarray,
    start: tuple[int, int],
    end: tuple[int, int],
    radius: int,
) -> None:
    """Paint a thick line, ensuring two random footprint lobes stay connected."""
    x0, y0 = start
    x1, y1 = end
    count = max(abs(x1 - x0), abs(y1 - y0), 1)
    for index in range(count + 1):
        fraction = index / count
        x = int(round(x0 + fraction * (x1 - x0)))
        y = int(round(y0 + fraction * (y1 - y0)))
        _paint_ellipse(mask, (x, y), (radius, radius))


def _procedural_footprint(
    config: dict[str, Any], rng: np.random.Generator
) -> np.ndarray:
    """Create a connected organic site envelope with no fixed named shape."""
    height, width = int(config["height"]), int(config["width"])
    mask = np.zeros((height, width), dtype=bool)
    spawn = spawn_center(config)
    centers = [spawn]
    area = width * height
    lobe_count = int(np.clip(area // 650, 7, 24))
    min_rx, max_rx = max(4, width // 22), max(7, width // 11)
    min_ry, max_ry = max(4, height // 22), max(7, height // 11)
    _paint_ellipse(mask, spawn, (max(5, min_rx), max(5, min_ry)))

    # Every random lobe is connected to the nearest existing one through a
    # randomly oriented elbow. The union is irregular but connected by design.
    for _ in range(lobe_count):
        center = (
            int(rng.integers(2, max(3, width - 2))),
            int(rng.integers(2, max(3, height - 2))),
        )
        nearest = min(
            centers,
            key=lambda old: (old[0] - center[0]) ** 2 + (old[1] - center[1]) ** 2,
        )
        radii = (
            int(rng.integers(min_rx, max_rx + 1)),
            int(rng.integers(min_ry, max_ry + 1)),
        )
        _paint_ellipse(mask, center, radii)
        corridor_radius = int(rng.integers(2, 5))
        elbow = (
            (center[0], nearest[1])
            if bool(rng.integers(2))
            else (nearest[0], center[1])
        )
        _paint_segment(mask, nearest, elbow, corridor_radius)
        _paint_segment(mask, elbow, center, corridor_radius)
        centers.append(center)
    return mask


def build_footprint_mask(
    config: dict[str, Any], rng: np.random.Generator | None = None
) -> np.ndarray:
    """Return the traversable site envelope inside the rectangular storage grid."""
    height, width = int(config["height"]), int(config["width"])
    footprint = str(config.get("footprint", "full")).lower()
    mask = np.zeros((height, width), dtype=bool)
    if height < 8 or width < 8:
        raise ValueError("World dimensions must both be at least 8 cells")
    interior = np.zeros_like(mask)
    interior[1:-1, 1:-1] = True

    if footprint == "full":
        mask = interior
    elif footprint == "l_shape":
        vertical_width = max(6, int(width * 0.42))
        horizontal_height = max(6, int(height * 0.32))
        mask[1:-1, 1:vertical_width] = True
        mask[1:horizontal_height, 1:-1] = True
    elif footprint == "t_shape":
        top_height = max(6, int(height * 0.30))
        stem_width = max(6, int(width * 0.24))
        center = width // 2
        left = max(1, center - stem_width // 2)
        right = min(width - 1, left + stem_width)
        mask[1:top_height, 1:-1] = True
        mask[1:-1, left:right] = True
    elif footprint == "multi_structure":
        # Three structures linked by narrow enclosed passages.
        blocks = [
            (1, 1, max(7, width // 3), max(7, height // 3)),
            (max(3, width // 3), max(3, height // 4), max(8, 2 * width // 3), max(8, 2 * height // 3)),
            (max(5, 2 * width // 3), max(5, height // 2), width - 1, height - 1),
        ]
        centers = []
        for x0, y0, x1, y1 in blocks:
            mask[y0:y1, x0:x1] = True
            centers.append(((x0 + x1) // 2, (y0 + y1) // 2))
        corridor_width = 3
        for (x0, y0), (x1, y1) in zip(centers, centers[1:]):
            mask[max(1, y0 - 1) : min(height - 1, y0 + corridor_width - 1), min(x0, x1) : max(x0, x1) + 1] = True
            mask[min(y0, y1) : max(y0, y1) + 1, max(1, x1 - 1) : min(width - 1, x1 + corridor_width - 1)] = True
    elif footprint == "tunnel":
        band = max(5, min(9, height // 6))
        spacing = max(band + 3, height // 4)
        rows = list(range(2, height - 2, spacing))
        if not rows:
            rows = [2]
        for index, y in enumerate(rows):
            y1 = min(height - 1, y + band)
            mask[y:y1, 1:-1] = True
            if index + 1 < len(rows):
                next_y = rows[index + 1]
                x = width - 4 if index % 2 == 0 else 2
                mask[y : min(height - 1, next_y + band), x : x + 3] = True
    elif footprint == "collapsed":
        mask = interior.copy()
        holes = [
            (width // 4, height // 3, width // 2, height // 2),
            (3 * width // 5, height // 5, 4 * width // 5, 2 * height // 5),
            (width // 2, 2 * height // 3, 3 * width // 4, 5 * height // 6),
        ]
        for x0, y0, x1, y1 in holes:
            mask[max(2, y0) : min(height - 2, y1), max(2, x0) : min(width - 2, x1)] = False
    elif footprint == "procedural":
        if rng is None:
            raise ValueError("The procedural footprint requires a seeded RNG")
        mask = _procedural_footprint(config, rng)
    else:
        raise ValueError(f"Unknown footprint: {footprint}")

    spawn = _spawn_mask(config)
    mask |= spawn
    mask[0, :] = mask[-1, :] = False
    mask[:, 0] = mask[:, -1] = False
    return mask


def _masked_path(
    allowed: np.ndarray, start: tuple[int, int], end: tuple[int, int]
) -> list[tuple[int, int]]:
    """Find a shortest corridor route that remains inside an irregular footprint."""
    height, width = allowed.shape
    queue = deque([start])
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    while queue:
        x, y = queue.popleft()
        if (x, y) == end:
            path = []
            cursor: tuple[int, int] | None = end
            while cursor is not None:
                path.append(cursor)
                cursor = came_from[cursor]
            return list(reversed(path))
        for nx, ny in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
            point = (nx, ny)
            if (
                0 <= nx < width
                and 0 <= ny < height
                and allowed[ny, nx]
                and point not in came_from
            ):
                came_from[point] = (x, y)
                queue.append(point)
    return []


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


def _rooms(
    config: dict[str, Any],
    rng: np.random.Generator,
    footprint_mask: np.ndarray,
) -> np.ndarray:
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
        if not np.all(footprint_mask[y : y + room_height, x : x + room_width]):
            continue
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
        if str(config.get("footprint", "full")).lower() == "full":
            _carve_corridor(grid, nearest, center, bool(rng.integers(2)))
        else:
            path = _masked_path(footprint_mask, nearest, center)
            for px, py in path:
                grid[py, px] = FREE
        centers.append(center)
        rectangles.append(rectangle)

    # Extra connections make alternate paths and reduce single-corridor bottlenecks.
    if len(centers) >= 4:
        for _ in range(max(1, len(centers) // 4)):
            first, second = rng.choice(len(centers), 2, replace=False)
            if str(config.get("footprint", "full")).lower() == "full":
                _carve_corridor(
                    grid,
                    centers[int(first)],
                    centers[int(second)],
                    bool(rng.integers(2)),
                )
            else:
                path = _masked_path(
                    footprint_mask, centers[int(first)], centers[int(second)]
                )
                for px, py in path:
                    grid[py, px] = FREE
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
    footprint_mask = build_footprint_mask(config, rng)
    if layout == "cave":
        grid = _cave(config, rng)
    elif layout == "maze":
        grid = _maze(config, rng)
    elif layout == "rooms":
        grid = _rooms(config, rng, footprint_mask)
    else:
        raise ValueError(f"Unknown layout: {layout}")

    grid[~footprint_mask] = WALL
    spawn_mask = _spawn_mask(config)
    if bool(config.get("border_walls", True)):
        _force_border(grid)
    grid[spawn_mask] = FREE
    if bool(config.get("border_walls", True)):
        _force_border(grid)
    _add_rubble(grid, config, rng, spawn_mask)
    grid, distances = close_unreachable(grid, spawn_center(config))
    reachable_ratio = float(
        np.count_nonzero(distances >= 0) / max(1, np.count_nonzero(footprint_mask))
    )
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
