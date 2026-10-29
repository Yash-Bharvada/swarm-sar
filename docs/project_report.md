# Swarm SAR project report

Status reviewed on **29 October 2026** against the [exact Problem Statement 5](problem_statement.md). This report distinguishes implemented functionality, measured simulation results and work still pending. It supersedes the earlier conclusion that meeting the internal baseline-only blueprint proves fulfillment of the entire problem statement.

## Assessment against the actual challenge

The project has a working heterogeneous swarm simulator, a cooperative PPO training framework, peer communication, a browser demonstration and a separate ROS 2/Gazebo physics workspace. The **MARL requirement is central**: the browser's frontier heuristic alone does not fulfill it. A GPU BC/PPO experiment and paired development evaluation now have a verified checkpoint handoff. The local Python-to-3D-browser PPO integration is now verified; ROS learned-policy integration and final testing are still needed before claiming the system meets the challenge end to end.

| Problem statement capability | Implemented evidence | Remaining boundary |
|---|---|---|
| Heterogeneous drones and rovers | Separate rover/drone policies, sensing and traversal parameters; default grid/browser fleet is two of each | Grid drones have visual altitude but 2D movement. ROS physics demo is a separate execution path; its default is two drones plus one rover, with a four-agent exploration profile available. |
| Decentralized cooperative MARL | Python PPO with two type-shared policies, private observations, team reward, recurrent GPU-v1 support, behavior-cloning warm start and checkpoint evaluation | PPO mode renders the actual Python checkpoint-driven mission; inference runs in Python, not JavaScript. The selected 753664-step GPU policy has development evidence; final-test seeds remain sealed. Goal planning is decentralized; simulator collision shielding uses privileged occupancy information. |
| Unknown GPS-denied exploration | Private occupancy beliefs, local scans, frontier choices, A*, drifting odometry and common-entry alignment | Exact own-cell planning/common-grid registration remain idealized. This is not validated collaborative SLAM or unknown-start alignment. |
| Thermal/acoustic survivor mapping | Seeded noisy thermal sectors and acoustic cues; evidence fusion and close confirmation | Synthetic sensor models, not real thermal images, microphones or perception accuracy measurements. “Saved” in the UI means location confirmed; evacuation is absent. |
| Peer-to-peer topological sharing | Python per-agent topology and graph/message information, goal claims, evidence, range/loss/delay/expiry/partition/recovery behavior | Browser transport shares occupancy deltas and evidence, not a full learned graph communication system. NetworkX is not a GNN. Physical radio behavior is unvalidated. |
| Efficiency and scalability | Existing baseline/scalability cohorts, fixed action/observation interfaces, variable robot counts and reproducible evaluation tooling | The browser stress sample does not establish a communication speedup. Learned efficiency and generalization must be evaluated against paired baselines, particularly maze/tunnel and larger-team cohorts. |
| Real-world applicability | ROS 2/Gazebo packages, simulated sensor streams, models, bridge/controller launch files and recorded Ubuntu physics evidence | Learned-policy transfer, hardware sensor calibration, independent deployed collision avoidance and field trials are not established. ROS runtime was not rerun on this Mac. |
| GNN, ROS 2/Gazebo/Isaac and collaborative SLAM hints | ROS 2/Gazebo workspace exists | GNN and full collaborative SLAM are not implemented. The statement lists these as hints; do not present graphs or common-frame map union as either capability. |

## Completed browser work from this conversation

- Bright, readable terrain and a compact interface with panels opened on demand; dark coverage mask and vignette removed.
- Level, north-up default map framing; wheel zoom anchors to the pointed area, and button/keyboard zoom uses the last indicated world point.
- Distinct rover/drone models, smooth turning and movement, stable pause/resume interpolation.
- Human survivor figures, a finite one-time confetti burst and persistent saved flags after actual confirmation. Amber viewer beacons reveal unconfirmed positions without entering robot observations. Each discovery pauses the swarm, frames the survivor from the front, announces “Survivor found” and shows seeded fictional dialogue. Continue restores the overview and resumes; simultaneous discoveries queue and the final story leads to the report. Confirmed people have compact name/chat pills and can be tapped to revisit their story without restarting paused/completed missions. Pills hide during conversations; the dialogue pool contains 24 seeded humorous messages.
- **Survivor authoring before launch:** exact count up to the map's eligible capacity, randomize, clear/automatic placement, and click-to-add/remove. No small arbitrary cap: one survivor per reachable walkable tile outside staging. Invalid placement is rejected. Editor markers become amber viewer beacons on leaving the editor; authored coordinates remain outside controller observations. Reset retains the layout; changing terrain restores defaults.
- **Persistent focus:** Focus camera follows that robot as it moves. Selecting another robot transfers focus; deselection or explicit camera manipulation releases it.
- **Watch maze:** hide the interface, labels, selection markers and diagnostic overlays while the simulation and focus continue. H, Esc or Show interface restores the controls and retained layer settings.
- **Soundscape:** optional continuous ambient music, stereo rover/drone loops, distinct focus cues, survivor/mission feedback, restrained warnings and UI effects. M enables/mutes sound; independent channel sliders remember levels. Audio stays outside deterministic sensing, planning and training.

Custom survivor counts do not increase batteries or mission time. Large layouts can take longer, consume more memory/rendering work, or end before every survivor is found. These authoring controls do not change the Python training distribution, sensor contract or Step 4 network protocol.

Fleet/menu refinement adds rotating rover/drone previews using the actual world models, a larger selected-unit turntable, cream/sage panels, rounded disclosure sections and subtle control animations. Previews share one additional renderer for up to ten robots and release it when Fleet closes; reduced-motion preferences disable rotation. [Fleet browser checks](browser_fleet_validation.json) verify visible animation, selection/focus, renderer cleanup, ten-unit scrolling and mobile layout. The production build and 127 tests pass; Python/training sources remain unchanged.

## Validation and result provenance

The latest local checks passed:

- Production frontend build and **137 frontend tests across 16 files**, including audio routing, discovery queues, paused-state protection, stable fictional dialogue and an identical final engine state with/without encounter pauses.
- **160 Python tests passed, 2 ROS/xacro-dependent tests skipped**, with two PettingZoo deprecation warnings.
- **30 frozen baseline file hashes verified** and GPU-v1 policy contract verified: `c5dff01368e1bb3a77112884c5d545457830097b11aefe54e0d412fc874c57c5`.
- Audited GPU training source manifest verified: **94 files**, manifest SHA-256 `554f1bc621d0b2144113e75a94fa6668ef73e02f1ce7ee2d308637b14ab920ef`. This UI/report pass leaves those training sources and the expert dataset unchanged.
- GPU pipeline `--plan` succeeds without starting training. The supplied A5000 handoff now records GPU execution; local review verified archive and checkpoint provenance hashes rather than rerunning CUDA.

Browser interaction evidence is recorded in [browser_controls_validation.json](browser_controls_validation.json). It covers count 100, real click placement/removal, camera stability during editing, moving-robot focus, clean viewing and mobile restoration. The earlier [200-mission browser audit](browser_swarm_audit.json) found **563/564 survivors**, with **199/200 complete missions** and zero **post-shield** collisions. It used 50 distinct layouts under four network conditions. The one failure depleted the fleet with one survivor remaining at 30% loss; these are bounded synthetic results, not field accuracy or an all-missions guarantee.

For trained-model evidence, [GPU architecture review](gpu_architecture_review.md) reports the corrected CPU diagnostic BC policy at **74.82% mean cohort recall** versus **87.13%** for the policy-compatible expert over 72 development missions. Those are historical CPU diagnostic results, distinct from the GPU PPO handoff described below. The older Step 3 PPO checkpoint and stronger frontier comparisons have their own run identities in [the readiness audit](hackathon_readiness_audit.md).

Audio browser evidence is recorded in [browser_audio_validation.json](browser_audio_validation.json). Chrome checks cover explicit startup, independent volumes, mute, rover/drone focus, autonomous survivor and completion cues, reset without replay, clean viewing, mobile layout and unchanged simulation state. A full music progression remained audible across 155 samples with at most 18 active tones; tab suspension/resumption also passed. These checks establish playback behavior, not subjective listening quality or certification across browsers.

Discovery UI evidence is recorded in [browser_survivor_validation.json](browser_survivor_validation.json): three real autonomous discoveries each received a camera/story pause, tap-to-revisit preserved the story, Continue restored the overview, and completed-mission revisits, mobile framing and clean viewing passed. Explored-map tiles now use crisp mint versus sand; generic clicks use a quieter, lower pitched sound. Python/training code remains unchanged.

Zoom refinement: wheel input now uses one cursor-anchored easing path, normalizes wheel units, preserves world scale when drawers resize, and bounds animation progress after stalled frames. [Browser zoom checks](browser_zoom_validation.json) cover monotonic zoom, cursor anchoring, reversal and drawer stability. Survivor transition browser checks were rerun.

## GPU phase and remaining work

The GPU experiment ran on 29 October 2026 using audited source commit
`92121ce81ac44c0feb7fd43dcccfdfa7bec3dc05`. The verified handoff is stored in
[artifacts/trained/ppo_754k](../artifacts/trained/ppo_754k/README.md). The selected
753664-step checkpoint has tree SHA-256
`23696e6cf3b0821b6c01235a3911cb5cb87d0707589efce6ec43cb58b5340040`.
Its review reports 89.29% fixed-development mean cohort recall, 88.22% shadow
mean cohort recall and 88.80% combined mean cohort recall. The paired expert
scores are 87.43% fixed and 87.13% combined. These small development samples,
used for checkpoint selection, do not establish statistical superiority or
real-world reliability. Final-test seeds remain sealed.

The default 20-runner production configuration failed Ray batch validation.
The runtime override to 16 runners preserves the model/observation contract
and is recorded in the effective training definition; the audited source tag
and configuration files were not rewritten. The pilot completed 262144 steps;
continuation reached 1015808 steps and paused on worst-cohort recall/coverage.
The 753664-step checkpoint is selected instead of the final checkpoint.

The selected model found 5/18 maze survivors versus the expert's 4/18, but
explored only 19.15% versus 33.66%. Tunnel results were 15/21 versus 13/21.
Both comparisons use eight development episodes and carry substantial
uncertainty. Battery exhaustion and poor large-maze exploration remain known
limitations. Zero recorded collisions are post-shield outcomes, not proof of
learned collision avoidance. No communication benefit has been established.

Next milestones:

1. Completed: preserve the selected handoff and reproduce one checkpoint-driven Python mission. [Demo instructions](ppo_demo.md), [CPU inference evidence](ppo_demo_validation.json) and a [recorded mission GIF](media/ppo_754k_seed10000.gif) are available. Seed 10000 matched its recorded review outcome: 4/4 survivors in 94 steps, 90.48% coverage and zero invalid actions/post-shield collisions. This is one development example, not additional benchmark or field validation.
2. Completed locally: the [PPO-to-browser adapter](ppo_frontend_integration.md) reproduces the Python mission through the 3D frontend. [Browser checks](browser_ppo_validation.json) cover real snapshots, pause/discovery, reset, failure without fallback and mobile options. ROS learned-policy execution remains pending.
3. Run a versioned maze curriculum experiment only after keeping this candidate
   as a fallback. Retain the original batteries, budgets and held-out definitions.
4. Confirm candidate performance across additional training seeds and freeze
   model selection before an explicitly acknowledged sealed final evaluation.

The isolated `gpu-training` branch and immutable audited release tag remain
unchanged. Refer to [GPU_TRANSFER_CHECKLIST.md](GPU_TRANSFER_CHECKLIST.md)
for the original release workflow; it does not automatically resume an aborted
pipeline or incorporate the 16-runner override.

## Sensor decision before GPU testing

Both grid robot types already have occupancy sensing, directional thermal evidence, acoustic evidence, odometry/uncertainty and battery telemetry. Rover/drone radii are respectively **4/7 cells for occupancy, 6/8 for thermal, 10/12 for acoustic**, with confirmation radius **2/2**. Step 5 additionally has separate simulated LiDAR/IMU/camera/range streams; they are not automatically PPO inputs.

**Keep the current training sensor interface for this GPU phase.** The challenge explicitly calls for thermal and acoustic sensing, which are already present in the simulation. Extra modalities are not a substitute for learned-policy validation. A new sensor does not require rebuilding all of Step 4: preserve the baseline, implement an adapter/fusion path, version any changed observations or message schema, and rerun affected sensing/autonomy/network and mission tests. Input dimensions or semantics changing requires a compatible model and retraining/fine-tuning/evaluation; even unchanged dimensions can create a distribution shift. See [sensor_extension_plan.md](sensor_extension_plan.md) for the full impact matrix.

## Branch delivery

This completion is intended to leave `main` and `rashiyaom` at the same reviewed commit containing these controls and reports. Branch spelling in the repository is **`rashiyaom`**. The GPU-only branch and all existing audited training tags are retained. Historical evidence remains labelled by its original run rather than overwritten by this status report.

## Yash PR #2 integration review — 29 October 2026

Integrated the ROS/Gazebo axes and survivor-encounter update from Yash Bharvada
(PR #2, source commit `b87c246`). It adds five human visual models, shared world-file
survivor coordinates, detection-only green RViz dots, flat batched occupancy tiles,
and distinct drone encounter routes. Vehicle dynamics and the rover circuit remain
unchanged. Submitted logs record three vehicle confirmations; these demonstrate
scripted encounters, not exhaustive autonomous search or learned-policy deployment.

Integration fixes select the active profile's scan topic for RViz readiness (including
drone-only launches), bound readiness to 120 wall-clock seconds, and place the
subscribe-only probe at `ros2_ws/tools/ros2_encounter_probe.py` to preserve the audited
GPU source manifest. Validation: 154 local Python tests passed, two ROS/xacro tests
skipped; all 94 GPU source hashes verified unchanged. ROS/Gazebo executables are
unavailable on this Mac, so live ROS package tests and physics were not rerun here.
Existing frontend work, immutable training tags and the server's running training
checkout are unaffected. No PR CI checks were configured at review time.

## Local trained-policy frontend integration

The selected 754k policy now drives the Python simulation behind an optional
3D browser mode, with an explicit Heuristic/PPO selector. Python owns the full
world, sensing, peer transport and recurrent policy state; browser ticks and
manual commands cannot advance a PPO mission. Development seed 10000 matches
its recorded review: 4/4 survivors in 94 steps and 90.48% coverage. This verifies
runtime integration, not a new benchmark. Camera, audio and discovery-story
pauses do not change the Python step sequence. Reset creates fresh recurrent
state. Connection loss pauses rather than silently falling back to heuristics.

The localhost service verifies the checkpoint/provenance hashes and restores
both actor modules on CPU without starting training/Ray workers. Browser tests
compare actual geometry, positions, batteries and coverage with Python and
exercise reset, connection failure, new map/team/radio options and heuristic
restoration. The final checks passed: production build, 137 frontend tests,
160 Python tests (two ROS-dependent skips), and the unchanged 94-file audited
GPU manifest. Per-packet drop/reconnect histories, full route export,
production deployment and ROS policy execution remain outside this adapter.
