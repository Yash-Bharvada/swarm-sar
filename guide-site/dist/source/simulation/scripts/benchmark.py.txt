"""Measure PettingZoo frontier-level environment steps per second."""

import argparse
import time

import numpy as np

from swarm_sar.sim.env import DisasterResponseParallelEnv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=12345)
    args = parser.parse_args()
    env = DisasterResponseParallelEnv()
    observations, _ = env.reset(args.seed)
    policy_rng = np.random.default_rng(args.seed + 1)
    completed = 0
    started = time.perf_counter()
    while completed < args.steps:
        actions = {}
        for agent in env.agents:
            valid = np.flatnonzero(observations[agent]["action_mask"])
            actions[agent] = int(policy_rng.choice(valid))
        observations, _, terminations, truncations, _ = env.step(actions)
        completed += 1
        done = not env.agents or all(terminations.values()) or all(truncations.values())
        if done and completed < args.steps:
            observations, _ = env.reset(args.seed + completed)
    elapsed = time.perf_counter() - started
    rate = completed / elapsed
    print(f"{completed} environment steps in {elapsed:.3f}s: {rate:,.0f} steps/s")
    print("PettingZoo frontier-level steps include frontier clustering and A* for all agents.")
    env.close()


if __name__ == "__main__":
    main()
