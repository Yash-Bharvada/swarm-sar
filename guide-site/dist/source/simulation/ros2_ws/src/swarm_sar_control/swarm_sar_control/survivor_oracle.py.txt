"""Noisy thermal/acoustic proxy; truth poses are never published directly."""

from __future__ import annotations

import math
import random
import xml.etree.ElementTree as ET

import rclpy
from rclpy.executors import ExternalShutdownException
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from visualization_msgs.msg import Marker, MarkerArray

from swarm_sar_interfaces.msg import SurvivorEvidence

from .peer_network_bridge import _intersects


def survivors_from_world(path):
    """Use the same survivor XY poses that Gazebo renders."""
    world = ET.parse(path).getroot().find("world")
    survivors = {}
    for entity in list(world.findall("model")) + list(world.findall("include")):
        name = entity.get("name") or entity.findtext("name", "")
        if name.startswith("survivor_"):
            pose = list(map(float, entity.findtext("pose").split()))
            survivors[name] = pose[:2]
    if not survivors:
        raise ValueError("World contains no survivor poses")
    return [value for name in sorted(survivors) for value in survivors[name]]


class SurvivorOracle(Node):
    def __init__(self) -> None:
        super().__init__("survivor_oracle")
        self.declare_parameter("agents", ["rover_0", "rover_1", "drone_0", "drone_1"])
        self.declare_parameter("survivors", [-14.0, 13.0, -2.0, 6.0, 14.0, 14.0, 13.0, -14.0, -13.0, -12.0])
        self.declare_parameter("world_file", "")
        self.declare_parameter("thermal_radius", 6.0)
        self.declare_parameter("acoustic_radius", 11.0)
        self.declare_parameter("noise_std", 0.04)
        self.declare_parameter("seed", 73)
        self.declare_parameter("spawn_positions", [-16.0, -17.0, -14.0, -17.0, -16.0, -14.0, -13.5, -14.0])
        self.declare_parameter("wall_segments", [-8.0, -9.0, -8.0, 13.0, -4.0, 9.0, 14.0, 9.0, 7.0, -14.0, 7.0, 4.0, -7.5, -9.0, 5.5, -9.0, 7.5, 2.0, 18.5, 2.0])
        self.agents = [str(value) for value in self.get_parameter("agents").value]
        spawn = list(map(float, self.get_parameter("spawn_positions").value))
        self.offsets = {agent: (spawn[2 * index], spawn[2 * index + 1]) for index, agent in enumerate(self.agents)}
        raw_survivors = list(map(float, self.get_parameter("survivors").value))
        if self.get_parameter("world_file").value:
            raw_survivors = survivors_from_world(self.get_parameter("world_file").value)
        self.survivors = [(raw_survivors[i], raw_survivors[i + 1]) for i in range(0, len(raw_survivors) - 1, 2)]
        raw_walls = list(map(float, self.get_parameter("wall_segments").value))
        self.walls = [((raw_walls[i], raw_walls[i + 1]), (raw_walls[i + 2], raw_walls[i + 3])) for i in range(0, len(raw_walls) - 3, 4)]
        self.rng = random.Random(int(self.get_parameter("seed").value))
        self.positions: dict[str, tuple[float, float]] = {}
        self.evidence_publishers = {agent: self.create_publisher(SurvivorEvidence, f"/{agent}/survivor_evidence", 10) for agent in self.agents}
        self.marker_pub = self.create_publisher(MarkerArray, "/survivor_markers", 10)
        self.odom_subscriptions = [self.create_subscription(Odometry, f"/{agent}/odom", lambda msg, source=agent: self._odom(source, msg), qos_profile_sensor_data) for agent in self.agents]
        self.create_timer(0.5, self._sense)

    def _odom(self, agent: str, msg: Odometry) -> None:
        offset = self.offsets.get(agent, (0.0, 0.0))
        self.positions[agent] = (msg.pose.pose.position.x + offset[0], msg.pose.pose.position.y + offset[1])

    def _sense(self) -> None:
        thermal_radius = float(self.get_parameter("thermal_radius").value)
        acoustic_radius = float(self.get_parameter("acoustic_radius").value)
        noise = float(self.get_parameter("noise_std").value)
        for agent, position in self.positions.items():
            for survivor_id, survivor in enumerate(self.survivors):
                distance = math.dist(position, survivor)
                walls = sum(_intersects(position, survivor, start, end) for start, end in self.walls)
                line_of_sight = walls == 0
                thermal = math.exp(-distance / 3.0) * (0.30 ** walls) if distance <= thermal_radius else 0.0
                acoustic = math.exp(-distance / 6.0) * (0.60 ** walls) if distance <= acoustic_radius else 0.0
                thermal = max(0.0, min(1.0, thermal + self.rng.gauss(0.0, noise)))
                acoustic = max(0.0, min(1.0, acoustic + self.rng.gauss(0.0, noise * 1.5)))
                if max(thermal, acoustic) < 0.08:
                    continue
                msg = SurvivorEvidence()
                msg.header.stamp, msg.header.frame_id = self.get_clock().now().to_msg(), "map"
                msg.source_id = agent
                msg.thermal_confidence, msg.acoustic_confidence = thermal, acoustic
                msg.line_of_sight = line_of_sight
                msg.confirmed = thermal >= 0.62 and acoustic >= 0.28
                sigma = max(0.12, 1.2 * (1.0 - max(thermal, acoustic)))
                msg.estimated_pose.pose.position.x = survivor[0] + self.rng.gauss(0.0, sigma)
                msg.estimated_pose.pose.position.y = survivor[1] + self.rng.gauss(0.0, sigma)
                msg.estimated_pose.pose.orientation.w = 1.0
                msg.estimated_pose.covariance[0] = msg.estimated_pose.covariance[7] = sigma * sigma
                self.evidence_publishers[agent].publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SurvivorOracle()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
