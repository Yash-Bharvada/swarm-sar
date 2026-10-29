# Controller compatibility: Python Step 4 ↔ browser simulator

The historical TypeScript/Python comparison below applies to **Browser heuristic**
mode. Optional **PPO · 754k** mode uses Python's authoritative world and recurrent
policies through the [mission service](../docs/ppo_frontend_integration.md); the
TypeScript controller does not execute there.


This document maps the TypeScript simulator in `frontend/src/simulation/` to the validated
Python Step 4 reference. The Python code is the behavioural source of truth; nothing in the
Python package was modified.

**Reference revision:** upstream `main` at `e2db65c` ("training: add guarded behavior cloning
and cohort gates"). That revision and its parent `0f9210d` changed
`baselines/decentralized.py` to respect the frontier action mask; the browser port includes
that change. Their other additions (GPU-v1 training pipeline, behavior cloning, cohort gates,
extra observation fields for learning) do not affect controller decisions and are not ported.

The browser's **Decentralized Autonomous Mode** ports the principles and algorithms of
`DecentralizedFrontierController`. It is not PPO, RL, MARL or a GNN, and it does not run ROS 2 or
Gazebo.

## File map

| Python reference | Browser implementation |
|---|---|
| `src/swarm_sar/world/cells.py` | `world/GridMap.ts` (`UNKNOWN`, `FREE`, `WALL`, `RUBBLE`) |
| `src/swarm_sar/world/generator.py`, `victims.py`, `reachability.py` | `world/ScenarioGenerator.ts`, `GridMap.ts` (`bfsDistances`, `closeUnreachable`) |
| `src/swarm_sar/robots/robot.py` | `robots/RobotState.ts` |
| `configs/robots.yaml` | `core/config.ts` `ROBOT_CONFIGS`, `robots/RoverRobot.ts`, `robots/DroneRobot.ts` |
| `src/swarm_sar/sensing/vision.py` | `sensing/Vision.ts` |
| `src/swarm_sar/sensing/victim_sensor.py` | `sensing/SensorModel.ts` |
| `src/swarm_sar/sim/planning.py` | `planning/AStar.ts`, `planning/FrontierPlanner.ts` |
| `src/swarm_sar/sim/engine.py` `apply_movements` | `controller/CollisionSafety.ts` `applyMovements` |
| `src/swarm_sar/sim/env.py` `_safety_filter_movements` | `controller/CollisionSafety.ts` `safetyFilter` |
| `src/swarm_sar/sim/env.py` (broadcast, merge, investigate, step order) | `core/SimulationEngine.ts` |
| `src/swarm_sar/network/messages.py` | `network/PeerMessage.ts` |
| `src/swarm_sar/network/peer.py` | `network/PeerNetwork.ts` |
| `src/swarm_sar/baselines/decentralized.py` | `controller/DecentralizedController.ts` (`AgentBrain`, `branchOwner`, `shouldInvestigate`) |
| `configs/network.yaml` | `core/config.ts` `DEFAULT_CONTROLLER` |
| `configs/sim.yaml` `network_*` keys | `core/config.ts` `DEFAULT_NETWORK` |
| `tests/test_network.py` | `src/tests/network.test.ts` |
| `tests/test_decentralized_controller.py` | `src/tests/controller.test.ts`, `autonomy.test.ts`, `determinism.test.ts` |

## World cell values

| Value | Name | Truth grid | Belief map |
|---:|---|---|---|
| -1 | `UNKNOWN` | never | not yet sensed or received |
| 0 | `FREE` | open floor | known open floor |
| 1 | `WALL` | wall, furniture, rock | known blocking cell |
| 2 | `RUBBLE` | passable at extra cost | known rubble |

The browser adds a render-only `material` layer (concrete, broken wall, rock, desk, crate,
shelf, pillar, collapsed slab). A desk is a `WALL` cell drawn as a desk. Materials never affect
logic.

## Robot state fields

| Python `Robot` | TypeScript `RobotState` | Notes |
|---|---|---|
| `id`, `type`, `name` (`rover_0`) | `id`, `type`, `name` | Same naming and ordering: rovers first, then drones, ids sequential |
| — | `label` (`Rover 1`) | Operator-facing only |
| `x`, `y` | `x`, `y` | Truth cell. Used for physics and sensor emulation, and, as in Python, as the robot's own cell for planning |
| `battery` | `battery`, `maxBattery` | Scaled by site area (see simplifications) |
| `belief` | `belief: GridMap` | Private per robot, starts all `UNKNOWN` |
| `visited`, `distance_travelled` | same | |
| `odom_x`, `odom_y`, `odom_uncertainty` | `odomX`, `odomY`, `odomUncertainty` | Drifting odometry broadcast as `pose` |
| `alive`, `last_action`, `collided` | same | |
| `thermal[4]`, `acoustic[1]`, `prev_*` | `thermal`, `acoustic`, `prevThermal`, `prevAcoustic` | Sectors: up, right, down, left |
| controller `local_goals[agent]` | `AgentBrain.localGoal` | One brain per robot holds only its own goal |
| env `_active_goals[agent]` | `RobotState.activeGoal`, `path` | Mirror for rendering and broadcasting |

## Action meanings

Movement actions (`sim/engine.py ACTIONS`): `0` stay, `1` up (y−1), `2` down (y+1), `3` left
(x−1), `4` right (x+1).

High-level policy actions (`sim/env.py`): `0–4` frontier slot, `5` investigate, `6` hold. The
browser brain returns a `Decision` whose `action` uses the same codes, with the frontier slot
indexing the robot's own candidate list (the active goal is prepended, exactly as
`_candidate_list` does).

**Action mask** (`env.observe`, honoured by the controller since `0f9210d`): a frontier slot is
valid only if its path's next step is not a cell occupied by a teammate. The brain keeps its
current goal only while that slot is valid and no higher-priority peer claims it. Otherwise it
releases the goal, recomputes its candidates, and picks only among valid slots. The chosen
slot's own frontier-search path is executed, as Python executes `candidates[slot]["path"]`.

Investigate steps towards the strongest thermal sector only if the robot's own belief says that
cell is traversable, then fuses an independent second sample.

## Message fields

| Conceptual field | Python `PeerMessage` / payload | TypeScript `PeerMessage` |
|---|---|---|
| senderId | `sender_id` | `senderId` |
| sequence | `seq` | `sequence` (monotonic per sender) |
| frameId | `frame_id` = `common_entry_v1` | `frameId` = `common_entry_v1` |
| sentStep | `sent_step` | `sentStep` |
| expiresStep | `expires_step` = sent + TTL | `expiresStep` |
| recipientId / broadcast | implicit broadcast | `recipientId: null` (neighbourhood broadcast; the only mode used) |
| kind | `kind` = `state_delta` | `kind` = `state_delta` |
| pose | `pose` (odometry) | `pose` |
| poseUncertainty | `pose_uncertainty` | `poseUncertainty` |
| robotType | `payload.robot_type` | `robotType` |
| claimedGoal | `payload.goal` | `claimedGoal` |
| evidence | `payload.evidence {thermal, acoustic, position}` | `evidence` (same shape; position is the sender's own estimate) |
| graphDelta | `payload.graph_delta` (≤5 frontiers) | `graphDelta` |
| mapCells | `payload.map_cells` `[x, y, value]` | `mapCells` |
| isSnapshot | `payload.map_snapshot` | `isSnapshot` |
| message id | `sender_id:seq` | `messageId()` = `senderId:sequence` |

## Network settings

| Setting | Python default (`configs/sim.yaml`) | Browser default |
|---|---|---|
| packet loss | 0.0 (audits: 0, 0.1, 0.3) | 5% in the UI, slider 0–30% |
| delay steps | [1, 2] | [1, 2]; slider sets [1, N] for N = 1–6 |
| message TTL | 8 | 8 |
| bandwidth bytes per sender per step | 8192 | 8192 |
| wall attenuation | 0.70 per wall on the Bresenham line | 0.70 |
| require LOS | false | false |
| snapshot interval | 8 | 8 |
| map chunk cells | 64 | 64 |
| transform uncertainty max | 4.0 | 4.0 |
| partition windows | `[{start, end, agents}]` | Same; the UI toggle adds an open-ended window for the selected robot |
| radio radius | min(sender, receiver) `comm_radius` (rover 8, drone 10) | same |

Transport order matches `PeerNetwork.advance`. Due deliveries come first, sorted by
(deliverStep, recipient, sender, seq). Then, for each sender in sorted order: bandwidth,
then per recipient in sorted order: partition, radio range and walls, a loss draw, a delay draw.
Delay 0 delivers immediately. Delivery checks expiry (`stale`), then de-duplication, then
updates the latest message per sender. `peerMessages()` returns the latest unexpired message
per sender with age ≤ TTL. Reconnections are counted when a pair's link goes from down to up.

Receivers merge map cells only into their own `UNKNOWN` cells, and only when the frame ID
matches and both uncertainties are within the limit. Otherwise the merge is refused and counted.

## Sensor concepts

| Concept | Rover | Drone |
|---|---:|---:|
| Vision radius (LOS ray-cast into private belief) | 4 | 7 |
| Thermal radius / decay / noise / detection p / false-positive rate | 6 / 3.0 / 0.05 / 0.88 / 0.02 | 8 / 4.0 / 0.07 / 0.92 / 0.025 |
| Acoustic radius / decay / noise / detection p / false-positive rate / wall factor | 10 / 6.0 / 0.10 / 0.90 / 0.03 / 0.4 | 12 / 7.0 / 0.12 / 0.92 / 0.035 / 0.5 |
| Confirm radius (with LOS, while investigating) | 2 | 2 |
| Battery / move / rubble / idle cost | 300 / 1 / 2 / 0.1 | 240 / 1 / 1 / 0.1 |
| Odometry drift std / uncertainty growth | 0.035 / 0.01 | 0.05 / 0.015 |

- Thermal is LOS-blocked and reports four sectors. Acoustic is omnidirectional, and walls attenuate it rather than block it.
- Investigation triggers on thermal ≥ 0.32, or on thermal ≥ 0.16 together with acoustic ≥ 0.20.
- Peer heat reports steer goal ranking when the reported thermal is ≥ 0.35.
- Confirmation follows the Step 4 controller test configuration: `auto_confirm_victims = false`, `investigate_confirms_victims = true`.
- The "Sensor noise" toggle off sets noise, false-positive rates and odometry drift to 0 and detection probability to 1.

## Autonomy restrictions

An autonomous robot's brain (`AgentBrain.decide`) receives only a `LocalView`:

- name, id, type and its own cell;
- its odometry pose;
- its private belief map;
- its rubble capability and battery fraction;
- its own thermal and acoustic readings;
- the latest unexpired messages actually delivered to its inbox;
- `adjacentRobots`: the 4-neighbour cells occupied by teammates (short-range proximity sensing, the only input the action mask needs);
- the step counter.

It never receives the truth grid, the survivor list, other robots' states, or any shared
assignment structure. Goal deconfliction uses only claimed goals in delivered messages: a lower
name wins an identical claim, and candidates within 3 cells of a peer claim are filtered out.
Branch ownership uses rendezvous hashing over the robots it has actually heard from.

The truth map is used only by:

- physics (`applyMovements`, the wall checks in `safetyFilter`);
- sensor emulation (`Vision.ts`, `SensorModel.ts`);
- the radio channel model (walls between robots);
- rendering;
- offline statistics (coverage);
- the Debug Only truth overlay.

Tests enforce this:

- `controller.test.ts` checks that the controller source never references survivor or world data and that brains hold only `localGoal`.
- `controller.test.ts` also mirrors upstream `test_controller_never_selects_a_masked_policy_action`: at 30% loss, no chosen frontier slot ever steps into a teammate's cell.
- `autonomy.test.ts` moves the hidden survivors in one of two otherwise identical worlds and checks that the robots' trajectories stay identical.

## Known intentional browser simplifications and deviations

1. **Random numbers.** The browser uses a seeded sfc32 generator instead of numpy PCG64. Runs are deterministic per seed and command log, but they are not bit-identical to Python runs on the same seed.
2. **Rendezvous hash.** The browser uses FNV-1a with an avalanche step instead of blake2s. The ownership principle is unchanged (coarse 8×8 keys, highest score wins, minimal reassignment), but specific owners differ from Python.
3. **Frontier sampling.** Only the multi-sample frontier branch (`frontier_samples_per_cluster = 5`, as used by the Step 4 controller tests and audit) is ported. The frozen Step 2 single-sample branch is omitted.
4. **Topological graphs.** The NetworkX topological graphs (`mapping/topology.py`) are not ported. The Python controller updates them for artifacts but never uses them to decide.
5. **Collision shield additions:**
   - The shield also cancels single steps into impassable cells. Autonomous A* never plans these; the check protects manual commands from registering physics collisions.
   - **Behavioural deviation:** the yield/convoy rule no longer pushes a peer that is already moving perpendicular to the pusher. In the browser maps, pushing such a peer produced a two-robot livelock at a corridor mouth (each robot's priority turn shoved the other back). Head-on and holding peers are still pushed as in Python. Same-cell claims, swap rejection and convoy advancement are unchanged. `collision.test.ts` covers both behaviours.
6. **Scenarios:**
   - The browser generates its own presets (Collapsed Office, Mine Tunnel, Earthquake Apartment, Random Irregular, Validation Demo) on 28–56-cell maps instead of the Python layouts.
   - Survivor count defaults to 2–4 (Python: 1–4). Minimum path distance from spawn is 8 cells (18 in the demo) and minimum separation is 4 cells.
   - Mission steps and battery scale with map area relative to 32×32, in the spirit of the Step 2.5 area scaling.
7. **Byte estimate.** Message size is the JSON length of the camelCase envelope, so bandwidth accounting differs numerically from Python's.
8. **Logging.** Range and wall drops are counted in metrics but not written to the per-packet log, which would otherwise be flooded with one entry per distant pair per tick.
9. **Manual and Mixed modes** are browser additions:
   - Manual intents come from operator steps or a waypoint. The waypoint path is planned on the robot's own belief, treating unknown cells as passable.
   - Steps into cells the robot knows are walls are refused.
   - Every manual move passes through the same `safetyFilter` and `applyMovements` as autonomous moves.
   - A manual robot broadcasts its waypoint as its claimed goal and sends no frontier list.
   - It confirms survivors only when the operator presses Scan.
10. **Telemetry.** Plain-language events are throttled per robot and per event type. "Single file" convoy messages fire when adjacent robots both advance through narrow cells in the same tick. This affects only the feed, not the simulation.
11. **Time.** One tick represents one second of mission time. The UI runs 4 ticks per second at 1× and interpolates rendering between ticks without changing simulation state.
12. **Drones** keep the Python 2D traversal rules: they never cross walls and pay a cost of 1 on rubble. Altitude, bobbing, searchlights and rotor animation are visual only.

## Future: learned policy slot

A PPO/ONNX policy could be added as another `Decision` producer behind the same `LocalView`
interface: build the versioned observation from `LocalView` (the frozen 129-value Step 3
contract, or upstream's 229-value `gpu-v1` contract in `artifacts/policy_contract_gpu_v1.json`,
whose per-peer features come only from delivered messages), run it with `onnxruntime-web`, and
apply the same seven-action mask. It would sit beside `AgentBrain` without touching the engine,
network or safety layers. No such mode exists today, and the UI makes no claim to one.
