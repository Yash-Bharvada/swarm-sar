# Step 5 integration into rashiyaom

Integrated from [PR #1](https://github.com/rashiyaom/swarm-sar/pull/1),
`Yash-Bharvada:ubuntu_simulations`, commit
`f565468aaf78f063222d4b5394c8f4e638b6f3ac`.
The original integration target was `rashiyaom`. The integration is now included
in both `rashiyaom` and `main`; this document retains the original integration evidence.

## Included functionality

- Four ROS packages under `simulation/ros2_ws/src`: interfaces, descriptions, control,
  and Gazebo launch/bridge configuration.
- Default physics presentation: two drones and one rover. The optional full
  profile retains two drones and two rovers.
- Rotor-thrust drone models, wheel/contact rover model, bridge topics, local
  occupancy display, peer transport, and synthetic survivor evidence.
- Detection-only RViz survivor markers, runtime probes, and upstream Ubuntu
  build/motion evidence under `docs/evidence/physics-demo/`.

Use [physics_demo.md](../guides/physics_demo.md) for the current launch guide. The older
Jazzy setup and earlier full-profile observations remain in
[ros2_gazebo.md](../guides/ros2_gazebo.md), explicitly labelled as historical where needed.

## Integration boundaries

The default scenario runs predefined waypoint routes and simulator world-pose
feedback. The four-robot exploration profile runs a ROS frontier controller.
Neither loads the GPU PPO checkpoint. The browser controller, grid MARL
training and ROS physics demo are three separate execution paths; combining
their files in one repository does not establish learned-policy transfer.

The ROS sensor oracle produces noisy proxies from simulator truth, and vehicle
parameters are not calibrated to hardware. The upstream guide records a bridge
shutdown crash and does not guarantee survivor encounters on demo routes.
Those limitations are retained rather than converted into success claims.

## Validation on the integration host

The Mac can run the Python/grid suite, ROS package/XML/topic/launch static
checks, Python compilation and shell syntax checks. ROS, Gazebo, colcon and
xacro are not installed here, so physical-model expansion tests are explicitly
skipped and the simulation is not rerun locally. Upstream ROS motion records
are preserved as upstream evidence, not relabelled as fresh local results.

Integration checks: **152 Python tests passed, 2 xacro-dependent physical-model
tests skipped**; compilation, shell syntax, 30 frozen baseline hashes and the
GPU-v1 policy contract passed. Six ROS static tests include explicit checks
for the default three-vehicle demo and optional four-vehicle full profile.
ROS-node helper/runtime tests still require a sourced ROS environment.

The GPU source manifest is refreshed because the merge introduces Python and
shell scripts. The prior `rashiyaom-gpu-v2-audited` tag stays immutable; the new
combined release is `rashiyaom-step5-integrated`. The GPU checklist uses the
combined tag so its exact-commit check remains valid after this merge.

Existing uncommitted frontend edits and unrelated local documents are excluded
from the integration commit and remain in the working tree.
