"""PettingZoo ParallelEnv with frontier-level decentralized actions."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from gymnasium import spaces
from pettingzoo import ParallelEnv

from swarm_sar.sensing.victim_sensor import acoustic_reading, thermal_reading
from swarm_sar.sim.engine import SwarmWorld
from swarm_sar.sim.planning import astar_path, frontier_candidates, movement_action

FRONTIER_SLOTS = 5
INVESTIGATE = 5
HOLD = 6
ACTION_COUNT = 7


class DisasterResponseParallelEnv(ParallelEnv):
    """Four-agent local-observation environment for Step 1 of the blueprint."""

    metadata = {
        "name": "swarm_sar_step1_v0",
        "render_modes": ["human", "rgb_array"],
        "render_fps": 10,
        "is_parallelizable": True,
    }

    def __init__(
        self,
        *,
        render_mode: str | None = None,
        world_config: dict[str, Any] | str | Path | None = None,
        robot_config: dict[str, Any] | str | Path | None = None,
        sim_config: dict[str, Any] | str | Path | None = None,
    ) -> None:
        if render_mode not in (None, "human", "rgb_array"):
            raise ValueError(f"Unsupported render mode: {render_mode}")
        self.render_mode = render_mode
        self.core = SwarmWorld(world_config, robot_config, sim_config)
        self.possible_agents = self._configured_agent_names()
        self.agents: list[str] = []
        self._robots_by_name = {}
        self._renderer = None
        self._invalid_actions: dict[str, bool] = {}
        self._candidate_cache: dict[str, list[dict[str, Any]]] = {}
        self._active_goals: dict[str, tuple[int, int]] = {}

    def _configured_agent_names(self) -> list[str]:
        counts = self.core.sim_config.get(
            "agent_counts", {"rover": int(self.core.sim_config.get("num_rovers", 0))}
        )
        names = []
        identifier = 0
        for robot_type, count in counts.items():
            for _ in range(int(count)):
                names.append(f"{robot_type}_{identifier}")
                identifier += 1
        return names

    @lru_cache(maxsize=None)
    def observation_space(self, agent: str):
        radius = int(self.core.sim_config["local_window_radius"])
        size = 2 * radius + 1
        return spaces.Dict(
            {
                "local_map": spaces.Box(-1, 2, shape=(size, size), dtype=np.int8),
                "battery": spaces.Box(0.0, 1.0, shape=(1,), dtype=np.float32),
                "thermal": spaces.Box(0.0, np.inf, shape=(4,), dtype=np.float32),
                "acoustic": spaces.Box(0.0, np.inf, shape=(1,), dtype=np.float32),
                "prev_thermal": spaces.Box(0.0, np.inf, shape=(4,), dtype=np.float32),
                "prev_acoustic": spaces.Box(0.0, np.inf, shape=(1,), dtype=np.float32),
                "rel_pos": spaces.Box(-4.0, 4.0, shape=(2,), dtype=np.float32),
                "pose_uncertainty": spaces.Box(0.0, np.inf, shape=(1,), dtype=np.float32),
                "collided": spaces.Box(0.0, 1.0, shape=(1,), dtype=np.float32),
                "frontier_features": spaces.Box(
                    -1.0, 1.0, shape=(FRONTIER_SLOTS, 5), dtype=np.float32
                ),
                "action_mask": spaces.MultiBinary(ACTION_COUNT),
            }
        )

    @lru_cache(maxsize=None)
    def action_space(self, agent: str):
        return spaces.Discrete(ACTION_COUNT)

    def _candidate_list(
        self, agent: str, *, refresh: bool = False
    ) -> list[dict[str, Any]]:
        if not refresh and agent in self._candidate_cache:
            return self._candidate_cache[agent]
        robot = self._robots_by_name[agent]
        config = self.core.robot_configs[robot.type]
        candidates = frontier_candidates(
            robot.belief,
            robot.position,
            max_candidates=int(self.core.sim_config.get("max_frontiers", FRONTIER_SLOTS)),
            max_per_cluster=int(
                self.core.sim_config.get("frontier_samples_per_cluster", 1)
            ),
            can_cross_rubble=bool(config["can_cross_rubble"]),
        )
        active_goal = self._active_goals.get(agent)
        if active_goal is not None and active_goal != robot.position:
            active_path = astar_path(
                robot.belief,
                robot.position,
                active_goal,
                can_cross_rubble=bool(config["can_cross_rubble"]),
            )
            if active_path:
                candidates = [
                    {
                        "position": active_goal,
                        "cluster_size": 1,
                        "path": active_path,
                        "distance": len(active_path) - 1,
                        "active_goal": True,
                    }
                ] + [
                    candidate
                    for candidate in candidates
                    if tuple(candidate["position"]) != active_goal
                ]
                candidates = candidates[:FRONTIER_SLOTS]
        self._candidate_cache[agent] = candidates
        return candidates

    def set_active_goal(self, agent: str, goal: tuple[int, int] | None) -> None:
        if goal is None:
            self._active_goals.pop(agent, None)
        else:
            self._active_goals[agent] = tuple(goal)
        self._candidate_cache.pop(agent, None)

    def observe(self, agent: str) -> dict[str, np.ndarray]:
        robot = self._robots_by_name[agent]
        observation = self.core._observation(robot)
        candidates = self._candidate_list(agent, refresh=True)
        features = np.zeros((FRONTIER_SLOTS, 5), dtype=np.float32)
        height, width = self.core.grid.shape
        scale = float(max(width, height))
        for index, candidate in enumerate(candidates[:FRONTIER_SLOTS]):
            x, y = candidate["position"]
            features[index] = (
                np.clip((x - robot.odom_x) / width, -1.0, 1.0),
                np.clip((y - robot.odom_y) / height, -1.0, 1.0),
                min(1.0, candidate["distance"] / scale),
                min(1.0, candidate["cluster_size"] / 20.0),
                1.0,
            )
        action_mask = np.zeros(ACTION_COUNT, dtype=np.int8)
        action_mask[: len(candidates)] = 1
        action_mask[INVESTIGATE] = 1
        action_mask[HOLD] = 1
        observation.update(
            {"frontier_features": features, "action_mask": action_mask}
        )
        return observation

    def reset(
        self,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, dict[str, Any]]]:
        del options
        self.core.reset(seed)
        self._robots_by_name = {robot.name: robot for robot in self.core.robots}
        actual_names = list(self._robots_by_name)
        if actual_names != self.possible_agents:
            raise RuntimeError(
                f"Configured agents {self.possible_agents} do not match spawned agents {actual_names}"
            )
        self.agents = self.possible_agents[:]
        self._invalid_actions = {agent: False for agent in self.agents}
        self._candidate_cache = {}
        self._active_goals = {}
        observations = {agent: self.observe(agent) for agent in self.agents}
        infos = {
            agent: {"agent_type": self._robots_by_name[agent].type, "seed": self.core.seed}
            for agent in self.agents
        }
        if self.render_mode == "human":
            self.render()
        return observations, infos

    def step(self, actions: dict[str, int]):
        if not self.agents:
            raise RuntimeError("Episode has ended; call reset()")
        missing = set(self.agents) - set(actions)
        extra = set(actions) - set(self.agents)
        if missing or extra:
            raise ValueError(f"Action keys mismatch; missing={sorted(missing)}, extra={sorted(extra)}")

        current_agents = self.agents[:]
        movement_actions: dict[int, int] = {}
        investigating: set[str] = set()
        self._invalid_actions = {}
        for agent in current_agents:
            action = int(actions[agent])
            if not self.action_space(agent).contains(action):
                raise ValueError(f"Invalid action {action} for {agent}")
            robot = self._robots_by_name[agent]
            candidates = self._candidate_list(agent)
            invalid = False
            movement = 0
            if 0 <= action < FRONTIER_SLOTS:
                if action >= len(candidates):
                    invalid = True
                else:
                    path = candidates[action]["path"]
                    self._active_goals[agent] = tuple(candidates[action]["position"])
                    if len(path) >= 2:
                        movement = movement_action(robot.position, path[1])
            elif action == INVESTIGATE:
                investigating.add(agent)
                if float(robot.thermal.max()) > 0.0:
                    sector = int(np.argmax(robot.thermal))
                    movement = (1, 4, 2, 3)[sector]
                    dx, dy = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0)}[
                        movement
                    ]
                    tx, ty = robot.x + dx, robot.y + dy
                    if not (
                        0 <= tx < robot.belief.shape[1]
                        and 0 <= ty < robot.belief.shape[0]
                        and robot.belief[ty, tx] in (0, 2)
                    ):
                        movement = 0
            elif action != HOLD:
                invalid = True
            self._invalid_actions[agent] = invalid
            movement_actions[robot.id] = movement

        _, core_info, _ = self.core.step(movement_actions)
        self._candidate_cache = {}
        for agent in list(self._active_goals):
            if self._robots_by_name[agent].position == self._active_goals[agent]:
                del self._active_goals[agent]
        # Investigate follows the strongest thermal sector when locally traversable,
        # then fuses an independent second sample without exposing truth.
        for agent in sorted(investigating):
            robot = self._robots_by_name[agent]
            if not robot.alive:
                continue
            config = self.core.robot_configs[robot.type]
            extra_thermal = thermal_reading(
                robot, self.core.victims, self.core.grid, config, self.core.rng
            )
            extra_acoustic = acoustic_reading(
                robot, self.core.victims, self.core.grid, config, self.core.rng
            )
            robot.thermal = ((robot.thermal + extra_thermal) / 2.0).astype(np.float32)
            robot.acoustic = ((robot.acoustic + extra_acoustic) / 2.0).astype(np.float32)
            self.core.events.append(
                {"step": self.core.step_count, "event": "investigate", "agent": agent}
            )
        all_found = core_info["victims_found"] == len(self.core.victims)
        all_dead = not any(robot.alive for robot in self.core.robots)
        timed_out = self.core.step_count >= int(self.core.sim_config["max_steps"])
        globally_terminated = all_found or all_dead
        globally_truncated = timed_out and not globally_terminated

        rewards: dict[str, float] = {}
        infos: dict[str, dict[str, Any]] = {}
        for agent in current_agents:
            robot = self._robots_by_name[agent]
            reward = (
                5.0 * core_info["newly_found"]
                + 0.1 * self.core.last_revealed_by_robot[robot.id]
                - float(robot.collided)
                - 0.01
            )
            rewards[agent] = float(reward)
            infos[agent] = {
                "agent_type": robot.type,
                "invalid_action": self._invalid_actions[agent],
                "investigating": agent in investigating,
                "newly_revealed": self.core.last_revealed_by_robot[robot.id],
                "victims_found": core_info["victims_found"],
                "coverage": core_info["coverage"],
            }
        terminations = {
            agent: globally_terminated or not self._robots_by_name[agent].alive
            for agent in current_agents
        }
        truncations = {agent: globally_truncated for agent in current_agents}
        self.agents = [
            agent
            for agent in current_agents
            if not terminations[agent] and not truncations[agent]
        ]
        observations = {agent: self.observe(agent) for agent in self.agents}
        if self.render_mode == "human":
            self.render()
        return observations, rewards, terminations, truncations, infos

    def render(self):
        if self.render_mode is None:
            return None
        if self._renderer is None:
            from swarm_sar.viz.renderer import Renderer

            self._renderer = Renderer(
                self.core,
                rgb_array=self.render_mode == "rgb_array",
            )
        return self._renderer.draw()

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    def save_episode(self, output_dir: str | Path) -> dict[str, Path]:
        return self.core.save_episode(output_dir)


def parallel_env(**kwargs) -> DisasterResponseParallelEnv:
    return DisasterResponseParallelEnv(**kwargs)
