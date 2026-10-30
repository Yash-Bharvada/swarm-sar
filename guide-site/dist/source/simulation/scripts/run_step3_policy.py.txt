"""Run a restored Step 3 checkpoint with a user-selected heterogeneous team."""

import argparse
import json
from pathlib import Path

import ray
from ray.rllib.algorithms.algorithm import Algorithm

from swarm_sar.learning.inference import evaluate_modules
from swarm_sar.learning.training import (
    DRONE_POLICY,
    ROVER_POLICY,
    register_swarm_env,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("models/step3/checkpoint"),
    )
    parser.add_argument("--rovers", type=int, default=2)
    parser.add_argument("--drones", type=int, default=2)
    parser.add_argument("--seed", type=int, default=900)
    parser.add_argument("--world-size", type=int, default=32)
    parser.add_argument("--max-steps", type=int, default=400)
    parser.add_argument("--network", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--deterministic", action="store_true")
    args = parser.parse_args()
    if args.rovers < 0 or args.drones < 0 or not 1 <= args.rovers + args.drones <= 16:
        raise SystemExit("The current 4x4 spawn supports a total of 1-16 robots")
    checkpoint = args.checkpoint.resolve()
    if not checkpoint.exists():
        raise SystemExit(f"Checkpoint not found: {checkpoint}")

    ray.init(include_dashboard=False, num_cpus=2, log_to_driver=False)
    algorithm = None
    try:
        register_swarm_env()
        algorithm = Algorithm.from_checkpoint(str(checkpoint))
        modules = {
            ROVER_POLICY: algorithm.get_module(ROVER_POLICY),
            DRONE_POLICY: algorithm.get_module(DRONE_POLICY),
        }
        rows = evaluate_modules(
            modules,
            seeds=[args.seed],
            team_profile={"rover": args.rovers, "drone": args.drones},
            network_enabled=args.network,
            max_steps=args.max_steps,
            world_size=args.world_size,
            stochastic=not args.deterministic,
        )
        print(json.dumps(rows[0], indent=2))
    finally:
        if algorithm is not None:
            algorithm.stop()
        ray.shutdown()


if __name__ == "__main__":
    main()
