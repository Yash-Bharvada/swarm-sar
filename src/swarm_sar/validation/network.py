"""Large irregular variable-team profiles for the Step 4 network audit."""

import copy
from pathlib import Path

import numpy as np

from swarm_sar.utils.config import load_config

MIN_SURVIVOR_RECALL = 0.90
MIN_HIGH_LOSS_RECALL = 0.85
MIN_NETWORK_OFF_RECALL = 0.50
MIN_MEAN_COVERAGE = 0.50
MAX_COLLISIONS = 0
MAX_PACKET_LOSS = 0.30


def network_scalability_configs(seed: int, packet_loss: float):
    if not 0.0 <= packet_loss <= MAX_PACKET_LOSS:
        raise ValueError("Step 4 packet loss must be between 0 and 30 percent")
    root = Path(__file__).resolve().parents[3]
    world = load_config(root / "configs/world.yaml")
    robots = copy.deepcopy(load_config(root / "configs/robots.yaml"))
    sim = load_config(root / "configs/sim.yaml")
    controller = load_config(root / "configs/network.yaml")
    rng = np.random.default_rng(int(seed) ^ 0x5354455034)
    short_side = int(rng.integers(64, 97))
    long_side = int(rng.integers(max(112, short_side + 20), 181))
    if bool(rng.integers(2)):
        height, width = short_side, long_side
    else:
        height, width = long_side, short_side
    storage_area = height * width
    estimated_site_area = int(storage_area * 0.42)
    agent_count = int(np.clip(round(estimated_site_area / 700), 4, 10))
    rover_count = int(rng.integers(1, agent_count))
    drone_count = agent_count - rover_count
    target_rooms = max(24, estimated_site_area // 78)
    max_steps = max(
        1200,
        int(round(400 * (storage_area / 1024) * (4 / agent_count))),
    )
    world.update(
        height=height,
        width=width,
        footprint="procedural",
        victim_min_dist_from_spawn=max(14, short_side // 3),
        victim_min_dist_between=max(6, short_side // 10),
        num_victims=[2, 5],
        num_rooms=[target_rooms, target_rooms + max(5, target_rooms // 8)],
        rubble_patches=max(8, estimated_site_area // 220),
        max_generation_retries=100,
        min_free_ratio=0.14,
    )
    sim.update(
        agent_counts={"rover": rover_count, "drone": drone_count},
        max_steps=max_steps,
        frontier_samples_per_cluster=5,
        investigate_confirms_victims=True,
        network_enabled=True,
        network_packet_loss=float(packet_loss),
        network_delay_steps=[1, 4],
        network_message_ttl=12,
        network_bandwidth_bytes=8192,
        network_wall_attenuation=0.65,
        network_require_los=False,
        network_snapshot_interval=6,
        network_map_chunk_cells=96,
        network_transform_uncertainty_max=4.0,
        network_partition_windows=[
            {"start": 20, "end": 60, "agents": ["rover_0"]}
        ],
    )
    controller.update(
        max_steps=max_steps,
        topology_update_interval=max(6, max(height, width) // 18),
    )
    for config in robots.values():
        config["battery"] = max(float(config["battery"]), max_steps * 1.15)
    case = {
        "height": height,
        "width": width,
        "agents": agent_count,
        "rovers": rover_count,
        "drones": drone_count,
        "packet_loss": packet_loss,
        "max_steps": max_steps,
    }
    return world, robots, sim, controller, case
