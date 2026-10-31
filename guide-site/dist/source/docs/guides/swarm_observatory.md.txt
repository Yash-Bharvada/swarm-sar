# Swarm intelligence observatory

The mapping and communications view now uses a real Three.js scene, with the same cream, sage and forest-green palette as the main simulator. The duplicate dark ROS dashboard and the old flat canvas renderer have been removed.

## Open

From the simulator, click **Swarm intelligence**. Direct routes:

- Browser mission: `/?mode=observatory`
- ROS SLAM: `/?mode=ros`
- Existing `/?mode=ros&view=observatory` links also open the same unified ROS view.

Run the frontend with `npm run dev -- --host 127.0.0.1` from `frontend`, and use the port Vite prints. World/observatory navigation preserves the browser mission and the Python PPO session. Switching source by a full URL reload is a separate session.

The main simulator also has a quieter HUD: compact fleet/radio context, grouped mission/display tools and a smaller playback dock. Mission configuration, audio, overlays, camera controls, manual driving, keyboard shortcuts and discovery pauses remain available.

## What changed

The scene fills the available viewport. Repeated metric cards, permanent side panels, miniature maps and overlapping labels are gone. Agent details open only when selected; messages appear in a collapsible tray. The disconnected ROS view shows one connection prompt and no placeholder robots or invented maps.

**3D map** displays the selected agent's actual private occupancy, raised known walls, robot models, trajectories, goals and actual communication. Unknown cells stay unknown. The renderer uses instanced occupancy geometry; any capped samples retain their measured cell footprint rather than inflating one sample into a block of known map.

**Peer network** presents posed agents in a spatial coordination layout, with actual transport links and packet pulses. It is a visualization of communication topology, not learned neural activations or evidence that the model uses a GNN. No disconnected agent is assigned an invented position.

Drag to orbit, scroll or use the buttons to zoom, and select a robot from the scene or compact agent rail. The camera button switches between isometric and top-down inspection. Reset view restores the camera. Map layers are behind the layers button. Freeze stops the visualization; the separate launch/pause button controls the browser mission. Use **Continue after discovery** when a survivor encounter pauses it.

Open **Messages** to filter actual delivered/applied/dropped events and export the current telemetry snapshot as JSON. The tray is closed by default. Renderer failures show a recovery screen while telemetry and controls remain available. The main simulator header also links to the public English audio fieldbook at https://swarmsar.vercel.app.

## ROS connection and radio controls

Start the existing Linux SLAM launch with `rosbridge:=true`, open `/?mode=ros` and select **Connect ROS bridge**. Use `ws://localhost:9090` on that host or via an existing SSH tunnel. The original ROS route now opens this interface directly; no extra dashboard is needed.

Select an agent to reveal **Isolate radio / Reconnect radio**. Those buttons use the existing ROS SetBool service, with isolation state reported by network telemetry. They are disabled until the connection, agent data and network status are fresh. A service acknowledgement does not fabricate a changed radio state. The page does not publish velocity, goals or map commands.

## Data boundaries

Browser mapping remains a private belief with simulated poses, not a SLAM backend. Browser beliefs include merged knowledge; separate peer-only cell provenance is unavailable. ROS rover data comes from the SLAM estimate, while the existing drones retain simulator localization. Missing battery/covariance information is not invented.

Packet delivery and receiver application remain separate states. Browser shared-cell counts are cumulative accepted updates; ROS receiver-applied counts describe snapshots observed during the current UI connection. Stale/disconnected telemetry or stopped simulation time stops motion effects. Clock/session changes reset affected visual state. Reduced-motion preferences are respected.

## Verification

Local checks cover production build, frontend tests and actual-browser navigation, mission continuity, PPO bridge continuity, 3D rendering, mobile bounds, packet filters/export, disconnected empty states and synthetic ROS service/topic contracts. The synthetic ROS/PPO checks validate presentation contracts only; live Gazebo/SLAM still requires the Linux machine.

```bash
.venv/bin/python frontend/tools/validate_observatory_ui.py --url http://127.0.0.1:5178 --output artifacts/observatory_redesign
```

Use `--browser-executable /absolute/path/to/chromium` when needed by the installed Playwright version. See `artifacts/observatory_redesign/` for test records and actual-browser screenshots. The ROS disconnected screenshot contains no synthetic operational mapping evidence.
