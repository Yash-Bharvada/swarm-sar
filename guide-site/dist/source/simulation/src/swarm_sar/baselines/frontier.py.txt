"""Coordinated, non-learning frontier exploration benchmark."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from swarm_sar.mapping.topology import AgentTopologicalMap
from swarm_sar.sim.env import HOLD, INVESTIGATE, DisasterResponseParallelEnv
from swarm_sar.utils.config import load_config


@dataclass
class EvidenceCluster:
    position: tuple[int, int]
    samples: dict[str, list[int]] = field(default_factory=dict)
    confidence: float = 0.0
    last_step: int = 0
    confirmed: bool = False
    last_verification_step: int = -10_000

    def add(self, agent: str, step: int, confidence: float) -> None:
        steps = self.samples.setdefault(agent, [])
        if not steps or steps[-1] != step:
            steps.append(step)
        self.confidence = max(self.confidence, float(confidence))
        self.last_step = step

    @property
    def agents(self) -> set[str]:
        return set(self.samples)

    def ready(self, repeat_required: int) -> bool:
        repeated = any(len(steps) >= repeat_required for steps in self.samples.values())
        corroborated = len(self.samples) >= 2
        return repeated or corroborated


class EvidenceBoard:
    """Groups noisy local detections without reading survivor ground truth."""

    def __init__(self, merge_radius: float, expiry_steps: int) -> None:
        self.merge_radius = float(merge_radius)
        self.expiry_steps = int(expiry_steps)
        self.clusters: list[EvidenceCluster] = []

    def record(
        self,
        agent: str,
        position: tuple[int, int],
        confidence: float,
        step: int,
    ) -> EvidenceCluster:
        self.clusters = [
            cluster
            for cluster in self.clusters
            if cluster.confirmed or step - cluster.last_step <= self.expiry_steps
        ]
        nearby = [
            cluster
            for cluster in self.clusters
            if not cluster.confirmed
            and np.hypot(
                cluster.position[0] - position[0],
                cluster.position[1] - position[1],
            )
            <= self.merge_radius
        ]
        if nearby:
            cluster = min(
                nearby,
                key=lambda item: np.hypot(
                    item.position[0] - position[0], item.position[1] - position[1]
                ),
            )
        else:
            cluster = EvidenceCluster(position=position, last_step=step)
            self.clusters.append(cluster)
        cluster.add(agent, step, confidence)
        return cluster


class CoordinatedFrontierBaseline:
    """Nearest-useful-frontier controller with reservations and evidence checks."""

    def __init__(
        self,
        env: DisasterResponseParallelEnv | None = None,
        config: dict[str, Any] | str | Path | None = None,
    ) -> None:
        self.env = env or DisasterResponseParallelEnv()
        root = Path(__file__).resolve().parents[4]
        self.config = (
            load_config(root / "configs/baseline.yaml")
            if config is None
            else load_config(config)
            if isinstance(config, (str, Path))
            else dict(config)
        )
        self.maps: dict[str, AgentTopologicalMap] = {}
        self.evidence = EvidenceBoard(
            self.config["evidence_merge_radius"], self.config["evidence_expiry_steps"]
        )
        self.goals: dict[str, tuple[int, int]] = {}
        self.reservations: dict[tuple[int, int], str] = {}
        self.events: list[dict[str, Any]] = []
        self.reservations_made = 0
        self.duplicate_goal_steps = 0
        self.verification_failures = 0
        self.map_exchange_events = 0
        self.observations: dict[str, dict[str, np.ndarray]] = {}

    def reset(self, seed: int) -> dict[str, dict[str, np.ndarray]]:
        self.observations, _ = self.env.reset(seed=seed)
        self.maps = {agent: AgentTopologicalMap(agent) for agent in self.env.agents}
        self.evidence = EvidenceBoard(
            self.config["evidence_merge_radius"], self.config["evidence_expiry_steps"]
        )
        self.goals = {}
        self.reservations = {}
        self.events = [{"step": 0, "event": "baseline_reset", "seed": seed}]
        self.reservations_made = 0
        self.duplicate_goal_steps = 0
        self.verification_failures = 0
        self.map_exchange_events = 0
        self._update_maps(force=True)
        return self.observations

    def _share_peer_maps(self) -> None:
        """Fuse occupancy knowledge only inside current radio-connected groups."""
        if not bool(self.config.get("peer_map_exchange", False)):
            return
        active = [
            self.env._robots_by_name[name]
            for name in self.env.agents
            if self.env._robots_by_name[name].alive
        ]
        unseen = {robot.id for robot in active}
        by_id = {robot.id: robot for robot in active}
        while unseen:
            root = unseen.pop()
            component = {root}
            frontier = [root]
            while frontier:
                current = by_id[frontier.pop()]
                linked = []
                for other_id in unseen:
                    other = by_id[other_id]
                    radius = min(
                        float(self.env.core.robot_configs[current.type]["comm_radius"]),
                        float(self.env.core.robot_configs[other.type]["comm_radius"]),
                    )
                    if np.hypot(current.x - other.x, current.y - other.y) <= radius:
                        linked.append(other_id)
                for other_id in linked:
                    unseen.remove(other_id)
                    component.add(other_id)
                    frontier.append(other_id)
            if len(component) < 2:
                continue
            members = [by_id[identifier] for identifier in sorted(component)]
            merged = np.full_like(members[0].belief, -1)
            for robot in members:
                known = robot.belief >= 0
                merged[known] = robot.belief[known]
            changed = 0
            for robot in members:
                received = (robot.belief < 0) & (merged >= 0)
                changed += int(np.count_nonzero(received))
                robot.belief[received] = merged[received]
            if changed:
                self.map_exchange_events += 1
                self.events.append(
                    {
                        "step": self.env.core.step_count,
                        "event": "peer_map_exchange",
                        "agents": [robot.name for robot in members],
                        "cells_received": changed,
                    }
                )

    def _estimate_detection_position(
        self, agent: str, thermal: np.ndarray
    ) -> tuple[int, int]:
        robot = self.env._robots_by_name[agent]
        config = self.env.core.robot_configs[robot.type]
        sector = int(np.argmax(thermal))
        strength = float(max(1e-4, thermal[sector]))
        distance = float(
            np.clip(
                -float(config["thermal_decay"]) * np.log(min(0.999, strength)),
                1.0,
                float(config["thermal_radius"]),
            )
        )
        dx, dy = ((0, -1), (1, 0), (0, 1), (-1, 0))[sector]
        width, height = self.env.core.grid.shape[1], self.env.core.grid.shape[0]
        return (
            int(np.clip(round(robot.odom_x + dx * distance), 1, width - 2)),
            int(np.clip(round(robot.odom_y + dy * distance), 1, height - 2)),
        )

    def _process_evidence(self) -> set[str]:
        investigating: set[str] = set()
        threshold = float(self.config["thermal_investigate_threshold"])
        repeat_required = int(self.config["repeat_evidence_required"])
        step = self.env.core.step_count
        for agent in self.env.agents:
            thermal = self.observations[agent]["thermal"]
            strength = float(np.max(thermal))
            if strength < threshold:
                continue
            investigating.add(agent)
            position = self._estimate_detection_position(agent, thermal)
            cluster = self.evidence.record(agent, position, strength, step)
            self.maps[agent].add_suspected_survivor(position, strength, step)
            self.events.append(
                {
                    "step": step,
                    "event": "survivor_evidence",
                    "agent": agent,
                    "position": position,
                    "confidence": strength,
                }
            )
            if not cluster.ready(repeat_required) or step - cluster.last_verification_step < 2:
                continue
            cluster.last_verification_step = step
            robot_ids = {
                self.env._robots_by_name[name].id
                for name in cluster.agents
                if name in self.env._robots_by_name
            }
            newly_found = self.env.core.confirm_from_evidence(robot_ids)
            if newly_found:
                cluster.confirmed = True
                for name in sorted(cluster.agents):
                    if name in self.maps:
                        self.maps[name].mark_survivor_confirmed(
                            cluster.position, cluster.confidence, step
                        )
                self.events.append(
                    {
                        "step": step,
                        "event": "survivor_confirmed",
                        "agents": sorted(cluster.agents),
                        "position": cluster.position,
                    }
                )
            else:
                self.verification_failures += 1
        return investigating

    def _update_maps(self, *, force: bool = False) -> None:
        step = self.env.core.step_count
        interval = int(self.config["topology_update_interval"])
        if not force and step % interval:
            return
        for agent in self.env.agents:
            robot = self.env._robots_by_name[agent]
            config = self.env.core.robot_configs[robot.type]
            self.maps[agent].update(
                robot.belief,
                self.env._candidate_list(agent),
                step,
                robot.odom_uncertainty,
                can_cross_rubble=bool(config["can_cross_rubble"]),
            )

    def _release_goal(self, agent: str) -> None:
        goal = self.goals.pop(agent, None)
        if goal is not None and self.reservations.get(goal) == agent:
            del self.reservations[goal]
        self.env.set_active_goal(agent, None)

    def _assign_frontiers(self, investigating: set[str]) -> dict[str, int]:
        actions = {agent: HOLD for agent in self.env.agents}
        active = set(self.env.agents)
        for agent in list(self.goals):
            if agent not in active:
                self._release_goal(agent)

        order = self.env.agents[:]
        if order:
            offset = self.env.core.step_count % len(order)
            order = order[offset:] + order[:offset]
        for agent in order:
            if agent in investigating:
                self._release_goal(agent)
                actions[agent] = INVESTIGATE
                continue
            robot = self.env._robots_by_name[agent]
            candidates = self.env._candidate_list(agent)
            by_position = {
                tuple(candidate["position"]): (slot, candidate)
                for slot, candidate in enumerate(candidates)
            }
            goal = self.goals.get(agent)
            if goal not in by_position:
                self._release_goal(agent)
                available = [
                    (slot, candidate)
                    for slot, candidate in enumerate(candidates)
                    if self.reservations.get(tuple(candidate["position"])) in (None, agent)
                ]
                if available:
                    acoustic = float(self.observations[agent]["acoustic"][0])
                    interest = acoustic >= float(self.config["acoustic_interest_threshold"])
                    slot, candidate = min(
                        available,
                        key=lambda item: (
                            item[1]["distance"]
                            - (0.15 if interest else 0.05) * item[1]["cluster_size"],
                            item[1]["distance"],
                        ),
                    )
                    goal = tuple(candidate["position"])
                    self.goals[agent] = goal
                    self.reservations[goal] = agent
                    self.env.set_active_goal(agent, goal)
                    candidates = self.env._candidate_list(agent)
                    by_position = {
                        tuple(item["position"]): (index, item)
                        for index, item in enumerate(candidates)
                    }
                    self.reservations_made += 1
                    self.events.append(
                        {
                            "step": self.env.core.step_count,
                            "event": "frontier_reserved",
                            "agent": agent,
                            "goal": goal,
                        }
                    )
                    actions[agent] = by_position[goal][0]
            else:
                actions[agent] = by_position[goal][0]
            if goal is not None and robot.position == goal:
                self._release_goal(agent)
                actions[agent] = HOLD
        return actions

    def _predicted_target(self, agent: str, action: int) -> tuple[int, int]:
        robot = self.env._robots_by_name[agent]
        if 0 <= action < 5:
            candidates = self.env._candidate_list(agent)
            if action < len(candidates) and len(candidates[action]["path"]) >= 2:
                return tuple(candidates[action]["path"][1])
        elif action == INVESTIGATE and float(robot.thermal.max()) > 0:
            sector = int(np.argmax(robot.thermal))
            dx, dy = ((0, -1), (1, 0), (0, 1), (-1, 0))[sector]
            target = (robot.x + dx, robot.y + dy)
            tx, ty = target
            if (
                0 <= tx < robot.belief.shape[1]
                and 0 <= ty < robot.belief.shape[0]
                and robot.belief[ty, tx] in (0, 2)
            ):
                return target
        return robot.position

    def _arbitrate_collisions(self, actions: dict[str, int]) -> dict[str, int]:
        occupied = {
            robot.position
            for robot in self.env.core.robots
            if robot.alive
        }
        planned: set[tuple[int, int]] = set()
        result = dict(actions)
        order = self.env.agents[:]
        if order:
            offset = self.env.core.step_count % len(order)
            order = order[offset:] + order[:offset]
        for agent in order:
            robot = self.env._robots_by_name[agent]
            target = self._predicted_target(agent, result[agent])
            if target == robot.position:
                continue
            if target in occupied or target in planned:
                result[agent] = HOLD
                continue
            planned.add(target)
        return result

    def choose_actions(self) -> dict[str, int]:
        self._share_peer_maps()
        self._update_maps()
        investigating = self._process_evidence()
        actions = self._assign_frontiers(investigating)
        if len(set(self.goals.values())) != len(self.goals):
            self.duplicate_goal_steps += 1
        return self._arbitrate_collisions(actions)

    def step(self):
        actions = self.choose_actions()
        result = self.env.step(actions)
        self.observations = result[0]
        return result

    def run_episode(self, seed: int, output_dir: str | Path | None = None) -> dict[str, Any]:
        self.reset(seed)
        max_steps = int(self.config["max_steps"])
        while self.env.agents and self.env.core.step_count < max_steps:
            self.step()
        self._update_maps(force=True)
        summary = self.summary()
        if output_dir is not None:
            self.save(output_dir, summary)
        return summary

    def summary(self) -> dict[str, Any]:
        metrics = self.env.core.metrics_snapshot()
        graph_counts = {
            agent: {
                "nodes": graph.graph.number_of_nodes(),
                "edges": graph.graph.number_of_edges(),
                "kinds": graph.node_kind_counts(),
            }
            for agent, graph in self.maps.items()
        }
        confirmed_markers = sum(
            data.get("kind") == "survivor_confirmed"
            for graph in self.maps.values()
            for _, data in graph.graph.nodes(data=True)
        )
        return {
            "seed": self.env.core.seed,
            "steps": self.env.core.step_count,
            "survivors_total": len(self.env.core.victims),
            "survivors_found": metrics["victims_found"],
            "coverage": metrics["coverage"],
            "collisions": metrics["collisions"],
            "reservations_made": self.reservations_made,
            "duplicate_goal_steps": self.duplicate_goal_steps,
            "evidence_clusters": len(self.evidence.clusters),
            "verification_failures": self.verification_failures,
            "map_exchange_events": self.map_exchange_events,
            "false_confirmations": 0,
            "confirmed_markers": confirmed_markers,
            "graphs": graph_counts,
        }

    def save(self, output_dir: str | Path, summary: dict[str, Any] | None = None) -> None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        self.env.save_episode(output / "episode")
        graph_dir = output / "topology"
        for agent, graph in self.maps.items():
            graph.save_json(graph_dir / f"{agent}.json")
        (output / "baseline_events.json").write_text(
            json.dumps(self.events, indent=2), encoding="utf-8"
        )
        (output / "baseline_summary.json").write_text(
            json.dumps(summary or self.summary(), indent=2), encoding="utf-8"
        )
