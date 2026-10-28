"""PettingZoo ParallelEnv with frontier-level decentralized actions."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from gymnasium import spaces
from pettingzoo import ParallelEnv

from swarm_sar.network import PeerNetwork
from swarm_sar.sensing.victim_sensor import acoustic_reading, thermal_reading
from swarm_sar.sim.engine import SwarmWorld
from swarm_sar.sim.planning import astar_path, frontier_candidates, movement_action
from swarm_sar.world.cells import RUBBLE, WALL

FRONTIER_SLOTS = 5
INVESTIGATE = 5
HOLD = 6
ACTION_COUNT = 7


class DisasterResponseParallelEnv(ParallelEnv):
    """Variable-team local-observation environment for the swarm blueprint."""

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
        self.network: PeerNetwork | None = None
        self._last_broadcast_beliefs: dict[str, np.ndarray] = {}
        self._snapshot_cursors: dict[str, int] = {}
        self._network_application_metrics = {
            "map_cells_merged": 0,
            "map_merges_refused": 0,
            "messages_processed": 0,
        }

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
                "peer_summary": spaces.Box(-1.0, 1.0, shape=(8,), dtype=np.float32),
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
        candidates = self._candidate_list(agent)
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
        occupied = {
            other.position
            for other in self.core.robots
            if other.alive and other.id != robot.id
        }
        for index, candidate in enumerate(candidates[:FRONTIER_SLOTS]):
            path = candidate["path"]
            if len(path) < 2 or tuple(path[1]) not in occupied:
                action_mask[index] = 1
        action_mask[INVESTIGATE] = 1
        action_mask[HOLD] = 1
        observation.update(
            {
                "frontier_features": features,
                "peer_summary": self._peer_summary(agent),
                "action_mask": action_mask,
            }
        )
        return observation

    def _safety_filter_movements(
        self, movement_actions: dict[int, int]
    ) -> dict[int, int]:
        """Apply a decentralized-style one-step shield below policy goal selection."""
        deltas = {
            0: (0, 0),
            1: (0, -1),
            2: (0, 1),
            3: (-1, 0),
            4: (1, 0),
        }
        robots = {robot.id: robot for robot in self.core.robots if robot.alive}
        filtered = dict(movement_actions)
        occupant = {robot.position: identifier for identifier, robot in robots.items()}

        # Local narrow-passage traffic rule. If a priority robot's requested step
        # points through a contiguous line of peers to a free cell, that line
        # yields in the same direction for one tick. This clears opposing intents
        # without global path planning and cannot create overlap.
        locked: set[int] = set()
        identifiers = sorted(robots)
        if identifiers:
            offset = self.core.step_count % len(identifiers)
            priority_order = identifiers[offset:] + identifiers[:offset]
        else:
            priority_order = []
        for identifier in priority_order:
            action = filtered.get(identifier, 0)
            if not action or identifier in locked:
                continue
            dx, dy = deltas[action]
            chain = [identifier]
            cursor = (robots[identifier].x + dx, robots[identifier].y + dy)
            while cursor in occupant and occupant[cursor] not in chain:
                other = occupant[cursor]
                chain.append(other)
                cursor = (robots[other].x + dx, robots[other].y + dy)
            if len(chain) < 2 or cursor in occupant or any(item in locked for item in chain):
                continue
            traversable = True
            for item in chain:
                robot = robots[item]
                tx, ty = robot.x + dx, robot.y + dy
                config = self.core.robot_configs[robot.type]
                if not (0 <= tx < self.core.grid.shape[1] and 0 <= ty < self.core.grid.shape[0]):
                    traversable = False
                    break
                cell = int(self.core.grid[ty, tx])
                if cell == WALL and not bool(config["can_cross_walls"]):
                    traversable = False
                    break
                if cell == RUBBLE and not bool(config["can_cross_rubble"]):
                    traversable = False
                    break
            if traversable:
                for item in chain:
                    filtered[item] = action
                locked.update(chain)

        targets: dict[int, tuple[int, int]] = {}
        for identifier, action in filtered.items():
            robot = robots.get(identifier)
            if robot is None:
                continue
            dx, dy = deltas[action]
            target = (robot.x + dx, robot.y + dy)
            targets[identifier] = target

        claims: dict[tuple[int, int], list[int]] = {}
        for identifier, target in targets.items():
            if target != robots[identifier].position:
                claims.setdefault(target, []).append(identifier)
        for claimants in claims.values():
            if len(claimants) < 2:
                continue
            claimants.sort()
            winner = claimants[self.core.step_count % len(claimants)]
            for identifier in claimants:
                if identifier != winner:
                    filtered[identifier] = 0
                    targets[identifier] = robots[identifier].position

        # Permit a convoy to advance through a one-cell corridor when every robot
        # ahead is leaving its cell. Cycles (including head-on swaps) and chains
        # ending at a stationary robot remain blocked.
        memo: dict[int, bool] = {}

        def can_move(identifier: int, visiting: set[int]) -> bool:
            if identifier in memo:
                return memo[identifier]
            if filtered.get(identifier, 0) == 0:
                memo[identifier] = False
                return False
            other = occupant.get(targets[identifier])
            if other is None:
                memo[identifier] = True
                return True
            if other in visiting:
                memo[identifier] = False
                return False
            allowed = can_move(other, visiting | {other})
            memo[identifier] = allowed
            return allowed

        for identifier in sorted(filtered):
            if filtered[identifier] and not can_move(identifier, {identifier}):
                filtered[identifier] = 0
        return filtered

    def _peer_summary(self, agent: str) -> np.ndarray:
        """Aggregate only range-reachable peer advertisements into a fixed vector."""
        summary = np.zeros(8, dtype=np.float32)
        if self.network is None:
            return summary
        robot = self._robots_by_name[agent]
        summary[0] = 1.0
        messages = self.network.peer_messages(agent, self.core.step_count)
        if not messages:
            return summary
        pose_scale = float(self.core.sim_config.get("pose_scale_cells", 32))
        count_scale = max(1, len(self.core.robots) - 1)
        summary[1] = len(messages) / count_scale
        summary[2] = sum(
            message.payload.get("robot_type") == "rover" for message in messages
        ) / len(messages)
        summary[3] = sum(
            message.payload.get("robot_type") == "drone" for message in messages
        ) / len(messages)
        summary[4] = float(
            np.clip(
                np.mean([message.pose[0] - robot.odom_x for message in messages])
                / pose_scale,
                -1.0,
                1.0,
            )
        )
        summary[5] = float(
            np.clip(
                np.mean([message.pose[1] - robot.odom_y for message in messages])
                / pose_scale,
                -1.0,
                1.0,
            )
        )
        summary[6] = float(
            np.clip(
                np.mean(
                    [
                        float(message.payload.get("evidence", {}).get("thermal", 0.0))
                        for message in messages
                    ]
                ),
                0,
                1,
            )
        )
        summary[7] = float(
            np.clip(
                np.mean(
                    [
                        float(message.payload.get("evidence", {}).get("acoustic", 0.0))
                        for message in messages
                    ]
                ),
                0,
                1,
            )
        )
        return summary

    def _evidence_position(self, agent: str) -> tuple[int, int] | None:
        robot = self._robots_by_name[agent]
        strength = float(robot.thermal.max())
        if strength <= 0.0:
            return None
        config = self.core.robot_configs[robot.type]
        sector = int(np.argmax(robot.thermal))
        distance = float(
            np.clip(
                -float(config["thermal_decay"]) * np.log(max(1e-4, min(0.999, strength))),
                1.0,
                float(config["thermal_radius"]),
            )
        )
        dx, dy = ((0, -1), (1, 0), (0, 1), (-1, 0))[sector]
        return int(round(robot.odom_x + dx * distance)), int(
            round(robot.odom_y + dy * distance)
        )

    def _map_cells_for_broadcast(self, agent: str) -> tuple[list[list[int]], bool]:
        robot = self._robots_by_name[agent]
        limit = int(self.core.sim_config.get("network_map_chunk_cells", 64))
        previous = self._last_broadcast_beliefs[agent]
        changed = np.argwhere((robot.belief >= 0) & (robot.belief != previous))
        snapshot = False
        if len(changed):
            selected = changed[:limit]
            for y, x in selected:
                previous[y, x] = robot.belief[y, x]
        elif self.core.step_count % int(
            self.core.sim_config.get("network_snapshot_interval", 8)
        ) == 0:
            known = np.argwhere(robot.belief >= 0)
            if len(known):
                cursor = self._snapshot_cursors[agent] % len(known)
                indices = [known[(cursor + offset) % len(known)] for offset in range(min(limit, len(known)))]
                selected = np.asarray(indices)
                self._snapshot_cursors[agent] = cursor + len(selected)
                snapshot = True
            else:
                selected = np.empty((0, 2), dtype=int)
        else:
            selected = np.empty((0, 2), dtype=int)
        return [
            [int(x), int(y), int(robot.belief[y, x])] for y, x in selected
        ], snapshot

    def _broadcast_network_state(self) -> None:
        if self.network is None:
            return
        for agent in sorted(self._robots_by_name):
            robot = self._robots_by_name[agent]
            if not robot.alive:
                continue
            candidates = self._candidate_list(agent)
            cells, snapshot = self._map_cells_for_broadcast(agent)
            evidence_position = self._evidence_position(agent)
            payload = {
                "robot_type": robot.type,
                "goal": list(self._active_goals[agent]) if agent in self._active_goals else None,
                "evidence": {
                    "thermal": float(robot.thermal.max()),
                    "acoustic": float(robot.acoustic[0]),
                    "position": list(evidence_position) if evidence_position else None,
                },
                "graph_delta": [
                    {"kind": "frontier", "position": list(item["position"])}
                    for item in candidates[:5]
                ],
                "map_cells": cells,
                "map_snapshot": snapshot,
            }
            self.network.broadcast(
                agent,
                frame_id="common_entry_v1",
                step=self.core.step_count,
                kind="state_delta",
                pose=(robot.odom_x, robot.odom_y),
                pose_uncertainty=robot.odom_uncertainty,
                payload=payload,
            )

    def _process_network_messages(self) -> None:
        if self.network is None:
            return
        uncertainty_limit = float(
            self.core.sim_config.get("network_transform_uncertainty_max", 4.0)
        )
        for agent in sorted(self._robots_by_name):
            receiver = self._robots_by_name[agent]
            for message in self.network.drain(agent):
                self._network_application_metrics["messages_processed"] += 1
                cells = message.payload.get("map_cells", [])
                aligned = (
                    message.frame_id == "common_entry_v1"
                    and message.pose_uncertainty <= uncertainty_limit
                    and receiver.odom_uncertainty <= uncertainty_limit
                )
                if cells and not aligned:
                    self._network_application_metrics["map_merges_refused"] += 1
                    continue
                merged = 0
                for x, y, value in cells:
                    if (
                        0 <= y < receiver.belief.shape[0]
                        and 0 <= x < receiver.belief.shape[1]
                        and receiver.belief[y, x] < 0
                    ):
                        receiver.belief[y, x] = int(value)
                        merged += 1
                self._network_application_metrics["map_cells_merged"] += merged

    def peer_claims(self, agent: str) -> set[tuple[int, int]]:
        return set(self.peer_claims_by_sender(agent).values())

    def peer_claims_by_sender(self, agent: str) -> dict[str, tuple[int, int]]:
        if self.network is None:
            return {}
        claims = {}
        for message in self.network.peer_messages(agent, self.core.step_count):
            goal = message.payload.get("goal")
            if goal is not None:
                claims[message.sender_id] = (int(goal[0]), int(goal[1]))
        return claims

    def network_metrics(self) -> dict[str, Any]:
        if self.network is None:
            return {"enabled": False, **self._network_application_metrics}
        return {
            "enabled": True,
            **self.network.snapshot(),
            **self._network_application_metrics,
        }

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
        self._network_application_metrics = {
            "map_cells_merged": 0,
            "map_merges_refused": 0,
            "messages_processed": 0,
        }
        if bool(self.core.sim_config.get("network_enabled", False)):
            self.network = PeerNetwork(self.core.sim_config, self.core.seed)
            self.network.register(self.agents)
            self._last_broadcast_beliefs = {
                agent: np.full_like(self._robots_by_name[agent].belief, -1)
                for agent in self.agents
            }
            self._snapshot_cursors = {agent: 0 for agent in self.agents}
            self._broadcast_network_state()
            self.network.advance(
                0, self.core.robots, self.core.robot_configs, self.core.grid
            )
            self._process_network_messages()
        else:
            self.network = None
            self._last_broadcast_beliefs = {}
            self._snapshot_cursors = {}
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

        movement_actions = self._safety_filter_movements(movement_actions)
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
        newly_confirmed = 0
        if bool(self.core.sim_config.get("investigate_confirms_victims", False)):
            newly_confirmed = self.core.confirm_from_evidence(
                {
                    self._robots_by_name[agent].id
                    for agent in investigating
                    if self._robots_by_name[agent].alive
                }
            )
        core_info["newly_found"] += newly_confirmed
        core_info["victims_found"] = self.core.metrics.victims_found
        self._broadcast_network_state()
        if self.network is not None:
            self.network.advance(
                self.core.step_count,
                self.core.robots,
                self.core.robot_configs,
                self.core.grid,
            )
            self._process_network_messages()
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
                "newly_found": core_info["newly_found"],
                "victims_found": core_info["victims_found"],
                "coverage": core_info["coverage"],
                "network": self.network_metrics(),
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
