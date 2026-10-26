"""Core simulation engine (intentionally independent of pygame)."""

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from swarm_sar.robots.robot import Robot
from swarm_sar.sensing.victim_sensor import confirm_victims, update_robot_sensors
from swarm_sar.sensing.vision import update_all_vision
from swarm_sar.sim.metrics import EpisodeMetrics
from swarm_sar.utils.config import load_config
from swarm_sar.utils.rng import make_rng
from swarm_sar.world.cells import RUBBLE, UNKNOWN, WALL
from swarm_sar.world.generator import generate_world, spawn_center
from swarm_sar.world.victims import place_victims

ACTIONS: dict[int, tuple[int, int]] = {
    0: (0, 0),
    1: (0, -1),
    2: (0, 1),
    3: (-1, 0),
    4: (1, 0),
}


def _normalise_actions(
    robots: list[Robot], actions: Mapping[int, int] | Sequence[int]
) -> dict[int, int]:
    if isinstance(actions, Mapping):
        values = {robot.id: int(actions.get(robot.id, 0)) for robot in robots}
    else:
        if len(actions) != len(robots):
            raise ValueError("Actions must contain one entry per robot")
        values = {robot.id: int(action) for robot, action in zip(robots, actions)}
    invalid = [action for action in values.values() if action not in ACTIONS]
    if invalid:
        raise ValueError(f"Actions must be integers from 0 to 4, got {invalid[0]}")
    return values


def apply_movements(
    robots: list[Robot],
    actions: Mapping[int, int] | Sequence[int],
    grid: np.ndarray,
    robot_config: dict[str, Any],
    rng: np.random.Generator,
) -> None:
    """Apply simultaneous intents in seeded random sequential order."""
    action_by_id = _normalise_actions(robots, actions)
    occupied = {robot.position for robot in robots if robot.alive}
    height, width = grid.shape
    for index in rng.permutation(len(robots)):
        robot = robots[int(index)]
        robot.collided = False
        robot.last_action = action_by_id[robot.id]
        if not robot.alive:
            continue

        dx, dy = ACTIONS[robot.last_action]
        target = (robot.x + dx, robot.y + dy)
        moving = robot.last_action != 0
        blocked = False
        if moving:
            tx, ty = target
            blocked = not (0 <= tx < width and 0 <= ty < height)
            if not blocked and grid[ty, tx] == WALL and not bool(robot_config["can_cross_walls"]):
                blocked = True
            if not blocked and grid[ty, tx] == RUBBLE and not bool(robot_config["can_cross_rubble"]):
                blocked = True
            if not blocked and target in occupied:
                blocked = True

        if blocked:
            robot.collided = True
            cost = float(robot_config["idle_cost"])
        elif not moving:
            cost = float(robot_config["idle_cost"])
        else:
            occupied.remove(robot.position)
            robot.x, robot.y = target
            occupied.add(target)
            robot.visited[robot.y, robot.x] = True
            robot.distance_travelled += 1
            cost = (
                float(robot_config["rubble_cost"])
                if grid[robot.y, robot.x] == RUBBLE
                else float(robot_config["move_cost"])
            )

        robot.battery = max(0.0, robot.battery - cost)
        if robot.battery <= 0.0:
            robot.alive = False
            occupied.discard(robot.position)


class SwarmWorld:
    """Deterministic multi-rover search-and-rescue world."""

    def __init__(
        self,
        world_config: dict[str, Any] | str | Path | None = None,
        robot_config: dict[str, Any] | str | Path | None = None,
        sim_config: dict[str, Any] | str | Path | None = None,
    ) -> None:
        root = Path(__file__).resolve().parents[3]
        self.world_config = self._config(world_config, root / "configs/world.yaml")
        all_robot_config = self._config(robot_config, root / "configs/robots.yaml")
        self.robot_config = all_robot_config.get("rover", all_robot_config)
        self.sim_config = self._config(sim_config, root / "configs/sim.yaml")
        self.rng = make_rng(int(self.sim_config["seed"]))
        self.grid = np.empty((0, 0), dtype=np.int8)
        self.distances = np.empty((0, 0), dtype=np.int32)
        self.victims: list[dict[str, Any]] = []
        self.robots: list[Robot] = []
        self.metrics: EpisodeMetrics | None = None
        self.step_count = 0
        self.done = False
        self.seed = int(self.sim_config["seed"])

    @staticmethod
    def _config(value: dict[str, Any] | str | Path | None, default: Path) -> dict[str, Any]:
        if value is None:
            return load_config(default)
        if isinstance(value, (str, Path)):
            return load_config(value)
        return dict(value)

    def _generate_with_victims(self) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
        retries = int(self.world_config["max_generation_retries"])
        last_error: Exception | None = None
        for _ in range(retries):
            grid, distances = generate_world(self.world_config, self.rng)
            try:
                victims = place_victims(grid, distances, self.world_config, self.rng)
                return grid, distances, victims
            except ValueError as error:
                last_error = error
        raise RuntimeError("Could not generate a map with valid victim placement") from last_error

    def _spawn_robots(self) -> list[Robot]:
        x0, y0 = map(int, self.world_config["spawn_origin"])
        size = int(self.world_config["spawn_size"])
        cells = [
            (x, y)
            for y in range(y0, y0 + size)
            for x in range(x0, x0 + size)
            if self.grid[y, x] != WALL
        ]
        count = int(self.sim_config["num_rovers"])
        if count > len(cells):
            raise ValueError(f"Spawn has {len(cells)} free cells for {count} rovers")
        order = self.rng.permutation(len(cells))[:count]
        return [
            Robot.create(
                robot_id,
                "rover",
                *cells[int(cell_index)],
                float(self.robot_config["battery"]),
                self.grid.shape,
            )
            for robot_id, cell_index in enumerate(order)
        ]

    def reset(self, seed: int | None = None) -> dict[int, dict[str, np.ndarray]]:
        self.seed = int(self.sim_config["seed"] if seed is None else seed)
        self.rng = make_rng(self.seed)
        self.grid, self.distances, self.victims = self._generate_with_victims()
        self.robots = self._spawn_robots()
        self.step_count = 0
        self.done = False
        update_all_vision(
            self.robots, self.grid, int(self.robot_config["vision_radius"])
        )
        for robot in self.robots:
            update_robot_sensors(
                robot,
                self.victims,
                self.grid,
                self.robot_config,
                self.rng,
                preserve_previous=False,
            )
        self.metrics = EpisodeMetrics(self.grid, self.distances, self.victims)
        self.metrics.update(0, self.robots)
        return self.observations()

    def step(
        self, actions: Mapping[int, int] | Sequence[int]
    ) -> tuple[dict[int, dict[str, np.ndarray]], dict[str, Any], bool]:
        if self.done:
            raise RuntimeError("Episode is done; call reset() before stepping again")
        if self.metrics is None:
            raise RuntimeError("Call reset() before step()")

        self.step_count += 1
        apply_movements(self.robots, actions, self.grid, self.robot_config, self.rng)
        newly_revealed = update_all_vision(
            self.robots, self.grid, int(self.robot_config["vision_radius"])
        )
        for robot in self.robots:
            if robot.alive:
                update_robot_sensors(
                    robot, self.victims, self.grid, self.robot_config, self.rng
                )
        newly_found = confirm_victims(
            self.robots,
            self.victims,
            self.grid,
            float(self.robot_config["confirm_radius"]),
            self.step_count,
        )
        self.metrics.update(self.step_count, self.robots)

        all_found = self.metrics.victims_found == len(self.victims)
        all_dead = not any(robot.alive for robot in self.robots)
        timed_out = self.step_count >= int(self.sim_config["max_steps"])
        self.done = (
            (all_found and bool(self.sim_config["end_when_all_found"]))
            or all_dead
            or timed_out
        )
        info = self.metrics.snapshot(self.step_count, self.robots)
        info.update({"newly_revealed": newly_revealed, "newly_found": newly_found})
        return self.observations(), info, self.done

    def observations(self) -> dict[int, dict[str, np.ndarray]]:
        return {robot.id: self._observation(robot) for robot in self.robots}

    def _observation(self, robot: Robot) -> dict[str, np.ndarray]:
        radius = int(self.sim_config["local_window_radius"])
        padded = np.pad(robot.belief, radius, constant_values=UNKNOWN)
        px, py = robot.x + radius, robot.y + radius
        local_map = padded[py - radius : py + radius + 1, px - radius : px + radius + 1].copy()
        full_battery = float(self.robot_config["battery"])
        spawn_x, spawn_y = spawn_center(self.world_config)
        height, width = self.grid.shape
        return {
            "local_map": local_map,
            "battery": np.array([robot.battery / full_battery], dtype=np.float32),
            "thermal": robot.thermal.copy(),
            "acoustic": robot.acoustic.copy(),
            "prev_thermal": robot.prev_thermal.copy(),
            "prev_acoustic": robot.prev_acoustic.copy(),
            "rel_pos": np.array(
                [(robot.x - spawn_x) / width, (robot.y - spawn_y) / height],
                dtype=np.float32,
            ),
            "collided": np.array([float(robot.collided)], dtype=np.float32),
        }

    def metrics_snapshot(self) -> dict[str, Any]:
        if self.metrics is None:
            raise RuntimeError("Call reset() first")
        return self.metrics.snapshot(self.step_count, self.robots)
