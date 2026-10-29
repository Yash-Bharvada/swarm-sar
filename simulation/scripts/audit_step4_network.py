"""Deep Step 4 audit for decentralized networking and large irregular missions."""

import argparse
import csv
import json
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from swarm_sar.baselines.decentralized import DecentralizedFrontierController
from swarm_sar.network import PeerNetwork
from swarm_sar.sim.env import DisasterResponseParallelEnv
from swarm_sar.sim.engine import SwarmWorld
from swarm_sar.utils.config import load_config
from swarm_sar.validation.network import (
    MAX_COLLISIONS,
    MIN_HIGH_LOSS_RECALL,
    MIN_MEAN_COVERAGE,
    MIN_NETWORK_OFF_RECALL,
    MIN_SURVIVOR_RECALL,
    network_scalability_configs,
)
from swarm_sar.world.cells import WALL


def aggregate(rows: list[dict]) -> dict:
    total = sum(row["survivors_total"] for row in rows)
    found = sum(row["survivors_found"] for row in rows)
    return {
        "episodes": len(rows),
        "survivors_found": found,
        "survivors_total": total,
        "survivor_recall": found / total if total else 0.0,
        "mean_coverage": sum(row["coverage"] for row in rows) / len(rows),
        "collisions": sum(row["collisions"] for row in rows),
        "duplicate_goal_ratio": sum(row["duplicate_goal_steps"] for row in rows)
        / max(1, sum(row["steps"] for row in rows)),
        "minimum_steps_per_second": min(row["steps_per_second"] for row in rows),
    }


def shape_metrics(grid: np.ndarray) -> dict:
    navigable = grid != WALL
    ys, xs = np.where(navigable)
    bbox = int((ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1))
    return {
        "navigable_cells": int(navigable.sum()),
        "irregularity": 1.0 - float(navigable.sum()) / bbox,
    }


def run_mission(seed: int, loss: float, output: Path | None, network_enabled=True):
    world, robots, sim, controller_config, case = network_scalability_configs(seed, loss)
    sim["network_enabled"] = bool(network_enabled)
    if not network_enabled:
        sim["network_partition_windows"] = []
    env = DisasterResponseParallelEnv(
        world_config=world, robot_config=robots, sim_config=sim
    )
    controller = DecentralizedFrontierController(env, controller_config)
    started = time.perf_counter()
    summary = controller.run_episode(seed, output)
    elapsed = time.perf_counter() - started
    row = {
        **case,
        **shape_metrics(env.core.grid),
        "seed": seed,
        "network_enabled": network_enabled,
        "steps": summary["steps"],
        "survivors_found": summary["survivors_found"],
        "survivors_total": summary["survivors_total"],
        "coverage": summary["coverage"],
        "collisions": summary["collisions"],
        "duplicate_goal_steps": summary["duplicate_goal_steps"],
        "elapsed_seconds": elapsed,
        "steps_per_second": summary["steps"] / max(elapsed, 1e-9),
        **{
            f"network_{key}": value
            for key, value in summary["network"].items()
            if isinstance(value, (int, float, bool))
        },
    }
    env.close()
    return row, summary


def transport_property_cases(count: int) -> list[dict]:
    robot_configs = load_config("configs/robots.yaml")
    rows = []
    for case in range(count):
        rng = np.random.default_rng(8000 + case)
        grid = np.zeros((24, 31), dtype=np.int8)
        if case % 3 == 0:
            grid[5:19, 14] = WALL
        robots = [
            SimpleNamespace(
                name="rover_0", type="rover", x=3, y=3, position=(3, 3), alive=True
            ),
            SimpleNamespace(
                name="drone_1",
                type="drone",
                x=int(rng.integers(4, 16)),
                y=int(rng.integers(3, 12)),
                position=(0, 0),
                alive=True,
            ),
        ]
        robots[1].position = (robots[1].x, robots[1].y)
        config = load_config("configs/sim.yaml")
        loss = (0.0, 0.1, 0.3)[case % 3]
        config.update(
            network_enabled=True,
            network_packet_loss=loss,
            network_delay_steps=[case % 2, 1 + case % 4],
            network_message_ttl=8,
            network_partition_windows=(
                [{"start": 1, "end": 2, "agents": ["rover_0"]}]
                if case % 5 == 0
                else []
            ),
        )
        snapshots = []
        deliveries = []
        for _ in range(2):
            network = PeerNetwork(config, 9000 + case)
            network.register([robot.name for robot in robots])
            network.broadcast(
                "rover_0",
                frame_id="common_entry_v1",
                step=0,
                kind="state_delta",
                pose=(3, 3),
                pose_uncertainty=0.1,
                payload={"case": case},
            )
            for step in range(7):
                network.advance(step, robots, robot_configs, grid)
            snapshots.append(network.snapshot())
            deliveries.append(
                [message.to_dict() for message in network.drain("drone_1")]
            )
        if snapshots[0] != snapshots[1] or deliveries[0] != deliveries[1]:
            raise AssertionError(f"Network case {case} is not deterministic")
        if snapshots[0]["messages_delivered"] > snapshots[0]["transmission_attempts"]:
            raise AssertionError("Delivered more messages than attempted")
        rows.append(
            {
                "case": case,
                "packet_loss": loss,
                "messages_delivered": snapshots[0]["messages_delivered"],
                "drops": sum(
                    value
                    for key, value in snapshots[0].items()
                    if key.startswith("dropped_")
                ),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mission-seeds", nargs="+", type=int, default=list(range(800, 812)))
    parser.add_argument("--offline-seeds", nargs="+", type=int, default=list(range(860, 866)))
    parser.add_argument("--property-cases", type=int, default=200)
    parser.add_argument("--generation-cases", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("training/runs/step4_network"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    losses = [0.0, 0.1, 0.3]
    definition = {
        "mission_seeds": args.mission_seeds,
        "packet_loss_cycle": losses,
        "offline_seeds": args.offline_seeds,
        "transport_property_cases": args.property_cases,
        "large_generation_cases": args.generation_cases,
        "dimension_ranges": {"short_side": [64, 96], "long_side": [112, 180]},
        "agent_range": [4, 10],
        "forced_partition": {"agent": "rover_0", "steps": [20, 60]},
        "gates": {
            "minimum_network_recall": MIN_SURVIVOR_RECALL,
            "minimum_30_percent_loss_recall": MIN_HIGH_LOSS_RECALL,
            "minimum_network_off_recall": MIN_NETWORK_OFF_RECALL,
            "minimum_mean_coverage": MIN_MEAN_COVERAGE,
            "maximum_collisions": MAX_COLLISIONS,
            "maximum_duplicate_goal_ratio": 0.35,
            "minimum_throughput_steps_per_second": 5.0,
            "requires_delivery_loss_partition_reconnect_and_map_merge": True,
        },
    }
    (args.output / "audit_definition.json").write_text(
        json.dumps(definition, indent=2), encoding="utf-8"
    )

    properties = transport_property_cases(args.property_cases)
    (args.output / "transport_properties.json").write_text(
        json.dumps(properties, indent=2), encoding="utf-8"
    )
    print(f"transport properties: {len(properties)}/{len(properties)} passed")

    generation_rows = []
    for index in range(args.generation_cases):
        seed = 1000 + index
        world, robots, sim, _, case = network_scalability_configs(
            seed, losses[index % len(losses)]
        )
        core = SwarmWorld(world, robots, sim)
        core.reset(seed)
        if world["height"] == world["width"]:
            raise AssertionError("Step 4 generated a square holdout")
        if not np.all(core.distances[core.grid != WALL] >= 0):
            raise AssertionError("Step 4 generated unreachable navigable cells")
        generation_rows.append({"seed": seed, **case, **shape_metrics(core.grid)})
    (args.output / "generation_properties.json").write_text(
        json.dumps(generation_rows, indent=2), encoding="utf-8"
    )
    print(f"large generation properties: {len(generation_rows)}/{len(generation_rows)} passed")

    mission_rows = []
    for index, seed in enumerate(args.mission_seeds):
        loss = losses[index % len(losses)]
        row, _ = run_mission(seed, loss, args.output / f"seed_{seed}")
        mission_rows.append(row)
        print(
            f"seed {seed}: {row['height']}x{row['width']} agents={row['agents']} "
            f"loss={loss:.0%} survivors={row['survivors_found']}/{row['survivors_total']} "
            f"coverage={row['coverage']:.1%} steps={row['steps']} "
            f"throughput={row['steps_per_second']:.1f}/s",
            flush=True,
        )

    offline_rows = []
    for seed in args.offline_seeds:
        row, _ = run_mission(seed, 0.0, args.output / f"offline_seed_{seed}", False)
        offline_rows.append(row)
        print(
            f"offline seed {seed}: survivors={row['survivors_found']}/"
            f"{row['survivors_total']} coverage={row['coverage']:.1%}",
            flush=True,
        )

    # A smaller exact replay proves action/message scheduling reproducibility.
    replay_sim = load_config("configs/sim.yaml")
    replay_sim.update(
        network_enabled=True,
        network_packet_loss=0.30,
        network_delay_steps=[1, 3],
        network_partition_windows=[{"start": 10, "end": 30, "agents": ["rover_0"]}],
        investigate_confirms_victims=True,
        frontier_samples_per_cluster=5,
    )
    replay_config = load_config("configs/network.yaml")
    first_env = DisasterResponseParallelEnv(sim_config=replay_sim)
    second_env = DisasterResponseParallelEnv(sim_config=replay_sim)
    first = DecentralizedFrontierController(first_env, replay_config)
    second = DecentralizedFrontierController(second_env, replay_config)
    first_summary = first.run_episode(499)
    second_summary = second.run_episode(499)
    deterministic_replay = first_summary == second_summary and first.events == second.events
    first_env.close()
    second_env.close()

    network_summary = aggregate(mission_rows)
    offline_summary = aggregate(offline_rows)
    loss_30_summary = aggregate(
        [row for row in mission_rows if row["packet_loss"] == 0.30]
    )
    transport_totals = {
        key: sum(row.get(f"network_{key}", 0) for row in mission_rows)
        for key in (
            "messages_created",
            "messages_delivered",
            "dropped_loss",
            "dropped_partition",
            "dropped_stale",
            "duplicates_suppressed",
            "bytes_delivered",
            "reconnections",
            "map_cells_merged",
            "map_merges_refused",
        )
    }
    result = {
        "transport_property_cases": len(properties),
        "generation_property_cases": len(generation_rows),
        "networked_missions": network_summary,
        "thirty_percent_loss_missions": loss_30_summary,
        "network_off_missions": offline_summary,
        "transport_totals": transport_totals,
        "maximum_dimension": max(
            max(row["height"], row["width"]) for row in mission_rows
        ),
        "agent_counts": sorted({row["agents"] for row in mission_rows}),
        "minimum_irregularity": min(row["irregularity"] for row in mission_rows),
        "deterministic_replay": deterministic_replay,
    }
    result["passed"] = (
        network_summary["survivor_recall"] >= MIN_SURVIVOR_RECALL
        and loss_30_summary["survivor_recall"] >= MIN_HIGH_LOSS_RECALL
        and offline_summary["survivor_recall"] >= MIN_NETWORK_OFF_RECALL
        and network_summary["mean_coverage"] >= MIN_MEAN_COVERAGE
        and network_summary["collisions"] <= MAX_COLLISIONS
        and offline_summary["collisions"] <= MAX_COLLISIONS
        and network_summary["duplicate_goal_ratio"] <= 0.35
        and network_summary["minimum_steps_per_second"] >= 5.0
        and transport_totals["messages_delivered"] > 0
        and transport_totals["dropped_loss"] > 0
        and transport_totals["dropped_partition"] > 0
        and transport_totals["reconnections"] > 0
        and transport_totals["map_cells_merged"] > 0
        and deterministic_replay
    )
    (args.output / "audit_summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    fields = list(mission_rows[0])
    with (args.output / "missions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(mission_rows)
    with (args.output / "offline_missions.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(offline_rows[0]))
        writer.writeheader()
        writer.writerows(offline_rows)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit("FAIL: Step 4 decentralized network gates were not met")
    print("PASS: Step 4 decentralized network and recovery gates met")


if __name__ == "__main__":
    main()
