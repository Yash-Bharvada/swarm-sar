# Frozen discovery baseline results — 30 October 2026

All 72 episodes completed in 172.7 seconds (about 2 minutes 53 seconds). Verified the frozen source/protocol lock, all 36 paired initial-state signatures, all expected cases and all 72 complete compressed traces. No rerun, training, confirmation-stage or final-seed access was performed during this inspection.

| Size | Layout | PPO survivors | Expert survivors | PPO completed missions | Expert completed missions |
|---|---|---|---|---|---|
| 32 | maze | 6/13 | 8/13 | 0/4 | 0/4 |
| 32 | rooms | 7/7 | 7/7 | 4/4 | 4/4 |
| 32 | cave | 10/10 | 10/10 | 4/4 | 4/4 |
| 56 | maze | 0/7 | 3/7 | 0/4 | 1/4 |
| 56 | rooms | 5/12 | 7/12 | 0/4 | 2/4 |
| 56 | cave | 10/11 | 10/11 | 3/4 | 3/4 |
| 64 | maze | 0/13 | 1/13 | 0/4 | 0/4 |
| 64 | rooms | 3/8 | 8/8 | 1/4 | 4/4 |
| 64 | cave | 6/10 | 10/10 | 0/4 | 4/4 |

These are fixed-resource development results, four seeds per stratum. They do not establish statistical superiority, sufficient large-map resources, or performance on sealed final cases. Confirmation remains reserved. See `artifacts/benchmark_discovery_baselines/verified_summary.json` for coverage and termination counts. The runner checks restored actor parameter hashes against the checkpoint and after each episode; this inspection validates its persisted results and traces rather than restoring the model again.
