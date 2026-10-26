"""Run a reproducible random-policy baseline and save episode metrics."""

import argparse
from pathlib import Path

import numpy as np

from swarm_sar.sim.engine import SwarmWorld
from swarm_sar.sim.metrics import append_episode_csv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("results/random_baseline.csv"))
    args = parser.parse_args()
    summaries = []
    for episode in range(args.episodes):
        world = SwarmWorld()
        world.reset(args.seed + episode)
        while not world.done:
            actions = world.rng.integers(0, 5, size=len(world.robots)).tolist()
            _, info, _ = world.step(actions)
        row = {"episode": episode, "seed": args.seed + episode, **info}
        append_episode_csv(args.output, row)
        summaries.append(info)
        print(f"episode {episode + 1:3d}/{args.episodes}: victims={info['victims_found']}/{len(world.victims)} coverage={info['coverage']:.1%} steps={info['step']}")
    mean_found = np.mean([row["victims_found"] for row in summaries])
    mean_coverage = np.mean([row["coverage"] for row in summaries])
    print(f"average victims found: {mean_found:.2f}; average coverage: {mean_coverage:.1%}")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
