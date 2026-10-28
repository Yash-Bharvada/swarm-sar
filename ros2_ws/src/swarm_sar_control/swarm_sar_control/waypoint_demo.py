"""Bounded, repeatable waypoint demonstration using physical vehicle controllers."""
import math
import rclpy
from geometry_msgs.msg import Twist
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import String
from .decentralized_agent import DecentralizedAgent, _wrap


def slew(value, target, step):
    return value + max(-step, min(step, target - value))


class WaypointDemo(DecentralizedAgent):
    def __init__(self):
        super().__init__()
        routes = {
            "rover_0": [(-1+3*math.cos(-math.pi/2+i*math.pi/8),
                         -14+3*math.sin(-math.pi/2+i*math.pi/8)) for i in range(16)],
            "rover_1": [(-15., -6.), (-12., -6.), (-12., 3.), (-15., 3.)],
            "drone_0": [(-5., -5.), (-2., -5.), (-2., -2.), (-5., -2.)],
            "drone_1": [(1., -6.), (4., -6.), (4., -3.), (1., -3.)],
        }
        self.route = routes[self.agent_id]
        self.target_height = 3.5 if self.agent_id == "drone_0" else 4.5
        self.index = 0
        self.last_command = Twist()
        self.last_odom_ns = None
        self.last_scan_ns = None
        self.hover_started = None
        self.stage_pub = self.create_publisher(String, "demo_stage", 10)
        self.stage = ""

    def _odom_callback(self, msg):
        super()._odom_callback(msg)
        self.last_odom_ns = self.get_clock().now().nanoseconds

    def _scan_callback(self, msg):
        super()._scan_callback(msg)
        self.last_scan_ns = self.get_clock().now().nanoseconds

    def _stage(self, value):
        if value != self.stage:
            self.stage = value
            self.get_logger().info(value)
        self.stage_pub.publish(String(data=value))

    def _control(self):
        now = self.get_clock().now().nanoseconds
        target = Twist()
        if self.pose is None or self.last_odom_ns is None or now - self.last_odom_ns > 1_000_000_000:
            self.cmd_pub.publish(target)
            self.last_command = target
            self._stage("WAITING_FOR_ODOMETRY")
            return
        x, y, yaw = self.pose
        gx, gy = self.route[self.index]
        self.goal = gx, gy
        dx, dy = gx-x, gy-y
        distance = math.hypot(dx, dy)
        if self.robot_type == "drone":
            target.linear.z = max(-0.6, min(0.6, 0.8*(self.target_height-self.altitude)))
            if self.hover_started is None:
                # Hold launch XY while climbing; dwell at height before flying.
                dx, dy = self.route[0][0]-x, self.route[0][1]-y
                self._stage("TAKEOFF")
                if abs(self.altitude-self.target_height) < 0.15:
                    self.hover_started = now
            elif now-self.hover_started < 3_000_000_000:
                self._stage("HOVER")
            else:
                self._stage(f"WAYPOINT_{self.index}")
                if distance < 0.35:
                    self.index = (self.index+1) % len(self.route)
                heading = math.atan2(dy, dx)
                target.angular.z = max(-0.3, min(0.3, _wrap(heading-yaw)*0.5))
            # World position error converted to body-frame velocity.
            vx, vy = 0.65*dx, 0.65*dy
            scale = min(1., 0.8/max(math.hypot(vx, vy), 1e-6))
            target.linear.x = scale*(math.cos(yaw)*vx+math.sin(yaw)*vy)
            target.linear.y = scale*(-math.sin(yaw)*vx+math.cos(yaw)*vy)
        else:
            if self.last_scan_ns is None or now-self.last_scan_ns > 2_000_000_000:
                self.cmd_pub.publish(Twist())
                self.last_command = Twist()
                self._stage("WAITING_FOR_SCAN")
                return
            if distance < 0.65:
                self.index = (self.index+1) % len(self.route)
            error = _wrap(math.atan2(dy, dx)-yaw)
            target.linear.x = 0.45*max(0.3, math.cos(error))
            # Pure-pursuit curvature with a minimum moving turn radius of 0.8 m.
            curvature = max(-1.25, min(1.25, 2*math.sin(error)/max(min(distance, 1.2), 0.8)))
            target.angular.z = target.linear.x*curvature
            front = [r for i, r in enumerate(self.scan.ranges)
                     if abs(self.scan.angle_min+i*self.scan.angle_increment) < 0.4 and math.isfinite(r)]
            if front and min(front) < 0.8:
                target = Twist()
                self._stage("OBSTACLE_STOP")
            else:
                self._stage(f"WAYPOINT_{self.index}")
        dt = 1/float(self.get_parameter("control_rate").value)
        for axis in ("x", "y", "z"):
            setattr(self.last_command.linear, axis, slew(getattr(self.last_command.linear, axis), getattr(target.linear, axis), 0.5*dt))
        self.last_command.angular.z = slew(self.last_command.angular.z, target.angular.z, 0.5*dt)
        self.cmd_pub.publish(self.last_command)


def main(args=None):
    rclpy.init(args=args)
    node = WaypointDemo()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
