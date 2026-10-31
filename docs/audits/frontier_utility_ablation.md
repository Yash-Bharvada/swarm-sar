# Information-gain/energy-aware frontier experiment — 30 October 2026

Completed 18 CPU-only episodes: baseline, HOLD-release-only and utility selection on 32/56-cell maze seeds 10000/10001, followed by the same fixed settings on two additional 56-cell development seeds, 10002/10003. These additional seeds were not used to tune the wrappers, but they are existing development cases, not sealed test data. All runs use the same four-robot team, 400-step deadline and original batteries. Actor hashes remain unchanged. No training, default controller modification or ROS deployment.

## What was tested

- **Baseline:** original deterministic frozen PPO.
- **HOLD release:** preserve frontier choices and INVESTIGATE. After four consecutive proposed HOLD decisions, choose a legal affordable frontier with an unknown-space opportunity of at least four cells, if available. A continued HOLD sequence can trigger repeated overrides until the actor proposes another action; a single injected move changes subsequent observations/actions.
- **Utility:** the same HOLD release plus heuristic selection among existing legal frontier slots whenever PPO proposes a frontier move. It does not enlarge/reorder the actor’s five candidate slots or change its input tensors. This is a hybrid heuristic override, not improved learned weights.

Utility = unknown-cell opportunity / ((1 + estimated route energy) × (1 + visits to goal) × peer-claim penalty). Opportunity counts unknown cells in a square around the goal using a radius capped at four cells. It is an optimistic proxy, not a visibility prediction: walls can occlude those cells. Path energy uses the robot-specific movement/rubble costs. Candidates must have a moving path, fit within 80% of remaining battery and the remaining step budget. Peer-claimed goals receive a factor-two penalty, using delivered valid peer claims. No survivor truth or global map is read by the selector.

## Results

| Size | Seed | Mode | Found | Coverage | Steps | Overrides | End |
|---|---|---|---|---|---|---|---|
| 32 | 10000 | baseline | 4/4 | 90.2% | 188 | 0 | all_survivors_found |
| 32 | 10000 | hold_release | 4/4 | 90.2% | 188 | 0 | all_survivors_found |
| 32 | 10000 | utility | 4/4 | 93.7% | 189 | 186 | all_survivors_found |
| 32 | 10001 | baseline | 1/1 | 42.5% | 201 | 0 | all_survivors_found |
| 32 | 10001 | hold_release | 1/1 | 42.5% | 201 | 0 | all_survivors_found |
| 32 | 10001 | utility | 1/1 | 53.1% | 69 | 98 | all_survivors_found |
| 56 | 10000 | baseline | 1/2 | 17.7% | 322 | 0 | all_batteries_depleted |
| 56 | 10000 | hold_release | 1/2 | 17.7% | 322 | 0 | all_batteries_depleted |
| 56 | 10000 | utility | 2/2 | 30.6% | 218 | 193 | all_survivors_found |
| 56 | 10001 | baseline | 0/1 | 29.3% | 400 | 0 | deadline |
| 56 | 10001 | hold_release | 0/1 | 27.8% | 326 | 20 | all_batteries_depleted |
| 56 | 10001 | utility | 1/1 | 34.9% | 134 | 161 | all_survivors_found |
| 56 | 10002 | baseline | 0/2 | 12.7% | 400 | 0 | deadline |
| 56 | 10002 | hold_release | 0/2 | 30.7% | 308 | 2 | all_batteries_depleted |
| 56 | 10002 | utility | 1/2 | 40.0% | 324 | 357 | all_batteries_depleted |
| 56 | 10003 | baseline | 1/2 | 18.9% | 400 | 0 | deadline |
| 56 | 10003 | hold_release | 0/2 | 17.4% | 333 | 10 | all_batteries_depleted |
| 56 | 10003 | utility | 0/2 | 40.0% | 304 | 395 | all_batteries_depleted |

## Interpretation

Across four 56-cell cases, baseline finds **2/7**, HOLD release **1/7**, and utility **4/7** survivors. Utility increases mean coverage from about **19.7% to 36.4%**, but regresses seed 10003 from **1/2 to 0/2**. It finds all survivors in both initial large cases and 1/2 in the first additional case, then fails entirely in the second. Both 32-cell cases retain full survivor recovery with utility, but those are only two cases.

**Decision: retain utility as a promising experimental baseline, not a default or validated rescue upgrade.** Higher coverage is insufficient if the newly explored branches omit the victim and consume the batteries. The additional-case regression rules out a robust-improvement claim from the initial success.

**HOLD is a symptom, not a safe universal fix.** On 56/10001, the HOLD-release trajectory has 62 proposed holds, 57 with an affordable unknown-space opportunity, and 20 actual overrides. It still finds 0/1 and exhausts batteries at step 326. On 10003, ten overrides lead to 0/2 versus baseline 1/2. These are different closed-loop trajectories; their hold counts must not be compared as if the robot followed the unchanged baseline path. The test establishes that some holds coexist with feasible candidate opportunities, not the neural network’s internal reason for selecting HOLD.

Neither experiment isolates expanded candidate availability: selection is restricted to the same five slots. The remaining questions are whether omitted branches matter, whether the unknown-cell proxy is misleading through walls, and whether pursuit of information needs explicit survivor-evidence/mission utility. A next controlled step would compare an occlusion-aware opportunity estimate and branch-diverse candidate pool with a strong non-learning reference, before modifying the policy contract or spending GPU time. Do not silently reorder actor slots or deploy an untrained changed observation interface.

## Validation and reproduction

- Full local Python suite: **192 passed**, two existing deprecation warnings. Eight experimental unit tests include utility budget/horizon/rubble accounting, delayed HOLD release, investigation preservation, no forced movement without legal affordable opportunity, and visit/claim penalties.
- All logged overrides were checked against their recorded legal utility entries, energy/time admission and minimum opportunity. Override counts match the traces. Four repeated baselines reproduce the earlier deterministic diagnosis.
- Actor hashes are checked against checkpoint metadata before inference, after every case group, and match between both experiment runs. Existing simulator-informed masks/shields remain unchanged; this is not a new fully sensor-only deployment claim.
- Primary artifacts: `artifacts/frontier_utility_ablation_20261030/summary.json` and compressed traces.
- Additional development cases: `artifacts/frontier_utility_confirmation_20261030/summary.json` and compressed traces.
- Combined verification: `artifacts/frontier_utility_comparison.json`.

```bash
PYTHONPATH=simulation/src .venv/bin/python simulation/scripts/ablate_goal_governor.py --modes baseline hold_release utility --output artifacts/utility_repeat
PYTHONPATH=simulation/src .venv/bin/python simulation/scripts/ablate_goal_governor.py --seeds 10002 10003 --sizes 56 --modes baseline hold_release utility --output artifacts/utility_additional_repeat
.venv/bin/python -m pytest tests/experiments -q
```

Use fresh output directories. The experimental utility implementation is `simulation/scripts/frontier_utility.py`; the shared runner and diagnostic instrumentation stay outside audited training/environment sources. All modes record original actor actions, executed actions and reasons, with candidate-level score/energy/opportunity diagnostics. No checkpoint, production controller, audited source manifest or default inference path was changed. No 64/128-cell or live ROS gain was tested.
