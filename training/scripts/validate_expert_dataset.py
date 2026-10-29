"""Validate hashes, shapes, masks and counts in an expert dataset."""

import argparse
import json
from pathlib import Path

from swarm_sar.learning.demonstrations import dataset_summary, validate_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--display-path")
    args = parser.parse_args()
    manifest = validate_dataset(args.dataset)
    if args.summary is not None:
        expected = json.loads(args.summary.read_text(encoding="utf-8"))
        actual = dataset_summary(args.dataset, display_path=args.display_path)
        if expected != actual:
            raise SystemExit("FAIL: tracked expert summary differs from dataset")
    print(
        f"PASS: {manifest['rows']} rows across {len(manifest['chunks'])} chunks "
        f"and {manifest['episode_count']} episodes"
    )


if __name__ == "__main__":
    main()
