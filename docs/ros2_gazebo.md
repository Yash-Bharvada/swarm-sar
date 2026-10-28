# ROS 2 Jazzy + Gazebo Harmonic integration

For the latest Lyrical engineering audit, measured results, low-resource
profiles and known failures, see [engineering_audit.md](engineering_audit.md).
The current default opens the disaster world in Gazebo and the map in RViz,
with exactly two drones and one rover. See [physics_demo.md](physics_demo.md)
for the current run guide. Use headless:=true rviz:=false for server-only runs.

The ROS workspace is under `ros2_ws/src` and contains four packages:

- `swarm_sar_interfaces`: peer envelope, survivor evidence, and agent status messages.
- `swarm_sar_description`: two robot descriptions and the 40 m disaster world.
- `swarm_sar_control`: independent frontier agents, lossy RF transport, and noisy survivor sensing.
- `swarm_sar_gazebo`: bridges, RViz configuration, spawning, and the master launch.

The controller receives no world model or survivor truth. Each instance updates a private occupancy grid from its own scan, ranks clustered frontiers, avoids peer claims delivered over the emulated radio, and uses a reactive LiDAR stop/turn barrier. The survivor oracle converts configured truth into range-limited, noisy evidence; it does not publish truth poses. The network node is transport-only and applies range, distance-dependent loss, wall attenuation, random delay, and message expiry.

## Detected development host

This checkout is currently validated with ROS 2 Lyrical and Gazebo Sim 10 on Ubuntu 26.04. Source `/opt/ros/lyrical/setup.bash` before building or launching. The Ubuntu 24.04/Jazzy path below remains available for VMware guests using the earlier LTS stack. Do not mix Ubuntu releases in the ROS apt repository.

Run the included detector at any time:

```bash
./scripts/ros2_preflight.sh
```

## Exact Ubuntu 24.04 setup

```bash
sudo apt update
sudo apt install -y software-properties-common curl
sudo add-apt-repository universe
sudo apt update
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list >/dev/null
sudo apt update
sudo apt install -y ros-jazzy-desktop ros-jazzy-ros-gz ros-jazzy-xacro \
  ros-jazzy-robot-state-publisher ros-jazzy-rmw-cyclonedds-cpp \
  python3-colcon-common-extensions python3-rosdep python3-vcstool mesa-utils
sudo rosdep init || true
rosdep update
```

Build from the repository root:

```bash
source /opt/ros/jazzy/setup.bash
cd ros2_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
ros2 launch swarm_sar_gazebo swarm_sar_sim.launch.py
```

On the detected Ubuntu 26.04/Lyrical host, use:

```bash
source /opt/ros/lyrical/setup.bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash
ros2 launch swarm_sar_gazebo swarm_sar_sim.launch.py
```

In a second terminal, useful checks are:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
ros2 node list
ros2 topic hz /rover_0/scan
ros2 topic echo /rover_0/status --once
ros2 topic echo /rover_0/peer_inbox --once
```

## VMware graphics and DDS

First enable **Accelerate 3D graphics** in the VMware display settings. If Ogre2 cannot create a context, use software rendering for the launch terminal:

```bash
export LIBGL_ALWAYS_SOFTWARE=1
export SVGA_VGPU10=0
export MESA_GL_VERSION_OVERRIDE=3.3
```

If DDS multicast is unreliable inside the guest, select CycloneDDS:

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
```

The launch file extends `GZ_SIM_RESOURCE_PATH` automatically. The world uses primitive rubble collisions intentionally: visual complexity can be increased later without destabilizing VM physics.

## Validation status

- XML, Python syntax, package dependencies, interface definitions, topic mappings, and launch composition are covered by repository tests.
- `colcon build --symlink-install` completes successfully for all four packages on ROS 2 Lyrical.
- Gazebo Sim 10 loads the world and exactly four robot entities (`rover_0`, `rover_1`, `drone_0`, and `drone_1`). All four control nodes, robot-state publishers, static map transforms, the ROS/Gazebo bridge, RF bridge, survivor oracle, and RViz start from the master launch.
- Live smoke testing confirmed odometry, LiDAR/IMU/camera bridges, private maps, commands, status, evidence, and peer topics. One sampled RF interval recorded 108 attempts, 78 deliveries, 16 out-of-range drops, 14 probabilistic drops, and zero expired packets.
- A longer unattended mission is still required to measure final coverage, survivor recovery, and collision count. VMware currently reports 3D acceleration disabled; enable it for usable real-time factor and clean RViz rendering.
- The drones use Gazebo's body velocity controller with altitude hold. This is stable for mission/controller testing but is not a PX4 motor/rotor aerodynamic model.
