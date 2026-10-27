"""Episode metrics and CSV persistence."""

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from swarm_sar.robots.robot import Robot
from swarm_sar.world.cells import UNKNOWN, WALL


class EpisodeMetrics:
    def __init__(self, grid: np.ndarray, distances: np.ndarray, victims: list[dict[str, Any]]):
        self.grid = grid
        self.distances = distances
        self.victims = victims
        self.time_to_first_victim: int | None = None
        self.time_to_all_victims: int | None = None
        self.collisions = 0
        self.coverage_over_time: list[float] = []
        self.victims_over_time: list[int] = []

    @property
    def victims_found(self) -> int:
        return sum(bool(victim["found"]) for victim in self.victims)

    def coverage(self, robots: list[Robot]) -> float:
        reachable = (self.distances >= 0) & (self.grid != WALL)
        denominator = int(np.count_nonzero(reachable))
        if denominator == 0:
            return 0.0
        known = np.zeros(self.grid.shape, dtype=bool)
        for robot in robots:
            known |= robot.belief != UNKNOWN
        return float(np.count_nonzero(known & reachable) / denominator)

    def update(self, step: int, robots: list[Robot]) -> None:
        self.record_victim_times(step)
        self.collisions += sum(robot.collided for robot in robots)
        self.coverage_over_time.append(self.coverage(robots))
        self.victims_over_time.append(self.victims_found)

    def record_victim_times(self, step: int) -> None:
        found = self.victims_found
        if found and self.time_to_first_victim is None:
            self.time_to_first_victim = step
        if found == len(self.victims) and self.time_to_all_victims is None:
            self.time_to_all_victims = step

    def snapshot(self, step: int, robots: list[Robot]) -> dict[str, Any]:
        return {
            "step": step,
            "victims_found": self.victims_found,
            "time_to_first_victim": self.time_to_first_victim,
            "time_to_all_victims": self.time_to_all_victims,
            "coverage": self.coverage(robots),
            "collisions": self.collisions,
            "distance_per_robot": {robot.id: robot.distance_travelled for robot in robots},
            "battery_left": {robot.id: robot.battery for robot in robots},
            "coverage_over_time": list(self.coverage_over_time),
            "victims_over_time": list(self.victims_over_time),
        }


def append_episode_csv(path: str | Path, row: dict[str, Any]) -> None:
    """Append one metrics row, JSON-encoding nested/list values."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    serialised = {
        key: json.dumps(value, separators=(",", ":")) if isinstance(value, (dict, list)) else value
        for key, value in row.items()
    }
    exists = output.exists() and output.stat().st_size > 0
    with output.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(serialised))
        if not exists:
            writer.writeheader()
        writer.writerow(serialised)
