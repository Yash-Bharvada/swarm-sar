# Physics demo validation evidence

These are real observations from ROS 2 Lyrical / Gazebo Sim 10.5.0 on
28 October 2026. They are not generated example outputs.

- first-flight.json: rotor flight succeeded; rover wheel-odometry drift led
  to an obstacle stop. This run was superseded.
- corrected-flight.json: world-pose feedback and rectangular rover route.
  All four stages appeared, but a later turn still overshot; not the final result.
- final-motion.json: final 16-waypoint curved route and longitudinal/lateral
  tire friction settings; both drones use motor-thrust physics.
- entities.txt: world listing for the three-vehicle demo: rover_0, drone_0, drone_1.
- tests.txt: seven static/expanded-model tests and five controller helper tests.
- build.txt: all four workspace packages built.
- steady-motion.json: settled motion sample, excluding the spawn interval.
- rover-controller.log: two complete 16-waypoint circuits and continuation.

The final 130-second sample covered rover X [-4.066, 2.065] m and
Y [-17.065, -10.932] m, with footprint Z within 0.000001 m of zero.
Drone 0 and drone 1 reached their 3.5 m and 4.5 m targets and all flight
waypoints; maximum sampled body tilt was under 0.067 rad (3.84 degrees).
Their observed horizontal envelopes remained separated.
No requested streams were missing. Initial odometry twist values spiked at
spawn (up to thousands of m/s); those raw readings are retained rather than
hidden. They are not a valid estimate of steady physical speed.

The runtime probe reports actual message counts, pose extrema, tilt, joint
velocities and observed controller stages. A missing-stream check alone does
not prove safe motion; examine the pose ranges and stages as well.
Gazebo rotor joint speeds are displayed with the model's 10x rotor-visualization
slowdown; do not equate the displayed joint speed with physical motor speed.

Camera checks: Gazebo accepted top, side and overview pose service calls
(data: true); follow commands were delivered through /gui/track.
The separately launched demo_sensor_views node subscribes to actual ROS scans
and poses. Native screenshot capture remains unavailable; no screenshot is
claimed here.

Known runtime limitation: during intermediate shutdown, ros_gz_bridge exited
with signal -11. Control nodes exited cleanly and the next simulation launched.
Do not describe shutdown as entirely error-free.

The radar-style map is an odometry presentation, not a simulated RF radar.
Physics constants are not calibrated to a specific real vehicle.
