import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

from swarm_sar.learning.gpu_pipeline import (
    PipelineStop, SubprocessFailure, Supervisor, archive_handoff, closed_loop_qualification,
    pilot_qualification, choose_candidate,
)
from swarm_sar.learning.release import atomic_json, build_source_manifest, verify_source_manifest


def report(recall, random=0.1, expert=0.9):
    return {"seed_split": "development", "final_seeds_used": False, "fixed_seeds": [10000, 10001, 10002, 10003],
            "cohorts": {"nominal": {"definition": {"world_size": 32}, "effective_max_steps": 400}},
            "summary": {"fixed_mean_cohort_recall": recall, "invalid_actions": 0,
                        "shadow_mean_cohort_recall": recall,
                        "diagnostic_only": False,
                        "baseline_fixed_mean_recalls": {"random_masked": random, "expert": expert}}}


def test_closed_loop_gate_rejects_classifier_only_or_nan_success():
    assert closed_loop_qualification(report(0.6))["passed"]
    assert not closed_loop_qualification(report(0.1))["passed"]
    assert not closed_loop_qualification(report(float("nan")))["passed"]


def test_pilot_must_improve_or_preserve_already_strong_policy():
    assert pilot_qualification(report(0.5), report(0.53))["passed"]
    assert not pilot_qualification(report(0.5), report(0.49))["passed"]
    assert pilot_qualification(report(0.9), report(0.9))["passed"]


@pytest.mark.parametrize("gate", [closed_loop_qualification, lambda item: pilot_qualification(report(0.5), item)])
def test_shortened_or_sealed_evaluation_cannot_qualify_long_training(gate):
    diagnostic = report(0.9)
    diagnostic["summary"]["diagnostic_only"] = True
    assert not gate(diagnostic)["passed"]
    sealed = report(0.9)
    sealed.update(seed_split="final", final_seeds_used=True)
    assert not gate(sealed)["passed"]


def test_impossible_scores_cannot_qualify_or_promote_checkpoint():
    assert not pilot_qualification(report(0.9), report(4.0))["passed"]
    assert not choose_candidate(report(0.9), report(4.0))
    assert not choose_candidate(report(0.9), report(float("nan")))


def test_changed_map_budgets_or_missing_fixed_seeds_cannot_qualify():
    candidate = report(0.9)
    candidate["cohorts"]["nominal"]["effective_max_steps"] = 10
    assert not pilot_qualification(report(0.5), candidate)["passed"]
    assert not choose_candidate(report(0.5), candidate)
    candidate = report(0.9)
    candidate.pop("fixed_seeds")
    assert not closed_loop_qualification(candidate)["passed"]


def test_fixed_score_gain_cannot_hide_rotating_shadow_regression():
    candidate = report(0.8)
    candidate["summary"]["shadow_mean_cohort_recall"] = 0.4
    assert not pilot_qualification(report(0.6), candidate)["passed"]
    assert not choose_candidate(report(0.6), candidate)


def test_continuation_regression_keeps_qualified_pilot():
    assert not choose_candidate(report(0.7), report(0.6))
    assert choose_candidate(report(0.7), report(0.7))
    assert choose_candidate(report(0.7), report(0.8))
    broken = report(0.8)
    broken["summary"]["invalid_actions"] = 1
    assert not choose_candidate(report(0.7), broken)
    different_cases = report(0.9)
    different_cases["fixed_seeds"] = [10004, 10005, 10006, 10007]
    assert not choose_candidate(report(0.7), different_cases)


def test_watchdog_stops_stuck_subprocess_and_keeps_log(tmp_path):
    supervisor = Supervisor(tmp_path, Path.cwd(), time.monotonic() + 5, minimum_free_bytes=0)
    with pytest.raises(PipelineStop, match="Wall-clock"):
        supervisor.run("stuck", [sys.executable, "-c", "import time; print('alive',flush=True); time.sleep(30)"], seconds=0.25)
    history = json.loads((tmp_path / "pipeline_history.json").read_text())
    assert history[0]["timed_out"] is True
    assert history[0]["status"] == "stopped"
    assert "alive" in (tmp_path / "logs/stuck.log").read_text()


def test_subprocess_failure_cannot_be_reported_as_success(tmp_path):
    supervisor = Supervisor(tmp_path, Path.cwd(), time.monotonic() + 5, minimum_free_bytes=0)
    with pytest.raises(SubprocessFailure, match="exited 7"):
        supervisor.run("broken", [sys.executable, "-c", "raise SystemExit(7)"], seconds=3)


def test_release_verifier_detects_edited_or_new_training_code(tmp_path):
    source = tmp_path / "simulation/src"
    source.mkdir(parents=True)
    (source / "module.py").write_text("value = 1\n")
    atomic_json(tmp_path / "training/artifacts/gpu_v2/source_manifest.json", build_source_manifest(tmp_path))
    assert verify_source_manifest(tmp_path)["passed"]
    (source / "module.py").write_text("value = 2\n")
    with pytest.raises(ValueError, match="module.py"):
        verify_source_manifest(tmp_path)


def test_handoff_hashes_checkpoint_and_records_claim_limits(tmp_path):
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "weights.bin").write_bytes(b"testweights")
    report = archive_handoff(tmp_path, status="paused", reason="no_progress", checkpoint=checkpoint, commit="abc")
    assert len(report["checkpoint_files"]["weights.bin"]["sha256"]) == 64
    assert report["status"] == "paused"
    assert report["claim_limits"]
