# Training

- `scripts/`: dataset export and recovery, behavior cloning, PPO, evaluation,
  GPU preflight, release verification and pipeline orchestration.
- `configs/`: learning settings, evaluation cohorts, seed splits and gates.
- `datasets/`: expert demonstrations; the shipped GPU-v2 dataset is versioned.
- `artifacts/`: summaries, policy contracts and source/baseline manifests.
- `runs/`: generated output, logs and extracted checkpoint archives; ignored by Git.

Run commands from the repository root after `python -m pip install -e .`:

```bash
python training/scripts/run_gpu_pipeline.py --plan
python training/scripts/train_step3.py --config training/configs/training.yaml
python training/scripts/freeze_training_baseline.py --verify
python training/scripts/freeze_gpu_release.py --verify
```

Shipped model bundles live in `models/`. Shared learning modules remain under
`simulation/src/swarm_sar/learning/` to keep training and serving imports aligned.
See [GPU transfer instructions](../docs/guides/GPU_TRANSFER_CHECKLIST.md).
