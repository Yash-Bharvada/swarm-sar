import numpy as np

from swarm_sar.robots.robot import Robot
from swarm_sar.sim.engine import apply_movements
from swarm_sar.utils.rng import make_rng
from swarm_sar.world.cells import FREE, RUBBLE, WALL


CONFIG = {
    "battery": 10,
    "move_cost": 1.0,
    "rubble_cost": 2.0,
    "idle_cost": 0.1,
    "can_cross_rubble": True,
    "can_cross_walls": False,
}


def robot(robot_id, x, y, battery=10, shape=(5, 5)):
    return Robot.create(robot_id, "rover", x, y, battery, shape)


def bordered_grid():
    grid = np.zeros((5, 5), dtype=np.int8)
    grid[[0, -1], :] = WALL
    grid[:, [0, -1]] = WALL
    return grid


def test_wall_and_edge_bumps():
    grid = bordered_grid()
    rover = robot(0, 1, 1)
    apply_movements([rover], [1], grid, CONFIG, make_rng(0))
    assert rover.position == (1, 1) and rover.collided
    open_grid = np.full((5, 5), FREE, dtype=np.int8)
    edge_rover = robot(0, 0, 0)
    apply_movements([edge_rover], [3], open_grid, CONFIG, make_rng(0))
    assert edge_rover.position == (0, 0) and edge_rover.collided


def test_two_robots_target_same_cell_only_one_moves():
    robots = [robot(0, 1, 2), robot(1, 3, 2)]
    apply_movements(robots, [4, 3], bordered_grid(), CONFIG, make_rng(2))
    assert sum(item.position == (2, 2) for item in robots) == 1
    assert sum(item.collided for item in robots) == 1


def test_swap_attempt_is_blocked():
    robots = [robot(0, 1, 2), robot(1, 2, 2)]
    apply_movements(robots, [4, 3], bordered_grid(), CONFIG, make_rng(4))
    assert [item.position for item in robots] == [(1, 2), (2, 2)]
    assert all(item.collided for item in robots)


def test_rubble_cost_battery_death_and_dead_robot_not_blocking():
    grid = bordered_grid()
    grid[2, 2] = RUBBLE
    rover = robot(0, 1, 2, battery=2)
    apply_movements([rover], [4], grid, CONFIG, make_rng(0))
    assert rover.position == (2, 2)
    assert rover.battery == 0 and not rover.alive
    follower = robot(1, 1, 2)
    apply_movements([follower, rover], [4, 0], grid, CONFIG, make_rng(0))
    assert follower.position == (2, 2)
