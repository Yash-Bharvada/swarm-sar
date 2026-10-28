"""Paired closed-loop reference controllers for the learned-policy evaluator."""

from __future__ import annotations

from typing import Any

import numpy as np

from swarm_sar.learning.demonstrations import PolicyCompatibleExpert
from swarm_sar.learning.env import VariableSwarmRLlibEnv
from swarm_sar.learning.training import policy_mapping_fn
from swarm_sar.sim.env import ACTION_COUNT


def evaluate_reference(
    name: str,
    *,
    seeds: list[int],
    team_profile: dict[str, int],
    network_enabled: bool,
    max_steps: int,
    world_size: int,
    sim_overrides: dict[str, Any] | None = None,
    robot_stress: dict[str, Any] | None = None,
    world_overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run each reference on the exact same initial cases as the learned actor.

    `mask_only` always chooses the first legal action; it deliberately has no
    neural network or sensor reasoning. `random` samples legal actions uniformly.
    `expert` uses the dataset's policy-compatible Step 4 teacher. It cannot
    cancel simulator goals or reorder action slots through privileged calls.
    """
    if name not in {"expert", "random", "mask_only"}:
        raise ValueError(f"Unknown reference controller: {name}")
    rows = []
    for seed in seeds:
        adapter = VariableSwarmRLlibEnv({
            "seed": seed,
            "curriculum": False,
            "fixed_team_profile": team_profile,
            "final_team_profiles": [team_profile],
            "world_sizes": [world_size],
            "max_steps": max_steps,
            "network_enabled": network_enabled,
            "sim_overrides": sim_overrides or {},
            "robot_stress": robot_stress or {},
            "world_overrides": world_overrides or {},
        })
        try:
            adapter.reset(seed=seed)
            env = adapter.env
            assert env is not None
            controller = PolicyCompatibleExpert(env) if name == "expert" else None
            observations = controller.reset(seed) if controller else {
                agent: env.observe(agent) for agent in env.agents
            }
            rng = np.random.default_rng(seed ^ 0x524546)
            counts = {policy: np.zeros(ACTION_COUNT, dtype=np.int64) for policy in ("rover_policy", "drone_policy")}
            entropy_sums = {policy: 0.0 for policy in counts}
            invalid_actions = 0
            while env.agents:
                if controller is not None:
                    actions = controller.choose_actions()
                else:
                    actions = {}
                    for agent in env.agents:
                        legal = np.flatnonzero(observations[agent]["action_mask"])
                        actions[agent] = int(rng.choice(legal) if name == "random" else legal[0])
                        if name == "random":
                            entropy_sums[policy_mapping_fn(agent)] += float(np.log(len(legal)))
                for agent, action in actions.items():
                    counts[policy_mapping_fn(agent)][action] += 1
                observations, _, _, _, infos = env.step(actions)
                invalid_actions += sum(bool(info["invalid_action"]) for info in infos.values())
                if controller is not None:
                    controller.observations = observations
            metrics = env.core.metrics_snapshot()
            rows.append({
                "seed": seed,
                "reference": name,
                "network_enabled": network_enabled,
                "rover_count": int(team_profile.get("rover", 0)),
                "drone_count": int(team_profile.get("drone", 0)),
                "steps": int(metrics["step"]),
                "survivors_found": int(metrics["victims_found"]),
                "survivors_total": len(env.core.victims),
                "coverage": float(metrics["coverage"]),
                "collisions": int(metrics["collisions"]),
                "invalid_actions": invalid_actions,
                "time_to_all_victims": metrics["time_to_all_victims"],
                "action_counts": {policy: values.tolist() for policy, values in counts.items()},
                "mean_action_entropy": {
                    policy: entropy_sums[policy] / max(1, int(values.sum()))
                    for policy, values in counts.items()
                },
            })
        finally:
            adapter.close()
    return rows
