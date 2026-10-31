# Large-map failure diagnosis — 30 October 2026

Completed CPU inference only, with the verified saved 753,664-step actors. No training, policy changes, or sealed final seeds. Two development seeds (10000, 10001), a four-robot team, 32/56-cell mazes, and 14 deterministic paired episodes. PPO and expert receive the same initial map/victims and resource settings within each pair. All four 56-cell baseline episodes exactly reproduce the saved review in steps, survivors and coverage.

## Measured results

| Size | Seed | Controller | Deadline | Battery multiplier | Found | Coverage | End step | Termination |
|---|---|---|---|---|---|---|---|---|
| 32 | 10000 | ppo | 400 | 1 | 4/4 | 90.2% | 188 | all_survivors_found |
| 32 | 10000 | expert | 400 | 1 | 4/4 | 87.5% | 196 | all_survivors_found |
| 32 | 10001 | ppo | 400 | 1 | 1/1 | 42.5% | 201 | all_survivors_found |
| 32 | 10001 | expert | 400 | 1 | 1/1 | 44.1% | 56 | all_survivors_found |
| 56 | 10000 | ppo | 400 | 1 | 1/2 | 17.7% | 322 | all_batteries_depleted |
| 56 | 10000 | expert | 400 | 1 | 2/2 | 19.7% | 228 | all_survivors_found |
| 56 | 10001 | ppo | 400 | 1 | 0/1 | 29.3% | 400 | deadline |
| 56 | 10001 | expert | 400 | 1 | 0/1 | 37.0% | 290 | all_batteries_depleted |
| 56 | 10001 | ppo | 800 | 1 | 0/1 | 18.6% | 800 | deadline |
| 56 | 10001 | expert | 800 | 1 | 0/1 | 37.0% | 290 | all_batteries_depleted |
| 56 | 10001 | ppo | 400 | 2 | 0/1 | 15.4% | 400 | deadline |
| 56 | 10001 | expert | 400 | 2 | 0/1 | 55.9% | 400 | deadline |
| 56 | 10001 | ppo | 800 | 2 | 0/1 | 11.5% | 800 | deadline |
| 56 | 10001 | expert | 800 | 2 | 0/1 | 68.0% | 588 | all_batteries_depleted |

## Findings and limits

1. **Repeated travel and goal changes are the strongest policy-specific signal.** On 56/seed 10000, PPO changes target before arrival 221 times versus 12 for the expert. PPO revisits previously visited positions on 500/1070 moves (46.7%), versus 108/491 (22.0%) for the expert. There are 163 immediate two-step position returns versus 20. PPO finds 1/2; the expert finds 2/2. This strongly motivates a goal-persistence/anti-loop ablation, but does not establish that every switch or revisit is harmful.
2. **Waiting is a separate failure mode, not predominantly a safety stop.** On 56/seed 10001, PPO issues 294 HOLD actions while a frontier slot is legal, versus only four requested moves stopped by the shield. It times out with rover_0 still holding 153.5 battery units. Legal options are not guaranteed to be useful; these counts do not justify banning HOLD. On seed 10000 the successful expert itself makes 213 holds with legal slots.
3. **Time alone does not fix the tested failure.** Extending 56/seed 10001 from 400 to 800 steps leaves PPO at 0/1, with 1384 holds despite legal frontier slots and 126.1/130.0 battery units remaining in its two rovers. The expert still exhausts its batteries at step 290, unchanged by the later deadline.
4. **Resources matter, but simply increasing them does not repair search.** With twice the battery and 800 steps, the expert reaches 68.0% coverage but still finds 0/1. PPO reaches only 11.5%, makes 1205 goal changes and 1144 immediate two-step returns, and still finds 0/1. Battery and horizon modify policy observations; these are out-of-distribution diagnostics, not clean causal effect estimates or improvements to the original benchmark.
5. **Map rejection is not the baseline bottleneck in these two failing mazes.** Instrumented baseline runs process mapping messages without uncertainty/frame refusals. In the 800-step/double-battery PPO diagnostic, 156 mapping messages are refused; 94 violate sender and 95 receiver uncertainty limits (reasons overlap). Localization/registration therefore becomes important for longer missions, but cannot explain these baseline failures.
6. **Congestion is not the dominant measured baseline mechanism here.** Requested-move shield stops are 18 and four in the two 56-cell PPO cases, compared with hundreds of goal changes/holds. This does not establish congestion is unimportant on other maps or larger teams.
7. **The victim is not geometrically disconnected or obviously beyond direct-travel energy.** An evaluation-only known-world Dijkstra bound on seed 10001 needs at least 101–108 movement-energy units to a cell within the confirmation radius, compared with initial battery 240/300. This optimistic bound ignores exploration, line-of-sight confirmation and sensing; it does not prove unknown-world discovery fits the mission budget.

## Recommended next experiment

Keep the actor and benchmark frozen. First run a labelled goal-persistence/anti-loop controller ablation against the same cases, distinguishing learned decisions from any override. Check survivor recall, coverage, reversals, premature switches and energy use. Only then consider changing candidate generation/observations and training a versioned large-maze policy. Do not start a large GPU run or migrate algorithms based on this small sample.

## Reproduction and evidence

Run from the repository root, using a fresh output directory:

```bash
PYTHONPATH=simulation/src .venv/bin/python simulation/scripts/diagnose_large_maps.py --output artifacts/large_map_diagnosis_repeat
```

- Primary summary: `artifacts/large_map_diagnosis_deterministic_20261030/summary.json`.
- Each primary case has a compressed per-step trace with selected actions, legal slots, frontier positions, chosen goal, position, battery, uncertainty, requested/shielded movement and survivor count.
- `optimistic_energy_bounds.json` records a separately computed evaluation-only known-world travel-energy lower bound.
- Aggregate switches/revisit/hold/shield counts come from the trace recorder. Immediate two-step return counts and the historical-reproduction checks were computed afterward from the stored traces/review, not supplied to either controller.
- A preliminary stochastic exploratory run is preserved separately under `artifacts/large_map_diagnosis_20261030`; it differs from the deterministic review and is excluded from the comparison table and conclusions above.
- Instrumentation is outside `simulation/src/swarm_sar`; no audited training/environment source or checkpoint was changed.

These two development seeds identify concrete failure symptoms and a justified next ablation. They do not establish performance on 64/128 grids, prove a universal root cause, or demonstrate that a proposed fix works.
