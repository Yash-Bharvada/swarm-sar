# Frozen-PPO goal-persistence and loop-prevention experiment

30 October 2026. Completed 16 CPU-only inference episodes: baseline, persistence, loop prevention and combined, on development seeds 10000/10001 at 32/56 cells. All use the original four-robot team, battery and 400-step deadline. No training or default-controller change. Actor hashes verified before/after each paired group. Baseline results exactly reproduce the preceding diagnosis.

## Fixed intervention settings

- Persistence: commit to the same goal coordinates for at most 12 ticks, releasing if masked/unavailable or stationary for four ticks.
- Loop prevention: within a 16-position history, detect a directed edge already traversed twice. Switch only to a legal candidate with a different, less repeated next step. Rank alternatives by edge repetitions, next-cell visits, recent goal repetition and route distance. Permit backtracking if no alternative exists.
- Combined: persistence followed by the loop check. All modes preserve the actor’s HOLD and INVESTIGATE decisions.

These are explicitly heuristic overrides, not retrained behavior. Each actor runs every tick and subsequent observations reflect the executed action. No candidate order/tensor or policy logits are modified. Wrappers use per-agent position history and existing private candidates/masks; no victim truth or teammate histories. The original simulator-informed action mask/shield remains.

## Results

| Size | Seed | Mode | Found | Coverage | Goal switches | Two-step returns | Overrides | End step |
|---|---|---|---|---|---|---|---|---|
| 32 | 10000 | baseline | 4/4 | 90.2% | 132 | 119 | 0 | 188 (all_survivors_found) |
| 32 | 10000 | persistence | 2/4 | 82.3% | 20 | 61 | 84 | 400 (deadline) |
| 32 | 10000 | loop | 4/4 | 83.3% | 116 | 95 | 11 | 190 (all_survivors_found) |
| 32 | 10000 | combined | 2/4 | 89.8% | 19 | 58 | 86 | 400 (deadline) |
| 32 | 10001 | baseline | 1/1 | 42.5% | 253 | 193 | 0 | 201 (all_survivors_found) |
| 32 | 10001 | persistence | 1/1 | 64.9% | 28 | 76 | 107 | 336 (all_survivors_found) |
| 32 | 10001 | loop | 1/1 | 92.1% | 174 | 109 | 11 | 267 (all_survivors_found) |
| 32 | 10001 | combined | 1/1 | 60.3% | 22 | 53 | 72 | 194 (all_survivors_found) |
| 56 | 10000 | baseline | 1/2 | 17.7% | 221 | 163 | 0 | 322 (all_batteries_depleted) |
| 56 | 10000 | persistence | 1/2 | 22.3% | 30 | 76 | 108 | 400 (deadline) |
| 56 | 10000 | loop | 1/2 | 36.2% | 100 | 90 | 3 | 400 (deadline) |
| 56 | 10000 | combined | 1/2 | 22.3% | 30 | 76 | 108 | 400 (deadline) |
| 56 | 10001 | baseline | 0/1 | 29.3% | 247 | 222 | 0 | 400 (deadline) |
| 56 | 10001 | persistence | 0/1 | 15.6% | 38 | 66 | 227 | 400 (deadline) |
| 56 | 10001 | loop | 0/1 | 35.2% | 258 | 197 | 44 | 327 (all_batteries_depleted) |
| 56 | 10001 | combined | 0/1 | 14.7% | 32 | 70 | 218 | 400 (deadline) |

## Decision

**Do not promote forced persistence or combined control.** Both reduce survivor recovery from 4/4 to 2/4 on 32/10000. Neither improves either large-maze survivor result. Fewer switches alone do not establish better search; a hard commitment can suppress useful replanning.
**Loop prevention is a coverage improvement in these two large cases, not a rescue improvement.** Coverage rises from 17.7% to 36.2% on 56/10000 and 29.3% to 35.2% on 56/10001. Large-map survivors remain 1/3, identical to baseline. The second case exhausts all batteries at step 327 instead of timing out with one rover alive. It also slows 32/10001 from 201 to 267 steps and lowers coverage on the other small map. Keep it experimental.

The next justified task is to inspect whether the five offered candidate branches are informative and why the actor holds with alternatives, then test a labelled information-gain/energy-aware candidate-ranking baseline. No large GPU run is justified by this ablation alone. Additional development seeds are required before promotion; these two cases are now diagnosis/selection data, not independent confirmation data.

## Reproduce and inspect

```bash
PYTHONPATH=simulation/src .venv/bin/python simulation/scripts/ablate_goal_governor.py --output artifacts/goal_governor_repeat
.venv/bin/python -m pytest tests/experiments/test_goal_governor.py -q
```

Use a fresh output directory; optional `--seeds` accepts only development seeds. `--sizes` selects grid sizes. Source hashes, actor hashes, exact settings and all results are in `artifacts/goal_governor_ablation_20261030/summary.json`. Each compressed trace records proposed and executed actions, override reason, legal slots, goal coordinates, positions, battery, uncertainty and requested/shielded motion. Aggregate two-step returns and baseline-reproduction assertions were computed from stored traces afterward.

Implementation: `simulation/scripts/goal_governor.py`, `ablate_goal_governor.py`, and the extended `diagnose_large_maps.py`. Four unit tests cover goal-identity persistence across candidate reordering, expiry/stall/mask release, preserved HOLD/INVESTIGATE, legal-alternative-only loop escape, private state and immutable inputs.

Limitations: four initial cases, one fixed configuration per wrapper, no hyperparameter search, no 64/128-cell or ROS/Gazebo validation. No audited training/environment source or checkpoint was changed. Production controllers remain unchanged.
