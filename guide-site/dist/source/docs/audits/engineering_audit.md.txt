# Engineering audit - 28 October 2026

Historical audit snapshot. The later [physical demo](../guides/physics_demo.md) replaces
the velocity-only drones and updates rover feedback, tire contact and demo
routes. See docs/evidence/physics-demo for current motion validation; earlier PDF
and pair logs describe the earlier implementation.

This audit extends the existing implementation on ubuntu_simulations. It does not
certify competition readiness. Raw observations are in docs/evidence/2026-10-28/logs.

## Initial findings

The host runs Ubuntu 26.04.1, ROS 2 Lyrical and Gazebo Sim 10.5.0.
The VM has 7.3 GiB RAM and no swap. The original launch always starts four
robots, Gazebo GUI and RViz, with two 640 x 480 cameras at 15 Hz.
No running Gazebo instance was found before the audit runs.

Four ROS packages separate interfaces, models, controllers and launch/config.
Each robot consumes its scan and odometry and produces a private occupancy
grid, frontier commands, status and peer messages. A transport-only node
models radio loss/delay; a survivor oracle produces synthetic evidence.
Commands cross ROS-to-Gazebo bridges; clock, odometry, TF and sensors cross
Gazebo-to-ROS bridges. These are modern Gazebo plugins, not Gazebo Classic.

Issues identified: fixed robot count and GUI workload; duplicate incoming TF
edges for drone base_link; no explicit 3D drone odometry setting; Python
shutdown exceptions; no bounded machine-readable live health probe.

## Changes

- Launch profiles: rover, drone, pair (rover_0 + drone_0), full (original four).
- RViz is opt-in. Headless mode uses server-only EGL rendering.
- Bridge configuration is filtered to selected robots using a temporary YAML,
  removed on normal launch-process exit. Peer and oracle agent lists and spawn
  offsets follow the same selection.
- Low-resource LiDAR: 180 rays at 5 Hz; drone camera: 320 x 240 at 3 Hz.
  Original fidelity remains available with low_resource:=false.
- Drone odometry targets base_footprint, so the fixed base_link transform has
  a unique parent; odometry explicitly requests three dimensions.
- ROS nodes catch normal interrupt/context shutdown and use try_shutdown.
- A read-only probe records topic counts, samples, positions and dynamic TF
  parents, and fails if requested streams are missing.

## Reproduce

From a clean Bash terminal:

```bash
cd /home/yash/Desktop/swarm-sar/simulation/ros2_ws
source /opt/ros/lyrical/setup.bash
colcon build --symlink-install
source install/setup.bash
LIBGL_ALWAYS_SOFTWARE=1 ros2 launch swarm_sar_gazebo swarm_sar_sim.launch.py scenario:=pair
```

Use scenario:=rover for one rover, scenario:=drone for one drone, or
scenario:=full for the original four. Add headless:=true for server-only
rendering; add rviz:=true to display RViz. Set low_resource:=false for the
original sensor workload. These options describe available configurations;
consult the run logs for which configurations were actually tested.

In another sourced terminal, from the repository root:

```bash
python3 simulation/scripts/ros2_runtime_probe.py --agents rover_0 drone_0 --seconds 30
ros2 node list
ros2 topic list
ros2 topic echo /rover_0/status --once
gz model --list
```

Stop using Ctrl+C in the launch terminal and wait for shutdown before restarting.
Build dependencies are declared in each package.xml; rosdep can resolve them:
`rosdep install --from-paths src --ignore-src -r -y` from ros2_ws.

## Limits requiring further engineering

Final corrected pair observation: 35.1 wall seconds, 81/82 rover/drone scans,
810/1614 IMU messages, 450 odometry messages per robot, 49 camera images,
and 14/13 peer inbox messages. No requested streams were missing.
Drone z changed from 2.4995 to 2.4510 m; both robots changed XY position.
Gazebo entity listing confirmed exactly rover_0 and drone_0 alongside world
models. Terminal Ctrl+C stopped all ROS nodes cleanly; Gazebo exited on
SIGINT (-2) without forced kill. An earlier timeout-based run required SIGKILL.

Live testing exposed missing IMU world-system configuration and world-relative
drone odometry being offset twice. Both were fixed before the final probe.

The drone is a velocity-controlled proxy, not an aerodynamic or PX4 vehicle.
The map uses odometry rather than SLAM and treats scans approximately at the
robot origin. The safety barrier is reactive, not a collision-free planner.
RF wall segments approximate the world and do not exactly follow every rotated
wall. Battery and health status are synthetic, not validated hardware telemetry.
The floor extends to z=0.1 while rover spawn is z=0, so initial contact settling
requires inspection. Wheel joint state publication is not implemented, limiting
RViz wheel transforms. Sustained coverage, contacts, survivor recovery and
deterministic replay remain untested. Do not describe these as completed.

## Screenshot collection

Direct GNOME screenshot capture returned AccessDenied: Screenshot is not allowed.
The user has offered to capture original PNGs manually. Save them under
docs/evidence/2026-10-28/screenshots. Until supplied, the PDF must state that the ten
screenshots are outstanding, not substitute illustrations or terminal mockups.

Capture: world overview; rover detail; node list; sensor sample; bridge info;
movement before/after; drone view; simultaneous pair; TF diagnostics; final scene.
Label each with its actual run and time. A still image alone cannot prove movement;
use the probe's first/last odometry and command observations alongside it.
