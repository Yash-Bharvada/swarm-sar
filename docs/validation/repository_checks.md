# Repository verification · 29 October 2026

Local environment: macOS, Python 3.13, Node.js/npm and installed Chrome. This
record covers the organized full-project checkout. It is a repository check,
not a hardware, field-rescue, or new GPU training evaluation.

| Check | Result |
| :--- | :--- |
| Python suite | 160 passed, 2 ROS/xacro-dependent tests skipped; 2 PettingZoo deprecation warnings |
| Frontend suite | 140 tests passed across 16 files |
| Frontend production build | TypeScript and Vite succeeded |
| Frozen Step 3 baseline | All 30 file hashes verified |
| Policy contract | GPU-v1 SHA-256 `c5dff01368e1bb3a77112884c5d545457830097b11aefe54e0d412fc874c57c5` verified |
| Current training source manifest | Verified against relocated source/configuration paths |
| Expert dataset | 868887 rows, 18 chunks, 2000 episodes validated |
| GPU orchestration | `--plan` succeeded without starting training |
| Browser documentation capture | Real office/mine/apartment runs; PPO seed 10000 reproduced 4/4 at step 94; no page errors |
| Original evidence and binary preservation | 80 relocated binary/evidence files matched their prior Git bytes |

Commands from the repository root:

```bash
python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
python training/scripts/freeze_training_baseline.py --verify
python training/scripts/verify_policy_contract.py
python training/scripts/freeze_gpu_release.py --verify
python training/scripts/validate_expert_dataset.py training/datasets/expert_train_gpu_v2
python training/scripts/run_gpu_pipeline.py --plan
```

The current full-project source manifest was refreshed for the folder relocation.
Original GPU release source identity remains available in history and on the
isolated training branch/tag. Historical report hashes describe their original
runs, not this documentation update. Live Gazebo was not rerun on this Mac;
the gallery preserves the supplied host captures and log.
