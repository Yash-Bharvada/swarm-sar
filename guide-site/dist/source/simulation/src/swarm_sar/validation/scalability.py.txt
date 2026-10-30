"""Fixed and random-shape Step 2.5 validation profiles."""

import copy
from pathlib import Path

import numpy as np

from swarm_sar.utils.config import load_config
from swarm_sar.world.generator import build_footprint_mask

SCALABILITY_CASES = (
    (24, 48, "l_shape"),
    (32, 64, "t_shape"),
    (40, 80, "multi_structure"),
    (64, 128, "tunnel"),
)

MIN_SURVIVOR_RECALL = 0.90
MIN_CONFIRMATION_PRECISION = 0.95
MIN_MEAN_COVERAGE = 0.75
MAX_COLLISIONS = 0
MAX_DUPLICATE_GOAL_STEPS = 0
MIN_STEPS_PER_SECOND = 10.0
MIN_IRREGULARITY = 0.08


def random_scalability_configs(seed: int):
    """Build a reproducible large case whose dimensions and shape vary by seed."""
    root = Path(__file__).resolve().parents[4]
    world = load_config(root / "configs/world.yaml")
    robots = copy.deepcopy(load_config(root / "configs/robots.yaml"))
    sim = load_config(root / "configs/sim.yaml")
    baseline = load_config(root / "configs/baseline.yaml")
    profile_rng = np.random.default_rng(int(seed) ^ 0x5A1725)
    short_side = int(profile_rng.integers(48, 91))
    long_side = int(profile_rng.integers(max(72, short_side + 12), 141))
    if bool(profile_rng.integers(2)):
        height, width = short_side, long_side
    else:
        height, width = long_side, short_side

    storage_area = height * width
    estimated_site_area = int(storage_area * 0.45)
    agent_count = int(np.clip(round(estimated_site_area / 750), 4, 8))
    rover_count = agent_count // 2
    drone_count = agent_count - rover_count
    target_rooms = max(16, estimated_site_area // 80)
    max_steps = max(
        900,
        int(round(400 * (storage_area / 1024) * (4 / agent_count))),
    )

    world.update(
        height=height,
        width=width,
        footprint="procedural",
        victim_min_dist_from_spawn=max(10, short_side // 3),
        victim_min_dist_between=max(5, short_side // 10),
        num_victims=[2, 5],
        num_rooms=[target_rooms, target_rooms + max(4, target_rooms // 8)],
        rubble_patches=max(6, estimated_site_area // 240),
        max_generation_retries=80,
        min_free_ratio=0.16,
    )
    sim["agent_counts"] = {"rover": rover_count, "drone": drone_count}
    sim["frontier_samples_per_cluster"] = 5
    sim["max_steps"] = max_steps
    baseline["max_steps"] = max_steps
    baseline["peer_map_exchange"] = True
    baseline["topology_update_interval"] = max(5, max(height, width) // 16)
    for config in robots.values():
        config["battery"] = max(float(config["battery"]), max_steps * 1.15)
    return world, robots, sim, baseline


def scalable_configs(case_index: int):
    root = Path(__file__).resolve().parents[4]
    world = load_config(root / "configs/world.yaml")
    robots = copy.deepcopy(load_config(root / "configs/robots.yaml"))
    sim = load_config(root / "configs/sim.yaml")
    baseline = load_config(root / "configs/baseline.yaml")

    height, width, footprint = SCALABILITY_CASES[case_index % len(SCALABILITY_CASES)]
    world.update(
        height=height,
        width=width,
        footprint=footprint,
        victim_min_dist_from_spawn=max(6, min(width, height) // 3),
        max_generation_retries=60,
        min_free_ratio=0.20,
    )
    allowed_cells = int(build_footprint_mask(world).sum())
    target_rooms = max(10, allowed_cells // 75)
    world["num_rooms"] = [target_rooms, target_rooms + max(3, target_rooms // 8)]
    world["rubble_patches"] = max(4, allowed_cells // 260)

    distance_scale = max(width, height) / 32.0
    sim["max_steps"] = max(400, int(round(400 * distance_scale)))
    sim["frontier_samples_per_cluster"] = 5
    baseline["max_steps"] = sim["max_steps"]
    baseline["peer_map_exchange"] = True
    for config in robots.values():
        config["battery"] *= max(1.0, distance_scale)
    return world, robots, sim, baseline, (height, width, footprint)
