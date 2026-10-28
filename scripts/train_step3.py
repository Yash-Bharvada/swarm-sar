"""Bounded PPO training with verified checkpoints and persistent quality gates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import signal
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import ray
import torch
from ray.rllib.core.rl_module.rl_module import RLModule

from swarm_sar.learning.cohort_evaluation import evaluate_cohorts, write_evaluation
from swarm_sar.learning.training import DRONE_POLICY, ROVER_POLICY, build_ppo_config, training_config
from swarm_sar.learning.training_gates import evaluate_gate, gate_definition, iteration_health
from swarm_sar.policy_contract import policy_contract

POLICIES = (ROVER_POLICY, DRONE_POLICY)


def parameter_vector(module) -> torch.Tensor:
    return torch.cat([parameter.detach().cpu().reshape(-1) for parameter in module.parameters()])


def vector_hash(vector: torch.Tensor) -> str:
    return hashlib.sha256(vector.numpy().tobytes()).hexdigest()


def json_safe(value):
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(json_safe(payload), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def checkpoint_index_path(output: Path) -> Path:
    return output / "checkpoint_index.json"


def load_checkpoint_index(output: Path) -> dict:
    path = checkpoint_index_path(output)
    if not path.exists():
        return {"schema_version": 2, "latest": None, "best": None, "best_fixed_recall": None, "checkpoints": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_checkpoint_index(output: Path, payload: dict) -> None:
    write_json_atomic(checkpoint_index_path(output), payload)


def prepare_output_directory(output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty training output: {output}")
    output.mkdir(parents=True, exist_ok=True)


def save_numbered_checkpoint(algorithm, output: Path, env_steps: int, *, publish: bool = True) -> Path:
    directory = output / "checkpoints" / f"step_{env_steps:012d}"
    if directory.exists():
        raise FileExistsError(f"Refusing to overwrite checkpoint: {directory}")
    saved = Path(algorithm.save_to_path(str(directory.resolve())))
    if publish:
        index = load_checkpoint_index(output)
        relative = saved.relative_to(output.resolve()).as_posix()
        index["latest"] = relative
        index["checkpoints"].append({"env_steps": int(env_steps), "path": relative})
        write_checkpoint_index(output, index)
    return saved


def learner_health(algorithm, *, require_cuda: bool) -> dict:
    """Inspect the optimizing learner, rather than the CPU inference replica."""
    def inspect(learner):
        policies = {}
        for name in POLICIES:
            module = learner.module[name]
            vector = parameter_vector(module)
            policies[name] = {"device": str(next(module.parameters()).device),
                              "finite": bool(torch.isfinite(vector).all()),
                              "sha256": vector_hash(vector), "parameter_count": int(vector.numel())}
        return policies
    calls = algorithm.learner_group.foreach_learner(inspect, timeout_seconds=30)
    if len(calls) != 1:
        raise RuntimeError("This launch contract requires exactly one PPO learner")
    result = next(iter(calls))
    if not result.ok:
        raise RuntimeError(f"Learner health call failed: {result.get()}")
    policies = result.get()
    failures = []
    for name, values in policies.items():
        if not values["finite"]:
            failures.append(f"non_finite_parameters:{name}")
        if require_cuda and not values["device"].startswith("cuda"):
            failures.append(f"learner_not_on_cuda:{name}")
    return {"policies": policies, "failures": failures}


def synchronized_modules(algorithm) -> dict:
    weights = algorithm.get_weights()
    modules = {name: algorithm.get_module(name) for name in POLICIES}
    for name, module in modules.items():
        module.set_state(weights[name])
        module.eval()
    return modules


def capture_schedules(algorithm) -> list[dict]:
    def collect(runner):
        return [env.unwrapped.schedule_state() for env in runner.env.envs] if runner.env is not None else []
    groups = algorithm.env_runner_group.foreach_env_runner(collect, timeout_seconds=30)
    return [item for group in groups for item in group]


def restore_schedules(algorithm, schedules: list[dict], *, previous_runner_count: int | None = None, runner_count: int | None = None) -> None:
    if not schedules:
        return
    by_worker = {int(item["worker_index"]): item for item in schedules}
    fallback = max(int(item["episode_index"]) for item in schedules)
    changed_topology = previous_runner_count is not None and runner_count != previous_runner_count
    if changed_topology:
        high_watermark = max(int(item["worker_index"]) + int(item["episode_index"]) * previous_runner_count for item in schedules)
        fallback = math.ceil((high_watermark + 1) / int(runner_count))
    def restore(runner):
        if runner.env is not None:
            for wrapped in runner.env.envs:
                env = wrapped.unwrapped
                restored = {"worker_index": env.worker_index, "episode_index": fallback}
                env.restore_schedule(restored if changed_topology else by_worker.get(env.worker_index, restored))
    algorithm.env_runner_group.foreach_env_runner(restore, timeout_seconds=30)


def restore_checkpoint_hashes(path: Path) -> dict[str, str]:
    hashes = {}
    for name in POLICIES:
        module = RLModule.from_checkpoint(str(path / "learner_group" / "learner" / "rl_module" / name))
        hashes[name] = vector_hash(parameter_vector(module))
        del module
    return hashes


def persist_history(output: Path, rows: list[dict]) -> None:
    write_json_atomic(output / "training_history.json", {"iterations": rows})
    if rows:
        temporary = output / "training_history.csv.tmp"
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(dict.fromkeys(key for row in rows for key in row)))
            writer.writeheader()
            writer.writerows(json_safe(rows))
        temporary.replace(output / "training_history.csv")


def fixed_score(report: dict) -> float:
    return float(report["summary"].get("fixed_mean_recall", report["summary"]["mean_cohort_recall"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/training.yaml"))
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--target-env-steps", type=int)
    parser.add_argument("--num-cpus", type=int)
    parser.add_argument("--num-env-runners", type=int)
    parser.add_argument("--num-gpus-per-learner", type=float)
    parser.add_argument("--evaluation-interval-steps", type=int)
    parser.add_argument("--max-seconds", type=float, default=0, help="Graceful iteration-boundary deadline; also use the outer watchdog")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--reference-evaluation", type=Path)
    parser.add_argument("--initial-evaluation", action="store_true")
    parser.add_argument("--smoke-evaluation", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("results/step3_training"))
    args = parser.parse_args()
    config = training_config(args.config)
    for value, key in ((args.num_cpus, "num_cpus"), (args.num_env_runners, "num_env_runners"), (args.num_gpus_per_learner, "num_gpus_per_learner"), (args.target_env_steps, "target_env_steps"), (args.evaluation_interval_steps, "evaluation_interval_steps")):
        if value is not None:
            config[key] = value
    if args.smoke:
        config.update(iterations=1, target_env_steps=512, checkpoint_interval_steps=512,
                      evaluation_interval_steps=0, evaluation_interval_seconds=0,
                      train_batch_size_per_learner=512, minibatch_size=128, num_epochs=2,
                      rollout_fragment_length=64, curriculum=False, curriculum_phase_episodes=[0, 0],
                      domain_randomization=False, final_team_profiles=[{"rover": 2, "drone": 2}],
                      world_sizes=[24], max_steps=120)
    if args.max_seconds < 0:
        parser.error("--max-seconds cannot be negative")
    iterations = int(args.iterations if args.iterations is not None else config["iterations"])
    target_steps = int(config.get("target_env_steps", 0))
    output = args.output.resolve()
    prepare_output_directory(output)
    write_json_atomic(output / "training_definition.json", {**config, "iterations": iterations,
                      "max_seconds": args.max_seconds, "resume": str(args.resume.resolve()) if args.resume else None,
                      "reference_evaluation": str(args.reference_evaluation.resolve()) if args.reference_evaluation else None,
                      "policy_contract": policy_contract()})
    state = {"schema_version": 2, "evaluation_index": 0, "recall_history": [], "gap_history": [], "shadow_gap_history": [], "env_steps": 0,
             "best_fixed_recall": None, "best_checkpoint": None, "schedules": [], "last_evaluation_step": 0,
             "runner_count": max(1, int(config.get("num_env_runners", 0)) + 1)}
    if args.resume and (args.resume / "run_state.json").exists():
        state.update(json.loads((args.resume / "run_state.json").read_text(encoding="utf-8")))
    reference = fixed_score(json.loads(args.reference_evaluation.read_text(encoding="utf-8"))) if args.reference_evaluation else None
    started = time.monotonic()
    latest_checkpoint, last_checkpoint_step = None, -1
    rows = []
    status, reasons = "completed", []
    exception_text, algorithm, initial_health, current_health = None, None, None, None
    safe_to_checkpoint = False
    stop_requested = []
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    def terminate(signum, frame):
        del signum, frame
        stop_requested.append("SIGTERM")
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    gates = gate_definition(config.get("training_gates_path"))
    require_cuda = float(config.get("num_gpus_per_learner", 0)) > 0

    def heartbeat(extra=None):
        write_json_atomic(output / "heartbeat.json", {
            "status": status if status != "completed" else "running", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.monotonic() - started, "iteration": len(rows), "env_steps": state["env_steps"],
            "latest_checkpoint": str(latest_checkpoint) if latest_checkpoint else None,
            "evaluation_index": state["evaluation_index"], **(extra or {}),
        })

    def checkpoint():
        nonlocal latest_checkpoint, last_checkpoint_step
        if last_checkpoint_step == state["env_steps"]:
            return latest_checkpoint
        state["schedules"] = capture_schedules(algorithm)
        saved = save_numbered_checkpoint(algorithm, output, state["env_steps"], publish=False)
        expected = {name: current_health["policies"][name]["sha256"] for name in POLICIES}
        if restore_checkpoint_hashes(saved) != expected:
            write_json_atomic(saved / "UNVERIFIED.json", {"reason": "restored_hash_mismatch"})
            raise RuntimeError("Checkpoint restored parameter hashes differ from optimizing learner")
        latest_checkpoint, last_checkpoint_step = saved, state["env_steps"]
        write_json_atomic(saved / "parameter_hashes.json", expected)
        write_json_atomic(saved / "run_state.json", state)
        write_json_atomic(output / "run_state.json", state)
        index = load_checkpoint_index(output)
        relative = saved.relative_to(output).as_posix()
        index.update(latest=relative)
        if state.get("best_checkpoint"):
            index["inherited_best"] = state["best_checkpoint"]
            index["best_fixed_recall"] = state["best_fixed_recall"]
            if index.get("best") is None:
                index["best"] = state["best_checkpoint"]
        index["checkpoints"].append({"env_steps": state["env_steps"], "path": relative, "verified": True})
        write_checkpoint_index(output, index)
        return saved

    def evaluate():
        nonlocal status, reasons
        checkpoint()
        heartbeat({"phase": "evaluation"})
        report = evaluate_cohorts(synchronized_modules(algorithm), evaluation_index=state["evaluation_index"],
                                  config_path=config.get("evaluation_cohorts_path"), seed_splits_path=config.get("seed_splits_path"),
                                  smoke=args.smoke_evaluation, max_steps_override=48 if args.smoke_evaluation else None,
                                  training_probe_config=config)
        report["env_steps"] = state["env_steps"]
        report_path = output / "evaluations" / f"step_{state['env_steps']:012d}_eval_{state['evaluation_index']:04d}.json"
        write_evaluation(report, report_path)
        score = fixed_score(report)
        state["recall_history"].append(score)
        if report["summary"].get("train_development_gap") is not None:
            state["gap_history"].append(float(report["summary"]["train_development_gap"]))
        state["shadow_gap_history"].append(score - float(report["summary"]["shadow_mean_recall"]))
        decision = evaluate_gate(report, env_steps=state["env_steps"], definition=gates,
                                 recall_history=state["recall_history"], reference_recall=reference,
                                 gap_history=state["gap_history"], shadow_gap_history=state["shadow_gap_history"])
        if decision["status"] == "continue" and (state["best_fixed_recall"] is None or score > state["best_fixed_recall"]):
            state["best_fixed_recall"] = score
            state["best_checkpoint"] = str(latest_checkpoint)
            index = load_checkpoint_index(output)
            index.update(best=latest_checkpoint.relative_to(output).as_posix(), best_fixed_recall=score)
            write_checkpoint_index(output, index)
        state["evaluation_index"] += 1
        state["last_evaluation_step"] = state["env_steps"]
        write_json_atomic(latest_checkpoint / "run_state.json", state)
        write_json_atomic(output / "run_state.json", state)
        heartbeat({"phase": "evaluation_complete", "evaluation": report["summary"], "gate": decision})
        if decision["status"] != "continue":
            status = "aborted" if decision["status"] == "abort" else "paused"
            reasons = decision["abort_reasons"] + decision["pause_reasons"]
        return report, decision

    try:
        ray.init(include_dashboard=False, num_cpus=int(config.get("num_cpus", 2)),
                 num_gpus=math.ceil(float(config.get("num_gpus_per_learner", 0))), log_to_driver=False)
        algorithm = build_ppo_config(config).build_algo()
        if args.resume:
            algorithm.restore_from_path(str(args.resume.resolve()))
            runner_count = max(1, int(config.get("num_env_runners", 0)) + 1)
            restore_schedules(algorithm, state["schedules"], previous_runner_count=state.get("runner_count"), runner_count=runner_count)
            state["runner_count"] = runner_count
        initial_health = current_health = learner_health(algorithm, require_cuda=require_cuda)
        if current_health["failures"]:
            raise RuntimeError(", ".join(current_health["failures"]))
        synchronized_modules(algorithm)
        safe_to_checkpoint = True
        checkpoint()
        heartbeat({"phase": "initialized", "learner_health": current_health})
        if args.initial_evaluation:
            evaluate()
        previous_hashes = {name: current_health["policies"][name]["sha256"] for name in POLICIES}
        stagnant = dict.fromkeys(POLICIES, 0)
        last_evaluation_time = time.monotonic()
        for iteration in range(1, iterations + 1):
            if status != "completed":
                break
            if args.max_seconds and time.monotonic() - started >= args.max_seconds:
                status, reasons = "budget_exhausted", ["wall_clock_budget"]
                break
            if target_steps and state["env_steps"] >= target_steps:
                break
            safe_to_checkpoint = False
            result = algorithm.train()
            runners, learners = result.get("env_runners", {}), result.get("learners", {})
            previous_steps = state["env_steps"]
            state["env_steps"] = int(result.get("num_env_steps_sampled_lifetime", 0))
            row = {"iteration": iteration, "env_steps": state["env_steps"],
                   "elapsed_seconds": time.monotonic() - started,
                   "episode_return_mean": float(runners.get("episode_return_mean", float("nan"))),
                   "episode_length_mean": float(runners.get("episode_len_mean", float("nan")))}
            for name, short in ((ROVER_POLICY, "rover"), (DRONE_POLICY, "drone")):
                loss = learners.get(name, {}).get("policy_loss")
                row[f"{short}_policy_loss"] = float(loss) if loss is not None else None
            health_failures = iteration_health(row)
            if not config.get("curriculum", True):
                for field in ("rover_policy_loss", "drone_policy_loss"):
                    if row[field] is None:
                        health_failures.append(f"missing_mixed_team_learner_metric:{field}")
            if state["env_steps"] <= previous_steps:
                health_failures.append("environment_steps_stalled")
            current_health = learner_health(algorithm, require_cuda=require_cuda)
            health_failures.extend(current_health["failures"])
            for name in POLICIES:
                changed = current_health["policies"][name]["sha256"] != previous_hashes[name]
                short = "rover" if name == ROVER_POLICY else "drone"
                if row[f"{short}_policy_loss"] is not None:
                    stagnant[name] = 0 if changed else stagnant[name] + 1
                    if stagnant[name] >= 3:
                        health_failures.append(f"policy_parameters_stagnant:{name}")
                previous_hashes[name] = current_health["policies"][name]["sha256"]
            row["health_failures"] = health_failures
            rows.append(row)
            persist_history(output, rows)
            print(json.dumps(json_safe(row), allow_nan=False), flush=True)
            heartbeat({"phase": "training", "learner_health": current_health, "health_failures": health_failures})
            if health_failures:
                status, reasons = "aborted", health_failures
                break
            safe_to_checkpoint = True
            write_json_atomic(output / "run_state.json", state)
            interval = int(config.get("checkpoint_interval_steps", 0))
            if interval > 0 and state["env_steps"] // interval > last_checkpoint_step // interval:
                checkpoint()
            interval = int(config.get("evaluation_interval_steps", 0))
            seconds = int(config.get("evaluation_interval_seconds", 0))
            due = interval > 0 and state["env_steps"] // interval > state["last_evaluation_step"] // interval
            due = due or (seconds > 0 and time.monotonic() - last_evaluation_time >= seconds)
            if due:
                report, decision = evaluate()
                row["development_fixed_recall"] = fixed_score(report)
                row["gate_status"] = decision["status"]
                persist_history(output, rows)
                last_evaluation_time = time.monotonic()
        if safe_to_checkpoint:
            checkpoint()
    except KeyboardInterrupt:
        status, reasons = "interrupted", stop_requested or ["SIGINT"]
        if algorithm is not None and safe_to_checkpoint:
            checkpoint()
    except Exception as error:
        status, reasons = "aborted", [f"{type(error).__name__}: {error}"]
        exception_text = traceback.format_exc()
        print(exception_text, flush=True)
    finally:
        final_policies = {}
        if initial_health and current_health:
            for name in POLICIES:
                final_policies[name] = {"initial_sha256": initial_health["policies"][name]["sha256"],
                                        "final_sha256": current_health["policies"][name]["sha256"],
                                        "parameter_count": current_health["policies"][name]["parameter_count"],
                                        "device": current_health["policies"][name]["device"]}
        summary = {"iterations_requested": iterations, "iterations_completed": len(rows),
                   "env_steps": state["env_steps"], "checkpoint": str(latest_checkpoint) if latest_checkpoint else None,
                   "resumed_from": str(args.resume.resolve()) if args.resume else None,
                   "termination_status": status, "termination_reasons": reasons,
                   "elapsed_seconds": time.monotonic() - started, "policy_contract": policy_contract(),
                   "policies": final_policies, "weights_updated": bool(final_policies) and all(
                       item["initial_sha256"] != item["final_sha256"] for item in final_policies.values()),
                   "exception": exception_text, "last_checkpoint_is_verified": latest_checkpoint is not None}
        write_json_atomic(output / "training_summary.json", summary)
        marker = {"completed": "COMPLETED", "budget_exhausted": "BUDGET_EXHAUSTED", "paused": "PAUSED", "interrupted": "INTERRUPTED"}.get(status, "ABORTED")
        write_json_atomic(output / f"{marker}.json", summary)
        persist_history(output, rows)
        heartbeat({"status": status, "termination_reasons": reasons})
        if rows:
            figure, axis = plt.subplots(figsize=(8, 4.5))
            axis.plot([row["env_steps"] for row in rows], [row["episode_return_mean"] for row in rows])
            axis.set(title="PPO training", xlabel="Environment steps", ylabel="Mean return")
            figure.tight_layout()
            figure.savefig(output / "training_curve.png", dpi=120)
            plt.close(figure)
        if algorithm is not None:
            algorithm.stop()
        ray.shutdown()
        signal.signal(signal.SIGTERM, previous_sigterm)
        print(json.dumps(json_safe(summary), indent=2, allow_nan=False), flush=True)
    if status == "paused":
        raise SystemExit(3)
    if status == "aborted":
        raise SystemExit(2)
    if status == "interrupted":
        raise SystemExit(130)
    if rows and not summary["weights_updated"] and not config.get("curriculum", True):
        raise SystemExit("FAIL: both policy weights must update in a mixed-team run")


if __name__ == "__main__":
    main()
