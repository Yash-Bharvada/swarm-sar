"""Victim placement and state helpers."""

from typing import Any

import numpy as np

from swarm_sar.world.cells import FREE


def place_victims(
    grid: np.ndarray,
    distances: np.ndarray,
    config: dict[str, Any],
    rng: np.random.Generator,
) -> list[dict[str, Any]]:
    """Place reachable, well-separated victims using the shared RNG."""
    minimum_path = int(config["victim_min_dist_from_spawn"])
    minimum_between = float(config["victim_min_dist_between"])
    configured_count = config["num_victims"]
    if isinstance(configured_count, (list, tuple)):
        low, high = map(int, configured_count)
        count = int(rng.integers(low, high + 1))
    else:
        count = int(configured_count)
    candidates = np.argwhere((grid == FREE) & (distances >= minimum_path))
    if len(candidates) < count:
        raise ValueError("Not enough eligible cells to place victims")

    candidates = candidates[rng.permutation(len(candidates))]
    chosen: list[tuple[int, int]] = []
    for y, x in candidates:
        point = (int(x), int(y))
        if all(np.hypot(point[0] - px, point[1] - py) >= minimum_between for px, py in chosen):
            chosen.append(point)
            if len(chosen) == count:
                break
    if len(chosen) != count:
        raise ValueError("Could not place victims with the requested separation")

    return [
        {"id": index, "x": x, "y": y, "found": False, "found_by": None, "found_step": None}
        for index, (x, y) in enumerate(chosen)
    ]
