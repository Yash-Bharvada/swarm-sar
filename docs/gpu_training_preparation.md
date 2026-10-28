# GPU-v1 training preparation

> Historical preparation record. The 29 October 2026 audit found additional
> full-launch and expert-data defects. Use
> [GPU_TRANSFER_CHECKLIST.md](GPU_TRANSFER_CHECKLIST.md) and the v2 data on
> `rashiyaom`; the old expert data and launch commands below are superseded.

## Status

Mac preparation Steps 1–8 were completed and validated on 28 October 2026.
The shipped Step 3 model remains frozen and reproducible; GPU-v1 is a new,
intentionally incompatible policy contract and must train from fresh weights or
a matching GPU-v1 imitation checkpoint.

## Completed safeguards

1. `artifacts/training_baseline_v1/manifest.json` freezes all 30 original Step 3
   files by byte length and SHA-256. The verifier refuses drift.
2. `artifacts/policy_contract_gpu_v1.json` freezes the 229-value observation and
   seven-action semantics under a canonical contract hash.
3. GPU-v1 adds previous action, active goal, mission progress and eight
   sender-sorted peer-message slots. All values are bounded and derived from
   agent state or delivered messages.
4. Ray CPU runners and learner GPU allocation are configurable. The A5000
   profile requests 20 environment runners, 28 CPUs and one learner GPU.
5. Training writes numbered checkpoints, an atomic checkpoint index, latest and
   best-development pointers, and supports `--resume`. Existing checkpoint
   directories are never overwritten.
6. Train, development and final seed ranges are immutable and disjoint. Ray
   worker indices receive interleaved training seeds without early duplicates.
7. Step 4 expert data is written as bounded compressed chunks with hashes,
   policy/action counts, episode provenance and independent validation. The
   exporter rejects NaNs, schema drift and masked expert actions.
8. Both 256-cell LSTM policies trained, checkpointed, restored, resumed and ran
   stateful inference on CPU during the Mac smoke gate.

## Mac verification commands

```bash
source .venv/bin/activate
pytest -q
python scripts/freeze_training_baseline.py --verify
python scripts/verify_policy_contract.py
python scripts/train_step3.py --config configs/training_gpu_a5000.yaml \
  --smoke --num-cpus 2 --num-env-runners 0 --num-gpus-per-learner 0 \
  --output results/mac_lstm_smoke
```

Generate a small dataset gate before a long export:

```bash
python scripts/export_step4_expert.py --episodes 2 --chunk-size 128 \
  --output results/expert_smoke
python scripts/validate_expert_dataset.py results/expert_smoke
```

Every exporter output directory is immutable: choose a new directory rather
than reusing a partial or completed dataset.

## A5000 launch command

First run the same smoke gate on the server with GPU allocation:

```bash
python scripts/train_step3.py --config configs/training_gpu_a5000.yaml \
  --smoke --num-cpus 4 --num-env-runners 2 --num-gpus-per-learner 1 \
  --output results/a5000_smoke
```

After verifying CUDA use, both policy deltas and checkpoint restore, launch the
full profile:

```bash
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
python scripts/train_step3.py --config configs/training_gpu_a5000.yaml \
  --output results/gpu_v1_run_001
```

Resume into a new output directory:

```bash
python scripts/train_step3.py --config configs/training_gpu_a5000.yaml \
  --resume /absolute/path/to/checkpoint \
  --output results/gpu_v1_run_001_resume
```

## Evidence from the preparation audit

- Complete suite: 92 passed.
- Original baseline: 30/30 artifact hashes verified.
- Full expert dataset: 811,652 decisions over 2,000 training-only seeds, both
  policies, all seven actions, 4,966/4,970 survivors and 17 independently
  verified chunks (128,390,937 compressed bytes). The complete dataset is at
  `results/expert_train_gpu_v1/`; its tracked compact summary is under
  `artifacts/gpu_v1/`.
- LSTM smoke: both 1,304,072-parameter modules updated; resume advanced lifetime
  sampling from 512 to 1,024 environment steps.
- Full Step 4 regression after the expert action-mask correction: 42/42
  survivors across 12 networked large-world missions, 16/16 at 30% loss, 17/17
  offline, zero collisions, exact replay, 200/200 transport properties and
  100/100 generation properties.

These are infrastructure and regression results, not evidence that the new
untrained LSTM already outperforms the frozen controller.

The expert action distribution is intentionally recorded rather than hidden:
action 0 represents 595,744 of 811,652 decisions. Supervised pretraining must
therefore use class-aware sampling or class weights and report per-action
accuracy, not accuracy alone.
