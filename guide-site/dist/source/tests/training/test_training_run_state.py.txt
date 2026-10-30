import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "training/scripts" / "train_step3.py"
SPEC = importlib.util.spec_from_file_location("train_step3", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeAlgorithm:
    def save_to_path(self, path):
        output = Path(path)
        output.mkdir(parents=True)
        (output / "checkpoint.txt").write_text("checkpoint", encoding="utf-8")
        return str(output)


def test_checkpoint_index_round_trip_is_atomic(tmp_path):
    payload = MODULE.load_checkpoint_index(tmp_path)
    payload["latest"] = "checkpoints/step_1"
    MODULE.write_checkpoint_index(tmp_path, payload)
    assert MODULE.load_checkpoint_index(tmp_path) == payload
    assert not (tmp_path / "checkpoint_index.json.tmp").exists()


def test_numbered_checkpoint_is_indexed_and_never_overwritten(tmp_path):
    saved = MODULE.save_numbered_checkpoint(FakeAlgorithm(), tmp_path, 123)
    assert saved.name == "step_000000000123"
    index = json.loads((tmp_path / "checkpoint_index.json").read_text())
    assert index["latest"].endswith("step_000000000123")
    assert index["checkpoints"] == [
        {"env_steps": 123, "path": "checkpoints/step_000000000123"}
    ]
    with pytest.raises(FileExistsError):
        MODULE.save_numbered_checkpoint(FakeAlgorithm(), tmp_path, 123)


def test_training_output_never_overwrites_existing_evidence(tmp_path):
    output = tmp_path / "run"
    MODULE.prepare_output_directory(output)
    (output / "evidence.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="non-empty"):
        MODULE.prepare_output_directory(output)


def fake_algorithm_with_envs(envs):
    class Group:
        def foreach_env_runner(self, function, **kwargs):
            return [function(SimpleNamespace(env=SimpleNamespace(envs=[env]))) for env in envs]
    return SimpleNamespace(env_runner_group=Group())


class ScheduleEnv:
    def __init__(self, worker_index):
        self.unwrapped = self
        self.worker_index = worker_index
        self.episode_index = 1

    def restore_schedule(self, state):
        assert state["worker_index"] == self.worker_index
        self.episode_index = max(self.episode_index, state["episode_index"])


def test_resume_preserves_exact_next_episode_counter_per_existing_worker():
    envs = [ScheduleEnv(0), ScheduleEnv(1)]
    algorithm = fake_algorithm_with_envs(envs)
    schedules = [{"worker_index": 0, "episode_index": 5}, {"worker_index": 1, "episode_index": 9}]
    MODULE.restore_schedules(algorithm, schedules, previous_runner_count=2, runner_count=2)
    assert [env.episode_index for env in envs] == [5, 9]


def test_changed_runner_count_advances_beyond_previous_seed_high_watermark():
    envs = [ScheduleEnv(0), ScheduleEnv(1), ScheduleEnv(2)]
    algorithm = fake_algorithm_with_envs(envs)
    schedules = [{"worker_index": 0, "episode_index": 5}, {"worker_index": 1, "episode_index": 9}]
    MODULE.restore_schedules(algorithm, schedules, previous_runner_count=2, runner_count=3)
    previous_high_watermark = 1 + 9 * 2
    assert all(env.worker_index + env.episode_index * 3 > previous_high_watermark for env in envs)


def test_unverified_checkpoint_is_never_published_in_index(tmp_path):
    saved = MODULE.save_numbered_checkpoint(FakeAlgorithm(), tmp_path, 123, publish=False)
    assert saved.exists()
    assert MODULE.load_checkpoint_index(tmp_path)["latest"] is None
