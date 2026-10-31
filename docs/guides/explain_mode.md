# Interactive Explain Mode

Run the existing frontend (`npm --prefix frontend run dev`) and choose **ⓘ Explain** in the top bar.
No Python service or ROS host is needed for the story.

Explain Mode also appears in both observatory workspaces:

- `/?mode=observatory&explain=1`: 12 scenes covering private 3D maps, robot inspection,
  routes/frontiers, peer networking, message filters/export, four GNN architecture stages,
  and visualization freeze.
- `/?mode=ros&explain=1`: 15 scenes adding bridge connection, rover SLAM versus drone
  simulator localization, peer-only map cells, and radio isolation/reconnection.

These tours operate the existing page tabs and layers, highlighting the relevant controls.
They restore the previous viewing settings on exit. They do not automatically launch a mission,
connect a ROS bridge, or send isolation commands. Offline ROS visitors can still follow every
scene and enlarge the original Gazebo/RViz captures. Live maps appear when a ROS host reports
data. The main story links directly into these workspace tours and explains Auto, Manual,
Mixed, and Python PPO control modes.

GNN copy highlights the implemented graph architecture, message animation, adjustable
attention, and experimental training work. Example weights remain identified as examples;
the active controller is the selected browser controller or saved recurrent PPO policy.

Ten chapters contain fourteen short scenes. Each begins with a simple story, connects it to
the technology, and highlights **What we built**. Visitors can move forward/back, select a
chapter, jump using the progress bar, pause the action, or enable 45-second auto navigation.
Optional **Read aloud** uses the browser's installed speech synthesis; voice availability
and quality depend on the browser. Text is always available.

The same Three.js canvas, world, animated rover and drone models, camera controls, routes,
private-map overlays, and real simulated packet effects support the story. Simple interactive
illustrations explain unknown-house mapping, rewards, cooperation, radio isolation, and
combining teammate clues. These games are labeled teaching illustrations.

The final scene lets visitors reveal **Sense → Map → Decide → Share → Search** in the world.
Arrow keys navigate scenes; Space pauses/resumes when no button or field has focus; Escape
returns to the mission. An enlarged screenshot consumes Escape before the story does.
The layout adapts to phones and respects reduced-motion preferences for the added visuals
and guided camera transitions.

## Preserving work

Explain Mode runs an independent, seeded browser mission. It keeps the original mission
engine, settings, authored geometry, survivor layout, encounter, and presentation state.
Returning restores the original mission and camera. The guided mission has unlimited energy
so reading slowly cannot exhaust the robots. Robot information explicitly labels the normal
energy settings separately.

A connected PPO session remains alive. Its bridge suspends requests while the sandbox is
visible and retains an already committed response until the original mission returns.
Finish map/survivor editing, or wait for a connecting PPO mission, before opening the story.
Browser Back navigation also restores the original mission before changing workspaces.

## Evidence and attribution

Original PNGs are imported from `docs/media`, with no image generation or retouching. Gazebo
and RViz scenes show actual Ubuntu-host captures from 29 October 2026 UTC. An interactive
slider compares five original recorded RViz map states. The proof gallery also includes
the browser private-map observatory and an actual Python-backed PPO mission. Every capture
can be enlarged; training configuration, evaluation, capture records, and the original
launch log can be downloaded.

The selected 753,664-step PPO checkpoint achieved 88.8% combined mean development-cohort
recall. Sixteen workers, batch size 16,384, learning rate 0.0001, clip 0.2, memory 256, and
the 400-step mission budget come from the retained training configuration. The gallery
explains what the metric measures and retains the difficult large-maze result in its details.
The browser heuristic, Python PPO service, and ROS physics workflow are distinct paths.
New SLAM source integration still awaits Linux runtime validation. The experimental GNN
candidate has not replaced the selected PPO baseline; the clue mixer is an illustration.

## Implementation and checks

- `frontend/src/explain/story.ts`: story content, chapter and scene navigation.
- `frontend/src/explain/ExplainMode.tsx`: presentation, narration, recorded scenes, system controls.
- `frontend/src/explain/ExplainScene.tsx`: existing-scene sensor highlight.
- `frontend/src/explain/session.ts`: independent sandbox and mission restoration.
- `frontend/src/explain/ConceptVisual.tsx`: interactive explanatory illustrations.
- `frontend/src/explain/EvidenceGallery.tsx`: original captures and supporting records.

Run `npm --prefix frontend test` and `npm --prefix frontend run build` for automated checks.
With Vite on port 5173, run `.venv/bin/python frontend/scripts/explain_qa.py` for Chrome
interaction checks and desktop/mobile screenshots under `artifacts/explain-mode/`.
Use `--ppo` for a separate focused check of automatic navigation and a Python response
arriving during the story; it uses the existing protocol fixture without a running backend.

Verified for this implementation: production build passed, 156 frontend tests passed,
10 desktop/mobile browser scenarios passed, and both focused auto/PPO checks passed.
The browser checks reported no page errors. Reports and six preview captures are in
`artifacts/explain-mode/`.
