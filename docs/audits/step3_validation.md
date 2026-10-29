# Step 3 Shared-Policy PPO Validation Report

Date: 2026-10-27

## Outcome

Step 3 passed its implementation and acceptance gates. RLlib PPO trained and exported exactly two policies: one shared by every rover and one shared by every drone. The restored checkpoint ran with networking enabled and disabled, obeyed every action mask, produced no collisions, and executed previously unseen 2-rover/3-drone and 4-rover/4-drone teams without changing network dimensions.

The learned policy did **not** outperform the frozen frontier baseline. This is reported explicitly, as required by the blueprint. The PPO checkpoint is a valid trained prototype and variable-team foundation, not the controller that should be used for the strongest current rescue demonstration.

## Implementation

- RLlib 2.59 PPO on the new RLModule/Learner API with PyTorch 2.14.
- Two shared 67,336-parameter actor-critic modules: `rover_policy` and `drone_policy`.
- Curriculum: one rover, then two rovers, then alternating 2+2 and 3+3 heterogeneous teams.
- Fixed 129-value per-agent vector containing only the local map crop, local sensors and history, battery, relative pose/confidence, frontier features, collision state, and an 8-value peer summary.
- Seven masked actions: five frontier slots, investigate, and hold. A* remains the low-level path planner.
- Cooperative reward tuned to +20 confirmed survivor, +0.05 newly observed cell, a small local thermal-evidence investigate bonus, collision penalty, and tick cost.
- Local one-step safety shield rejects occupied or duplicate movement targets below policy goal selection.
- Seeded stochastic categorical inference, matching PPO's learned policy distribution while remaining exactly reproducible.
- Variable team adapter supports user-selected mixtures up to the current 4×4 spawn capacity of 16 robots.

No ground-truth grid, survivor coordinate, or global assignment is included in the policy input.

## Training result

| Item | Result |
|---|---:|
| PPO iterations | 12 |
| Environment steps | 24,576 |
| Rover parameters | 67,336 |
| Drone parameters | 67,336 |
| Rover weight delta L2 | 4.3287 |
| Drone weight delta L2 | 4.1622 |
| Final reported mean return | 404.59 |
| Checkpoint restored | Yes |

Both final parameter hashes differ from initialization, proving both policies were optimized. A versioned copy of the checkpoint, curve and summaries is under `models/step3/`; raw run output remains under `training/runs/step3_training/`.

## Unseen 20-map comparison

Seeds 500–519, 2 rovers + 2 drones, 32×32 maps, 400-step limit:

| Metric | Shared PPO | Frozen frontier baseline |
|---|---:|---:|
| Survivors | 27/51 | 48/51 |
| Recall | 52.94% | 94.12% |
| Mean coverage | 49.54% | 73.17% |
| Mean episode steps | 281.15 | 115.95 |
| All-survivor episodes | 8/20 | 18/20 |
| Mean completion steps (completed only) | 135.75 | 83.39 |
| Collisions | 0 | 0 |
| Invalid actions | 0 | 0 |

Conclusion: PPO learned meaningful decentralized search behavior and cleared the declared 50% recall gate, but it is materially weaker than the baseline. The frontend demo should default to the frontier controller until later RL work closes this gap, while offering PPO as an experimental mode.

## Held-out swarm-size generalization

The policies were trained on 1 rover, 2 rovers, 2+2, and 3+3. They were then evaluated on team compositions never used during training:

- 2 rovers + 3 drones
- 4 rovers + 4 drones
- seeds 600–604
- networking disabled and enabled for every profile/seed pair

Aggregate result: 17/40 survivors (42.5% recall), 63.63% mean coverage, 4/20 all-survivor episodes, zero collisions, and zero invalid actions. Ten episodes ran with networking off and ten with networking on.

This validates structural variable-population operation; it does not imply equal policy quality for unlimited swarm sizes. The current spawn admits 1–16 robots, and much larger teams require scaling the spawn, radio simulation, compute, and training distribution.

## Acceptance gates

| Gate | Required | Result |
|---|---:|---:|
| Trained policies | exactly 2 shared modules | Pass |
| Both weights updated | yes | Pass |
| Checkpoint restores and runs | yes | Pass |
| PPO recall on 20 unseen maps | at least 50% | 52.94% |
| Held-out team recall | at least 25% | 42.5% |
| Networking modes | both off and on | Pass |
| Invalid actions | 0 | 0 |
| Collisions | 0 | 0 |
| Comparison against baseline | reported honestly | Pass |

## Regression validation

- 58 automated tests passed.
- Step 1 three-seed gate passed.
- Step 2 nominal gate passed: 55/55 survivors.
- Step 2 stressed gate passed: 46/46 survivors.
- Step 2.5 irregular-world gate passed: 22/22 survivors and 50/50 generation cases.

## Reproduce

```bash
source .venv/bin/activate
python training/scripts/train_step3.py
python training/scripts/validate_step3.py
python simulation/scripts/run_step3_policy.py --rovers 2 --drones 3 --network
pytest -q
```

Machine-readable results:

```text
training/runs/step3_training/training_definition.json
training/runs/step3_training/training_history.csv
training/runs/step3_training/training_summary.json
training/runs/step3_training/training_curve.png
training/runs/step3_training/checkpoint/
training/runs/step3_validation/validation_definition.json
training/runs/step3_validation/validation_summary.json
training/runs/step3_validation/*_episodes.csv
models/step3/checkpoint/
models/step3/training_curve.png
models/step3/training_summary.json
models/step3/validation_summary.json
```

## Remaining limitations

- PPO still trails the deterministic frontier baseline substantially.
- Peer communication is an ideal fixed summary. Step 4 must add packet loss, delay, range/LOS effects, and explicit messages without a central assignment server.
- The safety shield is a local motion layer; it does not provide cooperative goal assignment.
- MAPPO, GNN communication, recurrent memory, and much longer training are later improvements, not claims of this milestone.
- The simulator remains 2D and is not yet ROS 2/Gazebo or hardware validated.
