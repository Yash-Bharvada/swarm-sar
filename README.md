# Autonomous Disaster Response Swarm — Blueprint Steps 1–4

This repository implements Blueprint Steps 1–4: a deterministic heterogeneous disaster simulator, frontier and PPO policies, irregular-world scalability, and a decentralized lossy peer network. Agents use local maps, noisy sensors, relative pose, received peer messages and fixed action spaces; no server assigns goals or exposes global state.

## Setup

Python 3.10 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .
pytest -q
```

## Validate Step 1

```bash
python scripts/validate_step1.py
```

This runs seeds 0, 1, and 2; verifies the 2-rover/2-drone team, survivor range, observation boundary, reproducibility, collision-safe movement, wall constraints and odometry drift; and writes:

```text
results/step1_validation/summary.json
results/step1_validation/summary.csv
results/step1_validation/seed_N/map.json
results/step1_validation/seed_N/events.json
results/step1_validation/seed_N/trajectories.csv
results/step1_validation/seed_N/metrics.json
```

## Validate Step 2

No API key is required. NetworkX runs locally.

```bash
python scripts/validate_step2.py
```

The default gate runs 20 fixed seeds and writes four distinct agent graphs, baseline events, core episode artifacts and aggregate validation results under `results/step2_validation/`.

The frozen baseline also passed an untouched stressed holdout:

```bash
python scripts/audit_step2_robustness.py
```

This uses seeds 100–119, cycles through 24×24, 32×32 and 40×40 maps, increases sensor noise and false positives, lowers detection probability, doubles odometry drift and reduces battery. Its fixed pass thresholds are stored in the installed validation module and written to the results before episodes run.

## Validate Step 2.5

No API key is required.

```bash
python scripts/audit_step25_scalability.py
```

The audit first checks 50 generated worlds for reachability, survivor placement, non-square dimensions and irregular geometry. It then runs eight complete holdout missions over independently generated 48–90 by 72–140 cell sites, verifies the fixed 9×9 observation and seven-action contract during execution, and replays the first mission to check determinism. Full artifacts are written under `results/step25_scalability/`.

## Train and validate Step 3

No API key is required. Training runs locally with RLlib and PyTorch.

```bash
python scripts/train_step3.py
python scripts/validate_step3.py
python scripts/run_step3_policy.py --rovers 2 --drones 3 --network
```

Step 3 uses exactly two shared PPO policies regardless of agent count, curriculum training over 1–6 robots, and held-out evaluation on 5-agent and 8-agent teams. The checkpoint is evaluated on 20 unseen maps against the frozen frontier baseline. See `docs/step3_validation.md` for the honest comparison and limitations.

The validated checkpoint is versioned at `artifacts/step3/checkpoint/`; retraining output is written under `results/step3_training/`.

### GPU-v1 training preparation

Use the audited `rashiyaom` GPU pipeline and **v2 expert dataset** described in
[`docs/GPU_TRANSFER_CHECKLIST.md`](docs/GPU_TRANSFER_CHECKLIST.md). The older
`gpu-v1-training-ready` release and v1 expert data do not include the 29 October
full-launch, causal-teacher and stable-trajectory fixes.

The original Step 3 checkpoint remains frozen under its historical 129-value
contract. New training uses the versioned 229-value `gpu-v1` contract, bounded
per-peer features, goal/action memory, an optional LSTM, disjoint seed ranges,
parallel Ray runners, periodic non-overwriting checkpoints and resume support.

Mac infrastructure smoke test:

```bash
python scripts/train_step3.py --config configs/training_gpu_a5000.yaml \
  --smoke --num-cpus 2 --num-env-runners 0 --num-gpus-per-learner 0 \
  --output results/mac_lstm_smoke
```

Export and validate Step 4 expert demonstrations:

```bash
python scripts/export_step4_expert.py --episodes 2000 --output results/expert_train_gpu_v2
python scripts/validate_expert_dataset.py results/expert_train_gpu_v2
```

The complete GPU handoff, class-balanced recurrent behavior cloning, cohort
evaluation, and automatic training gates are documented in
[`docs/GPU_TRANSFER_CHECKLIST.md`](docs/GPU_TRANSFER_CHECKLIST.md).

The A5000 profile is `configs/training_gpu_a5000.yaml`. See
`docs/gpu_training_preparation.md` before launching it.

The corrected expert dataset contains 868,887 validated decisions from 2,000
training seeds at `results/expert_train_gpu_v2/`. Copy that ignored directory
or its 128 MiB archive to the GPU machine; its aggregate and manifest hash are
tracked in `artifacts/gpu_v2/`. The teacher found 4,930/4,970 survivors through
the same observation/action interface available to the learned policies.

## Validate Step 4

No API key or cloud service is required.

```bash
python scripts/audit_step4_network.py
```

The locked audit runs 200 deterministic transport property cases, generates 100 large irregular worlds, executes 12 untouched networked missions over 0%, 10% and 30% packet loss, executes six network-disabled fallback missions, forces a temporary partition, and checks exact replay. The final holdout recovered 40/42 survivors (95.24%), recovered 14/16 at 30% loss (87.5%), recovered 17/17 with the network disabled, and recorded zero collisions. See `docs/step4_validation.md`; compact evidence is versioned under `artifacts/step4/`.

## Run

```bash
python scripts/view_world.py       # Space/N: next seed, G: view, V: vision
python scripts/play_manual.py      # arrows: move, Tab: switch agent
python scripts/run_random.py       # random valid high-level actions
python scripts/run_frontier_baseline.py
python scripts/run_frontier_baseline.py --seeds 0 --render
python scripts/view_topology.py results/step2_validation/seed_0/topology/rover_0.json
python scripts/benchmark.py        # PettingZoo + frontier + A* throughput
```

Colors and shapes in the visualizer:

- Black: unknown
- Light grey: free
- Dark grey: wall
- Brown: rubble
- Red: survivor, visible only when found or in truth view
- Rounded square marked `R`: rover
- Circle marked `D`: drone

On a headless server, set `SDL_VIDEODRIVER=dummy` before starting Python. The environment also supports `render_mode="rgb_array"`.

## PettingZoo API

```python
from swarm_sar import DisasterResponseParallelEnv

env = DisasterResponseParallelEnv(render_mode="rgb_array")
observations, infos = env.reset(seed=0)

while env.agents:
    actions = {agent: 6 for agent in env.agents}  # 6 = hold
    observations, rewards, terminations, truncations, infos = env.step(actions)

env.save_episode("results/example")
env.close()
```

The seven policy actions are:

```text
0–4  choose one of up to five local frontier slots; A* supplies the next move
5    follow the strongest thermal sector and fuse an independent second sample
6    hold
```

The action mask identifies valid frontier slots. Every observation contains only the agent's private belief crop, drifting local pose, uncertainty, battery, noisy sensors, collision state, locally derived frontier features and a range-limited peer summary. True grids and survivor coordinates are never returned to policies.

## Environment model

- Configurable rectangular room/corridor worlds; default 32×32
- Large procedural footprints made from seeded random connected lobes/corridors
- Fixed, named L/T/multi-structure/tunnel footprints for targeted tests
- Walls, rubble, blocked passages, safe common-entry spawn and reachability cleanup
- Random 1–4 hidden survivors
- Two rovers with shorter vision and higher rubble cost
- Two 2D drone proxies with wider vision and lower rubble cost; neither type crosses walls
- LOS-occluded occupancy and thermal sensing
- Longer acoustic sensing with wall attenuation
- Configurable noise, detection misses and false positives
- Per-agent private maps and odometry drift/confidence
- Simultaneous collision resolution with safe convoy motion, no overlap, and blocked swaps

## Project layout

```text
configs/                 world, heterogeneous agents and simulation settings
src/swarm_sar/world/     rooms/caves/mazes, reachability and survivors
src/swarm_sar/robots/    agent state and type configuration
src/swarm_sar/sensing/   ray-cast vision, thermal, acoustic, confirmation
src/swarm_sar/sim/       core, PettingZoo API, A*, frontiers, metrics, logging
src/swarm_sar/mapping/   private NetworkX topological graphs
src/swarm_sar/network/   lossy, delayed, partitionable peer transport
src/swarm_sar/baselines/ coordinated and fully decentralized controllers
src/swarm_sar/learning/   RLlib adapter, PPO module, encoding and inference
src/swarm_sar/viz/       Pygame renderer, isolated from the simulation core
scripts/                 viewer, manual control, baseline, benchmark, validation
tests/                   unit, integration, property and official API tests
```

## Explicit prototype assumptions

1. Agents share an initial coordinate alignment at the common entry marker; this is not GPS.
2. Odometry accumulates simulated drift and exposes uncertainty, while the simulator retains truth internally for physics and offline evaluation.
3. Drones are 2D aerial proxies with wider sensing and easier rubble traversal, not full flight-dynamics models.
4. Thermal and acoustic outputs are probabilistic cues, not real sensor emulation.
5. Time is discrete and the A* controller advances at most one grid cell per environment step.
6. Policies never receive ground-truth maps or survivor coordinates. Offline JSON/CSV artifacts may contain truth for evaluation.
7. Step 4 coordination uses only delivered peer messages. Radio range, walls, loss, delay, bandwidth, expiry and partitions are simulated; it is not yet a ROS 2 DDS or RF-channel model.

## Step 1 status

- [x] Seeded 24×24–40×40 rooms/corridors with walls and rubble
- [x] Two rover-like plus two drone-like agents with separate rules
- [x] Random 1–4 hidden survivors
- [x] Private LOS occupancy maps and heterogeneous scan ranges
- [x] Noisy thermal/acoustic cues with misses and false positives
- [x] Drifting local odometry with confidence
- [x] Five frontier slots, investigate, hold and A* execution
- [x] PettingZoo `ParallelEnv` with fixed spaces and action masks
- [x] Pygame human and RGB-array rendering
- [x] JSON map/events/metrics and CSV trajectory artifacts
- [x] Three-seed acceptance gate and automated tests

## Step 2 status

- [x] Private occupancy maps updated only from local sensing
- [x] Frontier detection, clustering and up-to-five candidate slots
- [x] Nearest useful unclaimed frontier selection
- [x] Persistent goal reservations and A* navigation
- [x] Repeat-evidence or second-agent survivor confirmation
- [x] Per-agent NetworkX graphs with rooms, junctions, frontiers and survivor sites
- [x] Attributed graph edges and NetworkX shortest-path queries
- [x] Four distinct graph artifacts plus maps, events and confirmed markers
- [x] Twenty-seed baseline evaluation
- [x] Untouched stressed holdout and frozen Git milestone

Step 2 is frozen at Git tag `blueprint-step2-frozen`; Step 3 evaluates its learned policies against that unchanged historical baseline.

## Step 2.5 status

- [x] Portrait and landscape dimensions sampled independently per seed
- [x] Connected procedural footprints with no fixed named geometry
- [x] Reachability cleanup and valid survivor placement on every generated map
- [x] Four to eight heterogeneous agents and time/battery scaled by site area
- [x] Range-limited peer-to-peer occupancy-map fusion
- [x] Multi-sample frontier splitting for large connected boundaries
- [x] Fixed 9×9 local observation, five frontier slots and seven actions at every size
- [x] Adaptive renderer bounded by configured display dimensions
- [x] Fifty-world generation property test and eight-mission end-to-end holdout
- [x] Legacy Step 1, Step 2 and stressed Step 2 regression gates

Step 2.5 supports arbitrary finite dimensions within configured compute/resource limits; it does not claim an infinite map or guarantee a fixed robot team can cover unlimited physical area. See `docs/step25_scalability.md` for the validation report and limitations.

## Step 3 status

- [x] RLlib PPO on the current RLModule/Learner API
- [x] One shared rover policy and one shared drone policy
- [x] Frozen original 129-value input and masked seven-action output
- [x] Versioned 229-value GPU-v1 input with recurrent-training support
- [x] One-rover → two-rover → heterogeneous-team curriculum
- [x] Cooperative reward and local collision safety layer
- [x] Restorable checkpoint, training history and curve
- [x] Twenty unseen-map comparison against the frontier baseline
- [x] Networking-on/off inference
- [x] Held-out 2-rover/3-drone and 4-rover/4-drone execution

Step 3 is a valid learned prototype. The final regression run reached 64.71% survivor recall versus 98.04% for the frontier baseline; use the baseline/Step 4 controller for the strongest rescue demo and PPO as the experimental learned mode.

## Step 4 status

- [x] Sender sequence numbers, frame IDs, pose uncertainty, map deltas, goals and survivor evidence
- [x] Range and wall attenuation, 0–30% loss, 1–4-step delay, bandwidth and stale expiry
- [x] Forced partitions, continued local autonomy, reconnection detection and periodic snapshot recovery
- [x] Common-entry relative frame and uncertainty-gated map merge refusal
- [x] Per-agent local loop with no reservation server or centralized assignment table
- [x] Active-peer rendezvous hashing for decentralized frontier ownership and automatic reassignment
- [x] Safe narrow-corridor convoy/yield behavior with zero-overlap simultaneous motion
- [x] Variable 5–9-agent end-to-end holdout and 4–10-agent generation coverage
- [x] 95.24% survivor recall on the final untouched large irregular-world holdout
- [x] Full Steps 1–3 regression gates and 92-test suite

Step 4 is complete for this simulator. It does not prove 95.24% performance in physical disasters, unlimited map sizes, arbitrary RF conditions, or ROS 2/Gazebo; those require the next integration and validation stage.

## Browser simulator (frontend)

`frontend/` contains a standalone browser 3D "Swarm Mission Control" simulator (React, Three.js, TypeScript). It runs locally with `cd frontend && npm install && npm run dev`. It is separate from ROS 2/Gazebo and from the Python runtime. Its Decentralized Autonomous Mode is a TypeScript implementation of the Step 4 decentralized-controller principles, not PPO/RL. See `frontend/README.md` and `frontend/CONTROLLER_COMPATIBILITY.md`.
