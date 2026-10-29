# Swarm Mission Control: browser 3D simulator

A standalone browser simulation for the swarm-sar disaster-response project. Rovers and drones
search a site, share maps over a lossy peer-to-peer radio, and locate survivors. The world is a
bright isometric island with warm sandstone paths, terracotta ruins, blocky greenery, turquoise
water, and daylight. The presentation update changes the interface, camera, art, and animation;
the deterministic search, sensing, communication, and collision mechanics are unchanged.

- **Separate from ROS 2 and Gazebo.** Everything runs in the browser tab. No Python runtime, backend, WebSockets, database, or cloud service is required.
- **Autonomous Mode is not RL.** *Decentralized Autonomous Mode* implements the Step 4 decentralized frontier-controller principles (`src/swarm_sar/baselines/decentralized.py`) in TypeScript. It is not PPO, RL, MARL, or a GNN.
- **Robots use local knowledge.** Each robot decides from its private map, sensors, battery, pose, and messages that actually reached its inbox. There is no central planner, reservation table, or access to hidden survivor positions.

See [CONTROLLER_COMPATIBILITY.md](CONTROLLER_COMPATIBILITY.md) for the mapping to the Python
reference and the intentional differences.

## Install and run

Requires Node.js 18 or newer.

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

```bash
npm test             # Headless simulation and presentation-state tests
npm run build        # Type-check and build dist/
npm run preview      # Serve the production bundle locally
```

Optional interaction verification, with Python Playwright and local Chrome already installed:
start `npm run dev -- --host 127.0.0.1 --port 5174`, then run
`python3 scripts/browser_controls_qa.py` from `frontend/`. It checks real placement clicks,
moving-robot focus, focus transfer, scene-only viewing and mobile restoration. It writes
`docs/browser_controls_validation.json` at the repository root and temporary screenshots.

## Using the simulator

The world occupies the workspace. A command rail opens one panel at a time; select **World**
or close the panel to return to the full scene.

- **Mission:** choose the site, world seed, rover/drone team, and control mode. Radio, sensor, graphics, and mission tools are expandable sections.
- **Fleet:** inspect each robot's objective, battery, and connection. Expand its local map, sensor readings, communication, or technical details when needed. Selecting a robot in the world opens its fleet details.
- **Activity:** review recent mission events or open the **Radio log** for packet details and communication counters.
- **Controls:** see camera shortcuts and manual-driving instructions.

1. Open **Mission** and choose a site: Collapsed Office, Mine Tunnel, Earthquake Apartment, or Random Irregular Site.
2. Keep the default two rovers and two drones, or choose any mix of 1–10 robots. World settings lock after launch; reset the mission to change them.
3. Press **Launch mission** or Space. Playback controls offer pause, resume, reset, and 0.5×, 1×, 2×, or 4× speed.
4. Watch the compact mission counters and the team explore. Open **Fleet** or select a robot to inspect a particular decision.
5. Enable **Layers** when you want routes, radio activity, sensor evidence, or explored-map information.

The mission reset control asks before clearing an active mission. Camera reset simply restores
the world overview.

### Custom survivors

Before launch, use **Mission → Survivors** to apply an exact count, randomize positions, or
choose **Place on map**. The placement view shows amber markers: click a reachable tile to add
a survivor, or click a marker to remove it. **Done placing** hides these authored locations;
robots still learn survivor locations only through their sensors. Editing preserves your camera.

There is no fixed small survivor cap. Capacity is the number of reachable walkable cells outside
the robot staging square, with one survivor per tile. Walls, staging and duplicate placements
are rejected. Clear the layout to start from zero, then place at least one survivor before launch.
Changes lock during a mission. Reset preserves the authored layout; changing the site or seed
restores automatic placement. Automatic uses the standard seeded 2–4 survivors (the validation
scenario uses its own fixed count). Large counts increase computation and do not increase mission
time or battery budgets, so placing many survivors does not guarantee finding all of them.

### Camera and keyboard controls

The orthographic camera starts in a level, north-up angled view, so the map edges stay
horizontal. On-screen controls provide smooth zoom with a visible **60–400%** readout, angled and top-down views, **Fit world
to view**, and **Follow** for the selected robot. **Focus camera** in robot details frames and
continuously follows that robot. Selecting another robot transfers the lock. Deselecting,
dragging/zooming the camera, changing its view, or stopping Follow releases it. Scrolling zooms
around the ground under your cursor; the +/− buttons and keyboard zoom around the last point
you indicated in the world, falling back to the view centre before the first pointer interaction.

| Input | Action |
|---|---|
| Left-drag | Orbit |
| Right-drag | Pan |
| Wheel or + / − | Zoom at the cursor / last indicated world point |
| R | Fit the world to the isometric overview |
| Select a robot, then F | Focus the camera on that robot |
| Click a robot | Select it; click again to deselect |
| Space | Launch, pause, or resume |
| Esc | Close the panel and deselect |
| Manual or Mixed mode, robot selected | Click a walkable tile to set a waypoint |
| Arrow keys or WASD | Step the selected manual robot |
| E / X | Scan for a survivor / stop |
| H | Hide / restore the interface and diagnostic overlays |

**Watch maze** fills the workspace with the scene, hiding panels, labels, selection rings and
diagnostic layers while retaining their settings. It keeps the mission and camera follow running.
Use H, Esc or **Show interface** to return. It is unavailable during survivor placement so the
authoring status cannot disappear accidentally.

Camera and driving shortcuts do not fire while typing in a field or using Ctrl/Command/Alt.
Space on a focused button retains its native button action; driving keys still work after selecting a robot.

Control modes:

- **Auto:** every robot runs Decentralized Autonomous Mode.
- **Manual:** the operator drives the selected robot while the others hold.
- **Mixed:** the operator drives the selected robot while the others stay autonomous.

Manual commands pass through the same collision-safety layer and physics as autonomous moves.

### Layers and maps

Only compact robot badges, such as R1 and D1, are enabled initially; the selected robot shows its full label.
The terrain starts clear, with optional information
available through **Layers** or **Mission → Graphics & overlays**:

- planned routes, shown for the selected robot;
- radio links, message activity, ranges, and a network graph;
- thermal and acoustic evidence;
- explored map;
- robot labels;
- hidden-survivor debug view.

The explored-map layer applies a pale ground tint to unknown cells. With a robot selected it
shows that robot's private belief; without a selection it combines the team's explored maps.
It does not place a dark mask over the world. The local mini-map inside robot details also
uses pale unknown terrain, sand paths, green walls, and contrasting rover/drone markers.
Teammates appear at their last delivered reported position.

The hidden-survivor debug view displays a banner. Its information is never supplied to robots.
Confirmed survivors appear as seated human figures, with a small one-time confetti burst and
a persistent **SURVIVOR SAVED** flag. The subtitle **Location confirmed** is deliberate: this
feedback celebrates locating a survivor. Treatment and physical evacuation are not modeled.
Reduced-motion preferences suppress confetti, waving, and flag animation.
The **Activity → Radio log** lists sender, recipient, sequence, message type, delivery state,
delay, expiry, drop reason, and map-delta size. Aggregate counters are expandable.

### Music and sound

Use the speaker button near **Watch maze**, or press **M**, to enable sound. A fresh page waits
for that explicit interaction. The adjacent settings button opens independent **Master volume**,
**Ambient music**, **Fleet sounds** and **Event sounds** sliders. Levels are remembered locally;
playback permission is not assumed on the next visit. M also mutes/unmutes during clean viewing.

The original synthesized soundtrack combines slow, overlapping chords with gentle bell-like
melodies. It continues through mission pauses and resets. Rovers have low motor/wheel sounds;
drones have airy rotor sounds. Their stereo position and volume follow the camera view, and
focusing a robot brings that unit forward with a distinct rover/drone focus cue.

Short effects mark launch, pause/resume, reset, survivor confirmations, completion, investigation,
manual waypoints, placement/removal, radio loss/recovery, low batteries and common UI actions.
Frequent map-sharing/replanning cues are rate-limited and coalesced. Important discoveries soften
the music briefly. Vehicle sounds fade when paused or depleted. Switching away from the tab
suspends audio, and returning does not replay an event backlog. Survivor sounds do not replay
when changing graphics quality or selecting robots.

All audio is generated locally with Web Audio: no external soundtrack requests, downloaded
samples or new runtime packages. Audio observes presentation state and actual events; it never
changes the simulation, consumes its random generator, or reveals hidden survivor positions.

With the dev server running, optional browser audio checks run with
`python3 frontend/scripts/audio_qa.py --full-cycle` from the repository root (requires Python
Playwright and Chrome). Results are written to `docs/browser_audio_validation.json`; this
checks actual audio output and interactions, rather than subjective listening quality.

### Validation scenario

Before launch, open **Mission → Mission tools → Load validation scenario**. Rover 1 is
partitioned from step 20 to step 60, with 15% packet loss and a 1–3-tick message delay, on a
map containing a long one-cell-wide corridor. Launch, then enable radio and sensor layers
when you want to inspect them. The scenario demonstrates packet loss, temporary isolation,
reconnection, map sharing, survivor confirmation, and safe single-file movement.

`src/tests/demo.test.ts` verifies those behaviors headlessly.

## Rendering and performance

Graphics quality is under **Mission → Graphics & overlays**. The default is **Balanced**
(the `medium` setting in code).

| Quality | Pixel ratio | Sun shadows |
|---|---|---|
| Low | 1 | Off |
| Balanced | 1–1.5 | 1024 × 1024 |
| High | 1–2 | 2048 × 2048 |

Canvas antialiasing stays enabled across quality changes so the current camera and
interpolated motion are preserved without recreating the WebGL context.

All profiles use direct daylight rendering without a postprocessing chain. There is no
vignette, cloud cover, light-shaft effect, or robot spotlight pass. Terrain, rubble, vegetation,
and other repeated objects use instanced geometry. Textures are generated locally rather
than downloaded. The atmosphere setting controls light distance haze and restrained particles.

The engine advances at **4 ticks per real second at 1×**, up to **16 ticks per second at 4×**;
each tick represents one second of mission time. Robot rendering interpolates positions
linearly between ticks, with smooth turning, rover-wheel animation, and drone-rotor animation.
Pausing preserves the current interpolated pose. These visual motions do not alter physics.

Frame rate depends on the browser, GPU, viewport size, robot count, and enabled layers. For
slower hardware, choose Low, reduce playback speed, and disable radio message effects.
No particular frame rate is guaranteed.

## Architecture

```text
React UI (src/app, src/components)
  command rail → Mission / Fleet / Activity / Controls
  compact mission HUD, playback, camera tools, optional layers
                        │
Zustand store (src/store)
  settings, overlays, selection, camera requests, status, engine
                        │
React Three Fiber scene (src/scene)
  orthographic camera, daylight, instanced island world
  interpolated robots, optional network/evidence/map layers
                        │
Deterministic simulation core (src/simulation)
  commands → local controller → collision safety → movement
  → sensing → survivor investigation/confirmation
  → peer broadcasts and actual deliveries → private-map merge
```

The simulation core has no React or Three.js imports and runs unchanged in Vitest. With the
same options and command log, `SimulationEngine.stateHash()` produces the same result.
Rendering reads the engine and interpolation clock; camera changes do not change mission state.

## Tests

`npm test` runs these suites:

| Suite | Covers |
|---|---|
| `scenario.test.ts` | Seeded reproducibility, portrait/landscape maps, reachable survivors, clear spawn |
| `determinism.test.ts` | Matching state hashes, network metrics, feed, and command-log replay |
| `network.test.ts` | Loss, delay, expiry, range/wall attenuation, partitions, recovery, deduplication |
| `autonomy.test.ts` | Private observations, hidden-survivor isolation, network-off autonomy, delivered map sharing |
| `collision.test.ts` | No overlaps or swaps, narrow-corridor convoys, yielding, wall constraints, manual safety |
| `controller.test.ts` | Frontier ownership, corroboration, claim release, action masking, no truth access |
| `demo.test.ts` | Validation scenario loss, partition, recovery, sharing, survivor detection, safe convoy traffic |
| `missions.test.ts` | Complete missions on every preset with recall, coverage, and collision guards |
| `presentation.test.ts` | Clean defaults, repeated camera requests, view/follow/focus behavior, camera-target cleanup, simulation isolation |
| `audio.test.ts` | Explicit startup, volume boundaries, event priorities, rate limiting, history suppression and simulation isolation |

## Browser requirements

Use a browser with WebGL 2 and hardware acceleration. A desktop viewport provides the most
space for the world and controls; the interface also adapts to narrower viewports with a
compact rail and panels. A keyboard and mouse offer the complete driving and camera controls.

## Known limitations

- Movement remains grid-based. Smooth animation is a visual interpolation, not a continuous physics model.
- Drones remain 2D proxies with visual altitude. They obey the same wall constraints as Python Step 4 and do not perform full flight dynamics.
- The island art is a presentation of the generated search grid; decorative terrain does not add new navigable areas or change controller mechanics.
- Radio, thermal, and acoustic models are seeded abstractions, not calibrated physical sensors or RF propagation models.
- Browser and NumPy random streams differ, so runs are not bit-identical to Python for the same seed. See [CONTROLLER_COMPATIBILITY.md](CONTROLLER_COMPATIBILITY.md).
- Robots can be added or removed only before launch.
- No PPO/ONNX learned policy is included. `LocalView → Decision` remains the integration point.
- Maps stay browser-friendly, around 28–56 cells per side. Browser recall is a regression guard, not a reproduction of the much larger Python Step 4 audit.
