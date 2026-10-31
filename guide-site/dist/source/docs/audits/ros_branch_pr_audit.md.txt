**ROS implementation, pull-request, branch and screenshot audit**

Audit date: 30 October 2026. Current checkout: `rashiyaom`, source commit
`83cd96ce7a5651ee77f5816a7ab47844bc0cbf7a`.

**Conclusion**

The ROS 2/Gazebo implementation is already in this workspace. Its originating
collaborator branch is
[`Yash-Bharvada/swarm-sar:ubuntu_simulations`](https://github.com/Yash-Bharvada/swarm-sar/tree/ubuntu_simulations).
PRs #1 and #2 merged that work, and repository reorganization moved the old
`ros2_ws/` tree to `simulation/ros2_ws/`. It is unnecessary to import that whole
ROS workspace again before starting SLAM work.

The supplied screenshot log separately records PPO actors and decisions. The
matching `ppo_agent` implementation was not found in the inspected GitHub
branches, PR heads, tags or reachable ROS code history. This narrow missing
item must not be conflated with the already-present ROS physics, controller,
mapping and communication implementation.

**Live GitHub inspection**

Queried every currently listed PR, including closed/merged PRs, and paginated
branch listings for:

- `rashiyaom/swarm-sar`: six branches; three PRs, all merged.
- `pankti0409/swarm-sar`: two branches; no PRs.
- `Yash-Bharvada/swarm-sar`: two branches; no PRs on that fork itself. Its
  contribution PRs target the main repository.

Fetched origin/pankti branches and tags, both Yash branch heads into an audit
ref namespace, and all three main-repository PR head refs. Inspected 33 local,
remote-tracking, PR and tag refs, with duplicate revisions cached. The repository
is not shallow. Also read PR bodies, changed-file lists and commit lists, and
checked issue/review comments for additional implementation references.

No branch was checked out, merged, deleted or pushed. Existing untracked work
was retained.

| PR | Subject | Source | Status |
|---|---|---|---|
| [#1](https://github.com/rashiyaom/swarm-sar/pull/1) | ROS 2/Gazebo physics demo and detection-only RViz map | Yash `ubuntu_simulations`, head `f565468...` | Merged |
| [#2](https://github.com/rashiyaom/swarm-sar/pull/2) | RViz axes and rover/drone survivor encounters | Yash `ubuntu_simulations`, head `b87c246...` | Merged |
| [#3](https://github.com/rashiyaom/swarm-sar/pull/3) | Selected PPO 754k model and development evidence | `gpu-754k-handoff`, original PR head `54d87bd...` | Merged |

PR #3's description explicitly does not establish ROS learned-policy integration.
Its delivered model is different from simply adding a ROS controller adapter.

**Source comparison**

Yash's current `ubuntu_simulations` head is
`b87c24632843f5278992d1c4dfe93ec59f4baec7`.

After normalizing the relocated root directory:

- All 35 ROS workspace files in that branch remain present here.
- 33 are byte-identical Git blobs.
- Two have later readiness changes: selected scan-topic configuration and a
  bounded startup wait in `wait_for_simulation.py` / the main launch file.
- The current ROS tree has one additional relocated encounter probe under
  `simulation/ros2_ws/tools/`.

The current workspace contains four ROS packages:

| Package | Role |
|---|---|
| `swarm_sar_description` | Rover/drone models, survivor assets, disaster world |
| `swarm_sar_interfaces` | Status, evidence and peer-message schemas |
| `swarm_sar_control` | Controllers, map/evidence handling and peer transport |
| `swarm_sar_gazebo` | Launch, bridges and RViz configuration |

The current main launch selects `waypoint_demo` for its default demo profile
and `decentralized_agent` for other profiles. Its registered executable list
does not contain `ppo_agent`. Searches also covered imports and checkpoint
loading strings, not just a particular missing filename.

**Photos and recorded-run evidence**

The original images are under `docs/media/simulation-screenshots/`:

- `03-gazebo-overview.png`: original disaster-world overview, visually inspected.
- `10-rviz-progress.png`: original occupancy-map/robot view, visually inspected.
- `01/05/07/09`: additional Gazebo captures.
- `02/04/06/08`: earlier RViz captures from the session.
- `run.log`, `README.md`, `capture-manifest.json`: accompanying records.

`docs/media/simulation-screenshots.zip` contains those ten images and three
text/metadata files. It does not contain the host controller source.
`docs/media/rviz-map-sequence.gif` displays successive original RViz captures.

The log records:

- Lines 104–105 and 207: rover/drone PPO actor loads.
- Lines 221, 228–229 and 240–242: policy decisions.
- Lines 223–227: robot map connections and live occupancy visualization.
- Lines 236 onward: peer-network attempted/delivered/dropped packet counters.

The captured host stack reports Jazzy/Gazebo 8.15.0. The merged physics-demo
PRs report Lyrical/Gazebo 10.5.0. These are different host/runtime records and
must not be silently treated as the same reproducible installation.

The recorded ROS actor hashes begin `a6d62df2` / `49fbbd06`; selected grid-policy
parameter hashes begin `3edcfc12` / `8e1c10a6`, as documented in the gallery.
The evidence supports a recorded ROS PPO session, but not an assertion that it
used the selected grid handoff or a particular validated SLAM backend.

**Practical consequence for the current SLAM task**

Develop launch/config/communication changes against the ROS source already
present here and validate on Linux. If extending the recorded PPO node, first
locate that node in the actual running Linux checkout, its installed package
or uncommitted host work. The remaining recovery question concerns that specific
variant, not whether the team has implemented ROS/Gazebo simulation.

Machine-readable ref, PR and media identity details are in
`ros_branch_pr_audit.json`. This audit did not execute a ROS/Gazebo simulation
or benchmark a new model.
