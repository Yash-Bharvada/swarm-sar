from swarm_sar.validation.robustness import (
    MAX_COLLISIONS,
    MIN_CONFIRMATION_PRECISION,
    MIN_SURVIVOR_RECALL,
    stressed_configs,
)


def test_holdout_gates_are_fixed_and_strict():
    assert MIN_SURVIVOR_RECALL == 0.90
    assert MIN_CONFIRMATION_PRECISION == 0.95
    assert MAX_COLLISIONS == 2


def test_stress_profile_cycles_sizes_and_degrades_agents():
    first_world, first_robots, _, first_size = stressed_configs(0)
    second_world, _, _, second_size = stressed_configs(1)
    third_world, _, _, third_size = stressed_configs(2)
    assert (first_size, second_size, third_size) == (24, 32, 40)
    assert first_world["width"] == first_world["height"] == 24
    assert second_world["width"] == 32 and third_world["width"] == 40
    assert first_robots["rover"]["thermal_noise"] == 0.07500000000000001
    assert first_robots["rover"]["thermal_detection_probability"] == 0.78
    assert first_robots["rover"]["odometry_drift_std"] == 0.07
    assert first_robots["rover"]["battery"] == 255.0
