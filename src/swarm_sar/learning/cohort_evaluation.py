"""Disjoint, repeatable evaluation cohorts and anti-collapse metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from swarm_sar.learning.inference import evaluate_modules
from swarm_sar.utils.config import load_config
from swarm_sar.validation.seeds import load_seed_splits


def cohort_definition(path: str | Path | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3]
    return load_config(path or root / "configs/evaluation_cohorts.yaml")


def evaluation_seeds(
    *, split: range, fixed_count: int, rotating_count: int, evaluation_index: int
) -> list[int]:
    if fixed_count < 1 or rotating_count < 0 or fixed_count + rotating_count > len(split):
        raise ValueError("Invalid fixed/rotating evaluation seed counts")
    fixed = list(split)[:fixed_count]
    pool = list(split)[fixed_count:]
    if not pool or rotating_count == 0:
        return fixed
    start = (evaluation_index * rotating_count) % len(pool)
    rotating = [pool[(start + offset) % len(pool)] for offset in range(rotating_count)]
    return fixed + rotating


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("Cannot aggregate an empty evaluation cohort")
    total = sum(row["survivors_total"] for row in rows)
    found = sum(row["survivors_found"] for row in rows)
    policies = ("rover_policy", "drone_policy")
    action_counts = {
        policy: np.sum(
            [np.asarray(row["action_counts"][policy], dtype=np.int64) for row in rows],
            axis=0,
        )
        for policy in policies
    }
    action_distribution = {
        policy: (counts / max(1, counts.sum())).tolist()
        for policy, counts in action_counts.items()
    }
    return {
        "episodes": len(rows),
        "survivor_recall": found / max(1, total),
        "completion_rate": sum(row["survivors_found"] == row["survivors_total"] for row in rows)
        / len(rows),
        "mean_coverage": float(np.mean([row["coverage"] for row in rows])),
        "mean_steps": float(np.mean([row["steps"] for row in rows])),
        "mean_time_to_all_victims": float(
            np.mean(
                [
                    row["time_to_all_victims"]
                    if row["time_to_all_victims"] is not None
                    else row["steps"]
                    for row in rows
                ]
            )
        ),
        "collisions": int(sum(row["collisions"] for row in rows)),
        "invalid_actions": int(sum(row["invalid_actions"] for row in rows)),
        "action_counts": {policy: counts.tolist() for policy, counts in action_counts.items()},
        "action_distribution": action_distribution,
        "dominant_action_ratio": {
            policy: max(distribution) if distribution else 0.0
            for policy, distribution in action_distribution.items()
        },
        "mean_action_entropy": {
            policy: float(np.mean([row["mean_action_entropy"][policy] for row in rows]))
            for policy in policies
        },
    }


def evaluate_cohorts(
    modules: dict[str, Any],
    *,
    evaluation_index: int,
    config_path: str | Path | None = None,
    seed_splits_path: str | Path | None = None,
    smoke: bool = False,
) -> dict[str, Any]:
    definition = cohort_definition(config_path)
    splits = load_seed_splits(seed_splits_path)
    seeds = evaluation_seeds(
        split=splits["development"],
        fixed_count=int(definition["fixed_seed_count"]),
        rotating_count=int(definition["rotating_seed_count"]),
        evaluation_index=evaluation_index,
    )
    if set(seeds).intersection(splits["final"]):
        raise AssertionError("Development evaluation touched sealed final seeds")
    cohort_reports = {}
    for cohort in definition["cohorts"]:
        cohort_seeds = seeds[:1] if smoke else seeds
        rows = evaluate_modules(
            modules,
            seeds=cohort_seeds,
            team_profile=cohort["team_profile"],
            network_enabled=bool(cohort.get("network_enabled", True)),
            max_steps=int(cohort["max_steps"]),
            world_size=int(cohort["world_size"]),
            stochastic=False,
            sim_overrides=cohort.get("sim_overrides", {}),
            robot_stress=cohort.get("robot_stress", {}),
        )
        cohort_reports[cohort["name"]] = {
            "definition": cohort,
            "metrics": aggregate_rows(rows),
            "episodes": rows,
        }
    recalls = [report["metrics"]["survivor_recall"] for report in cohort_reports.values()]
    coverages = [report["metrics"]["mean_coverage"] for report in cohort_reports.values()]
    return {
        "schema_version": 1,
        "evaluation_index": evaluation_index,
        "seed_split": "development",
        "seeds": seeds[:1] if smoke else seeds,
        "final_seeds_used": False,
        "cohorts": cohort_reports,
        "summary": {
            "minimum_cohort_recall": min(recalls),
            "mean_cohort_recall": float(np.mean(recalls)),
            "minimum_cohort_coverage": min(coverages),
            "invalid_actions": sum(
                report["metrics"]["invalid_actions"] for report in cohort_reports.values()
            ),
            "collisions": sum(
                report["metrics"]["collisions"] for report in cohort_reports.values()
            ),
            "maximum_dominant_action_ratio": max(
                ratio
                for report in cohort_reports.values()
                for ratio in report["metrics"]["dominant_action_ratio"].values()
            ),
        },
    }


def write_evaluation(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
