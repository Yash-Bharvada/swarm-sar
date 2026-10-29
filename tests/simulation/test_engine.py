import numpy as np
import pytest

from swarm_sar.sim.engine import SwarmWorld


EXPECTED_FIELDS = {
    "local_map",
    "battery",
    "thermal",
    "acoustic",
    "prev_thermal",
    "prev_acoustic",
    "rel_pos",
    "pose_uncertainty",
    "collided",
}


def test_reset_and_step_observation_shapes_and_no_ground_truth():
    world = SwarmWorld()
    observations = world.reset(11)
    assert len(observations) == 4
    assert [robot.type for robot in world.robots].count("rover") == 2
    assert [robot.type for robot in world.robots].count("drone") == 2
    for observation in observations.values():
        assert set(observation) == EXPECTED_FIELDS
        assert observation["local_map"].shape == (9, 9)
        assert observation["thermal"].shape == (4,)
        assert observation["acoustic"].shape == (1,)
        assert observation["rel_pos"].shape == (2,)
    observations, info, done = world.step([0] * 4)
    assert not done
    assert 0 <= info["coverage"] <= 1


def test_same_seed_and_actions_give_identical_episode():
    first, second = SwarmWorld(), SwarmWorld()
    first_obs, second_obs = first.reset(99), second.reset(99)
    actions = [[4, 2, 0, 3], [0, 4, 2, 1], [1, 1, 4, 0]]
    for action in actions:
        first_obs, first_info, _ = first.step(action)
        second_obs, second_info, _ = second.step(action)
    assert np.array_equal(first.grid, second.grid)
    assert first.victims == second.victims
    for robot_id in first_obs:
        for field in EXPECTED_FIELDS:
            assert np.array_equal(first_obs[robot_id][field], second_obs[robot_id][field])
    assert first_info == second_info


def test_max_steps_termination_and_no_steps_after_done():
    config = {
        "agent_counts": {"rover": 1},
        "max_steps": 2,
        "seed": 0,
        "end_when_all_found": False,
        "render_cell_px": 8,
        "fps": 10,
        "local_window_radius": 4,
        "max_frontiers": 5,
    }
    world = SwarmWorld(sim_config=config)
    world.reset()
    assert not world.step([0])[2]
    assert world.step([0])[2]
    with pytest.raises(RuntimeError):
        world.step([0])


def test_all_victims_found_and_all_robots_dead_terminate():
    found_world = SwarmWorld()
    found_world.reset(4)
    found_world.sim_config["auto_confirm_victims"] = True
    rover = found_world.robots[0]
    for victim in found_world.victims:
        victim["x"], victim["y"] = rover.position
    _, info, done = found_world.step([0] * len(found_world.robots))
    assert done and info["victims_found"] == len(found_world.victims)

    robot_config = {
        name: dict(config) for name, config in found_world.robot_configs.items()
    }
    robot_config["rover"]["battery"] = 0.05
    sim_config = dict(found_world.sim_config)
    sim_config.update(agent_counts={"rover": 1}, end_when_all_found=False)
    dead_world = SwarmWorld(robot_config=robot_config, sim_config=sim_config)
    dead_world.reset(5)
    assert dead_world.step([0])[2]
    assert not dead_world.robots[0].alive
