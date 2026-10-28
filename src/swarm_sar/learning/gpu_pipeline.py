"""Budgeted subprocess supervision and evidence gates for an unattended GPU run."""

from __future__ import annotations

import json
import math
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from swarm_sar.learning.release import atomic_json, tree_manifest


class PipelineStop(RuntimeError):
    """A completed check says further GPU spend is not justified."""


class SubprocessFailure(RuntimeError):
    """Infrastructure failure; distinguish an error from a quality pause."""


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_development_report(report: dict[str, Any]) -> bool:
    summary = report.get("summary", {})
    seeds = report.get("fixed_seeds", [])
    return (
        report.get("seed_split") == "development"
        and report.get("final_seeds_used") is False
        and summary.get("diagnostic_only") is False
        and summary.get("invalid_actions") == 0
        and isinstance(seeds, list)
        and len(seeds) >= 4
        and len(set(seeds)) == len(seeds)
        and all(isinstance(seed, int) and 10000 <= seed < 10100 for seed in seeds)
    )


def paired_cases(reference: dict[str, Any], candidate: dict[str, Any]) -> bool:
    def cases(report):
        return {name: (cohort.get("definition"), cohort.get("effective_max_steps"))
                for name, cohort in report.get("cohorts", {}).items()}
    return reference.get("fixed_seeds") == candidate.get("fixed_seeds") and bool(cases(reference)) and cases(reference) == cases(candidate)


def closed_loop_qualification(report: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    learned = float(summary["fixed_mean_cohort_recall"])
    baselines = summary["baseline_fixed_mean_recalls"]
    random_recall = float(baselines["random_masked"])
    expert_recall = float(baselines["expert"])
    values = (learned, random_recall, expert_recall)
    finite = all(math.isfinite(value) and 0 <= value <= 1 for value in values)
    evidence_of_use = finite and (
        learned >= random_recall + 0.05
        or (learned >= 0.50 and learned >= expert_recall - 0.10)
    )
    valid = valid_development_report(report)
    return {
        "passed": bool(evidence_of_use and valid),
        "learned_fixed_recall": learned,
        "random_fixed_recall": random_recall,
        "expert_fixed_recall": expert_recall,
        "reason": "closed_loop_sanity_passed" if evidence_of_use and valid else "no_useful_closed_loop_warm_start",
        "interpretation": "A small development sanity gate, not a significance or real-world safety claim.",
    }


def pilot_qualification(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    before = float(reference["summary"]["fixed_mean_cohort_recall"])
    after = float(candidate["summary"]["fixed_mean_cohort_recall"])
    finite = all(math.isfinite(value) and 0 <= value <= 1 for value in (before, after))
    improved = finite and after >= before + 0.01
    already_good = finite and after >= 0.85 and after >= before - 0.02
    shadow_before = float(reference["summary"].get("shadow_mean_cohort_recall", float("nan")))
    shadow_after = float(candidate["summary"].get("shadow_mean_cohort_recall", float("nan")))
    shadow_retained = all(math.isfinite(value) and 0 <= value <= 1 for value in (shadow_before, shadow_after)) and shadow_after >= shadow_before - 0.05
    return {
        "passed": bool((improved or already_good) and shadow_retained and valid_development_report(reference) and valid_development_report(candidate) and paired_cases(reference, candidate)),
        "bc_fixed_recall": before,
        "ppo_fixed_recall": after,
        "difference": after - before,
        "shadow_difference": shadow_after - shadow_before,
        "reason": "pilot_improved_or_retained_strong_policy" if improved or already_good else "pilot_did_not_justify_more_compute",
    }


def choose_candidate(reference: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """Promotion requires paired fixed cases and cannot discard a stronger pilot."""
    if not valid_development_report(reference) or not valid_development_report(candidate):
        return False
    if not paired_cases(reference, candidate):
        return False
    before = float(reference["summary"]["fixed_mean_cohort_recall"])
    after = float(candidate["summary"]["fixed_mean_cohort_recall"])
    shadow_before = float(reference["summary"].get("shadow_mean_cohort_recall", float("nan")))
    shadow_after = float(candidate["summary"].get("shadow_mean_cohort_recall", float("nan")))
    return all(math.isfinite(value) and 0 <= value <= 1 for value in (before, after, shadow_before, shadow_after)) and after >= before and shadow_after >= shadow_before - 0.05


def selected_checkpoint(output: Path, summary: dict[str, Any]) -> Path:
    index = read_json(output / "checkpoint_index.json")
    relative = index.get("best") or index.get("latest")
    path = (output / relative).resolve() if relative else Path(summary["checkpoint"]).resolve()
    if not path.is_dir():
        raise PipelineStop(f"Selected checkpoint does not exist: {path}")
    return path


def stop_child(child: subprocess.Popen, grace_seconds: float = 45.0) -> None:
    if child.poll() is not None:
        return
    child.send_signal(signal.SIGINT)
    try:
        child.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "posix":
        os.killpg(child.pid, signal.SIGTERM)
    else:
        child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(child.pid, signal.SIGKILL)
        else:
            child.kill()
        child.wait(timeout=10)


@dataclass
class Supervisor:
    output: Path
    root: Path
    deadline: float
    minimum_free_bytes: int = 10 * 1024**3
    maximum_silence_seconds: float = 1200.0
    stages: list[dict[str, Any]] = field(default_factory=list)

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def run(self, name: str, command: list[str], *, seconds: float, allowed_codes=(0,)) -> int:
        allotted = min(float(seconds), self.remaining())
        if allotted <= 0:
            raise PipelineStop(f"No wall-clock budget remains before {name}")
        log = self.output / "logs" / f"{name}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        stage = {"name": name, "command": command, "log": str(log), "status": "running", "allotted_seconds": allotted}
        self.stages.append(stage)
        atomic_json(self.output / "pipeline_history.json", self.stages)
        print(json.dumps({"stage": name, "log": str(log), "remaining_hours": self.remaining() / 3600}), flush=True)
        child = None
        timed_out = False
        last_log_size, last_progress = 0, started
        try:
            with log.open("w", encoding="utf-8") as handle:
                child = subprocess.Popen(command, cwd=self.root, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
                while child.poll() is None:
                    elapsed = time.monotonic() - started
                    log_size = log.stat().st_size
                    if log_size != last_log_size:
                        last_log_size, last_progress = log_size, time.monotonic()
                    atomic_json(self.output / "heartbeat.json", {"stage": name, "pid": child.pid, "elapsed_seconds": elapsed, "remaining_seconds": self.remaining(), "log": str(log)})
                    if elapsed >= allotted:
                        timed_out = True
                        stop_child(child)
                        break
                    if time.monotonic() - last_progress > self.maximum_silence_seconds:
                        stop_child(child)
                        raise PipelineStop(f"No process log progress for {self.maximum_silence_seconds:g}s in {name}")
                    if shutil.disk_usage(self.output).free < self.minimum_free_bytes:
                        stop_child(child)
                        raise PipelineStop("Disk free space fell below runtime reserve")
                    time.sleep(min(2.0, max(0.01, allotted - elapsed)))
                code = child.wait()
            stage.update(returncode=code, elapsed_seconds=time.monotonic() - started, timed_out=timed_out)
            if timed_out:
                raise PipelineStop(f"Wall-clock limit reached in {name}; inspect saved artifacts")
            if code not in allowed_codes:
                raise SubprocessFailure(f"{name} exited {code}; see {log}")
            stage["status"] = "passed" if code == 0 else "paused"
            return code
        except BaseException as error:
            if child is not None:
                stop_child(child)
            stage.update(status="stopped", reason=str(error), elapsed_seconds=time.monotonic() - started)
            raise
        finally:
            atomic_json(self.output / "pipeline_history.json", self.stages)


def archive_handoff(output: Path, *, status: str, reason: str, checkpoint: Path | None, commit: str) -> dict[str, Any]:
    payload = {
        "schema_version": 2,
        "status": status,
        "reason": reason,
        "git_commit": commit,
        "checkpoint": str(checkpoint) if checkpoint else None,
        "checkpoint_files": tree_manifest(checkpoint) if checkpoint and checkpoint.is_dir() else {},
        "claim_limits": [
            "No physical robot or ROS2/Gazebo validation was performed by this pipeline.",
            "Browser simulation uses a separate controller; a trained checkpoint is not automatically loaded there.",
            "Final evaluation seeds remain sealed; development scores are not final test scores.",
        ],
    }
    atomic_json(output / "HANDOFF.json", payload)
    return payload
