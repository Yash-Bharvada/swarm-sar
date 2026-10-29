# Repository guide

Run Python commands from the repository root. Install the package with
`python -m pip install -e .`; after updating an existing checkout, repeat this
command so its editable installation points to `simulation/src`.

```text
frontend/                 React/Vite mission control and browser simulation
backend/                  Python HTTP service for saved PPO inference
simulation/
  src/swarm_sar/           Python simulator and shared learning library
  scripts/                 Viewers, baselines, benchmarks and simulation audits
  ros2_ws/                 ROS 2 packages, Gazebo models and launch files
training/
  configs/                 Training, evaluation, seed splits and quality gates
  scripts/                 Dataset export, BC/PPO training and GPU orchestration
  datasets/                Expert demonstration chunks and manifests
  artifacts/               Training summaries, contracts and integrity records
  runs/                    Generated runs, logs and extracted handoffs (ignored)
models/                    Shipped PPO models and frozen Step 3 checkpoint
configs/                   Shared world, robots, sensors and network settings
docs/                      Reports, guides, architecture, audits and media
tests/                     backend/, simulation/, training/ and ros2/ tests

```

The Python import name remains `swarm_sar`. Its `learning/` module stays beside
the simulator because training and inference both depend on the same environment,
observation encoding, and policy contract. Training commands, configuration,
datasets, and outputs have their own `training/` directory.

## Common commands

```bash
python -m pip install -e .
python -m backend.ppo_service
python simulation/scripts/view_world.py
python training/scripts/train_step3.py
python training/scripts/run_gpu_pipeline.py --plan
python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run dev
```

Build ROS packages from `simulation/ros2_ws/` using `colcon build`, then source
`install/setup.bash` there. See [the physics demo](guides/physics_demo.md).

## Documentation

- [Real-capture gallery](gallery.md), [branch scope](branches.md), and [repository checks](validation/repository_checks.md)


- [Project report](project_report.md) and [problem statement](problem_statement.md)
- [Architecture](architecture/architecture.md)
- `guides/`: setup, demos, frontend integration and GPU transfer
- `audits/`: engineering, readiness and milestone reviews
- `validation/`: recorded browser and PPO validation JSON
- `planning/`: implementation plans and original development prompts
- `reference/`: original implementation blueprint and file relocation map
- `evidence/`: captured ROS logs and measurements
- `media/`: demo animation, original simulation screenshots and their ZIP
- `reports/`: generated PDF reports; generator in `scripts/`

Historical JSON, logs, model metadata and archives retain their recorded paths
and hashes. Use [the relocation map](reference/structure-moves.json) to locate
files referenced by those records. Baseline file hashes remain unchanged; its
manifest source path and the current training source manifest follow this layout.

Put new application code in the component that owns it, keep model bundles in
`models/`, datasets in `training/datasets/`, and generated run output in
`training/runs/`. Keep shared runtime settings in root `configs/` and training
settings in `training/configs/`.
