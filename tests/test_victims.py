import numpy as np

from swarm_sar.sensing.victim_sensor import confirm_victims
from swarm_sar.robots.robot import Robot
from swarm_sar.utils.config import load_config
from swarm_sar.utils.rng import make_rng
from swarm_sar.world.cells import WALL
from swarm_sar.world.generator import generate_world, spawn_center
from swarm_sar.world.victims import place_victims


def test_victim_placement_rules_over_100_seeds():
    cfg = load_config("configs/world.yaml")
    for seed in range(100):
        rng = make_rng(seed)
        grid, distances = generate_world(cfg, rng)
        victims = place_victims(grid, distances, cfg, rng)
        assert len(victims) == cfg["num_victims"]
        for victim in victims:
            assert distances[victim["y"], victim["x"]] >= cfg["victim_min_dist_from_spawn"]
            assert not victim["found"]
        for index, first in enumerate(victims):
            for second in victims[index + 1 :]:
                assert np.hypot(first["x"] - second["x"], first["y"] - second["y"]) >= cfg["victim_min_dist_between"]


def test_confirmation_updates_found_fields():
    grid = np.zeros((5, 5), dtype=np.int8)
    robot = Robot.create(7, "rover", 1, 2, 10, grid.shape)
    victims = [{"id": 0, "x": 3, "y": 2, "found": False, "found_by": None, "found_step": None}]
    assert confirm_victims([robot], victims, grid, 2, 9) == 1
    assert victims[0]["found_by"] == 7
    assert victims[0]["found_step"] == 9
    grid[2, 2] = WALL
    victims[0].update(found=False, found_by=None, found_step=None)
    assert confirm_victims([robot], victims, grid, 2, 10) == 0
