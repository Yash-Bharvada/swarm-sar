"""Paired development-only evaluation of a manifested GNN actor bundle.

No final-test access and no automatic promotion or browser activation.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import torch
from ray.rllib.core.rl_module.rl_module import RLModule

from experiments.gnn.attention import ARCHITECTURE
from experiments.gnn.artifacts import assert_paired_reports, verified_manifest
from experiments.gnn.module import GraphResidualPPOModule
from experiments.gnn.smoke import DEFAULT, verified_originals
from swarm_sar.learning.cohort_evaluation import evaluate_cohorts, paired_recall_difference
from swarm_sar.learning.release import atomic_json, file_hash
from swarm_sar.learning.training_gates import evaluate_gate, gate_definition


def verified_candidate(bundle):
    bundle = bundle.resolve()
    manifest = verified_manifest(bundle)
    experiment = bundle.parents[1] / "experiment.json"
    if file_hash(experiment) != manifest.get("experiment_sha256"):
        raise ValueError("Candidate experiment definition integrity failed")
    actors = {name: RLModule.from_checkpoint(str(bundle / name)).to("cpu").eval()
              for name in ("rover_policy", "drone_policy")}
    if not all(isinstance(actor, GraphResidualPPOModule) for actor in actors.values()):
        raise ValueError("Candidate is not a graph policy")
    if any(not torch.isfinite(p).all() for actor in actors.values() for p in actor.parameters()):
        raise ValueError("Candidate contains non-finite parameters")
    return actors, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True, help="run/actors/step_... directory")
    parser.add_argument("--baseline", type=Path, default=DEFAULT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true", help="Short diagnostic; never promotion evidence")
    parser.add_argument("--ablation", action="store_true", help="Also evaluate trained trunk with graph residual disabled")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a fresh output directory")
    torch.set_num_threads(1)
    originals, digest = verified_originals(args.baseline)
    candidate, manifest = verified_candidate(args.candidate)
    if manifest.get("base_checkpoint_sha256") != digest:
        raise ValueError("Candidate was not initialized from this original checkpoint")
    args.output.mkdir(parents=True)
    kwargs = {"evaluation_index": 0, "seed_split": "development", "smoke": args.smoke,
              "max_steps_override": 48 if args.smoke else None, "include_train_probe": False}
    original_report = evaluate_cohorts(originals, **kwargs)
    atomic_json(args.output / "original_ppo.json", original_report)
    candidate_report = evaluate_cohorts(candidate, include_baselines=True, **kwargs)
    atomic_json(args.output / "gnn_ppo.json", candidate_report)
    assert_paired_reports(original_report, candidate_report)
    comparisons = {}
    for name, report in candidate_report["cohorts"].items():
        comparisons[name] = paired_recall_difference(
            report["episodes"], original_report["cohorts"][name]["episodes"])
    gate = evaluate_gate(candidate_report, env_steps=manifest["env_steps"],
                         definition=gate_definition(), recall_history=[candidate_report["summary"]["fixed_mean_recall"]],
                         reference_recall=original_report["summary"]["fixed_mean_recall"])
    ablation_summary = None
    if args.ablation:
        disabled = copy.deepcopy(candidate)
        with torch.no_grad():
            for actor in disabled.values():
                actor.graph_adapter.residual.weight.zero_()
                actor.graph_adapter.residual.bias.zero_()
        ablation_report = evaluate_cohorts(disabled, **kwargs)
        assert_paired_reports(original_report, ablation_report)
        atomic_json(args.output / "disabled_graph.json", ablation_report)
        ablation_summary = ablation_report["summary"]
    atomic_json(args.output / "comparison.json", {
        "architecture": ARCHITECTURE, "candidate_manifest_sha256": file_hash(args.candidate / "manifest.json"),
        "base_checkpoint_sha256": digest, "diagnostic_only": args.smoke,
        "final_seeds_used": False, "automatically_promoted": False,
        "original": original_report["summary"], "candidate": candidate_report["summary"],
        "paired_by_cohort": comparisons,
        "quality_gate": gate,
        "trained_trunk_without_graph": ablation_summary,
        "interpretation": "Development comparison only; inspect all cohorts and gates before promotion."})
    print(json.dumps({"output": str(args.output), "diagnostic_only": args.smoke,
                      "promoted": False}, indent=2))


if __name__ == "__main__":
    main()
