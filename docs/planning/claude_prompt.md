# Claude Prompt — Swarm Mission Control Frontend Visual Overhaul

> **Usage:** Paste this entire prompt into Claude, attach the reference image (the isometric pixel-art village screenshot), and send. Claude will have full context to produce the code changes.

---

## Context

I have a React + Three.js + TypeScript browser simulator called **Swarm Mission Control** for a disaster-response robot swarm project (`swarm-sar`). It is a 3D top-down/isometric view of rovers and drones exploring a collapsed building, sharing maps over a lossy peer-to-peer radio network, and locating survivors.

The **reference image** I've attached shows the visual style I want to reach: a warm, lush, isometric pixel-art game (think Stardew Valley / A-Frame meets Apple Arcade). It has:
- Chunky, vibrant, colourful isometric tiles with great depth
- Lush greens, warm sandy paths, turquoise water accents
- Soft fluffy clouds and rich environmental shadows
- Warm wooden/earthy tones for props and structures
- A cozy, polished Apple-Arcade / macOS game aesthetic

I want you to transform the Swarm Mission Control 3D scene and UI into something equally polished and visually inviting — while keeping all the simulation logic untouched.

---

## Codebase Structure (read-only context, do NOT change simulation logic files)

```
frontend/
  src/
    scene/
      World.tsx          ← Walls, floors, rubble, dust (Three.js instanced meshes)
      Robots.tsx         ← Rover and drone 3D meshes, scan sweeps, labels
      Network.tsx        ← NetworkLinks (thin colored lines), PacketPulses (moving dots)
      Overlays.tsx       ← CoverageFog, SurvivorBeacons, EvidenceMarkers
      SceneRoot.tsx      ← Camera, lights, canvas, scene composition
      common.ts          ← COLORS, cellToWorld, QualityProfile, texture generators
    components/
      TopBar.tsx         ← Mission timer, play/pause, speed, quality
      LeftPanel.tsx      ← Scenario/network/mode settings
      RightPanel.tsx     ← Fleet status, robot inspector, mini-map
      EventFeed.tsx      ← Plain-language event feed + Advanced Network Log table
      SceneHud.tsx       ← In-canvas HUD overlays
    styles/
      app.css            ← All UI CSS (CSS custom properties + layout grid)
    store/
      simStore.ts        ← Zustand store (settings, overlays, engine, version)
    simulation/          ← DO NOT CHANGE ANYTHING IN HERE
```

**Key existing colours** (from `common.ts`):
```ts
COLORS = {
  rover: '#ff9a3c', drone: '#46d9ff',
  healthy: '#38f28a', weak: '#ffd23f', down: '#ff3b4a',
  survivor: '#7dffb2', heat: '#ff6a2b', sound: '#b48cff',
}
```

**Current CSS theme** (from `app.css`): dark, gunmetal blue-grey panels. I want this replaced with a lighter, warmer, glass-morphism Mac-style panel system for the UI.

---

## What I Want You to Build

### 1. 🌍 World / Environment — Isometric Game-Art Feel

**In `World.tsx`:**

- **Floor**: Replace the current procedural concrete texture with a **vibrant isometric tile grid**. Use warm sandy/earthy tones (`#e8d5a3`, `#d4c48a`) for open walkable tiles, with thin contrasting grout lines. Add subtle top-face highlights and left/right-face shading to give isometric depth.
- **Walls / Rubble**: Recolour with warm earthy browns and terracotta (`#8B4513`, `#A0522D`, `#CD853F`). Give rubble chunks slight randomised Y rotation and scale variation to look organic and chunky (like the stone blocks in the reference image).
- **Greenery props**: Procedurally scatter small bush/grass sprites on open cells near walls (use `THREE.Sprite` with a radial gradient canvas texture in lush green `#4caf50` → `#2e7d32`). About 1 per 6 open cells.
- **Water accent strip**: If the map has a boundary row, render it as turquoise/teal water (`#26c6da`) with a gentle sine-wave normal animation.
- **Lighting**:
  - Add a warm **directional sun light** at 45° azimuth, colour `#fff5e0`, intensity 1.8.
  - Add a soft **ambient light** in `#c8e6f5` (sky blue), intensity 0.6.
  - Add 2–3 **point lights** in emergency orange (`#ff7043`) floating above rubble piles.
  - Enable **soft shadows** at Medium+ quality (already has a shadows flag in QualityProfile).
- **Clouds**: Add 4–6 slowly drifting `THREE.Mesh` flat ellipsoid clouds (white `#ffffff` with soft edges, scale ~3×0.4×2) at Y=6–8, drifting slowly in +X at 0.02 units/s. On low quality, skip clouds.

---

### 2. 🤖 Robots — Expressive & Readable

**In `Robots.tsx`:**

- **Rover mesh**: Replace the current box with a proper chunky low-poly rover body:
  - Main body: rounded box (`THREE.BoxGeometry` with bevel effect via `THREE.EdgesGeometry` highlights), warm orange `#ff9a3c`, scale 0.7×0.45×0.55.
  - Two axle wheel pairs: dark grey cylinders rotated 90° on X, 0.18 radius.
  - A small antenna stub: thin cylinder 0.04 radius, 0.3 tall, silver `#b0bec5`.
  - **Emit a warm orange point light** (intensity 0.4, distance 2.5) from the body when alive — like a dashboard glow.

- **Drone mesh**: Replace with a proper quad-rotor silhouette:
  - Central hub: flat cylinder 0.25 radius, cyan `#46d9ff`.
  - Four arms: thin boxes radiating at 45°, 0.12×0.06×0.55.
  - Four rotor discs: flat rings `THREE.RingGeometry`, spin in `useFrame` at 800 rpm equivalent.
  - **Emit a cool cyan point light** (intensity 0.3, distance 2.5) beneath the drone.
  - Hover animation: sine-wave Y offset ±0.08 at ~1 Hz (each drone offset by its ID).

- **Scan sweep**: Make the existing expanding ring thicker (inner/outer ratio 0.6/1.0), increase opacity to 0.8, and add a **second trailing ring** at 60% scale for a double-pulse sonar effect.

- **Selection ring**: When a robot is selected, add a **hexagonal selection glow** beneath it (use a canvas-drawn hexagon texture, animated scale pulse 1.0→1.12→1.0 at 2 Hz).

---

### 3. 📡 Peer Communication Highlight — THE KEY FEATURE

This is the most important new feature. When a robot **detects something** (survivor evidence, new map cells) and **broadcasts a PeerMessage**, I want the entire communication chain to be visually highlighted, step by step:

**In `Network.tsx` — New Component: `CommEvent`**

The `SimulationEngine` already emits packet visuals (`PacketVisual` type). Enhance them with:

#### A. Discovery Flash (on the sender)
When a robot finds new evidence or frontier cells (detectable from `mapDeltaSize > 0` or `evidence.thermal > 0` in `PacketVisual`):
- Flash a **bright starburst** at the sender's position: a `THREE.Mesh` with a star-shaped plane geometry (or `THREE.Points` with a burst), colour `#ffeb3b` (yellow-gold), opacity 1 → 0 over 0.6s.
- Display a **floating toast label** using `@react-three/drei`'s `<Html>` at Y+1.5 above sender: `"🔍 Found heat sig!"` or `"🗺 Map update"` — fades out over 1.2s.

#### B. Transmission Arc (the broadcast)
When a packet is `in_flight`:
- Replace the current plain dot pulse with a **glowing energy arc** — a `THREE.QuadraticBezierCurve3` from sender to receiver, with the control point lifted 1.5 units above midpoint (giving a ballistic arc).
- Render this as a `THREE.TubeGeometry` with radius 0.05, emissive material in the COLORS scheme (healthy=green, weak=yellow).
- Animate a bright **travelling bead** (small sphere, radius 0.1) along the arc using `t = (clock.elapsedTime - startTime) / travelTime`.
- The arc itself glows and fades: full opacity when bead is mid-arc, fades at both ends.

#### C. Reception Burst (on the receiver)
When a packet is delivered (`state === 'delivered'`):
- Show a **ripple ring** expanding from the receiver's feet: `THREE.RingGeometry`, colour matching the sender's robot type, scale 0→2 over 0.4s, opacity 1→0.
- If `mapDeltaSize > 0` (new map cells learned), additionally show a brief **map-cell highlight**: flash the newly merged cells on the floor with a bright colour overlay (`#80deea` teal) for 0.8s.

#### D. Network Link Beautification
- Replace plain `THREE.Line` links with **dashed animated tubes**: use `THREE.LineDashedMaterial` with `dashOffset` animated in `useFrame` to make dashes flow in the direction of data.
- Healthy links: flowing green dashes. Weak: amber dashes, slower flow. Down: red static dashes, no flow.
- Add subtle **glow sprites** at each robot's antenna tip (small `THREE.Sprite` with the glow texture, colour matching health, scale 0.3).

#### E. EventFeed Integration
- In `EventFeed.tsx`, when a feed item has tone `'network'` and involves a peer message with `mapDeltaSize > 0`, highlight that row with a left-border glow: `border-left: 3px solid var(--accent)` and a brief background flash animation (`@keyframes row-flash`).

---

### 4. 🖥 UI — macOS Apple Arcade Glass Panel System

**In `app.css`:**

Replace the current dark gunmetal theme with a **warm glassmorphism system**:

```css
:root {
  /* New warm palette */
  --bg: #0d1117;                          /* near-black with warm tint */
  --panel: rgba(22, 27, 38, 0.88);        /* dark glass */
  --panel-glass: rgba(255,255,255,0.06);  /* frosted glass face */
  --glass-border: rgba(255,255,255,0.12); /* highlight rim */
  --glass-shadow: rgba(0,0,0,0.6);
  --accent: #64ffda;       /* mint green — Apple-ish */
  --accent-2: #ff9a3c;     /* warm orange for rovers */
  --accent-3: #46d9ff;     /* cyan for drones */
  --text: #e8f0fe;
  --muted: #8fa3c0;
  --good: #00e676;
  --warn: #ffca28;
  --bad: #ff5252;
}
```

- **Panels** (`.panel.left`, `.panel.right`): Apply `backdrop-filter: blur(24px) saturate(180%)`, `background: var(--panel-glass)`, `border: 1px solid var(--glass-border)`, `box-shadow: 0 8px 32px var(--glass-shadow)`, `border-radius: 16px`. Add subtle inner highlight on the top edge with `box-shadow: inset 0 1px 0 rgba(255,255,255,0.15)`.
- **Top bar**: Give it a frosted gradient `background: linear-gradient(to bottom, rgba(30,35,50,0.95), rgba(20,25,40,0.9))` with a fine 1px bottom border.
- **Buttons**: Rounded pill shape (`border-radius: 20px`), gradient fill `linear-gradient(135deg, var(--accent), #00b8a9)`, `box-shadow: 0 2px 12px rgba(100,255,218,0.3)`, with hover scale transform `scale(1.03)` and `transition: all 0.15s ease`.
- **Section headers in panels**: Style them like macOS sidebar group labels — `font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); padding: 4px 0 8px`.
- **Fleet cards** (in RightPanel): Each robot card gets `border-radius: 12px`, `background: rgba(255,255,255,0.04)`, `border: 1px solid var(--glass-border)`, a left-side colour stripe in `--accent-2` (rovers) or `--accent-3` (drones), and a gentle hover glow `box-shadow: 0 0 0 1px var(--accent)`.
- **EventFeed rows**: Alternating very subtle background stripe, `border-radius: 6px`, icons replaced with emoji or SF-symbol-inspired SVG icons. `tone-success` rows get `background: rgba(0,230,118,0.06)`. `tone-danger` get `background: rgba(255,82,82,0.06)`.
- **MiniMap**: Give it a `border-radius: 10px`, `box-shadow: 0 0 0 2px var(--glass-border), 0 4px 16px rgba(0,0,0,0.5)`.

---

### 5. 🎬 Camera & Atmosphere

**In `SceneRoot.tsx`:**

- Set the default camera to a proper **isometric-ish angle**: elevation 55°, azimuth 35°, matching the reference image's feel.
- Add **post-processing** (if using `@react-three/postprocessing` — add it to `package.json`):
  - Bloom effect: `luminanceThreshold: 0.7, intensity: 0.6` to make emissive lights glow.
  - Vignette: `offset: 0.5, darkness: 0.5` for cinematic edges.
  - (Optional) SMAA anti-aliasing.
- Set `scene.fog = new THREE.FogExp2('#1a1f2e', 0.018)` for atmospheric depth.
- Scene background: gradient canvas texture simulating a **night-ops sky** — deep navy `#070b14` at top, subtle horizon glow `#1a2744` at bottom.

---

### 6. 📊 Readability Improvements

- **Robot labels** (in `Robots.tsx`): Redesign the HTML label to look like a **Mac tooltip** — `background: rgba(0,0,0,0.75)`, `backdrop-filter: blur(8px)`, `border: 1px solid rgba(255,255,255,0.15)`, `border-radius: 8px`, `padding: 3px 8px`, small arrow pointer below. Show: icon + name + battery bar inline.
- **Battery bar**: Replace the text battery value with a slim horizontal bar (6px tall, `border-radius: 3px`) using CSS gradient `#00e676` → `#ffca28` → `#ff5252` via `width: ${pct}%`.
- **Survivor beacons**: Replace current column with a pulsing **SOS beacon**: a vertical light beam (`THREE.CylinderGeometry`, emissive `#7dffb2`, thin radius 0.05, height 4), topped with a spinning star-of-life cross (two flat boxes).
- **Coverage fog**: Add a subtle **scanline pattern** to the fog overlay (CSS repeating-linear-gradient of very faint lines) for a "sensor mode" feel.

---

## Implementation Order

Please implement in this order so each step is testable:

1. `app.css` — full colour system and glass panel redesign
2. `common.ts` — add `COLORS` warm additions and a new `makeIsoTileTexture()` function
3. `World.tsx` — floor tile texture, wall recolour, greenery props, sun light
4. `SceneRoot.tsx` — camera angle, fog, background, bloom post-processing
5. `Robots.tsx` — rover and drone mesh redesign, hover, scan sweep, labels
6. `Network.tsx` — energy arc, discovery flash, reception burst, link beautification
7. `Overlays.tsx` — survivor beacon redesign, scanline fog
8. `EventFeed.tsx` — row highlighting for peer communication events

---

## Constraints

- **DO NOT modify anything under `src/simulation/`** — only visual/scene/UI files.
- Keep the existing `QualityProfile` system — add new visual effects only at `medium` and `high`.
- Keep all existing TypeScript types and exports working.
- The Vite dev server runs at `http://localhost:5173`. The app uses React 18, Three.js 0.169, @react-three/fiber 8.17, @react-three/drei 9.114, Zustand 4.5.
- `vitest` tests must still pass (`npm run test`) — they run headlessly in Node and don't touch scene files.

---

## What to Output

For each file changed, output the **complete new file contents** (not a diff). Start with `app.css`, then proceed through the list above. Add code comments explaining the key visual techniques.
