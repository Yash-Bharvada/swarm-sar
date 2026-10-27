"""Checkpoint inference and deterministic evaluation helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from ray.rllib.core.columns import Columns

from swarm_sar.learning.env import VariableSwarmRLlibEnv
from swarm_sar.learning.training import policy_mapping_fn


def deterministic_action(module, observation: dict[str, np.ndarray]) -> int:
    return policy_action(module, observation, rng=None)


def policy_action(
    module,
    observation: dict[str, np.ndarray],
    rng: np.random.Generator | None,
) -> int:
    batch = {
        Columns.OBS: {
            "action_mask": torch.as_tensor(
                observation["action_mask"][None, :], dtype=torch.float32
            ),
            "observations": torch.as_tensor(
                observation["observations"][None, :], dtype=torch.float32
            ),
        }
    }
    with torch.no_grad():
        output = module.forward_inference(batch)
    logits = output[Columns.ACTION_DIST_INPUTS][0]
    if rng is None:
        action = int(torch.argmax(logits).item())
    else:
        probabilities = torch.softmax(logits, dim=-1).cpu().numpy()
        action = int(rng.choice(len(probabilities), p=probabilities))
    if observation["action_mask"][action] <= 0:
        raise AssertionError(f"Masked policy selected invalid action {action}")
    return action


def evaluate_modules(
    modules: dict[str, Any],
    *,
    seeds: list[int],
    team_profile: dict[str, int],
    network_enabled: bool,
    max_steps: int = 400,
    world_size: int = 32,
    stochastic: bool = True,
) -> list[dict[str, Any]]:
    rows = []
    for seed in seeds:
        env = VariableSwarmRLlibEnv(
            {
                "seed": seed,
                "fixed_team_profile": team_profile,
                "curriculum": False,
                "world_sizes": [world_size],
                "max_steps": max_steps,
                "network_enabled": network_enabled,
                "final_team_profiles": [team_profile],
            }
        )
        observations, _ = env.reset(seed=seed)
        rng = np.random.default_rng(seed ^ 0x5033)
        while env.agents:
            actions = {
                agent: policy_action(
                    modules[policy_mapping_fn(agent)],
                    observation,
                    rng if stochastic else None,
                )
                for agent, observation in observations.items()
                if agent in env.agents
            }
            observations, _, _, _, _ = env.step(actions)
        metrics = env.metrics_snapshot()
        rows.append(
            {
                "seed": seed,
                "network_enabled": network_enabled,
                "rover_count": int(team_profile.get("rover", 0)),
                "drone_count": int(team_profile.get("drone", 0)),
                "steps": int(metrics["step"]),
                "survivors_found": int(metrics["victims_found"]),
                "survivors_total": int(metrics["survivors_total"]),
                "coverage": float(metrics["coverage"]),
                "collisions": int(metrics["collisions"]),
                "invalid_actions": int(metrics["invalid_actions"]),
                "time_to_all_victims": metrics["time_to_all_victims"],
            }
        )
        env.close()
    return rows
