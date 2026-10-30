# Master Prompt: Porting Swarm-SAR to ROS 2 & Gazebo in Ubuntu (VMware)

Historical planning prompt. The repository now includes a Step 5 ROS 2/Gazebo demo; see `docs/guides/physics_demo.md` and `docs/audits/step5_integration.md` for its implemented behavior and limits.

> **Instructions for User:**
> 1. Open your Ubuntu VM in VMware.
> 2. Copy your `swarm` repository into the VM (e.g., via shared folder, Git clone, or SSH).
> 3. Provide this entire document as your instruction prompt to Claude / your AI coding assistant inside the Ubuntu VM.

---

## Mission Brief

You are a Senior Robotics & Autonomous Systems Engineer. You are tasked with taking this repository—**Autonomous Disaster Response Swarm (`swarm-sar`)**—and creating a **state-of-the-art ROS 2 and Gazebo multi-robot simulation** running inside an Ubuntu VMware virtual machine.

At the time this prompt was written, the project implemented Steps 1–4 of a heterogeneous search-and-rescue swarm (2 ground rovers + 2 aerial drones) with decentralized frontier exploration and a lossy peer-to-peer radio network in Python and a 2D/browser simulator.

Your objective is to build the **production-grade ROS 2 & Gazebo integration package (`swarm_sar_gazebo`)** that runs the full multi-robot search-and-rescue mission in a 3D collapsed-building world with continuous physics and sensor streams.

---

## Phase 1: Environment & Version Auto-Detection

Before writing or compiling code, inspect the host environment and adapt all package names, Gazebo plugins, and launch syntax accordingly. Run:

```bash
lsb_release -a
echo "ROS_DISTRO: $ROS_DISTRO"
which ros2
gz sim --version 2>/dev/null || ign gazebo --version 2>/dev/null || gazebo --version 2>/dev/null
glxinfo -B | grep -E "OpenGL vendor|OpenGL renderer" 2>/dev/null || echo "Check graphics"
```

### Version Matrix Handling:
- **Ubuntu 22.04 LTS**:
  - ROS 2: **Humble Hawksbill** (or Iron)
  - Gazebo: **Gazebo Fortress** (`ign gazebo` / `ros-humble-ros-ign-gazebo`) or **Gazebo Harmonic** (`gz sim` / `ros-humble-ros-gz`)
- **Ubuntu 24.04 LTS**:
  - ROS 2: **Jazzy Jalisco**
  - Gazebo: **Gazebo Harmonic** (`gz sim` / `ros-jazzy-ros-gz`)

*If ROS 2 or Gazebo is missing or incomplete, output the exact `apt-get` commands required to install the missing dependencies and build tools (`colcon`, `rosdep`, `vcstool`).*

---

## Phase 2: Package Architecture & Directory Layout

Create a clean, standard ROS 2 package structure inside `simulation/ros2_ws/src/` (or in a dedicated `ros2/` subfolder of this repository):

```text
swarm_sar_ros/
├── swarm_sar_interfaces/           # Custom ROS 2 msg/srv definitions
│   ├── msg/
│   │   ├── PeerMessageEnvelope.msg # Wire-safe peer mesh envelope
│   │   ├── SurvivorEvidence.msg    # Thermal & acoustic signals + estimated pose
│   │   └── AgentStatus.msg         # Battery, health, claimed frontiers
│   ├── CMakeLists.txt
│   └── package.xml
│
├── swarm_sar_description/          # URDF / Xacro / SDF models & meshes
│   ├── urdf/
│   │   ├── rover.urdf.xacro        # 4WD / Skid-steer rover model
│   │   └── drone.urdf.xacro        # Quadrotor multicopter model
│   ├── models/                     # Open-source PBR 3D meshes and materials
│   └── worlds/
│       └── disaster_site.world     # Collapsed building / rubble environment (SDF)
│
├── swarm_sar_gazebo/               # Simulation launch & Gazebo bridge
│   ├── launch/
│   │   ├── swarm_sar_sim.launch.py # Master launch file (spawns 4 robots + world)
│   │   └── rviz.launch.py          # RViz2 visualization
│   ├── config/
│   │   ├── ros_gz_bridge.yaml      # Clock, scan, odom, cmd_vel mappings
│   │   └── rviz_config.rviz        # Pre-configured RViz multi-robot dashboard
│   ├── package.xml
│   └── CMakeLists.txt
│
└── swarm_sar_control/              # Python ROS 2 Nodes
    ├── swarm_sar_control/
    │   ├── decentralized_agent.py  # ROS 2 node port of decentralized.py
    │   ├── peer_network_bridge.py  # Emulates RF loss, range limits, and wall attenuation
    │   └── survivor_oracle.py      # Simulates noisy thermal/acoustic detector
    ├── package.xml
    └── setup.py
```

---

## Phase 3: Robot Models (State-of-the-Art Open-Source Designs)

Use high-quality open-source robotics models with realistic physics and sensors:

### 1. Ground Rover (2 Instances: `/rover_0`, `/rover_1`)
- **Base model**: Leverage open-source 4WD skid-steer or differential drive (such as TurtleBot4, Clearpath Husky, or Leo Rover URDF/Xacro).
- **Physics**: Proper wheel collision, friction coefficients ($\mu=1.0$), inertia tensors, and mass (~10–20 kg).
- **Sensors (Gazebo plugins)**:
  - 2D or 3D LiDAR (`gpu_lidar` or `ray` sensor) publishing to `/<robot_ns>/scan` (10 Hz, 12 m range, $360^\circ$).
  - Differential drive plugin subscribing to `/<robot_ns>/cmd_vel` and publishing `/<robot_ns>/odom` and TF (`odom` $\to$ `base_footprint`).
  - IMU sensor publishing to `/<robot_ns>/imu/data`.
  - Thermal camera proxy: simulated sensor publishing thermal hotspots or forward-facing camera with synthetic overlay.

### 2. Aerial Drone (2 Instances: `/drone_0`, `/drone_1`)
- **Base model**: Quadrotor multicopter (based on open-source PX4 Iris, Crazyflie, or Hector Quadrotor SDF/URDF).
- **Flight dynamics**: Utilize Gazebo's Multicopter Motor plugin (`gz::sim::systems::MulticopterMotorModel` or velocity control plugin).
- **Sensors**:
  - Downward-facing camera / optical flow publishing to `/<robot_ns>/downward_camera/image_raw`.
  - Downward 1D LiDAR / sonar rangefinder publishing `/<robot_ns>/altitude` (range 0.1–10 m).
  - 360° lightweight planar LiDAR for obstacle avoidance.
  - Odometry and IMU sensors.

---

## Phase 4: The 3D Disaster World (`disaster_site.world`)

Create an immersive, realistic collapsed disaster site:
- **Terrain & Obstacles**:
  - Concrete floor with cracks, concrete barrier slabs, rubble piles (`box`/`mesh` debris), and damaged walls forming rooms, choke points, and narrow corridors.
  - Boundary walls containing the site (e.g., 40 m $\times$ 40 m).
- **Lighting & Atmosphere**:
  - Low ambient illumination with directional sun light cast at an angle to create pronounced shadows.
  - Emergency warning lights (flashing amber/orange point lights) stationed at key rubble intersections.
- **Survivors / Victims**:
  - Place 3 to 6 survivor models (open-source human/casualty meshes) trapped in rubble or tucked behind collapsed walls.
  - Each survivor has an assigned $(x, y, z)$ position, emitting thermal signatures (detectable within ~6 m line-of-sight/attenuated through rubble) and periodic acoustic beeps.

---

## Phase 5: Porting the Decentralized Controller to ROS 2

Replicate the exact logic from `simulation/src/swarm_sar/baselines/decentralized.py` and `simulation/src/swarm_sar/network/peer_network.py` without introducing any global state or cheating:

### 1. Agent Node (`decentralized_agent.py`)
- Instantiated per robot namespace: `/rover_0`, `/rover_1`, `/drone_0`, `/drone_1`.
- **Inputs**:
  - Subscribes to local LiDAR (`scan`), local odometry (`odom`), and local sensor evidence (`survivor_evidence`).
  - Subscribes to peer inbox: `/<robot_ns>/peer_inbox` (`PeerMessageEnvelope`).
- **Local Belief & Frontier Selection**:
  - Maintains a private occupancy grid (`nav_msgs/OccupancyGrid`) updated only from local sensor scans and verified map deltas from peer messages.
  - Computes open frontiers using BFS / topological graph clustering.
  - Dispatches velocity commands (`cmd_vel`) or sends goal poses to Nav2/simple trajectory follower.
- **Safety Filter**:
  - Employs local repulsive potential fields / reactive safety barrier to guarantee zero robot-to-robot or robot-to-wall collisions.

### 2. Peer Network Bridge Node (`peer_network_bridge.py`)
- Replaces raw ROS 2 topic multicasting with realistic peer-to-peer radio simulation:
  - Listens to peer broadcasts on `/<robot_ns>/peer_outbox`.
  - Calculates inter-robot Euclidean distance from true robot poses.
  - **Drop Probability**:
    $$P_{\text{drop}} = P_{\text{loss\_base}} + f(\text{distance}) + \text{wall\_attenuation}$$
  - **Latency Queue**: Buffers delivered messages for $T_{\text{delay}} \in [1, 3]$ ticks before publishing to the recipient's `/<target_ns>/peer_inbox`.
  - If robots are separated by a wall barrier or exceed maximum radio range (e.g., > 18 m), drop packets and record a network partition event.

---

## Phase 6: Single-Command Master Launch (`swarm_sar_sim.launch.py`)

A single launch command must bring up the entire system cleanly:
```bash
ros2 launch swarm_sar_gazebo swarm_sar_sim.launch.py
```
This launch file must:
1. Start Gazebo Sim with `disaster_site.world`.
2. Start the `ros_gz_bridge` translating Gazebo topics (`/scan`, `/odom`, `/cmd_vel`) to ROS 2 topics.
3. Spawn `/rover_0` and `/rover_1` at the staging area with non-overlapping initial poses.
4. Spawn `/drone_0` and `/drone_1` at aerial spawn coordinates.
5. Launch the `peer_network_bridge` node.
6. Launch 4 independent instances of `decentralized_agent` under their respective namespaces.
7. Launch RViz2 with a multi-robot config file (`rviz_config.rviz`) showing merged and private map layers, laser scans, planned paths, and survivor detection beacons.

---

## Phase 7: VMware Specific Optimizations & Debugging

Virtual machine graphics drivers often encounter GLX/Vulkan issues with modern Gazebo. Anticipate and provide fixes for:

1. **OpenGL / SVGA Hardware Acceleration**:
   - In VMware, if Gazebo crashes with `X11 connection rejected` or `Failed to create OpenGL context`:
     ```bash
     export LIBGL_ALWAYS_SOFTWARE=1
     export SVGA_VGPU10=0
     export MESA_GL_VERSION_OVERRIDE=3.3
     ```
2. **FastDDS / CycloneDDS Loopback in VM**:
   - Multiple namespaces on one host can saturate multicast buffers. Provide `export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` or a tuned FastDDS XML config if packet drops occur on localhost.
3. **Gazebo Model Path**:
   - Automatically export environment variables in the launch file or `.bashrc`:
     ```bash
     export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:$(ros2 pkg prefix swarm_sar_description)/share/swarm_sar_description/models
     ```

---

## Acceptance Criteria
- [ ] Running `colcon build --symlink-install` succeeds with zero errors.
- [ ] `ros2 launch swarm_sar_gazebo swarm_sar_sim.launch.py` boots Gazebo and RViz2.
- [ ] Both rovers and both drones spawn cleanly without physics explosions or overlapping.
- [ ] Robots autonomously explore frontiers, avoid walls and each other, and exchange map deltas over the simulated peer network.
- [ ] When a survivor thermal hotspot is confirmed, an alert marker is published and broadcast across the swarm.

Begin by inspecting the system versions and outputting the exact setup commands.
