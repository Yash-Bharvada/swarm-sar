#!/usr/bin/env python3
"""Read-only, bounded smoke probe; writes genuine observations as JSON."""
import argparse
import json
import math
import time
from collections import defaultdict

import rclpy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan, Imu, Image, JointState
from std_msgs.msg import String
from rosgraph_msgs.msg import Clock
from tf2_msgs.msg import TFMessage
from rclpy.qos import qos_profile_sensor_data
from swarm_sar_interfaces.msg import AgentStatus, PeerMessageEnvelope


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", nargs="+", default=["rover_0", "drone_0"])
    parser.add_argument("--seconds", type=float, default=25)
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node("swarm_validation_probe")
    counts, details, positions, parents = defaultdict(int), {}, {}, defaultdict(set)
    motion, stages = {}, defaultdict(set)

    def receive(topic, msg):
        counts[topic] += 1
        if isinstance(msg, Odometry):
            p = msg.pose.pose.position
            value = [p.x, p.y, p.z]
            positions.setdefault(topic, {"first": value})["last"] = value
            q = msg.pose.pose.orientation
            tilt = math.acos(max(-1., min(1., 1-2*(q.x*q.x+q.y*q.y))))
            state = motion.setdefault(topic, {"min": value[:], "max": value[:], "max_tilt_rad": 0., "max_speed": 0.})
            state["min"] = [min(a, b) for a, b in zip(state["min"], value)]
            state["max"] = [max(a, b) for a, b in zip(state["max"], value)]
            state["max_tilt_rad"] = max(state["max_tilt_rad"], tilt)
            v = msg.twist.twist.linear
            state["max_speed"] = max(state["max_speed"], math.sqrt(v.x*v.x+v.y*v.y+v.z*v.z))
            details[topic] = {"frame": msg.header.frame_id, "child": msg.child_frame_id}
        elif isinstance(msg, LaserScan):
            valid = [v for v in msg.ranges if math.isfinite(v)]
            details[topic] = {"samples": len(msg.ranges), "finite": len(valid),
                              "minimum": min(valid) if valid else None, "frame": msg.header.frame_id}
        elif isinstance(msg, Clock):
            details[topic] = msg.clock.sec + msg.clock.nanosec * 1e-9
        elif isinstance(msg, TFMessage):
            for transform in msg.transforms:
                parents[transform.child_frame_id].add(transform.header.frame_id)
        elif isinstance(msg, Image):
            details[topic] = {"width": msg.width, "height": msg.height, "encoding": msg.encoding}
        elif isinstance(msg, JointState):
            details[topic] = {"names": list(msg.name), "velocity": list(msg.velocity)}
        elif isinstance(msg, String):
            stages[topic].add(msg.data)

    subs = []
    topics = [("/clock", Clock), ("/tf", TFMessage)]
    for agent in args.agents:
        topics += [(f"/{agent}/{suffix}", typ) for suffix, typ in
                   [("odom", Odometry), ("scan", LaserScan), ("imu/data", Imu),
                    ("status", AgentStatus), ("joint_states", JointState)]]
        topics.append((f"/{agent}/demo_stage", String))
        if len(args.agents) > 1:
            topics.append((f"/{agent}/peer_inbox", PeerMessageEnvelope))
        if agent.startswith("drone"):
            topics.append((f"/{agent}/downward_camera/image_raw", Image))
    for topic, typ in topics:
        subs.append(node.create_subscription(typ, topic, lambda msg, t=topic: receive(t, msg), qos_profile_sensor_data))
    started = time.monotonic()
    while time.monotonic() - started < args.seconds:
        rclpy.spin_once(node, timeout_sec=0.1)
    nodes = sorted(node.get_node_names_and_namespaces())
    result = {"wall_seconds": time.monotonic() - started, "nodes": nodes,
              "counts": dict(counts), "samples": details, "positions": positions,
              "motion": motion, "stages": {k: sorted(v) for k, v in stages.items()},
              "dynamic_tf_parents": {k: sorted(v) for k, v in parents.items()},
              "missing": [t for t, _ in topics if counts[t] == 0]}
    print(json.dumps(result, indent=2))
    node.destroy_node()
    rclpy.shutdown()
    raise SystemExit(1 if result["missing"] else 0)


if __name__ == "__main__":
    main()
