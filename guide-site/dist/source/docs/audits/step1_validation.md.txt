# Blueprint Step 1 validation record

Validated on 27 October 2026 in the project `.venv`.

## Automated checks

- 36 pytest tests passed, including PettingZoo's official `parallel_api_test`.
- Dependency check reported no broken requirements.
- Python bytecode compilation completed for all source and script files.
- 300 generated maps were fuzzed: 100 each at 24×24, 32×32 and 40×40.
- All 300 maps had reachable non-wall cells and strictly interior survivors.
- Survivor counts covered all configured values from one through four.
- 3,000 randomized PettingZoo steps across 30 seeds preserved valid observation spaces, unique living-agent positions and wall constraints.
- Headless RGB-array rendering was validated.

## Required three-seed gate

`python simulation/scripts/validate_step1.py --seeds 0 1 2 --max-steps 200`

For all three seeds:

- Exactly two rovers and two drones spawned.
- Survivor count remained within one through four.
- No observation exposed a true grid or survivor position.
- Living agents never overlapped, entered walls or produced a blocked-move collision.
- Resetting the same seed reproduced the map, survivors and spawn positions.
- Movement produced odometry drift and increasing confidence bounds.
- Map, event, trajectory and metric artifacts were written and parsed successfully.

The non-learning frontier coordination quality is deliberately not a Step 1 pass condition; it is the Step 2 deliverable.
