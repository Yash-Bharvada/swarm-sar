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


def initial_policy_state(module):
    """Create a single-batch recurrent state on the module's device."""
    if not module.is_stateful():
        return None
    device = next(module.parameters()).device
    return {
        branch: {
            name: tensor.unsqueeze(1).to(device)
            for name, tensor in values.items()
        }
        for branch, values in module.get_initial_state().items()
    }


def module_observation_size(module) -> int:
    space = module.observation_space
    if hasattr(space, "spaces") and "observations" in space.spaces:
        return int(space["observations"].shape[-1])
    return int(space.shape[-1])


def policy_step(
    module,
    observation: dict[str, np.ndarray],
    rng: np.random.Generator | None,
    state=None,
):
    """Select one action and advance optional recurrent state."""
    device = next(module.parameters()).device
    stateful = module.is_stateful()
    if stateful and state is None:
        state = initial_policy_state(module)
    prefix = (None, None) if stateful else (None,)
    action_mask = torch.as_tensor(
        observation["action_mask"][prefix], dtype=torch.float32, device=device
    )
    vector = observation["observations"]
    expected_size = module_observation_size(module)
    if vector.shape[-1] < expected_size:
        raise ValueError(
            f"Policy expects {expected_size} values, observation has {vector.shape[-1]}"
        )
    # GPU-v1 only appends fields to the frozen Step 3 prefix. Truncation keeps
    # the immutable 129-value checkpoint executable without changing its model.
    vector = vector[..., :expected_size]
    observations = torch.as_tensor(vector[prefix], dtype=torch.float32, device=device)
    batch = {
        Columns.OBS: {
            "action_mask": action_mask,
            "observations": observations,
        }
    }
    if stateful:
        batch[Columns.STATE_IN] = state
    with torch.no_grad():
        output = module.forward_inference(batch)
    logits = output[Columns.ACTION_DIST_INPUTS]
    logits = logits[0, -1] if logits.ndim == 3 else logits[0]
    if rng is None:
        action = int(torch.argmax(logits).item())
    else:
        probabilities = torch.softmax(logits, dim=-1).cpu().numpy()
        action = int(rng.choice(len(probabilities), p=probabilities))
    if observation["action_mask"][action] <= 0:
        raise AssertionError(f"Masked policy selected invalid action {action}")
    next_state = output.get(Columns.STATE_OUT) if stateful else None
    return action, next_state


def policy_action(
    module,
    observation: dict[str, np.ndarray],
    rng: np.random.Generator | None,
) -> int:
    action, _ = policy_step(module, observation, rng, state=None)
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
        states = {
            agent: initial_policy_state(modules[policy_mapping_fn(agent)])
            for agent in env.agents
        }
        while env.agents:
            actions = {}
            for agent, observation in observations.items():
                if agent not in env.agents:
                    continue
                action, next_state = policy_step(
                    modules[policy_mapping_fn(agent)],
                    observation,
                    rng if stochastic else None,
                    states.get(agent),
                )
                actions[agent] = action
                states[agent] = next_state
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
