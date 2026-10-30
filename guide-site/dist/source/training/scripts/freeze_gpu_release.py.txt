"""Freeze/verify the exact Python training source for the rashiyaom release."""

import argparse
from pathlib import Path

from swarm_sar.learning.release import atomic_json, build_source_manifest, verify_source_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.verify:
        print(verify_source_manifest(root))
    else:
        atomic_json(root / "training/artifacts/gpu_v2/source_manifest.json", build_source_manifest(root))


if __name__ == "__main__":
    main()
