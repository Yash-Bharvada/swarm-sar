# Swarm SAR

Swarm SAR is a deterministic, seedable 2D search-and-rescue simulation for a team of rovers. Cave or maze maps contain walls, rubble, and hidden victims; each rover sees only its private fog-of-war map plus noisy directional thermal and omnidirectional acoustic readings. This repository implements Part 1—the simulation environment and tools, without learning.

## Setup

Python 3.10 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .
pytest -q
```

## Run

```bash
python scripts/view_world.py       # Space/N: next seed, G: view, V: vision
python scripts/play_manual.py      # arrows: move, Tab: switch rover
python scripts/run_random.py       # 100-episode baseline and results CSV
python scripts/benchmark.py        # 5,000-step performance gate
```

All behavior is configured in `configs/world.yaml`, `configs/robots.yaml`, and `configs/sim.yaml`. Set `SDL_VIDEODRIVER=dummy` before starting Python when rendering on a headless server. The renderer also supports an off-screen `rgb_array` mode.

## Layout

```text
configs/              world, robot, and simulation settings
src/swarm_sar/world/  generation, reachability, and victims
src/swarm_sar/robots/ robot state and type configuration
src/swarm_sar/sensing/vision, thermal, acoustic, confirmation
src/swarm_sar/sim/    engine and metrics
src/swarm_sar/viz/    pygame renderer (not imported by the engine)
scripts/              visualizer, manual play, baseline, benchmark
tests/                deterministic behavioral tests
results/              generated CSVs/screenshots (git-ignored)
docs/                 architecture notes and diagrams
```

## Assumptions

1. All rovers share one coordinate frame anchored at the spawn area. Later map merging depends on this.
2. Odometry (`rel_pos`) is noiseless in Part 1. Drift can be added later.
3. Time is discrete and every move is exactly one cell.
4. Dead rovers do not block other rovers.
5. Rovers cannot swap cells, and collision damage is not modeled.
6. Beliefs are private in Part 1. Communication and map merging come later.
7. The world and sensing are simulated in 2D. This is a validated prototype, with ROS 2 and Gazebo as the deployment path.

## Current status

- [x] Seeded cave and optional maze generation with reachable-map cleanup
- [x] Reachable, separated victims and distinct rover spawning
- [x] Collision-safe movement, battery, rubble, and death rules
- [x] Private fog of war with wall-occluded line of sight
- [x] Directional thermal, attenuated acoustic, and LOS confirmation
- [x] Ground-truth-free observations and episode metrics
- [x] Known-map/ground-truth pygame views and off-screen RGB frames
- [x] Manual controls, random baseline, and automated tests
- [x] Speed gate: 2,343 environment steps/second in the project virtual environment (5,000-step run)

The seeded 100-episode random baseline completed successfully and wrote `results/random_baseline.csv`; it averaged 0.71 of 4 victims found and 22.4% coverage. This intentionally weak policy is only a smoke-test baseline, not the required Part 2 frontier baseline.

Before Part 2, add a frontier-exploration baseline and ensure it finds at least 90% of victims within `max_steps`. If it cannot, adjust episode length or map difficulty before training.
