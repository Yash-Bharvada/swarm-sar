"""RLlib PPO construction and checkpoint utilities for Step 3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ray.rllib.algorithms.ppo import PPOConfig
from ray.rllib.core.rl_module.multi_rl_module import MultiRLModuleSpec
from ray.rllib.core.rl_module.rl_module import RLModuleSpec
from ray.rllib.policy.policy import PolicySpec
from ray.tune.registry import register_env

from swarm_sar.learning.env import VariableSwarmRLlibEnv
from swarm_sar.learning.rllib_module import SwarmActionMaskingTorchRLModule
from swarm_sar.utils.config import load_config
from swarm_sar.validation.seeds import load_seed_splits

ENV_NAME = "swarm_sar_step3_v0"
ROVER_POLICY = "rover_policy"
DRONE_POLICY = "drone_policy"


def policy_mapping_fn(agent_id: str, *args, **kwargs) -> str:
    del args, kwargs
    if agent_id.startswith("rover_"):
        return ROVER_POLICY
    if agent_id.startswith("drone_"):
        return DRONE_POLICY
    raise ValueError(f"Unknown swarm agent id: {agent_id}")


def register_swarm_env() -> None:
    def creator(context):
        config = dict(context)
        config["worker_index"] = int(getattr(context, "worker_index", 0))
        return VariableSwarmRLlibEnv(config)

    register_env(ENV_NAME, creator)


def training_config(path: str | Path | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4]
    return load_config(path or root / "training/configs/training.yaml")


def rllib_env_config(config: dict[str, Any], **overrides) -> dict[str, Any]:
    splits = load_seed_splits(config.get("seed_splits_path"))
    # Ray reserves worker index 0 for the local runner and numbers remote
    # runners from 1, so the seed schedule must admit N + 1 distinct slots.
    runner_count = max(1, int(config.get("num_env_runners", 0)) + 1)
    result = {
        "seed": int(config["seed"]),
        "max_steps": int(config["max_steps"]),
        "world_sizes": list(config["world_sizes"]),
        "curriculum": bool(config.get("curriculum", True)),
        "domain_randomization": bool(config.get("domain_randomization", False)),
        "randomization_seed": int(config["seed"]),
        "training_episode_offset": int(config.get("training_episode_offset", 0)),
        "curriculum_phase_episodes": list(config["curriculum_phase_episodes"]),
        "final_team_profiles": list(config["final_team_profiles"]),
        "network_enabled": bool(config["network_enabled"]),
        "survivor_reward": float(config["survivor_reward"]),
        "new_cell_reward": float(config["new_cell_reward"]),
        "investigate_evidence_reward": float(config["investigate_evidence_reward"]),
        "training_seed_range": [splits["train"].start, splits["train"].stop],
        "runner_count": runner_count,
    }
    result.update(overrides)
    return result


def build_ppo_config(config: dict[str, Any] | None = None) -> PPOConfig:
    config = dict(config or training_config())
    register_swarm_env()
    env_config = rllib_env_config(config)
    probe = VariableSwarmRLlibEnv(env_config)
    observation_space = probe.observation_space
    action_space = probe.action_space
    probe.close()
    model_config = {
        "fcnet_hiddens": list(config["hidden_layers"]),
        "fcnet_activation": "relu",
        "head_fcnet_hiddens": [],
        "vf_share_layers": False,
        "use_lstm": bool(config.get("use_lstm", False)),
        "lstm_cell_size": int(config.get("lstm_cell_size", 256)),
        "max_seq_len": int(config.get("max_seq_len", 32)),
    }
    module_specs = {
        policy_id: RLModuleSpec(
            module_class=SwarmActionMaskingTorchRLModule,
            observation_space=observation_space,
            action_space=action_space,
            model_config=model_config,
        )
        for policy_id in (ROVER_POLICY, DRONE_POLICY)
    }
    policy_specs = {
        policy_id: PolicySpec(
            observation_space=observation_space,
            action_space=action_space,
        )
        for policy_id in (ROVER_POLICY, DRONE_POLICY)
    }
    return (
        PPOConfig()
        .environment(ENV_NAME, env_config=env_config, disable_env_checking=False)
        .framework("torch")
        .env_runners(
            num_env_runners=int(config.get("num_env_runners", 0)),
            num_cpus_per_env_runner=float(config.get("num_cpus_per_env_runner", 1)),
            rollout_fragment_length=int(config["rollout_fragment_length"]),
            batch_mode="truncate_episodes",
        )
        .learners(
            num_learners=0,
            num_gpus_per_learner=float(config.get("num_gpus_per_learner", 0)),
        )
        .training(
            lr=float(config["learning_rate"]),
            gamma=float(config["gamma"]),
            lambda_=float(config["gae_lambda"]),
            clip_param=float(config["clip_param"]),
            entropy_coeff=float(config["entropy_coeff"]),
            train_batch_size_per_learner=int(config["train_batch_size_per_learner"]),
            minibatch_size=int(config["minibatch_size"]),
            num_epochs=int(config["num_epochs"]),
        )
        .multi_agent(
            policies=policy_specs,
            policy_mapping_fn=policy_mapping_fn,
            policies_to_train=[ROVER_POLICY, DRONE_POLICY],
            count_steps_by="env_steps",
        )
        .rl_module(
            rl_module_spec=MultiRLModuleSpec(rl_module_specs=module_specs),
        )
        .debugging(seed=int(config["seed"]))
    )
