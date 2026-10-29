"""Grayscale live RViz map and confirmed survivor dots; no world truth overlay."""

import math
import time

import numpy as np
import rclpy
from geometry_msgs.msg import Point
from nav_msgs.msg import OccupancyGrid, Odometry
from std_msgs.msg import ColorRGBA
from rosgraph_msgs.msg import Clock
from swarm_sar_interfaces.msg import SurvivorEvidence
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from visualization_msgs.msg import Marker, MarkerArray


def label(text, x, y, z, namespace, marker_id, color):
    marker = Marker()
    marker.header.frame_id = "map"
    marker.ns, marker.id = namespace, marker_id
    marker.type = Marker.TEXT_VIEW_FACING
    marker.pose.orientation.w = 1.0
    marker.pose.position.x, marker.pose.position.y, marker.pose.position.z = float(x), float(y), float(z)
    marker.scale.z = 0.65
    marker.color.r, marker.color.g, marker.color.b, marker.color.a = color
    marker.text = text
    return marker


def map_tiles(grid):
    """Render measured occupancy cells without RViz's failing indexed-map shader."""
    marker = Marker()
    marker.header.frame_id = grid.header.frame_id
    marker.ns = "measured_map"
    marker.type = Marker.TRIANGLE_LIST
    marker.pose = grid.info.origin
    marker.scale.x = marker.scale.y = marker.scale.z = 1.0
    marker.color.a = 1.0
    width, height = grid.info.width, grid.info.height
    if width <= 0 or height <= 0 or grid.info.resolution <= 0 or len(grid.data) != width*height:
        marker.action = Marker.DELETE
        return MarkerArray(markers=[marker])
    # Merge equal horizontal cells into flat rectangles. This preserves every
    # measured cell while avoiding tens of thousands of 3D cubes on the VM.
    rows = np.asarray(grid.data).reshape(height, width)
    resolution = grid.info.resolution
    for y, row in enumerate(rows):
        edges = np.r_[0, np.flatnonzero(row[1:] != row[:-1])+1, width]
        for start, end in zip(edges[:-1], edges[1:]):
            value = int(row[start])
            if value < 0:
                continue  # Unknown remains dark; never present it as free.
            shade = 0.88 - 0.70 * min(value, 100) / 100
            x0, x1, y0, y1 = start*resolution, end*resolution, y*resolution, (y+1)*resolution
            for x, yy in ((x0,y0),(x1,y0),(x1,y1),(x0,y0),(x1,y1),(x0,y1)):
                marker.points.append(Point(x=float(x), y=float(yy), z=-0.02))
                marker.colors.append(ColorRGBA(r=shade, g=shade, b=shade, a=1.0))
    if not marker.points:
        marker.action = Marker.DELETE
    return MarkerArray(markers=[marker])


class SurvivorDetections:
    """Accumulate confirmed observations, never world-file survivor positions."""
    def __init__(self):
        self.markers = MarkerArray()

    def observe(self, msg):
        if not msg.confirmed and not (msg.thermal_confidence >= 0.62 and msg.acoustic_confidence >= 0.28):
            return False
        p = msg.estimated_pose.pose.position
        if msg.header.frame_id != "map" or not all(math.isfinite(v) for v in (p.x, p.y)):
            return False
        if any(math.hypot(p.x-m.pose.position.x, p.y-m.pose.position.y) < 1.0 for m in self.markers.markers):
            return False
        marker = Marker()
        marker.header.frame_id = "map"
        marker.ns, marker.id = "confirmed_survivors", len(self.markers.markers)
        marker.type = Marker.SPHERE
        marker.pose.orientation.w = 1.0
        marker.pose.position.x, marker.pose.position.y, marker.pose.position.z = p.x, p.y, 0.12
        marker.scale.x = marker.scale.y = 0.65
        marker.scale.z = 0.18
        marker.color.g = marker.color.a = 1.0
        self.markers.markers.append(marker)
        return True


class DisasterScene(Node):
    def __init__(self):
        super().__init__("disaster_scene")
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.detections = SurvivorDetections()
        self.detection_pub = self.create_publisher(MarkerArray, "/detected_survivors", qos)
        self.evidence_subscriptions = [self.create_subscription(
            SurvivorEvidence, f"/{name}/survivor_evidence", self.receive_evidence, 10)
            for name in ("rover_0", "rover_1", "drone_0", "drone_1")]
        self.last_sim_time = None
        self.clock_subscription = self.create_subscription(Clock, "/clock", self.receive_clock, qos_profile_sensor_data)
        self.vehicle_pub = self.create_publisher(MarkerArray, "/demo_vehicle_markers", 1)
        self.map_pub = self.create_publisher(MarkerArray, "/demo_map_tiles", qos)
        self.latest_map = None
        self.map_subscription = self.create_subscription(OccupancyGrid, "/rover_0/private_map", self.receive_map, 1)
        self.map_timer = self.create_timer(1.0, self.publish_map)
        self.poses = {}
        self.colors = {name: (.55, .55, .55, 1.) for name in ("rover_0", "drone_0", "drone_1")}
        self.subscriptions_ = [self.create_subscription(
            Odometry, f"/{name}/odom", lambda msg, robot=name: self.poses.update({robot: (msg, time.monotonic())}),
            qos_profile_sensor_data) for name in self.colors]
        self.vehicle_timer = self.create_timer(0.1, self.publish_vehicles)
        # Republishing also supports RViz when a display is toggled or reopened.
        self.timer = self.create_timer(2.0, self.publish_detections)
        self.publish_detections()
        self.get_logger().info("Grayscale live map; green dots only for confirmed survivor observations")

    def publish_detections(self):
        clear = Marker()
        clear.action = Marker.DELETEALL
        self.detection_pub.publish(MarkerArray(markers=[clear, *self.detections.markers.markers]))

    def receive_evidence(self, msg):
        if self.detections.observe(msg):
            self.publish_detections()

    def receive_clock(self, msg):
        now = msg.clock.sec * 1_000_000_000 + msg.clock.nanosec
        if self.last_sim_time is not None and now < self.last_sim_time:
            self.detections = SurvivorDetections()
            self.poses.clear()
            self.publish_detections()
        self.last_sim_time = now

    def receive_map(self, msg):
        self.latest_map = msg

    def publish_map(self):
        if self.latest_map is not None:
            self.map_pub.publish(map_tiles(self.latest_map))
            self.latest_map = None

    def publish_vehicles(self):
        markers = MarkerArray()
        for name, (odom, received) in self.poses.items():
            if time.monotonic() - received > 2.0:
                continue
            # Vehicle orientation is drawn by native RViz TF axes, not arrows.
            p = odom.pose.pose.position
            text = label(name, p.x, p.y, p.z+1.0, name, 1, self.colors[name])
            text.header.frame_id = odom.header.frame_id
            text.lifetime.sec = 2
            markers.markers.append(text)
        self.vehicle_pub.publish(markers)


def main():
    rclpy.init()
    node = DisasterScene()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
