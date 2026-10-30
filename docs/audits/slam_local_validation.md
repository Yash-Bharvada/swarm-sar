# Local SLAM integration validation — 2026-10-30

The source implementation and local checks are complete. **Live SLAM/Gazebo and the missing Linux ROS PPO controller are not validated on this Mac.** Follow [the Linux prompt](../guides/LINUX_SLAM_VALIDATION_PROMPT.md) for that remaining work.

Baseline: `83cd96ce7a5651ee77f5816a7ab47844bc0cbf7a`. Host: macOS, project Python 3.13 virtual environment, existing frontend Node/npm environment. `rclpy`, `launch` and `tf2_ros` are unavailable locally. Xacro 2.1.1 was installed in the project virtual environment to expand the actual robot descriptions.

| Check | Result | Evidence / limits |
|---|---|---|
| Full Python suite | **184 passed** | `artifacts/slam_local_python_tests.txt`; two existing PettingZoo deprecation warnings |
| ROS-independent/static/expanded-model subset | **32 passed** | `PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/ros2 -q`; includes actual rover/drone Xacro expansion, not Gazebo execution |
| Frontend production build | **Passed** | `cd frontend && npm run build`; TypeScript and Vite succeed |
| Frontend suite | **142 passed, 17 files** | `cd frontend && npm test -- --reporter=dot`; includes ROS map frame/shape/rotation checks |
| Browser ROS contract | **Passed** | `artifacts/slam_local_ui/report.json`; ten checks using explicitly synthetic rosbridge fixtures |
| Python syntax | **Passed** | AST parsing of ROS sources, probes and packaging/browser validation tools without importing unavailable ROS |
| Whitespace/conflict check | **Passed** | `git diff --check` |
| Live SLAM lifecycle, scans/maps/TF | **Pending Linux** | Must use actual installed ROS/Gazebo; no simulated PASS recorded |
| Real radio partition/recovery | **Pending Linux** | Pure snapshot/budget/lease logic is tested; actual ROS callbacks/services still need runtime validation |
| Learned search using estimated feedback | **Pending Linux** | Recover the host's real PPO implementation and verify observation compatibility and actor/action evidence |
| Successful loop closure / map accuracy | **Pending Linux** | Enabling scan matching and loop closure is configuration, not an observed result |

The local geometry/protocol tests cover rotated/translated maps, coarse-cell occupancy conflicts, invalid shapes/values, out-of-order chunk assembly, selective recovery after deterministic packet loss, atomic snapshot replacement, session rollover, delayed old-session rejection, malformed new sessions preserving previous knowledge, removal of stale session metadata, TTL/frame/uncertainty admission, immutable local maps, radio budgeting and expiring/non-replayed frontier intent. Bridge projection tests check that truth TF is removed and wheel TF is retained.

The browser test runs Chromium with Playwright and verifies disconnected waiting state, native socket subscriptions, incoming topic handling, the isolation service payload, acknowledgement versus observed network state, visible service failures, disconnect disabling controls, absence of control/map publications, and no page errors. The generated screenshot is a **disconnected real UI preview**, not a fabricated mapped mission. Synthetic input tests are deliberately not saved as operational SLAM screenshots.

Reproduce the UI contract test after starting Vite on port 5178:

```bash
.venv/bin/python frontend/tools/validate_ros_ui.py
# If using a separately installed Chromium, add --browser-executable /absolute/path/to/browser
```

The virtual environment's Playwright expected a newer browser revision than the already cached one. The successful local test explicitly used the installed Chromium headless-shell executable through the supported override. No project npm dependency was added for this test.

The ROS profile has no synthetic replacement for the missing learned actor. `controller:=ppo` fails if its configured executable is missing. A present executable still requires source/observation/action validation on Linux. `waypoint` and `frontier` remain explicitly diagnostic/heuristic choices. The checked-in waypoint controller now also stops on stale or future-dated odometry/scan reception times, covering clock rollback while the SLAM adapter fails closed.

The handoff archive is produced with `python3 simulation/scripts/package_slam_handoff.py`. That tool verifies each payload checksum, applies the tracked patch to an isolated copy of the actual baseline and compares the reconstructed files against the workspace. It does not touch the working tree, commit, push, change weights or overwrite Linux files. Its result is written to `artifacts/slam_handoff_manifest.json`.

The packager defaults to the fixed pre-SLAM baseline above, so it can also be rerun after the integration has been committed. `--base-ref` selects a different explicit baseline. The primary Linux delivery is the GitHub `rashiyaom` branch; the archive is a fallback and its patch must not be reapplied over the already integrated branch.

No trained actor weights, audited training manifests, core learning environment or existing experiment results were modified. The existing demo launch remains available; the new SLAM profile always starts rover SLAM and makes the motion controller explicit.
