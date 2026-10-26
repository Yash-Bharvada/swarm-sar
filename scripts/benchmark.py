"""Measure complete environment steps per second without rendering."""

import argparse
import time

from swarm_sar.sim.engine import SwarmWorld


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=12345)
    args = parser.parse_args()
    world = SwarmWorld()
    world.reset(args.seed)
    completed = 0
    started = time.perf_counter()
    while completed < args.steps:
        actions = world.rng.integers(0, 5, size=len(world.robots)).tolist()
        _, _, done = world.step(actions)
        completed += 1
        if done and completed < args.steps:
            world.reset(args.seed + completed)
    elapsed = time.perf_counter() - started
    rate = completed / elapsed
    print(f"{completed} environment steps in {elapsed:.3f}s: {rate:,.0f} steps/s")
    print("PASS: speed gate met" if rate >= 1000 else "BELOW TARGET: profile before Part 2")


if __name__ == "__main__":
    main()
