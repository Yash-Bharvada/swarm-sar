import numpy as np

from swarm_sar.learning.cohort_evaluation import aggregate_rows, evaluation_seeds
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
