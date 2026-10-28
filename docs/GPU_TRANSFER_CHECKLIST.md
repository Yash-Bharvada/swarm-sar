# GPU training transfer checklist

This is the fail-closed handoff for the A5000 run. Do not launch a long PPO
job until every preflight and smoke command below passes.

## Immutable identities

- GPU-v1 policy contract SHA-256:
  `c5dff01368e1bb3a77112884c5d545457830097b11aefe54e0d412fc874c57c5`
- Expert manifest SHA-256:
  `b4afe76df70480e24dba15ecc6b526044647fa94fd2efffbeefdbb2271fd2857`
- Expert contents: 811,652 decisions, 2,000 seeds, 17 chunks, all seven
  actions, 4,966/4,970 survivors.
- The release commit is the commit pointed to by the annotated
  `gpu-v1-training-ready` tag. Verify with `git rev-parse HEAD` and
  `git rev-list -n 1 gpu-v1-training-ready`.

## 1. Clone and environment

```bash
git clone https://github.com/rashiyaom/swarm-sar.git
cd swarm-sar
git checkout gpu-v1-training-ready
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

The expert data is intentionally not committed to Git. Either copy the exact
`results/expert_train_gpu_v1/` directory from the Mac, or deterministically
regenerate it on the server:

```bash
python scripts/export_step4_expert.py --episodes 2000 --chunk-size 50000 \
  --output results/expert_train_gpu_v1
```

Never reuse a partial output directory.

## 2. Strict preflight

```bash
python scripts/preflight_gpu.py --dataset results/expert_train_gpu_v1
python -m pytest -q
python scripts/freeze_training_baseline.py --verify
python scripts/verify_policy_contract.py
```

Preflight must report `passed: true`, a clean worktree, CUDA available, at
least 20 GiB VRAM and the exact hashes above. One RTX A5000 is expected; NVLink
does not add value unless a second GPU is installed.

## 3. Behavior-cloning warm start

First run the two-batch GPU plumbing smoke:

```bash
python scripts/train_behavior_cloning.py \
  --dataset results/expert_train_gpu_v1 \
  --output results/bc_gpu_smoke --smoke --num-cpus 4 --num-gpus 1
```

Then run the real sequence-aware, class-weighted rover/drone clone:

```bash
python scripts/train_behavior_cloning.py \
  --dataset results/expert_train_gpu_v1 \
  --output results/bc_gpu_v1 --num-cpus 8 --num-gpus 1
```

Continue only if `summary.json` says `passed: true`, both initial/final hashes
differ, each validation balanced accuracy is at least 0.40, and each train vs
validation gap is at most 0.15. Raw accuracy is not an acceptance metric.

## 4. PPO handoff smoke and intensive run

```bash
python scripts/train_step3.py --config configs/training_gpu_a5000.yaml \
  --resume results/bc_gpu_v1/checkpoint --smoke \
  --num-cpus 4 --num-env-runners 2 --num-gpus-per-learner 1 \
  --output results/ppo_gpu_smoke
```

Confirm `weights_updated: true`, then launch:

```bash
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
python scripts/train_step3.py --config configs/training_gpu_a5000.yaml \
  --resume results/bc_gpu_v1/checkpoint \
  --output results/gpu_v1_run_001
```

Inspect `heartbeat.json` after every iteration. A full cohort report runs every
250,000 environment steps or every hour, whichever comes first. The run writes
a numbered checkpoint before each
gate. `PAUSED.json` means review the recorded quality reason and resume only
after diagnosis; `ABORTED.json` means the run encountered a hard integrity
failure. Never bypass a gate merely to reach five million steps.

## 5. Anti-overfitting evidence

Training samples seeds 0–9,999. BC validation uses seeds 1,800–1,999 and PPO
does not use those labels. Online evaluation uses only development seeds
10,000–10,099: four fixed seeds plus four rotating seeds over six cohorts.
Final seeds 20,000–20,199 remain sealed until model and hyperparameters are
frozen. Report the final range exactly once for the chosen candidate.

Archive the repo commit, BC summary, training definition, checkpoint index,
all cohort JSON files, heartbeat/termination marker, and final checkpoint.
