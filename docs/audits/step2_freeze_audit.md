# Step 2 frozen-baseline audit

Executed on 27 October 2026 before freezing the Step 2 implementation.

## No-tuning protocol

The audit thresholds and stress profile were encoded before running any holdout episode. Seeds 100–119 had not been used to develop or tune the frontier baseline.

Each of the 20 episodes simultaneously applied:

- Map sizes cycling through 24×24, 32×32 and 40×40
- Thermal and acoustic noise multiplied by 1.5
- Thermal and acoustic detection probability reduced by 0.10
- Thermal and acoustic false-positive probability increased by 0.05
- Odometry drift and uncertainty growth multiplied by 2
- Battery capacity multiplied by 0.85

Predeclared gates:

- Survivor recall at least 90%
- Confirmation precision at least 95%
- At most two collisions over the complete audit
- Zero duplicate-goal steps

## Results

```text
Episodes:                    20
Survivors found:             49 / 51
Survivor recall:             96.08%
Confirmation precision:      100.00%
Mean coverage:               77.73%
All-survivor successes:      18 / 20
Collisions:                  0
Duplicate-goal steps:        0
False confirmations:         0
Saved private graph files:   80
```

Size breakdown:

| Map size | Survivors found | Survivors total |
|---|---:|---:|
| 24×24 | 17 | 17 |
| 32×32 | 17 | 17 |
| 40×40 | 15 | 17 |

The two misses were in stressed 40×40 episodes that reached the 400-step limit. No parameters were changed after observing this result because the predeclared freeze gates passed.

Artifacts:

```text
training/runs/step2_robustness/audit_definition.json
training/runs/step2_robustness/audit_summary.json
training/runs/step2_robustness/episodes.csv
training/runs/step2_robustness/seed_*/
```

Reproduce with:

```bash
python simulation/scripts/audit_step2_robustness.py
```
