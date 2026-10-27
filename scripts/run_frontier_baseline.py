"""Run and save the coordinated non-learning Step 2 benchmark."""

import argparse
import csv
import json
from pathlib import Path

from swarm_sar.baselines.frontier import CoordinatedFrontierBaseline
from swarm_sar.sim.env import DisasterResponseParallelEnv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=list(range(20)))
    parser.add_argument("--output", type=Path, default=Path("results/frontier_baseline"))
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in args.seeds:
        baseline = CoordinatedFrontierBaseline(
            DisasterResponseParallelEnv(render_mode="human" if args.render else None)
        )
        summary = baseline.run_episode(seed, args.output / f"seed_{seed}")
        rows.append(summary)
        baseline.env.close()
        print(
            f"seed {seed:3d}: survivors={summary['survivors_found']}/"
            f"{summary['survivors_total']} coverage={summary['coverage']:.1%} "
            f"steps={summary['steps']} collisions={summary['collisions']}"
        )
    total_survivors = sum(row["survivors_total"] for row in rows)
    aggregate = {
        "seeds": args.seeds,
        "episodes": len(rows),
        "survivors_total": total_survivors,
        "survivors_found": sum(row["survivors_found"] for row in rows),
        "survivor_recall": sum(row["survivors_found"] for row in rows) / total_survivors,
        "mean_coverage": sum(row["coverage"] for row in rows) / len(rows),
        "all_survivors_found_episodes": sum(
            row["survivors_found"] == row["survivors_total"] for row in rows
        ),
        "collisions": sum(row["collisions"] for row in rows),
        "duplicate_goal_steps": sum(row["duplicate_goal_steps"] for row in rows),
        "false_confirmations": sum(row["false_confirmations"] for row in rows),
    }
    (args.output / "aggregate.json").write_text(
        json.dumps(aggregate, indent=2), encoding="utf-8"
    )
    flat_fields = [
        "seed",
        "steps",
        "survivors_total",
        "survivors_found",
        "coverage",
        "collisions",
        "reservations_made",
        "duplicate_goal_steps",
        "evidence_clusters",
        "verification_failures",
        "false_confirmations",
        "confirmed_markers",
    ]
    with (args.output / "episodes.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=flat_fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in flat_fields} for row in rows)
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
