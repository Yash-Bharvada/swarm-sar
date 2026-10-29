import numpy as np

from swarm_sar.robots.robot import Robot
from swarm_sar.sim.engine import SwarmWorld, apply_movements
from swarm_sar.utils.rng import make_rng
from swarm_sar.world.cells import FREE, RUBBLE, WALL


def test_default_team_is_two_rovers_and_two_drones():
    world = SwarmWorld()
    world.reset(12)
    assert [robot.type for robot in world.robots] == ["rover", "rover", "drone", "drone"]
    assert world.robot_configs["drone"]["vision_radius"] > world.robot_configs["rover"]["vision_radius"]
    assert world.robot_configs["drone"]["rubble_cost"] < world.robot_configs["rover"]["rubble_cost"]
    assert not world.robot_configs["drone"]["can_cross_walls"]


def test_type_specific_mobility_and_odometry_drift():
    grid = np.full((5, 6), FREE, dtype=np.int8)
    grid[[0, -1], :] = WALL
    grid[:, [0, -1]] = WALL
    grid[2, 2] = RUBBLE
    rover = Robot.create(0, "rover", 1, 2, 10, grid.shape)
    drone = Robot.create(1, "drone", 1, 3, 10, grid.shape)
    configs = {
        "rover": {
            "move_cost": 1.0,
            "rubble_cost": 2.0,
            "idle_cost": 0.1,
            "can_cross_rubble": True,
            "can_cross_walls": False,
            "odometry_drift_std": 0.1,
            "odometry_uncertainty_growth": 0.02,
        },
        "drone": {
            "move_cost": 1.0,
            "rubble_cost": 1.0,
            "idle_cost": 0.1,
            "can_cross_rubble": True,
            "can_cross_walls": False,
            "odometry_drift_std": 0.1,
            "odometry_uncertainty_growth": 0.03,
        },
    }
    apply_movements([rover, drone], [4, 4], grid, configs, make_rng(2))
    assert rover.battery == 8.0
    assert drone.battery == 9.0
    assert rover.odom_uncertainty == 0.02
    assert drone.odom_uncertainty == 0.03
    assert (rover.odom_x, rover.odom_y) != (float(rover.x), float(rover.y))


def test_drone_and_rover_both_stop_at_walls():
    grid = np.full((5, 5), FREE, dtype=np.int8)
    grid[2, 2] = WALL
    configs = {
        kind: {
            "move_cost": 1.0,
            "rubble_cost": 1.0,
            "idle_cost": 0.1,
            "can_cross_rubble": True,
            "can_cross_walls": False,
        }
        for kind in ("rover", "drone")
    }
    for kind in ("rover", "drone"):
        robot = Robot.create(0, kind, 1, 2, 10, grid.shape)
        apply_movements([robot], [4], grid, configs, make_rng(1))
        assert robot.position == (1, 2) and robot.collided
