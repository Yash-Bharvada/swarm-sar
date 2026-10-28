"""Train the two shared Step 3 PPO policies and export a checkpoint/curve."""

import argparse
import csv
import hashlib
import json
import math
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import ray
import torch

from swarm_sar.learning.training import (
    DRONE_POLICY,
    ROVER_POLICY,
    build_ppo_config,
    training_config,
)
from swarm_sar.learning.cohort_evaluation import evaluate_cohorts, write_evaluation
from swarm_sar.learning.training_gates import evaluate_gate, gate_definition, iteration_health
from swarm_sar.policy_contract import policy_contract


def parameter_vector(module) -> torch.Tensor:
    return torch.cat(
        [parameter.detach().cpu().reshape(-1) for parameter in module.parameters()]
    )


def vector_hash(vector: torch.Tensor) -> str:
    return hashlib.sha256(vector.numpy().tobytes()).hexdigest()


def checkpoint_index_path(output: Path) -> Path:
    return output / "checkpoint_index.json"


def load_checkpoint_index(output: Path) -> dict:
    path = checkpoint_index_path(output)
    if not path.exists():
        return {
            "schema_version": 1,
            "latest": None,
            "best": None,
            "best_development_recall": None,
            "checkpoints": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def write_checkpoint_index(output: Path, payload: dict) -> None:
    path = checkpoint_index_path(output)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare_output_directory(output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            f"Refusing to overwrite non-empty training output: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)


def save_numbered_checkpoint(algorithm, output: Path, env_steps: int) -> Path:
    directory = output / "checkpoints" / f"step_{env_steps:012d}"
    if directory.exists():
        raise FileExistsError(f"Refusing to overwrite checkpoint: {directory}")
    saved = Path(algorithm.save_to_path(str(directory.resolve())))
    index = load_checkpoint_index(output)
    relative = saved.relative_to(output.resolve()).as_posix()
    index["latest"] = relative
    index["checkpoints"].append({"env_steps": int(env_steps), "path": relative})
    write_checkpoint_index(output, index)
    return saved


def write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/training.yaml"))
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--target-env-steps", type=int)
    parser.add_argument("--num-cpus", type=int)
    parser.add_argument("--num-env-runners", type=int)
    parser.add_argument("--num-gpus-per-learner", type=float)
    parser.add_argument("--resume", type=Path)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run a tiny mixed-team infrastructure test that updates both policies.",
    )
    parser.add_argument("--output", type=Path, default=Path("results/step3_training"))
    args = parser.parse_args()
    config = training_config(args.config)
    for argument, key in (
        (args.num_cpus, "num_cpus"),
        (args.num_env_runners, "num_env_runners"),
        (args.num_gpus_per_learner, "num_gpus_per_learner"),
        (args.target_env_steps, "target_env_steps"),
    ):
        if argument is not None:
            config[key] = argument
    if args.smoke:
        config.update(
            iterations=1,
            target_env_steps=512,
            checkpoint_interval_steps=512,
            evaluation_interval_steps=0,
            train_batch_size_per_learner=512,
            minibatch_size=128,
            num_epochs=2,
            rollout_fragment_length=64,
            curriculum_phase_episodes=[0, 0],
            final_team_profiles=[{"rover": 2, "drone": 2}],
            world_sizes=[24],
            max_steps=120,
        )
    iterations = int(args.iterations or config["iterations"])
    target_env_steps = int(config.get("target_env_steps", 0))
    output = args.output.resolve()
    prepare_output_directory(output)
    (args.output / "training_definition.json").write_text(
        json.dumps(
            {
                **config,
                "iterations": iterations,
                "resume": str(args.resume.resolve()) if args.resume else None,
                "policy_contract": policy_contract(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    gpu_count = math.ceil(float(config.get("num_gpus_per_learner", 0)))
    ray.init(
        include_dashboard=False,
        num_cpus=int(config.get("num_cpus", 2)),
        num_gpus=gpu_count,
        log_to_driver=False,
    )
    algorithm = None
    try:
        algorithm = build_ppo_config(config).build_algo()
        if args.resume is not None:
            resume = args.resume.resolve()
            if not resume.exists():
                raise FileNotFoundError(f"Resume checkpoint does not exist: {resume}")
            algorithm.restore_from_path(str(resume))
    except Exception:
        if algorithm is not None:
            algorithm.stop()
        ray.shutdown()
        raise
    initial = {
        policy: parameter_vector(algorithm.get_module(policy)).clone()
        for policy in (ROVER_POLICY, DRONE_POLICY)
    }
    rows = []
    latest_checkpoint: Path | None = None
    existing_index = load_checkpoint_index(output)
    last_checkpoint_step = max(
        (int(item["env_steps"]) for item in existing_index["checkpoints"]),
        default=0,
    )
    last_evaluation_step = 0
    checkpoint_interval = int(config.get("checkpoint_interval_steps", 0))
    evaluation_interval = int(config.get("evaluation_interval_steps", 0))
    evaluation_interval_seconds = int(config.get("evaluation_interval_seconds", 0))
    last_evaluation_time = time.monotonic()
    interrupted = False
    termination_status = "completed"
    termination_reasons: list[str] = []
    recall_history: list[float] = []
    gates = gate_definition(config.get("training_gates_path"))
    evaluation_index = 0
    try:
        for iteration in range(1, iterations + 1):
            try:
                result = algorithm.train()
            except KeyboardInterrupt:
                interrupted = True
                if not rows:
                    raise
                print("Training interrupted; saving the most recent completed iteration")
                break
            runners = result.get("env_runners", {})
            learners = result.get("learners", {})
            row = {
                "iteration": iteration,
                "env_steps": int(result.get("num_env_steps_sampled_lifetime", 0)),
                "episode_return_mean": float(
                    runners.get("episode_return_mean", float("nan"))
                ),
                "episode_length_mean": float(
                    runners.get("episode_len_mean", float("nan"))
                ),
                "rover_policy_loss": float(
                    learners.get(ROVER_POLICY, {}).get("policy_loss", float("nan"))
                ),
                "drone_policy_loss": float(
                    learners.get(DRONE_POLICY, {}).get("policy_loss", float("nan"))
                ),
            }
            rows.append(row)
            print(json.dumps(row), flush=True)

            health_failures = iteration_health(row)
            write_json_atomic(
                output / "heartbeat.json",
                {
                    "status": "running",
                    "iteration": iteration,
                    "env_steps": row["env_steps"],
                    "latest_checkpoint": str(latest_checkpoint) if latest_checkpoint else None,
                    "health_failures": health_failures,
                },
            )
            if health_failures:
                termination_status = "aborted"
                termination_reasons = health_failures
                break

            env_steps = row["env_steps"]
            due_checkpoint = checkpoint_interval > 0 and (
                env_steps // checkpoint_interval
                > last_checkpoint_step // checkpoint_interval
            )
            due_evaluation = evaluation_interval > 0 and (
                env_steps // evaluation_interval
                > last_evaluation_step // evaluation_interval
            )
            due_evaluation = due_evaluation or (
                evaluation_interval_seconds > 0
                and time.monotonic() - last_evaluation_time >= evaluation_interval_seconds
            )
            if due_checkpoint:
                latest_checkpoint = save_numbered_checkpoint(
                    algorithm, output, env_steps
                )
                last_checkpoint_step = env_steps
            if due_evaluation:
                report = evaluate_cohorts(
                    {
                        ROVER_POLICY: algorithm.get_module(ROVER_POLICY),
                        DRONE_POLICY: algorithm.get_module(DRONE_POLICY),
                    },
                    evaluation_index=evaluation_index,
                    config_path=config.get("evaluation_cohorts_path"),
                    seed_splits_path=config.get("seed_splits_path"),
                )
                write_evaluation(
                    report,
                    output / "evaluations" / f"step_{env_steps:012d}.json",
                )
                recall = float(report["summary"]["mean_cohort_recall"])
                recall_history.append(recall)
                row["development_mean_cohort_recall"] = recall
                last_evaluation_step = env_steps
                last_evaluation_time = time.monotonic()
                if latest_checkpoint is None or last_checkpoint_step != env_steps:
                    latest_checkpoint = save_numbered_checkpoint(
                        algorithm, output, env_steps
                    )
                    last_checkpoint_step = env_steps
                index = load_checkpoint_index(output)
                best = index.get("best_development_recall")
                if best is None or recall > float(best):
                    index["best_development_recall"] = recall
                    index["best"] = latest_checkpoint.relative_to(output).as_posix()
                    write_checkpoint_index(output, index)
                decision = evaluate_gate(
                    report,
                    env_steps=env_steps,
                    definition=gates,
                    recall_history=recall_history,
                )
                row["gate_status"] = decision["status"]
                write_json_atomic(
                    output / "heartbeat.json",
                    {
                        "status": decision["status"],
                        "iteration": iteration,
                        "env_steps": env_steps,
                        "latest_checkpoint": str(latest_checkpoint),
                        "evaluation": report["summary"],
                        "gate": decision,
                    },
                )
                evaluation_index += 1
                if decision["status"] != "continue":
                    termination_status = "aborted" if decision["status"] == "abort" else "paused"
                    termination_reasons = decision["abort_reasons"] + decision["pause_reasons"]
                    break
            if target_env_steps > 0 and env_steps >= target_env_steps:
                break

        if not rows:
            raise RuntimeError("Training produced no iterations")
        final_steps = rows[-1]["env_steps"]
        if latest_checkpoint is None or last_checkpoint_step != final_steps:
            latest_checkpoint = save_numbered_checkpoint(
                algorithm, output, final_steps
            )
        checkpoint = latest_checkpoint
        final = {
            policy: parameter_vector(algorithm.get_module(policy)).clone()
            for policy in (ROVER_POLICY, DRONE_POLICY)
        }
        parameter_report = {
            policy: {
                "parameter_count": int(final[policy].numel()),
                "initial_sha256": vector_hash(initial[policy]),
                "final_sha256": vector_hash(final[policy]),
                "delta_l2": float(torch.linalg.vector_norm(final[policy] - initial[policy])),
            }
            for policy in (ROVER_POLICY, DRONE_POLICY)
        }
        summary = {
            "iterations_requested": iterations,
            "iterations_completed": len(rows),
            "env_steps": rows[-1]["env_steps"],
            "checkpoint": str(checkpoint),
            "resumed_from": str(args.resume.resolve()) if args.resume else None,
            "interrupted": interrupted,
            "termination_status": termination_status,
            "termination_reasons": termination_reasons,
            "policy_contract": policy_contract(),
            "policies": parameter_report,
            "weights_updated": all(
                report["delta_l2"] > 0 for report in parameter_report.values()
            ),
        }
        (output / "training_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        with (output / "training_history.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            fields = list(
                dict.fromkeys(key for row in rows for key in row)
            )
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        figure, axis = plt.subplots(figsize=(8, 4.5))
        axis.plot(
            [row["env_steps"] for row in rows],
            [row["episode_return_mean"] for row in rows],
            marker="o",
        )
        axis.set(title="Step 3 PPO training", xlabel="Environment steps", ylabel="Mean return")
        axis.grid(alpha=0.3)
        figure.tight_layout()
        figure.savefig(output / "training_curve.png", dpi=150)
        plt.close(figure)
        print(json.dumps(summary, indent=2))
        write_json_atomic(
            output / ("ABORTED.json" if termination_status == "aborted" else "PAUSED.json" if termination_status == "paused" else "COMPLETED.json"),
            summary,
        )
        if not summary["weights_updated"]:
            raise SystemExit("FAIL: one or more PPO policies did not update")
        if termination_status == "aborted":
            raise SystemExit("ABORT: " + ", ".join(termination_reasons))
    finally:
        if algorithm is not None:
            algorithm.stop()
        ray.shutdown()


if __name__ == "__main__":
    main()
