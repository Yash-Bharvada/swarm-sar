import csv
import json

import numpy as np
from pettingzoo.test import parallel_api_test

from swarm_sar.sim.env import HOLD, INVESTIGATE, DisasterResponseParallelEnv


def test_pettingzoo_parallel_api_contract():
    env = DisasterResponseParallelEnv()
    parallel_api_test(env, num_cycles=50)
    env.close()


def test_observations_are_local_fixed_shape_and_contained():
    env = DisasterResponseParallelEnv()
    observations, infos = env.reset(seed=7)
    assert len(env.agents) == 4
    assert {info["agent_type"] for info in infos.values()} == {"rover", "drone"}
    forbidden = {"grid", "true_grid", "victims", "victim_positions"}
    for agent, observation in observations.items():
        assert not forbidden.intersection(observation)
        assert observation["local_map"].shape == (9, 9)
        assert observation["frontier_features"].shape == (5, 5)
        assert observation["action_mask"].shape == (7,)
        assert env.observation_space(agent).contains(observation)
    env.close()


def test_hold_episode_is_deterministic_for_same_seed():
    first, second = DisasterResponseParallelEnv(), DisasterResponseParallelEnv()
    first_obs, _ = first.reset(seed=31)
    second_obs, _ = second.reset(seed=31)
    for _ in range(5):
        actions = {agent: HOLD for agent in first.agents}
        first_obs, first_rewards, first_terms, first_truncs, _ = first.step(actions)
        second_obs, second_rewards, second_terms, second_truncs, _ = second.step(actions)
        assert first_rewards == second_rewards
        assert first_terms == second_terms and first_truncs == second_truncs
        for agent in first_obs:
            for field in first_obs[agent]:
                assert np.array_equal(first_obs[agent][field], second_obs[agent][field])
    first.close()
    second.close()


def test_frontier_action_executes_first_astar_step():
    env = DisasterResponseParallelEnv()
    env.reset(seed=0)
    selected = None
    for agent in env.agents:
        candidates = env._candidate_list(agent)
        for slot, candidate in enumerate(candidates):
            if len(candidate["path"]) >= 2:
                selected = (agent, slot, candidate["path"][1])
                break
        if selected:
            break
    assert selected is not None
    agent, slot, expected_position = selected
    actions = {name: HOLD for name in env.agents}
    actions[agent] = slot
    env.step(actions)
    assert env._robots_by_name[agent].position == expected_position
    env.close()


def test_investigate_fuses_an_extra_sensor_sample():
    env = DisasterResponseParallelEnv()
    env.reset(seed=9)
    investigated = env.agents[0]
    _, _, _, _, infos = env.step(
        {
            agent: INVESTIGATE if agent == investigated else HOLD
            for agent in env.agents
        }
    )
    assert infos[investigated]["investigating"]
    assert env.core.events[-1] == {
        "step": 1,
        "event": "investigate",
        "agent": investigated,
    }
    env.close()


def test_episode_artifacts_contain_map_events_and_trajectories(tmp_path):
    env = DisasterResponseParallelEnv()
    env.reset(seed=5)
    env.step({agent: HOLD for agent in env.agents})
    paths = env.save_episode(tmp_path)
    assert set(paths) == {"map", "events", "trajectories", "metrics"}
    map_data = json.loads(paths["map"].read_text())
    events = json.loads(paths["events"].read_text())
    with paths["trajectories"].open(newline="") as handle:
        trajectories = list(csv.DictReader(handle))
    assert map_data["seed"] == 5 and len(map_data["agents"]) == 4
    assert events[0]["event"] == "reset"
    assert len(trajectories) == 8
    env.close()


def test_rgb_array_render(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    env = DisasterResponseParallelEnv(render_mode="rgb_array")
    env.reset(seed=2)
    frame = env.render()
    assert frame.ndim == 3 and frame.shape[2] == 3 and frame.dtype == np.uint8
    env.close()
