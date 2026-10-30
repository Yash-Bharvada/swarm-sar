# SLAM and peer communication integration

Status: implemented in this checkout and checked locally. **Live ROS/Gazebo validation is pending on Linux.** A Python unit test or frontend build is not evidence that a robot has mapped a scene. Use [the Linux agent prompt](LINUX_SLAM_VALIDATION_PROMPT.md) for the runtime checks.

GitHub source: [rashiyaom/swarm-sar, branch `rashiyaom`](https://github.com/rashiyaom/swarm-sar/tree/rashiyaom). Fetch that branch explicitly; the Linux prompt gives fresh-clone and isolated-worktree instructions, PPO recovery steps, exact launch commands and the full validation gates. The older `main` branch is not the delivery branch for this integration.

## What this adds

The rover receives simulated lidar and wheel odometry from Gazebo. `slam_toolbox` matches the scans, maintains a pose graph and estimates the transform between its map and odometry frames. A separate adapter exposes the estimated mission-frame pose and private mapping belief to a controller. The controller still decides where to search; SLAM estimates where the rover is and what its sensors observed.

Each rover has its own SLAM process. Agents exchange bounded, versioned occupancy snapshots, frontier component positions and leased frontier intent over the existing simulated radio. Maps are aligned using **known starting positions**, not automatic unknown-start map registration. Received knowledge supplements unknown cells in each receiver's belief; it does not modify that receiver's local pose graph. This is local SLAM with decentralized map/intent sharing, not a joint distributed pose-graph optimizer.

The drones retain their existing simulated world-pose/raycast mapping. Their telemetry says `simulator_pose_raycast`. This implementation does not claim aerial visual SLAM, 3D SLAM, GNN communication, physical thermal sensing or validated large-map MARL performance. Thermal/acoustic observations remain the existing noisy Gazebo-world proxy.

## Where the missing ROS PPO matters

The checked-in executables are `waypoint_demo` and `decentralized_agent`. The supplied Linux run log shows a different PPO-capable ROS implementation that is absent from every fetched source ref inspected. Preserve and recover that implementation on Linux. Do not overwrite its source, entry points, actor files or local modifications with this checkout.

The new launch has an explicit `controller:=ppo` option and checks that the named executable exists. It raises an error if it is missing. **Finding an executable is only a prerequisite:** the Linux agent must inspect/adapt its actual observation and control pipeline and prove the actor loaded and produced actions. There is no silent heuristic fallback.

Controller inputs in this profile:

| Topic | Meaning |
|---|---|
| `/<rover>/odom` | Estimated mission-frame pose from the SLAM TF chain, not world truth |
| `/<rover>/estimated_odom` | Same estimate, explicitly named for telemetry |
| `/<rover>/belief_map` | Local estimated map plus accepted RF-received knowledge |
| `/<rover>/local_slam_map` | Local SLAM observations alone, projected into the fixed mission grid |
| `/<rover>/scan` | Real simulated lidar, including obstacle sensing |
| `/<agent>/peer_inbox` | Existing controller messages routed by the radio |
| `/<agent>/slam_peer_inbox` | Versioned map snapshots, repair requests and leased intent |
| `/<agent>/slam_health`, `topology`, `estimated_path` | Operator telemetry |
| `/<rover>/ground_truth/odom` | Simulator truth for radio/sensor emulation and evaluation only |

The adapter publishes no `cmd_vel`. Run exactly one motion controller per robot. `controller:=external` starts no motion controller; `waypoint` is a repeatable mapping diagnostic, and `frontier` is the existing heuristic. Neither diagnostic proves learned search. The existing launch/default demo remains available unchanged.

Estimated odometry is primarily a **pose** interface. Its twist is not populated. TF provides no measured covariance; negative diagonal entries flag unavailable covariance, and `slam_health.covariance_available` is false. This is an application convention, not a standard `nav_msgs/Odometry` covariance sentinel. Any controller needing velocity/covariance must use wheel odometry for velocity and an explicitly suitable estimator; do not interpret the zero twist as a stopped robot.

## Transform ownership

```text
map                                 mission origin, metres
 ├─ rover_0/map                     static KNOWN start (-1,-17)
 │   └─ rover_0/odom                dynamic slam_toolbox correction
 │       └─ rover_0/base_footprint  dynamic wheel odometry
 │           └─ rover_0/base_link → lidar_link  robot_state_publisher
 ├─ rover_1/map                     static KNOWN start (-6,-17)
 │   └─ rover_1/odom → ...
 └─ drone_*/odom                    identity simulator world origin
     └─ drone_*/base_footprint      existing simulator world-pose TF
```

The SLAM bridge removes rover world-pose TF and bridges `wheel_tf` instead. It sends world odometry to the diagnostic topic. The rover Xacro flag `slam_mode:=true` labels truth as `map → <rover>/ground_truth_base`; that truth TF is not bridged. Default Xacro behavior and the old launch are preserved.

There must be no static `map → rover/odom` and no second dynamic publisher owning a rover base transform. Wheel odometry starts at zero; do not add the known spawn offset inside the controller again. The 240×240 belief grid at 0.2 m/cell spans 48×48 m, centered on the mission origin. This ROS map is separate from the learning environment's 32×32 grid: it does not establish that the policy now generalizes to larger maps.

## Peer protocol and honest visualization

The shared radio carries both controller (`peer`) and mapping (`slam_peer`) traffic. The SLAM profile sets a 32,768 byte/s token budget per sender, an 18 m range and the existing wall attenuation, stochastic loss and 0.1–0.3 s delay. Payload bytes plus a fixed 256-byte envelope estimate count against the budget; this is not physical Wi-Fi airtime. Queues and repair requests are bounded. Receiver identity follows the source topic; sender spoofing is rejected. Runtime services isolate either direction of an agent's radio and recheck queued deliveries.

Snapshots use a sender session UUID, revision, fixed grid specification, chunk index/count and cells. The receiver rejects incompatible frames, grid geometry, expired packets, duplicate sequences, old sessions and malformed data. The sender retains two immutable snapshots and answers requests for missing chunks over the same lossy/budgeted radio. A complete snapshot replaces the sender's previous layer atomically; a partial snapshot remains buffered. Full refreshes periodically repair knowledge lost in earlier transmissions. At high loss or heavy load, completion can take longer or fail; the UI shows that through actual buffered/applied events and snapshot age. Do not promise a fixed convergence time.

Local observations take precedence over peer cells. Between conflicting peer layers, deterministic sender ordering is used, not probabilistic sensor fusion. Received maps persist during a partition as historical knowledge, with age shown; short lived frontier intent expires after 8 simulated seconds. The `alignment_uncertainty_m` field is a configurable starting-alignment assumption (default 0.25 m), not a measured SLAM covariance or a guarantee against later drift. Peers above the configured admission threshold are rejected.

Frontier topology contains bounded frontier component representatives and IDs. It does not infer traversability edges, replace a navigation planner or add a learned GNN. Existing controller claim messages remain in use; the new mapping intent/graph also supports inspection and a clear PPO integration surface.

The browser's ROS mode connects to actual ROS topics. It never invokes the browser simulator or publishes velocity/goal/map commands. White/slate show local occupied/free cells, cyan shows peer-only knowledge, coloured points and trails show ROS poses, and green squares show locally estimated frontiers. Map origin, cell resolution, orientation and mission coordinates are respected. Disconnected/stale poses fade and the live indicator becomes stale. It does not keep moving robots cosmetically. This is a live 2D knowledge view alongside Gazebo's actual physical 3D scene and RViz's robot/map overlays.

## Linux build and launch

Use the host's working ROS/Gazebo installation; do not switch distributions just for this change. Commands below assume the repository is the current directory and the appropriate `/opt/ros/<distro>/setup.bash` is already sourced.

```bash
rosdep install --from-paths simulation/ros2_ws/src --ignore-src -r -y
cd simulation/ros2_ws
colcon build --symlink-install
source install/setup.bash
# FIRST: diagnostic mapping, explicitly not a PPO run
ros2 launch swarm_sar_gazebo slam_demo.launch.py scenario:=rovers controller:=waypoint rosbridge:=true
```

Then use a second sourced terminal, from the repo root:

```bash
python3 simulation/ros2_ws/tools/slam_runtime_probe.py --seconds 120 --wall-timeout 600 --output artifacts/slam_runtime.json
ros2 lifecycle get /rover_0/slam_toolbox
ros2 lifecycle get /rover_1/slam_toolbox
ros2 topic info /rover_0/cmd_vel --verbose
ros2 run tf2_ros tf2_echo rover_0/map rover_0/odom
ros2 run tf2_ros tf2_echo map rover_0/base_footprint
```

The probe requires scans, wheel feedback, multiple local scan maps, more than 100 observed cells, estimated rover movement exceeding 0.5 m, expected frames, SLAM/wheel TF edges, and at least one applied peer snapshot for multiple rovers. It checks elapsed simulation time with a wall deadline. It exits nonzero on missing evidence. It does not certify mapping accuracy, successful loop closure or PPO execution; inspect/measure those separately.

For the heterogeneous profile use `scenario:=swarm`. Diagnose rover mapping first to avoid adding drone/rendering load while fixing transforms. Stop the whole launch before changing profiles. After recovering/adapting the actual Linux PPO source:

```bash
ros2 launch swarm_sar_gazebo slam_demo.launch.py scenario:=swarm controller:=ppo ppo_executable:=ppo_agent rosbridge:=true
# Add ppo_params:=/absolute/path/to/actual_controller.yaml if needed.
```

The new launch passes the checked-in controller parameters (`external_belief_map` and `accept_peer_map` among them). A different PPO implementation may not declare/use these; adapt its actual code and verify subscriptions before driving. Do not blindly assume an inherited name implies the right behavior.

## Browser and RViz

From `frontend`: `npm ci`, then `npm run dev -- --host 127.0.0.1`. Open `http://localhost:5173/?mode=ros`. The existing simulator has a **Live ROS / SLAM** link. Enter the rosbridge WebSocket address and press Connect. The default bridge binds to loopback. To view Linux ROS on the Mac, prefer a tunnel:

```bash
ssh -L 9090:127.0.0.1:9090 <linux-user>@<linux-host>
```

Then the Mac page can use `ws://localhost:9090`. For a trusted local-network demo, binding `rosbridge_address:=0.0.0.0` permits a direct `ws://<linux-host>:9090` connection. An HTTPS page requires WSS or a local HTTP frontend. No maps or moving markers are fabricated while disconnected.

RViz opens `slam_demo.rviz`. The default occupancy tiles use the existing VM-compatible marker renderer, now sourced from the rover belief map. Enable the independent local/peer Map displays when the native renderer works. Paths come from estimates; rover robot models and scans follow the same TF tree. Ground-truth Gazebo geometry is the reference scene, not the agent's input map.

## Demo acceptance and presentation

1. Show the Gazebo scene and the initially unknown ROS belief. Drive with the mapping diagnostic only while checking integration; label it clearly.
2. Show each rover's scan-built map and estimated trajectory. Confirm the SLAM lifecycle is active and the estimate is being consumed by the active controller.
3. In the live browser, select an agent and inspect `transport_delivered` versus `receiver_applied`. Select a peer with observations outside the selected robot's own field of view to see cyan cells; overlapping maps can legitimately have no peer-only cells.
4. Isolate a rover with the real radio service. Leave it isolated for 15 **simulation** seconds. Local observations should continue while peer snapshot revision/age shows no new application. Claims should expire. Retained historical cyan cells should not disappear just to make the demonstration dramatic.
5. Reconnect. Observe actual transport events and a completed repaired/new snapshot. Allow up to multiple snapshot intervals at the current loss/load and record the observed recovery delay rather than inventing one.
6. Repeat using the recovered PPO controller; record actor identity/hash, loaded log, nonzero learned decisions, correct estimated inputs and one `cmd_vel` owner per robot. Save a rosbag, screenshots and the JSON probe output from three fresh runs.
7. For a loop-closure claim, drive a revisited loop and capture actual correction/pose-graph evidence supported by the installed toolbox. `do_loop_closing: true` alone proves configuration only. Measure estimated trajectory against truth separately for evaluation.

Restart the complete simulation/SLAM launch after a `/clock` rewind or Gazebo reset. The adapter/network fail closed and publish restart-required state; clearing a browser view does not reset an existing SLAM pose graph.

Do not present the integration as fully validated until the Linux evidence exists. The credible hackathon statement after successful validation is: **“Our learned search controller runs in a physical simulator using rover SLAM estimates; robots maintain independent mapping processes and exchange mapping knowledge and exploration intent through a lossy, range-limited peer radio.”** Qualify the drones' simulator localization and known-start alignment.

## Source files

| File | Responsibility |
|---|---|
| `simulation/ros2_ws/src/swarm_sar_gazebo/launch/slam_demo.launch.py` | Dedicated launch, lifecycle startup, TF/bridge ownership, explicit controller choice |
| `simulation/ros2_ws/src/swarm_sar_gazebo/config/slam_rover.yaml` | Ceres scan matching/loop-closure settings |
| `simulation/ros2_ws/src/swarm_sar_gazebo/config/slam_demo.rviz` | Physical models, local/peer maps, estimates and scans |
| `simulation/ros2_ws/src/swarm_sar_control/swarm_sar_control/slam_agent.py` | Estimated pose/map adapter, per-agent peer snapshot exchange, health/topology/path telemetry |
| `simulation/ros2_ws/src/swarm_sar_control/swarm_sar_control/slam_support.py` | ROS-independent geometry, snapshot validation/assembly, leases, budget, bridge projection |
| `simulation/ros2_ws/src/swarm_sar_control/swarm_sar_control/peer_network_bridge.py` | Existing transport expanded with shared channels, budget, isolation, event/stats telemetry |
| `simulation/ros2_ws/src/swarm_sar_control/swarm_sar_control/decentralized_agent.py` | Optional external belief input and expiring legacy peer claims |
| `simulation/ros2_ws/src/swarm_sar_description/urdf/rover.urdf.xacro` | Default-compatible truth frame labelling for SLAM mode |
| `simulation/ros2_ws/tools/slam_runtime_probe.py` | Bounded live runtime evidence and nonzero failure exit |
| `frontend/src/ros/` | ROS WebSocket transport, mission view, actual isolation service control |
| `tests/ros2/test_slam_support.py`, `test_physical_models.py` | Geometry, loss/recovery, reset/session boundaries, radio budget, expanded physical-model checks |

The package manifests/setup register the new node/dependencies; survivor sensing uses an explicit truth-only topic list, and the existing map-tile renderer accepts a configured map topic. No policy weights, training manifests or experiment outputs are modified.

## Upstream references

Configuration/lifecycle wiring follows [slam_toolbox's ROS 2 source](https://github.com/SteveMacenski/slam_toolbox/tree/ros2) and [online async launch](https://github.com/SteveMacenski/slam_toolbox/blob/ros2/launch/online_async_launch.py). The map name is set explicitly because upstream can default to an absolute `/map` topic. Wheel odometry behavior is checked against [Gazebo DiffDrive](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/diff_drive/DiffDrive.cc). Browser transport follows the [rosbridge protocol](https://github.com/RobotWebTools/rosbridge_suite/blob/ros2/ROSBRIDGE_PROTOCOL.md). Confirm installed host versions during runtime testing rather than assuming current upstream exactly matches the host.
