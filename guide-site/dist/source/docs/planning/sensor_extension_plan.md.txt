# Sensors and the impact of extending Step 4

Reviewed on 29 October 2026. This document describes the Python and browser simulated sensor contracts, then recommends how to extend them without discarding the validated baseline. Step 5 separately added ROS 2/Gazebo simulated LiDAR, IMU, drone camera and range streams. It does not establish physical sensor drivers or learned-policy deployment on ROS robots.

## Current rover and drone inputs

Both robot types use the same modalities with different configured ranges. Values are **grid-cell radii**, not measured hardware specifications. The browser renders one cell as one metre, but the sensing models are not calibrated to a real device.

| Input | Rover | Drone proxy | What is actually implemented |
|---|---:|---:|---|
| Occupancy/range-scan abstraction | Radius 4 | Radius 7 | Line-of-sight ray casting reveals nearby grid cells into the robot's private map. Walls occlude the scan. This is lidar-like occupancy sensing, not a real lidar stream or RGB image. |
| Thermal evidence | Radius 6 | Radius 8 | Four directional sector intensities; distance decay, missed detections, noise and false positives. Walls block the line of sight. There is no thermal image or thermal-camera detector. |
| Acoustic evidence | Radius 10 | Radius 12 | One omnidirectional signal with decay, noise, misses and false positives. Walls attenuate it. There is no microphone waveform, speech recognition or sound-source localization pipeline. |
| Close confirmation | Radius 2 | Radius 2 | An investigating robot can confirm a simulator survivor within range and line of sight. This is an environment-side confirmation rule, not another modeled physical device. |
| Odometry / pose uncertainty | Drift std 0.035; uncertainty growth 0.01 | Drift std 0.05; uncertainty growth 0.015 | Simulated drifting pose and uncertainty are maintained. Real wheel encoders, visual-inertial odometry and an IMU are not implemented. Planning still receives the exact own grid cell under the existing abstraction. |
| Nearby teammates / collision feedback | Four adjacent cells; collision flag | Four adjacent cells; collision flag | Adjacent teammate cells and collision outcomes come from simulator state. They are not readings from an independently implemented proximity sensor. |
| Battery telemetry | Budget 300 before area scaling | Budget 240 before area scaling | Move, rubble and idle consumption are modeled. This is telemetry rather than a sensor modality; browser goal planning currently does not use battery fraction to return or recharge. |
| Peer radio | Radius 8 | Radius 10 | A simulated communication channel carries delivered peer updates, with range, walls, loss, latency, expiry and partitions. This is transport, not an additional perception sensor. |

The numeric configuration is in [configs/robots.yaml](../../configs/robots.yaml#L1), mirrored by [browser config](../../frontend/src/simulation/core/config.ts#L39). Implementations are [Vision.ts](../../frontend/src/simulation/sensing/Vision.ts#L73), [SensorModel.ts](../../frontend/src/simulation/sensing/SensorModel.ts#L19), [Python vision](../../simulation/src/swarm_sar/sensing/vision.py#L58), and [Python victim sensing](../../simulation/src/swarm_sar/sensing/victim_sensor.py#L11). [LocalView](../../frontend/src/simulation/controller/DecentralizedController.ts#L21) and [its assembly](../../frontend/src/simulation/core/SimulationEngine.ts#L286) show the inputs actually delivered to browser planning.

The Python training and browser policy paths have **no live RGB camera, depth camera, calibrated lidar, IMU, barometer, GPS, radar, gas detector or physiological sensor input**. Step 5's Gazebo camera, LiDAR and IMU are separate simulated streams and are not inputs to the trained policy. Camera/lidar-shaped meshes and drone altitude in the browser view do not add those capabilities.

## Is this enough, and should more be added?

**Keep the current sensor set for the documented hackathon simulation MVP.** It already provides complementary information for exploration and survivor location: occupancy for routes, directional thermal clues, longer-range acoustic clues, and close confirmation. Adding more labels or meshes would not improve the underlying evidence.

The next useful engineering work is to reduce existing abstractions and measure a benefit: local sensing-based collision avoidance, localization/uncertainty that genuinely affects map registration, and battery-aware replanning. These address demonstrated limits in [the readiness audit](../audits/hackathon_readiness_audit.md). This is a project-specific prioritization, not a claim that the current set is enough for physical disaster response.

If an additional capability is required:

| Goal | Sensible extension | Scope |
|---|---|---|
| Improve obstacle realism and local safety | Noisy range/depth observations feeding a local occupancy/cost map, with blind spots and latency | A sensing/mapping/safety change; a new policy input is optional if the existing map semantics are preserved. |
| Improve pose estimation on an eventual rover | Wheel-encoder/IMU fusion, optionally corrected by a mapping/localization source | Requires real or simulated sensor streams, timestamps, frame transforms, covariance handling and registration tests. It is not solved by adding a position-noise slider. |
| Add independent visible-person evidence | An RGB/depth detection pipeline with explicit confidence, false alarms and occlusion behavior | More substantial perception work. Give this evidence its own semantics; do not relabel RGB confidence as “thermal” just to keep the old fields. |
| Model a flying drone | Flight-state estimation and an actual flight-control/sensor model | A separate robotics milestone; unnecessary for the present 2D aerial proxy. |

The map-adapter approach is consistent with Nav2's separation between sensor observations and costmaps: its obstacle/voxel layers consume `LaserScan` and `PointCloud2` sources. See the official [Nav2 Jazzy costmap documentation](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/costmap_2d/). The official [`robot_localization` state-estimation documentation](https://github.com/cra-ros-pkg/robot_localization/blob/rolling-devel/doc/state_estimation_nodes.rst) describes fusing odometry/IMU-style inputs while retaining explicit map, odom and robot frames. Those packages are possible future integration components, not dependencies currently running in this simulator.

## Would this require redoing Step 4?

**No wholesale rebuild is necessary. Revalidate the parts whose contracts or behavior change.** Preserve the original Step 4 implementation and results as a named baseline; evaluate a sensor extension as a separate configuration/version.

| Extension | Existing Step 4 architecture | Required work |
|---|---|---|
| Extra UI-only visualization | Unchanged | Presentation checks. It must not be described as an implemented sensor. |
| Change range/noise/false-positive parameters of an existing modality | Reusable | Sensor tests plus fixed-seed mission, localization, autonomy and network-fault regressions. New result numbers belong to the new configuration. |
| Fuse a sensor into an existing occupancy map or pose estimate, preserving units and meanings | Controller and peer envelope can often remain | Add a sensor adapter/fusion layer; validate timing, unknown/occupied map behavior, uncertainty and coordinate frames. Re-run affected missions and map-merge tests. Re-evaluate learned policies because input distributions can change even when vector size does not. |
| Expose new per-agent evidence to decisions | Local decision loop remains useful | Extend robot state, local observations and controller/fusion rules. Add truth-boundary and false-confirmation tests. Update learned-policy inputs if the model is meant to use the new evidence. |
| Send new evidence in peer messages | Transport mechanisms remain useful | Version/document the message schema; update sender, receiver, serialization/size estimates, snapshots and compatibility behavior. Re-test bandwidth, loss, delay, TTL, deduplication, partitions and reconnection with the new payload. |
| Change localization or map-coordinate conventions | Requires special care | Revisit frame transforms, uncertainty thresholds, registration and map merging. Existing same-cell common-grid fusion cannot be assumed correct for a new coordinate system. |
| Change learned input dimensions or semantics | Historical checkpoints remain a frozen baseline | Version the observation contract and encoder, migrate/create a compatible model, and retrain or fine-tune/evaluate it. An old model cannot use an extra channel merely because a sensor was added. |

The browser and Python systems are separate implementations. Extending only the browser does not upgrade the Python Step 4 controller or its PPO checkpoint; extending only Python does not make the new modality visible in the browser.

## Files and interfaces affected by a real sensor extension

1. **Configuration and sensor simulation/adapter:** `configs/robots.yaml`; `simulation/src/swarm_sar/sensing/`; browser `simulation/core/config.ts` and `simulation/sensing/`. Define output units, frame, rate, noise, misses, false positives and failure behavior. Keep stochastic outputs seeded; avoid silently changing old random streams when preserving a frozen baseline.
2. **State and private observations:** `simulation/src/swarm_sar/robots/robot.py`, `simulation/src/swarm_sar/sim/engine.py`, `simulation/src/swarm_sar/sim/env.py`; browser `RobotState.ts`, `SimulationEngine.localView()` and `LocalView`. New measurements must reach a robot through its own sensor adapter or a genuinely delivered peer message, not a hidden truth lookup in planning.
3. **Fusion, decisions and confirmation:** both decentralized controllers and investigation/confirmation paths. Specify what a new cue changes and how conflicting or stale cues are handled. A rendered human/flag is not a perception measurement.
4. **Peer evidence only when needed:** `simulation/src/swarm_sar/network/messages.py`, Python environment broadcast/merge code; browser `PeerMessage.ts` and `SimulationEngine.broadcastState()/processMessages()`. Current browser evidence is thermal, acoustic and an estimated position; pose and pose uncertainty govern merge acceptance ([envelope](../../frontend/src/simulation/network/PeerMessage.ts#L4), [broadcast](../../frontend/src/simulation/core/SimulationEngine.ts#L523), [merge](../../frontend/src/simulation/core/SimulationEngine.ts#L546)). Prefer compact evidence summaries rather than broadcasting raw image/depth arrays.
5. **Learned contract if exposed to PPO:** `simulation/src/swarm_sar/policy_contract.py`, `learning/observation.py`, environment observation spaces, model/training configuration, demonstration data and export/inference tests. The current `gpu-v1` encoder has **229 values**. The older Step 3 checkpoint consumes a deliberately preserved **129-value prefix** ([contract](../../simulation/src/swarm_sar/policy_contract.py#L10), [encoder](../../simulation/src/swarm_sar/learning/observation.py#L12), [compatibility adapter](../../simulation/src/swarm_sar/learning/inference.py#L55)). Do not reorder or repurpose old fields without a new contract. Same vector length does not make changed semantics backward compatible.
6. **UI, logging and tests:** add understandable readouts and per-modality diagnostics, then sensor unit tests, no-truth-leak tests, same-seed replay, collision checks and network-on/off mission evaluation. Keep old modality-off behavior available as a regression comparison.

An acceptance comparison should use identical map seeds and robot budgets with the extension on/off, reporting recall, false confirmations, missed detections, coverage, mission time, unsafe requested moves versus post-shield collisions, computation and message traffic. Exercise 0/10/30% loss and partition/recovery when peer evidence changes. Retain a new sensor only when its measured benefit justifies the complexity.

For the current hackathon, the recommended decision is therefore: **finish and validate the existing sensing/coordination pipeline first; do not add new modalities solely to increase the sensor count.**
