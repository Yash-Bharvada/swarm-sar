**Swarm SAR: overnight delivery plan for the presentation**

Working window: Friday 30 October, 7 PM IST, through Saturday 31 October,
8 AM IST. Presentation: approximately 2 PM IST on 31 October. Finals:
1 November. A GPU is available overnight; live ROS work requires the Linux
ROS/Gazebo host. This plan defines intended work and acceptance checks, not
features already implemented or results already achieved.

The large-map roadmap remains the longer-term plan. Tonight's release should
add a useful localization component, expose real peer cooperation, preserve
the verified learned demo, and attempt one bounded model improvement. New
frameworks, new observation dimensions and a complete collaborative-SLAM/GNN
rewrite are outside the critical path.

**Recorded ROS learned-run evidence — clarification**

The supplied `docs/media/simulation-screenshots/run.log` records `ppo_agent`
processes, loaded rover/drone PPO actors, repeated policy decisions, live
occupancy maps and peer-network activity during a Gazebo/RViz session. It is
incorrect to describe all existing ROS work as waypoint-only. The current
checked-in launch defaults to waypoint control, and the matching `ppo_agent`
implementation is absent from the inspected local branches and remote-tracking
refs. Its actor hashes differ from the selected grid-policy handoff. Therefore,
first recover and reproduce the recorded host checkout, launch command and
model provenance. Do not rebuild an adapter until that existing work is audited.
The recorded learned run does not by itself establish SLAM or estimated-pose
localization: those require separate verification.

**Current priority update:** The active focus is now SLAM integration and
stronger agent-to-agent communication. Use
[the focused SLAM/communication plan](slam_communication_integration_plan.md)
for implementation order and visualization. The GPU-training lane below is
optional and must not delay that focused release.

**The three release deliverables**

1. A verified learned browser mission with private maps, sensor evidence,
   communication state, clear controller identity and a reproducible report.
2. A rover SLAM integration using actual simulated laser scans and estimated
   odometry, with an estimated map and trajectory in RViz, plus at least one
   downstream consumer of that map if time permits.
3. A bounded checkpoint experiment with paired development evaluation. A
   candidate replaces the selected 753,664-step model only after verification
   and successful integration; keeping the existing candidate is valid.

Show a distinction between the learned grid execution path and the physical
ROS path until the learned ROS adapter is actually validated. First recover and verify the recorded learned ROS host version. An estimated-localization
upgrade to that version is the highest-value stretch result. Single-rover SLAM is a
valid integration milestone, not a claim of collaborative SLAM or full learned
SLAM-driven search.

**Suggested human workstreams**

Agree ownership according to availability and skills. Suggested assignments
are Om on learning/evaluation, Yash on the ROS host/SLAM, Purva on planning and
peer evidence, and Pankti on UI, evidence and the presentation. These are
proposed overnight responsibilities, not statements of past authorship.

Keep one person responsible for the release decision so checkpoints, configs
and screenshots do not describe different versions. Each lane must leave
commands and artifacts another teammate can operate.

**Schedule and decision points**

| IST | ROS/localization lane | Learning/diagnosis lane | Peer/UI/evidence lane |
|---|---|---|---|
| 19:00–19:45 | Reproduce existing physics demo; inspect packages, scans and TF. | Verify selected checkpoint and baseline browser mission; confirm GPU runtime. | Record working demos, source/config identity and fallback commands. |
| 19:45–21:30 | Integrate single-rover SLAM in an optional profile. | Run small time/energy/stall diagnostics; measure rollout throughput. | Show actual private beliefs, received claims/evidence and network events. |
| 21:30–22:30 | Validate map growth and estimated-pose provenance; record a first successful run. | Prepare one compatible experiment and run a short GPU/checkpoint pilot. | Make one reproducible peer-delivery/partition demonstration; begin slides. |
| 22:30–03:30 | Connect SLAM output to topology/evidence; attempt learned adapter only after mapping works. | Run a maximum five-hour continuation if pilot qualifies; checkpoint and evaluate periodically. | Test critical flows, prepare scale results and real recordings. |
| 03:30–06:00 | Validate retained ROS integration; stop unresolved stretch work. | Stop training, verify artifacts and compare old/candidate on paired development cases. | Update evidence with exact results, prepare failure recovery and package demo. |
| 06:00–08:00 | Clean-terminal reruns and recorded fallback. | Final promotion/retention decision; verify browser uses exact selected weights. | Two full rehearsals, offline copies and release freeze. |
| 08:00–10:00 | No architecture changes. | No new training needed for the presentation. | Finish slides and operating runbook; check another teammate can launch. |
| 10:00–12:00 | Buffer for measured fixes only. | Preserve frozen candidate. | Rehearse answers and prepare equipment/travel. |
| 12:00–14:00 | Presentation preparation. | Do not depend on a new checkpoint arriving. | Use frozen live demo and labelled backups. |

If the start slips, shorten stretch work and training first; preserve evaluation,
recordings and rehearsal. The morning buffer is part of delivery, not spare
time for a framework migration.

**Rover SLAM: what the repository already provides**

The rover has `/rover_0/scan`, `/rover_0/wheel_odom`, a lidar frame and a robot
description. That is a useful starting point for SLAM Toolbox. Inspect the
installed ROS distribution and available package executables on the real host;
do not mix the older Jazzy notes with the recorded Lyrical host setup.

Useful read-only checks, after sourcing that host's ROS and workspace:

```bash
ros2 pkg executables slam_toolbox
ros2 topic hz /rover_0/scan
ros2 topic echo /rover_0/scan --once
ros2 topic echo /rover_0/wheel_odom --once
ros2 run tf2_tools view_frames
```

The important integration detail is transform ownership. The current launch
publishes a static `map -> rover_0/odom` transform; SLAM must own its estimated
map-to-odometry relation in the new profile. Do not let two publishers drive
the same transform. The rover description also publishes world-pose odometry
and its TF, while the wheel drive has a separate wheel TF topic. Establish one
consistent `map -> odom -> base -> lidar` chain for the SLAM experiment.

Prefer wheel/estimated odometry for mapping validation. If using simulator
world odometry during an initial wiring test, label it as such and do not
present that test as drift-correcting field localization. Keep other demo
profiles unchanged. An isolated SLAM TF tree is another possible staging
strategy, but frame remapping must be consistent for scan, base and odometry.

Use a compatible released SLAM Toolbox package when available. Configure the
actual scan topic, frames, simulation time, range and resolution; the upstream
defaults are examples rather than the correct parameters for our rover.
Start with one rover. Do not spend the first hours getting every drone to run
2D SLAM; their laser planes and altitude need separate consideration.

Acceptance by the first gate:

- Maps grow from scans as the rover moves; no truth map is loaded into SLAM.
- The TF tree has a single authority for each dynamic relation.
- Scans align reasonably with the estimated occupancy map over a repeated path.
- Save the occupancy map and, when supported, the pose graph.
- Log input odometry source and use ground truth only as a separate evaluation
  reference for localization error.
- Observe and record an actual loop closure if claiming one; enabling the
  configuration is not proof that a loop closure occurred.

If SLAM still cannot consume stable scans/TF after approximately two hours,
stop feature expansion, preserve the diagnostic output and retain the existing
physics demonstration. If it works, consume its map in a topology or semantic
evidence adapter before adding another visual display. Keep estimated survivor
positions in the correct timestamped frame and do not substitute world truth.

Sources:
[SLAM Toolbox](https://github.com/SteveMacenski/slam_toolbox),
[configuration example](https://github.com/SteveMacenski/slam_toolbox/blob/ros2/config/mapper_params_online_async.yaml),
[Nav2 SLAM tutorial](https://docs.nav2.org/rolling/tutorials/general_tutorials/navigation2_with_slam/navigation2_with_slam/).

**Collaborative mapping: a useful optional route, with an availability gate**

The inspected current upstream SLAM Toolbox branch documents a decentralized
multi-robot node that exchanges localized scans. Check whether the installed
distribution actually supplies it before planning around it. The documented
setup assumes known starting positions and a common reference odometry frame;
it does not remove unknown-start registration requirements.

Only attempt a two-rover version after the single-rover path is stable. Do not
rebuild or replace the ROS distribution to chase an upstream feature tonight.
Its direct DDS scan exchange is also not automatically subject to our lossy
radio emulator. If that traffic bypasses the emulator, label the channel and
scope separately rather than reporting radio-resilient collaborative SLAM.

Source: [upstream multi-robot SLAM documentation](https://github.com/SteveMacenski/slam_toolbox/blob/ros2/docs/decentralized_multi_robot_slam.md).

**Make peer cooperation visible and causal**

Use real message delivery and recipient belief changes, not an animated line
that merely means robots are within range. Prepare a short repeatable example:

1. Robot A discovers a region or evidence.
2. A packet advertises the relevant information with sender, sequence and age.
3. Robot B receives it and updates its private belief or goal claim.
4. With a configured partition, B temporarily lacks that information.
5. After reconnection, a valid packet/snapshot restores some missing knowledge.

Use the existing Python/TypeScript network paths where validated. The backend
does not expose every per-packet drop/reconnect history; use actual supported
metrics or add a narrowly tested event export. Do not fill missing telemetry
with fabricated event histories.

For topology, the Python NetworkX graphs already provide a starting point.
Display the graph from a real episode and explain which data traversed the
peer channel. If adding a ROS SLAM topology adapter, extract from the estimated
occupancy map, carry frame/uncertainty metadata, and demonstrate receiver-side
use. A graph drawn centrally from truth is a debug visualization, not exchanged
robot knowledge.

Avoid calling NetworkX a GNN. Tonight a clear useful graph/map exchange is
preferable to an untrained graph neural network added for the acronym.

**The GPU experiment**

Use one compatible experiment. Retain the 229-value observation, seven-action
interface, recurrent structure and type-shared policies tonight so the selected
weights remain a usable warm start. Do not start BC and PPO from scratch merely
because the full pipeline exists; the current pipeline is a longer sequence
that may redo work already completed.

By 22:30, choose between:

- Continue from the selected checkpoint with a diagnosis-supported curriculum
  adjustment, after proving that the effective environment actually changed.
- Keep the selected model and use compute for better paired evaluation if the
  diagnosis does not support more training.

Useful diagnostics are original versus changed time/energy budgets, feasible
frontier counts, voluntary hold versus shield intervention, rejected map merges
and route revisits. Eight or so development cases can direct engineering;
they cannot establish broad reliability. Keep original benchmark conditions
and custom 64-map conditions separate.

If targeting larger mazes, the current code caps randomized PPO maze sizes at
32. Editing `world_sizes` to include 64 does not remove that cap. Implement a
small explicit experiment setting and record actual generated layout/size/team
samples before starting the long run. An input-compatible curriculum change
still creates new evaluation conditions and new artifact provenance.

Pilot requirements:

- CUDA is used by both optimizing policies and parameters remain finite.
- Rollout workers produce varied intended training cases.
- A saved checkpoint restores with matching hashes and individual recurrent
  state; a short mission can execute after restore.
- Throughput is measured, and no optimizer-only loss plot is used as a rescue
  performance claim.
- The resume path uses the intended config and a target above the restored
  lifetime step count. The CLI target is not necessarily an additional-step
  budget.

The existing trainer supports `--resume`, `--config`, `--output`,
`--max-seconds`, `--initial-evaluation`, and `--reference-evaluation`.
Its deadline is checked at iteration boundaries, so use an outer watchdog and
rolling verified checkpoints too. Choose the exact command only after the
effective config/reference report is prepared; do not paste an old server
checkpoint path from metadata. Resume the selected 753,664 candidate, not the
later checkpoint that triggered quality gates.

Allow roughly 30–60 minutes for the pilot, up to five hours for a qualified
continuation and at least two hours afterward for evaluation and integration.
Checkpoint frequency should be short enough that interruption does not lose
the entire night. Stop on numerical failures, invalid actions or regression;
do not weaken existing gates to produce a newer model.

Evaluate the baseline and candidate on matched development cases and identical
budgets, including small maps and the previously weak cases. Add new 64-map
cases only as a separately defined development cohort. Ideally retain the full
original nine-cohort evaluation for promotion; if time permits only a subset,
state that limitation and prefer the verified baseline for the main demo.

**New checkpoint serving is a real task**

The current `backend/ppo_service.py` verifies against the selected 754k review
and hard-codes that candidate's provenance. Merely supplying a different
`--checkpoint` will fail its hash check. If a new model earns promotion, add
a tested versioned artifact manifest/report path while keeping the default
754k bundle unchanged. Preserve contract, tree and parameter verification;
do not disable those checks to make a candidate load.

Repeat reset, pause, discovery continuation, connection-failure and controller
switching checks on the actual served candidate. Make sure logs, UI and slides
identify the model being used. If promotion cannot be completed before freeze,
show the candidate's evaluated offline rollout separately.

**Recover the existing learned ROS path before considering a new adapter**

The recorded host run already logs PPO actors and decisions. Recover its source,
exact launch and checkpoint before implementing another adapter. The following
checks apply to that recovered implementation; a new adapter is a fallback if
the source cannot be recovered.

An adapter must reconstruct the trained sensor and frontier semantics from
estimated ROS data, keep per-agent recurrent state, transform goals correctly
and execute through an appropriate local planner. Matching vector length alone
does not establish a valid adapter. Start in shadow mode, comparing proposed
choices with actual maps, before giving it motion authority.

Only promote to learned ROS execution after successful fresh launches and
repeatable behavior on a small supplied scenario. There must be exactly one
active velocity-command authority per robot. Do not leave a waypoint node and
Nav2/learned controller simultaneously publishing competing commands.

Adding Nav2 is optional tonight: use it if installed and the rover's required
frames/sensors are already sound. Otherwise its bringup, costmap and controller
tuning can consume the remaining window. Preserve a safe local path follower
and clearly state the current control source.

**The demo and presentation package**

Aim for a 3–4 minute live sequence with short labelled backup recordings:

1. Introduce the unknown disaster site and the different rover/drone capabilities.
2. Run the actual saved PPO browser mission, showing local information and
   survivor evidence rather than only the global scene.
3. Show one causal peer-information transfer and a bounded communication failure.
4. Show rover SLAM/RViz with its input odometry source stated, if validated.
5. Present the paired results, a difficult case and the measured next step.

If learned ROS execution is validated, combine steps 2–4 into that actual
connected path. Otherwise use an architecture slide with separate runtime
lanes; do not imply the windows are the same executed mission.

The results slide should distinguish original evaluation, tonight's experiment
and custom-budget stress tests. A 64×64 success is one demonstration until a
suite supports a broader claim. Do not advertise arbitrary 128-map reliability.
Use a frozen candidate before final evaluation; avoid repeatedly opening sealed
test seeds during the overnight selection process.

Explain open-source contribution in terms of contracts: PyTorch/RLlib train the
policy; PettingZoo defines the environment; ROS 2 connects components; Gazebo
simulates physical models; SLAM Toolbox estimates map/pose if integrated;
NetworkX represents topology. Our work is the heterogeneous SAR environment,
evidence and radio models, policies/training/evaluation, interfaces and operator
experience. Credit upstream components and show our own actual integration.

Freeze deliverables by 08:00:

- Exact source revision, checkpoint/config identities and one-command runbook.
- Verified launch/reset sequences and a stop/recovery procedure.
- Short real recordings and screenshots stored locally on two machines.
- Evaluation table with denominators, conditions and limitations.
- A feature/claim table distinguishing working, measured and proposed items.
- A five-minute pitch and answers about decentralization, SLAM, PPO, simulator
  truth, collision shielding and why the robots cooperate.

Do not use the last hour before presenting to install packages, migrate models
or change the scenario. After the first round, use judge feedback to choose
one finals improvement: complete a nearly working learned ROS adapter, extend
validated SLAM/peer use, or demonstrate a measured large-map policy improvement.
Preserve tomorrow's working release while doing that work.
