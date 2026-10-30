# Blueprint Steps 1–4 architecture

The core owns the episode RNG and passes it to generation, survivor placement, movement-conflict resolution, odometry drift, detection misses, false positives and sensor noise. Calling `reset(seed)` replaces that generator, so a seed plus an action sequence fully identifies an episode.

```text
YAML configs
    |
    v
ParallelEnv.reset --> SwarmWorld --> rooms/corridors --> survivor placement
    |                                                       |
    +--> private Robot belief maps                          |
    |                                                       |
ParallelEnv.step(frontier/investigate/hold)                 |
    +--> local frontier extraction + A*                     |
    +--> simultaneous safe movement + odometry drift        |
    +--> vision / private belief updates                    |
    +--> thermal + acoustic sensing <-----------------------+
    +--> line-of-sight confirmation
    +--> observations + metrics + done

Artifact logger <--- truth for offline JSON/CSV evaluation only
Renderer        <--- explicit world state (debug/user interface only)
```

Step 2 adds a non-learning controller above the fixed PettingZoo contract. Each agent's private belief independently produces frontier clusters and a NetworkX graph. A reservation table prevents duplicate targets in this benchmark; it does not merge beliefs. Thermal evidence becomes a suspected-survivor node, and confirmation requires repeat evidence or corroboration before the simulator checks physical range and LOS.

The policy-facing observation contains only private belief data, normalized battery, noisy readings and their previous values, drifting odometry with uncertainty, frontier features/action mask, a range-limited fixed peer summary, and the last collision flag. Ground-truth grids and survivor records stay on `SwarmWorld` for physics, metrics, explicit debug rendering and offline artifacts; they never enter observations.

The frozen Step 3 checkpoint wraps its contract in a fixed 129-value vector and trains two RLlib PPO modules. Every `rover_*` agent maps to `rover_policy`; every `drone_*` agent maps to `drone_policy`, so adding agents does not add neural networks. Curriculum episodes vary team size while each actor executes from its own observation. A local one-step safety shield rejects occupied or duplicate immediate movement targets below policy goal selection. Seeded categorical checkpoint inference preserves PPO's exploratory distribution reproducibly.

The new `gpu-v1` contract is deliberately incompatible with that historical checkpoint. It has 229 values: the original local fields plus previous high-level action, active-goal features, mission progress, and eight bounded per-peer message slots. Its contract JSON and hash are checked into `training/artifacts/`. GPU-v1 supports a 256-cell LSTM, recurrent checkpoint inference, disjoint parallel-worker seed scheduling, resumable numbered checkpoints and Step 4 expert-demonstration export.

Step 4 inserts `PeerNetwork` between independent sender outboxes and recipient inboxes. It applies radio range, wall attenuation or strict LOS, seeded packet loss, delay, bandwidth, TTL expiry and configured partitions. Messages contain a sender/sequence identity, common-entry frame, uncertain pose, goal, graph frontier deltas, sensor evidence and bounded occupancy-map chunks. Receivers deduplicate messages, refuse unaligned/uncertain map merges, and periodically receive snapshot chunks so missed changes can recover after reconnection.

The Step 4 controller reads only its agent's observation, private map and delivered messages. It uses active-peer rendezvous hashing to assign frontier branches without a reservation server; ownership changes automatically when a peer disappears. Thermal evidence can be independently corroborated by acoustic evidence. A local traffic rule clears opposing intents in narrow passages, while the simultaneous movement resolver permits safe follow-the-leader chains, blocks swaps and duplicate targets, and prevents overlap.

Ground truth remains limited to physics, collision/radio propagation, offline metrics and debug artifacts. Rendering imports pygame lazily, so importing or training with the environment does not initialize a display.
