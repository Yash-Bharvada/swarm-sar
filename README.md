# Autonomous Disaster Response Swarm — Blueprint Steps 1–2

This repository implements the Blueprint Step 1 disaster-world testbed and Step 2 non-learning benchmark: a deterministic NumPy simulation with two rover-like and two drone-like agents, private occupancy and topological maps, noisy thermal/acoustic sensing, drifting odometry, hidden survivors, coordinated frontier reservations, evidence-based confirmation, A* motion, a PettingZoo `ParallelEnv`, structured artifacts, and a Pygame visualizer. Peer networking and reinforcement learning are later steps.

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

The action mask identifies valid frontier slots. Every observation contains only the agent's private belief crop, drifting local pose, uncertainty, battery, noisy sensors, collision state and locally derived frontier features. True grids and survivor coordinates are never returned to policies.

## Environment model

- Configurable 24×24 through 40×40 room/corridor worlds; default 32×32
- Walls, rubble, blocked passages, safe common-entry spawn and reachability cleanup
- Random 1–4 hidden survivors
- Two rovers with shorter vision and higher rubble cost
- Two 2D drone proxies with wider vision and lower rubble cost; neither type crosses walls
- LOS-occluded occupancy and thermal sensing
- Longer acoustic sensing with wall attenuation
- Configurable noise, detection misses and false positives
- Per-agent private maps and odometry drift/confidence
- Sequentially resolved movement that prevents overlap and swaps

## Project layout

```text
configs/                 world, heterogeneous agents and simulation settings
src/swarm_sar/world/     rooms/caves/mazes, reachability and survivors
src/swarm_sar/robots/    agent state and type configuration
src/swarm_sar/sensing/   ray-cast vision, thermal, acoustic, confirmation
src/swarm_sar/sim/       core, PettingZoo API, A*, frontiers, metrics, logging
src/swarm_sar/mapping/   private NetworkX topological graphs
src/swarm_sar/baselines/ coordinated frontier and evidence controller
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
7. Goal reservations and evidence arbitration are direct calls inside the Step 2 benchmark. Transporting them as lossy peer messages is deliberately deferred to Step 4.

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

The next milestone is Blueprint Step 3: RLlib PPO with one shared rover policy and one shared drone policy, trained on the same fixed observation/action contract and evaluated against this frozen frontier baseline.
