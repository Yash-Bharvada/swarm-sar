import hashlib
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "freeze_training_baseline.py"
SPEC = importlib.util.spec_from_file_location("freeze_training_baseline", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_sha256_file_reads_complete_binary_content(tmp_path):
    payload = (b"swarm-baseline\x00" * 100_000) + b"tail"
    path = tmp_path / "artifact.bin"
    path.write_bytes(payload)
    assert MODULE.sha256_file(path) == hashlib.sha256(payload).hexdigest()


def test_shipped_baseline_manifest_has_expected_contract_and_metrics():
    manifest = MODULE.build_manifest()
    assert manifest["policy_contract"] == {
        "observation_version": "step3-v1",
        "encoded_observation_size": 129,
        "action_count": 7,
    }
    assert manifest["reported_metrics"]["ppo_survivor_recall"] > 0.5
    assert "checkpoint/rllib_checkpoint.json" in manifest["files"]


def test_manifest_can_verify_the_historical_source_commit():
    manifest = MODULE.build_manifest(source_git_commit="historical-commit")
    assert manifest["git_commit"] == "historical-commit"
