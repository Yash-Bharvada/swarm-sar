"""Noisy thermal/acoustic sensing and victim confirmation."""

from typing import Any

import numpy as np

from swarm_sar.robots.robot import Robot
from swarm_sar.sensing.vision import has_line_of_sight


def thermal_reading(
    robot: Robot,
    victims: list[dict[str, Any]],
    grid: np.ndarray,
    config: dict[str, Any],
    rng: np.random.Generator,
) -> np.ndarray:
    """Return signals in up, right, down, left sectors."""
    values = np.zeros(4, dtype=np.float64)
    radius = float(config["thermal_radius"])
    decay = float(config["thermal_decay"])
    detection_probability = float(config.get("thermal_detection_probability", 1.0))
    for victim in victims:
        if victim.get("found", False):
            continue
        dx, dy = int(victim["x"]) - robot.x, int(victim["y"]) - robot.y
        distance = float(np.hypot(dx, dy))
        if distance > radius or not has_line_of_sight(grid, robot.position, (victim["x"], victim["y"])):
            continue
        if rng.random() > detection_probability:
            continue
        if abs(dy) >= abs(dx):
            sector = 0 if dy <= 0 else 2
        else:
            sector = 1 if dx > 0 else 3
        values[sector] += np.exp(-distance / decay)
    false_positive_rate = float(config.get("thermal_false_positive_rate", 0.0))
    if rng.random() < false_positive_rate:
        values[int(rng.integers(4))] += float(rng.uniform(0.1, 0.4))
    values += rng.normal(0.0, float(config["thermal_noise"]), size=4)
    return np.clip(values, 0.0, None).astype(np.float32)


def acoustic_reading(
    robot: Robot,
    victims: list[dict[str, Any]],
    grid: np.ndarray,
    config: dict[str, Any],
    rng: np.random.Generator,
) -> np.ndarray:
    """Return one omnidirectional value; walls attenuate rather than block."""
    total = 0.0
    radius = float(config["acoustic_radius"])
    decay = float(config["acoustic_decay"])
    wall_factor = float(config["acoustic_wall_factor"])
    detection_probability = float(config.get("acoustic_detection_probability", 1.0))
    for victim in victims:
        if victim.get("found", False):
            continue
        distance = float(np.hypot(victim["x"] - robot.x, victim["y"] - robot.y))
        if distance > radius:
            continue
        if rng.random() > detection_probability:
            continue
        signal = float(np.exp(-distance / decay))
        if not has_line_of_sight(grid, robot.position, (victim["x"], victim["y"])):
            signal *= wall_factor
        total += signal
    if rng.random() < float(config.get("acoustic_false_positive_rate", 0.0)):
        total += float(rng.uniform(0.1, 0.4))
    total += float(rng.normal(0.0, float(config["acoustic_noise"])))
    return np.array([max(0.0, total)], dtype=np.float32)


def update_robot_sensors(
    robot: Robot,
    victims: list[dict[str, Any]],
    grid: np.ndarray,
    config: dict[str, Any],
    rng: np.random.Generator,
    *,
    preserve_previous: bool = True,
) -> None:
    if preserve_previous:
        robot.prev_thermal = robot.thermal.copy()
        robot.prev_acoustic = robot.acoustic.copy()
    robot.thermal = thermal_reading(robot, victims, grid, config, rng)
    robot.acoustic = acoustic_reading(robot, victims, grid, config, rng)


def confirm_victims(
    robots: list[Robot],
    victims: list[dict[str, Any]],
    grid: np.ndarray,
    confirm_radius: float | dict[str, float],
    step: int,
) -> int:
    """Mark newly confirmed victims and return their count."""
    newly_found = 0
    for victim in victims:
        if victim["found"]:
            continue
        for robot in robots:
            if not robot.alive:
                continue
            radius = (
                float(confirm_radius[robot.type])
                if isinstance(confirm_radius, dict)
                else float(confirm_radius)
            )
            distance = float(np.hypot(victim["x"] - robot.x, victim["y"] - robot.y))
            if distance <= radius and has_line_of_sight(
                grid, robot.position, (victim["x"], victim["y"])
            ):
                victim["found"] = True
                victim["found_by"] = robot.id
                victim["found_step"] = step
                newly_found += 1
                break
    return newly_found
