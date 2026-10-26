"""Line-of-sight vision and fog-of-war updates."""

from functools import lru_cache

import numpy as np

from swarm_sar.robots.robot import Robot
from swarm_sar.world.cells import WALL


def bresenham_line(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    """Return all integer points on a line, including both endpoints."""
    x0, y0 = start
    x1, y1 = end
    points: list[tuple[int, int]] = []
    dx, sx = abs(x1 - x0), 1 if x0 < x1 else -1
    dy, sy = -abs(y1 - y0), 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return points
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


@lru_cache(maxsize=None)
def vision_rays(radius: int) -> tuple[tuple[int, int, tuple[tuple[int, int], ...]], ...]:
    """Precompute disk offsets and strict intermediate line cells."""
    rays = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                line = bresenham_line((0, 0), (dx, dy))
                rays.append((dx, dy, tuple(line[1:-1])))
    return tuple(rays)


def has_line_of_sight(
    grid: np.ndarray, start: tuple[int, int], end: tuple[int, int]
) -> bool:
    """Walls strictly between two cells block sight; the end wall is visible."""
    height, width = grid.shape
    ex, ey = end
    if not (0 <= ex < width and 0 <= ey < height):
        return False
    for x, y in bresenham_line(start, end)[1:-1]:
        if not (0 <= x < width and 0 <= y < height) or grid[y, x] == WALL:
            return False
    return True


def update_vision(robot: Robot, grid: np.ndarray, radius: int) -> int:
    """Reveal visible cells in one robot's private belief map."""
    height, width = grid.shape
    newly_revealed = 0
    for dx, dy, intermediates in vision_rays(int(radius)):
        tx, ty = robot.x + dx, robot.y + dy
        if not (0 <= tx < width and 0 <= ty < height):
            continue
        blocked = False
        for ix, iy in intermediates:
            if grid[robot.y + iy, robot.x + ix] == WALL:
                blocked = True
                break
        if not blocked:
            if robot.belief[ty, tx] < 0:
                newly_revealed += 1
            robot.belief[ty, tx] = grid[ty, tx]
    return newly_revealed


def update_all_vision(robots: list[Robot], grid: np.ndarray, radius: int) -> int:
    return sum(update_vision(robot, grid, radius) for robot in robots if robot.alive)
