"""Per-agent frontier control using only local state and peer messages."""

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from swarm_sar.mapping.topology import AgentTopologicalMap
from swarm_sar.sim.env import HOLD, INVESTIGATE, DisasterResponseParallelEnv
from swarm_sar.utils.config import load_config


class DecentralizedFrontierController:
    """Orchestrates independent agent loops without a global reservation table."""

    def __init__(
        self,
        env: DisasterResponseParallelEnv,
        config: dict[str, Any] | str | Path | None = None,
    ) -> None:
        self.env = env
        root = Path(__file__).resolve().parents[3]
        self.config = (
            load_config(root / "configs/network.yaml")
            if config is None
            else load_config(config)
            if isinstance(config, (str, Path))
            else dict(config)
        )
        self.maps: dict[str, AgentTopologicalMap] = {}
        self.local_goals: dict[str, tuple[int, int]] = {}
        self.events: list[dict[str, Any]] = []
        self.observations: dict[str, dict[str, np.ndarray]] = {}
        self.duplicate_goal_steps = 0

    def reset(self, seed: int):
        self.observations, _ = self.env.reset(seed=seed)
        self.maps = {agent: AgentTopologicalMap(agent) for agent in self.env.agents}
        self.local_goals = {}
        self.events = [{"step": 0, "event": "decentralized_reset", "seed": seed}]
        self.duplicate_goal_steps = 0
        self._update_maps(force=True)
        return self.observations

    def _update_maps(self, *, force: bool = False) -> None:
        step = self.env.core.step_count
        interval = int(self.config["topology_update_interval"])
        if not force and step % interval:
            return
        for agent in self.env.agents:
            robot = self.env._robots_by_name[agent]
            robot_config = self.env.core.robot_configs[robot.type]
            self.maps[agent].update(
                robot.belief,
                self.env._candidate_list(agent),
                step,
                robot.odom_uncertainty,
                can_cross_rubble=bool(robot_config["can_cross_rubble"]),
            )

    def _peer_evidence_positions(self, agent: str) -> list[tuple[int, int]]:
        if self.env.network is None:
            return []
        threshold = float(self.config["peer_evidence_threshold"])
        positions = []
        for message in self.env.network.peer_messages(agent, self.env.core.step_count):
            evidence = message.payload.get("evidence", {})
            position = evidence.get("position")
            if position is not None and float(evidence.get("thermal", 0.0)) >= threshold:
                positions.append((int(position[0]), int(position[1])))
        return positions

    def _active_participants(self, agent: str) -> tuple[str, ...]:
        if self.env.network is None:
            return (agent,)
        peers = {
            message.sender_id
            for message in self.env.network.peer_messages(
                agent, self.env.core.step_count
            )
        }
        return tuple(sorted(peers | {agent}))

    @staticmethod
    def _branch_owner(
        position: tuple[int, int], participants: tuple[str, ...]
    ) -> str:
        x, y = position
        # Coarse spatial keys keep ownership stable as a frontier advances by a
        # few cells. Rendezvous hashing changes only branches owned by a peer
        # that joins or disappears.
        key = f"{x // 8}:{y // 8}"
        return max(
            participants,
            key=lambda name: hashlib.blake2s(
                f"{key}:{name}".encode("utf-8"), digest_size=8
            ).digest(),
        )

    def _release_goal(self, agent: str) -> None:
        self.local_goals.pop(agent, None)
        self.env.set_active_goal(agent, None)

    def _should_investigate(self, agent: str) -> bool:
        thermal = float(self.observations[agent]["thermal"].max())
        acoustic = float(self.observations[agent]["acoustic"][0])
        return thermal >= float(self.config["thermal_investigate_threshold"]) or (
            thermal >= float(self.config["thermal_corroboration_threshold"])
            and acoustic >= float(self.config["acoustic_interest_threshold"])
        )

    def _choose_agent_action(self, agent: str) -> int:
        robot = self.env._robots_by_name[agent]
        thermal = float(self.observations[agent]["thermal"].max())
        if self._should_investigate(agent):
            self._release_goal(agent)
            self.events.append(
                {
                    "step": self.env.core.step_count,
                    "event": "local_investigate",
                    "agent": agent,
                    "thermal": thermal,
                }
            )
            return INVESTIGATE

        candidates = self.env._candidate_list(agent)
        by_position = {
            tuple(candidate["position"]): (slot, candidate)
            for slot, candidate in enumerate(candidates)
        }
        goal = self.local_goals.get(agent)
        claims_by_sender = self.env.peer_claims_by_sender(agent)
        if goal in by_position:
            lower_priority_claim = any(
                peer_goal == goal and sender < agent
                for sender, peer_goal in claims_by_sender.items()
            )
            if not lower_priority_claim:
                return by_position[goal][0]
        self._release_goal(agent)
        if not candidates:
            return HOLD

        peer_claims = set(claims_by_sender.values())
        separation = int(self.config["goal_separation_cells"])
        available = [
            (slot, candidate)
            for slot, candidate in enumerate(candidates)
            if all(
                abs(candidate["position"][0] - claim[0])
                + abs(candidate["position"][1] - claim[1])
                > separation
                for claim in peer_claims
            )
        ]
        if not available:
            available = [
                (slot, candidate)
                for slot, candidate in enumerate(candidates)
                if tuple(candidate["position"]) not in peer_claims
            ]
        if not available:
            return HOLD
        peer_evidence = self._peer_evidence_positions(agent)
        acoustic = float(self.observations[agent]["acoustic"][0])

        def score(item):
            _, candidate = item
            evidence_distance = (
                min(
                    abs(candidate["position"][0] - point[0])
                    + abs(candidate["position"][1] - point[1])
                    for point in peer_evidence
                )
                if peer_evidence
                else 0
            )
            return (
                evidence_distance if peer_evidence else 0,
                candidate["distance"]
                - (0.15 if acoustic >= float(self.config["acoustic_interest_threshold"]) else 0.05)
                * candidate["cluster_size"],
                candidate["distance"],
                candidate["position"],
            )

        ranked = sorted(available, key=score)
        if peer_evidence:
            slot, candidate = ranked[0]
        else:
            participants = self._active_participants(agent)
            owned = [
                item
                for item in ranked
                if self._branch_owner(tuple(item[1]["position"]), participants)
                == agent
            ]
            if owned:
                slot, candidate = owned[0]
            else:
                slot, candidate = ranked[robot.id % len(ranked)]
        goal = tuple(candidate["position"])
        self.local_goals[agent] = goal
        self.env.set_active_goal(agent, goal)
        candidates = self.env._candidate_list(agent)
        slot = next(
            index
            for index, item in enumerate(candidates)
            if tuple(item["position"]) == goal
        )
        self.events.append(
            {
                "step": self.env.core.step_count,
                "event": "local_goal_selected",
                "agent": agent,
                "goal": goal,
                "peer_claims_seen": len(peer_claims),
            }
        )
        return slot

    def choose_actions(self) -> dict[str, int]:
        self._update_maps()
        actions = {
            agent: self._choose_agent_action(agent) for agent in self.env.agents
        }
        goals = list(self.local_goals.values())
        if len(goals) != len(set(goals)):
            self.duplicate_goal_steps += 1
        return actions

    def step(self):
        result = self.env.step(self.choose_actions())
        self.observations = result[0]
        return result

    def run_episode(self, seed: int, output_dir: str | Path | None = None):
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
        return {
            "seed": self.env.core.seed,
            "steps": self.env.core.step_count,
            "survivors_total": len(self.env.core.victims),
            "survivors_found": metrics["victims_found"],
            "coverage": metrics["coverage"],
            "collisions": metrics["collisions"],
            "duplicate_goal_steps": self.duplicate_goal_steps,
            "network": self.env.network_metrics(),
            "graphs": {
                agent: {
                    "nodes": graph.graph.number_of_nodes(),
                    "edges": graph.graph.number_of_edges(),
                    "kinds": graph.node_kind_counts(),
                }
                for agent, graph in self.maps.items()
            },
        }

    def save(self, output_dir: str | Path, summary: dict[str, Any]) -> None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        self.env.save_episode(output / "episode")
        graph_dir = output / "topology"
        for agent, graph in self.maps.items():
            graph.save_json(graph_dir / f"{agent}.json")
        (output / "controller_events.json").write_text(
            json.dumps(self.events, indent=2), encoding="utf-8"
        )
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
