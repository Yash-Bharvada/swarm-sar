"""Fail-closed health and quality gates for long GPU training runs."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from swarm_sar.utils.config import load_config


def gate_definition(path: str | Path | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4]
    return load_config(path or root / "training/configs/training_gates.yaml")


def iteration_health(row: dict[str, Any]) -> list[str]:
    failures = []
    for field in ("episode_return_mean", "episode_length_mean", "rover_policy_loss", "drone_policy_loss"):
        if row.get(field) is None:
            # A curriculum phase can omit a policy. Absence is different from
            # a computed loss becoming NaN; per-policy updates are checked too.
            if field.endswith("policy_loss"):
                continue
            failures.append(f"missing:{field}")
            continue
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
    reference_recall: float | None = None,
    gap_history: list[float] | None = None,
    shadow_gap_history: list[float] | None = None,
) -> dict[str, Any]:
    summary = report["summary"]
    abort_reasons = []
    pause_reasons = []
    warning_reasons = []
    required = ("mean_cohort_recall", "minimum_cohort_recall", "minimum_cohort_coverage", "maximum_dominant_action_ratio")
    for field in required:
        value = summary.get(field)
        if value is None or not math.isfinite(float(value)):
            abort_reasons.append(f"non_finite_evaluation:{field}")
        elif not 0.0 <= float(value) <= 1.0:
            abort_reasons.append(f"out_of_range_evaluation:{field}")
    for field in ("fixed_mean_recall", "shadow_mean_recall", "train_probe_recall", "train_development_gap"):
        if field not in summary:
            continue
        if summary[field] is None:
            abort_reasons.append(f"non_finite_evaluation:{field}")
            continue
        value = float(summary[field])
        low = -1.0 if field == "train_development_gap" else 0.0
        if not math.isfinite(value):
            abort_reasons.append(f"non_finite_evaluation:{field}")
        elif not low <= value <= 1.0:
            abort_reasons.append(f"out_of_range_evaluation:{field}")
    for field in ("invalid_actions", "collisions"):
        value = summary.get(field)
        if value is None or not math.isfinite(float(value)) or float(value) < 0 or not float(value).is_integer():
            abort_reasons.append(f"invalid_evaluation_count:{field}")
    for label, values in (("history", recall_history), ("reference", [] if reference_recall is None else [reference_recall])):
        if any(not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0 for value in values):
            abort_reasons.append(f"invalid_evaluation:{label}")
    if gap_history is not None and any(not math.isfinite(float(value)) or not -1.0 <= float(value) <= 1.0 for value in gap_history):
        abort_reasons.append("invalid_evaluation:gap_history")
    if shadow_gap_history is not None and any(not math.isfinite(float(value)) or not -1.0 <= float(value) <= 1.0 for value in shadow_gap_history):
        abort_reasons.append("invalid_evaluation:shadow_gap_history")
    if abort_reasons:
        return {"status": "abort", "stage": "integrity", "abort_reasons": abort_reasons, "pause_reasons": [], "warning_reasons": []}
    if int(summary["invalid_actions"]) > int(definition["hard_abort"]["max_invalid_actions"]):
        abort_reasons.append("invalid_actions")
    if int(summary["collisions"]) > int(definition["hard_abort"]["max_collisions_per_evaluation"]):
        abort_reasons.append("collision_explosion")
    fixed_recall = float(summary.get("fixed_mean_recall", summary["mean_cohort_recall"]))
    if not math.isfinite(fixed_recall):
        abort_reasons.append("non_finite_evaluation:fixed_mean_recall")
    if (
        float(summary["maximum_dominant_action_ratio"]) > float(definition["quality"]["max_dominant_action_ratio"])
        and fixed_recall < float(definition["quality"].get("collapse_max_recall", 0.20))
    ):
        pause_reasons.append("policy_action_collapse")
    if reference_recall is not None and fixed_recall < reference_recall - float(definition["quality"].get("max_reference_regression", 0.10)):
        pause_reasons.append("regression_from_behavior_cloning")
    gap = summary.get("train_development_gap")
    gap_limit = float(definition["quality"].get("max_train_development_gap", 0.35))
    if gap is not None and float(gap) > gap_limit:
        warning_reasons.append("train_development_generalization_gap")
        history = list(gap_history or [])
        # A small training probe is a noisy diagnostic. Require persistent
        # failure rather than treating one four-map estimate as proof.
        required_count = int(definition["quality"].get("generalization_gap_patience", 2))
        if len(history) >= required_count and all(value > gap_limit for value in history[-required_count:]):
            pause_reasons.append("persistent_train_development_generalization_gap")
    shadow = summary.get("shadow_mean_recall")
    shadow_limit = float(definition["quality"].get("max_fixed_shadow_gap", 0.25))
    if shadow is not None and fixed_recall - float(shadow) > shadow_limit:
        warning_reasons.append("fixed_shadow_generalization_gap")
        history = list(shadow_gap_history or [])
        patience = int(definition["quality"].get("generalization_gap_patience", 2))
        if len(history) >= patience and all(value > shadow_limit for value in history[-patience:]):
            pause_reasons.append("persistent_fixed_shadow_generalization_gap")
    stage = applicable_stage(definition, env_steps)
    if stage is not None:
        if fixed_recall < float(stage["min_mean_recall"]):
            pause_reasons.append("stage_mean_recall")
        if float(summary["minimum_cohort_recall"]) < float(stage["min_worst_recall"]):
            pause_reasons.append("stage_worst_recall")
        if float(summary["minimum_cohort_coverage"]) < float(stage["min_worst_coverage"]):
            pause_reasons.append("stage_worst_coverage")
    window = int(definition["quality"]["plateau_evaluations"])
    if len(recall_history) >= window:
        recent = recall_history[-window:]
        improvement = max(recent[1:]) - recent[0]
        if improvement < float(definition["quality"]["minimum_recall_improvement"]) and recent[-1] < float(definition["quality"].get("plateau_target_recall", 0.90)):
            pause_reasons.append("recall_plateau")
    status = "abort" if abort_reasons else "pause" if pause_reasons else "continue"
    return {
        "status": status,
        "stage": stage["name"] if stage else "warmup",
        "abort_reasons": abort_reasons,
        "pause_reasons": pause_reasons,
        "warning_reasons": warning_reasons,
    }
