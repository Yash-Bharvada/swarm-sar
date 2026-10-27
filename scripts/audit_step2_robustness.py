"""No-tuning holdout and stress audit used to freeze the Step 2 baseline."""

import argparse
import csv
import json
from pathlib import Path

from swarm_sar.baselines.frontier import CoordinatedFrontierBaseline
from swarm_sar.sim.env import DisasterResponseParallelEnv
from swarm_sar.validation.robustness import (
    MAX_COLLISIONS,
    MAX_DUPLICATE_GOAL_STEPS,
    MIN_CONFIRMATION_PRECISION,
    MIN_SURVIVOR_RECALL,
    stressed_configs,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=list(range(100, 120)))
    parser.add_argument("--output", type=Path, default=Path("results/step2_robustness"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    audit_definition = {
        "seeds": args.seeds,
        "map_sizes": [24, 32, 40],
        "thermal_noise_multiplier": 1.5,
        "acoustic_noise_multiplier": 1.5,
        "detection_probability_delta": -0.10,
        "false_positive_rate_delta": 0.05,
        "odometry_drift_multiplier": 2.0,
        "battery_multiplier": 0.85,
        "gates": {
            "minimum_survivor_recall": MIN_SURVIVOR_RECALL,
            "minimum_confirmation_precision": MIN_CONFIRMATION_PRECISION,
            "maximum_collisions": MAX_COLLISIONS,
            "maximum_duplicate_goal_steps": MAX_DUPLICATE_GOAL_STEPS,
        },
    }
    (args.output / "audit_definition.json").write_text(
        json.dumps(audit_definition, indent=2), encoding="utf-8"
    )

    rows = []
    for index, seed in enumerate(args.seeds):
        world, robots, sim, size = stressed_configs(index)
        env = DisasterResponseParallelEnv(
            world_config=world,
            robot_config=robots,
            sim_config=sim,
        )
        baseline = CoordinatedFrontierBaseline(env)
        summary = baseline.run_episode(seed, args.output / f"seed_{seed}")
        summary["map_size"] = size
        rows.append(summary)
        env.close()
        print(
            f"seed {seed}: size={size} survivors={summary['survivors_found']}/"
            f"{summary['survivors_total']} coverage={summary['coverage']:.1%} "
            f"steps={summary['steps']}"
        )

    total = sum(row["survivors_total"] for row in rows)
    found = sum(row["survivors_found"] for row in rows)
    false_confirmations = sum(row["false_confirmations"] for row in rows)
    precision = found / (found + false_confirmations) if found + false_confirmations else 1.0
    result = {
        "episodes": len(rows),
        "survivors_found": found,
        "survivors_total": total,
        "survivor_recall": found / total,
        "confirmation_precision": precision,
        "mean_coverage": sum(row["coverage"] for row in rows) / len(rows),
        "collisions": sum(row["collisions"] for row in rows),
        "duplicate_goal_steps": sum(row["duplicate_goal_steps"] for row in rows),
        "false_confirmations": false_confirmations,
        "all_survivors_found_episodes": sum(
            row["survivors_found"] == row["survivors_total"] for row in rows
        ),
    }
    result["passed"] = (
        result["survivor_recall"] >= MIN_SURVIVOR_RECALL
        and result["confirmation_precision"] >= MIN_CONFIRMATION_PRECISION
        and result["collisions"] <= MAX_COLLISIONS
        and result["duplicate_goal_steps"] <= MAX_DUPLICATE_GOAL_STEPS
    )
    (args.output / "audit_summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    fields = [
        "seed",
        "map_size",
        "steps",
        "survivors_total",
        "survivors_found",
        "coverage",
        "collisions",
        "duplicate_goal_steps",
        "false_confirmations",
        "confirmed_markers",
    ]
    with (args.output / "episodes.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row[field] for field in fields} for row in rows)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit("FAIL: Step 2 robustness gates were not met; do not freeze")
    print("PASS: unseen stressed holdout met the predeclared Step 2 freeze gates")


if __name__ == "__main__":
    main()
