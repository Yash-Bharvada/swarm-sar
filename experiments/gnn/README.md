# GNN-PPO experiment: implementation and GPU runbook

**Status:** CPU-validated experimental implementation. CUDA training and full-budget candidate evaluation are pending. The active browser still uses the original verified PPO checkpoint. The smoke-trained GNN candidate regressed in a shortened diagnostic and was not promoted.

Read the [one-night plan](../../docs/planning/gnn_overnight_plan.md) and [validation report](../../docs/audits/gnn_implementation_validation.md) before running a long job.

## What is implemented

Each robot constructs a receiver-local star graph from its own features and the eight peer slots already present in the 229-value observation. A peer edge exists only for a valid, delivered advertisement. Query/key attention aggregates encoded messages over that graph. A self edge makes disconnected operation well-defined.

The graph's output is projected into a residual on the existing PPO input, then processed by the existing LSTM and masked action head. The new projection starts at zero so the original actors can warm-start the candidate with identical initial decisions. Both the existing policy and graph branch train during PPO; the trunk is not frozen. No additional graph package or simulator rewrite is required.

This is one-hop learned message aggregation, not a learned transmitter or radio-routing policy. It does not automatically reduce bandwidth, perform SLAM or create messages across a partition. The full hybrid policy retains ordered peer inputs and an eight-peer cap; only the graph aggregation branch is invariant to peer reordering.

| File | Responsibility |
|---|---|
| `attention.py` | Masked star-graph attention and initially zero residual |
| `module.py` | RLlib PPO integration, action-mask preservation and strict original-weight transfer |
| `config.py` | Opt-in recurrent rover/drone PPO specs |
| `smoke.py` | Verified original/checkpoint restore and identical zero-residual mission replay |
| `preflight.py` | Actual actor/critic/graph backward passes on CPU or required CUDA |
| `pilot.py` | Bounded PPO process, worker sync, graph-specific optimizer checks, verified saves and resume |
| `artifacts.py` | File/source integrity and paired-case admission checks |
| `evaluate.py` | Original PPO versus GNN, expert/random/first-legal references and optional graph-disabled ablation |

All commands run from the **repository root**, because `experiments` and `training` are imported from there. Transfer this code along with the full project to the training host; the earlier source ZIP predates these changes. The normal Python package install alone does not package this experiment directory.

## When to start GPU training

The local implementation checks have passed. **You can now move this exact source snapshot to the NVIDIA host and run the CUDA preflight.** Start a small GPU smoke only if preflight passes, then a bounded pilot only if the smoke records real updates for both graph encoders and verifies its checkpoints.

Do not start an all-night continuation immediately. Evaluate the pilot against original PPO first. If it regresses, retain the original model and investigate rather than spending the rest of the night automatically. This implementation has no automatic model-promotion path.

### 1. Prepare the existing GPU environment

Use the project's compatible NVIDIA/Python/Ray/Torch environment. Verify it has CUDA support; the local Mac cannot validate that. Set CPU thread counts before starting Ray:

```bash
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
nvidia-smi
```

Commands below use `.venv-gpu/bin/python`; replace that path consistently if the host already uses a differently named environment. The supplied checkpoint extraction workflow requires Python 3.12+.

If the selected checkpoint has not been extracted on that host, run the existing checksum/path-validated preparation:

```bash
.venv-gpu/bin/python -c 'from backend.ppo_service import DEFAULT_CHECKPOINT, prepare_checkpoint; prepare_checkpoint(DEFAULT_CHECKPOINT)'
```

This writes under ignored `training/runs/`; it does not train or replace the selected bundle. An incomplete existing extraction is rejected and must be inspected.

### 2. CUDA preflight: start here

```bash
.venv-gpu/bin/python -m experiments.gnn.preflight --gpu
```

Required: both policies report CUDA, finite gradients and `graph_encoder_updated: true`. This uses throwaway modules; saved actors remain unchanged. If CUDA is unavailable, it fails instead of silently falling back to CPU. Its memory numbers describe a tiny backward-pass check, not the production batch.

### 3. GPU smoke: allow up to ten minutes

```bash
.venv-gpu/bin/python -m experiments.gnn.pilot \
  --execute --gpu --smoke --runners 2 \
  --max-seconds 600 \
  --output training/runs/gnn_cuda_smoke_01
```

This runs three small PPO iterations with short episodes. Check:

- `run/summary.json`: `cuda: true`, `weights_updated: true`, all four encoder/residual update flags true.
- `run/checkpoint_index.json`: a verified latest checkpoint.
- `run/history.json`: finite losses, advancing steps, no health failures and observed CUDA memory usage.
- `pipeline_history.json`: supervised process finished successfully.

Short episodes and tiny batches are correctness checks. Their reward, recall and throughput must not be represented as full training performance. Every output directory must be fresh; commands refuse to overwrite prior evidence.

### 4. Real GPU pilot: cap at 30 minutes initially

```bash
.venv-gpu/bin/python -m experiments.gnn.pilot \
  --execute --gpu --runners 4 --epochs 1 \
  --target-steps 25000 --max-seconds 1800 \
  --output training/runs/gnn_gpu_pilot_01
```

This starts a **fresh warm-started experiment**, not a continuation of the tiny smoke curriculum. It uses the normal randomized training domains and 400-step episodes. The conservative pilot uses four rollout runners and one optimizer epoch per batch; these are experiment settings, not a proven optimal configuration. Default batch size is 16,384 environment steps, so the 25,000 target can overshoot to the next complete batch.

`--max-seconds` is a wall budget, not a promise to reach the target. The worker reserves time for saving, and an outer supervisor interrupts/kills stalled or over-budget work with a bounded shutdown grace. It may leave a last verified checkpoint without a successful final summary. Inspect status before continuing.

Training history records per-iteration environment steps/second and CUDA peak allocated/reserved memory. For device utilization and overall process memory, observe separately:

```bash
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total --format=csv -l 5
```

CPU simulation and A* can be the bottleneck. Increase runners only in a new, explicitly defined experiment after measuring resources. Do not assume all GPU memory is needed or that a larger GPU will make this workload proportionally faster.

### 5. Evaluate before continuing

Find the latest actual step in `run/checkpoint_index.json`. Its actor bundle is `run/actors/step_<12-digit-step>/`. Substitute that exact path below:

```bash
# Short pipeline diagnostic only: nine cohorts, two cases each, 48-step horizon.
.venv-gpu/bin/python -m experiments.gnn.evaluate \
  --candidate training/runs/gnn_gpu_pilot_01/run/actors/step_000000032768 \
  --output training/runs/gnn_gpu_diagnostic_01 --smoke --ablation

# Full configured development suite: required before judging continuation/promotion.
.venv-gpu/bin/python -m experiments.gnn.evaluate \
  --candidate training/runs/gnn_gpu_pilot_01/run/actors/step_000000032768 \
  --output training/runs/gnn_gpu_development_01 --ablation
```

The step `32768` is illustrative; use the saved step, not an assumed filename. Evaluation runs on CPU even from a CUDA-enabled environment. It does not start a Ray cluster or use final seeds.

Outputs include original PPO, GNN-PPO, three reference controllers and optionally the trained trunk with graph output disabled. Comparisons reject mismatched budgets, cohorts, fleet/network settings, seeds and survivor totals. Existing quality gates report numerical failures and large regressions; passing them alone is not proof of an improvement. Both evaluations report `automatically_promoted: false`.

The full default evaluation uses nine cohorts × eight cases for each of six conditions when `--ablation` is selected: original PPO, GNN, expert, random legal, first legal, and graph-disabled GNN. That is **432 missions**. Allow measured evaluation time before the presentation; do not fill the entire night with training.

### 6. Resume only a qualified GNN checkpoint

After reviewing a full-budget paired result, a bounded continuation can use:

```bash
.venv-gpu/bin/python -m experiments.gnn.pilot \
  --execute --gpu --runners 4 --epochs 1 \
  --resume training/runs/gnn_gpu_pilot_01/run/checkpoints/step_000000032768 \
  --target-steps 100000 --max-seconds 3600 \
  --output training/runs/gnn_gpu_continue_01
```

The target is **total lifetime steps in this GNN experiment**, not additional steps and not the original model's 753,664-step count. Use the exact saved path. Resume requires the same effective configuration, device/runners and recorded source. It restores the full algorithm checkpoint and training seed schedule; it does not promise exact replay of partially completed environment episodes from before shutdown. Resume rejects the original baseline checkpoint, changed sources, corrupted artifacts and incompatible configuration.

## What is validated locally

- All **211 Python tests**, including eleven GNN checks, passed in one run; all **148 frontend tests** passed.
- Zero-residual warm start matched the original 400-step mission exactly: seed 10000, four survivors, 94 steps, 90.48% coverage, plus identical restored replay.
- Three real CPU PPO iterations updated both graph encoders and residual heads; checkpoint hashes matched restored actors.
- Full-checkpoint resume advanced 384 → 768 steps with additional graph updates.
- Two remote CPU rollout workers also sampled and trained successfully.
- A shortened paired/ablation evaluation executed **108 missions** without invalid learned actions or post-shield collisions. The smoke-trained GNN was worse than original PPO and received a pause decision. It remains unpromoted.

The old GPU release manifest predates nine already-committed experiment scripts, so its whole-tree verifier fails on those additions. The 30-file historical baseline and gpu-v1 contract still verify. We leave historical records unchanged; the GNN saves a separate manifest covering its current dependencies and experiment code. Hashes establish identity/integrity, not authorship or security against a malicious checkpoint creator.

No CUDA run, long training, full-budget GNN comparison, new ROS learned controller or browser GNN activation has been performed. Existing weights, core simulator, sensor contract, frontend runtime and training release files were not modified by this experiment.

## Frontend handoff after training

First produce a qualified artifact and full development comparison. Then add an explicit GNN-PPO selection, versioned verified model serving and actual receiver-attention telemetry tied to sender IDs and inference step. The simulator scene can stay the same. Never infer attention from distance, fabricate weights or label the existing PPO as GNN. Attention weights indicate associations, not causal percentages. Until this stage is complete, use the original browser mode and inspect GNN output offline.
