"""Run the audited BC -> qualification -> PPO pilot -> continuation workflow."""

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from swarm_sar.learning.gpu_pipeline import (
    PipelineStop, Supervisor, archive_handoff, closed_loop_qualification,
    pilot_qualification, read_json, selected_checkpoint, choose_candidate,
)
from swarm_sar.learning.release import atomic_json


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("training/datasets/expert_train_gpu_v2"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--hours", type=float, default=15.0)
    parser.add_argument("--started-epoch", type=float, help="Launcher start time; installation counts toward the same budget")
    parser.add_argument("--plan", action="store_true", help="Show stages without starting any process")
    args = parser.parse_args()
    if not 0 < args.hours <= 24:
        parser.error("hours must be in (0,24]")
    stages = ["source_and_cuda_preflight", "repository_tests", "frozen_baseline_verification", "contract_verification", "bc_gpu_smoke", "class_balanced_bc", "bc_closed_loop_vs_baselines", "ppo_gpu_smoke", "ppo_one_hour_pilot", "pilot_closed_loop", "qualified_continuation", "final_development_report_and_hashes"]
    if args.plan:
        print(json.dumps({"hours": args.hours, "branch": "rashiyaom", "dataset": str(args.dataset), "stages": stages, "final_test_seeds": "sealed"}, indent=2))
        return
    output = (args.output or Path("training/runs") / ("gpu_pipeline_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))).resolve()
    if output.exists():
        parser.error("output must be a new directory; previous evidence is never overwritten")
    output.mkdir(parents=True)
    dataset = args.dataset.resolve()
    python = sys.executable
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    setup_elapsed = max(0.0, time.time() - args.started_epoch) if args.started_epoch else 0.0
    supervisor = Supervisor(output, ROOT, time.monotonic() + max(0.0, args.hours * 3600 - setup_elapsed))
    checkpoint = None
    status, reason = "stopped", "not_started"
    lock = (ROOT / "training/runs/.gpu_pipeline.lock").open("a")
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def terminate(signum, frame):
        del signum, frame
        raise KeyboardInterrupt("Supervisor received SIGTERM")

    signal.signal(signal.SIGTERM, terminate)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise PipelineStop("Another managed GPU pipeline is active") from error
        atomic_json(output / "run_definition.json", {"git_commit": commit, "hours": args.hours, "setup_elapsed_seconds": setup_elapsed, "dataset": str(dataset), "stages": stages})

        def run(name, script, arguments=(), seconds=1800, allowed_codes=(0,)):
            return supervisor.run(name, [python, str(ROOT / "training/scripts" / script), *map(str, arguments)], seconds=seconds, allowed_codes=allowed_codes)

        run("host_preflight", "preflight_gpu.py", ["--dataset", dataset, "--host-only", "--output", output / "host_preflight.json"], seconds=120)
        if not dataset.exists():
            run("dataset_export", "export_step4_expert.py", ["--episodes", "2000", "--output", dataset], seconds=min(5400, args.hours * 1800))
        run("preflight", "preflight_gpu.py", ["--dataset", dataset, "--output", output / "preflight.json"], seconds=600)
        supervisor.run("tests", [python, "-m", "pytest", "-q"], seconds=900)
        supervisor.run("package_versions", [python, "-m", "pip", "freeze"], seconds=120)
        run("baseline_integrity", "freeze_training_baseline.py", ["--verify"], seconds=120)
        run("contract_integrity", "verify_policy_contract.py", seconds=120)
        run("bc_smoke", "train_behavior_cloning.py", ["--dataset", dataset, "--output", output / "bc_smoke", "--smoke", "--num-cpus", "4", "--num-gpus", "1"], seconds=600)
        bc_dir = output / "bc"
        run("behavior_cloning", "train_behavior_cloning.py", ["--dataset", dataset, "--output", bc_dir, "--num-cpus", "8", "--num-gpus", "1", "--max-seconds", str(min(7200, supervisor.remaining() * 0.25))], seconds=min(9000, supervisor.remaining() * 0.30), allowed_codes=(0, 1))
        bc_summary = read_json(bc_dir / "summary.json")
        checkpoint = Path(bc_summary["checkpoint"])
        if bc_summary["diagnostic"] or not bc_summary["quality_passed"] or not bc_summary["checkpoint_roundtrip_passed"] or bc_summary["training_device"] != "cuda:0":
            raise PipelineStop("BC quality, CUDA-device, or checkpoint roundtrip gate failed")
        reference_path = output / "bc_evaluation.json"
        run("bc_evaluation", "evaluate_gpu_checkpoint.py", ["--checkpoint", checkpoint, "--output", reference_path, "--include-baselines"], seconds=3600)
        reference = read_json(reference_path)
        qualification = closed_loop_qualification(reference)
        atomic_json(output / "bc_qualification.json", qualification)
        if not qualification["passed"]:
            raise PipelineStop(qualification["reason"])
        run("ppo_smoke", "train_step3.py", ["--config", "training/configs/training_gpu_a5000.yaml", "--resume", checkpoint, "--output", output / "ppo_smoke", "--smoke", "--num-cpus", "4", "--num-env-runners", "2", "--num-gpus-per-learner", "1"], seconds=900)
        pilot_dir = output / "pilot"
        code = run("ppo_pilot", "train_step3.py", ["--config", "training/configs/training_gpu_a5000.yaml", "--resume", checkpoint, "--output", pilot_dir, "--target-env-steps", "250000", "--max-seconds", "3600", "--initial-evaluation", "--reference-evaluation", reference_path], seconds=4500, allowed_codes=(0, 3))
        pilot_summary = read_json(pilot_dir / "training_summary.json")
        if code == 3:
            raise PipelineStop("PPO pilot paused: " + str(pilot_summary.get("termination_reasons")))
        candidate = selected_checkpoint(pilot_dir, pilot_summary)
        candidate_path = output / "pilot_evaluation.json"
        run("pilot_evaluation", "evaluate_gpu_checkpoint.py", ["--checkpoint", candidate, "--output", candidate_path], seconds=2400)
        qualification = pilot_qualification(reference, read_json(candidate_path))
        qualification["environment_steps"] = pilot_summary["env_steps"]
        qualification["elapsed_seconds"] = pilot_summary["elapsed_seconds"]
        qualification["environment_steps_per_wall_second"] = pilot_summary["env_steps"] / max(1, pilot_summary["elapsed_seconds"])
        atomic_json(output / "pilot_qualification.json", qualification)
        if not qualification["passed"]:
            raise PipelineStop(qualification["reason"])
        checkpoint = candidate
        qualified_pilot = checkpoint
        qualified_pilot_report = read_json(candidate_path)
        remaining = supervisor.remaining() - 2400
        if remaining >= 900:
            continuation = output / "continuation"
            code = run("ppo_continuation", "train_step3.py", ["--config", "training/configs/training_gpu_a5000.yaml", "--resume", checkpoint, "--output", continuation, "--max-seconds", str(max(1, remaining - 120)), "--reference-evaluation", reference_path], seconds=remaining, allowed_codes=(0, 3))
            summary = read_json(continuation / "training_summary.json")
            candidate = selected_checkpoint(continuation, summary)
            checkpoint = candidate
            if code == 3:
                reason = "Continuation paused; retained best development checkpoint"
        run("candidate_evaluation", "evaluate_gpu_checkpoint.py", ["--checkpoint", checkpoint, "--output", output / "candidate_evaluation.json", "--include-baselines", "--rollout-output", output / "rollouts"], seconds=min(2400, supervisor.remaining()))
        candidate_report = read_json(output / "candidate_evaluation.json")
        if not choose_candidate(qualified_pilot_report, candidate_report):
            checkpoint = qualified_pilot
            atomic_json(output / "selection.json", {"selected": str(checkpoint), "rejected": candidate_report.get("provenance"), "reason": "Continuation did not retain paired fixed-seed performance; kept qualified pilot", "selected_report": str(candidate_path)})
        else:
            atomic_json(output / "selection.json", {"selected": str(checkpoint), "selected_report": str(output / "candidate_evaluation.json")})
        status = "candidate_ready_for_review"
        if reason == "not_started":
            reason = "Completed qualified stages within wall-clock budget"
    except (PipelineStop, KeyboardInterrupt, Exception) as error:
        reason = str(error) or type(error).__name__
        status = "paused" if isinstance(error, PipelineStop) else "aborted"
        print(f"{status.upper()}: {reason}", flush=True)
    finally:
        payload = archive_handoff(output, status=status, reason=reason, checkpoint=checkpoint, commit=commit)
        atomic_json(output / ("COMPLETED.json" if status == "candidate_ready_for_review" else "PAUSED.json" if status == "paused" else "ABORTED.json"), payload)
        print(json.dumps({"status": status, "reason": reason, "handoff": str(output / "HANDOFF.json")}, indent=2), flush=True)
        lock.close()
        signal.signal(signal.SIGTERM, previous_sigterm)
    if status != "candidate_ready_for_review":
        raise SystemExit(3 if status == "paused" else 2)


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    main()
