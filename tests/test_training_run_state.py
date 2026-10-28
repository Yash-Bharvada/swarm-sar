import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "train_step3.py"
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
