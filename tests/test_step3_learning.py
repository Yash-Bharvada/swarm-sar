import numpy as np

from swarm_sar.learning.env import VariableSwarmRLlibEnv
from swarm_sar.learning.observation import (
    ENCODED_OBSERVATION_SIZE,
    encode_observation,
    wrap_observation,
)
from swarm_sar.learning.training import (
    DRONE_POLICY,
    ROVER_POLICY,
    policy_mapping_fn,
)
from swarm_sar.sim.env import HOLD, INVESTIGATE, DisasterResponseParallelEnv
from swarm_sar.utils.config import load_config
from swarm_sar.world.cells import FREE


def test_policy_encoding_is_fixed_and_contains_no_truth():
    env = DisasterResponseParallelEnv()
    observations, _ = env.reset(seed=12)
    raw = observations[env.agents[0]]
    encoded = encode_observation(raw)
    wrapped = wrap_observation(raw)
    assert encoded.shape == (ENCODED_OBSERVATION_SIZE,)
    assert encoded.dtype == np.float32
    assert np.all(np.isfinite(encoded))
    assert np.min(encoded) >= -1 and np.max(encoded) <= 1
    assert set(wrapped) == {"action_mask", "observations"}
    assert not {"grid", "victims", "survivor_positions"}.intersection(raw)
    env.close()


def test_variable_team_env_supports_custom_and_held_out_team_sizes():
    for profile in ({"rover": 2, "drone": 3}, {"rover": 4, "drone": 4}):
        env = VariableSwarmRLlibEnv(
            {
                "fixed_team_profile": profile,
                "curriculum": False,
                "world_sizes": [24],
                "max_steps": 10,
                "final_team_profiles": [profile],
            }
        )
        observations, _ = env.reset(seed=21)
        assert len(env.agents) == sum(profile.values())
        assert {policy_mapping_fn(agent) for agent in env.agents} == {
            ROVER_POLICY,
            DRONE_POLICY,
        }
        assert all(env.observation_space.contains(obs) for obs in observations.values())
        env.close()


def test_curriculum_advances_from_one_rover_to_mixed_teams():
    env = VariableSwarmRLlibEnv(
        {
            "curriculum": True,
            "curriculum_phase_episodes": [1, 1],
            "final_team_profiles": [{"rover": 2, "drone": 2}],
            "world_sizes": [24],
            "max_steps": 5,
        }
    )
    env.reset(seed=1)
    assert env.current_profile == {"rover": 1, "drone": 0}
    env.reset(seed=2)
    assert env.current_profile == {"rover": 2, "drone": 0}
    env.reset(seed=3)
    assert env.current_profile == {"rover": 2, "drone": 2}
    env.close()


def test_network_toggle_changes_peer_summary_without_changing_shape():
    sim = load_config("configs/sim.yaml")
    sim["network_enabled"] = False
    off = DisasterResponseParallelEnv(sim_config=sim)
    off_observations, _ = off.reset(seed=8)
    assert all(np.all(obs["peer_summary"] == 0) for obs in off_observations.values())
    off.close()

    sim["network_enabled"] = True
    on = DisasterResponseParallelEnv(sim_config=sim)
    on_observations, _ = on.reset(seed=8)
    for _ in range(2):
        on_observations, _, _, _, _ = on.step(
            {agent: HOLD for agent in on.agents}
        )
    assert all(obs["peer_summary"].shape == (8,) for obs in on_observations.values())
    assert all(obs["peer_summary"][0] == 1 for obs in on_observations.values())
    assert any(obs["peer_summary"][1] > 0 for obs in on_observations.values())
    on.close()


def test_investigate_action_can_confirm_without_exposing_truth():
    sim = load_config("configs/sim.yaml")
    sim.update(
        agent_counts={"rover": 1, "drone": 0},
        investigate_confirms_victims=True,
    )
    env = DisasterResponseParallelEnv(sim_config=sim)
    observations, _ = env.reset(seed=3)
    robot = env.core.robots[0]
    victim = env.core.victims[0]
    robot.x, robot.y = victim["x"], victim["y"]
    robot.odom_x, robot.odom_y = float(robot.x), float(robot.y)
    robot.belief[robot.y, robot.x] = FREE
    robot.thermal[:] = 0
    _, rewards, _, _, infos = env.step({robot.name: INVESTIGATE})
    assert victim["found"]
    assert infos[robot.name]["newly_found"] >= 1
    assert rewards[robot.name] >= 5
    env.close()


def test_action_mask_prevents_invalid_high_level_choices():
    env = VariableSwarmRLlibEnv(
        {
            "fixed_team_profile": {"rover": 1, "drone": 0},
            "curriculum": False,
            "world_sizes": [24],
            "max_steps": 2,
            "final_team_profiles": [{"rover": 1, "drone": 0}],
        }
    )
    observations, _ = env.reset(seed=17)
    observation = next(iter(observations.values()))
    invalid = np.where(observation["action_mask"] == 0)[0]
    valid = np.where(observation["action_mask"] == 1)[0]
    assert len(valid) >= 2
    assert all(action < 5 for action in invalid)
    env.close()
