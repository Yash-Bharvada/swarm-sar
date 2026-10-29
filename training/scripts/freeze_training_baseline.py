"""Create or verify an immutable manifest for the shipped Step 3 baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "models" / "step3"
DEFAULT_OUTPUT = ROOT / "training/artifacts" / "training_baseline_v1" / "manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def build_manifest(
    source: Path = DEFAULT_SOURCE, *, source_git_commit: str | None = None
) -> dict[str, Any]:
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Baseline artifact directory does not exist: {source}")
    files = {
        path.relative_to(source).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(source.rglob("*"))
        if path.is_file()
    }
    if not files:
        raise ValueError(f"No baseline files found under {source}")
    validation_path = source / "validation_summary.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "label": "step3-original",
        "source": source.relative_to(ROOT).as_posix(),
        "git_commit": source_git_commit or git_commit(ROOT),
        "policy_contract": {
            "observation_version": "step3-v1",
            "encoded_observation_size": 129,
            "action_count": 7,
        },
        "reported_metrics": {
            "ppo_survivor_recall": validation["ppo"]["survivor_recall"],
            "frontier_survivor_recall": validation["frontier_baseline"][
                "survivor_recall"
            ],
            "held_out_team_recall": validation["held_out_team_generalization"][
                "survivor_recall"
            ],
        },
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify an existing manifest instead of creating it.",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if args.verify:
        if not output.exists():
            raise SystemExit(f"Missing baseline manifest: {output}")
        expected = json.loads(output.read_text(encoding="utf-8"))
        manifest = build_manifest(
            args.source, source_git_commit=str(expected["git_commit"])
        )
        if expected != manifest:
            raise SystemExit("FAIL: shipped Step 3 baseline differs from its manifest")
        print(f"PASS: verified {len(manifest['files'])} baseline files")
        return
    manifest = build_manifest(args.source)
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing baseline manifest: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen {len(manifest['files'])} files in {output}")


if __name__ == "__main__":
    main()
