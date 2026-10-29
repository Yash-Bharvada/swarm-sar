"""Run the blueprint Step 1 acceptance gate on three deterministic seeds."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from swarm_sar.sim.env import HOLD, DisasterResponseParallelEnv
from swarm_sar.world.cells import WALL

FORBIDDEN_OBSERVATION_FIELDS = {"grid", "true_grid", "victims", "victim_positions"}


def collision_free_actions(
    env: DisasterResponseParallelEnv, step: int
) -> dict[str, int]:
    """Move at most one rotating agent along a safe locally known A* path."""
    actions = {agent: HOLD for agent in env.agents}
    occupied = {
        robot.position for robot in env.core.robots if robot.alive
    }
    ordered = env.agents[step % len(env.agents) :] + env.agents[: step % len(env.agents)]
    for agent in ordered:
        for slot, candidate in enumerate(env._candidate_list(agent)):
            if len(candidate["path"]) >= 2 and candidate["path"][1] not in occupied:
                actions[agent] = slot
                return actions
    return actions


def validate_seed(seed: int, output_root: Path, max_steps: int) -> dict[str, object]:
    env = DisasterResponseParallelEnv()
    observations, _ = env.reset(seed=seed)
    initial_grid = env.core.grid.copy()
    initial_victims = [dict(victim) for victim in env.core.victims]
    initial_positions = [robot.position for robot in env.core.robots]

    types = [robot.type for robot in env.core.robots]
    assert types.count("rover") == 2 and types.count("drone") == 2
    assert 1 <= len(env.core.victims) <= 4
    for agent, observation in observations.items():
        assert env.observation_space(agent).contains(observation)
        assert not FORBIDDEN_OBSERVATION_FIELDS.intersection(observation)

    overlap_free = True
    wall_free = True
    steps = 0
    while env.agents and steps < max_steps:
        actions = collision_free_actions(env, steps)
        observations, _, terminations, truncations, _ = env.step(actions)
        positions = [robot.position for robot in env.core.robots if robot.alive]
        overlap_free &= len(positions) == len(set(positions))
        wall_free &= all(env.core.grid[y, x] != WALL for x, y in positions)
        steps += 1
        if all(terminations.values()) or all(truncations.values()):
            break

    artifact_dir = output_root / f"seed_{seed}"
    artifacts = env.save_episode(artifact_dir)
    assert all(path.exists() and path.stat().st_size > 0 for path in artifacts.values())
    metrics = env.core.metrics_snapshot()
    drift_observed = any(
        abs(robot.odom_x - robot.x) > 1e-8 or abs(robot.odom_y - robot.y) > 1e-8
        for robot in env.core.robots
        if robot.distance_travelled
    )

    # A second reset proves seed-level map, survivor and spawn reproducibility.
    replay = DisasterResponseParallelEnv()
    replay.reset(seed=seed)
    reproducible = (
        np.array_equal(initial_grid, replay.core.grid)
        and initial_victims == replay.core.victims
        and initial_positions == [robot.position for robot in replay.core.robots]
    )
    replay.close()
    env.close()
    collision_free = metrics["collisions"] == 0
    assert overlap_free and wall_free and collision_free and reproducible
    return {
        "seed": seed,
        "agents": len(types),
        "rovers": types.count("rover"),
        "drones": types.count("drone"),
        "survivors": len(initial_victims),
        "steps": steps,
        "coverage": metrics["coverage"],
        "survivors_found": metrics["victims_found"],
        "overlap_free": overlap_free,
        "wall_free": wall_free,
        "collision_attempts": metrics["collisions"],
        "collision_free": collision_free,
        "no_hidden_state": True,
        "reproducible": reproducible,
        "odometry_drift_observed": drift_observed,
        "artifacts": {name: str(path) for name, path in artifacts.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--output", type=Path, default=Path("training/runs/step1_validation"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = [validate_seed(seed, args.output, args.max_steps) for seed in args.seeds]
    summary_json = args.output / "summary.json"
    summary_csv = args.output / "summary.csv"
    summary_json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    flat_rows = [{key: value for key, value in row.items() if key != "artifacts"} for row in rows]
    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0]))
        writer.writeheader()
        writer.writerows(flat_rows)
    print(json.dumps(rows, indent=2))
    print(f"PASS: Step 1 three-seed gate; wrote {summary_json} and {summary_csv}")


if __name__ == "__main__":
    main()
