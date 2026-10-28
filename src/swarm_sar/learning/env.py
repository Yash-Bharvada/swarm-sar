"""RLlib adapter with curriculum and variable heterogeneous team sizes."""

import copy
from pathlib import Path
from typing import Any

from gymnasium import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv

from swarm_sar.learning.observation import policy_observation_space, wrap_observation
from swarm_sar.sim.env import ACTION_COUNT, DisasterResponseParallelEnv
from swarm_sar.utils.config import load_config
from swarm_sar.validation.seeds import scheduled_training_seed


def normalise_profile(profile: dict[str, Any]) -> dict[str, int]:
    result = {
        "rover": int(profile.get("rover", 0)),
        "drone": int(profile.get("drone", 0)),
    }
    if min(result.values()) < 0 or sum(result.values()) < 1:
        raise ValueError(f"Invalid team profile: {profile}")
    return result


class VariableSwarmRLlibEnv(MultiAgentEnv):
    """Select a team profile per episode while retaining fixed per-agent spaces."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__()
        config = dict(config or {})
        root = Path(__file__).resolve().parents[3]
        self.base_world = load_config(root / "configs/world.yaml")
        self.base_robots = load_config(root / "configs/robots.yaml")
        self.base_sim = load_config(root / "configs/sim.yaml")
        self.base_seed = int(config.get("seed", 42))
        seed_bounds = config.get("training_seed_range")
        self.training_seed_range = (
            range(int(seed_bounds[0]), int(seed_bounds[1])) if seed_bounds else None
        )
        self.worker_index = int(config.get("worker_index", 0))
        self.runner_count = int(config.get("runner_count", 1))
        self.max_steps = int(config.get("max_steps", 240))
        self.world_sizes = [int(size) for size in config.get("world_sizes", [24, 28, 32])]
        self.network_enabled = bool(config.get("network_enabled", True))
        self.sim_overrides = copy.deepcopy(config.get("sim_overrides", {}))
        self.robot_stress = copy.deepcopy(config.get("robot_stress", {}))
        self.survivor_reward = float(config.get("survivor_reward", 20.0))
        self.new_cell_reward = float(config.get("new_cell_reward", 0.05))
        self.investigate_evidence_reward = float(
            config.get("investigate_evidence_reward", 0.2)
        )
        self.curriculum = bool(config.get("curriculum", True))
        self.phase_episodes = [
            int(value) for value in config.get("curriculum_phase_episodes", [12, 12])
        ]
        if len(self.phase_episodes) != 2:
            raise ValueError("curriculum_phase_episodes must contain two counts")
        self.final_profiles = [
            normalise_profile(profile)
            for profile in config.get(
                "final_team_profiles",
                [{"rover": 2, "drone": 2}, {"rover": 3, "drone": 3}],
            )
        ]
        fixed = config.get("fixed_team_profile")
        self.fixed_profile = normalise_profile(fixed) if fixed else None
        known_profiles = self.final_profiles + [
            {"rover": 1, "drone": 0},
            {"rover": 2, "drone": 0},
        ]
        if self.fixed_profile:
            known_profiles.append(self.fixed_profile)
        self.possible_agents = sorted(
            {
                name
                for profile in known_profiles
                for name in self._names_for_profile(profile)
            }
        )
        self._agent_ids = set(self.possible_agents)
        self.agents: list[str] = []
        self.observation_space = policy_observation_space()
        self.action_space = spaces.Discrete(ACTION_COUNT)
        self.observation_spaces = {
            agent: self.observation_space for agent in self.possible_agents
        }
        self.action_spaces = {agent: self.action_space for agent in self.possible_agents}
        self.episode_index = 0
        self.current_profile: dict[str, int] | None = None
        self.current_seed = self.base_seed
        self.invalid_action_count = 0
        self.env: DisasterResponseParallelEnv | None = None

    @staticmethod
    def _names_for_profile(profile: dict[str, int]) -> list[str]:
        names = []
        identifier = 0
        for robot_type in ("rover", "drone"):
            for _ in range(int(profile.get(robot_type, 0))):
                names.append(f"{robot_type}_{identifier}")
                identifier += 1
        return names

    def _select_profile(self) -> dict[str, int]:
        if self.fixed_profile is not None:
            return dict(self.fixed_profile)
        if self.curriculum and self.episode_index < self.phase_episodes[0]:
            return {"rover": 1, "drone": 0}
        if self.curriculum and self.episode_index < sum(self.phase_episodes):
            return {"rover": 2, "drone": 0}
        offset = self.episode_index - sum(self.phase_episodes)
        return dict(self.final_profiles[offset % len(self.final_profiles)])

    def _episode_configs(self, profile: dict[str, int]):
        world = copy.deepcopy(self.base_world)
        robots = copy.deepcopy(self.base_robots)
        sim = copy.deepcopy(self.base_sim)
        size = self.world_sizes[self.episode_index % len(self.world_sizes)]
        world.update(
            width=size,
            height=size,
            victim_min_dist_from_spawn=max(6, size // 4),
        )
        sim.update(
            agent_counts=profile,
            max_steps=self.max_steps,
            network_enabled=self.network_enabled,
            investigate_confirms_victims=True,
            frontier_samples_per_cluster=5,
        )
        sim.update(self.sim_overrides)
        for robot_config in robots.values():
            robot_config["thermal_noise"] *= float(
                self.robot_stress.get("noise_multiplier", 1.0)
            )
            robot_config["acoustic_noise"] *= float(
                self.robot_stress.get("noise_multiplier", 1.0)
            )
            robot_config["thermal_detection_probability"] = max(
                0.0,
                robot_config["thermal_detection_probability"]
                - float(self.robot_stress.get("detection_probability_drop", 0.0)),
            )
            robot_config["acoustic_detection_probability"] = max(
                0.0,
                robot_config["acoustic_detection_probability"]
                - float(self.robot_stress.get("detection_probability_drop", 0.0)),
            )
            robot_config["thermal_false_positive_rate"] = min(
                1.0,
                robot_config["thermal_false_positive_rate"]
                + float(self.robot_stress.get("false_positive_increase", 0.0)),
            )
            robot_config["acoustic_false_positive_rate"] = min(
                1.0,
                robot_config["acoustic_false_positive_rate"]
                + float(self.robot_stress.get("false_positive_increase", 0.0)),
            )
            robot_config["odometry_drift_std"] *= float(
                self.robot_stress.get("drift_multiplier", 1.0)
            )
            robot_config["odometry_uncertainty_growth"] *= float(
                self.robot_stress.get("drift_multiplier", 1.0)
            )
        required = sum(profile.values())
        if required > int(world["spawn_size"]) ** 2:
            raise ValueError(
                f"Spawn has capacity {int(world['spawn_size']) ** 2}, requested {required}"
            )
        return world, robots, sim

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed, options=options)
        if options and "team_profile" in options:
            profile = normalise_profile(options["team_profile"])
        else:
            profile = self._select_profile()
        world, robots, sim = self._episode_configs(profile)
        if self.env is not None:
            self.env.close()
        self.env = DisasterResponseParallelEnv(
            world_config=world,
            robot_config=robots,
            sim_config=sim,
        )
        if seed is not None:
            episode_seed = int(seed)
        elif self.training_seed_range is not None:
            episode_seed = scheduled_training_seed(
                self.training_seed_range,
                worker_index=self.worker_index,
                runner_count=self.runner_count,
                episode_index=self.episode_index,
            )
        else:
            episode_seed = self.base_seed + self.episode_index
        observations, infos = self.env.reset(seed=episode_seed)
        self.current_seed = episode_seed
        self.current_profile = profile
        self.agents = list(self.env.agents)
        self.invalid_action_count = 0
        self.episode_index += 1
        for info in infos.values():
            info["team_profile"] = dict(profile)
            info["network_enabled"] = self.network_enabled
        return {
            agent: wrap_observation(observation)
            for agent, observation in observations.items()
        }, infos

    def step(self, action_dict: dict[str, int]):
        if self.env is None:
            raise RuntimeError("Call reset() before step()")
        observations, _, terminations, truncations, infos = self.env.step(action_dict)
        acted_agents = list(action_dict)
        for agent in acted_agents:
            if agent not in observations and (
                terminations.get(agent, False) or truncations.get(agent, False)
            ):
                observations[agent] = self.env.observe(agent)
        self.invalid_action_count += sum(
            bool(infos[agent]["invalid_action"]) for agent in acted_agents
        )
        newly_found = max(
            (int(infos[agent]["newly_found"]) for agent in acted_agents), default=0
        )
        newly_revealed = sum(
            int(infos[agent]["newly_revealed"]) for agent in acted_agents
        )
        collisions = sum(
            bool(self.env._robots_by_name[agent].collided) for agent in acted_agents
        )
        evidence = sum(
            float(self.env._robots_by_name[agent].thermal.max())
            for agent, action in action_dict.items()
            if int(action) == 5
        ) / max(1, len(acted_agents))
        team_reward = float(
            self.survivor_reward * newly_found
            + self.new_cell_reward * newly_revealed
            + self.investigate_evidence_reward * evidence
            - collisions
            - 0.01
        )
        rewards = {agent: team_reward for agent in acted_agents}
        for info in infos.values():
            info["team_reward"] = team_reward
            info["team_profile"] = dict(self.current_profile or {})
            info["network_enabled"] = self.network_enabled
        self.agents = list(self.env.agents)
        terminations["__all__"] = not self.agents and all(terminations.values())
        truncations["__all__"] = not self.agents and all(truncations.values())
        return (
            {
                agent: wrap_observation(observation)
                for agent, observation in observations.items()
            },
            rewards,
            terminations,
            truncations,
            infos,
        )

    def metrics_snapshot(self) -> dict[str, Any]:
        if self.env is None:
            raise RuntimeError("Call reset() first")
        metrics = self.env.core.metrics_snapshot()
        metrics.update(
            {
                "survivors_total": len(self.env.core.victims),
                "invalid_actions": self.invalid_action_count,
                "team_profile": dict(self.current_profile or {}),
                "network_enabled": self.network_enabled,
                "sim_overrides": copy.deepcopy(self.sim_overrides),
                "robot_stress": copy.deepcopy(self.robot_stress),
                "seed": self.current_seed,
            }
        )
        return metrics

    def close(self) -> None:
        if self.env is not None:
            self.env.close()
            self.env = None
