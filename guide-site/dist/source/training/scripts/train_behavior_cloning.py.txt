"""Class-balanced rover/drone behavior cloning for GPU-v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
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


def write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("training/configs/training_gpu_a5000.yaml"))
    parser.add_argument("--output", type=Path, default=Path("training/runs/behavior_cloning_v1"))
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--validation-fraction", type=float, default=0.10)
    parser.add_argument("--num-cpus", type=int, default=4)
    parser.add_argument("--num-gpus", type=float, default=1.0)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--max-batches", type=int, help="Diagnostic pilot: cap batches per epoch and validation")
    parser.add_argument("--max-seconds", type=float, help="Budget shared evenly between the two policies")
    parser.add_argument("--burn-in", type=int, default=16)
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1 or args.patience < 1 or args.learning_rate <= 0:
        parser.error("epochs, batch-size, patience and learning-rate must be positive")
    if args.max_batches is not None and args.max_batches < 1:
        parser.error("max-batches must be positive")
    if args.max_seconds is not None and args.max_seconds <= 0:
        parser.error("max-seconds must be positive")
    if args.burn_in < 0 or args.num_gpus < 0 or args.num_gpus > 1:
        parser.error("burn-in cannot be negative; num-gpus must be between 0 and 1")
    device = torch.device("cuda:0" if args.num_gpus > 0 else "cpu")
    if device.type == "cuda" and not torch.cuda.is_available():
        raise SystemExit("FAIL: requested CUDA behavior cloning but CUDA is unavailable")
    output = prepare_output(args.output)
    arrays, manifest = load_expert_arrays(args.dataset)
    train_seeds, validation_seeds = expert_seed_split(
        manifest, args.validation_fraction
    )
    config = training_config(args.config)
    config.update(
        num_env_runners=0,
        num_cpus=args.num_cpus,
        # BC explicitly owns the training module/device. The otherwise unused
        # PPO learner stays on CPU until trained weights are synchronized.
        num_gpus_per_learner=0,
    )
    epochs = 1 if args.smoke else args.epochs
    max_batches = 2 if args.smoke else args.max_batches
    minimum_balanced_accuracy = 0.0 if args.smoke else 0.40
    maximum_overfit_gap = 1.0 if args.smoke else 0.15
    ray.init(
        include_dashboard=False,
        num_cpus=args.num_cpus,
        num_gpus=math.ceil(args.num_gpus),
        log_to_driver=False,
    )
    algorithm = None
    verification = None
    try:
        algorithm = build_ppo_config(config).build_algo()
        initial_hashes = {
            name: parameter_hash(algorithm.get_module(name))
            for name in (ROVER_POLICY, DRONE_POLICY)
        }
        reports = {}
        for name, policy_id in ((ROVER_POLICY, 0), (DRONE_POLICY, 1)):
            module = algorithm.get_module(name)
            module.to(device)
            if any(parameter.device.type != device.type for parameter in module.parameters()):
                raise RuntimeError(f"{name} is not on requested BC device {device}")
            policy_started = time.monotonic()
            deadline = policy_started + args.max_seconds / 2 if args.max_seconds is not None else None

            def epoch_progress(record, policy_name=name):
                write_json(output / f"{policy_name}_progress.json", {
                    "policy": policy_name, "device": str(device),
                    "elapsed_seconds": time.monotonic() - policy_started,
                    **record,
                })
                print(json.dumps({"policy": policy_name, "epoch": record["epoch"], "validation_balanced_accuracy": record["validation"]["balanced_accuracy"]}), flush=True)

            reports[name] = train_policy_clone(
                module,
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
                burn_in=args.burn_in,
                deadline=deadline,
                on_epoch=epoch_progress,
            )
            reports[name]["elapsed_seconds"] = time.monotonic() - policy_started
            module.to("cpu")
            write_json(output / f"{name}_report.json", reports[name])
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
        verification = build_ppo_config(config).build_algo()
        verification.restore_from_path(str(checkpoint))
        restored_hashes = {
            name: parameter_hash(verification.get_module(name))
            for name in (ROVER_POLICY, DRONE_POLICY)
        }
        roundtrip_passed = final_hashes == restored_hashes
        if not roundtrip_passed:
            raise RuntimeError("Behavior-cloning checkpoint failed exact weight roundtrip")
        quality_passed = clone_summary_passed(
                reports,
                minimum_balanced_accuracy=minimum_balanced_accuracy,
                maximum_overfit_gap=maximum_overfit_gap,
                minimum_per_action_recall=0.0 if args.smoke else 0.05,
                minimum_baseline_margin=0.0 if args.smoke else 0.10,
            )
        passed = (
            all(initial_hashes[name] != final_hashes[name] for name in initial_hashes)
            and (args.smoke or quality_passed)
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
            "restored_hashes": restored_hashes,
            "checkpoint_roundtrip_passed": roundtrip_passed,
            "training_device": str(device),
            "cuda_peak_memory_bytes": torch.cuda.max_memory_allocated() if device.type == "cuda" else 0,
            "minimum_balanced_accuracy": minimum_balanced_accuracy,
            "maximum_overfit_gap": maximum_overfit_gap,
            "reports": reports,
            "smoke": args.smoke,
            "diagnostic": args.smoke or args.max_batches is not None,
            "max_batches": max_batches,
            "budget_seconds": args.max_seconds,
            "passed": passed,
            "quality_passed": quality_passed,
        }
        write_json(output / "summary.json", summary)
        print(json.dumps({key: value for key, value in summary.items() if key != "reports"}, indent=2))
        if not passed:
            raise SystemExit("FAIL: behavior-cloning gates were not met")
    finally:
        if verification is not None:
            verification.stop()
        if algorithm is not None:
            algorithm.stop()
        ray.shutdown()


if __name__ == "__main__":
    main()
