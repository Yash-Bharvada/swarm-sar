import numpy as np

from swarm_sar.utils.config import load_config
from swarm_sar.utils.rng import make_rng
from swarm_sar.world.cells import FREE, WALL
from swarm_sar.world.generator import generate_candidate, generate_world


def config():
    return load_config("configs/world.yaml")


def test_same_seed_gives_same_map():
    first, first_distances = generate_world(config(), make_rng(42))
    second, second_distances = generate_world(config(), make_rng(42))
    assert np.array_equal(first, second)
    assert np.array_equal(first_distances, second_distances)


def test_border_spawn_and_reachability_over_100_seeds():
    cfg = config()
    x, y = cfg["spawn_origin"]
    size = cfg["spawn_size"]
    for seed in range(100):
        grid, distances = generate_world(cfg, make_rng(seed))
        assert np.all(grid[0, :] == WALL)
        assert np.all(grid[-1, :] == WALL)
        assert np.all(grid[:, 0] == WALL)
        assert np.all(grid[:, -1] == WALL)
        assert np.all(grid[y : y + size, x : x + size] == FREE)
        assert np.all(distances[grid != WALL] >= 0)


def test_single_candidate_rejection_rate_below_20_percent():
    cfg = config()
    rejected = 0
    for seed in range(200):
        _, _, ratio = generate_candidate(cfg, make_rng(seed))
        rejected += ratio < cfg["min_free_ratio"]
    assert rejected / 200 < 0.20


def test_optional_maze_layout_is_reachable():
    cfg = config()
    cfg.update({"layout": "maze", "width": 33, "height": 33, "min_free_ratio": 0.35})
    grid, distances = generate_world(cfg, make_rng(5))
    assert grid.shape == (33, 33)
    assert np.all(distances[grid != WALL] >= 0)


def test_blueprint_room_maps_support_24_and_40_cells():
    cfg = config()
    for size in (24, 40):
        sized = {
            **cfg,
            "width": size,
            "height": size,
            "victim_min_dist_from_spawn": max(6, size // 4),
        }
        for seed in range(10):
            grid, distances = generate_world(sized, make_rng(seed))
            assert grid.shape == (size, size)
            assert np.all(distances[grid != WALL] >= 0)
