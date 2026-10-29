import importlib.util
from pathlib import Path

from swarm_sar.learning.demonstrations import DemonstrationWriter, collect_episode, sha256_file, validate_dataset


def test_recovery_matches_fresh_export_byte_for_byte(tmp_path):
    script = Path(__file__).resolve().parents[2] / "training/scripts/recover_expert_export.py"
    spec = importlib.util.spec_from_file_location("recover_expert_export", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = DemonstrationWriter(tmp_path / "fresh", chunk_size=128)
    episodes = [collect_episode(seed, original) for seed in range(2)]
    expected = original.finish(episodes)
    log = tmp_path / "export.log"
    log.write_text("\n".join(
        f"expert {index + 1}/2 seed={row['seed']} survivors={row['survivors_found']}/{row['survivors_total']} steps={row['steps']}"
        for index, row in enumerate(episodes)
    ))
    recovered, prefix, start = module.restore_prefix(tmp_path / "fresh", log, tmp_path / "recovered", chunk_size=128)
    assert start == 1
    actual = recovered.finish(prefix + [collect_episode(seed, recovered) for seed in range(start, 2)])
    assert actual == expected
    validate_dataset(tmp_path / "recovered")
    assert sha256_file(tmp_path / "fresh/manifest.json") == sha256_file(tmp_path / "recovered/manifest.json")
