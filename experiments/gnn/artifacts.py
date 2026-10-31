"""Experiment provenance and admission checks, separate from immutable releases."""
from pathlib import Path
import json

from experiments.gnn.attention import ARCHITECTURE
from swarm_sar.learning.release import file_hash, source_paths, tree_manifest

ROOT = Path(__file__).resolve().parents[2]


def source_hashes():
    paths = set(source_paths(ROOT)) | set((ROOT / "experiments/gnn").glob("*.py"))
    return {p.relative_to(ROOT).as_posix(): file_hash(p) for p in sorted(paths)}


def verified_manifest(directory, *, filename="manifest.json", verify_sources=True):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / filename).read_text())
    if manifest.get("architecture") != ARCHITECTURE or manifest.get("final_seeds_used") is not False:
        raise ValueError("Wrong graph architecture or development provenance")
    if any(p.is_symlink() for p in directory.rglob("*")):
        raise ValueError("Symlinks are not allowed in a candidate artifact")
    actual = tree_manifest(directory)
    actual.pop(filename, None)
    if actual != manifest.get("files"):
        raise ValueError("Candidate artifact integrity failed")
    if verify_sources and manifest.get("source_sha256") != source_hashes():
        raise ValueError("Candidate source differs from this checkout; use the recorded experiment source")
    return manifest


def assert_paired_reports(original, candidate):
    """Reject incomplete/unmatched cohorts before computing any comparison."""
    if original.get("final_seeds_used") is not False or candidate.get("final_seeds_used") is not False:
        raise ValueError("Only development comparisons are accepted")
    for field in ("seed_split", "seeds", "fixed_seeds", "shadow_seeds"):
        if original.get(field) != candidate.get(field):
            raise ValueError(f"Mismatched report field: {field}")
    if not original.get("cohorts") or set(original["cohorts"]) != set(candidate.get("cohorts", {})):
        raise ValueError("Incomplete/mismatched cohort set")
    for name, left in original["cohorts"].items():
        right = candidate["cohorts"][name]
        for field in ("definition", "effective_max_steps"):
            if left.get(field) != right.get(field):
                raise ValueError(f"Mismatched {field}: {name}")
        for report in (left, right):
            seeds = [row["seed"] for row in report["episodes"]]
            if seeds != original["seeds"] or len(seeds) != len(set(seeds)):
                raise ValueError(f"Missing/duplicate/reordered episodes: {name}")
        for a, b in zip(left["episodes"], right["episodes"]):
            for field in ("seed", "survivors_total", "rover_count", "drone_count", "network_enabled"):
                if a.get(field) != b.get(field):
                    raise ValueError(f"Mismatched episode {field}: {name}")
