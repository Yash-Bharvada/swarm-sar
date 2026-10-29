import numpy as np

from swarm_sar.learning.env import VariableSwarmRLlibEnv
from swarm_sar.learning.training import rllib_env_config, training_config


def gpu_env():
    config = training_config("training/configs/training_gpu_a5000.yaml")
    return VariableSwarmRLlibEnv(rllib_env_config(config))


def test_gpu_uses_both_robot_types_from_first_episode_and_excludes_ppo_holdout():
    env = gpu_env()
    for seed in range(40):
        profile = env._select_profile(seed)
        assert profile["rover"] > 0 and profile["drone"] > 0
        assert profile != {"rover": 1, "drone": 4}
        assert profile != {"rover": 2, "drone": 3}


def test_domain_choices_are_seed_keyed_reproducible_and_varied():
    env = gpu_env()
    worlds, losses, noises = [], [], []
    for seed in range(40):
        world, robots, sim = env._episode_configs({"rover": 2, "drone": 2}, seed)
        worlds.append((world["width"], world["layout"], world["footprint"], tuple(world["spawn_origin"])))
        losses.append(sim["network_packet_loss"])
        noises.append(robots["rover"]["thermal_noise"])
        assert world["width"] < 56
        assert world["footprint"] != "tunnel"
        if world["layout"] == "maze":
            assert world["width"] <= 32
    assert len(set(worlds)) > 10
    assert set(losses) == {0.0, 0.1, 0.3}
    assert np.std(noises) > 0.001
    assert any(world[1] == "maze" for world in worlds)
    first = env._episode_configs({"rover": 2, "drone": 2}, 17)
    env.episode_index = 999
    assert env._episode_configs({"rover": 2, "drone": 2}, 17) == first


def test_declared_ppo_team_holdouts_are_absent_from_training_profiles():
    config = training_config("training/configs/training_gpu_a5000.yaml")
    for profile in config["held_out_team_profiles"]:
        assert profile not in config["final_team_profiles"]


def test_resume_keeps_next_training_seed_and_ignores_rllib_initial_seed():
    env = gpu_env()
    env.restore_schedule({"worker_index": 0, "episode_index": 17})
    _, infos = env.reset(seed=42)
    assert env.current_seed == 17 * env.runner_count
    assert env.schedule_state()["episode_index"] == 18
    env.close()
