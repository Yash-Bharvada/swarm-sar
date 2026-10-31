# Frozen large-map development benchmark v1

Prepared 30 October 2026. This freezes the next evaluation protocol; **it does not report a new performance improvement**. No training or full controller sweep was started. Final-test seeds remain sealed.

Protocol: `large_map_development_v1.json`. Integrity manifest: `large_map_development_v1.lock.json`. Changes to the protocol or locked source require a reviewed new version; do not update hashes to hide a changed experiment. Hashes provide auditability, not access control.

## Fixed cases and budgets

Each stage has **36 cases**: three sizes (32, 56, 64), three families (maze, rooms, cave) and four seeds. All use two rovers, two drones, original batteries, network enabled, deterministic PPO and a 400-step horizon. This is a fixed-resource scaling test, not a claim that these resources suffice at 64 cells. A future operationally scaled budget track must be a separate predeclared protocol.

- Discovery: development seeds 10020–10023. Use this stage to compare candidates.
- Confirmation: development seeds 10080–10083. Reserved for one nominated, frozen candidate. Do not inspect these maps before nomination.
- These allocations are disjoint within this protocol and outside our immediately preceding ablations. They are not guaranteed historically unused, nor interchangeable with the sealed final split.

Room counts scale with area: 10–14 at 32, 31–43 at 56, 40–56 at 64. A generation-only construction check showed the original fixed 10–14 rooms fails the 30% reachable-area requirement at the two larger sizes. This was resolved before any controller evaluation; both failed and corrected generation checks are retained. No seeds were substituted and no controller outcomes were used to choose room counts. Maze/cave generation and the minimum-area threshold remain unchanged.

## Primary metric and promotion gates

For each size/layout stratum, compute total survivors found divided by total survivors across its four episodes. Average these stratum recalls equally, preventing a family with more victims from dominating the whole benchmark.

A candidate must satisfy **all** engineering gates against frozen PPO:

1. Average recall gain of at least **10 percentage points** across the six 56/64-cell strata.
2. Average recall decrease no worse than **2 points** across the three 32-cell strata.
3. No individual size/layout stratum loses more than **5 points**.
4. Complete, paired results for PPO, expert and the candidate, with no missing, duplicate or mismatched initial cases.

Coverage, completion rate, termination, steps and remaining energy are secondary. Coverage cannot rescue a failed survivor-recall gate. Always retain per-case failures and measured resource use. These thresholds are engineering criteria, not statistical significance. Four seeds per stratum are weak evidence; passing does not establish real-world reliability or authorize automatic deployment. Shared seeds across layouts create dependence; do not treat victims or robot ticks as independent trials.

## Implemented safeguards

- The default runner only validates the lock and prints the case count; simulation execution requires `--execute`.
- The runner verifies policy parameter hashes, unchanged actors after each episode and matched initial worlds between controllers.
- The protocol/source hash lock includes simulator, sensor, policy/inference and config inputs, the runner/evaluator and current candidate planner implementations.
- Confirmation requires a candidate lock identifying its source hashes, actor hashes, discovery results and protocol. The provided nomination command only accepts a complete discovery result passing the gates.
- The candidate lock is marked consumed before confirmation episodes begin. An interrupted confirmation still counts as data access; preserve its evidence rather than restarting it as untouched data.
- The one-candidate-per-version rule also requires discipline: copying/deleting nomination files can bypass local bookkeeping. Do not do this or label reused confirmation data independent.
- Exceptions leave a failure record and incomplete results. The assessor rejects incomplete/duplicate/unpaired comparisons rather than silently dropping failures.
- The currently supported candidates (`square5`, `visible5`, `visible24`) are separate heuristic planners, not retrained actors. This benchmark does not promote previous failed candidates; it provides a reproducible way to evaluate a future reviewed version.

## Commands

From the repository root, with the existing compatible Python environment:

```bash
# Cheap: validate protocol/source integrity and stage allocation; no episodes.
PYTHONPATH=simulation/src .venv/bin/python simulation/scripts/frozen_development_benchmark.py

# Construction smoke: first discovery seed for each size/layout, no robot actions.
PYTHONPATH=simulation/src .venv/bin/python simulation/scripts/frozen_development_benchmark.py \
  --smoke-worlds --output artifacts/benchmark_world_smoke_repeat

# Explicit full discovery baseline: PPO + expert = 72 episodes.
PYTHONPATH=simulation/src .venv/bin/python simulation/scripts/frozen_development_benchmark.py \
  --execute --stage discovery --output artifacts/benchmark_discovery_baselines

# A reviewed candidate comparison: PPO + expert + candidate = 108 episodes.
# Example candidate name only; the previous tests did not establish visible5 as a winner.
PYTHONPATH=simulation/src .venv/bin/python simulation/scripts/frozen_development_benchmark.py \
  --execute --stage discovery --candidate visible5 --output artifacts/benchmark_discovery_candidate

# Assess complete results and nominate only if ALL discovery gates pass.
PYTHONPATH=simulation/src .venv/bin/python simulation/scripts/assess_development_benchmark.py \
  artifacts/benchmark_discovery_candidate/results.json --candidate visible5 \
  --nominate artifacts/benchmark_candidate_lock.json

# Only after nomination/review: one frozen confirmation attempt, 108 episodes.
PYTHONPATH=simulation/src .venv/bin/python simulation/scripts/frozen_development_benchmark.py \
  --execute --stage confirmation --candidate visible5 \
  --candidate-lock artifacts/benchmark_candidate_lock.json --output artifacts/benchmark_confirmation

PYTHONPATH=simulation/src .venv/bin/python simulation/scripts/assess_development_benchmark.py \
  artifacts/benchmark_confirmation/results.json --candidate visible5
```

Use fresh output directories. Do not run the larger commands merely to inspect this setup. The implementation currently reruns matched baselines with a candidate rather than reusing unverified cached rows. CPU inference is used; no GPU training is started. Confirmation results are still development evidence; final evaluation remains a separate later controlled step.

## Local validation completed

- Protocol/source-lock validation passed.
- Nine generation-only discovery maps, one per size/layout, generated successfully with the final settings; **zero mission episodes executed**.
- Smoke output: `artifacts/frozen_benchmark_v1_verified/world_smoke.json`.
- Initial failed room-generation construction audit: `artifacts/frozen_benchmark_v1_generation_audit/world_smoke.json`.
- Tests reject missing, duplicate, unpaired or incomplete results, overlapping/incorrect seed allocation, and small-map/layout regressions hidden by average gains.
- The full local suite result is recorded under `artifacts/frozen_benchmark_v1_verified/python_tests.txt`.

The other discovery seeds and all confirmation maps have not been generated by this setup check. Any later generation failure must remain visible as incomplete evidence; it must not trigger cherry-picked replacement seeds. No 64-cell performance result exists yet, and this protocol makes no 128-cell claim.
