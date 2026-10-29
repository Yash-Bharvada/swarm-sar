"""Range-, wall-, loss-, delay-, and expiry-aware peer message transport."""

from __future__ import annotations

import heapq
import math
import random

import rclpy
from rclpy.executors import ExternalShutdownException
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from swarm_sar_interfaces.msg import PeerMessageEnvelope


def _orientation(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _intersects(a, b, c, d) -> bool:
    return _orientation(a, b, c) * _orientation(a, b, d) < 0 and _orientation(c, d, a) * _orientation(c, d, b) < 0


class PeerNetworkBridge(Node):
    """Transport only: it never selects goals or exposes truth to an agent."""

    def __init__(self) -> None:
        super().__init__("peer_network_bridge")
        self.declare_parameter("agents", ["rover_0", "rover_1", "drone_0", "drone_1"])
        self.declare_parameter("max_range", 18.0)
        self.declare_parameter("base_loss", 0.05)
        self.declare_parameter("distance_loss", 0.30)
        self.declare_parameter("wall_attenuation", 0.22)
        self.declare_parameter("delay_min", 0.10)
        self.declare_parameter("delay_max", 0.30)
        self.declare_parameter("seed", 42)
        self.declare_parameter("spawn_positions", [-16.0, -17.0, -14.0, -17.0, -16.0, -14.0, -13.5, -14.0])
        self.declare_parameter("wall_segments", [-8.0, -9.0, -8.0, 13.0, -4.0, 9.0, 14.0, 9.0, 7.0, -14.0, 7.0, 4.0, -7.5, -9.0, 5.5, -9.0, 7.5, 2.0, 18.5, 2.0])
        self.agents = [str(value) for value in self.get_parameter("agents").value]
        spawn = list(map(float, self.get_parameter("spawn_positions").value))
        self.offsets = {agent: (spawn[2 * index], spawn[2 * index + 1]) for index, agent in enumerate(self.agents)}
        self.max_range = float(self.get_parameter("max_range").value)
        self.rng = random.Random(int(self.get_parameter("seed").value))
        raw = list(map(float, self.get_parameter("wall_segments").value))
        self.walls = [((raw[i], raw[i + 1]), (raw[i + 2], raw[i + 3])) for i in range(0, len(raw) - 3, 4)]
        self.positions: dict[str, tuple[float, float]] = {}
        self.inbox_publishers = {agent: self.create_publisher(PeerMessageEnvelope, f"/{agent}/peer_inbox", 50) for agent in self.agents}
        self.input_subscriptions = []
        for agent in self.agents:
            self.input_subscriptions.append(self.create_subscription(PeerMessageEnvelope, f"/{agent}/peer_outbox", lambda msg, source=agent: self._route(source, msg), 50))
            self.input_subscriptions.append(self.create_subscription(Odometry, f"/{agent}/odom", lambda msg, source=agent: self._odom(source, msg), qos_profile_sensor_data))
        self.queue: list[tuple[int, int, str, PeerMessageEnvelope]] = []
        self.counter = 0
        self.metrics = {"attempted": 0, "delivered": 0, "dropped_range": 0, "dropped_loss": 0, "dropped_expired": 0}
        self.create_timer(0.02, self._deliver_due)
        self.create_timer(10.0, self._report)

    def _odom(self, agent: str, msg: Odometry) -> None:
        offset = self.offsets.get(agent, (0.0, 0.0))
        self.positions[agent] = (msg.pose.pose.position.x + offset[0], msg.pose.pose.position.y + offset[1])

    def _route(self, source: str, msg: PeerMessageEnvelope) -> None:
        source_position = self.positions.get(source)
        if source_position is None:
            return
        recipients = [msg.target_id] if msg.target_id else self.agents
        for target in recipients:
            if target == source or target not in self.inbox_publishers:
                continue
            self.metrics["attempted"] += 1
            target_position = self.positions.get(target)
            if target_position is None:
                self.metrics["dropped_range"] += 1
                continue
            distance = math.dist(source_position, target_position)
            if distance > self.max_range:
                self.metrics["dropped_range"] += 1
                continue
            wall_count = sum(_intersects(source_position, target_position, start, end) for start, end in self.walls)
            probability = float(self.get_parameter("base_loss").value)
            probability += float(self.get_parameter("distance_loss").value) * (distance / self.max_range) ** 2
            probability += wall_count * float(self.get_parameter("wall_attenuation").value)
            if self.rng.random() < min(0.98, probability):
                self.metrics["dropped_loss"] += 1
                continue
            delay = self.rng.uniform(float(self.get_parameter("delay_min").value), float(self.get_parameter("delay_max").value))
            due = self.get_clock().now().nanoseconds + int(delay * 1e9)
            self.counter += 1
            heapq.heappush(self.queue, (due, self.counter, target, msg))

    def _deliver_due(self) -> None:
        now = self.get_clock().now().nanoseconds
        while self.queue and self.queue[0][0] <= now:
            _, _, target, msg = heapq.heappop(self.queue)
            expiry = int(msg.expires_at.sec) * 1_000_000_000 + int(msg.expires_at.nanosec)
            if expiry and now > expiry:
                self.metrics["dropped_expired"] += 1
                continue
            self.inbox_publishers[target].publish(msg)
            self.metrics["delivered"] += 1

    def _report(self) -> None:
        self.get_logger().info("network " + " ".join(f"{key}={value}" for key, value in self.metrics.items()))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PeerNetworkBridge()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
