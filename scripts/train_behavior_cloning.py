"""Class-balanced rover/drone behavior cloning for GPU-v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import ray
import torch

from swarm_sar.learning.behavior_cloning import (
    clone_summary_passed,
    expert_seed_split,
    load_expert_arrays,
    train_policy_clone,
)
from swarm_sar.learning.demonstrations import sha256_file
from swarm_sar.learning.training import (
    DRONE_POLICY,
    ROVER_POLICY,
    build_ppo_config,
    training_config,
)
from swarm_sar.policy_contract import policy_contract


def parameter_hash(module) -> str:
    digest = hashlib.sha256()
    for parameter in module.parameters():
        digest.update(parameter.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def prepare_output(path: Path) -> Path:
    output = path.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite behavior-cloning output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/training_gpu_a5000.yaml"))
    parser.add_argument("--output", type=Path, default=Path("results/behavior_cloning_v1"))
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--validation-fraction", type=float, default=0.10)
    parser.add_argument("--num-cpus", type=int, default=4)
    parser.add_argument("--num-gpus", type=float, default=1.0)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    output = prepare_output(args.output)
    arrays, manifest = load_expert_arrays(args.dataset)
    train_seeds, validation_seeds = expert_seed_split(
        manifest, args.validation_fraction
    )
    config = training_config(args.config)
    config.update(
        num_env_runners=0,
        num_cpus=args.num_cpus,
        num_gpus_per_learner=args.num_gpus,
    )
    epochs = 1 if args.smoke else args.epochs
    max_batches = 2 if args.smoke else None
    minimum_balanced_accuracy = 0.0 if args.smoke else 0.40
    maximum_overfit_gap = 1.0 if args.smoke else 0.15
    ray.init(
        include_dashboard=False,
        num_cpus=args.num_cpus,
        num_gpus=math.ceil(args.num_gpus),
        log_to_driver=False,
    )
    algorithm = None
    try:
        algorithm = build_ppo_config(config).build_algo()
        initial_hashes = {
            name: parameter_hash(algorithm.get_module(name))
            for name in (ROVER_POLICY, DRONE_POLICY)
        }
        reports = {}
        for name, policy_id in ((ROVER_POLICY, 0), (DRONE_POLICY, 1)):
            reports[name] = train_policy_clone(
                algorithm.get_module(name),
                arrays,
                policy_id=policy_id,
                train_seeds=train_seeds,
                validation_seeds=validation_seeds,
                epochs=epochs,
                batch_size=args.batch_size,
                learning_rate=args.learning_rate,
                max_seq_len=int(config["max_seq_len"]),
                seed=int(config["seed"]),
                patience=args.patience,
                max_batches=max_batches,
            )
            print(json.dumps({name: reports[name]}, indent=2), flush=True)
        final_hashes = {
            name: parameter_hash(algorithm.get_module(name))
            for name in (ROVER_POLICY, DRONE_POLICY)
        }
        # get_module() is the local EnvRunner copy on RLlib's new API stack.
        # Explicitly synchronize into the LearnerGroup, which is the copy that
        # Algorithm.save_to_path() serializes and PPO subsequently optimizes.
        algorithm.set_weights(
            {
                name: algorithm.get_module(name).get_state()
                for name in (ROVER_POLICY, DRONE_POLICY)
            }
        )
        checkpoint = Path(
            algorithm.save_to_path(str((output / "checkpoint").resolve()))
        )
        passed = (
            all(initial_hashes[name] != final_hashes[name] for name in initial_hashes)
            and clone_summary_passed(
                reports,
                minimum_balanced_accuracy=minimum_balanced_accuracy,
                maximum_overfit_gap=maximum_overfit_gap,
            )
        )
        summary = {
            "schema_version": 1,
            "dataset": str(args.dataset.resolve()),
            "dataset_manifest_sha256": sha256_file(args.dataset.resolve() / "manifest.json"),
            "policy_contract": policy_contract(),
            "train_seed_count": len(train_seeds),
            "validation_seed_count": len(validation_seeds),
            "train_seed_range": [min(train_seeds), max(train_seeds)],
            "validation_seed_range": [min(validation_seeds), max(validation_seeds)],
            "checkpoint": str(checkpoint),
            "initial_hashes": initial_hashes,
            "final_hashes": final_hashes,
            "minimum_balanced_accuracy": minimum_balanced_accuracy,
            "maximum_overfit_gap": maximum_overfit_gap,
            "reports": reports,
            "smoke": args.smoke,
            "passed": passed,
        }
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        if not passed:
            raise SystemExit("FAIL: behavior-cloning gates were not met")
    finally:
        if algorithm is not None:
            algorithm.stop()
        ray.shutdown()


if __name__ == "__main__":
    main()
