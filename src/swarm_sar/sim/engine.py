"""Core simulation engine (intentionally independent of pygame)."""

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from swarm_sar.robots.robot import Robot
from swarm_sar.sensing.victim_sensor import confirm_victims, update_robot_sensors
from swarm_sar.sensing.vision import update_vision
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
    robot_config: dict[str, Any] | dict[str, dict[str, Any]],
    rng: np.random.Generator,
) -> None:
    """Resolve and apply simultaneous intents without corridor-order artefacts."""
    action_by_id = _normalise_actions(robots, actions)
    height, width = grid.shape
    alive = {robot.id: robot for robot in robots if robot.alive}
    occupant = {robot.position: robot.id for robot in alive.values()}
    targets: dict[int, tuple[int, int]] = {}
    eligible: set[int] = set()

    def config_for(robot: Robot) -> dict[str, Any]:
        return (
            robot_config[robot.type]
            if robot.type in robot_config and isinstance(robot_config[robot.type], dict)
            else robot_config
        )

    for robot in robots:
        robot.collided = False
        robot.last_action = action_by_id[robot.id]
        if not robot.alive:
            continue
        dx, dy = ACTIONS[robot.last_action]
        target = (robot.x + dx, robot.y + dy)
        targets[robot.id] = target
        if robot.last_action:
            config = config_for(robot)
            tx, ty = target
            blocked = not (0 <= tx < width and 0 <= ty < height)
            if not blocked and grid[ty, tx] == WALL and not bool(config["can_cross_walls"]):
                blocked = True
            if not blocked and grid[ty, tx] == RUBBLE and not bool(config["can_cross_rubble"]):
                blocked = True
            if not blocked:
                eligible.add(robot.id)

    claims: dict[tuple[int, int], list[int]] = {}
    for identifier in eligible:
        claims.setdefault(targets[identifier], []).append(identifier)
    for claimants in claims.values():
        if len(claimants) > 1:
            ordered = sorted(claimants)
            winner = ordered[int(rng.integers(len(ordered)))]
            eligible.difference_update(identifier for identifier in ordered if identifier != winner)

    memo: dict[int, bool] = {}

    def can_move(identifier: int, visiting: set[int]) -> bool:
        if identifier in memo:
            return memo[identifier]
        other = occupant.get(targets[identifier])
        if other is None:
            memo[identifier] = True
            return True
        if other not in eligible or other in visiting:
            memo[identifier] = False
            return False
        allowed = can_move(other, visiting | {other})
        memo[identifier] = allowed
        return allowed

    accepted = {
        identifier
        for identifier in eligible
        if can_move(identifier, {identifier})
    }

    for robot in robots:
        if not robot.alive:
            continue
        config = config_for(robot)
        moving = robot.last_action != 0
        accepted_move = robot.id in accepted

        if moving and not accepted_move:
            robot.collided = True
            cost = float(config["idle_cost"])
        elif not moving:
            cost = float(config["idle_cost"])
        else:
            dx, dy = ACTIONS[robot.last_action]
            robot.x, robot.y = targets[robot.id]
            robot.visited[robot.y, robot.x] = True
            robot.distance_travelled += 1
            drift_std = float(config.get("odometry_drift_std", 0.0))
            robot.odom_x += dx + float(rng.normal(0.0, drift_std))
            robot.odom_y += dy + float(rng.normal(0.0, drift_std))
            robot.odom_uncertainty += float(
                config.get("odometry_uncertainty_growth", drift_std)
            )
            cost = (
                float(config["rubble_cost"])
                if grid[robot.y, robot.x] == RUBBLE
                else float(config["move_cost"])
            )

        robot.battery = max(0.0, robot.battery - cost)
        if robot.battery <= 0.0:
            robot.alive = False


class SwarmWorld:
    """Deterministic heterogeneous search-and-rescue simulation core."""

    def __init__(
        self,
        world_config: dict[str, Any] | str | Path | None = None,
        robot_config: dict[str, Any] | str | Path | None = None,
        sim_config: dict[str, Any] | str | Path | None = None,
    ) -> None:
        root = Path(__file__).resolve().parents[3]
        self.world_config = self._config(world_config, root / "configs/world.yaml")
        all_robot_config = self._config(robot_config, root / "configs/robots.yaml")
        self.robot_configs = (
            all_robot_config
            if all(isinstance(value, dict) for value in all_robot_config.values())
            else {"rover": all_robot_config}
        )
        # Kept for compatibility with older callers; new code uses robot_configs.
        self.robot_config = self.robot_configs["rover"]
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
        self.events: list[dict[str, Any]] = []
        self.trajectory: list[dict[str, Any]] = []
        self.last_revealed_by_robot: dict[int, int] = {}

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
        configured_counts = self.sim_config.get("agent_counts")
        if configured_counts is None:
            configured_counts = {"rover": int(self.sim_config.get("num_rovers", 0))}
        robot_types = [
            robot_type
            for robot_type, count in configured_counts.items()
            for _ in range(int(count))
        ]
        count = len(robot_types)
        if count > len(cells):
            raise ValueError(f"Spawn has {len(cells)} free cells for {count} agents")
        unknown_types = set(robot_types) - set(self.robot_configs)
        if unknown_types:
            raise ValueError(f"Missing robot configuration for: {sorted(unknown_types)}")
        order = self.rng.permutation(len(cells))[:count]
        return [
            Robot.create(
                robot_id,
                robot_type,
                *cells[int(cell_index)],
                float(self.robot_configs[robot_type]["battery"]),
                self.grid.shape,
            )
            for robot_id, (robot_type, cell_index) in enumerate(zip(robot_types, order))
        ]

    def _record_trajectory(self) -> None:
        for robot in self.robots:
            self.trajectory.append(
                {
                    "step": self.step_count,
                    "agent": robot.name,
                    "type": robot.type,
                    "x": robot.x,
                    "y": robot.y,
                    "odom_x": robot.odom_x,
                    "odom_y": robot.odom_y,
                    "pose_uncertainty": robot.odom_uncertainty,
                    "battery": robot.battery,
                    "alive": robot.alive,
                    "action": robot.last_action,
                    "collided": robot.collided,
                }
            )

    def reset(self, seed: int | None = None) -> dict[int, dict[str, np.ndarray]]:
        self.seed = int(self.sim_config["seed"] if seed is None else seed)
        self.rng = make_rng(self.seed)
        self.grid, self.distances, self.victims = self._generate_with_victims()
        self.robots = self._spawn_robots()
        self.step_count = 0
        self.done = False
        self.events = [{"step": 0, "event": "reset", "seed": self.seed}]
        self.trajectory = []
        self.last_revealed_by_robot = {}
        for robot in self.robots:
            self.last_revealed_by_robot[robot.id] = update_vision(
                robot,
                self.grid,
                int(self.robot_configs[robot.type]["vision_radius"]),
            )
            update_robot_sensors(
                robot,
                self.victims,
                self.grid,
                self.robot_configs[robot.type],
                self.rng,
                preserve_previous=False,
            )
        self.metrics = EpisodeMetrics(self.grid, self.distances, self.victims)
        self.metrics.update(0, self.robots)
        self._record_trajectory()
        return self.observations()

    def step(
        self, actions: Mapping[int, int] | Sequence[int]
    ) -> tuple[dict[int, dict[str, np.ndarray]], dict[str, Any], bool]:
        if self.done:
            raise RuntimeError("Episode is done; call reset() before stepping again")
        if self.metrics is None:
            raise RuntimeError("Call reset() before step()")

        self.step_count += 1
        alive_before = {robot.id: robot.alive for robot in self.robots}
        apply_movements(self.robots, actions, self.grid, self.robot_configs, self.rng)
        self.last_revealed_by_robot = {}
        for robot in self.robots:
            if robot.alive:
                self.last_revealed_by_robot[robot.id] = update_vision(
                    robot,
                    self.grid,
                    int(self.robot_configs[robot.type]["vision_radius"]),
                )
                update_robot_sensors(
                    robot,
                    self.victims,
                    self.grid,
                    self.robot_configs[robot.type],
                    self.rng,
                )
            else:
                self.last_revealed_by_robot[robot.id] = 0
        newly_found = 0
        if bool(self.sim_config.get("auto_confirm_victims", True)):
            newly_found = confirm_victims(
                self.robots,
                self.victims,
                self.grid,
                {
                    robot_type: float(config["confirm_radius"])
                    for robot_type, config in self.robot_configs.items()
                },
                self.step_count,
            )
        for robot in self.robots:
            if robot.collided:
                self.events.append(
                    {"step": self.step_count, "event": "collision", "agent": robot.name}
                )
            if alive_before[robot.id] and not robot.alive:
                self.events.append(
                    {"step": self.step_count, "event": "battery_depleted", "agent": robot.name}
                )
        for victim in self.victims:
            if victim["found_step"] == self.step_count:
                finder = next(robot.name for robot in self.robots if robot.id == victim["found_by"])
                self.events.append(
                    {
                        "step": self.step_count,
                        "event": "survivor_confirmed",
                        "victim_id": victim["id"],
                        "agent": finder,
                    }
                )
        self.metrics.update(self.step_count, self.robots)
        self._record_trajectory()

        all_found = self.metrics.victims_found == len(self.victims)
        all_dead = not any(robot.alive for robot in self.robots)
        timed_out = self.step_count >= int(self.sim_config["max_steps"])
        self.done = (
            (all_found and bool(self.sim_config["end_when_all_found"]))
            or all_dead
            or timed_out
        )
        info = self.metrics.snapshot(self.step_count, self.robots)
        info.update(
            {
                "newly_revealed": sum(self.last_revealed_by_robot.values()),
                "newly_revealed_by_robot": dict(self.last_revealed_by_robot),
                "newly_found": newly_found,
            }
        )
        return self.observations(), info, self.done

    def observations(self) -> dict[int, dict[str, np.ndarray]]:
        return {robot.id: self._observation(robot) for robot in self.robots}

    def _observation(self, robot: Robot) -> dict[str, np.ndarray]:
        radius = int(self.sim_config["local_window_radius"])
        padded = np.pad(robot.belief, radius, constant_values=UNKNOWN)
        px, py = robot.x + radius, robot.y + radius
        local_map = padded[py - radius : py + radius + 1, px - radius : px + radius + 1].copy()
        full_battery = float(self.robot_configs[robot.type]["battery"])
        spawn_x, spawn_y = spawn_center(self.world_config)
        pose_scale = float(self.sim_config.get("pose_scale_cells", 32))
        return {
            "local_map": local_map,
            "battery": np.array([robot.battery / full_battery], dtype=np.float32),
            "thermal": robot.thermal.copy(),
            "acoustic": robot.acoustic.copy(),
            "prev_thermal": robot.prev_thermal.copy(),
            "prev_acoustic": robot.prev_acoustic.copy(),
            "rel_pos": np.array(
                [
                    np.clip((robot.odom_x - spawn_x) / pose_scale, -4.0, 4.0),
                    np.clip((robot.odom_y - spawn_y) / pose_scale, -4.0, 4.0),
                ],
                dtype=np.float32,
            ),
            "pose_uncertainty": np.array([robot.odom_uncertainty], dtype=np.float32),
            "collided": np.array([float(robot.collided)], dtype=np.float32),
        }

    def metrics_snapshot(self) -> dict[str, Any]:
        if self.metrics is None:
            raise RuntimeError("Call reset() first")
        return self.metrics.snapshot(self.step_count, self.robots)

    def save_episode(self, output_dir: str | Path) -> dict[str, Path]:
        """Save ground-truth map metadata, events and per-agent trajectories."""
        from swarm_sar.sim.logging import save_episode_artifacts

        if self.metrics is None:
            raise RuntimeError("Call reset() before saving an episode")
        return save_episode_artifacts(self, output_dir)

    def confirm_from_evidence(self, robot_ids: set[int] | list[int]) -> int:
        """Ask the truth-side confirmation sensor to verify evidence-bearing agents."""
        if self.metrics is None:
            raise RuntimeError("Call reset() before confirming survivors")
        selected = [robot for robot in self.robots if robot.id in set(robot_ids)]
        newly_found = confirm_victims(
            selected,
            self.victims,
            self.grid,
            {
                robot_type: float(config["confirm_radius"])
                for robot_type, config in self.robot_configs.items()
            },
            self.step_count,
        )
        if newly_found:
            self.metrics.record_victim_times(self.step_count)
            if self.metrics.victims_over_time:
                self.metrics.victims_over_time[-1] = self.metrics.victims_found
            for victim in self.victims:
                if victim["found_step"] == self.step_count:
                    finder = next(
                        robot.name for robot in self.robots if robot.id == victim["found_by"]
                    )
                    event = {
                        "step": self.step_count,
                        "event": "survivor_confirmed",
                        "victim_id": victim["id"],
                        "agent": finder,
                        "confirmation": "repeat_or_multi_agent_evidence",
                    }
                    if event not in self.events:
                        self.events.append(event)
        return newly_found
