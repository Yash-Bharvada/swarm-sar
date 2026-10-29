#!/usr/bin/env python3
"""Observe real survivor evidence and corresponding RViz dots; publish nothing."""
import argparse
import json
import math
import time

import rclpy
from rclpy.qos import DurabilityPolicy, QoSProfile
from swarm_sar_interfaces.msg import SurvivorEvidence
from visualization_msgs.msg import Marker, MarkerArray


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=300)
    args = parser.parse_args()
    rclpy.init()
    node = rclpy.create_node("encounter_validation_probe")
    confirmations, dots = {}, []
    agents = ("rover_0", "drone_0", "drone_1")

    def evidence(msg):
        if msg.confirmed and msg.source_id not in confirmations:
            p = msg.estimated_pose.pose.position
            confirmations[msg.source_id] = {
                "simulation_seconds": msg.header.stamp.sec+msg.header.stamp.nanosec/1e9,
                "position": [p.x, p.y],
                "thermal": msg.thermal_confidence,
                "acoustic": msg.acoustic_confidence,
            }
            print("Confirmed", msg.source_id, json.dumps(confirmations[msg.source_id]), flush=True)

    def markers(msg):
        dots[:] = [[m.pose.position.x, m.pose.position.y] for m in msg.markers
                   if m.action == Marker.ADD and (m.color.r, m.color.g, m.color.b) == (0., 1., 0.)]

    def complete():
        return all(agent in confirmations and any(
            math.dist(confirmations[agent]["position"], point) < 1.0 for point in dots)
            for agent in agents)

    subscriptions = [node.create_subscription(SurvivorEvidence, f"/{agent}/survivor_evidence", evidence, 10)
                     for agent in agents]
    subscriptions.append(node.create_subscription(
        MarkerArray, "/detected_survivors", markers,
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)))
    start = progress = time.monotonic()
    try:
        while time.monotonic()-start < args.seconds and not complete():
            rclpy.spin_once(node, timeout_sec=.2)
            if time.monotonic()-progress >= 20:
                print("Waiting:", [agent for agent in agents if agent not in confirmations],
                      "green dots:", len(dots), flush=True)
                progress = time.monotonic()
        result = {"confirmed_by_agent": confirmations, "green_dots": dots, "passed": complete()}
        print(json.dumps(result, indent=2), flush=True)
        if not result["passed"]:
            raise SystemExit("Not all agents produced a confirmed encounter with a matching green dot")
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
