# GPU training decision and architecture limits

Review date: 29 October 2026. This review applies to the Python training
prototype on `rashiyaom`; the browser changes are a separate workstream.

Step 5 update: PR #1 adds the ROS2/Gazebo workspace and recorded physics-demo
evidence. The original review below predates that merge. ROS packages/models
are now present, but the default demo is a waypoint controller using simulator
pose feedback, not the learned policy. See [step5_integration.md](../audits/step5_integration.md).

## Decision

The A5000 is worth using for a measured experiment: behavior cloning,
closed-loop evaluation, and a short PPO pilot, followed by more training only
if held-out rescue behavior improves. An unconditional 15-hour job is not
justified by the evidence currently in this repository. No training run can
guarantee an improved policy or a hackathon win.

## Measured warm-start result

The corrected 2,000-map teacher dataset contains 868,887 decisions and found
4,930/4,970 survivors (99.20%). The teacher uses only the learner's public
observation/action interface; the older, stronger-looking dataset was unsafe.

A CPU diagnostic trained six epochs capped at 64 batches per policy. It passed
the classifier gates: rover/drone balanced validation accuracy 62.45%/63.93%,
train–validation gaps 1.20/0.40 percentage points, and investigation recall
88.32%/85.52%. These are sampled diagnostic training passes, not the full GPU
training recipe or evidence against every form of overfitting.

The final evaluation used nine cohorts × eight development cases (72 missions)
with identical paired controller budgets. It did not use final seeds:

| Controller | Mean of cohort recalls |
|---|---:|
| Diagnostic learned BC policy | 74.82% |
| Policy-compatible expert | 87.13% |
| Random legal actions | 28.52% |
| First legal action | 22.27% |

The learned policy found 136/181 victims overall, with zero invalid actions and
zero post-shield collisions. Fixed-core mean recall was 72.88%; rotating-shadow
mean recall was 78.44%. Exact training-domain probes found all 9 victims, versus
12/13 on the matched unseen-domain probes; four seeds per group give weak
evidence and are not a reliability certificate.

Generalization is still weak: the learned policy found 2/18 on the 56-cell maze
and 4/21 on the unseen tunnel footprint. The expert found 4/18 and 13/21 there.
The maze is also a tight-budget challenge, so its low score cannot be attributed
only to the neural model. Small mazes were added to PPO's domain mix after this
finding; scale 56 and the tunnel footprint remain held out. A GPU pilot must
improve the same frozen development suite before receiving the remaining time.

Evidence is tracked under `training/artifacts/gpu_v2/`. A useful warm start now exists,
but claiming robust arbitrary-labyrinth or real-world performance is unsupported.

The stored Step 3 checkpoint found 27/51 survivors on its 20-map comparison,
while the frontier controller found 48/51 (`docs/audits/step3_validation.md`).
Successful weight updates and zero masked actions are infrastructure checks;
the useful output is a checkpoint with a measured advantage on paired cases,
or a clear early-stop report identifying why the attempt failed.

## What the architecture can learn

`learning/training.py` builds two shared PPO actor-critic modules. All rovers
use one module and all drones the other. Each actor receives a private map
crop, noisy thermal/acoustic readings, memory, odometry features, frontier
choices, and delivered peer-message features (`learning/observation.py`,
`sim/env.py`). Agents share a team reward. This is a cooperative decentralized
MARL prototype with type-level parameter sharing. It is not a centralized
MAPPO critic or a graph neural network. The LSTM can retain history but does
not perform graph message passing.

The neural policy selects one of five generated frontier targets, investigate,
or hold. A* executes a one-cell movement toward the chosen target. A safety
shield arbitrates traffic (`sim/env.py`). Consequently rescue results measure
the complete policy/planner/shield system; zero collisions cannot be attributed
solely to learned coordination. The occupancy/action-mask-only baseline helps
expose improvements that come from the simulator interface instead of learning.

## Overfitting risks addressed in evaluation

Repeated development evaluation now preserves a fixed core for comparable
checkpoint selection, while separate rotating shadow cases diagnose whether
improvements transfer to new maps. Training-range probes reconstruct exact
seed-keyed training configurations and compare unseen cases drawn from the
same randomized domain. They are diagnostics, not a
statistical proof of memorization: a seed in the training range may not have
been sampled by a particular PPO worker yet.

Each cohort reports episode-bootstrap recall intervals, completion, coverage,
time, invalid actions, action distributions and entropy. Optional paired
references use the policy-compatible Step 4 teacher, uniform legal-action sampling,
and the first legal-action rule on identical initial cases and budgets. Final
seeds are inaccessible without an explicit post-freeze acknowledgement, and
cannot be evaluated with shortened smoke budgets.

The dataset teacher uses the same observation/action interface as the learner.
It may update private controller memory, but cannot cancel simulator goals
or reorder frontier slots through an extra method before emitting its action.
Some expert choices also depend on robot names and private ownership memory,
which are not fully encoded in the actor input. Exact supervised imitation
is therefore not guaranteed even with more epochs. Closed-loop rescue
evaluation decides whether the warm start is useful.

The old `heldout_2r3d` label was misleading because that composition appeared
in PPO training. It is now `mixed_team_2r3d`. A separate 1-rover/4-drone cohort
is excluded from PPO composition sampling (it can appear in the expert dataset).
The first complete BC pilot exposed very poor performance on 56-cell mazes.
PPO now sees small mazes (at most 32 cells), while the 56-cell case remains
a size-extrapolation stress test. A separate 48-cell tunnel footprint is absent
from both BC and PPO, preserving a structural holdout. These are simulator
generalization tests; a finite procedural
generator does not establish real-world generalization.

## Limits GPU time will not fix

- Local maps use visible truth cells in a common lattice; the crop and A* start
  use the true grid position (`sensing/vision.py`, `sim/engine.py`, `sim/env.py`).
  Drifting odometry features and uncertain message rejection do not implement
  SLAM, loop closure, or unknown-start map registration.
- Thermal/acoustic readings are synthetic. Confirmation uses simulated true
  distance and line of sight (`sensing/victim_sensor.py`). It cannot establish
  real sensor precision, survivor identity, or reliable field detection.
- The Python training radio emulator tests loss/delay/TTL/partition logic.
  Step 5 adds separate ROS 2 nodes and Gazebo models; the GPU training pipeline
  does not exercise them. Calibrated dynamics, hardware deployment and measured
  learned-policy transfer to the ROS environment are still unvalidated.
- `frontend/src/simulation/core/SimulationEngine.ts` constructs a TypeScript
  `DecentralizedController`. It does not load the Python PPO checkpoint.
  Learned-policy rollout artifacts can be archived for a later integration,
  but the existing browser autonomy is not evidence of that checkpoint running.

The defensible hackathon claim is a reproducible decentralized search-and-rescue
simulation with heterogeneous agents, unreliable peer communication, and a
measured learned-policy experiment. A learned browser-policy bridge and a
small ROS 2/Gazebo integration are useful later milestones; training time
alone does not deliver either integration.
