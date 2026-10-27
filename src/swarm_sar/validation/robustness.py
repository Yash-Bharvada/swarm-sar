"""Fixed Step 2 holdout stress profile."""

import copy
from pathlib import Path

from swarm_sar.utils.config import load_config

MIN_SURVIVOR_RECALL = 0.90
MIN_CONFIRMATION_PRECISION = 0.95
MAX_COLLISIONS = 2
MAX_DUPLICATE_GOAL_STEPS = 0


def stressed_configs(seed_index: int):
    root = Path(__file__).resolve().parents[3]
    world = load_config(root / "configs/world.yaml")
    robots = load_config(root / "configs/robots.yaml")
    sim = load_config(root / "configs/sim.yaml")

    size = (24, 32, 40)[seed_index % 3]
    world.update(
        width=size,
        height=size,
        victim_min_dist_from_spawn=max(6, size // 4),
    )
    robots = copy.deepcopy(robots)
    for config in robots.values():
        config["thermal_noise"] *= 1.5
        config["acoustic_noise"] *= 1.5
        config["thermal_detection_probability"] = max(
            0.0, config["thermal_detection_probability"] - 0.10
        )
        config["acoustic_detection_probability"] = max(
            0.0, config["acoustic_detection_probability"] - 0.10
        )
        config["thermal_false_positive_rate"] = min(
            1.0, config["thermal_false_positive_rate"] + 0.05
        )
        config["acoustic_false_positive_rate"] = min(
            1.0, config["acoustic_false_positive_rate"] + 0.05
        )
        config["odometry_drift_std"] *= 2.0
        config["odometry_uncertainty_growth"] *= 2.0
        config["battery"] *= 0.85
    return world, robots, sim, size
