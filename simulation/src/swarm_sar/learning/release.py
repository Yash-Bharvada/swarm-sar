"""Portable integrity records for source and trained checkpoint transfer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_manifest(root: Path) -> dict[str, dict[str, Any]]:
    return {
        path.relative_to(root).as_posix(): {"bytes": path.stat().st_size, "sha256": file_hash(path)}
        for path in sorted(root.rglob("*")) if path.is_file() and not path.is_symlink()
    }


def source_paths(root: Path) -> list[Path]:
    paths = []
    for folder, pattern in (("simulation/src", "*.py"), ("configs", "*.yaml"), ("training/configs", "*.yaml"), ("simulation/scripts", "*.py"), ("simulation/scripts", "*.sh"), ("training/scripts", "*.py"), ("training/scripts", "*.sh")):
        paths.extend((root / folder).rglob(pattern))
    paths.extend(root / name for name in ("pyproject.toml", "backend/requirements.txt", "training/requirements-gpu.lock"))
    paths.extend(root / name for name in (
        "training/artifacts/policy_contract_gpu_v1.json", "training/artifacts/gpu_v2/expert_dataset_summary.json",
    ))
    return sorted(set(path for path in paths if path.is_file()))


def build_source_manifest(root: Path) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "label": "rashiyaom-gpu-v2",
        "files": {
            path.relative_to(root).as_posix(): {"bytes": path.stat().st_size, "sha256": file_hash(path)}
            for path in source_paths(root)
        },
    }


def verify_source_manifest(root: Path) -> dict[str, Any]:
    path = root / "training/artifacts/gpu_v2/source_manifest.json"
    expected = json.loads(path.read_text())
    actual = build_source_manifest(root)
    if expected != actual:
        changed = sorted(
            name for name in set(expected["files"]) | set(actual["files"])
            if expected["files"].get(name) != actual["files"].get(name)
        )
        raise ValueError("source hash mismatch: " + ", ".join(changed))
    return {"passed": True, "file_count": len(actual["files"]), "manifest_sha256": file_hash(path)}
