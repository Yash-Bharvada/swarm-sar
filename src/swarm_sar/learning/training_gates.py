"""Fail-closed health and quality gates for long GPU training runs."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from swarm_sar.utils.config import load_config


def gate_definition(path: str | Path | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3]
    return load_config(path or root / "configs/training_gates.yaml")


def iteration_health(row: dict[str, Any]) -> list[str]:
    failures = []
    for field in ("episode_return_mean", "episode_length_mean", "rover_policy_loss", "drone_policy_loss"):
        value = float(row[field])
        if not math.isfinite(value):
            failures.append(f"non_finite:{field}")
    if int(row.get("env_steps", 0)) <= 0:
        failures.append("no_environment_progress")
    return failures


def applicable_stage(definition: dict[str, Any], env_steps: int) -> dict[str, Any] | None:
    eligible = [stage for stage in definition["stages"] if env_steps >= int(stage["env_steps"])]
    return eligible[-1] if eligible else None


def evaluate_gate(
    report: dict[str, Any],
    *,
    env_steps: int,
    definition: dict[str, Any],
    recall_history: list[float],
) -> dict[str, Any]:
    summary = report["summary"]
    abort_reasons = []
    pause_reasons = []
    if int(summary["invalid_actions"]) > int(definition["hard_abort"]["max_invalid_actions"]):
        abort_reasons.append("invalid_actions")
    if int(summary["collisions"]) > int(definition["hard_abort"]["max_collisions_per_evaluation"]):
        abort_reasons.append("collision_explosion")
    if float(summary["maximum_dominant_action_ratio"]) > float(definition["quality"]["max_dominant_action_ratio"]):
        pause_reasons.append("policy_action_collapse")
    stage = applicable_stage(definition, env_steps)
    if stage is not None:
        if float(summary["mean_cohort_recall"]) < float(stage["min_mean_recall"]):
            pause_reasons.append("stage_mean_recall")
        if float(summary["minimum_cohort_recall"]) < float(stage["min_worst_recall"]):
            pause_reasons.append("stage_worst_recall")
        if float(summary["minimum_cohort_coverage"]) < float(stage["min_worst_coverage"]):
            pause_reasons.append("stage_worst_coverage")
    window = int(definition["quality"]["plateau_evaluations"])
    if len(recall_history) >= window:
        recent = recall_history[-window:]
        if max(recent) - min(recent) < float(definition["quality"]["minimum_recall_improvement"]):
            pause_reasons.append("recall_plateau")
    status = "abort" if abort_reasons else "pause" if pause_reasons else "continue"
    return {
        "status": status,
        "stage": stage["name"] if stage else "warmup",
        "abort_reasons": abort_reasons,
        "pause_reasons": pause_reasons,
    }
