# Audited GPU handoff: rashiyaom, pipeline v2

The 29 October audit supersedes the old `gpu-v1-training-ready` launch advice.
The 229-value policy contract remains `gpu-v1`; the **expert dataset and run
protocol are v2**. Do not use `expert_train_gpu_v1`: its agent identities and
teacher action interface were unsafe for recurrent imitation.

The honest architecture/go–no-go review is in
[gpu_architecture_review.md](gpu_architecture_review.md). A 15-hour slot is a
maximum experiment budget, not a commitment to keep training after a failure.

## Transfer identity and branch

Use the `rashiyaom` branch and the `rashiyaom-gpu-browser-integrated` tag. Both
`rashiyaom` and `main` include this revision. Verify the exact code and dataset
using the tracked records:

- `artifacts/gpu_v2/source_manifest.json`: every training source/config file
  and the dependency/data records, with byte counts and SHA-256.
- `artifacts/gpu_v2/expert_dataset_summary.json`: exact dataset manifest hash,
  counts and policy-contract hash.
- `artifacts/gpu_v2/mac_validation.json`: measured validation evidence and
  explicit GPU/hardware limitations.

The policy contract hash is
`c5dff01368e1bb3a77112884c5d545457830097b11aefe54e0d412fc874c57c5`.

The corrected dataset has 868,887 decisions and 18 chunks. Its manifest SHA-256
is `610fe2e0ed6462f8a97036cb581c7af5e5edd2884c176be52d865cd0132bbdae`.
The local transferable archive has SHA-256
`f1701522a6e1255863ca23d544454c18169424479bde132a56c3f71496e792dc`.

The verified expert dataset is tracked as 18 compressed chunks and a manifest
under `results/expert_train_gpu_v2/`. A clean clone includes it, so no separate
archive transfer or regeneration is needed. The larger tar archive remains
ignored because it exceeds GitHub's per-file limit and duplicates these chunks.
The preflight checks every chunk. A partial or mismatched directory causes a
stop; it is never overwritten or silently accepted.

## One-command server workflow

On a clean Linux clone, with NVIDIA drivers, Python's venv support, pip and GNU
`timeout` available:

```bash
git clone --branch rashiyaom --single-branch https://github.com/rashiyaom/swarm-sar.git
cd swarm-sar
git fetch origin tag rashiyaom-gpu-browser-integrated
```

The launcher requires branch `rashiyaom`. Verify its HEAD matches the audited
tag, then launch:

```bash
test "$(git rev-parse HEAD)" = "$(git rev-list -n 1 rashiyaom-gpu-browser-integrated)"
bash scripts/launch_gpu.sh --hours 15
```

Run inside an SSH session manager (such as an already installed tmux) if the
connection may close. Training itself is supervised by the repository's
Python program; a chat conversation is not the process supervisor.

The launcher creates its own `.venv-gpu`, installs pinned direct dependencies,
records setup logs, and counts setup time toward the same wall-clock budget.
It selects the official PyTorch 2.14.1 CUDA 12.6 wheel rather than relying on
whatever CUDA variant pip happens to choose; this is one of the distributions
listed in [PyTorch's installation matrix](https://pytorch.org/get-started/previous-versions/).
It then performs:

1. Source identity, clean worktree, actual CUDA backward pass and disk checks.
2. Missing-data generation followed by full hash/schema/identity validation.
3. Repository tests, frozen baseline and policy-contract verification.
4. Two-batch BC CUDA/checkpoint smoke.
5. Full class-balanced recurrent BC, capped at two training hours plus
   validation allowance; each epoch is logged.
6. Actual rescue rollouts on nine cohorts against the policy-compatible
   expert, random legal actions and first-legal-action references.
7. GPU PPO/checkpoint smoke, then at most one hour of pilot PPO.
8. Paired comparison against BC. Further compute requires improvement, or
   retention of already high recall.
9. Qualified continuation within the remaining budget, final development
   report, rollout artifacts and a hashed checkpoint handoff.

If continuation regresses, the qualified pilot is retained. The pipeline does
not automatically lower quality thresholds, bypass a pause, or unseal final
test seeds. Child processes have timeouts and a no-progress watchdog.

## Acceptance and monitoring

BC requires all seven actions in both splits, balanced validation accuracy
at least 0.40 per robot type, at least 0.05 recall for each action, a 0.10
balanced-accuracy margin over the mask-only classifier, an overfitting gap no
greater than 0.15, finite parameters, and exact restored weight hashes. These
are minimum sanity gates, not guarantees of useful rescue behavior; the
following closed-loop gate must pass too.

PPO checks both optimizing policies after every iteration, evaluates every
250,000 environment steps or hour, and pauses on regression, persistent
generalization gaps, low-performance action collapse, unmet stages or plateau.
Repeated sensor evidence does not earn the GPU policy an investigation bonus;
discovery reward is counted once per coordinate for the whole swarm.

Inspect `results/gpu_pipeline_*/heartbeat.json`, `pipeline_history.json`, stage
logs, BC progress files, PPO iteration history and cohort JSON. Exit 3 is a
quality/budget pause; exit 2 is an error/abort. `HANDOFF.json` always records
the reason, exact Git commit, available checkpoint and per-file hashes. A
pause is a useful result: preserve the evidence before deciding another run.

CUDA itself has to pass on the actual A5000. The Mac validates CPU execution
and the stop paths; no Mac test can prove A5000 throughput or driver support.

## Overfitting boundaries

BC splits whole episode seeds (0–1,799 training, 1,800–1,999 validation), with
stable robot trajectories, recurrent context and class-balanced loss. PPO
samples procedural cases from 0–9,999, so the BC validation seeds cease to be
an untouched rollout test during later PPO. Independent development seeds are
10,000–10,099; four remain fixed for comparable progress and four rotate for
additional coverage. Training-range probes are explicitly weak diagnostics.

Nine cohorts cover nominal, alternate team mixture, swarm scale, no network,
30% loss/partition, sensor/pose-feature stress, a composition omitted from
PPO, a 56-cell maze (PPO maze sizes are at most 32), and a tunnel footprint
absent from both BC and PPO. Expert BC may contain the
team mixture, so it is only a **PPO composition holdout**. Bootstrap intervals
and paired baselines expose uncertainty; eight maps per cohort are not a
reliability certificate.

Final seeds 20,000–20,199 remain sealed. Final evaluation requires an explicit
freeze acknowledgement and cannot run in shortened/smoke mode. Use it once
after choosing the model and all hyperparameters.

This trains a hierarchical grid-world cooperative policy. Accurate own-cell
planning and canonical map registration remain simulator conveniences. Step 5
now supplies a separate ROS2/Gazebo physics workspace with recorded Ubuntu
validation. Its default waypoint demo does not load this learned policy.
Real SLAM/localization, the learned-policy-to-ROS adapter and the browser policy
bridge remain separate integration milestones. See [step5_integration.md](step5_integration.md).
