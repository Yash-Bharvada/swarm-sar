# Part 1 architecture

The engine owns the episode RNG and passes it to generation, victim placement, movement-order shuffling, and sensor noise. Calling `reset(seed)` replaces that generator, so a seed plus an action sequence fully identifies an episode.

```text
YAML configs
    |
    v
SwarmWorld.reset --> generator --> reachability cleanup --> victim placement
    |                                                       |
    +--> private Robot belief maps                          |
    |                                                       |
SwarmWorld.step(actions)                                    |
    +--> shuffled sequential movement                       |
    +--> vision / private belief updates                    |
    +--> thermal + acoustic sensing <-----------------------+
    +--> line-of-sight confirmation
    +--> observations + metrics + done

Renderer <--- explicit world state (debug/user interface only)
```

The policy-facing observation contains only private belief data, normalized battery, noisy readings and their previous values, odometry, and the last collision flag. Ground-truth grids and victim records stay on `SwarmWorld` for simulation, metrics, and explicit debug rendering; they never enter observations.

Movement intents are processed in a newly shuffled order each step. Occupancy is updated after each accepted move, preventing overlaps and swaps. Dead robots are excluded from occupancy. Rendering imports pygame lazily, so importing or training with the engine does not initialize a display.
