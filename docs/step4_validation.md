# Step 4 decentralized-network validation

## Outcome

Step 4 passed its locked simulator gate on 28 October 2026. The final untouched holdout recovered 40 of 42 survivors (95.24%) across 12 networked missions, including 14 of 16 (87.5%) under 30% packet loss. Six network-disabled missions recovered 17 of 17 survivors. All 18 missions recorded zero collisions.

This is simulator accuracy, not a claim of physical-world accuracy. ROS 2, Gazebo, real radios, sensor drivers, flight/drive dynamics and hardware timing remain outside this milestone.

## Implemented behavior

- Each agent broadcasts its sender ID, monotonic sequence, common-entry frame ID, uncertain local pose, current goal, frontier graph deltas, thermal/acoustic evidence and bounded map deltas.
- `PeerNetwork` performs neighborhood delivery with heterogeneous communication radii, wall attenuation or strict LOS, packet loss, seeded delay, byte budgets, TTL expiry, partitions, deduplication and reconnection counting.
- Periodic bounded map snapshots recover changes missed during loss or partition.
- A receiver merges only unknown cells and only when the shared entry frame and both uncertainty bounds are acceptable; otherwise it records a refused merge.
- Goal selection has no global reservation table. Active peers independently compute the same rendezvous owner for coarse frontier regions. If a peer vanishes from delivered-message TTL state, its branches are reassigned automatically.
- Agents continue their local frontier loop when the network is disabled.
- Simultaneous movement supports safe convoy chains in narrow corridors, rejects swaps/same-cell conflicts and uses a deterministic local yield rule for opposing intents.

## Anti-overfitting protocol

Seeds 400–405 were used while developing transport and corridor behavior. A first locked holdout on seeds 700–711 scored 38/44 (86.36%) and failed the 90% gate. Those seeds were retired into development, and their traces identified branch allocation—not packet transport—as the main failure.

The final change was general active-peer rendezvous ownership of distinct frontier branches. A rejected robot-ID tail-sampling experiment was removed after it regressed a retired case. The final code was then locked and evaluated on untouched networked seeds 800–811 and offline seeds 860–865. No algorithm parameters were changed during that final holdout.

## Final locked audit

Run:

```bash
python scripts/audit_step4_network.py
```

Predeclared gates and results:

| Measure | Gate | Result |
|---|---:|---:|
| Networked survivor recall | ≥90% | 40/42 = 95.24% |
| Recall at 30% packet loss | ≥85% | 14/16 = 87.5% |
| Network-off survivor recall | ≥50% | 17/17 = 100% |
| Mean networked coverage | ≥50% | 86.32% |
| Networked duplicate-goal ratio | ≤35% | 5.78% |
| Collisions | 0 | 0 |
| Minimum throughput | ≥5 steps/s | 20.04 steps/s |
| Deterministic exact replay | required | passed |
| Transport property cases | required | 200/200 |
| Large generation cases | required | 100/100 |

The full missions sampled portrait and landscape storage dimensions from 64–96 by 112–180 cells. Actual final-cohort maximum dimension was 166, agent counts were 5–9, rover/drone ratios varied independently, navigable footprints were connected and highly non-rectangular, and each networked mission isolated `rover_0` during steps 20–60. The 100 generation cases covered the configured 4–10-agent range.

Transport totals across the 12 final networked missions included 133,827 delivered messages, 18,646 packet-loss drops, 5,494 partition drops, 2,225 reconnections, 18,604 merged map cells and 14,788 uncertainty-refused merges. These counts prove that the pass did not bypass the fault model.

## Full regression evidence

- Complete tests: 75 passed.
- Step 1: three-seed gate passed.
- Step 2: 55/55 survivors, zero collisions.
- Frozen Step 2 stress audit: 44/46 (95.65%), zero collisions, 100% confirmation precision.
- Step 2.5: 21/22 (95.45%) across eight large irregular missions; 50/50 generation cases.
- Step 3 checkpoint: restored successfully; PPO 33/51 (64.71%), held-out teams 26/40 (65%), frozen frontier comparison 50/51 (98.04%), zero collisions and invalid actions.

## Honest limits before ROS 2/Gazebo

- The map is finite and grid-based. Runtime and mission budget must scale with area, geometry and robot count; no finite swarm can guarantee an unlimited site.
- Drones remain 2D proxies and do not model altitude, aerodynamics, downwash or 3D occlusion.
- Radio behavior is a deterministic seeded abstraction, not DDS discovery/QoS or a calibrated RF channel.
- Thermal and acoustic signals are probabilistic abstractions, not hardware sensor models.
- The common-entry transform is assumed. Step 4 validates uncertainty gating, not online multi-robot transform estimation.
- Two survivors were missed in the final cohort. The system exceeds the requested 90–95% target but is not a guaranteed life-safety system.

The next stage should wrap each agent loop as a ROS 2 namespace/node group, map message fields to explicit interfaces and QoS profiles, replace grid actions with Nav2/flight controllers, and replay the same loss/partition/variable-team matrix in Gazebo before any hardware claim.
