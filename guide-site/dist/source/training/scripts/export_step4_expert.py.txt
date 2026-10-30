"""Export Step 4 controller decisions as chunked expert demonstrations."""

import argparse
import json
from pathlib import Path

from swarm_sar.learning.demonstrations import (
    DemonstrationWriter,
    collect_episode,
    validate_dataset,
)
from swarm_sar.validation.seeds import load_seed_splits


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("training/runs/expert_train"))
    parser.add_argument("--episodes", type=int, default=2000)
    parser.add_argument("--start-offset", type=int, default=0)
    parser.add_argument("--chunk-size", type=int, default=50_000)
    args = parser.parse_args()
    if args.episodes < 1 or args.start_offset < 0 or args.chunk_size < 1:
        raise SystemExit("episodes and chunk-size must be positive; offset cannot be negative")
    train = load_seed_splits()["train"]
    if args.start_offset + args.episodes > len(train):
        raise SystemExit("Requested expert episodes exceed the immutable training split")
    seeds = list(train)[args.start_offset : args.start_offset + args.episodes]
    writer = DemonstrationWriter(args.output, args.chunk_size)
    rows = []
    for index, seed in enumerate(seeds, start=1):
        row = collect_episode(seed, writer)
        rows.append(row)
        print(
            f"expert {index}/{len(seeds)} seed={seed} "
            f"survivors={row['survivors_found']}/{row['survivors_total']} "
            f"steps={row['steps']}",
            flush=True,
        )
    manifest = writer.finish(rows)
    validate_dataset(args.output)
    print(json.dumps({key: manifest[key] for key in ("rows", "episode_count", "survivors_found", "survivors_total", "action_counts", "policy_counts")}, indent=2))
    print("PASS: expert dataset exported and independently validated")


if __name__ == "__main__":
    main()
