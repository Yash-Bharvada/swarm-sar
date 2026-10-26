import numpy as np

from swarm_sar.robots.robot import Robot
from swarm_sar.sensing.vision import has_line_of_sight, update_vision
from swarm_sar.world.cells import FREE, UNKNOWN, WALL


def test_wall_visible_but_cells_behind_stay_unknown():
    grid = np.full((7, 7), FREE, dtype=np.int8)
    grid[3, 3] = WALL
    rover = Robot.create(0, "rover", 1, 3, 10, grid.shape)
    update_vision(rover, grid, 5)
    assert rover.belief[3, 3] == WALL
    assert rover.belief[3, 4] == UNKNOWN
    assert has_line_of_sight(grid, (1, 3), (3, 3))
    assert not has_line_of_sight(grid, (1, 3), (4, 3))


def test_radius_and_newly_revealed_count():
    grid = np.full((9, 9), FREE, dtype=np.int8)
    rover = Robot.create(0, "rover", 4, 4, 10, grid.shape)
    first = update_vision(rover, grid, 2)
    second = update_vision(rover, grid, 2)
    expected = sum(dx * dx + dy * dy <= 4 for dx in range(-2, 3) for dy in range(-2, 3))
    assert first == expected
    assert second == 0
    assert rover.belief[4, 7] == UNKNOWN
