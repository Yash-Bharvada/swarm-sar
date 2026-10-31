# GNN implementation validation — 31 October 2026

**Decision:** the experimental implementation is ready for an NVIDIA-host CUDA preflight and bounded GPU pilot. It is not a qualified replacement for the selected PPO policy. The smoke-trained candidate regressed in short-horizon diagnostics and was not promoted.

The [GPU runbook](../../experiments/gnn/README.md) provides exact commands, evaluation gates and continuation instructions. The [overnight plan](../planning/gnn_overnight_plan.md) explains scope and intended frontend changes.

## Implemented architecture

`gnn-residual-v1` is a one-hop receiver-local star-graph attention encoder. It processes existing local features and eight delivered peer slots. Validity masking excludes unavailable peers; self attention allows no-peer operation. The graph output is a learned residual before the existing recurrent PPO actor/critic. Its initially zero projection preserves the selected baseline's initial logits and actions.

Rover and drone actors remain separate type-shared policies, with per-agent recurrent state. Existing transport loss/delay/TTL, local observations, planner, action masks, sensors and batteries remain in place. Both the original trunk and new graph parameters train. This is learned aggregation of structured received messages, not a learned transmission schedule, full-team global graph access, SLAM GNN or physical-radio implementation.

## Actual checks

| Check | Observed result |
|---|---|
| Full Python regression suite, with Xacro on PATH and permitted localhost HTTP binding | **211 passed**, no skips, two existing PettingZoo deprecation warnings; 15.94 seconds |
| Frontend regression suite | **148 passed**, 18 files |
| GNN behavioral tests within Python suite | **11 passed**: permutation-invariant graph branch, padding/no-peer, real gradients, recurrent/nonrecurrent masking and restore, actual delivered-message boundary, invalid input rejection, integrity rejection, paired-case mismatch rejection, graph-output ablation |
| Verified original actor warm start | Same seed-10000 trajectory: **4/4 survivors, 94 steps, 90.48% coverage**, horizon 400; exact trajectory hash and restored replay match |
| Direct CPU preflight | Both rover and drone graph encoders updated through three actor/critic backward passes with finite gradients |
| Real local-runner PPO smoke | Three iterations, **384 environment steps**; both graph encoders and residual heads updated; full checkpoint parameter hashes verified |
| Real checkpoint resume | Continued **384 → 768 lifetime steps**, with further graph updates and verified checkpoint saves |
| Distributed sampling | Two remote CPU rollout workers, three iterations, **384 steps**, successful graph updates and verified save |
| Paired/ablation evaluation plumbing | **108 completed diagnostic missions**: nine cohorts × two cases × six controller conditions, horizon 48; no invalid learned actions/post-shield collisions |
| Original gpu-v1 policy contract | Passed |
| Frozen historical baseline | All 30 files verified |

These smokes exercise real saved actors and real simulator episodes. The tests do not substitute a mock GNN for the optimizing learner. A zero-residual warm start establishes compatibility, not a learned improvement; optimizer updates establish learning mechanics, not rescue quality.

## Diagnostic results and release decision

The trained local smoke used tiny batches and a short 40-step training horizon. Its evaluation used two development cases per cohort and a shortened 48-step horizon. These conditions deliberately test mechanics quickly and do not reproduce the selected model's full development benchmark.

| Diagnostic controller | Survivors across 18 cases | Combined mean cohort recall |
|---|---:|---:|
| Original selected PPO | 17/43 | 33.24% |
| Smoke-trained GNN-PPO | 14/43 | 23.15% |
| Same trained trunk, graph residual disabled | 15/43 | 25.93% |

Pooled survivor recall and mean cohort recall have different denominators/weighting. The comparison also runs the policy-compatible expert, random legal actions and first-legal-action references. All cases use the same declared cohort settings; admission rejects missing/duplicate/reordered seeds, different fleets, network settings, survivor totals or budgets.

The existing quality gate returned **pause** for baseline-relative regression. Its inherited reason string is `regression_from_behavior_cloning`; in this experiment the supplied reference was original PPO, so read that label as regression from the reference model. The smoke-trained candidate is unpromoted. More GPU time is not presumed to fix it, and the original policy remains the demo model.

The evaluator supports a full configured development run and graph-disabled ablation. Full-budget paired results and additional training seeds are required before claiming useful GNN coordination. Final-test seeds remain sealed. No parameters were tuned against these diagnostic results during this validation.

## Issues found and handled

1. **Relative resume path:** PyArrow rejected a relative checkpoint URI. The experiment now resolves paths before restore. A subsequent run using the same relative CLI style successfully resumed and trained to 768 steps.
2. **Historical source manifest:** the original GPU release manifest omits nine scripts already committed at HEAD: `ablate_goal_governor.py`, `ablate_visibility.py`, `assess_development_benchmark.py`, `diagnose_large_maps.py`, `frontier_utility.py`, `frozen_development_benchmark.py`, `goal_governor.py`, `package_slam_handoff.py` and `visibility_frontiers.py`. Their bytes match HEAD and were not changed by GNN work. The historical manifest was not rewritten. GNN artifacts use separate source/file manifests covering both the experiment and existing dependencies.
3. **Interrupted validation processes:** earlier partial output directories remain preserved. Only completed reports identified below are claimed as successful evidence.
4. **Framework warnings:** Ray emitted existing deprecation/monitoring notices and a remote-worker object-store restart warning. The tested distributed run completed. Worker-failure recovery under that warning has not been established by this smoke.

## Preserved evidence

Compact results are stored in [artifacts/gnn_initial_validation](../../artifacts/gnn_initial_validation). Its [verification.json](../../artifacts/gnn_initial_validation/verification.json) indexes copied reports with source paths and hashes. Original full checkpoints and logs remain under ignored `training/runs/`:

- `gnn_warm_start_400_v2/`: original versus zero-residual trajectory/restore verification.
- `gnn_validated_cpu_v3/`: final local optimizer smoke, source definition, checkpoint and actor manifests.
- `gnn_resume_cpu_v3/`: full-checkpoint continuation evidence.
- `gnn_distributed_cpu_v3/`: two-worker sampling/update evidence.
- `gnn_evaluation_cpu_v3/`: complete diagnostic controller and paired/ablation reports.

Source manifests intentionally reject a modified experiment when loading a prior candidate. Preserve or restore the recorded source rather than changing its hashes to make verification pass. Hashes prove identity against the recorded artifact, not that an arbitrary serialized checkpoint is trustworthy.

## What remains before a live GNN demo

1. Run `preflight --gpu` on the NVIDIA host, then the short CUDA smoke; inspect both policy devices, gradients, memory and checkpoint results.
2. Run a bounded real-domain GPU pilot and stop for paired evaluation before any continuation.
3. If a candidate qualifies, implement versioned backend artifact admission and actual sender-linked attention telemetry; the existing service intentionally accepts only the original selected model.
4. Add the candidate's explicit frontend controller label and attention display, preserving the normal scene and packet-loss semantics. Do not show arbitrary attention animation.

No paid GPU was provisioned, CUDA job started, final evaluation opened, live ROS run performed or browser model switched in this implementation pass.
