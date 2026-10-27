import numpy as np
import pytest

from swarm_sar.robots.robot import Robot
from swarm_sar.sensing.victim_sensor import acoustic_reading, thermal_reading
from swarm_sar.utils.rng import make_rng
from swarm_sar.world.cells import WALL


CONFIG = {
    "thermal_radius": 6,
    "thermal_decay": 3.0,
    "thermal_noise": 0.0,
    "thermal_detection_probability": 1.0,
    "thermal_false_positive_rate": 0.0,
    "acoustic_radius": 10,
    "acoustic_decay": 6.0,
    "acoustic_noise": 0.0,
    "acoustic_detection_probability": 1.0,
    "acoustic_false_positive_rate": 0.0,
    "acoustic_wall_factor": 0.4,
}


def victim(x, y):
    return {"id": 0, "x": x, "y": y, "found": False, "found_by": None, "found_step": None}


def test_thermal_is_directional_and_increases_when_closer():
    grid = np.zeros((12, 12), dtype=np.int8)
    far = Robot.create(0, "rover", 2, 5, 10, grid.shape)
    close = Robot.create(1, "rover", 5, 5, 10, grid.shape)
    target = [victim(7, 5)]
    far_value = thermal_reading(far, target, grid, CONFIG, make_rng(0))
    close_value = thermal_reading(close, target, grid, CONFIG, make_rng(0))
    assert far_value[1] > 0
    assert np.count_nonzero(far_value) == 1
    assert close_value[1] > far_value[1]


def test_wall_blocks_thermal_but_attenuates_acoustic():
    clear = np.zeros((9, 9), dtype=np.int8)
    blocked = clear.copy()
    blocked[4, 4] = WALL
    rover = Robot.create(0, "rover", 2, 4, 10, clear.shape)
    targets = [victim(6, 4)]
    assert thermal_reading(rover, targets, blocked, CONFIG, make_rng(0)).sum() == 0
    clear_sound = acoustic_reading(rover, targets, clear, CONFIG, make_rng(0))[0]
    blocked_sound = acoustic_reading(rover, targets, blocked, CONFIG, make_rng(0))[0]
    assert blocked_sound == pytest.approx(clear_sound * CONFIG["acoustic_wall_factor"])


def test_beyond_acoustic_range_is_noise_only():
    config = {**CONFIG, "acoustic_noise": 0.0}
    grid = np.zeros((20, 20), dtype=np.int8)
    rover = Robot.create(0, "rover", 1, 1, 10, grid.shape)
    assert acoustic_reading(rover, [victim(15, 15)], grid, config, make_rng(1))[0] == 0


def test_configurable_misses_and_false_positives():
    grid = np.zeros((10, 10), dtype=np.int8)
    rover = Robot.create(0, "rover", 2, 2, 10, grid.shape)
    missed = {
        **CONFIG,
        "thermal_detection_probability": 0.0,
        "acoustic_detection_probability": 0.0,
    }
    target = [victim(3, 2)]
    assert thermal_reading(rover, target, grid, missed, make_rng(3)).sum() == 0
    assert acoustic_reading(rover, target, grid, missed, make_rng(3))[0] == 0

    false_positive = {
        **CONFIG,
        "thermal_false_positive_rate": 1.0,
        "acoustic_false_positive_rate": 1.0,
    }
    assert thermal_reading(rover, [], grid, false_positive, make_rng(4)).sum() > 0
    assert acoustic_reading(rover, [], grid, false_positive, make_rng(4))[0] > 0
