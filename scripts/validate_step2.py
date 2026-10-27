"""Validate the Step 2 mapping and coordinated frontier baseline."""

import argparse
import json
from pathlib import Path

from swarm_sar.baselines.frontier import CoordinatedFrontierBaseline


REQUIRED_EDGE_FIELDS = {
    "estimated_distance",
    "traversability",
    "observation_confidence",
    "last_update",
}


def validate_episode(seed: int, output_root: Path) -> dict:
    baseline = CoordinatedFrontierBaseline()
    summary = baseline.run_episode(seed, output_root / f"seed_{seed}")
    assert len(baseline.maps) == 4
    assert len({id(mapping) for mapping in baseline.maps.values()}) == 4
    assert summary["reservations_made"] > 0
    assert summary["duplicate_goal_steps"] == 0
    assert summary["collisions"] == 0
    assert summary["false_confirmations"] == 0
    assert summary["survivors_found"] == summary["survivors_total"]
    assert summary["confirmed_markers"] >= summary["survivors_found"]
    for agent, mapping in baseline.maps.items():
        assert mapping.graph.number_of_nodes() > 0, agent
        assert mapping.graph.number_of_edges() > 0, agent
        for _, _, data in mapping.graph.edges(data=True):
            assert REQUIRED_EDGE_FIELDS <= set(data)
    folder = output_root / f"seed_{seed}"
    assert (folder / "baseline_summary.json").exists()
    assert (folder / "baseline_events.json").exists()
    assert len(list((folder / "topology").glob("*.json"))) == 4
    assert (folder / "episode/map.json").exists()
    assert (folder / "episode/trajectories.csv").exists()
    baseline.env.close()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=list(range(20)))
    parser.add_argument("--output", type=Path, default=Path("results/step2_validation"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = [validate_episode(seed, args.output) for seed in args.seeds]
    total = sum(row["survivors_total"] for row in rows)
    found = sum(row["survivors_found"] for row in rows)
    result = {
        "seeds": args.seeds,
        "episodes": len(rows),
        "survivors_found": found,
        "survivors_total": total,
        "survivor_recall": found / total,
        "mean_coverage": sum(row["coverage"] for row in rows) / len(rows),
        "collisions": sum(row["collisions"] for row in rows),
        "duplicate_goal_steps": sum(row["duplicate_goal_steps"] for row in rows),
        "false_confirmations": sum(row["false_confirmations"] for row in rows),
        "confirmed_markers": sum(row["confirmed_markers"] for row in rows),
    }
    assert result["survivor_recall"] >= 0.90
    assert result["mean_coverage"] >= 0.65
    assert result["collisions"] == 0
    assert result["duplicate_goal_steps"] == 0
    assert result["false_confirmations"] == 0
    (args.output / "validation_summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    print("PASS: Step 2 mapping, coordination, evidence and artifact gates")


if __name__ == "__main__":
    main()
