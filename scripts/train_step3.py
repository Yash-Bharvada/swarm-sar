"""Train the two shared Step 3 PPO policies and export a checkpoint/curve."""

import argparse
import csv
import hashlib
import json
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


def parameter_vector(module) -> torch.Tensor:
    return torch.cat(
        [parameter.detach().cpu().reshape(-1) for parameter in module.parameters()]
    )


def vector_hash(vector: torch.Tensor) -> str:
    return hashlib.sha256(vector.numpy().tobytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/training.yaml"))
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--output", type=Path, default=Path("results/step3_training"))
    args = parser.parse_args()
    config = training_config(args.config)
    iterations = int(args.iterations or config["iterations"])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "training_definition.json").write_text(
        json.dumps({**config, "iterations": iterations}, indent=2), encoding="utf-8"
    )

    ray.init(include_dashboard=False, num_cpus=2, log_to_driver=False)
    algorithm = build_ppo_config(config).build_algo()
    initial = {
        policy: parameter_vector(algorithm.get_module(policy)).clone()
        for policy in (ROVER_POLICY, DRONE_POLICY)
    }
    rows = []
    try:
        for iteration in range(1, iterations + 1):
            result = algorithm.train()
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

        checkpoint = Path(algorithm.save_to_path(str((args.output / "checkpoint").resolve())))
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
            "iterations": iterations,
            "env_steps": rows[-1]["env_steps"],
            "checkpoint": str(checkpoint),
            "policies": parameter_report,
            "weights_updated": all(
                report["delta_l2"] > 0 for report in parameter_report.values()
            ),
        }
        (args.output / "training_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        with (args.output / "training_history.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
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
        figure.savefig(args.output / "training_curve.png", dpi=150)
        plt.close(figure)
        print(json.dumps(summary, indent=2))
        if not summary["weights_updated"]:
            raise SystemExit("FAIL: one or more PPO policies did not update")
    finally:
        algorithm.stop()
        ray.shutdown()


if __name__ == "__main__":
    main()
