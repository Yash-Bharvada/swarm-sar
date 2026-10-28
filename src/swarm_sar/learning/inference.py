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
            name: tensor.unsqueeze(0).to(device)
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
    probabilities = torch.softmax(logits, dim=-1).cpu().numpy()
    if rng is None:
        action = int(torch.argmax(logits).item())
    else:
        action = int(rng.choice(len(probabilities), p=probabilities))
    if observation["action_mask"][action] <= 0:
        raise AssertionError(f"Masked policy selected invalid action {action}")
    next_state = output.get(Columns.STATE_OUT) if stateful else None
    return action, next_state


def policy_step_with_diagnostics(module, observation, rng, state=None):
    """Inference step plus policy entropy, used only by evaluation."""
    device = next(module.parameters()).device
    stateful = module.is_stateful()
    if stateful and state is None:
        state = initial_policy_state(module)
    prefix = (None, None) if stateful else (None,)
    vector = observation["observations"][..., : module_observation_size(module)]
    batch = {
        Columns.OBS: {
            "action_mask": torch.as_tensor(
                observation["action_mask"][prefix], dtype=torch.float32, device=device
            ),
            "observations": torch.as_tensor(
                vector[prefix], dtype=torch.float32, device=device
            ),
        }
    }
    if stateful:
        batch[Columns.STATE_IN] = state
    with torch.no_grad():
        output = module.forward_inference(batch)
    logits = output[Columns.ACTION_DIST_INPUTS]
    logits = logits[0, -1] if logits.ndim == 3 else logits[0]
    probabilities = torch.softmax(logits, dim=-1)
    action = int(
        torch.argmax(logits).item()
        if rng is None
        else rng.choice(len(probabilities), p=probabilities.cpu().numpy())
    )
    if observation["action_mask"][action] <= 0:
        raise AssertionError(f"Masked policy selected invalid action {action}")
    entropy = float(-(probabilities * probabilities.clamp_min(1e-12).log()).sum())
    return action, output.get(Columns.STATE_OUT) if stateful else None, entropy


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
    sim_overrides: dict[str, Any] | None = None,
    robot_stress: dict[str, Any] | None = None,
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
                "sim_overrides": sim_overrides or {},
                "robot_stress": robot_stress or {},
            }
        )
        observations, _ = env.reset(seed=seed)
        rng = np.random.default_rng(seed ^ 0x5033)
        states = {
            agent: initial_policy_state(modules[policy_mapping_fn(agent)])
            for agent in env.agents
        }
        action_counts = {
            "rover_policy": np.zeros(7, dtype=np.int64),
            "drone_policy": np.zeros(7, dtype=np.int64),
        }
        entropy_sums = {"rover_policy": 0.0, "drone_policy": 0.0}
        policy_steps = {"rover_policy": 0, "drone_policy": 0}
        while env.agents:
            actions = {}
            for agent, observation in observations.items():
                if agent not in env.agents:
                    continue
                policy_id = policy_mapping_fn(agent)
                action, next_state, entropy = policy_step_with_diagnostics(
                    modules[policy_id],
                    observation,
                    rng if stochastic else None,
                    states.get(agent),
                )
                actions[agent] = action
                states[agent] = next_state
                action_counts[policy_id][action] += 1
                entropy_sums[policy_id] += entropy
                policy_steps[policy_id] += 1
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
                "action_counts": {
                    policy: counts.tolist() for policy, counts in action_counts.items()
                },
                "mean_action_entropy": {
                    policy: entropy_sums[policy] / max(1, policy_steps[policy])
                    for policy in action_counts
                },
            }
        )
        env.close()
    return rows
