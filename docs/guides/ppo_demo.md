# Saved PPO mission demonstration

`simulation/scripts/demo_ppo.py` runs actual CPU inference with the selected recurrent
rover/drone policies. It does not train, create Ray workers, change the
observation interface or automatically connect PPO to the browser/ROS demo.
The tool lives outside the audited training-source directories.

The included [mission recording](../media/ppo_754k_seed10000.gif) and
[validation record](../validation/ppo_demo_validation.json) reproduce development seed 10000:
4/4 survivors in 94 steps, matching the handoff review episode. It is an
illustrative 2D Python grid view, distinct from the voxel browser's heuristic.
Robot beliefs determine policy actions; ground-truth display is operator-only.

## GPU server / Jupyter

Keep the original training checkout intact and create a separate demo worktree:

```bash
cd /root/swarm-training/swarm-sar
git fetch origin main
git worktree add --detach /root/swarm-training/swarm-demo FETCH_HEAD
cd /root/swarm-training/swarm-demo

PYTHONPATH="$PWD/simulation/src" /root/swarm-training/swarm-sar/.venv-gpu/bin/python simulation/scripts/demo_ppo.py \
  --checkpoint /root/swarm-training/swarm-sar/training/runs/gpu_continue_1m/checkpoints/step_000000753664 \
  --seed 10000 --output training/runs/ppo_demo_10000
```

This reuses the installed training environment and original checkpoint. No GPU
is needed for this inference example. On a headless server, it exports a GIF
without opening a display. In a Jupyter Python notebook cell, display it with:

```python
from IPython.display import Image, display
display(Image(filename="/root/swarm-training/swarm-demo/training/runs/ppo_demo_10000/mission.gif"))
```

The output also contains `demo_manifest.json`, `metrics.json`, `map.json`,
`events.json` and `trajectories.csv`. The manifest identifies restored parameter
hashes, checkpoint digest, viewer code hash, environment settings and seed.
An existing output directory is refused; use a new output name for each run.
Don't repeat worktree creation after it succeeds.

## Local desktop

With this repository's Python dependencies installed and the verified handoff
already extracted into `training/runs/ppo_754k_handoff`, run from the repository root:

```bash
.venv/bin/python simulation/scripts/demo_ppo.py --live --seed 10000 --output training/runs/ppo_demo_live
```

A Pygame window opens. V toggles sensor ranges, G toggles operator ground truth,
and Q/Escape exits and saves the partial mission with `interrupted: true`.
Without `--live`, the same command exports a GIF using a headless renderer.
Pillow and Pygame are provided by the existing dependency environment.

Only development seeds are accepted. Change `--seed`, `--rovers`, `--drones`,
`--world-size`, `--layout` or `--no-network` for clearly labelled illustrative
missions; a changed scenario is not the original fixed evaluation benchmark.
Frame rate and frame stride affect playback, not policy decisions or mission
budgets. Reports/GIFs do not claim calibrated sensors or physical rescue.
