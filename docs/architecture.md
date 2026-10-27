# Blueprint Steps 1–3 architecture

The core owns the episode RNG and passes it to generation, survivor placement, movement-order shuffling, odometry drift, detection misses, false positives and sensor noise. Calling `reset(seed)` replaces that generator, so a seed plus an action sequence fully identifies an episode.

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
    +--> shuffled sequential movement + odometry drift      |
    +--> vision / private belief updates                    |
    +--> thermal + acoustic sensing <-----------------------+
    +--> line-of-sight confirmation
    +--> observations + metrics + done

Artifact logger <--- truth for offline JSON/CSV evaluation only
Renderer        <--- explicit world state (debug/user interface only)
```

Step 2 adds a non-learning controller above the fixed PettingZoo contract. Each agent's private belief independently produces frontier clusters and a NetworkX graph. A reservation table prevents duplicate targets in this benchmark; it does not merge beliefs. Thermal evidence becomes a suspected-survivor node, and confirmation requires repeat evidence or corroboration before the simulator checks physical range and LOS.

The policy-facing observation contains only private belief data, normalized battery, noisy readings and their previous values, drifting odometry with uncertainty, frontier features/action mask, a range-limited fixed peer summary, and the last collision flag. Ground-truth grids and survivor records stay on `SwarmWorld` for physics, metrics, explicit debug rendering and offline artifacts; they never enter observations.

Step 3 wraps that contract in a fixed 129-value vector and trains two RLlib PPO modules. Every `rover_*` agent maps to `rover_policy`; every `drone_*` agent maps to `drone_policy`, so adding agents does not add neural networks. Curriculum episodes vary team size while each actor executes from its own observation. A local one-step safety shield rejects occupied or duplicate immediate movement targets below policy goal selection. Seeded categorical checkpoint inference preserves PPO's exploratory distribution reproducibly.

Movement intents are processed in a newly shuffled order each step. Occupancy is updated after each accepted move, preventing overlaps and swaps. Dead agents are excluded from occupancy and individually removed from the PettingZoo active-agent list. Rendering imports pygame lazily, so importing or training with the environment does not initialize a display.
