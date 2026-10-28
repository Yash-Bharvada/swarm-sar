# Two-drone and rover physics demo

Validated on the installed Lyrical / Gazebo 10.5.0 host: exactly two drones and
one rover; final 130-second wall-time sample received every requested stream.
The rover completed repeated curved-route waypoints without an obstacle stop;
its measured footprint remained at ground level. Both drones progressed through
takeoff, hover and all four flight waypoints. See evidence/physics-demo.

## Launch from a new terminal

Close any earlier simulation first. Start only one world at a time.

```bash
cd /home/yash/Desktop/swarm-sar/ros2_ws
source /opt/ros/lyrical/setup.bash
colcon build --symlink-install
source install/setup.bash
LIBGL_ALWAYS_SOFTWARE=1 ros2 launch swarm_sar_gazebo swarm_sar_sim.launch.py
```

The demo contains exactly **drone_0, drone_1 and rover_0**. The drones take off,
hover for three simulated seconds, then repeat separate waypoint circuits at
3.5 m and 4.5 m. The rover repeatedly follows its ground route. A slow VM takes
longer than wall-clock seconds to complete these stages.

The original diagnostic scenarios remain available, but only the demo profile
is the validated three-vehicle presentation. Do not select the older pair/drone
profiles if the demonstration must contain exactly two drones.

## Cameras and live sensor views

The command above now opens Gazebo and the original RViz map concurrently.
RViz shows the live rover occupancy map, LiDAR returns and labeled moving
vehicle arrows in grayscale. There are no preset survivor locations or colored
world-obstacle overlays. **Detected Survivors - green dots** adds a green dot
only when a rover or drone reports confirmed survivor evidence (or meets the
existing thermal >= 0.62 and acoustic >= 0.28 confirmation thresholds).
Dots use estimated detection positions, merge observations within one metre,
remain visible during the view session and clear when simulation time resets.
Before a confirmed encounter there are no green dots. Existing demo routes
do not guarantee a close encounter with every survivor.
The vehicle physics, routes, world collisions and sensing remain unchanged.
Drag with the left mouse button to orbit in RViz; scroll to zoom.
The current physical demo remains exactly two drones and one rover.
To reopen only RViz against a running simulation, use:

```bash
ros2 launch swarm_sar_gazebo rviz.launch.py
```

The custom map window is optional with views:=true; it is off by default.
In the sensor window select a robot, then click **top**, **side**, **overview**
or **follow**. Follow uses the selected robot. Other buttons stop following and
move the Gazebo camera to the requested preset.

The optional custom window shows a **rectangular occupancy-grid map**, north up,
with a Cartesian metre grid. White means observed free space, dark means
obstacles, and gray means unobserved space. It uses the selected robot's live
/private_map topic, with vehicle positions and headings overlaid.
Choose rover_0 for the most informative map: the drones fly above most walls.
Vehicle trails are optional and off by default. There are no circular LiDAR
or radar-ring displays. Camera buttons and vehicle motion are unchanged.

To open the views separately, in a second terminal:

```bash
source /opt/ros/lyrical/setup.bash
source /home/yash/Desktop/swarm-sar/ros2_ws/install/setup.bash
ros2 run swarm_sar_control demo_views
```

Camera controls can also run directly:

```bash
ros2 run swarm_sar_control demo_camera top
ros2 run swarm_sar_control demo_camera side
ros2 run swarm_sar_control demo_camera follow --robot drone_1
ros2 run swarm_sar_control demo_camera overview
```

The Gazebo GUI must be running for camera services. Headless physics is available
with headless:=true views:=false rviz:=false. RViz is enabled by default.
**Live Occupancy Map** draws the actual /rover_0/private_map cells as batched
tiles at up to 1 Hz, avoiding this VM's failing indexed-texture map shader.
Unknown cells remain the dark background, free cells are light, and occupied
cells are dark. The native **Rover 0 Private Map** display is available but off
by default. Vehicle markers update at up to 10 Hz from live odometry.
Low-resource sensors are the default; low_resource:=false restores
the higher sensor workload.

## What was wrong, and what changed

- Drone motion previously used direct body-velocity assignment and fixed rotors.
  Four revolute rotor joints now use Gazebo MulticopterMotorModel thrust, reaction
  torque, motor time constants and drag. MulticopterVelocityControl controls
  attitude and motor speeds; ROS provides rate-limited body velocity requests.
  There is no direct pose teleportation or gravity disable.
- The floor top was at z=0.1, while rover wheel bottoms spawned at z=0. The floor
  now has its top at z=0. Wheel inertias match their Y-axis rotation. Friction
  uses 0.9 longitudinal and 0.15 lateral coefficients for controlled skid steering;
  DiffDrive acceleration, deceleration and angular rates are bounded.
- The exploration controller aimed at frontier centroids without planning a
  drivable route, which could lead toward walls. The demo uses explicit routes
  in clear space, with pure-pursuit rover steering and a forward obstacle stop.
  The rover's final route is a 16-waypoint circle of radius 3 m centred at
  (-1, -14), starting at (-1, -17). Smooth curvature avoids late rectangular
  turns that overshot in the intermediate test.
  It demonstrates repeatable motion; it is not a general autonomous planner.
- Four-wheel skid-steer odometry accumulated turning error in the first test.
  The simulation path loop now uses world-pose odometry for every vehicle,
  while /rover_0/wheel_odom retains independent wheel integration. This is
  simulator ground-truth feedback, not a claim of real-world localization.
- Namespaces, command topics and all rotor controllers are separate. The drones
  have separated XY routes and different target altitudes.

## Recheck and record

```bash
cd /home/yash/Desktop/swarm-sar
python3 scripts/ros2_runtime_probe.py --agents rover_0 drone_0 drone_1 --seconds 100
gz model --list
ros2 topic echo /rover_0/demo_stage
```

Stop the echo with Ctrl+C. Stop the simulation with Ctrl+C in its launch terminal.
Keep original captures of actual windows. Tests and real run observations are
  stored in evidence/physics-demo. first-flight.json retains wheel-odometry
  drift; corrected-flight.json retains the intermediate rectangular path test
  (which later overshot). final-motion.json is the final curved-route test.

## Scope of realism

The initial Gazebo odometry twist samples showed derivative spikes at spawn.
They are retained in final-motion.json; use steady-motion.json for settled speed
measurements and the pose trajectory for motion verification. No aircraft
performance or safety certification is claimed. Intermediate shutdowns also
showed a ros_gz_bridge crash after Ctrl+C; it did not prevent restarting, but
shutdown is not entirely clean on this installed stack.

These are rigid-body simulation models with physical contact and rotor thrust.
Motor coefficients and gains are plausible simulation values, not calibrated
to a particular aircraft or rover. The flight controller uses Gazebo state,
not PX4 or an estimated IMU/GNSS state. No wind, prop wash, battery dynamics,
terrain suspension or real radar model is claimed.

Plugin references: [multicopter controller](https://gazebosim.org/api/sim/10/classgz_1_1sim_1_1systems_1_1MulticopterVelocityControl.html)
and [differential drive](https://gazebosim.org/api/sim/10/classgz_1_1sim_1_1systems_1_1DiffDrive.html).
