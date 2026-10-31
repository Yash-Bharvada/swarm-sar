# Workspace launcher and extended fieldbook — 31 October 2026

The root `npm run swarm` command starts or reuses the frontend on 5173, the
verified PPO service on 8765 and the English fieldbook server on 8088. It checks
prerequisites and occupied ports, waits for readiness, prefixes service logs and
shuts down its own child processes on Ctrl+C. ROS/Gazebo remain native Linux
services and are not emulated by this command.

A cold-start integration check started all three services from stopped state,
verified HTTP health and sent SIGINT. All owned ports closed and the launcher
exited zero. Existing-service reuse and `--check` also passed. Evidence:
`artifacts/workspace_launcher/`. The services were then started again through
`npm run swarm`.

The README and gallery now include current browser application photographs,
Python-generated PPO setup preview and actual browser-map/peer telemetry.
`docs/media/updates/capture-manifest.json` records origins and hashes. Original
Gazebo/RViz images retain their original host-session provenance. No new live
Linux SLAM run is claimed.

The fieldbook is extended to 91 reader pages, 20 chapters, 15,320 words and
115.8 minutes of recorded English narration. It includes 17 new pages about
rover SLAM, transforms, radio-mediated map/intent sharing, the observatory,
large-map ablations, frozen baseline findings, startup and setup preview.
Original page IDs are retained. Its source atlas contains 693 project/evidence
files and excludes generated fieldbook files to prevent recursive duplication.
The complete M4B has 91 chapter markers. The printable illustrated PDF has
92 physical pages.

Validation:

- Full Python suite: **200 passed**, two existing deprecation warnings.
- Frontend suite: **148 passed**; production TypeScript/Vite build passed.
- Fieldbook: **215 checks passed**, including all desktop/mobile page bounds,
  narration, source references, current photographs, interactions and PDF.
- Frozen development benchmark lock: verified without executing simulations.
- Refreshed SLAM handoff archive: baseline reconstruction and payload hashes passed.

The fieldbook records reviewed source `d554464752fc9d5f3aa114d55c46fb7b300f49a7`.
Its new source edition is served at https://swarmsar.vercel.app. Local book QA is
recorded in `guide-site/qa/verification.json`; public deployment verification is
recorded separately under `artifacts/audiobook_vercel/`.
