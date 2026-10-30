"""Paired cohort evaluation with fixed, shadow, and sealed final cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from swarm_sar.learning.expert_evaluation import evaluate_reference
from swarm_sar.learning.inference import evaluate_modules
from swarm_sar.learning.training import training_config, rllib_env_config
from swarm_sar.utils.config import load_config
from swarm_sar.validation.seeds import load_seed_splits


def cohort_definition(path: str | Path | None = None) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4]
    definition = load_config(path or root / "training/configs/evaluation_cohorts.yaml")
    names = [cohort["name"] for cohort in definition["cohorts"]]
    if not names or len(names) != len(set(names)):
        raise ValueError("Evaluation cohorts need unique names")
    return definition


def evaluation_seeds(*, split: range, fixed_count: int, rotating_count: int,
                     evaluation_index: int) -> list[int]:
    if evaluation_index < 0:
        raise ValueError("evaluation_index cannot be negative")
    if fixed_count < 1 or rotating_count < 0 or fixed_count + rotating_count > len(split):
        raise ValueError("Invalid fixed/rotating evaluation seed counts")
    fixed, pool = list(split)[:fixed_count], list(split)[fixed_count:]
    if not pool or rotating_count == 0:
        return fixed
    start = (evaluation_index * rotating_count) % len(pool)
    return fixed + [pool[(start + offset) % len(pool)] for offset in range(rotating_count)]


def bootstrap_recall_interval(rows: list[dict[str, Any]]) -> list[float]:
    """Resample complete episodes, never pretend victims are independent trials."""
    if len(rows) < 2:
        return [0.0, 1.0]
    found = np.asarray([row["survivors_found"] for row in rows], dtype=float)
    totals = np.asarray([row["survivors_total"] for row in rows], dtype=float)
    indices = np.random.default_rng(0x4556414C).integers(0, len(rows), size=(1000, len(rows)))
    recalls = found[indices].sum(axis=1) / np.maximum(1, totals[indices].sum(axis=1))
    return np.quantile(recalls, [0.025, 0.975]).tolist()


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("Cannot aggregate an empty evaluation cohort")
    for row in rows:
        if not 0 <= row["survivors_found"] <= row["survivors_total"]:
            raise ValueError("Invalid survivor counts")
        if not np.isfinite(row["coverage"]) or not 0 <= row["coverage"] <= 1:
            raise ValueError("Invalid coverage value")
    total = sum(row["survivors_total"] for row in rows)
    found = sum(row["survivors_found"] for row in rows)
    policies = ("rover_policy", "drone_policy")
    counts = {policy: np.sum([np.asarray(row["action_counts"][policy], dtype=np.int64) for row in rows], axis=0)
              for policy in policies}
    distributions = {policy: (values / max(1, values.sum())).tolist() for policy, values in counts.items()}
    completed = [row for row in rows if row["survivors_found"] == row["survivors_total"]]
    return {
        "episodes": len(rows), "survivors_found": int(found), "survivors_total": int(total),
        "survivor_recall": found / max(1, total),
        "recall_episode_bootstrap_ci95": bootstrap_recall_interval(rows),
        "confidence_note": "Conditional episode bootstrap; few cases give weak evidence and cannot establish real-world reliability.",
        "completion_rate": len(completed) / len(rows),
        "mean_coverage": float(np.mean([row["coverage"] for row in rows])),
        "mean_steps": float(np.mean([row["steps"] for row in rows])),
        "mean_time_to_all_victims": float(np.mean([
            row["time_to_all_victims"] if row["time_to_all_victims"] is not None else row["steps"] for row in rows])),
        "mean_completion_steps_completed_only": float(np.mean([row["steps"] for row in completed])) if completed else None,
        "collisions": int(sum(row["collisions"] for row in rows)),
        "invalid_actions": int(sum(row["invalid_actions"] for row in rows)),
        "safety_interventions": (
            int(sum(row["safety_interventions"] for row in rows))
            if all("safety_interventions" in row for row in rows) else None
        ),
        "action_counts": {policy: values.tolist() for policy, values in counts.items()},
        "action_distribution": distributions,
        "dominant_action_ratio": {policy: max(values) for policy, values in distributions.items()},
        "mean_action_entropy": {
            policy: float(sum(row["mean_action_entropy"][policy] * sum(row["action_counts"][policy]) for row in rows)
                          / max(1, int(counts[policy].sum()))) for policy in policies},
    }


def paired_recall_difference(learned: list[dict], reference: list[dict]) -> dict[str, Any]:
    if [row["seed"] for row in learned] != [row["seed"] for row in reference]:
        raise ValueError("Paired comparison requires identical ordered seeds")
    if [row["survivors_total"] for row in learned] != [row["survivors_total"] for row in reference]:
        raise ValueError("Paired reference cases have different victim totals")
    differences = np.asarray([left["survivors_found"] - right["survivors_found"] for left, right in zip(learned, reference)], dtype=float)
    totals = np.asarray([row["survivors_total"] for row in learned], dtype=float)
    if len(learned) >= 2:
        indices = np.random.default_rng(0x50414952).integers(0, len(learned), size=(1000, len(learned)))
        samples = differences[indices].sum(axis=1) / np.maximum(1, totals[indices].sum(axis=1))
        interval = np.quantile(samples, [0.025, 0.975]).tolist()
    else:
        interval = [-1.0, 1.0]
    return {"learned_minus_reference_recall": float(differences.sum() / max(1, totals.sum())),
            "episode_bootstrap_ci95": interval, "paired_episode_count": len(learned)}


def _mean_recall(cohorts: dict[str, Any], subgroup: str = "metrics") -> float:
    return float(np.mean([report[subgroup]["survivor_recall"] for report in cohorts.values()]))


def matched_training_probe(modules, *, train_seeds, development_seeds, config=None, max_steps_override=None):
    """Reconstruct real training cases and sample matched unseen-domain cases."""
    config = config or training_config(Path(__file__).resolve().parents[4] / "training/configs/training_gpu_a5000.yaml")
    env_config = rllib_env_config(config, training_seed_range=None, curriculum=False)
    # Explicit reset seeds select the same seed-keyed team/map/stress settings
    # as training, rather than applying training-range numbers to a new map.
    env_config.update(fixed_team_profile=None, randomization_seed=int(config["seed"]))
    kwargs = dict(team_profile={"rover": 2, "drone": 2}, network_enabled=True,
                  stochastic=False, env_config_overrides=env_config)
    if max_steps_override is not None:
        env_config["max_steps"] = int(max_steps_override)
    train_rows = evaluate_modules(modules, seeds=train_seeds, **kwargs)
    development_rows = evaluate_modules(modules, seeds=development_seeds, **kwargs)
    return {"seeds": train_seeds, "metrics": aggregate_rows(train_rows), "episodes": train_rows,
            "matched_development": {"seeds": development_seeds, "metrics": aggregate_rows(development_rows), "episodes": development_rows}}


def evaluate_cohorts(
    modules: dict[str, Any], *, evaluation_index: int,
    config_path: str | Path | None = None, seed_splits_path: str | Path | None = None,
    smoke: bool = False, include_baselines: bool = False, seed_split: str = "development",
    acknowledge_final: bool = False, max_steps_override: int | None = None,
    include_train_probe: bool = True, rollout_output: str | Path | None = None,
    training_probe_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    definition, splits = cohort_definition(config_path), load_seed_splits(seed_splits_path)
    if seed_split not in {"development", "final"}:
        raise ValueError("Only development or explicitly acknowledged final evaluation is supported")
    if seed_split == "final" and not acknowledge_final:
        raise ValueError("Final seeds are sealed; freeze the candidate and explicitly acknowledge final evaluation")
    if seed_split == "final" and (smoke or max_steps_override is not None):
        raise ValueError("Final evaluation cannot use smoke mode or shortened episode budgets")
    if max_steps_override is not None and max_steps_override < 1:
        raise ValueError("max_steps_override must be positive")
    fixed_count, rotating_count = int(definition["fixed_seed_count"]), int(definition["rotating_seed_count"])
    if seed_split == "final":
        fixed_seeds, shadow_seeds = list(splits["final"]), []
    else:
        selected = evaluation_seeds(split=splits["development"], fixed_count=fixed_count,
                                    rotating_count=rotating_count, evaluation_index=evaluation_index)
        fixed_seeds, shadow_seeds = selected[:fixed_count], selected[fixed_count:]
        if smoke:
            fixed_seeds, shadow_seeds = fixed_seeds[:1], shadow_seeds[:1]
    seeds, cohort_reports = fixed_seeds + shadow_seeds, {}
    references = {"expert": "expert", "random_masked": "random", "frontier0": "mask_only"}
    for cohort in definition["cohorts"]:
        print(json.dumps({"evaluation_cohort": cohort["name"], "phase": "learned", "episodes": len(seeds)}), flush=True)
        kwargs = {"seeds": seeds, "team_profile": cohort["team_profile"],
                  "network_enabled": bool(cohort.get("network_enabled", True)),
                  "max_steps": int(max_steps_override or cohort["max_steps"]),
                  "world_size": int(cohort["world_size"]),
                  "sim_overrides": cohort.get("sim_overrides", {}),
                  "robot_stress": cohort.get("robot_stress", {}),
                  "world_overrides": cohort.get("world_overrides", {})}
        inference_kwargs = dict(kwargs)
        if rollout_output is not None:
            inference_kwargs["rollout_output"] = Path(rollout_output) / cohort["name"]
        rows = evaluate_modules(modules, stochastic=False, **inference_kwargs)
        fixed_rows, shadow_rows = rows[:len(fixed_seeds)], rows[len(fixed_seeds):]
        report = {"definition": cohort, "effective_max_steps": kwargs["max_steps"],
                  "metrics": aggregate_rows(rows), "fixed": aggregate_rows(fixed_rows),
                  "shadow": aggregate_rows(shadow_rows) if shadow_rows else aggregate_rows(fixed_rows),
                  "episodes": rows}
        if include_baselines:
            report["baselines"] = {}
            for public_name, internal_name in references.items():
                print(json.dumps({"evaluation_cohort": cohort["name"], "phase": public_name, "episodes": len(seeds)}), flush=True)
                baseline_rows = evaluate_reference(internal_name, **kwargs)
                report["baselines"][public_name] = {
                    "metrics": aggregate_rows(baseline_rows),
                    "fixed": aggregate_rows(baseline_rows[:len(fixed_seeds)]),
                    "paired": paired_recall_difference(rows, baseline_rows), "episodes": baseline_rows}
        cohort_reports[cohort["name"]] = report
    summary = {
        "minimum_cohort_recall": min(report["metrics"]["survivor_recall"] for report in cohort_reports.values()),
        "mean_cohort_recall": _mean_recall(cohort_reports),
        "fixed_mean_recall": _mean_recall(cohort_reports, "fixed"),
        "fixed_mean_cohort_recall": _mean_recall(cohort_reports, "fixed"),
        "shadow_mean_recall": _mean_recall(cohort_reports, "shadow"),
        "shadow_mean_cohort_recall": _mean_recall(cohort_reports, "shadow"),
        "fixed_shadow_gap": _mean_recall(cohort_reports, "fixed") - _mean_recall(cohort_reports, "shadow"),
        "minimum_cohort_coverage": min(report["metrics"]["mean_coverage"] for report in cohort_reports.values()),
        "invalid_actions": sum(report["metrics"]["invalid_actions"] for report in cohort_reports.values()),
        "collisions": sum(report["metrics"]["collisions"] for report in cohort_reports.values()),
        "maximum_dominant_action_ratio": max(ratio for report in cohort_reports.values() for ratio in report["metrics"]["dominant_action_ratio"].values()),
        "diagnostic_only": bool(smoke or max_steps_override is not None),
    }
    train_probe = None
    if include_train_probe and seed_split == "development":
        count = min(int(definition.get("train_probe_seed_count", 2)), len(splits["train"]), len(fixed_seeds))
        probe_seeds = list(splits["train"])[:count]
        train_probe = matched_training_probe(modules, train_seeds=probe_seeds,
                                            development_seeds=fixed_seeds[:count], config=training_probe_config,
                                            max_steps_override=max_steps_override)
        summary["train_probe_recall"] = train_probe["metrics"]["survivor_recall"]
        summary["matched_development_probe_recall"] = train_probe["matched_development"]["metrics"]["survivor_recall"]
        summary["train_development_gap"] = summary["train_probe_recall"] - summary["matched_development_probe_recall"]
        summary["train_probe_note"] = "Exact seed-keyed training configuration; few cases and seeds not yet sampled by PPO make this a diagnostic, not a proof of memorization."
    if include_baselines:
        summary["baseline_mean_recalls"] = {name: float(np.mean([
            report["baselines"][name]["metrics"]["survivor_recall"] for report in cohort_reports.values()])) for name in references}
        summary["baseline_fixed_mean_recalls"] = {name: float(np.mean([
            report["baselines"][name]["fixed"]["survivor_recall"] for report in cohort_reports.values()])) for name in references}
        summary["baseline_mean_recall"] = summary["baseline_mean_recalls"]["expert"]
    return {"schema_version": 2, "evaluation_index": evaluation_index,
            "seed_split": seed_split, "seeds": seeds, "fixed_seeds": fixed_seeds,
            "shadow_seeds": shadow_seeds, "final_seeds_used": seed_split == "final",
            "final_acknowledged": acknowledge_final, "cohorts": cohort_reports,
            "train_probe": train_probe, "summary": summary}


def write_evaluation(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(target)
