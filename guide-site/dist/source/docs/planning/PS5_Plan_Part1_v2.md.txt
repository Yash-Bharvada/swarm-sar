# PS5 Swarm Search and Rescue: Plan Part 1 (v2, validated)

*Folder setup and the 2D Python world (rovers only). Build this on the day of the hackathon, not before.*

## Changes from v1

| # | Fix | Where |
|---|---|---|
| 1 | Added `pyproject.toml` and `pip install -e .` (v1 scripts would fail with `ModuleNotFoundError`) | 1.1, 1.2 |
| 2 | Removed the "thousands of steps per second" claim. Added a speed benchmark gate and optimization tips | Step 11 |
| 3 | Removed the "wrap as VMAS with almost no changes" claim. Part 2 uses a PettingZoo/TorchRL-style wrapper, which is real work | Section 0 |
| 4 | Thermal sensing is now directional (4 sectors), so a policy can tell which way a victim is | Step 8, 3.1 |
| 5 | Added acoustic sensing (the problem statement requires thermal and acoustic) | Step 8 |
| 6 | `flood_fill` replaced by `bfs_distances` (Step 4 needs distances, not just a mask) | Step 3 |
| 7 | Coverage formula fixed (v1 could exceed 100%) | Step 10 |
| 8 | Spawn area starts at (1,1), not (0,0), so it does not overlap the border wall | 2.1 |
| 9 | `types.py` renamed `robot_types.py`; headless pygame note added | 1.2, Step 12 |
| 10 | Added missing test files, movement conflict rules, assumptions list, optional maze layout | Steps 6, 14, Section 4 |
| 11 | Rubble size reduced, battery made a real constraint, map rejection rate is now tested | 2.1, 2.2, Step 14 |

## 0. Scope and Rules

**Goal of Part 1:** a deterministic, seedable 2D disaster world with random walls and rubble, hidden victims, rovers with local vision only, fog of war, thermal and acoustic sensing, metrics, and a pygame visualizer. No learning yet.

**Design principles**

- Simple grid world, discrete moves, rovers only. Drones come later through a config entry, not new code.
- Everything is driven by config files and one random seed, so any run can be reproduced.
- Separate the true world (ground truth) from what each robot knows (its belief map). This is the GPS-denied part.
- Keep the engine free of drawing code and keep observations as separate fields, so Part 2 can wrap it.
- Performance matters: PPO needs millions of environment steps. At 1,000 steps per second, 1 million steps takes about 17 minutes on one core (estimate), so the engine must hit that floor (Step 11).

**About Part 2 (honest note):** VMAS scenarios are written as batched PyTorch code, so this grid engine cannot simply be dropped into VMAS. The realistic route is a PettingZoo-style wrapper plus parallel worker processes, using TorchRL/BenchMARL or another MARL library. Check the library docs for how to add a custom environment before the hackathon. Expect this wrapper to take a few hours.

**Hackathon rule:** all work must be created during the event. Before the 31st you may only install tools, run library demos, and plan on paper.

## 1. Folder Setup

### 1.1 Create the project

On Windows (PowerShell) or inside Ubuntu:

```
mkdir swarm-sar
cd swarm-sar
python -m venv .venv
```

Activate: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Ubuntu). Then create `pyproject.toml` (below) and run:

```
pip install -e .
pip freeze --exclude-editable > backend/requirements.txt
git init
```

`pyproject.toml`:

```
[project]
name = "swarm-sar"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["numpy", "pyyaml", "pygame", "matplotlib", "pytest"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

After `pip install -e .`, `import swarm_sar` works from any script or test.

### 1.2 Folder structure

```
swarm-sar/
  README.md
  pyproject.toml
  backend/requirements.txt
  .gitignore
  configs/
    world.yaml
    robots.yaml
    sim.yaml
  simulation/src/swarm_sar/
    __init__.py
    world/
      __init__.py
      cells.py          # cell type constants
      generator.py      # random map creation (cave, optional maze)
      reachability.py   # BFS distances, cleanup
      victims.py        # victim placement
    robots/
      __init__.py
      robot.py          # Robot class and state
      robot_types.py    # loads robot type configs
    sensing/
      __init__.py
      vision.py         # line of sight, fog of war update
      victim_sensor.py  # thermal, acoustic, confirmation
    sim/
      __init__.py
      engine.py         # reset, step, termination
      metrics.py        # coverage, victims, collisions
    viz/
      __init__.py
      renderer.py       # pygame drawing
    utils/
      __init__.py
      config.py         # YAML loading
      rng.py            # seeded random generator
  scripts/
    view_world.py       # generate and show maps
    play_manual.py      # keyboard control for testing
    run_random.py       # random-walk rollout with metrics
    benchmark.py        # steps-per-second check
  tests/
    test_generator.py
    test_reachability.py
    test_victims.py
    test_movement.py
    test_vision.py
    test_sensing.py
    test_engine.py
  training/runs/              # CSV logs, screenshots (git-ignored)
  docs/                 # architecture notes, diagrams
```

### 1.3 `.gitignore`

```
.venv/
__pycache__/
*.pyc
*.egg-info/
training/runs/
.ipynb_checkpoints/
```

### 1.4 Git habits

- First commit: empty structure, `pyproject.toml`, `backend/requirements.txt`, README title.
- Commit after every numbered step in Section 3. Message format: `world: add bfs distances`.
- Use one branch per teammate task if more than one person edits at once.
- Tag a working version when done: `git tag part1-done`.

### 1.5 README skeleton

Title, one-paragraph problem statement, how to run (`python simulation/scripts/view_world.py`), folder map, the assumptions list from Section 4, current status checklist. Update it at the end of each part.

## 2. Configuration Files

### 2.1 `configs/world.yaml`

| Key | Starting value | Meaning |
|---|---|---|
| `layout` | cave | `cave` (default) or `maze` (optional labyrinth mode) |
| `width`, `height` | 48, 48 | Grid size. Use 32 for fast debugging |
| `wall_fill` | 0.42 | Initial random wall probability for cave generation (untested, tune it) |
| `smoothing_steps` | 4 | Cellular automata passes |
| `border_walls` | true | Solid outer boundary |
| `rubble_patches` | 6 | Number of rubble blobs |
| `rubble_patch_radius` | [2, 4] | Radius range of each blob |
| `spawn_origin` | [1, 1] | Top-left cell of the spawn square (inside the border) |
| `spawn_size` | 3 | Side of the spawn square |
| `num_victims` | 4 | Victims per map |
| `victim_min_dist_from_spawn` | 12 | BFS path distance, in cells |
| `victim_min_dist_between` | 5 | Euclidean distance, in cells |
| `min_free_ratio` | 0.45 | Reject maps that are too closed in |
| `max_generation_retries` | 20 | Then raise an error |

### 2.2 `configs/robots.yaml`

```
rover:
  speed: 1
  vision_radius: 3
  thermal_radius: 6
  thermal_decay: 3.0
  thermal_noise: 0.05
  acoustic_radius: 10
  acoustic_decay: 6.0
  acoustic_noise: 0.10
  acoustic_wall_factor: 0.4
  confirm_radius: 2
  battery: 300
  move_cost: 1.0
  rubble_cost: 2.0
  idle_cost: 0.1
  can_cross_rubble: true
  can_cross_walls: false
  comm_radius: 8
```

Every robot property lives here. A drone is added later as a second block (`drone:`) with larger speed and vision. With `battery: 300` and `max_steps: 400`, a rover that moves every step runs out of battery around step 300, so efficiency matters. Set it to 1000 to effectively disable battery.

### 2.3 `configs/sim.yaml`

`num_rovers: 5`, `max_steps: 400`, `seed: 0`, `end_when_all_found: true`, `render_cell_px: 16`, `fps: 10`, `local_window_radius: 3` (the observation window is `2*radius+1` cells wide, matching the vision radius).

## 3. The Python World: Step by Step

Each step has a goal, what to write, and a check that tells you it works. Do them in order and commit after each.

### Step 1: Cell types and config loading (20 min)

- `cells.py`: constants `FREE=0`, `WALL=1`, `RUBBLE=2`, `UNKNOWN=-1`.
- `config.py`: `load_config(path)` returns a dict from YAML.
- `rng.py`: returns `numpy.random.default_rng(seed)`. The engine owns one generator and passes it to every function that needs randomness. No other random source anywhere.
- **Check:** loading each YAML prints the expected dict.

### Step 2: Random map generator (45 min)

Cave method, which looks like collapsed rooms:

1. Fill a grid randomly: each cell is WALL with probability `wall_fill`.
2. Force the border to WALL.
3. Repeat `smoothing_steps` times: a cell becomes WALL if 5 or more of its 8 neighbours are WALL (cells outside the grid count as WALL), otherwise FREE.
4. Clear the spawn square (starting at `spawn_origin`) to FREE.
5. Add rubble: pick random FREE centers, mark cells within a random radius from `rubble_patch_radius` as RUBBLE (only where currently FREE, never on the spawn square).
6. Return an integer numpy array of shape (height, width), indexed `grid[y, x]`.

- **Check:** `view_world.py` shows 10 maps from 10 seeds. They should look like caves with scattered rubble. The same seed must always give the same map.
- **Optional (30 min, only if time remains): `layout: maze`.** Use a recursive-backtracker maze on an odd-sized grid, then knock out about 5 percent of interior walls to create loops, so rovers can route around each other. This gives the "labyrinthine" look from the problem statement.

### Step 3: BFS distances and cleanup (35 min)

`reachability.py`:

- `bfs_distances(grid, start)`: BFS over non-WALL cells (4-neighbour). Returns an integer array of the same shape, with `-1` for unreachable cells and the path length otherwise. Reachable mask is `dist >= 0`.
- After generating, run it from the spawn center. Convert every unreachable FREE or RUBBLE cell into WALL, so no area is cut off.
- Reject and regenerate if the reachable non-wall ratio is below `min_free_ratio`. Retry up to `max_generation_retries` times (each retry keeps drawing from the same generator, so it stays deterministic), then raise an error.
- **Check:** unit test that every non-wall cell is reachable from spawn on 100 seeds.

### Step 4: Victim placement (30 min)

`victims.py`:

- Candidate cells: reachable, FREE (not rubble), with BFS distance from spawn of at least `victim_min_dist_from_spawn`.
- Pick `num_victims` candidates at random, rejecting any closer than `victim_min_dist_between` (Euclidean) to an already chosen victim.
- Store as a list of dicts: `{id, x, y, found: False, found_by: None, found_step: None}`.
- **Check:** all victims are reachable and respect both distance rules, on 100 seeds.

### Step 5: Robot class (30 min)

`robot.py` fields:

- `id`, `type`, `x`, `y`, `battery`, `alive`
- `belief`: array of shape (height, width), `UNKNOWN` or the cell type once seen (private to this robot)
- `visited`: boolean array of cells this robot stepped on
- `last_action`, `collided` (bool, this step), `distance_travelled`

Spawn robots on distinct free cells inside the spawn square (a 3x3 square has 9 cells for 5 rovers).

### Step 6: Movement rules (40 min)

Actions: `0` stay, `1` up, `2` down, `3` left, `4` right.

Process robots one at a time in a random order (re-shuffled every step, using the engine's generator):

1. Skip robots that are not alive.
2. Compute the target cell.
3. If the target is outside the grid or WALL: stay, `collided = True`.
4. If the target is occupied by another living robot: stay, `collided = True`.
5. Otherwise move. Battery cost is `move_cost`, or `rubble_cost` if the target is RUBBLE. Staying costs `idle_cost`.
6. If battery reaches 0: `alive = False`.

Because robots are processed sequentially, two robots can never swap cells (the second one sees the first one's cell as occupied only if the first did not move, so a swap attempt ends in a blocked move). Dead robots are removed from occupancy and do not block cells (documented simplification).

- **Check:** tests for wall bump, edge bump, two robots targeting the same cell (only one moves), swap attempt blocked, rubble costing more battery, dead robot not blocking.

### Step 7: Vision and fog of war (50 min)

`vision.py`:

- For each robot, cells within `vision_radius` (Euclidean circle) are candidates.
- Line of sight uses Bresenham lines. If a WALL lies strictly between the robot and the cell, the cell is hidden. The wall itself is visible.
- Write the seen cell types into the robot's `belief`.
- Return the number of newly revealed cells (used later for the exploration reward).
- **Speed tip (do this now, it saves time at Step 11):** precompute once per radius the list of offsets in the disk and, for each offset, the intermediate cells on its Bresenham line. Pad the grid with a wall border of width equal to the largest radius, so no bounds checks are needed. Then one numpy indexing call per robot checks all lines of sight.
- **Check:** put a robot next to a wall and confirm the cells behind the wall stay UNKNOWN.

### Step 8: Victim sensing, thermal and acoustic (60 min)

`victim_sensor.py` has three parts. Both sensors use ground-truth victim positions internally, and each robot only receives the noisy numbers.

**Thermal (short range, directional, needs line of sight).**
For each robot and each victim within `thermal_radius` and with line of sight, compute `s = exp(-d / thermal_decay)`. Add `s` to one of four sectors (up, right, down, left) chosen by the dominant axis of the offset (victim minus robot). Add Gaussian noise (`thermal_noise`) to each sector and clip at 0. Output: 4 floats.

**Acoustic (longer range, no direction, passes through walls).**
For each victim within `acoustic_radius`, compute `s = exp(-d / acoustic_decay)`, multiplied by `acoustic_wall_factor` if line of sight is blocked. Sum over victims, add Gaussian noise (`acoustic_noise`), clip at 0. Output: 1 float.

Together, the acoustic reading says "someone is somewhere near" and the thermal sectors say "which way, once close". This is what makes sensing useful to a learning policy.

**Confirmation (discrete).**
A victim is marked found when a living robot is within `confirm_radius` with line of sight. Record `found_by` and `found_step`.

- **Check:** thermal sector values rise as a rover approaches a victim from that side, a wall between them blocks thermal but only weakens acoustic, and a victim beyond `acoustic_radius` produces noise only.

### Step 9: Simulation engine (45 min)

`engine.py`, class `SwarmWorld`:

- `reset(seed=None)`: generate the map, place victims, spawn rovers, clear beliefs, run the first vision update, return the observations.
- `step(actions)`: apply movement, run vision, run sensing, update metrics, then return `(observations, info, done)`.
- Termination: all victims found, all robots dead, or `max_steps` reached.
- No drawing code and no pygame import in this file.

Observation per robot (a dict of separate fields; Part 2 turns them into tensors):

| Field | Shape | Meaning |
|---|---|---|
| `local_map` | (2R+1, 2R+1) | Window of the robot's own belief centered on it, `UNKNOWN` outside the grid |
| `battery` | 1 | Fraction of full battery left |
| `thermal` | 4 | Noisy directional readings (up, right, down, left) |
| `acoustic` | 1 | Noisy omnidirectional reading |
| `prev_thermal`, `prev_acoustic` | 4, 1 | Previous step's readings, so a feed-forward policy can sense change |
| `rel_pos` | 2 | Position relative to spawn, scaled by map size (odometry, see assumptions) |
| `collided` | 1 | 1 if the last move was blocked |

Never include ground truth (true grid, victim positions) in observations.

- **Check:** `run_random.py` runs 100 episodes with random actions without error and prints the average metrics.

### Step 10: Metrics (25 min)

`metrics.py` tracks per episode:

- `victims_found`, `time_to_first_victim`, `time_to_all_victims`
- `coverage`: the number of cells known by at least one robot that are reachable and non-wall, divided by the number of reachable non-wall cells. This stays between 0 and 1.
- `collisions`: wall hits plus robot hits
- `distance_per_robot`, `battery_left`
- `coverage_over_time` and `victims_over_time` lists (for plots later)

Save one CSV row per episode into `training/runs/`.

### Step 11: Speed benchmark and optimization gate (45 min)

`simulation/scripts/benchmark.py`: 48x48 map, 5 rovers, random actions, no rendering, 5,000 steps total (resetting when an episode ends). Report environment steps per second, where one step moves all 5 rovers.

- **Gate: at least 1,000 steps per second on one core.** This is a target, not a measured fact, so run it and see.
- If below the gate: profile with `python -m cProfile -s cumtime simulation/scripts/benchmark.py`, then use the precomputed line-of-sight offsets from Step 7, avoid Python loops over cells, and as a last resort add `numba` to the hot functions.
- Do not move on to the visualizer until this passes. Slow environments make every training run slower.

### Step 12: Visualizer (60 min)

`renderer.py` with pygame:

- Draw the grid, one square per cell, `render_cell_px` pixels.
- Colors: WALL dark grey, FREE light grey, RUBBLE brown, UNKNOWN black, victims red (shown only once found, or in a debug toggle), rovers in distinct colors with their id as a number.
- Two views toggled with `G`: **Known map** (union of all robot beliefs, the default) and **Ground truth** (for debugging).
- Faint vision circles toggled with `V`.
- A side panel with step count, victims found out of total, coverage percent, and battery bars per rover.
- Support an `rgb_array` mode that returns the frame as a numpy array, so you can save a GIF or video later. On servers without a display (Colab), set `SDL_VIDEODRIVER=dummy` before importing pygame.
- **Check:** `view_world.py` looks right at 32x32 and 48x48.

### Step 13: Manual play and random baseline (30 min)

- `play_manual.py`: arrow keys move the selected rover, `TAB` switches rover, the others stay still. Use it to feel the sensing, find a victim yourself, and confirm the rules.
- `run_random.py`: random actions for all rovers, prints and saves the metrics. This is your first baseline number and is reused in the final comparison charts.

### Step 14: Tests (50 min)

Run with `pytest -q`.

- `test_generator.py`: same seed gives the same map, border is wall, spawn square is free, and the rejection rate over 200 seeds is below 20 percent (if not, tune `wall_fill`).
- `test_reachability.py`: no unreachable non-wall cells, distances correct on a small hand-made grid.
- `test_victims.py`: victims reachable, both distance rules respected, found flags update.
- `test_movement.py`: wall, edge, collision, swap, rubble cost, battery death.
- `test_vision.py`: walls block line of sight, radius respected, newly revealed count correct.
- `test_sensing.py`: thermal directional and blocked by walls, acoustic weakened by walls, noise-only beyond range, confirmation radius.
- `test_engine.py`: reset and step output shapes, termination works, same seed gives identical episodes with the same actions, no ground-truth fields in observations.

## 4. Assumptions to Write in the README

State these openly. Judges respect a clear list of simplifications.

1. All rovers share one coordinate frame anchored at the spawn area. Map merging in later parts depends on this.
2. Odometry (`rel_pos`) is noiseless in Part 1. Drift can be added later as an optional feature.
3. Time is discrete and every move is exactly one cell.
4. Dead rovers do not block other rovers.
5. Rovers cannot swap cells, and no collision damage is modeled.
6. Beliefs are private in Part 1. Communication and map merging come in a later part.
7. The world is 2D and sensing is simulated, so this is a validated simulation prototype, with ROS 2 and Gazebo as the deployment path.

## 5. Definition of Done for Part 1

- [ ] `pip install -e .` works and `python simulation/scripts/view_world.py` shows a new cave map for each seed
- [ ] The same seed always reproduces the same map, victims, and episode
- [ ] Every non-wall cell and every victim is reachable from spawn
- [ ] 5 rovers spawn together, move by the rules, and never overlap
- [ ] Fog of war works, and walls block vision
- [ ] Thermal is directional and blocked by walls, acoustic is omnidirectional and passes through walls with attenuation
- [ ] Victims are found only by confirmation inside `confirm_radius` with line of sight
- [ ] Observations contain no ground truth
- [ ] `benchmark.py` reports at least 1,000 steps per second (or you have a written reason and a plan)
- [ ] `play_manual.py` lets you drive a rover and find a victim
- [ ] `run_random.py` completes 100 episodes and writes a metrics CSV
- [ ] `pytest` passes
- [ ] Everything committed and tagged `part1-done`

**Gate to check at the start of Part 2:** the frontier-exploration baseline should find at least 90 percent of victims within `max_steps`. If it cannot, the task is too hard for RL as well. Raise `max_steps`, shrink the map, or reduce rubble before training anything.

## 6. Time Estimate

| Block | Time |
|---|---|
| Folder setup, `pyproject.toml`, configs, git | 35 min |
| Steps 1 to 4 (config, map, BFS, victims) | about 2 h 10 min |
| Steps 5 to 8 (robots, movement, vision, sensing) | about 3 h |
| Steps 9 to 11 (engine, metrics, speed gate) | about 1 h 55 min |
| Steps 12 to 13 (visualizer, manual play, random baseline) | about 1 h 30 min |
| Step 14 (tests) | 50 min |
| **Total** | **about 10 hours of work, or 5 to 6 hours with two people in parallel** |

The optional maze layout adds about 30 minutes. These are estimates, so add buffer for debugging.

**Splitting between teammates:** one person does Steps 2 to 4 (map and victims), another does Steps 5 to 8 (robots and sensing), then the engine, speed gate, visualizer and tests are done together.

## 7. Common Mistakes to Avoid

- Calling `random` or `numpy.random` directly, which breaks reproducibility. Always use the engine's seeded generator.
- Letting the engine import pygame. Rendering stays in `viz/`, or training will crash on headless servers like Colab.
- Leaking ground truth into observations. A robot may only read its own belief and its own sensor readings.
- Generating maps with cut-off areas, which makes some victims impossible to find and ruins training.
- Hard-coding rover numbers (speed, radius) in the code instead of the YAML.
- Making the map large too early. Debug on 32x32 with 3 rovers first.
- Skipping the speed benchmark. A slow environment is the most common reason RL runs do not finish.
- Using `grid[x, y]` in some places and `grid[y, x]` in others. The convention in this plan is `grid[y, x]` everywhere.

## 8. Hooks for the Next Parts

- `comm_radius` is already in the robot config, so map merging between nearby rovers can be added inside the engine's step.
- Robot types come from a config dict, so a drone block can be added without changing core logic.
- Observations are separate fields, so Part 2 can turn them into tensors for a policy network.
- The `info` dictionary returned from `step` is ready to carry reward components.
- `rgb_array` rendering is ready for demo videos.
- `prev_thermal` and `prev_acoustic` are already in the observation, so a plain feed-forward policy can start learning before you add recurrence.

*Next parts to plan: baselines (frontier exploration), RL environment wrapper, reward design, training, communication, demo and submission.*
