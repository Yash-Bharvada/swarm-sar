"""Independent frontier explorer using only local sensors and delivered peer data."""

from __future__ import annotations

from collections import deque
import hashlib
import json
import math
from typing import Iterable

import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from geometry_msgs.msg import Point, Twist
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from visualization_msgs.msg import Marker

from swarm_sar_interfaces.msg import AgentStatus, PeerMessageEnvelope, SurvivorEvidence


UNKNOWN, FREE, OCCUPIED = -1, 0, 100


def _yaw(q) -> float:
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def _wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def _bresenham(x0: int, y0: int, x1: int, y1: int) -> Iterable[tuple[int, int]]:
    dx, sx, dy, sy = abs(x1 - x0), (1 if x0 < x1 else -1), -abs(y1 - y0), (1 if y0 < y1 else -1)
    error = dx + dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            return
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


class DecentralizedAgent(Node):
    """A private-map controller; no truth map or centralized reservation is used."""

    def __init__(self) -> None:
        super().__init__("decentralized_agent")
        self.declare_parameter("agent_id", self.get_namespace().strip("/") or "rover_0")
        self.declare_parameter("robot_type", "rover")
        self.declare_parameter("map_resolution", 0.20)
        self.declare_parameter("map_size", 240)
        self.declare_parameter("control_rate", 10.0)
        self.declare_parameter("frontier_replan_seconds", 2.0)
        self.declare_parameter("goal_tolerance", 0.45)
        self.declare_parameter("safety_distance", 0.65)
        self.declare_parameter("cruise_speed", 0.65)
        self.declare_parameter("radio_broadcast_seconds", 1.0)
        self.declare_parameter("battery_seconds", 1200.0)
        self.declare_parameter("initial_x", 0.0)
        self.declare_parameter("initial_y", 0.0)
        self.declare_parameter("initial_z", 0.0)
        self.agent_id = str(self.get_parameter("agent_id").value)
        self.robot_type = str(self.get_parameter("robot_type").value)
        self.resolution = float(self.get_parameter("map_resolution").value)
        self.size = int(self.get_parameter("map_size").value)
        self.origin = -0.5 * self.size * self.resolution
        self.grid = np.full((self.size, self.size), UNKNOWN, dtype=np.int8)
        self.dirty_cells: set[tuple[int, int]] = set()
        self.pose: tuple[float, float, float] | None = None
        self.altitude = 0.0
        self.scan: LaserScan | None = None
        self.goal: tuple[float, float] | None = None
        self.peer_claims: dict[str, tuple[float, float]] = {}
        self.peer_seen_ns: dict[str, int] = {}
        self.sequence = 0
        self.started_ns = self.get_clock().now().nanoseconds
        self.last_plan_ns = 0
        self.confirmed: list[tuple[float, float]] = []

        self.cmd_pub = self.create_publisher(Twist, "cmd_vel", 10)
        self.map_pub = self.create_publisher(OccupancyGrid, "private_map", 1)
        self.outbox_pub = self.create_publisher(PeerMessageEnvelope, "peer_outbox", 20)
        self.status_pub = self.create_publisher(AgentStatus, "status", 10)
        self.marker_pub = self.create_publisher(Marker, "survivor_alert", 10)
        self.create_subscription(LaserScan, "scan", self._scan_callback, qos_profile_sensor_data)
        self.create_subscription(Odometry, "odom", self._odom_callback, qos_profile_sensor_data)
        self.create_subscription(SurvivorEvidence, "survivor_evidence", self._evidence_callback, 10)
        self.create_subscription(PeerMessageEnvelope, "peer_inbox", self._peer_callback, 50)
        rate = float(self.get_parameter("control_rate").value)
        self.create_timer(1.0 / rate, self._control)
        self.create_timer(float(self.get_parameter("radio_broadcast_seconds").value), self._broadcast)
        self.create_timer(1.0, self._publish_map)

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return int((x - self.origin) / self.resolution), int((y - self.origin) / self.resolution)

    def _world(self, x: int, y: int) -> tuple[float, float]:
        return self.origin + (x + 0.5) * self.resolution, self.origin + (y + 0.5) * self.resolution

    def _inside(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size

    def _set_cell(self, x: int, y: int, value: int) -> None:
        if self._inside(x, y) and int(self.grid[y, x]) != value:
            self.grid[y, x] = value
            self.dirty_cells.add((x, y))

    def _odom_callback(self, msg: Odometry) -> None:
        p = msg.pose.pose.position
        self.pose = (
            p.x + float(self.get_parameter("initial_x").value),
            p.y + float(self.get_parameter("initial_y").value),
            _yaw(msg.pose.pose.orientation),
        )
        self.altitude = p.z + float(self.get_parameter("initial_z").value)

    def _scan_callback(self, msg: LaserScan) -> None:
        self.scan = msg
        if self.pose is None:
            return
        px, py, heading = self.pose
        ox, oy = self._cell(px, py)
        stride = max(1, len(msg.ranges) // 360)
        for index in range(0, len(msg.ranges), stride):
            measured = float(msg.ranges[index])
            hit = math.isfinite(measured) and measured < msg.range_max
            distance = min(measured if hit else msg.range_max, 12.0)
            angle = heading + msg.angle_min + index * msg.angle_increment
            ex, ey = self._cell(px + distance * math.cos(angle), py + distance * math.sin(angle))
            ray = list(_bresenham(ox, oy, ex, ey))
            for cx, cy in ray[:-1] if hit else ray:
                self._set_cell(cx, cy, FREE)
            if hit and ray:
                self._set_cell(*ray[-1], OCCUPIED)

    def _frontier_clusters(self) -> list[list[tuple[int, int]]]:
        free = self.grid == FREE
        unknown = self.grid == UNKNOWN
        adjacent_unknown = np.zeros_like(free)
        adjacent_unknown[1:, :] |= unknown[:-1, :]
        adjacent_unknown[:-1, :] |= unknown[1:, :]
        adjacent_unknown[:, 1:] |= unknown[:, :-1]
        adjacent_unknown[:, :-1] |= unknown[:, 1:]
        mask = free & adjacent_unknown
        seen: set[tuple[int, int]] = set()
        clusters = []
        for y, x in np.argwhere(mask):
            seed = (int(x), int(y))
            if seed in seen:
                continue
            queue, cluster = deque([seed]), []
            seen.add(seed)
            while queue:
                current = queue.popleft()
                cluster.append(current)
                cx, cy = current
                for neighbor in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    nx, ny = neighbor
                    if self._inside(nx, ny) and mask[ny, nx] and neighbor not in seen:
                        seen.add(neighbor)
                        queue.append(neighbor)
            if len(cluster) >= 3:
                clusters.append(cluster)
        return clusters

    def _choose_goal(self) -> None:
        if self.pose is None:
            return
        now = self.get_clock().now().nanoseconds
        active_peers = sorted(name for name, stamp in self.peer_seen_ns.items() if now - stamp < 8_000_000_000)
        participants = tuple(sorted(active_peers + [self.agent_id]))
        choices = []
        for cluster in self._frontier_clusters():
            cx = round(sum(p[0] for p in cluster) / len(cluster))
            cy = round(sum(p[1] for p in cluster) / len(cluster))
            nearest = min(cluster, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
            wx, wy = self._world(*nearest)
            if any(math.hypot(wx - px, wy - py) < 1.2 for px, py in self.peer_claims.values()):
                continue
            key = f"{nearest[0] // 8}:{nearest[1] // 8}"
            owner = max(participants, key=lambda name: hashlib.blake2s(f"{key}:{name}".encode(), digest_size=8).digest())
            distance = math.hypot(wx - self.pose[0], wy - self.pose[1])
            choices.append((owner != self.agent_id, distance - 0.03 * len(cluster), -len(cluster), wx, wy))
        self.goal = None if not choices else tuple(sorted(choices)[0][-2:])

    def _control(self) -> None:
        command = Twist()
        if self.robot_type == "drone" and self.pose is not None:
            command.linear.z = max(-0.5, min(0.5, 0.8 * (2.5 - self.altitude)))
        if self.pose is None or self.scan is None:
            self.cmd_pub.publish(command)
            return
        now = self.get_clock().now().nanoseconds
        replan_ns = int(float(self.get_parameter("frontier_replan_seconds").value) * 1e9)
        tolerance = float(self.get_parameter("goal_tolerance").value)
        if self.goal is None or math.hypot(self.goal[0] - self.pose[0], self.goal[1] - self.pose[1]) < tolerance or now - self.last_plan_ns >= replan_ns:
            self._choose_goal()
            self.last_plan_ns = now
        if self.goal is None:
            self.cmd_pub.publish(command)
            return
        desired = math.atan2(self.goal[1] - self.pose[1], self.goal[0] - self.pose[0])
        error = _wrap(desired - self.pose[2])
        ranges = np.asarray(self.scan.ranges, dtype=float)
        ranges[~np.isfinite(ranges)] = self.scan.range_max
        angles = self.scan.angle_min + np.arange(len(ranges)) * self.scan.angle_increment
        front = ranges[np.abs(angles) < 0.52]
        left = ranges[(angles >= 0.15) & (angles < 1.4)]
        right = ranges[(angles <= -0.15) & (angles > -1.4)]
        safety = float(self.get_parameter("safety_distance").value)
        blocked = front.size and float(np.min(front)) < safety
        if blocked:
            command.linear.x = 0.0
            command.angular.z = 0.9 if (left.size and right.size and np.mean(left) >= np.mean(right)) else -0.9
        else:
            command.angular.z = max(-1.0, min(1.0, 1.8 * error))
            command.linear.x = float(self.get_parameter("cruise_speed").value) * max(0.0, 1.0 - abs(error) / 1.2)
        if self.robot_type == "drone":
            command.linear.z = max(-0.5, min(0.5, 0.8 * (2.5 - self.altitude)))
        self.cmd_pub.publish(command)

    def _evidence_callback(self, msg: SurvivorEvidence) -> None:
        if not msg.confirmed and not (msg.thermal_confidence >= 0.62 and msg.acoustic_confidence >= 0.28):
            return
        p = msg.estimated_pose.pose.position
        if any(math.hypot(p.x - x, p.y - y) < 1.0 for x, y in self.confirmed):
            return
        self.confirmed.append((p.x, p.y))
        marker = Marker()
        marker.header = msg.header
        marker.ns, marker.id, marker.type, marker.action = "survivor_alerts", len(self.confirmed), Marker.SPHERE, Marker.ADD
        marker.pose = msg.estimated_pose.pose
        marker.scale.x = marker.scale.y = marker.scale.z = 0.8
        marker.color.r, marker.color.g, marker.color.a = 0.0, 1.0, 1.0
        self.marker_pub.publish(marker)
        self._publish_envelope("survivor_evidence", {"position": [p.x, p.y], "thermal": float(msg.thermal_confidence), "acoustic": float(msg.acoustic_confidence), "confirmed": True})

    def _peer_callback(self, msg: PeerMessageEnvelope) -> None:
        if msg.sender_id == self.agent_id:
            return
        self.peer_seen_ns[msg.sender_id] = self.get_clock().now().nanoseconds
        try:
            payload = json.loads(msg.payload_json)
        except (TypeError, ValueError):
            return
        claim = payload.get("claim")
        if isinstance(claim, list) and len(claim) == 2:
            self.peer_claims[msg.sender_id] = (float(claim[0]), float(claim[1]))
        for cell in payload.get("map_delta", []):
            if isinstance(cell, list) and len(cell) == 3:
                x, y, value = map(int, cell)
                if self._inside(x, y) and value in (FREE, OCCUPIED) and self.grid[y, x] == UNKNOWN:
                    self.grid[y, x] = value
        if msg.kind == "survivor_evidence":
            position = payload.get("position")
            if isinstance(position, list) and len(position) == 2 and bool(payload.get("confirmed")):
                self.confirmed.append((float(position[0]), float(position[1])))

    def _publish_envelope(self, kind: str, payload: dict) -> None:
        msg = PeerMessageEnvelope()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "map"
        msg.sender_id, msg.sequence, msg.kind = self.agent_id, self.sequence, kind
        msg.target_id = ""
        msg.expires_at = (self.get_clock().now() + Duration(seconds=8.0)).to_msg()
        if self.pose:
            msg.sender_pose.pose.position.x, msg.sender_pose.pose.position.y = self.pose[:2]
            msg.sender_pose.pose.orientation.w = 1.0
        msg.payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        self.sequence += 1
        self.outbox_pub.publish(msg)

    def _broadcast(self) -> None:
        delta = [[x, y, int(self.grid[y, x])] for x, y in sorted(self.dirty_cells)[:600]]
        for x, y, _ in delta:
            self.dirty_cells.discard((x, y))
        self._publish_envelope("state_delta", {"claim": list(self.goal) if self.goal else None, "map_delta": delta, "survivors": self.confirmed[-8:]})
        status = AgentStatus()
        status.header.stamp, status.header.frame_id = self.get_clock().now().to_msg(), "map"
        status.agent_id, status.robot_type = self.agent_id, self.robot_type
        elapsed = (self.get_clock().now().nanoseconds - self.started_ns) / 1e9
        status.battery_fraction = max(0.0, 1.0 - elapsed / float(self.get_parameter("battery_seconds").value))
        status.health_fraction = 1.0
        status.has_claim = self.goal is not None
        if self.goal:
            status.claimed_frontier = Point(x=self.goal[0], y=self.goal[1], z=0.0)
        self.status_pub.publish(status)

    def _publish_map(self) -> None:
        msg = OccupancyGrid()
        msg.header.stamp, msg.header.frame_id = self.get_clock().now().to_msg(), "map"
        msg.info.resolution, msg.info.width, msg.info.height = self.resolution, self.size, self.size
        msg.info.origin.position.x = msg.info.origin.position.y = self.origin
        msg.info.origin.orientation.w = 1.0
        msg.data = self.grid.reshape(-1).astype(int).tolist()
        self.map_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DecentralizedAgent()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
