from types import SimpleNamespace

import numpy as np

from swarm_sar.network import PeerNetwork
from swarm_sar.sim.env import HOLD, DisasterResponseParallelEnv
from swarm_sar.utils.config import load_config
from swarm_sar.world.cells import FREE, UNKNOWN, WALL


def robot(name, robot_type, x, y):
    return SimpleNamespace(
        name=name,
        type=robot_type,
        x=x,
        y=y,
        position=(x, y),
        alive=True,
    )


def network_config(**updates):
    config = load_config("configs/sim.yaml")
    config.update(
        network_enabled=True,
        network_packet_loss=0.0,
        network_delay_steps=[1, 1],
        network_message_ttl=4,
        network_bandwidth_bytes=8192,
        network_wall_attenuation=0.7,
        network_require_los=False,
        network_partition_windows=[],
    )
    config.update(updates)
    return config


def robot_configs():
    return load_config("configs/robots.yaml")


def send(network, sender="rover_0", step=0, payload=None):
    return network.broadcast(
        sender,
        frame_id="common_entry_v1",
        step=step,
        kind="state_delta",
        pose=(1.0, 1.0),
        pose_uncertainty=0.1,
        payload=payload or {"value": 1},
    )


def test_message_delay_and_delivery_are_deterministic():
    grid = np.zeros((20, 20), dtype=np.int8)
    robots = [robot("rover_0", "rover", 2, 2), robot("drone_1", "drone", 5, 2)]
    first = PeerNetwork(network_config(network_delay_steps=[2, 2]), 9)
    second = PeerNetwork(network_config(network_delay_steps=[2, 2]), 9)
    for network in (first, second):
        network.register([item.name for item in robots])
        send(network)
        network.advance(0, robots, robot_configs(), grid)
        assert network.drain("drone_1") == []
        network.advance(1, robots, robot_configs(), grid)
        assert network.drain("drone_1") == []
        network.advance(2, robots, robot_configs(), grid)
    assert first.drain("drone_1") == second.drain("drone_1")
    assert first.snapshot() == second.snapshot()


def test_range_and_wall_attenuation_block_links():
    grid = np.zeros((20, 20), dtype=np.int8)
    far = [robot("rover_0", "rover", 1, 1), robot("drone_1", "drone", 15, 1)]
    network = PeerNetwork(network_config(network_delay_steps=[0, 0]), 1)
    network.register([item.name for item in far])
    send(network)
    network.advance(0, far, robot_configs(), grid)
    assert not network.drain("drone_1")
    assert network.snapshot()["dropped_range"] == 1

    near = [robot("rover_0", "rover", 2, 2), robot("drone_1", "drone", 8, 2)]
    grid[2, 5] = WALL
    network = PeerNetwork(network_config(network_delay_steps=[0, 0]), 1)
    network.register([item.name for item in near])
    send(network)
    network.advance(0, near, robot_configs(), grid)
    assert not network.drain("drone_1")
    assert network.snapshot()["dropped_wall"] == 1


def test_line_of_sight_mode_rejects_any_intervening_wall():
    grid = np.zeros((20, 20), dtype=np.int8)
    grid[2, 4] = WALL
    robots = [robot("rover_0", "rover", 2, 2), robot("drone_1", "drone", 6, 2)]
    network = PeerNetwork(
        network_config(network_delay_steps=[0, 0], network_require_los=True), 2
    )
    network.register([item.name for item in robots])
    send(network)
    network.advance(0, robots, robot_configs(), grid)
    assert network.drain("drone_1") == []
    assert network.snapshot()["dropped_wall"] == 1


def test_packet_loss_bandwidth_expiry_and_dedup_are_counted():
    grid = np.zeros((10, 10), dtype=np.int8)
    robots = [robot("rover_0", "rover", 2, 2), robot("drone_1", "drone", 3, 2)]
    lossy = PeerNetwork(
        network_config(network_packet_loss=1.0, network_delay_steps=[0, 0]), 3
    )
    lossy.register([item.name for item in robots])
    send(lossy)
    lossy.advance(0, robots, robot_configs(), grid)
    assert lossy.snapshot()["dropped_loss"] == 1

    narrow = PeerNetwork(network_config(network_bandwidth_bytes=1), 3)
    narrow.register([item.name for item in robots])
    send(narrow)
    narrow.advance(0, robots, robot_configs(), grid)
    assert narrow.snapshot()["dropped_bandwidth"] == 1

    expiry = PeerNetwork(network_config(network_message_ttl=1), 3)
    expiry.register([item.name for item in robots])
    message = send(expiry)
    expiry.outboxes["rover_0"].clear()
    expiry.inject_delivery("drone_1", message, deliver_step=3)
    expiry.advance(3, robots, robot_configs(), grid)
    assert expiry.snapshot()["dropped_stale"] == 1

    dedup = PeerNetwork(network_config(), 3)
    dedup.register([item.name for item in robots])
    message = send(dedup)
    dedup.outboxes["rover_0"].clear()
    dedup.inject_delivery("drone_1", message, deliver_step=0)
    dedup.inject_delivery("drone_1", message, deliver_step=0)
    dedup.advance(0, robots, robot_configs(), grid)
    assert len(dedup.drain("drone_1")) == 1
    assert dedup.snapshot()["duplicates_suppressed"] == 1


def test_partition_blocks_then_records_reconnection():
    grid = np.zeros((10, 10), dtype=np.int8)
    robots = [robot("rover_0", "rover", 2, 2), robot("drone_1", "drone", 3, 2)]
    config = network_config(
        network_delay_steps=[0, 0],
        network_partition_windows=[{"start": 0, "end": 2, "agents": ["rover_0"]}],
    )
    network = PeerNetwork(config, 4)
    network.register([item.name for item in robots])
    send(network, step=1)
    network.advance(1, robots, robot_configs(), grid)
    assert network.snapshot()["dropped_partition"] == 1
    send(network, step=3)
    network.advance(3, robots, robot_configs(), grid)
    assert len(network.drain("drone_1")) == 1
    assert network.snapshot()["reconnections"] == 1


def test_environment_merges_only_aligned_delivered_map_cells():
    sim = network_config(
        network_delay_steps=[0, 0],
        network_map_chunk_cells=5000,
        network_snapshot_interval=1,
    )
    env = DisasterResponseParallelEnv(sim_config=sim)
    env.reset(seed=20)
    sender, receiver = env.core.robots[:2]
    candidates = np.argwhere(
        (sender.belief == UNKNOWN) & (receiver.belief == UNKNOWN) & (env.core.grid == FREE)
    )
    y, x = map(int, candidates[-1])
    sender.belief[y, x] = FREE
    env.step({agent: HOLD for agent in env.agents})
    assert receiver.belief[y, x] == FREE
    assert env.network_metrics()["map_cells_merged"] > 0
    env.close()


def test_transform_uncertainty_refuses_map_merge():
    sim = network_config(
        network_delay_steps=[0, 0],
        network_map_chunk_cells=5000,
        network_transform_uncertainty_max=0.2,
    )
    env = DisasterResponseParallelEnv(sim_config=sim)
    env.reset(seed=22)
    sender, receiver = env.core.robots[:2]
    candidates = np.argwhere(
        (sender.belief == UNKNOWN) & (receiver.belief == UNKNOWN) & (env.core.grid == FREE)
    )
    y, x = map(int, candidates[-1])
    sender.belief[y, x] = FREE
    sender.odom_uncertainty = 1.0
    env.step({agent: HOLD for agent in env.agents})
    assert receiver.belief[y, x] == UNKNOWN
    assert env.network_metrics()["map_merges_refused"] > 0
    env.close()


def test_environment_recovers_snapshot_after_partition():
    sim = network_config(
        network_delay_steps=[0, 0],
        network_map_chunk_cells=5000,
        network_snapshot_interval=1,
        network_partition_windows=[
            {"start": 1, "end": 3, "agents": ["rover_0"]}
        ],
    )
    env = DisasterResponseParallelEnv(sim_config=sim)
    env.reset(seed=24)
    sender = env._robots_by_name["rover_0"]
    receiver = env._robots_by_name["rover_1"]
    candidates = np.argwhere(
        (sender.belief == UNKNOWN) & (receiver.belief == UNKNOWN) & (env.core.grid == FREE)
    )
    y, x = map(int, candidates[-1])
    sender.belief[y, x] = FREE
    for _ in range(3):
        env.step({agent: HOLD for agent in env.agents})
    assert receiver.belief[y, x] == UNKNOWN
    env.step({agent: HOLD for agent in env.agents})
    assert receiver.belief[y, x] == FREE
    assert env.network_metrics()["reconnections"] > 0
    env.close()
