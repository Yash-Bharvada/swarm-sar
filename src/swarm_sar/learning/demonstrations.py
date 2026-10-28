"""Chunked expert-demonstration collection and validation utilities."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from swarm_sar.baselines.decentralized import DecentralizedFrontierController
from swarm_sar.learning.observation import wrap_observation
from swarm_sar.policy_contract import ENCODED_OBSERVATION_SIZE, policy_contract
from swarm_sar.sim.env import ACTION_COUNT, DisasterResponseParallelEnv
from swarm_sar.utils.config import load_config


POLICY_IDS = {"rover": 0, "drone": 1}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expert_case(seed: int) -> tuple[dict, dict, dict, dict, dict[str, Any]]:
    """Build a deterministic, moderately sized domain-randomized training case."""
    root = Path(__file__).resolve().parents[3]
    world = copy.deepcopy(load_config(root / "configs/world.yaml"))
    robots = copy.deepcopy(load_config(root / "configs/robots.yaml"))
    sim = copy.deepcopy(load_config(root / "configs/sim.yaml"))
    controller = copy.deepcopy(load_config(root / "configs/network.yaml"))
    rng = np.random.default_rng(int(seed) ^ 0x455850455254)
    size = (24, 28, 32, 40, 48)[seed % 5]
    agent_count = int(rng.integers(2, 9))
    rover_count = int(rng.integers(1, agent_count))
    drone_count = agent_count - rover_count
    packet_loss = (0.0, 0.1, 0.3)[seed % 3]
    max_steps = max(300, int(round(400 * (size * size / 1024) * (4 / agent_count))))
    world.update(
        width=size,
        height=size,
        footprint="procedural" if size >= 40 else "full",
        victim_min_dist_from_spawn=max(6, size // 4),
        num_victims=[1, 4],
        max_generation_retries=100,
        min_free_ratio=0.14 if size >= 40 else world["min_free_ratio"],
    )
    sim.update(
        agent_counts={"rover": rover_count, "drone": drone_count},
        max_steps=max_steps,
        frontier_samples_per_cluster=5,
        investigate_confirms_victims=True,
        network_enabled=True,
        network_packet_loss=packet_loss,
        network_delay_steps=[1, 4],
        network_partition_windows=(
            [{"start": 20, "end": 60, "agents": ["rover_0"]}]
            if seed % 4 == 0
            else []
        ),
    )
    for config in robots.values():
        config["battery"] = max(float(config["battery"]), max_steps * 1.15)
    controller["max_steps"] = max_steps
    metadata = {
        "seed": int(seed),
        "size": size,
        "rovers": rover_count,
        "drones": drone_count,
        "packet_loss": packet_loss,
        "partitioned": bool(sim["network_partition_windows"]),
        "max_steps": max_steps,
    }
    return world, robots, sim, controller, metadata


@dataclass
class DemonstrationWriter:
    output: Path
    chunk_size: int = 50_000
    _rows: dict[str, list] = field(default_factory=dict)
    chunks: list[dict[str, Any]] = field(default_factory=list)
    total_rows: int = 0
    action_counts: dict[str, int] = field(default_factory=dict)
    policy_counts: dict[str, int] = field(
        default_factory=lambda: {"rover": 0, "drone": 0}
    )

    def __post_init__(self) -> None:
        self.output = self.output.resolve()
        if self.output.exists() and any(self.output.iterdir()):
            raise FileExistsError(f"Refusing to overwrite dataset: {self.output}")
        self.output.mkdir(parents=True, exist_ok=True)
        self._rows = {
            "observations": [],
            "action_masks": [],
            "actions": [],
            "policy_ids": [],
            "episode_seeds": [],
            "steps": [],
            "agent_indices": [],
            "packet_loss": [],
            "team_sizes": [],
        }

    def add(
        self,
        *,
        observation: dict[str, np.ndarray],
        action: int,
        robot_type: str,
        seed: int,
        step: int,
        agent_index: int,
        packet_loss: float,
        team_size: int,
    ) -> None:
        wrapped = wrap_observation(observation)
        vector = wrapped["observations"]
        mask = wrapped["action_mask"]
        if vector.shape != (ENCODED_OBSERVATION_SIZE,) or not np.all(np.isfinite(vector)):
            raise ValueError("Expert observation is invalid")
        if not 0 <= int(action) < ACTION_COUNT or mask[int(action)] <= 0:
            raise ValueError(f"Expert selected masked action {action}")
        if robot_type not in POLICY_IDS:
            raise ValueError(f"Unknown expert robot type: {robot_type}")
        self._rows["observations"].append(vector.astype(np.float32, copy=False))
        self._rows["action_masks"].append(mask.astype(np.uint8, copy=False))
        self._rows["actions"].append(int(action))
        self._rows["policy_ids"].append(POLICY_IDS[robot_type])
        self._rows["episode_seeds"].append(int(seed))
        self._rows["steps"].append(int(step))
        self._rows["agent_indices"].append(int(agent_index))
        self._rows["packet_loss"].append(float(packet_loss))
        self._rows["team_sizes"].append(int(team_size))
        self.action_counts[str(int(action))] = self.action_counts.get(str(int(action)), 0) + 1
        self.policy_counts[robot_type] = self.policy_counts.get(robot_type, 0) + 1
        if len(self._rows["actions"]) >= self.chunk_size:
            self.flush()

    def flush(self) -> None:
        rows = len(self._rows["actions"])
        if not rows:
            return
        path = self.output / f"chunk_{len(self.chunks):05d}.npz"
        np.savez_compressed(
            path,
            observations=np.stack(self._rows["observations"]).astype(np.float32),
            action_masks=np.stack(self._rows["action_masks"]).astype(np.uint8),
            actions=np.asarray(self._rows["actions"], dtype=np.int8),
            policy_ids=np.asarray(self._rows["policy_ids"], dtype=np.int8),
            episode_seeds=np.asarray(self._rows["episode_seeds"], dtype=np.int32),
            steps=np.asarray(self._rows["steps"], dtype=np.int32),
            agent_indices=np.asarray(self._rows["agent_indices"], dtype=np.int16),
            packet_loss=np.asarray(self._rows["packet_loss"], dtype=np.float32),
            team_sizes=np.asarray(self._rows["team_sizes"], dtype=np.int16),
        )
        self.chunks.append(
            {
                "path": path.name,
                "rows": rows,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
        self.total_rows += rows
        for values in self._rows.values():
            values.clear()

    def finish(self, episodes: list[dict[str, Any]]) -> dict[str, Any]:
        self.flush()
        manifest = {
            "schema_version": 1,
            "policy_contract": policy_contract(),
            "rows": self.total_rows,
            "episodes": episodes,
            "episode_count": len(episodes),
            "survivors_found": sum(item["survivors_found"] for item in episodes),
            "survivors_total": sum(item["survivors_total"] for item in episodes),
            "action_counts": self.action_counts,
            "policy_counts": self.policy_counts,
            "chunks": self.chunks,
        }
        (self.output / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        return manifest


def validate_dataset(path: str | Path) -> dict[str, Any]:
    root = Path(path).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["policy_contract"] != policy_contract():
        raise ValueError("Dataset policy contract does not match executable contract")
    rows = 0
    action_counts: dict[str, int] = {}
    policy_counts = {"rover": 0, "drone": 0}
    for chunk in manifest["chunks"]:
        chunk_path = root / chunk["path"]
        if sha256_file(chunk_path) != chunk["sha256"]:
            raise ValueError(f"Corrupt demonstration chunk: {chunk_path.name}")
        with np.load(chunk_path) as data:
            count = len(data["actions"])
            if data["observations"].shape != (count, ENCODED_OBSERVATION_SIZE):
                raise ValueError("Invalid demonstration observation shape")
            if data["action_masks"].shape != (count, ACTION_COUNT):
                raise ValueError("Invalid demonstration action-mask shape")
            if not np.all(np.isfinite(data["observations"])):
                raise ValueError("Non-finite demonstration observation")
            actions = data["actions"].astype(int)
            masks = data["action_masks"]
            if np.any(actions < 0) or np.any(actions >= ACTION_COUNT):
                raise ValueError("Out-of-range expert action")
            if np.any(masks[np.arange(count), actions] <= 0):
                raise ValueError("Dataset contains masked expert action")
            if np.any((data["policy_ids"] < 0) | (data["policy_ids"] > 1)):
                raise ValueError("Invalid policy ID")
            for action in actions:
                key = str(int(action))
                action_counts[key] = action_counts.get(key, 0) + 1
            policy_counts["rover"] += int(np.sum(data["policy_ids"] == 0))
            policy_counts["drone"] += int(np.sum(data["policy_ids"] == 1))
            rows += count
        if count != int(chunk["rows"]):
            raise ValueError("Chunk row count differs from manifest")
    if rows != int(manifest["rows"]):
        raise ValueError("Dataset row count differs from manifest")
    if action_counts != manifest["action_counts"]:
        raise ValueError("Dataset action counts differ from manifest")
    if policy_counts != manifest["policy_counts"]:
        raise ValueError("Dataset policy counts differ from manifest")
    return manifest


def dataset_summary(
    path: str | Path,
    *,
    display_path: str | None = None,
) -> dict[str, Any]:
    root = Path(path).resolve()
    manifest = validate_dataset(root)
    seeds = [int(item["seed"]) for item in manifest["episodes"]]
    total = int(manifest["survivors_total"])
    found = int(manifest["survivors_found"])
    return {
        "dataset_path": display_path or str(root),
        "manifest_sha256": sha256_file(root / "manifest.json"),
        "policy_contract_sha256": manifest["policy_contract"]["sha256"],
        "episode_seed_range": [min(seeds), max(seeds)],
        "episode_count": int(manifest["episode_count"]),
        "rows": int(manifest["rows"]),
        "chunks": len(manifest["chunks"]),
        "compressed_chunk_bytes": sum(
            int(chunk["bytes"]) for chunk in manifest["chunks"]
        ),
        "survivors_found": found,
        "survivors_total": total,
        "survivor_recall": found / max(1, total),
        "action_counts": manifest["action_counts"],
        "policy_counts": manifest["policy_counts"],
        "validation": "passed",
    }


def collect_episode(seed: int, writer: DemonstrationWriter) -> dict[str, Any]:
    world, robots, sim, controller_config, metadata = expert_case(seed)
    env = DisasterResponseParallelEnv(
        world_config=world, robot_config=robots, sim_config=sim
    )
    controller = DecentralizedFrontierController(env, controller_config)
    controller.reset(seed)
    try:
        while env.agents and env.core.step_count < int(controller_config["max_steps"]):
            acting_agents = list(env.agents)
            actions = controller.choose_actions()
            for agent_index, agent in enumerate(acting_agents):
                writer.add(
                    observation=controller.observations[agent],
                    action=actions[agent],
                    robot_type=env._robots_by_name[agent].type,
                    seed=seed,
                    step=env.core.step_count,
                    agent_index=agent_index,
                    packet_loss=metadata["packet_loss"],
                    team_size=len(acting_agents),
                )
            result = env.step(actions)
            controller.observations = result[0]
        summary = controller.summary()
        return {
            **metadata,
            "steps": summary["steps"],
            "survivors_found": summary["survivors_found"],
            "survivors_total": summary["survivors_total"],
            "coverage": summary["coverage"],
        }
    finally:
        env.close()
