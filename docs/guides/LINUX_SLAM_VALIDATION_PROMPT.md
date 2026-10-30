# Prompt for the Linux Codex agent

Copy the entire prompt below the divider into the agent running on the existing ROS/Gazebo Linux machine. The primary delivery is now GitHub; no manual archive transfer is needed when GitHub is reachable.

- Repository: **https://github.com/rashiyaom/swarm-sar.git**
- Branch containing the implementation, frontend, fieldbook and this prompt: **`rashiyaom`**
- Browser link to this file: **https://github.com/rashiyaom/swarm-sar/blob/rashiyaom/docs/guides/LINUX_SLAM_VALIDATION_PROMPT.md**
- Do not assume `main`, `frontend`, `simulator_web`, `gpu-training` or a teammate's ROS branch contains these new changes. Fetch **`rashiyaom`**, record its actual fetched commit, and create an isolated Linux validation branch from that commit.

The fallback archive remains `artifacts/slam_linux_handoff.tar.gz`. It includes a baseline patch, new files, checksum manifest and local check evidence. The screenshot is a disconnected UI preview and the browser contract report uses synthetic fixtures; neither is live SLAM evidence. Do not reapply its patch over a Git checkout that already contains the integration.

---

You are working on **https://github.com/rashiyaom/swarm-sar.git**, source branch **`rashiyaom`**. Fetch that branch explicitly. Read this entire prompt, including the detailed commands and acceptance table after the ten tasks, before making changes. Work in a fresh clone or an isolated worktree so the existing Linux PPO implementation and working physical demo remain recoverable. Record the fetched commit and the final tested commit in the validation report.

Implement the host integration and validate the Swarm SAR SLAM + communication changes end to end on this Linux machine. Work autonomously, fix failures and save evidence. Do not stop after a plan or static checks. The presentation is imminent; prioritize a working, honest two-rover diagnostic, then the actual PPO heterogeneous run.

CRITICAL: The Mac checkout does NOT contain the Linux ROS PPO implementation that produced our supplied run log. `docs/media/simulation-screenshots/run.log` records PPO actors loading and decisions. All fetched refs inspected contained only waypoint/heuristic ROS nodes. The missing PPO variant may exist as uncommitted source, another checkout, an installed executable or on another team member's host. Find it before applying any potentially overlapping changes. A waypoint demo is not acceptable evidence of PPO. Do not silently fall back, invent an actor-loading log or change model hashes to match a story.

1. Inspect `AGENTS.md`, git status/branch/remotes, the installed ROS distro and Gazebo version, current workspace(s), package prefixes and running ROS nodes/processes. Inventory and back up local modified source/launch/setup files before merging. Locate `ppo_agent`, actual loaded actor paths and its source/entry point, including untracked files and installed console scripts. Inspect shell history/logs only narrowly for the missing project invocation; do not expose unrelated secrets. Preserve existing actor files, hashes, training manifests, custom Gazebo fixes and local PPO code. Report clearly if it cannot be recovered. Do not claim learned control is validated in that case; still finish all independent SLAM/radio work.

2. Read `docs/guides/slam_integration.md` completely. Review the new `slam_demo.launch.py`, `slam_agent.py`, `slam_support.py`, changed network bridge/Xacro and frontend ROS view. If given `artifacts/slam_linux_handoff.tar.gz`, extract into a staging directory; read `MANIFEST.json` and verify SHA-256 for each included file. The archive has `tracked.patch` plus `new/` files. Use `git apply --check` first. If the baseline differs, integrate each change manually or with a reviewed three-way merge; never overwrite the host's package `setup.py`, PPO controller, launch files or model assets wholesale. Preserve all existing console scripts and append `slam_agent`. Do not run `git reset --hard`, `git clean` or checkout over local changes. The archive is source integration material, not an instruction to blindly overlay a running workspace.

3. Use the host's already working ROS/Gazebo distro combination. Resolve the declared dependencies with rosdep (including slam_toolbox, tf2_ros, lifecycle_msgs, std_srvs, rosbridge_server); do not change distro or add Isaac Sim. Build with colcon, source the built workspace, and run the Python/physical-model tests and frontend build/tests. Fix API/launch/lifecycle/QoS discrepancies against the installed packages. Verify `map_name` actually yields `/<rover>/slam_map`, each SLAM lifecycle reaches active and both maps are independent. Upstream may default to absolute `/map`; do not leave both SLAM nodes publishing one map topic.

4. First launch `ros2 launch swarm_sar_gazebo slam_demo.launch.py scenario:=rovers controller:=waypoint rosbridge:=true`. This is explicitly a mapping diagnostic. The original launch remains available separately. Do not run two worlds/controllers on the same topics. Validate these exact TF authorities: static `map -> rover/map` for known starting positions; SLAM `rover/map -> rover/odom`; wheel `rover/odom -> rover/base_footprint`; robot_state_publisher for base/lidar. Rover world TF must be excluded. `/rover_0/ground_truth/odom` is evaluation/sensor-radio emulation only; canonical `/rover_0/odom` comes from estimated SLAM TF. Check all robots, not only rover_0. Ensure scans, wheel TF, scan timestamps, map names and scan matching work. Measure that estimated and truth pose agree initially without adding spawn offsets twice. Keep later drift visible; do not swap truth back in to make the map prettier.

5. Run `python3 simulation/ros2_ws/tools/slam_runtime_probe.py --seconds 120 --wall-timeout 600 --output artifacts/slam_runtime_run1.json` from the repo root with the ROS environment sourced. Inspect the report; fix failures rather than editing thresholds or faking results. Require repeated scan-built maps with meaningful known cells, rover movement, expected TF, fresh estimated poses and actual receiver-applied peer snapshots. Inspect map quality against Gazebo manually; add alignment/drift metrics if feasible. Verify unique TF ownership using node/publisher inspection, because the smoke probe alone cannot certify unique publishers. For loop closure, actually revisit a loop and inspect installed toolbox correction/graph evidence; an enabled parameter alone does not prove a closure occurred.

6. Validate failure behavior. The radio's two channels (`peer` and `slam_peer`) must share one modeled sender byte budget, range/loss/delay and partitions. No direct SLAM-to-SLAM map subscriber may bypass it. Observe queued, dropped, transport-delivered, receiver-buffered and receiver-applied events. Call `ros2 service call /swarm/network/isolate/rover_0 std_srvs/srv/SetBool '{data: true}'`. Hold for 15 simulation seconds. Confirm rover_0's own mapping/control continues, its received snapshot revision stops advancing, peer data ages and short-lived claims expire. Reconnect with `{data: false}` and measure time to a repaired/new complete snapshot. Verify packet loss, reorder/dedup, invalid-frame rejection and bounded queues. Never erase retained maps just for a visual effect. After a Gazebo clock rewind, stop/restart the whole SLAM launch; test that the adapter/network mark restart-required instead of using an old pose graph.

7. Recover/adapt the REAL PPO controller. Read its observation code and actuator interfaces before changing anything. It must consume estimated mission-frame pose, the receiver's belief map and delivered peer data without rebuilding its mapping input from simulator truth or automatically rasterizing raw scans over a SLAM belief. Use the `external_belief_map` and `accept_peer_map` conventions only if the actual host controller implements them; add equivalent functionality where needed. Preserve observation tensor dimensions, action masks, trained actor normalization and role handling. The ROS belief grid is 240×240 at 0.2 m; the trained search observation has its own geometry. Implement and test an explicit compatible crop/downsample/feature adapter if needed. Do not feed an arbitrary resized tensor to the actor. Read the existing host mapping between policy actions and Gazebo commands. Respect its semantics, and add a stale estimated-pose/scan stop. The adapter's estimated odometry has pose but no velocity/covariance; use wheel odometry for velocity if the PPO observation requires it. Do not interpret zero twist/unknown covariance as measured truth.

8. Stop the diagnostic, launch `scenario:=swarm controller:=ppo ppo_executable:=<actual executable>` with the real params. Verify model loads successfully, record actor paths/hash and actual learned decision logs, identify all cmd_vel publishers and prove exactly one active controller per robot. Trace the learned action -> physical command -> Gazebo motion -> scan/SLAM update -> next observation loop. The launcher refuses a missing executable but cannot prove its content; do that inspection. Drones retain simulator localization and noisy thermal/acoustic proxy sensing; label it honestly. Do not claim aerial or joint multi-robot SLAM.

9. Start the existing frontend and open `/?mode=ros`. Connect its native ROS bridge client to the actual ROS service. Check selected-agent local maps, cyan peer-only cells where peers have unique observations, estimated paths, frontier components, source/freshness labels, packet events and real isolation/reconnection buttons. Test disconnect/stale behavior: points must fade and freeze, no browser simulation should keep running in ROS mode. Test that unavailable isolation services show failure instead of cosmetic success. Check the physical Gazebo 3D scene and RViz robot/map overlays side by side. Preserve the original browser simulator at `/`. A loopback bridge can be tunnelled with `ssh -L 9090:127.0.0.1:9090 <user>@<host>` for the Mac frontend.

10. Complete three fresh launch runs and save reproducible evidence under `artifacts/slam_linux/`: probe JSON, commands/versions, node/topic/TF/controller ownership, actor identity and action trace, radio partition/recovery measurement, rosbag location, actual Gazebo/RViz/live-frontend screenshots and errors fixed. Preserve disk limits when recording. Write `docs/audits/slam_linux_validation.md` with a PASS/FAIL table for diagnostic SLAM, physical motion, estimated controller feedback, local/peer distinction, loss recovery, partition, frontend liveness, actual PPO execution, heterogeneous scenario and demonstrated loop closure. Mark unavailable/unproven items explicitly. Do not mark the whole task done based only on a frontend build or waypoint motion.

## Detailed execution instructions

### A. Access the correct branch without losing the host's PPO work

First identify any existing project checkout and the workspace used by the running or previously working ROS demo. Before changing its files, record its current branch, commit, remotes and modified/untracked files. Back up modified source and relevant untracked PPO/controller/launch/config files outside that checkout. Preserve both staged and unstaged changes; a Git branch name alone does not save uncommitted files. Keep backups local and avoid printing credentials or copying unrelated personal data.

For an existing checkout, use the following pattern **after** the inventory/backup. Replace the first directory with the actual discovered repository. `swarm-handoff` is an additional remote; do not change an existing `origin` that might point to a teammate's fork.

```bash
cd /absolute/path/to/existing/swarm-sar
SWARM_ORIGINAL_ROOT="$(git rev-parse --show-toplevel)"
git status --short
git branch --show-current
git rev-parse HEAD
git remote -v

# If this remote name already exists, inspect it first and verify the URL below.
# Reuse it only if it points to the intended repository; otherwise choose a new name.
if ! git remote get-url swarm-handoff >/dev/null 2>&1; then
  git remote add swarm-handoff https://github.com/rashiyaom/swarm-sar.git
fi
git remote get-url swarm-handoff
git fetch swarm-handoff refs/heads/rashiyaom
SWARM_HANDOFF_REVISION="$(git rev-parse FETCH_HEAD)"
git show -s --format=fuller "$SWARM_HANDOFF_REVISION"

SWARM_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
SWARM_TEST_ROOT="$(dirname "$SWARM_ORIGINAL_ROOT")/swarm-slam-validation-$SWARM_RUN_ID"
git worktree add -b "linux/slam-validation-$SWARM_RUN_ID" "$SWARM_TEST_ROOT" "$SWARM_HANDOFF_REVISION"
cd "$SWARM_TEST_ROOT"
git status --short
git rev-parse HEAD
```

If there is no repository checkout, clone into a new unused directory instead:

```bash
git clone --branch rashiyaom --single-branch https://github.com/rashiyaom/swarm-sar.git swarm-slam-validation
cd swarm-slam-validation
SWARM_TEST_ROOT="$(pwd)"
SWARM_HANDOFF_REVISION="$(git rev-parse HEAD)"
SWARM_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
git switch -c "linux/slam-validation-$SWARM_RUN_ID"
```

The new Linux branch is a safe working branch based on the fetched **`rashiyaom`** branch. Do not accidentally base it on `main`. If GitHub authentication is needed, use the machine's existing Git/SSH/gh credential configuration; never write access tokens into this repository or logs. If the remote already exists with a different URL, correct the command to use another remote name rather than silently fetching the wrong repository.

Check that all these files exist in the fetched revision before building:

```text
docs/guides/slam_integration.md
docs/audits/slam_local_validation.md
docs/audits/ros_branch_pr_audit.md
simulation/ros2_ws/src/swarm_sar_gazebo/launch/slam_demo.launch.py
simulation/ros2_ws/src/swarm_sar_gazebo/config/slam_rover.yaml
simulation/ros2_ws/src/swarm_sar_gazebo/config/slam_demo.rviz
simulation/ros2_ws/src/swarm_sar_control/swarm_sar_control/slam_agent.py
simulation/ros2_ws/src/swarm_sar_control/swarm_sar_control/slam_support.py
simulation/ros2_ws/tools/slam_runtime_probe.py
frontend/src/ros/RosMissionControl.tsx
frontend/tools/validate_ros_ui.py
guide-site/dist/index.html
```

Create `artifacts/slam_linux/<UTC-run-id>/` under the new checkout. Put the fetched commit, worktree path, original source checkout, tested branch, command logs, exit codes and environment inventory there. Use a fresh evidence directory for each attempt; do not overwrite failed-run evidence with a later success.

```bash
SWARM_EVIDENCE="$SWARM_TEST_ROOT/artifacts/slam_linux/$SWARM_RUN_ID"
mkdir -p "$SWARM_EVIDENCE"
git rev-parse HEAD > "$SWARM_EVIDENCE/source_commit.txt"
git branch --show-current > "$SWARM_EVIDENCE/working_branch.txt"
git status --short > "$SWARM_EVIDENCE/initial_status.txt"
```

Read existing `AGENTS.md` instructions in the relevant directories. Inspect `/opt/ros`, `/etc/os-release`, `ROS_DISTRO`, `ROS_DOMAIN_ID`, `RMW_IMPLEMENTATION`, Python version, `AMENT_PREFIX_PATH`, `COLCON_PREFIX_PATH`, `DISPLAY`, graphics support, disk space and Gazebo version. Run `bash simulation/scripts/ros2_preflight.sh` and save its output. Historical docs mention both Jazzy/Harmonic and Lyrical/Gazebo 10; detect the actual host rather than choosing one from the documentation.

### B. Recover the real learned ROS controller

Inspect the original workspace **before** sourcing the new overlay. `ros2 pkg prefix swarm_sar_control` and `ros2 pkg executables swarm_sar_control` identify the currently installed package and entry points. Record their outputs. Search narrowly within project roots and installed package directories for `ppo_agent`, `PPO actor loaded`, actor loading/inference calls, observation construction, policy action conversion and the launch command that produced the supplied log.

Useful source search pattern, with large/generated trees excluded:

```bash
rg -n --hidden --glob '!**/.git/**' --glob '!**/.venv*/**' \
  --glob '!**/node_modules/**' --glob '!**/build/**' --glob '!**/log/**' \
  --glob '!guide-site/dist/source/**' --glob '!**/*.pt' --glob '!**/*.npz' \
  'ppo_agent|PPO actor loaded|torch[.]load|load_state_dict|compute_single_action' \
  /actual/project/root /actual/other/relevant/checkout
```

Use real discovered paths, not the placeholders above. The fieldbook's `dist/source/*.txt` files are a historical reading snapshot, not executable ROS source; do not mistake a text copy for the active controller. Check source and installed console scripts separately; a script in `install/` may reference a different source tree or Python interpreter. Do not import or execute an unreviewed installed entry point just to identify it—inspect its text first.

Record a provenance table for the controller source, setup entry point, launch/config, observation adapter, actor/checkpoint, normalization and recurrent state handling. Include original file path, SHA-256, recovered destination and reason for every merged change. Copy/merge the needed source into the isolated checkout. Preserve all existing console scripts when adding `slam_agent`; do not copy the Mac `setup.py` over the host's PPO entries.

The repository's grid inference code and `simulation/scripts/demo_ppo.py` can help explain the policy contract. They are not proof that the missing physical ROS controller was recovered. If that controller is genuinely unavailable, finish the mapping/radio/frontend validation, mark learned physical control **BLOCKED**, and report exactly which missing files are needed. If you implement a new ROS policy adapter as a fallback, identify it as newly implemented, use the real checkpoint and full contract, and validate it separately; never label it as recovered historical code or use a heuristic behind a PPO name.

### C. Build and run the tests in environments compatible with ROS

Start a clean shell sourced with the host's chosen `/opt/ros/<detected-distro>/setup.bash`. Do not source the old project's `install/setup.bash` into the new test shell. Preserve the original shell/environment for recovery. Use the matching system Python for `rclpy` and generated ROS interfaces; an arbitrary training virtual environment can have a different Python ABI.

In the isolated checkout, run and log:

```bash
set -o pipefail
rosdep install --from-paths simulation/ros2_ws/src --ignore-src -r -y \
  2>&1 | tee "$SWARM_EVIDENCE/rosdep.txt"

cd simulation/ros2_ws
colcon build --symlink-install --event-handlers console_direct+ \
  2>&1 | tee "$SWARM_EVIDENCE/colcon_build.txt"
source install/setup.bash
colcon test --packages-select swarm_sar_control --event-handlers console_direct+ \
  2>&1 | tee "$SWARM_EVIDENCE/colcon_test.txt"
colcon test-result --verbose 2>&1 | tee "$SWARM_EVIDENCE/colcon_test_results.txt"
cd "$SWARM_TEST_ROOT"
python3 -m pytest tests/ros2 -q 2>&1 | tee "$SWARM_EVIDENCE/ros_python_tests.txt"
```

Check every command's exit status. `tee` succeeding does not mean the test succeeded; retain `pipefail` or record the pipeline status. Resolve rosdep errors rather than continuing with an incomplete build. Verify new package prefixes resolve to this test worktree's install directory. Record versions of ROS, Gazebo, slam_toolbox, ros_gz, rosbridge, Python, NumPy, Node, npm and the actor runtime. Inspect installed slam_toolbox launch/parameter APIs when adapting lifecycle behavior; do not mix source examples from incompatible releases.

Run the full repository Python suite in a suitable project environment, keeping ROS-compatible tests in the ROS environment if necessary. Use an existing compatible environment or create an isolated one; do not replace the system ROS Python packages or change the original GPU training environment just to make tests pass. Missing dependencies, skipped tests and environmental failures must be reported explicitly. The Mac record was 184 Python tests and 142 frontend tests at handoff; verify actual collected tests on Linux rather than copying those numbers.

```bash
python3 -m pytest -q 2>&1 | tee "$SWARM_EVIDENCE/python_full_tests.txt"
cd frontend
npm ci 2>&1 | tee "$SWARM_EVIDENCE/npm_ci.txt"
npm run build 2>&1 | tee "$SWARM_EVIDENCE/frontend_build.txt"
npm test -- --reporter=dot 2>&1 | tee "$SWARM_EVIDENCE/frontend_tests.txt"
cd "$SWARM_TEST_ROOT"
git diff --check
```

If the full Python suite needs a separate interpreter, replace `python3` with its actual path and record it. Do not pretend running only `tests/ros2` is the full suite. Fix failures, rerun affected tests, and record the final result after the final code changes.

Create a small reusable environment helper containing only the exact ROS setup file, new workspace setup file, project path and relevant ROS domain/middleware settings. Source it in every probe/UI/inspection terminal. Do not put secrets into it. Keep `ROS_DOMAIN_ID` and middleware consistent, and make sure unrelated demos do not publish into the same domain.

### D. Prove rover SLAM and correct feedback before using PPO

Identify existing project launch processes and stop only the relevant demo after preserving its invocation. Do not indiscriminately kill all ROS/Gazebo processes on a shared machine. Start the two-rover diagnostic in a managed terminal/process group and save its actual PID and complete log:

```bash
ros2 launch swarm_sar_gazebo slam_demo.launch.py \
  scenario:=rovers controller:=waypoint low_resource:=true \
  rviz:=true rosbridge:=true 2>&1 | tee "$SWARM_EVIDENCE/diagnostic_launch.txt"
```

For a truly headless host use `headless:=true rviz:=false`, then explicitly mark visual RViz/Gazebo checks pending until an actual display is available. Do not fabricate screenshots or mark graphical checks as passed from a headless log. Diagnose missing clock/scans before adding GUI load.

From another sourced terminal, capture bounded inspections:

```bash
ros2 node list
ros2 topic list -t
ros2 lifecycle get /rover_0/slam_toolbox
ros2 lifecycle get /rover_1/slam_toolbox
ros2 param dump /rover_0/slam_toolbox
ros2 param dump /rover_1/slam_toolbox
ros2 topic info /rover_0/slam_map --verbose
ros2 topic info /rover_1/slam_map --verbose
ros2 topic info /rover_0/odom --verbose
ros2 topic info /rover_0/cmd_vel --verbose
ros2 topic info /rover_1/cmd_vel --verbose
ros2 node info /rover_0/search_controller
ros2 node info /rover_1/search_controller
timeout 15s ros2 topic hz /rover_0/scan
timeout 15s ros2 topic hz /rover_1/scan
timeout 15s ros2 run tf2_ros tf2_echo map rover_0/base_footprint
timeout 15s ros2 run tf2_ros tf2_echo rover_0/map rover_0/odom
```

Save each command's output under the evidence directory. A `timeout` exit of 124 is expected for an intentionally bounded streaming inspection if meaningful output arrived; it is not automatically a successful sensor check. Inspect both rovers symmetrically. If node names differ after a necessary host fix, record the actual names and explain the change.

Required observations:

- Both lifecycle nodes become active and publish independent scan-built `/<rover>/slam_map` maps in `rover_0/map` and `rover_1/map` respectively. There must be no accidental shared global `/map` publisher carrying both maps.
- Clock, scan and TF timestamps use the same simulation time. Scans have a real lidar frame that resolves to the corresponding base frame. Wheel odometry is `/<rover>/wheel_odom` in `<rover>/odom`.
- Static known-start transforms are `map -> rover_0/map` at (-1,-17) and `map -> rover_1/map` at (-6,-17), unless you intentionally change the spawn configuration and update both consistently.
- Dynamic transforms are `<rover>/map -> <rover>/odom` from SLAM and `<rover>/odom -> <rover>/base_footprint` from the wheel bridge. Inspect publisher/node/bridge provenance; merely seeing a TF edge is not proof of a unique authority. No second static map-to-odom transform, competing parent, or bridged rover world-pose transform may control that base frame.
- `/<rover>/ground_truth/odom` is diagnostic truth, while `/<rover>/odom` and `estimated_odom` come from the adapter's estimated chain. Trace the controller's actual subscription to the latter. Initial spawn offsets must not be added twice.
- `local_slam_map` is projected from local SLAM alone. `belief_map` adds accepted radio knowledge, with local observations taking precedence. No operator-combined map or hidden global occupancy service may feed the robot's private SLAM backend.
- One active motion controller publishes each robot's `cmd_vel`. The SLAM adapter never drives motors. Nonzero commands lead to actual Gazebo motion and subsequent observations; a command log alone does not prove movement.

Run the bundled probe, not a handwritten replacement with weaker checks:

```bash
python3 simulation/ros2_ws/tools/slam_runtime_probe.py \
  --agents rover_0 rover_1 --seconds 120 --wall-timeout 600 \
  --output "$SWARM_EVIDENCE/diagnostic_probe.json" \
  2>&1 | tee "$SWARM_EVIDENCE/diagnostic_probe_stdout.txt"
```

It must exit zero and its individual checks must pass: at least ten scans, wheel and estimated messages per rover; at least three raw SLAM maps; more than 100 known cells; more than 0.5 m of movement from the initial estimate; expected map/odom/TF frames; tracking health; and an applied peer snapshot for multiple rovers. These are integration smoke thresholds, not accuracy or exploration quality guarantees. The probe does not inspect PPO loading, prove unique TF publishers, prove loop closure, or certify every peer direction.

Add read-only evaluation tooling if needed to record synchronized estimated and truth trajectories outside the audited training sources. Report median/RMS/p95 position error, heading error, sample count, matched timestamp tolerance and unmatched samples. Use a documented simulation-time matching tolerance (for example 0.1 s); do not compare arbitrarily separated samples. Truth is permitted only in the evaluator/radio/sensor proxy, never as a controller observation or correction. Report measured values; do not invent a pass threshold after looking at the result. Inspect occupancy alignment with Gazebo walls and open space, including coordinate orientation and rover footprints.

To demonstrate loop closure, drive a physically feasible route back through a previously observed area and capture actual pose-graph/correction evidence supported by the installed toolbox. A pretty map, repeated route or `do_loop_closing: true` alone does not prove a closure occurred. If closure cannot be demonstrated, report the exact attempted route and evidence and leave that row NOT DEMONSTRATED.

### E. Validate real peer communication, partitions and recovery

Capture `/swarm/network/events`, `/swarm/network/stats`, each agent's `slam_health`, and source/destination mapping channel activity. Validate both rover directions; a single global `receiver_applied` event does not prove both receivers work. For the heterogeneous run also inspect drone-to-rover and rover-to-drone traffic. Distinguish snapshot application from a leased claim being applied.

The default SLAM profile uses both `peer` and `slam_peer` in the same radio process and a 32,768 byte/s sender budget. Confirm this against actual runtime stats and source. Ensure repair requests and retransmitted chunks traverse that same process and budget. Budget accounts payload bytes plus the configured envelope estimate, not physical Wi-Fi airtime. A broadcast consumes one sender transmission, while per-recipient event rows can appear multiple times; do not multiply those rows into a false transmitted-byte total.

Run the partition experiment after both rover receivers have applied at least one snapshot:

```bash
ros2 service call /swarm/network/isolate/rover_0 std_srvs/srv/SetBool '{data: true}'
# Measure at least 15 seconds using /clock, not a 15-second wall-clock sleep.
ros2 service call /swarm/network/isolate/rover_0 std_srvs/srv/SetBool '{data: false}'
```

Write an automated recorder/assertion script when practical so screenshots are supported by data. Record request time, acknowledgement, confirmed isolation state, before/during/after local source-map timestamps, peer snapshot revision, peer age, live claims, applied events and reconnection time. Allow existing transport delay to settle before measuring the isolated interval. During the partition:

- Local scans, estimated feedback and the robot's own mapping process continue. Known-cell count can remain stable on a fully observed route; require fresh local data rather than inventing new cells.
- No post-isolation mapping delivery involving the isolated robot is accepted after the bounded in-flight/acknowledgement interval. Queued packets must also respect isolation.
- Its incoming peer revisions stop advancing; peers stop receiving new knowledge from it. Historical peer cells remain visible with increasing age. Eight-second frontier leases expire without fresh intent.
- Other non-isolated agents can still exchange messages. A UI-only visual change is not sufficient proof of a radio partition.

On reconnect, record the first actual delivered chunk and the first complete repaired/new snapshot applied in each relevant receiver. Record repair requests/retransmissions, elapsed simulation seconds and the resulting map knowledge. A snapshot can need multiple refresh intervals under loss; if none completes, diagnose/fix it and rerun. Do not change the display to simulate convergence. Peer-only cells may legitimately be zero when maps overlap; use real distinct observations within radio reach to demonstrate their contribution.

Exercise additional bounded tests on a disposable run/domain and preserve results:

- Raise real transport packet loss and verify nonzero dropped-loss counters and eventual complete snapshot recovery. Restore normal conditions and measure recovery.
- Exercise delay/reordering and duplication; verify no partial snapshot application and no duplicate/older session overwriting newer knowledge.
- Send deliberately expired, wrong-frame and malformed mapping envelopes through the normal modeled radio using an isolated test publisher, and verify rejection. Keep these labelled test injections out of final operational screenshots.
- Verify sender identity rejection, queue bounds and budget drops under controlled load without unbounded publisher spam. Never inject velocity or fabricated survivor detections.
- Reset/restart a sender session and verify old session traffic cannot repopulate its retired map, and old layer metadata cannot crash health publishing.
- Check radio range/wall attenuation through the real emulator, with documented positions/settings. Moving or configuring a real test is required; drawing a network line is not evidence of range behavior.

Inspect whether a parameter is read at startup or dynamically before changing it. In the current bridge `bytes_per_second` and `max_range` initialize cached objects/fields; setting a ROS parameter afterward does not automatically rebuild those objects. Use an explicit tested launch override or implement a validated parameter-update path for such tests. `base_loss` and delays are read while routing. Record actual effective settings in every test and restore the final demo configuration.

For reset behavior, inspect the installed Gazebo reset service/API and perform a real simulation clock rewind in a disposable diagnostic run. Do not publish a second fake `/clock` into the operational domain. Verify the adapter/network become restart-required, old queues/layers cannot masquerade as a fresh mission and the active controller stops on stale/future feedback. Stop the full launch and start a fresh SLAM session afterward; refreshing the frontend is not a pose-graph reset.

### F. Connect the genuine PPO pipeline and validate heterogeneous physical search

Before launching the actor, create a written interface table from its actual code: observation feature names/order, tensor shapes and dtypes, crop/scale/world origin, occupancy semantics, action meanings/masks, role identity, normalization, recurrent hidden state/reset and required velocity inputs. Compare this to the supplied checkpoint's saved contract. The ROS 240×240 grid at 0.2 m/cell is a mapping representation; it is not automatically the actor's trained 32×32 observation. Preserve physical scale and action semantics in any crop/resampling/feature adapter, and test it on known geometric examples. Retain unknown versus free versus occupied distinctions.

Validate finite tensors, legal masked actions, stable role handling and recurrent reset at a new mission. Add a regression check comparing the recovered adapter's output against its documented observation contract. Log the actor's actual input-source topic names and a compact observation checksum/summary, not just its weight load. An actor that loads but receives the wrong features is not an integrated learned controller.

Use `/<rover>/odom` or `estimated_odom` for estimated pose and `belief_map` for the rover's exploration belief. Use raw scans for local obstacle protection and wheel feedback for velocity when needed. TF-derived odometry has no measured covariance and its twist is unpopulated; do not treat zero twist as measured stationary motion or the application's unavailable-covariance convention as a valid covariance estimate. Preserve the active controller's emergency/stale-data stop and show when a safety override changes a learned command.

Stop the waypoint diagnostic. In a clean sourced terminal run:

```bash
# Replace ppo_agent only if the recovered executable has another verified name.
ros2 launch swarm_sar_gazebo slam_demo.launch.py \
  scenario:=swarm controller:=ppo ppo_executable:=ppo_agent \
  low_resource:=true rviz:=true rosbridge:=true \
  2>&1 | tee "$SWARM_EVIDENCE/ppo_swarm_launch.txt"
```

If required, add `ppo_params:=/absolute/path/to/the/recovered/controller.yaml`. Check node names and namespace matching in that YAML; the launch names the controller `search_controller`, which may differ from the old host configuration. Adapt parameter scope explicitly. The current launch also passes `external_belief_map` and `accept_peer_map`; verify the recovered controller declares/uses their intended behavior rather than assuming it does.

The full profile must contain two physical rovers and two physical drones. Record actual actor/checkpoint file SHA-256 and the parameter identity used by inference; these can be different hash formats, so identify each precisely. Save genuine load and decision logs. Trace multiple consecutive learned actions through command publishing, actual Gazebo motion, new scans, SLAM updates and subsequent observations. Record learned decision count, safety overrides, task progress and failures. One `cmd_vel` publisher per agent and the absence of a parallel waypoint controller are mandatory.

Show at least one genuine sensor-proxy survivor encounter if feasible and identify how the evidence becomes an estimated location/peer message. Do not publish confirmed survivors just for the demo. Thermal/acoustic evidence remains simulated and noisy, and drones retain simulator localization; show those limitations in the report. Do not claim real thermal hardware, aerial SLAM, joint multi-robot optimization, GNN communication, larger-map policy generalization or a guaranteed hackathon win from these tests.

### G. Validate the actual physical-simulation frontend

Start Vite from this checkout's `frontend` directory, using an available port and recording it:

```bash
cd "$SWARM_TEST_ROOT/frontend"
npm run dev -- --host 127.0.0.1 --port 5173
# Open http://127.0.0.1:5173/?mode=ros
```

Use `ws://127.0.0.1:9090` on Linux. For the Mac frontend, keep the Linux bridge on loopback and use `ssh -L 9090:127.0.0.1:9090 <actual-user>@<actual-linux-host>`. If a trusted local-network demo explicitly needs direct access, use the launch's `rosbridge_address` option and record the bind address. An HTTPS page needs WSS or a local HTTP frontend. Do not expose an unauthenticated bridge to the public internet.

Use actual incoming ROS messages to verify selected-agent local maps, peer-only overlays, estimated trajectories, frontier components, leased claims, source labels, snapshot ages, real packet events and recently delivered link indicators. Confirm coordinate orientation with the actual Gazebo scene. Switch between both rovers and the drones; do not label drone truth/raycast localization as SLAM. Confirm the browser starts no local simulated mission in ROS mode and sends no velocity/goal/map commands. Its isolation/reconnection buttons must call the actual ROS service; visual state must follow network telemetry, not merely a successful service response.

Test browser disconnect, stalled simulation clock, stale pose/map data, refused/unavailable service, bridge restart and reconnect. Positions must stop advancing/fade when data are stale. Service failure must be visible and cannot cosmetically change the robot's radio state. Test reset and sender session changes so old mission data does not appear as a new live map. Preserve the existing browser simulator at `/` and verify it still loads separately.

The script `frontend/tools/validate_ros_ui.py` is an additional synthetic WebSocket contract test. Start Vite on 5178 or supply its `--url`, and use a compatible installed Playwright/Chromium environment. Save that test's result separately. It does not replace the real ROS browser session or count as live SLAM evidence. If the host has no browser automation, use an actual browser and record the manual checks; mark automation unavailable rather than inventing a pass.

The `guide-site` fieldbook is also included on the `rashiyaom` branch as ordinary files. Its prebuilt pages/audio can be served with `python3 guide-site/scripts/serve.py` from the repository root. Verify the script's actual port and open it if checking the educational deliverable. It is a historical project edition, not a live SLAM dashboard. Do not rebuild macOS TTS audio on Linux or treat historical screenshots/source copies as new validation evidence.

### H. Repeat, record evidence and report the exact validation state

Complete the diagnostic gate and then **three fresh full-PPO swarm launches**, using separate run IDs and evidence directories. Each final run must start from a new simulation and SLAM session, use the verified actor, and complete at least 120 simulation seconds plus its applicable fault/recovery observations. Do not count three probes attached to one surviving world as three fresh runs. Repeat the packet partition/recovery exercise on the final pipeline; preserve raw data for each repeat. If the actual PPO source/checkpoint cannot be obtained, perform three fresh diagnostic runs and explicitly leave the learned/full-system gate blocked.

Use `slam_runtime_probe.py` on the two rover SLAM instances during each final run, plus the additional actor/drone/ownership and fault checks described above. The probe only covers rover smoke checks; report drone physical stability, simulator localization, learned decisions and peer traffic separately. Adjust an infrastructure wall timeout only with a documented reason such as a slow real-time factor; do not silently lower functional thresholds to get a pass. Measure simulation duration and wall duration separately.

Record a bounded rosbag of selected topics: `/clock`, `/tf`, `/tf_static`, rover scans, wheel/estimated/truth odometry, raw/local/belief/peer maps, health/topology/status, network events/stats and the relevant peer envelope channels. Record controller decisions if a real decision topic exists. Use the installed rosbag CLI's explicit topic selection and suitable QoS overrides for transient-local maps/static TF; verify the bag contains the expected messages. Avoid recording every camera/depth topic by default. Check disk space before and during recording, stop bags cleanly and save `ros2 bag info`. Do not restart bag replay into the operational ROS domain.

Capture actual Gazebo, RViz and live-frontend screenshots/video with matching run IDs/timestamps. Keep diagnostic, synthetic-fixture and final learned-run evidence in clearly named locations. Save a concise exact reproduction command and environment source helper for each final scenario. Record failures and their fixes; retain original failed logs.

Write `docs/audits/slam_linux_validation.md` and a machine-readable summary such as `artifacts/slam_linux/<run-id>/validation_summary.json`. Use **PASS**, **FAIL**, **BLOCKED** or **NOT DEMONSTRATED** with an evidence path and measured result for each row:

| Gate | Evidence required |
|---|---|
| Correct Git source | Fetched `rashiyaom` commit, final tested commit/worktree, relevant diff |
| Host/controller preservation | Backup locations and recovered PPO source/config/actor provenance |
| Build and tests | Real rosdep/colcon/ROS helper/full Python/frontend commands, exit codes and skips |
| Independent rover SLAM | Two active lifecycles, two scan-built maps, valid frames and source timestamps |
| Unique TF and pose feedback | Ownership inspection and actual controller subscriptions; truth kept diagnostic |
| Physical motion and safety | Actual rover/drone motion, single controller ownership, stale/reset stop |
| Map/pose quality | Actual trajectory error statistics and map alignment inspection, limitations |
| Demonstrated loop closure | Revisited route plus installed-toolbox correction/graph evidence |
| Peer map contribution | Real sender/receiver snapshot application in both rover directions, distinct local/peer layers |
| Radio constraints | Actual range/loss/delay/budget/queue settings and bounded failure tests |
| Partition/recovery | At least 15 simulation seconds isolated, lease expiry, measured repaired/new snapshot recovery |
| Reset/session isolation | Real clock rewind test, restart-required behavior and clean full restart |
| Genuine PPO inference | Verified actor identity, compatible observations, real actions and end-to-end physical feedback |
| Heterogeneous run | Two rovers/two drones, role handling, physical stability and communication evidence |
| Survivor encounter | Actual simulated sensor evidence and location sharing, or a precise missing-result explanation |
| Live frontend | Real ROS maps/events/service controls and disconnect/stale/error behavior |
| Repeatability | Three distinct fresh runs and their per-run results; separate diagnostic from learned runs |

Overall full integration is **PASS only when all required build, SLAM, estimated feedback, communication/fault recovery, genuine PPO, heterogeneous physical operation, frontend and repeatability gates pass**. Map quality and loop-closure results must be stated separately; an undemonstrated loop closure cannot become a claimed success. If any required gate is blocked/failed, use PARTIAL/BLOCKED overall and name the blocker. Averages must not conceal a failed run. Do not copy Mac test results or old screenshots into Linux PASS rows.

If you make code fixes after a successful run, rerun the affected tests and live acceptance gates against the final source. Preserve reviewed implementation changes and the concise report on the Linux validation branch. Keep large bags/videos local with paths, sizes and checksums instead of accidentally committing them or private backup directories. Do not modify audited actor/training manifests or start policy retraining for this integration.

Keep me updated while working. Finish all feasible authorized implementation and testing without stopping at an outline. The final reply must include the actual repository/working branch and tested revision; exact launch and frontend commands; PASS/FAIL/BLOCKED table; actor provenance; measured map/trajectory and partition/recovery results; three-run results; evidence/report paths; and any remaining blocker. Do not say the whole project is done when only waypoint mapping or a frontend build has passed. No deployment or force-push is part of this Linux validation task.
