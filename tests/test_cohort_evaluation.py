import numpy as np
import pytest

from swarm_sar.learning.cohort_evaluation import (
    aggregate_rows, evaluation_seeds, evaluate_cohorts, paired_recall_difference,
    bootstrap_recall_interval,
)
from swarm_sar.learning.env import VariableSwarmRLlibEnv


def test_fixed_and_rotating_seeds_are_reproducible_and_disjoint():
    first = evaluation_seeds(split=range(100, 120), fixed_count=2, rotating_count=3, evaluation_index=0)
    second = evaluation_seeds(split=range(100, 120), fixed_count=2, rotating_count=3, evaluation_index=1)
    assert first == [100, 101, 102, 103, 104]
    assert second == [100, 101, 105, 106, 107]
    assert set(first[2:]).isdisjoint(second[2:])


def test_aggregate_exposes_recall_completion_and_action_collapse():
    row = {
        "survivors_total": 2, "survivors_found": 1, "coverage": 0.5,
        "steps": 100, "time_to_all_victims": None, "collisions": 1,
        "invalid_actions": 0,
        "action_counts": {"rover_policy": [9, 1, 0, 0, 0, 0, 0], "drone_policy": [1, 1, 1, 1, 1, 1, 1]},
        "mean_action_entropy": {"rover_policy": 0.2, "drone_policy": 1.0},
    }
    metrics = aggregate_rows([row])
    assert metrics["survivor_recall"] == 0.5
    assert metrics["completion_rate"] == 0.0
    assert metrics["dominant_action_ratio"]["rover_policy"] == 0.9
    assert np.isclose(sum(metrics["action_distribution"]["drone_policy"]), 1.0)


def test_network_and_sensor_stress_reach_underlying_simulator_configs():
    env = VariableSwarmRLlibEnv({
        "fixed_team_profile": {"rover": 1, "drone": 1},
        "curriculum": False,
        "sim_overrides": {"network_packet_loss": 0.3},
        "robot_stress": {"noise_multiplier": 2.0, "drift_multiplier": 3.0},
    })
    _, robots, sim = env._episode_configs({"rover": 1, "drone": 1})
    assert sim["network_packet_loss"] == 0.3
    assert robots["rover"]["thermal_noise"] == 0.1
    assert np.isclose(robots["drone"]["odometry_drift_std"], 0.15)


def test_final_evaluation_refuses_implicit_or_shortened_access():
    with pytest.raises(ValueError, match="sealed"):
        evaluate_cohorts({}, evaluation_index=0, seed_split="final")
    with pytest.raises(ValueError, match="shortened"):
        evaluate_cohorts({}, evaluation_index=0, seed_split="final", acknowledge_final=True, smoke=True)


def test_paired_comparison_rejects_mismatched_cases():
    left = [{"seed": 1, "survivors_found": 2, "survivors_total": 3}]
    right = [{"seed": 2, "survivors_found": 1, "survivors_total": 3}]
    with pytest.raises(ValueError, match="identical ordered seeds"):
        paired_recall_difference(left, right)
    right[0]["seed"] = 1
    comparison = paired_recall_difference(left, right)
    assert comparison["learned_minus_reference_recall"] == pytest.approx(1 / 3)
    assert comparison["episode_bootstrap_ci95"] == [-1.0, 1.0]


def test_single_episode_does_not_claim_narrow_confidence():
    assert bootstrap_recall_interval([{"survivors_found": 4, "survivors_total": 4}]) == [0.0, 1.0]


def test_fixed_and_shadow_metrics_are_separate(monkeypatch):
    import swarm_sar.learning.cohort_evaluation as evaluation

    definition = {"fixed_seed_count": 1, "rotating_seed_count": 1, "cohorts": [
        {"name": "nominal", "team_profile": {"rover": 1, "drone": 1}, "max_steps": 2, "world_size": 24}
    ]}
    monkeypatch.setattr(evaluation, "cohort_definition", lambda _: definition)

    def fake_modules(modules, **kwargs):
        return [{"seed": seed, "survivors_found": int(index == 0), "survivors_total": 1,
                 "coverage": 0.5, "steps": 2, "time_to_all_victims": None,
                 "collisions": 0, "invalid_actions": 0,
                 "action_counts": {"rover_policy": [1, 0, 0, 0, 0, 0, 0], "drone_policy": [1, 0, 0, 0, 0, 0, 0]},
                 "mean_action_entropy": {"rover_policy": 0.0, "drone_policy": 0.0}}
                for index, seed in enumerate(kwargs["seeds"])]

    monkeypatch.setattr(evaluation, "evaluate_modules", fake_modules)
    report = evaluate_cohorts({}, evaluation_index=0, include_train_probe=False)
    assert report["summary"]["fixed_mean_recall"] == 1.0
    assert report["summary"]["shadow_mean_recall"] == 0.0
    assert report["summary"]["fixed_shadow_gap"] == 1.0
    assert report["final_seeds_used"] is False


def test_domain_holdouts_are_absent_from_ppo_training_config():
    from swarm_sar.learning.cohort_evaluation import cohort_definition
    from swarm_sar.learning.training import training_config

    training = training_config("configs/training_gpu_a5000.yaml")
    cohorts = {cohort["name"]: cohort for cohort in cohort_definition()["cohorts"]}
    assert cohorts["ppo_unseen_team_1r4d"]["team_profile"] not in training["final_team_profiles"]
    assert cohorts["ood_maze_56"]["world_size"] not in training["world_sizes"]


def test_training_probe_reconstructs_actual_seed_keyed_training_cases(monkeypatch):
    from swarm_sar.learning import cohort_evaluation as evaluation
    from swarm_sar.learning.training import rllib_env_config, training_config
    from swarm_sar.learning.env import VariableSwarmRLlibEnv
    config = training_config("configs/training_gpu_a5000.yaml")
    observed = []

    def fake_evaluate(modules, *, seeds, **kwargs):
        assert modules == {}
        override = kwargs["env_config_overrides"]
        assert override["training_seed_range"] is None
        assert override["domain_randomization"] is True
        env = VariableSwarmRLlibEnv(override)
        expected = VariableSwarmRLlibEnv(rllib_env_config(config, training_seed_range=None))
        for seed in seeds:
            env.reset(seed=seed)
            expected.reset(seed=seed)
            assert env.current_profile == expected.current_profile
            assert env.env.core.world_config == expected.env.core.world_config
            assert env.env.core.robot_configs == expected.env.core.robot_configs
            observed.append(seed)
        env.close()
        expected.close()
        return [{"seed": seed, "survivors_found": 1, "survivors_total": 1,
                 "coverage": 0.5, "steps": 2, "time_to_all_victims": 2,
                 "collisions": 0, "invalid_actions": 0,
                 "action_counts": {"rover_policy": [1, 0, 0, 0, 0, 0, 0], "drone_policy": [1, 0, 0, 0, 0, 0, 0]},
                 "mean_action_entropy": {"rover_policy": 0.0, "drone_policy": 0.0}} for seed in seeds]

    monkeypatch.setattr(evaluation, "evaluate_modules", fake_evaluate)
    probe = evaluation.matched_training_probe({}, train_seeds=[0], development_seeds=[10000], config=config)
    assert observed == [0, 10000]
    assert probe["matched_development"]["metrics"]["survivor_recall"] == 1.0
