"""Step 2.5 audit over large, random-dimension, procedural-shape worlds."""

import argparse
import csv
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from swarm_sar.baselines.frontier import CoordinatedFrontierBaseline
from swarm_sar.sim.env import DisasterResponseParallelEnv
from swarm_sar.sim.engine import SwarmWorld
from swarm_sar.validation.scalability import (
    MAX_COLLISIONS,
    MAX_DUPLICATE_GOAL_STEPS,
    MIN_CONFIRMATION_PRECISION,
    MIN_IRREGULARITY,
    MIN_MEAN_COVERAGE,
    MIN_STEPS_PER_SECOND,
    MIN_SURVIVOR_RECALL,
    random_scalability_configs,
)
from swarm_sar.world.cells import WALL


def shape_metrics(grid: np.ndarray) -> dict[str, float | int | str]:
    traversable = grid != WALL
    ys, xs = np.where(traversable)
    bbox_area = int((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
    traversable_cells = int(np.count_nonzero(traversable))
    return {
        "traversable_cells": traversable_cells,
        "bounding_box_cells": bbox_area,
        "irregularity": 1.0 - traversable_cells / bbox_area,
        "map_fingerprint": hashlib.sha256(grid.tobytes()).hexdigest()[:16],
    }


def assert_world_invariants(core: SwarmWorld) -> None:
    navigable = core.grid != WALL
    if core.grid.shape[0] == core.grid.shape[1]:
        raise AssertionError("Random audit generated a square world")
    if not np.all(core.distances[navigable] >= 0):
        raise AssertionError("Generated world contains unreachable navigable cells")
    metrics = shape_metrics(core.grid)
    if metrics["irregularity"] < MIN_IRREGULARITY:
        raise AssertionError("Generated world is insufficiently irregular")
    if not all(core.grid[victim["y"], victim["x"]] != WALL for victim in core.victims):
        raise AssertionError("A survivor was placed outside the navigable site")


def run_mission(seed: int, output: Path | None = None):
    world, robots, sim, baseline_config = random_scalability_configs(seed)
    env = DisasterResponseParallelEnv(
        world_config=world,
        robot_config=robots,
        sim_config=sim,
    )
    controller = CoordinatedFrontierBaseline(env, baseline_config)
    started = time.perf_counter()
    observations = controller.reset(seed)
    assert_world_invariants(env.core)
    for agent, observation in observations.items():
        if not env.observation_space(agent).contains(observation):
            raise AssertionError(f"Invalid fixed observation for {agent}")
    while env.agents and env.core.step_count < int(baseline_config["max_steps"]):
        controller.step()
        if env.core.step_count % 100 == 0:
            for agent, observation in controller.observations.items():
                if not env.observation_space(agent).contains(observation):
                    raise AssertionError(f"Observation contract changed for {agent}")
    controller._update_maps(force=True)
    summary = controller.summary()
    elapsed = time.perf_counter() - started
    if output is not None:
        controller.save(output, summary)
    dimensions = f"{world['height']}x{world['width']}"
    row = {
        **summary,
        **shape_metrics(env.core.grid),
        "height": world["height"],
        "width": world["width"],
        "dimensions": dimensions,
        "agents": len(env.core.robots),
        "elapsed_seconds": elapsed,
        "steps_per_second": summary["steps"] / max(elapsed, 1e-9),
    }
    replay_state = (summary, controller.events, env.core.grid.copy())
    env.close()
    return row, replay_state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=list(range(700, 708)))
    parser.add_argument("--generation-seeds", type=int, default=50)
    parser.add_argument("--output", type=Path, default=Path("results/step25_scalability"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    definition = {
        "mission_seeds": args.seeds,
        "generation_property_seeds": [1000, 1000 + args.generation_seeds - 1],
        "dimension_distribution": {
            "short_side_cells": [48, 90],
            "long_side_cells": [72, 140],
            "orientation": "seeded random portrait or landscape",
        },
        "footprint": "seeded procedural connected lobes and corridors; no named shape",
        "resource_policy": "4-8 heterogeneous agents and mission budget scaled by area",
        "fixed_policy_interface": {"local_map": [9, 9], "actions": 7},
        "gates": {
            "minimum_survivor_recall": MIN_SURVIVOR_RECALL,
            "minimum_confirmation_precision": MIN_CONFIRMATION_PRECISION,
            "minimum_mean_coverage": MIN_MEAN_COVERAGE,
            "minimum_shape_irregularity": MIN_IRREGULARITY,
            "maximum_collisions": MAX_COLLISIONS,
            "maximum_duplicate_goal_steps": MAX_DUPLICATE_GOAL_STEPS,
            "minimum_steps_per_second": MIN_STEPS_PER_SECOND,
            "deterministic_replay": True,
        },
    }
    (args.output / "audit_definition.json").write_text(
        json.dumps(definition, indent=2), encoding="utf-8"
    )

    generation_rows = []
    for seed in range(1000, 1000 + args.generation_seeds):
        world, robots, sim, _ = random_scalability_configs(seed)
        core = SwarmWorld(world, robots, sim)
        core.reset(seed)
        assert_world_invariants(core)
        generation_rows.append(
            {
                "seed": seed,
                "height": world["height"],
                "width": world["width"],
                **shape_metrics(core.grid),
            }
        )
    (args.output / "generation_properties.json").write_text(
        json.dumps(generation_rows, indent=2), encoding="utf-8"
    )
    print(f"generation properties: {len(generation_rows)}/{len(generation_rows)} passed")

    rows = []
    first_state = None
    for seed in args.seeds:
        row, replay_state = run_mission(seed, args.output / f"seed_{seed}")
        rows.append(row)
        if first_state is None:
            first_state = replay_state
        print(
            f"seed {seed}: {row['dimensions']} agents={row['agents']} "
            f"survivors={row['survivors_found']}/{row['survivors_total']} "
            f"coverage={row['coverage']:.1%} irregularity={row['irregularity']:.1%} "
            f"steps={row['steps']} throughput={row['steps_per_second']:.1f}/s"
        )

    _, replay_state = run_mission(args.seeds[0])
    deterministic_replay = (
        first_state[0] == replay_state[0]
        and first_state[1] == replay_state[1]
        and np.array_equal(first_state[2], replay_state[2])
    )
    total = sum(row["survivors_total"] for row in rows)
    found = sum(row["survivors_found"] for row in rows)
    false_confirmations = sum(row["false_confirmations"] for row in rows)
    precision = found / (found + false_confirmations) if found else 1.0
    result = {
        "episodes": len(rows),
        "generation_property_cases": len(generation_rows),
        "distinct_dimensions": len({row["dimensions"] for row in rows}),
        "survivors_found": found,
        "survivors_total": total,
        "survivor_recall": found / total,
        "confirmation_precision": precision,
        "mean_coverage": sum(row["coverage"] for row in rows) / len(rows),
        "minimum_irregularity": min(row["irregularity"] for row in rows),
        "collisions": sum(row["collisions"] for row in rows),
        "duplicate_goal_steps": sum(row["duplicate_goal_steps"] for row in rows),
        "false_confirmations": false_confirmations,
        "minimum_steps_per_second": min(row["steps_per_second"] for row in rows),
        "all_survivors_found_episodes": sum(
            row["survivors_found"] == row["survivors_total"] for row in rows
        ),
        "deterministic_replay": deterministic_replay,
    }
    result["passed"] = (
        result["survivor_recall"] >= MIN_SURVIVOR_RECALL
        and result["confirmation_precision"] >= MIN_CONFIRMATION_PRECISION
        and result["mean_coverage"] >= MIN_MEAN_COVERAGE
        and result["minimum_irregularity"] >= MIN_IRREGULARITY
        and result["collisions"] <= MAX_COLLISIONS
        and result["duplicate_goal_steps"] <= MAX_DUPLICATE_GOAL_STEPS
        and result["minimum_steps_per_second"] >= MIN_STEPS_PER_SECOND
        and result["distinct_dimensions"] == len(rows)
        and result["deterministic_replay"]
    )
    (args.output / "audit_summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    fields = [
        "seed", "height", "width", "dimensions", "agents", "steps",
        "survivors_total", "survivors_found", "coverage", "irregularity",
        "traversable_cells", "map_fingerprint", "collisions",
        "duplicate_goal_steps", "false_confirmations", "map_exchange_events",
        "elapsed_seconds", "steps_per_second",
    ]
    with (args.output / "episodes.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row[field] for field in fields} for row in rows)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit("FAIL: Step 2.5 scalability gates were not met")
    print("PASS: Step 2.5 random-shape scalability gates met")


if __name__ == "__main__":
    main()
