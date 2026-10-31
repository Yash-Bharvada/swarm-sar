"""Opt-in, supervised PPO pilot for the GNN residual. Never promotes a model.

Default is a read-only plan. --execute launches a bounded child process.
Existing audited training helpers are reused without modifying their source.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import ray
import torch
from ray.rllib.core.rl_module.rl_module import RLModule

from experiments.gnn.attention import ARCHITECTURE
from experiments.gnn.artifacts import source_hashes, verified_manifest
from experiments.gnn.config import build_gnn_ppo_config, experiment_config
from experiments.gnn.module import warm_start_actor
from experiments.gnn.smoke import DEFAULT, ROOT, verified_originals
from swarm_sar.learning.gpu_pipeline import Supervisor
from swarm_sar.learning.release import atomic_json, file_hash, tree_manifest
from swarm_sar.learning.training_gates import iteration_health
from training.scripts.train_step3 import (
    POLICIES, json_safe, learner_health, restore_checkpoint_hashes,
    save_numbered_checkpoint, synchronized_modules, write_checkpoint_index,
    load_checkpoint_index,
    capture_schedules, restore_schedules,
)


def worker(args):
    config = experiment_config(smoke=args.smoke, gpu=args.gpu)
    if args.runners is not None:
        config.update(num_env_runners=args.runners, num_cpus=max(2, args.runners + 2))
    if args.epochs is not None:
        config["num_epochs"] = args.epochs
    resume_manifest = None
    if args.resume:
        resume_manifest = verified_manifest(args.resume, filename="gnn_manifest.json")
        if resume_manifest.get("config") != config:
            raise ValueError("Resume requires identical effective config (including runners/device)")
    if args.gpu and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable; no CPU fallback")
    originals, digest = verified_originals(args.checkpoint)
    if resume_manifest and resume_manifest.get("base_checkpoint_sha256") != digest:
        raise ValueError("Resume baseline provenance differs from the verified original")
    output = args.output / "run"
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "experiment.json", {
        "architecture": ARCHITECTURE, "observation_version": "gpu-v1",
        "base_checkpoint_sha256": digest, "config": config, "final_seeds_used": False,
        "initialization": ("resume_graph_optimizer_and_counters" if args.resume else
                           "original_actor_weights_plus_zero_residual; fresh PPO optimizer/counters"),
        "source_sha256": source_hashes(),
        "resumed_from": str(args.resume.resolve()) if args.resume else None,
        "claim": "pilot_only_not_promoted",
    })
    algorithm = None
    started = time.monotonic()
    steps = 0
    rows = []
    status = "running"
    try:
        ray.init(include_dashboard=False, num_cpus=config["num_cpus"],
                 num_gpus=1 if args.gpu else 0, log_to_driver=False)
        algorithm = build_gnn_ppo_config(config).build_algo()

        if args.resume:
            if args.target_steps <= resume_manifest["env_steps"]:
                raise ValueError("Target is lifetime experiment steps and must exceed resumed steps")
            algorithm.restore_from_path(str(args.resume.resolve()))
            steps = resume_manifest["env_steps"]
            restore_schedules(algorithm, resume_manifest["schedules"],
                              previous_runner_count=config["num_env_runners"] + 1,
                              runner_count=config["num_env_runners"] + 1)
            if restore_checkpoint_hashes(args.resume.resolve()) != {
                name: values["sha256"] for name, values in learner_health(algorithm, require_cuda=args.gpu)["policies"].items()
            }:
                raise RuntimeError("Resumed learner differs from saved checkpoint")
        else:
            def initialize(learner):
                return {name: warm_start_actor(learner.module[name], originals[name]) for name in POLICIES}

            calls = algorithm.learner_group.foreach_learner(initialize, timeout_seconds=60)
            if len(calls) != 1 or not next(iter(calls)).ok:
                raise RuntimeError("Warm-start optimizing learner failed")
        algorithm.env_runner_group.sync_weights(
            from_worker_or_learner_group=algorithm.learner_group, inference_only=True)
        before = learner_health(algorithm, require_cuda=args.gpu)
        if before["failures"]:
            raise RuntimeError(str(before["failures"]))
        # Before spending the pilot budget, verify an initialized actor can restore.
        initial = synchronized_modules(algorithm)
        for name, actor in initial.items():
            saved = actor.save_to_path(str(output / "initial_actors" / name))
            restored = RLModule.from_checkpoint(saved)
            for key, value in actor.state_dict().items():
                torch.testing.assert_close(value.cpu(), restored.state_dict()[key].cpu(), rtol=0, atol=0)
        # Inspect graph-specific tensors on the optimizing learner, not the replica.
        def graph_health(learner):
            import hashlib
            return {name: {group: hashlib.sha256(b"".join(
                value.detach().cpu().contiguous().numpy().tobytes()
                for key, value in learner.module[name].graph_adapter.state_dict().items()
                if (key.startswith("residual.") if group == "residual" else not key.startswith("residual."))
            )).hexdigest() for group in ("encoder", "residual")} for name in POLICIES}

        def optimizing_graph():
            result = next(iter(algorithm.learner_group.foreach_learner(graph_health, timeout_seconds=30)))
            if not result.ok:
                raise RuntimeError("Graph learner inspection failed")
            return result.get()

        graph_before = optimizing_graph()
        if args.gpu:
            torch.cuda.reset_peak_memory_stats()
        limit = args.iterations if args.iterations else (3 if args.smoke else 10000)
        last_saved = steps
        for iteration in range(1, limit + 1):
            if time.monotonic() - started >= args.max_seconds * 0.8:
                break  # leave budget for save/restore; outer supervisor enforces stop
            iteration_started = time.monotonic()
            result = algorithm.train()
            iteration_seconds = time.monotonic() - iteration_started
            previous, steps = steps, int(result.get("num_env_steps_sampled_lifetime", 0))
            runners, learners = result.get("env_runners", {}), result.get("learners", {})
            row = {"iteration": iteration, "env_steps": steps,
                   "elapsed_seconds": time.monotonic() - started,
                   "episode_return_mean": float(runners.get("episode_return_mean", float("nan"))),
                   "episode_length_mean": float(runners.get("episode_len_mean", float("nan")))}
            row.update(iteration_seconds=iteration_seconds,
                       training_env_steps_per_second=(steps - previous) / max(iteration_seconds, 1e-9),
                       cuda_peak_allocated_bytes=torch.cuda.max_memory_allocated() if args.gpu else None,
                       cuda_peak_reserved_bytes=torch.cuda.max_memory_reserved() if args.gpu else None)
            for name, short in (("rover_policy", "rover"), ("drone_policy", "drone")):
                loss = learners.get(name, {}).get("policy_loss")
                row[f"{short}_policy_loss"] = float(loss) if loss is not None else None
            health = learner_health(algorithm, require_cuda=args.gpu)
            failures = iteration_health(row) + health["failures"]
            if steps <= previous:
                failures.append("no_environment_step_progress")
            if any(row[f"{short}_policy_loss"] is None for short in ("rover", "drone")):
                failures.append("missing_actor_loss")
            row["failures"] = failures
            rows.append(json_safe(row))
            atomic_json(output / "history.json", rows)
            print(json.dumps(json_safe(row), allow_nan=False), flush=True)
            if failures:
                raise RuntimeError("Pilot health gate: " + ", ".join(failures))
            due = steps - last_saved >= config["checkpoint_interval_steps"]
            finished = steps >= args.target_steps or iteration == limit
            due = due or finished or time.monotonic() - started >= args.max_seconds * 0.65
            if not due:
                continue
            # Save completed healthy iterations, preserving schedules and optimizer.
            saved = save_numbered_checkpoint(algorithm, output, steps, publish=False)
            expected = {name: health["policies"][name]["sha256"] for name in POLICIES}
            if restore_checkpoint_hashes(saved) != expected:
                raise RuntimeError("Checkpoint parameter restore mismatch")
            atomic_json(saved / "parameter_hashes.json", expected)
            atomic_json(saved / "gnn_manifest.json", {"architecture": ARCHITECTURE,
                "env_steps": steps, "config": config, "schedules": capture_schedules(algorithm),
                "base_checkpoint_sha256": digest, "final_seeds_used": False,
                "source_sha256": source_hashes(), "files": tree_manifest(saved)})
            last_saved = steps
            index = load_checkpoint_index(output)
            relative = saved.relative_to(output).as_posix()
            index["latest"] = relative
            index["checkpoints"].append({"path": relative, "env_steps": steps, "verified": True})
            write_checkpoint_index(output, index)
            # Manifest is last: interrupted exports are never admitted by evaluator.
            actors = synchronized_modules(algorithm)
            bundle = output / "actors" / f"step_{steps:012d}"
            for name, actor in actors.items():
                actor.save_to_path(str(bundle / name))
            atomic_json(bundle / "manifest.json", {"architecture": ARCHITECTURE,
                "env_steps": steps, "base_checkpoint_sha256": digest,
                "final_seeds_used": False, "files": tree_manifest(bundle),
                "experiment_sha256": file_hash(output / "experiment.json"),
                "source_sha256": source_hashes(),
                "status": "unpromoted_training_candidate"})
            if finished:
                break
        after = learner_health(algorithm, require_cuda=args.gpu)
        if not rows or any(before["policies"][n]["sha256"] == after["policies"][n]["sha256"] for n in POLICIES):
            raise RuntimeError("Both actors must make real optimizer updates")
        graph_after = optimizing_graph()
        graph_updates = {name: {part: graph_before[name][part] != graph_after[name][part]
                               for part in ("encoder", "residual")} for name in POLICIES}
        if any(not all(parts.values()) for parts in graph_updates.values()):
            raise RuntimeError("Both graph encoders and residual heads must make real optimizer updates")
        if last_saved != steps:
            raise RuntimeError("Time budget ended before the final verified checkpoint; use the last indexed artifact")
        status = "target_reached" if steps >= args.target_steps else "smoke_complete" if args.smoke else "budget_or_iteration_limit"
        atomic_json(output / "summary.json", {"architecture": ARCHITECTURE, "env_steps": steps,
            "iterations": len(rows), "elapsed_seconds": time.monotonic() - started,
            "status": status, "graph_updates": graph_updates,
            "weights_updated": True, "cuda": args.gpu, "promoted": False,
            "interpretation": "Optimizer/checkpoint evidence; run paired evaluation before claiming improvement."})
    except BaseException as exc:
        atomic_json(output / "FAILED.json", {"error": f"{type(exc).__name__}: {exc}", "env_steps": steps})
        raise
    finally:
        if algorithm is not None:
            algorithm.stop()
        ray.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT)
    parser.add_argument("--resume", type=Path, help="Verified GNN full checkpoint, never a baseline checkpoint")
    parser.add_argument("--runners", type=int, help="Override rollout runners; 0 is a local runner")
    parser.add_argument("--epochs", type=int, help="Optimizer epochs per batch")
    parser.add_argument("--iterations", type=int, help="Additional iteration limit for bounded verification")
    parser.add_argument("--max-seconds", type=int, default=1800)
    parser.add_argument("--target-steps", type=int, default=25000)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.max_seconds < 60 or args.target_steps < 1:
        parser.error("Use at least 60 seconds and a positive target step count")
    if args.runners is not None and not 0 <= args.runners <= 16:
        parser.error("Choose 0–16 rollout runners")
    if args.epochs is not None and not 1 <= args.epochs <= 10:
        parser.error("Choose 1–10 optimizer epochs")
    if args.iterations is not None and args.iterations < 1:
        parser.error("Iterations must be positive")
    if args.plan or not args.execute:
        config = experiment_config(smoke=args.smoke, gpu=args.gpu)
        if args.runners is not None:
            config.update(num_env_runners=args.runners, num_cpus=max(2, args.runners + 2))
        if args.epochs is not None:
            config["num_epochs"] = args.epochs
        print(json.dumps({"architecture": ARCHITECTURE, "config": config,
                          "max_seconds": args.max_seconds, "target_steps": args.target_steps,
                          "training_started": False, "next": "Explicit --execute and fresh --output required"}, indent=2))
        return
    if args.output is None:
        parser.error("--output is required")
    args.output = args.output.resolve()
    if args.resume:
        args.resume = args.resume.resolve()
    if args.worker:
        worker(args)
        return
    if args.output.exists():
        parser.error("Use a new output directory")
    args.output.mkdir(parents=True)
    supervisor = Supervisor(args.output, ROOT, time.monotonic() + args.max_seconds,
                            minimum_free_bytes=2 * 1024**3)
    supervisor.run("gnn_pilot", [sys.executable, "-u", "-m", "experiments.gnn.pilot", *sys.argv[1:], "--worker"],
                   seconds=args.max_seconds)


if __name__ == "__main__":
    main()
