# Blueprint Step 2 validation record

Validated on 27 October 2026 in the project `.venv`.

## Scope

- Per-agent occupancy beliefs remain private and sensor-derived.
- Frontiers are detected, clustered and exposed as at most five action slots.
- The scripted baseline selects nearby useful unclaimed targets and maintains reservations.
- A* performs low-level motion while collision arbitration prevents conflicting moves.
- Thermal evidence creates suspected-survivor graph nodes.
- A survivor is confirmed only after repeated evidence from one agent or evidence from at least two agents, followed by a truth-side proximity/LOS verification.
- Every agent maintains its own NetworkX graph with room, junction, frontier, suspected-survivor and confirmed-survivor node support.
- Graph edges store estimated distance, traversability, observation confidence and last-update time.

## Automated validation

- 45 pytest tests passed, including the official PettingZoo parallel API test.
- Twenty fixed seeds produced 80 distinct private topology graphs.
- The graphs contained 1,668 attributed edges during the validation run.
- All required node kinds occurred across the evaluation set.
- Evidence trails contained 48 repeat-evidence confirmations and 7 multi-agent confirmations.
- Two independent Python processes reproduced identical summaries, evidence events and all 80 graph artifacts.

## Twenty-seed results

```text
Survivors found:       55 / 55
Survivor recall:       100.00%
Mean coverage:         81.05%
Collisions:            0
Duplicate-goal steps:  0
False confirmations:   0
Confirmed graph marks: 64 across private maps
```

Coverage is measured when an episode ends. Several episodes terminate early after all survivors are confirmed, so full-map coverage is intentionally not required after a successful rescue.

Reproduce with:

```bash
python simulation/scripts/validate_step2.py
```
