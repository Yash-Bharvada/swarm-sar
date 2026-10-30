"""Range-, wall-, loss-, delay-, and expiry-aware peer message transport."""

from __future__ import annotations

import heapq
import math
import random

import rclpy
from rclpy.executors import ExternalShutdownException
from nav_msgs.msg import Odometry
from std_msgs.msg import String
from std_srvs.srv import SetBool
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from swarm_sar_interfaces.msg import PeerMessageEnvelope
from swarm_sar_control.slam_support import RadioBudget, slim_json


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
        self.declare_parameter("channels", ["peer"])
        self.declare_parameter("truth_odom_topics", [""])
        self.declare_parameter("bytes_per_second", 0.0)
        self.declare_parameter("max_queue", 2000)
        self.declare_parameter("spawn_positions", [-16.0, -17.0, -14.0, -17.0, -16.0, -14.0, -13.5, -14.0])
        self.declare_parameter("wall_segments", [-8.0, -9.0, -8.0, 13.0, -4.0, 9.0, 14.0, 9.0, 7.0, -14.0, 7.0, 4.0, -7.5, -9.0, 5.5, -9.0, 7.5, 2.0, 18.5, 2.0])
        self.agents = [str(value) for value in self.get_parameter("agents").value]
        spawn = list(map(float, self.get_parameter("spawn_positions").value))
        self.offsets = {agent: (spawn[2 * index], spawn[2 * index + 1]) for index, agent in enumerate(self.agents)}
        self.max_range = float(self.get_parameter("max_range").value)
        if not math.isfinite(self.max_range) or self.max_range <= 0:
            raise ValueError("max_range must be finite and positive")
        self.rng = random.Random(int(self.get_parameter("seed").value))
        raw = list(map(float, self.get_parameter("wall_segments").value))
        self.walls = [((raw[i], raw[i + 1]), (raw[i + 2], raw[i + 3])) for i in range(0, len(raw) - 3, 4)]
        self.positions: dict[str, tuple[float, float]] = {}
        self.channels = list(self.get_parameter("channels").value)
        self.inbox_publishers = {(channel, agent): self.create_publisher(PeerMessageEnvelope, f"/{agent}/{channel}_inbox", 50) for channel in self.channels for agent in self.agents}
        self.isolated = set()
        self.budget = RadioBudget(float(self.get_parameter("bytes_per_second").value))
        self.event_pub = self.create_publisher(String, "/swarm/network/events", 100)
        self.stats_pub = self.create_publisher(String, "/swarm/network/stats", 1)
        self.last_now = 0
        self.reset_required = False
        truth_topics = list(self.get_parameter("truth_odom_topics").value)
        if truth_topics != [""] and len(truth_topics) != len(self.agents):
            raise ValueError("truth_odom_topics must match agents")
        self.input_subscriptions = []
        self.services = []
        for index, agent in enumerate(self.agents):
            for channel in self.channels:
                self.input_subscriptions.append(self.create_subscription(PeerMessageEnvelope, f"/{agent}/{channel}_outbox", lambda msg, source=agent, ch=channel: self._route(source, msg, ch), 50))
            topic = f"/{agent}/odom" if truth_topics == [""] else truth_topics[index]
            self.input_subscriptions.append(self.create_subscription(Odometry, topic, lambda msg, source=agent: self._odom(source, msg), qos_profile_sensor_data))
            self.services.append(self.create_service(SetBool, f"/swarm/network/isolate/{agent}", lambda req, res, source=agent: self._isolate(source, req, res)))
        self.queue = []
        self.counter = 0
        self.metrics = {key: 0 for key in ("attempted", "delivered", "dropped_range", "dropped_loss", "dropped_expired", "dropped_isolated", "dropped_budget", "dropped_queue", "dropped_identity", "dropped_pose", "bytes_sent")}
        self.create_timer(0.02, self._deliver_due)
        self.create_timer(10.0, self._report)
        self.create_timer(1.0, self._stats)

    def _event(self, event, source, target, msg, channel, **extra):
        self.event_pub.publish(String(data=slim_json(dict(event=event, source=source, target=target,
            sequence=int(msg.sequence), channel=channel, sim_time=self.get_clock().now().nanoseconds/1e9, **extra))))

    def _isolate(self, source, request, response):
        if request.data: self.isolated.add(source)
        else: self.isolated.discard(source)
        response.success = True
        response.message = f"{source} isolated={request.data}; queued traffic is rechecked on delivery"
        self._stats()
        return response

    def _stats(self):
        self.stats_pub.publish(String(data=slim_json(dict(sim_time=self.get_clock().now().nanoseconds/1e9,
            metrics=self.metrics, isolated=sorted(self.isolated), queue=len(self.queue),
            reset_required=self.reset_required, max_range=self.max_range,
            bytes_per_second=self.budget.rate, positions=self.positions))))

    def _odom(self, agent: str, msg: Odometry) -> None:
        offset = self.offsets.get(agent, (0.0, 0.0))
        self.positions[agent] = (msg.pose.pose.position.x + offset[0], msg.pose.pose.position.y + offset[1])

    def _route(self, source: str, msg: PeerMessageEnvelope, channel="peer") -> None:
        if self.reset_required: return
        if msg.sender_id != source:
            self.metrics["dropped_identity"] += 1
            self._event("dropped_identity", source, msg.target_id, msg, channel)
            return
        source_position = self.positions.get(source)
        if source_position is None:
            self.metrics["dropped_pose"] += 1
            self._event("dropped_pose", source, msg.target_id, msg, channel)
            return
        recipients = [msg.target_id] if msg.target_id else self.agents
        # One broadcast transmission consumes the sender budget once, not per receiver.
        size = len(msg.payload_json.encode("utf-8")) + 256
        if not self.budget.take(source, size, self.get_clock().now().nanoseconds/1e9):
            self.metrics["dropped_budget"] += 1
            self._event("dropped_budget", source, msg.target_id, msg, channel, bytes=size)
            return
        self.metrics["bytes_sent"] += size
        for target in recipients:
            if target == source or (channel, target) not in self.inbox_publishers:
                continue
            self.metrics["attempted"] += 1
            if source in self.isolated or target in self.isolated:
                self.metrics["dropped_isolated"] += 1
                self._event("dropped_isolated", source, target, msg, channel)
                continue
            target_position = self.positions.get(target)
            if target_position is None:
                self.metrics["dropped_range"] += 1
                self._event("dropped_range", source, target, msg, channel)
                continue
            distance = math.dist(source_position, target_position)
            if distance > self.max_range:
                self.metrics["dropped_range"] += 1
                self._event("dropped_range", source, target, msg, channel)
                continue
            wall_count = sum(_intersects(source_position, target_position, start, end) for start, end in self.walls)
            probability = float(self.get_parameter("base_loss").value)
            probability += float(self.get_parameter("distance_loss").value) * (distance / self.max_range) ** 2
            probability += wall_count * float(self.get_parameter("wall_attenuation").value)
            if self.rng.random() < min(0.98, probability):
                self.metrics["dropped_loss"] += 1
                self._event("dropped_loss", source, target, msg, channel)
                continue
            if len(self.queue) >= int(self.get_parameter("max_queue").value):
                self.metrics["dropped_queue"] += 1
                self._event("dropped_queue", source, target, msg, channel)
                continue
            delay = self.rng.uniform(float(self.get_parameter("delay_min").value), float(self.get_parameter("delay_max").value))
            due = self.get_clock().now().nanoseconds + int(delay * 1e9)
            self.counter += 1
            heapq.heappush(self.queue, (due, self.counter, target, msg, channel, source))
            self._event("queued", source, target, msg, channel, bytes=size)

    def _deliver_due(self) -> None:
        now = self.get_clock().now().nanoseconds
        if now < self.last_now:
            self.queue.clear(); self.positions.clear(); self.reset_required = True
        self.last_now = now
        while self.queue and self.queue[0][0] <= now:
            _, _, target, msg, channel, source = heapq.heappop(self.queue)
            if source in self.isolated or target in self.isolated:
                self.metrics["dropped_isolated"] += 1
                self._event("dropped_isolated", source, target, msg, channel)
                continue
            expiry = int(msg.expires_at.sec) * 1_000_000_000 + int(msg.expires_at.nanosec)
            if expiry and now >= expiry:
                self.metrics["dropped_expired"] += 1
                self._event("dropped_expired", source, target, msg, channel)
                continue
            self.inbox_publishers[(channel, target)].publish(msg)
            self.metrics["delivered"] += 1
            self._event("transport_delivered", source, target, msg, channel)

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
