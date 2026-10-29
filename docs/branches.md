# Branch scope

The full project is maintained on `main` and `rashiyaom`. Publish both at the
same reviewed commit. Other branches are focused workspaces or handoff packages;
they do not receive every full-project change automatically.

| Branch | Keep in its working tree | Dependencies and updates |
| :--- | :--- | :--- |
| `main`, `rashiyaom` | Complete project and all relevant evidence | Integrated runnable project; synchronized delivery |
| `frontend` | React/Vite app, its browser engine, frontend tests/QA, browser captures and UI notes | Browser engine is required by the UI; Python PPO backend runs from a full-project checkout |
| `simulator_web` | Browser engine, runnable React visualization, browser tests and controller/contract notes | UI is the browser simulator's executable shell; Python/ROS/GPU data is excluded |
| `gpu-training` | Original audited Python runtime, configurations, expert data, safeguards, tests and operator prompt | Keep the audited source layout and hashes; documentation can change without altering source identity |
| `gpu-754k-handoff` | Selected checkpoint archive, checksum, development review, source identity and recorded 2D demo | Artifact delivery only; run inference from the full-project branches |

Focused branches may share dependencies. `frontend` and `simulator_web` both
need the browser engine and visual shell, but their documentation emphasizes
UI work and simulation/controller work respectively. Neither carries Python
training data, model archives or ROS packages.

Branch cleanup is recorded in new commits. Prior commits and the immutable
`gpu-training-v1` tag retain historical source and evidence. The separate
`pankti` remote belongs to the upstream collaborator and is not modified by
this publication.

To move a focused change back to the full project, review the patch against its
current source layout, run the affected checks, and commit the integration on
`main`/`rashiyaom`. Do not merge an artifact-only pruning commit into the full
project. Historical PR branches deleted on the server are not recreated.
