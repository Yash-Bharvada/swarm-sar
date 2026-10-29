"""Wait for running simulation sensors before starting a second graphics app."""
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import LaserScan


def main():
    rclpy.init()
    node = rclpy.create_node("wait_for_simulation")
    node.declare_parameter("scan_topic", "/rover_0/scan")
    node.declare_parameter("timeout_seconds", 120.0)
    scan_topic = node.get_parameter("scan_topic").value
    deadline = time.monotonic() + float(node.get_parameter("timeout_seconds").value)
    state = {"scan": False, "seconds": 0}
    subscriptions = [
        node.create_subscription(LaserScan, scan_topic, lambda msg: state.update(scan=bool(msg.ranges)), qos_profile_sensor_data),
        node.create_subscription(Clock, "/clock", lambda msg: state.update(seconds=msg.clock.sec), qos_profile_sensor_data),
    ]
    node.get_logger().info("Waiting for Gazebo sensors before opening RViz")
    ready_at = None
    success = False
    try:
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.2)
            if state["scan"] and state["seconds"] >= 2:
                if ready_at is None:
                    ready_at = time.monotonic()
                if time.monotonic()-ready_at >= 5:
                    success = True
                    node.get_logger().info("Gazebo is running; opening RViz")
                    break
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    if not success:
        raise SystemExit(1)
