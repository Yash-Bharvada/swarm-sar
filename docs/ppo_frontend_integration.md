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
