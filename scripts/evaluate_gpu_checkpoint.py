"""Evaluate a GPU-v1 checkpoint on all development cohorts."""

import argparse
import hashlib
import json
from pathlib import Path

import ray

from swarm_sar.learning.cohort_evaluation import evaluate_cohorts, write_evaluation
from swarm_sar.learning.training import DRONE_POLICY, ROVER_POLICY, build_ppo_config, training_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/training_gpu_a5000.yaml"))
    parser.add_argument("--cohorts", type=Path, default=Path("configs/evaluation_cohorts.yaml"))
    parser.add_argument("--evaluation-index", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--include-baselines", action="store_true")
    parser.add_argument("--max-steps-override", type=int)
    parser.add_argument("--seed-split", choices=["development", "final"], default="development")
    parser.add_argument("--acknowledge-final-after-freeze", action="store_true")
    parser.add_argument("--rollout-output", type=Path)
    args = parser.parse_args()
    config = training_config(args.config)
    config.update(num_env_runners=0, num_gpus_per_learner=0)
    ray.init(include_dashboard=False, num_cpus=2, log_to_driver=False)
    algorithm = None
    try:
        algorithm = build_ppo_config(config).build_algo()
        algorithm.restore_from_path(str(args.checkpoint.resolve()))
        report = evaluate_cohorts(
            {name: algorithm.get_module(name) for name in (ROVER_POLICY, DRONE_POLICY)},
            evaluation_index=args.evaluation_index,
            config_path=args.cohorts,
            seed_splits_path=config.get("seed_splits_path"),
            smoke=args.smoke,
            include_baselines=args.include_baselines,
            max_steps_override=args.max_steps_override,
            seed_split=args.seed_split,
            acknowledge_final=args.acknowledge_final_after_freeze,
            rollout_output=args.rollout_output,
            training_probe_config=config,
        )
        digest = hashlib.sha256()
        for file in sorted(args.checkpoint.resolve().rglob("*")):
            if file.is_file():
                digest.update(file.relative_to(args.checkpoint.resolve()).as_posix().encode())
                with file.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(block)
        report["checkpoint_provenance"] = {
            "path": str(args.checkpoint.resolve()),
            "tree_sha256": digest.hexdigest(),
            "cohort_config_sha256": hashlib.sha256(args.cohorts.read_bytes()).hexdigest(),
            "training_config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        }
        write_evaluation(report, args.output)
        print(json.dumps(report["summary"], indent=2))
    finally:
        if algorithm is not None:
            algorithm.stop()
        ray.shutdown()


if __name__ == "__main__":
    main()
