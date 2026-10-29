# PPO-controlled 3D browser missions

The browser can now render the selected 753664-step recurrent PPO checkpoint's
actual Python missions. Python owns the map, robot positions, private beliefs,
thermal/acoustic sensors, action masks, recurrent state, peer transport,
confirmation and termination. The TypeScript frontier controller never ticks
while PPO mode is selected. Actor inputs remain each robot's existing private
GPU-v1 observation; truth sent to the browser is operator rendering data only.

## Start locally

Use the repository's installed Python environment (Python 3.12+ for this
checkpoint/service), then run from the repository root in one terminal:

```bash
.venv/bin/python tools/ppo_service.py
```

On a fresh checkout this verifies and extracts the included handoff archive
into `results/ppo_754k_handoff`. Startup checks the checkpoint tree against the
recorded evaluation provenance, both restored parameter hashes and the 229-value
observation contract. The service runs CPU inference and does not start training
or a Ray cluster. It binds to `127.0.0.1:8765`.

In a second terminal:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open http://127.0.0.1:5173. Click **Heuristic → New PPO mission** above the map.
Wait for **PPO · 754k** and the ready mission, then click **Launch mission**.
Defaults are seed 10000, 32×32 rooms and two rovers/two drones, matching the
recorded nominal development example. Camera, follow, audio, clean viewing,
private maps and discovery stories remain presentation features. Every discovery
pauses further requests until Continue exploration; final confirmation leads to
the mission report. Reset creates a new Python mission and fresh recurrent state.

The controller menu also supports development seeds 10000–10099, 24–56-cell maps,
rooms/maze/cave layouts, one to ten robots, and radio on/off for labelled demo
missions. Custom options are not the original frozen evaluation suite. Mission
geometry, survivor editing and manual driving stay available in **Browser
heuristic** mode; PPO uses its Python-generated world. Switching back restores
the saved heuristic mission settings. Graphics, camera, sound and playback speed
remain available in PPO mode.

## Request and failure behavior

Vite proxies `/api/ppo` to the loopback service. The Python service offers health,
create, read, single-step and close operations; it does not accept browser robot
actions or truth as policy inputs. Each mission has an opaque ID and independent
recurrent state. Steps carry the expected step counter. Retrying a lost response
returns the already committed snapshot rather than advancing twice.

The client permits one in-flight step, ignores responses from replaced missions,
and freezes on connection/protocol errors without heuristic fallback. Pause stops
new requests; at most one already submitted step may finish. Reset is the explicit
recovery action. Browser reload/reset releases an earlier mission associated with
that tab's client key. Up to four sessions are supported, with a 30-minute idle
expiry. Playback speed is a target rate; backpressure slows it when inference or
rendering takes longer. Hidden tabs issue no new steps.

Actual private maps, sensor readings, aggregate radio counters, current physical
radio links, delivered-message snapshots and scheduled packet pulses are exposed.
Per-packet drop histories and reconnect event traces are not available from this
Python adapter; the Activity panel labels that limit. Goals are displayed when
available; full local route previews are not exported. The decoration/cutaway
walls do not change Python collision or sensing rules.

This is a local development integration. Production hosting/authentication,
ROS learned-policy execution, calibrated physics/sensors and sealed final-test
evaluation remain separate work. The browser default remains the heuristic,
with an explicit controller label for each runtime.

## Evidence and checks

[Browser validation](browser_ppo_validation.json) drives real HTTP requests and
checks exact map/position/battery/coverage agreement with Python, pause and all
four survivor conversations, reset, connection-loss handling, mobile controller
options and switching back to the heuristic. The default run reproduced the
recorded seed-10000 result: **4/4 survivors, 94 steps, 90.48% coverage**, zero invalid
actions and zero post-shield collisions. This is one development reproduction,
not additional held-out performance evidence.

```bash
.venv/bin/python -m pytest -q tests/test_ppo_service.py
cd frontend
npm test
npm run build
```

With both servers running, browser checks use Python Playwright and installed
Chrome (the checked script's graphics flags target this Mac):

```bash
python3 frontend/scripts/ppo_qa.py
```

The service lives in `tools/` so all 94 audited training-source hashes, configs,
source manifests and immutable training tags remain unchanged. The original
training checkout on the GPU server does not need to be updated.

## Seed selection and traversable rubble

The map seed accepts every integer from 10000 through 10099, not just the default
10000. A visible validation message explains invalid entries such as 1000, and
Shuffle chooses another allowed seed. This is an evaluation-separation guardrail:
0–9999 are training seeds and 20000–20199 are sealed final seeds. The model itself
is not intrinsically limited to one map seed.

RUBBLE cells mean low, traversable rough debris in the grid simulator. Rovers
spend 2 battery units entering rubble versus 1 on ordinary ground; drones spend
1 in either case. Artwork now uses low chips (0.025–0.06 scene units high) so
traversable cells do not depict tall boulders. WALL cells represent blocking
obstacles and stop both types in this grid model. Decorative scale is not a
physical calibration. Wheel climbing, suspension/contact dynamics and flight
over walls are not simulated here. Changing traversal/energy rules would require
new evaluation and potentially fine-tuning; this presentation correction changes
none of those rules or the verified checkpoint.

## Battery modes

Mission settings now offer **Limited** (the default) and **Unlimited** for both
heuristic and PPO missions. The PPO controller menu also offers a battery mode
for new missions. Changing the mode in settings resets the current mission on
the same map; launch again to explore. The selection survives mission resets.

Limited retains the existing budgets and consumption. Unlimited sets movement,
rubble and idle costs to zero in the mission's own robot configuration. Battery
therefore stays at its finite full value, and the policy still receives the same
229-value observation contract. Fleet indicators show infinity and the scene
labels its battery mode. Time limits, sensing, navigation and radio rules still
apply. The Python service applies this override before creating the world;
training source files, checkpoint weights and prior evaluation evidence are
unchanged. Unlimited runs are a different condition from the recorded limited
battery benchmark. Restart an already-running Python service after updating.

No tests or evaluation missions were run for this change, at the user's request.
Compilation/build checks are recorded separately from behavioral validation.
