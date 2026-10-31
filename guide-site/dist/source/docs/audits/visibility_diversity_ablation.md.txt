# Visibility-aware gain and expanded frontier-pool test

30 October 2026. **Do not promote these planners.** The fixed additional-development comparison did not improve survivor recovery. No training, actor changes, default-controller change or ROS integration was performed.

## Overfitting precautions

- Settings, modes and cases were saved in `plan.json` before simulation began; no tuning or reruns with revised thresholds occurred after observing failures.
- Seeds 10008–10011 were outside the immediately preceding diagnosis/override comparisons (10000–10003). They are additional development data, not guaranteed never used elsewhere historically, and not a sealed final test.
- Two small-map cases (32/10008, 32/10009) and four large cases (56/10008–10011) were evaluated. All four modes share initial world/victim signatures, fleet, original batteries and 400-step horizon per case.
- All cases and regressions are reported. Final seeds 20000–20199 remain sealed. These additional seeds are now consumed development evidence and should not become repeated tuning targets.

## Controlled comparisons

**PPO:** original deterministic frozen actor and unchanged observation/action contract.

**square5:** separate non-learning frontier planner using square unknown-cell gain, route energy, goal-visit penalty, delivered peer-claim penalty and the original five offered candidates. This is not the earlier hybrid utility override: no actor is run in this heuristic arm.

**visible5:** same heuristic planner, replacing square gain with ray tests that reject unknown target cells behind **known** walls. The same radius-four-capped square footprint is retained so footprint shape/range does not confound the gain comparison. Unknown intermediate cells can conceal walls, so gain remains optimistic rather than a measured visibility guarantee.

**visible24:** same visibility-aware planner with an independently generated pool of up to 24 locally reachable frontier representatives, at most five per connected frontier cluster. The existing generator prioritizes distinct clusters and spatial samples; this is not a newly implemented corridor-graph diversity method, and the actual pool can have fewer than 24 options.

The heuristic arms share a minimum gain of four, route energy within 80% of battery, route length within the remaining horizon, visit/peer penalties, and thermal/acoustic investigation thresholds of 0.35/0.08. They select an explicit goal through the existing simulator goal API and map it to a legal execution slot. No PPO inference is performed after such goal/candidate changes. The widened candidate pool is never fed into the old actor. The existing simulator-informed masks/shield remain unchanged.

## Aggregate results

| Size | Cases | Mode | Survivors | Mean coverage |
|---|---|---|---|---|
| 32 | 2 | ppo | 6/8 | 89.4% |
| 32 | 2 | square5 | 7/8 | 89.0% |
| 32 | 2 | visible5 | 5/8 | 58.1% |
| 32 | 2 | visible24 | 5/8 | 57.2% |
| 56 | 4 | ppo | 3/10 | 25.7% |
| 56 | 4 | square5 | 2/10 | 46.7% |
| 56 | 4 | visible5 | 2/10 | 24.5% |
| 56 | 4 | visible24 | 1/10 | 25.3% |

## Every case

| Size | Seed | Mode | Found | Coverage | Steps | Termination |
|---|---|---|---|---|---|---|
| 32 | 10008 | ppo | 3/4 | 88.3% | 303 | all_batteries_depleted |
| 32 | 10008 | square5 | 4/4 | 90.2% | 216 | all_found |
| 32 | 10008 | visible5 | 2/4 | 31.1% | 400 | deadline |
| 32 | 10008 | visible24 | 2/4 | 33.8% | 400 | deadline |
| 32 | 10009 | ppo | 3/4 | 90.6% | 295 | all_batteries_depleted |
| 32 | 10009 | square5 | 3/4 | 87.9% | 400 | deadline |
| 32 | 10009 | visible5 | 3/4 | 85.1% | 400 | deadline |
| 32 | 10009 | visible24 | 3/4 | 80.5% | 400 | deadline |
| 56 | 10008 | ppo | 1/1 | 22.3% | 203 | all_found |
| 56 | 10008 | square5 | 0/1 | 43.3% | 377 | all_batteries_depleted |
| 56 | 10008 | visible5 | 1/1 | 8.5% | 30 | all_found |
| 56 | 10008 | visible24 | 1/1 | 7.7% | 24 | all_found |
| 56 | 10009 | ppo | 0/3 | 17.6% | 314 | all_batteries_depleted |
| 56 | 10009 | square5 | 1/3 | 40.7% | 331 | all_batteries_depleted |
| 56 | 10009 | visible5 | 0/3 | 24.8% | 400 | deadline |
| 56 | 10009 | visible24 | 0/3 | 32.7% | 400 | deadline |
| 56 | 10010 | ppo | 1/3 | 28.4% | 308 | all_batteries_depleted |
| 56 | 10010 | square5 | 0/3 | 52.1% | 400 | deadline |
| 56 | 10010 | visible5 | 1/3 | 34.9% | 400 | deadline |
| 56 | 10010 | visible24 | 0/3 | 29.6% | 400 | deadline |
| 56 | 10011 | ppo | 1/3 | 34.4% | 400 | deadline |
| 56 | 10011 | square5 | 1/3 | 50.9% | 400 | deadline |
| 56 | 10011 | visible5 | 0/3 | 29.9% | 400 | deadline |
| 56 | 10011 | visible24 | 0/3 | 31.2% | 400 | deadline |

## Interpretation and next decision

1. **Visibility filtering is not an established improvement.** Among the heuristic arms, visible5 does not beat square5 on large-map survivor totals and loses on the small maps. Known-wall ray filtering can lower opportunities beneath the fixed threshold, causing stationary decisions; this interacts with the minimum-gain and energy gates. The experiment does not isolate a universal causal explanation or show that visibility-aware planning is inherently bad.
2. **The wider pool does not solve the problem at these settings.** visible24 falls from 2/10 to 1/10 large-map survivors relative to visible5. More available frontiers alone do not ensure good branch selection or survivor-directed exploration.
3. **Coverage is not rescue performance.** square5 explores 46.7% on large maps versus PPO’s 25.7%, yet finds 2/10 survivors versus PPO’s 3/10. Optimizing unknown area per route energy can prioritize space that is irrelevant to a victim.
4. **No claim about retrained PPO/MAPPO follows.** These heuristic planners do not train or evaluate an actor on expanded candidates. PPO-versus-heuristic comparisons combine many controller differences. The earlier hybrid utility result (4/7 on seeds 10000–10003) is a different intervention and cannot be pooled with these pure-planner results or claimed independently confirmed here.
5. **Stop stacking fixes selected on a few maps.** Keep the original production actor. Before any more architecture changes or GPU time, freeze a broader development evaluation protocol with seed/layout strata, baseline comparisons, budgets and a primary survivor-recall/non-regression criterion. A small pilot here rejected the proposed fixed planner rather than finding a winner. An energy/evidence-aware expert and conditional hold diagnostics remain research directions, not established fixes. No setting was tuned after these outcomes.

## Validation and reproduction

Full Python suite: **196 passed**, two existing deprecation warnings. Twelve experiment tests include wall occlusion, unknown-wall uncertainty, map boundaries, input immutability, reachable expanded candidates and independent planner histories. The actor is checked against checkpoint hashes and rechecked after every case group. Six matched initial states and all 24 recorded traces were verified. No audited training/environment files or weights changed.

```bash
PYTHONPATH=simulation/src .venv/bin/python simulation/scripts/ablate_visibility.py --output artifacts/visibility_repeat
.venv/bin/python -m pytest tests/experiments -q
```

Use a new output directory. Do not rerun the same seeds to choose new thresholds and then report them as independent validation.

- Pre-run design: `artifacts/visibility_diversity_20261030/plan.json`.
- Results, exact configuration, actor identity and experiment source hashes: `artifacts/visibility_diversity_20261030/summary.json`.
- Verification and aggregates: `artifacts/visibility_diversity_20261030/verification.json`.
- Per-step compressed traces in the same directory include execution actions, selected goal, gain estimate, energy and pool size.
- Source: `simulation/scripts/visibility_frontiers.py` and `simulation/scripts/ablate_visibility.py`.

Limitations: four large development cases and two small cases, one fixed configuration, maze family only. No broad reliability, statistical superiority, 64/128-cell gain, actual SLAM quality or ROS physical performance is established.
