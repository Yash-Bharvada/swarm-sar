# Step 2.5 Scalability and Irregular-World Validation Report

Date: 2026-10-27

## Outcome

Step 2.5 passed its complete validation gate. The controller found all 22 survivors in eight end-to-end holdout missions across eight independently sampled, non-square dimensions and procedural shapes. It produced no collisions, duplicate goals, or false confirmations, and replayed deterministically.

This milestone removes the assumption that a disaster site is a fixed square. It does not claim an infinite environment: every simulated mission is finite, and the number of robots plus the mission time and battery budget scale with estimated site area.

## What changed

- World storage dimensions can be rectangular, portrait, or landscape.
- `footprint: procedural` creates a seeded connected union of random lobes and corridors. It is not selected from a list of L/T/rectangle templates.
- Named L, T, multi-structure, tunnel, and collapsed footprints remain available for targeted regression tests.
- Large connected frontier boundaries yield several spatially separated candidate goals while the policy still sees exactly five frontier slots.
- Agents exchange occupancy knowledge only within current radio-connected components. Their map arrays and topological graphs remain separate.
- The swarm scales from four to eight heterogeneous agents and receives an area-scaled mission/battery budget.
- Relative pose normalization no longer depends on total map dimensions.
- Rendering automatically reduces cell size for large maps.
- Episode artifacts record the exact world and simulator configuration.

The original Step 2 path planner and no-sharing behavior remain the defaults. Step 2.5 features are enabled explicitly by the scalability profile, preserving the frozen milestone.

## Predeclared gates

| Metric | Required |
|---|---:|
| Survivor recall | at least 90% |
| Confirmation precision | at least 95% |
| Mean reachable-area coverage | at least 75% |
| Shape irregularity | at least 8% absent from navigable bounding box |
| Collisions | 0 |
| Duplicate-goal steps | 0 |
| Minimum throughput | at least 10 steps/s |
| Deterministic replay | exact match |
| Policy interface | 9×9 local map, 5 frontier slots, 7 actions |

## Tests performed

1. Fifty generated-property cases (seeds 1000–1049): varied dimensions, connected reachable navigation, valid survivor placement, border integrity, and irregularity.
2. Eight end-to-end holdout missions (seeds 700–707): full sensing, exploration, local communication, mapping, survivor evidence, confirmation, topology generation, and artifact export.
3. Exact replay of seed 700: summary, event stream, and generated grid matched.
4. Full automated test suite: 52 tests passed.
5. Step 1 three-seed validation passed.
6. Step 2 nominal validation passed with 55/55 survivors across 20 episodes.
7. Step 2 stressed regression passed with 46/46 survivors across 20 episodes.

## Holdout results

| Seed | Dimensions | Agents | Survivors | Coverage | Steps | Steps/s |
|---:|---:|---:|---:|---:|---:|---:|
| 700 | 81×60 | 4 | 3/3 | 84.0% | 563 | 279.8 |
| 701 | 80×116 | 6 | 2/2 | 57.3% | 427 | 132.8 |
| 702 | 122×60 | 4 | 2/2 | 69.5% | 242 | 71.0 |
| 703 | 56×134 | 5 | 5/5 | 77.7% | 229 | 66.2 |
| 704 | 95×68 | 4 | 3/3 | 91.1% | 365 | 93.3 |
| 705 | 122×77 | 6 | 2/2 | 42.0% | 112 | 94.0 |
| 706 | 73×120 | 5 | 3/3 | 87.4% | 195 | 71.0 |
| 707 | 74×116 | 5 | 2/2 | 99.1% | 488 | 34.2 |

Aggregate: 22/22 survivors, 100% recall, 100% precision, 76.03% mean coverage, 0 collisions, 0 duplicate-goal steps, 0 false confirmations, and 34.2 minimum steps/s. All eight map dimensions were unique. Minimum measured irregularity was 73.55%.

Coverage is measured when the mission ends. A mission stops immediately after all survivors are confirmed, so a low coverage value such as seed 705's 42.0% means the objective was completed early, not that the controller timed out.

## Reproduce

```bash
source .venv/bin/activate
python simulation/scripts/audit_step25_scalability.py
pytest -q
python simulation/scripts/validate_step1.py
python simulation/scripts/validate_step2.py
python simulation/scripts/audit_step2_robustness.py
```

The machine-readable definition and results are written to:

```text
training/runs/step25_scalability/audit_definition.json
training/runs/step25_scalability/audit_summary.json
training/runs/step25_scalability/episodes.csv
training/runs/step25_scalability/generation_properties.json
training/runs/step25_scalability/seed_*/
```

## Limits before real deployment

- The simulator is a 2D grid, and drones are still 2D sensing proxies.
- Local exchange is range-gated but has no packet loss, bandwidth cap, latency, or radio occlusion yet.
- The procedural generator is broad, but it cannot represent every real collapse geometry.
- Scaling requires more robots or more mission time as traversable area grows; no finite swarm can guarantee coverage of an unbounded site.
- ROS 2/Gazebo or Isaac Sim, learned policies, SLAM loop closure, dynamic hazards, and hardware-in-the-loop tests remain future milestones.

These are reasons to continue to Step 3 and later integration—not reasons to keep tuning the Step 2 frontier baseline.
