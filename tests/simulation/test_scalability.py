import numpy as np

from swarm_sar.baselines.frontier import CoordinatedFrontierBaseline
from swarm_sar.sim.env import DisasterResponseParallelEnv
from swarm_sar.sim.planning import frontier_candidates
from swarm_sar.utils.config import load_config
from swarm_sar.utils.rng import make_rng
from swarm_sar.validation.scalability import random_scalability_configs
from swarm_sar.world.cells import FREE, UNKNOWN, WALL
from swarm_sar.world.generator import build_footprint_mask, generate_world


def test_procedural_footprints_are_seeded_connected_and_irregular():
    config = load_config("configs/world.yaml")
    config.update(width=97, height=61, footprint="procedural")
    first = build_footprint_mask(config, make_rng(44))
    replay = build_footprint_mask(config, make_rng(44))
    different = build_footprint_mask(config, make_rng(45))
    assert np.array_equal(first, replay)
    assert not np.array_equal(first, different)
    assert not np.any(first[[0, -1], :]) and not np.any(first[:, [0, -1]])

    points = {tuple(point[::-1]) for point in np.argwhere(first)}
    pending = [next(iter(points))]
    seen = {pending[0]}
    while pending:
        x, y = pending.pop()
        for point in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if point in points and point not in seen:
                seen.add(point)
                pending.append(point)
    assert seen == points
    ys, xs = np.where(first)
    bbox_area = (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)
    assert 1 - first.sum() / bbox_area > 0.08


def test_random_profiles_vary_dimensions_but_keep_policy_spaces_fixed():
    dimensions = set()
    for seed in range(310, 315):
        world, robots, sim, _ = random_scalability_configs(seed)
        dimensions.add((world["height"], world["width"]))
        assert world["height"] != world["width"]
        env = DisasterResponseParallelEnv(
            world_config=world, robot_config=robots, sim_config=sim
        )
        observations, _ = env.reset(seed=seed)
        for agent, observation in observations.items():
            assert observation["local_map"].shape == (9, 9)
            assert observation["frontier_features"].shape == (5, 5)
            assert observation["action_mask"].shape == (7,)
            assert env.observation_space(agent).contains(observation)
        env.close()
    assert len(dimensions) == 5


def test_large_connected_frontier_offers_multiple_fixed_slots():
    belief = np.full((35, 70), UNKNOWN, dtype=np.int8)
    belief[10:25, 5:50] = FREE
    candidates = frontier_candidates(
        belief, (10, 15), max_candidates=5, max_per_cluster=5
    )
    assert len(candidates) == 5
    assert len({candidate["position"] for candidate in candidates}) == 5


def test_peer_map_exchange_is_range_limited_and_keeps_private_arrays():
    baseline_config = load_config("configs/baseline.yaml")
    baseline_config["peer_map_exchange"] = True
    baseline = CoordinatedFrontierBaseline(config=baseline_config)
    baseline.reset(6)
    first, second = baseline.env.core.robots[:2]
    assert first.belief is not second.belief
    target = tuple(np.argwhere(first.belief == UNKNOWN)[0][::-1])
    first.belief[target[1], target[0]] = WALL
    second.x, second.y = first.x, first.y
    baseline._share_peer_maps()
    assert second.belief[target[1], target[0]] == WALL

    far_target = tuple(np.argwhere(first.belief == UNKNOWN)[0][::-1])
    first.belief[far_target[1], far_target[0]] = WALL
    second.x = min(first.belief.shape[1] - 1, first.x + 20)
    second.y = min(first.belief.shape[0] - 1, first.y + 20)
    baseline._share_peer_maps()
    assert second.belief[far_target[1], far_target[0]] == UNKNOWN
    baseline.env.close()


def test_random_large_world_is_fully_reachable():
    world, _, _, _ = random_scalability_configs(399)
    grid, distances = generate_world(world, make_rng(399))
    assert grid.shape == (world["height"], world["width"])
    assert np.all(distances[grid != WALL] >= 0)
