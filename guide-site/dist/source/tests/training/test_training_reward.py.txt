import numpy as np
import pytest

from swarm_sar.learning.env import VariableSwarmRLlibEnv
from swarm_sar.learning.training import training_config
from swarm_sar.sim.env import HOLD
from swarm_sar.world.cells import UNKNOWN


def reward_env():
    return VariableSwarmRLlibEnv({
        "fixed_team_profile": {"rover": 2, "drone": 2},
        "curriculum": False, "world_sizes": [24], "max_steps": 8,
        "network_enabled": False, "survivor_reward": 0.0,
        "new_cell_reward": 1.0, "investigate_evidence_reward": 0.0,
    })


def test_coverage_reward_counts_union_once_and_ignores_inflated_per_robot_counts(monkeypatch):
    env = reward_env()
    env.reset(seed=12)
    before = env._team_known_mask.copy()
    per_robot_known = sum(np.count_nonzero(robot.belief != UNKNOWN) for robot in env.env.core.robots)
    assert per_robot_known > np.count_nonzero(before)  # The spawn views overlap.
    raw_step = env.env.step
    def inflated_step(actions):
        result = raw_step(actions)
        for info in result[-1].values():
            info["newly_revealed"] = 1000000
        return result
    monkeypatch.setattr(env.env, "step", inflated_step)
    _, rewards, _, _, infos = env.step({agent: HOLD for agent in env.agents})
    unique_new = int(np.count_nonzero(env._known_cell_union() & ~before))
    collisions = sum(robot.collided for robot in env.env.core.robots)
    expected = float(unique_new - collisions - 0.01)
    assert all(value == pytest.approx(expected) for value in rewards.values())
    assert all(info["team_newly_revealed"] == unique_new for info in infos.values())
    assert unique_new == 0
    env.close()


def test_gpu_reward_disables_repeat_thermal_cue_bonus():
    config = training_config("training/configs/training_gpu_a5000.yaml")
    assert config["investigate_evidence_reward"] == 0.0
