# Backend

The HTTP service runs CPU inference using the saved PPO rover and drone policies.
Install the Python package from the repository root with `python -m pip install -e .`.
Start the service there with `python -m backend.ppo_service` (default port 8765),
then start Vite with `npm --prefix frontend run dev`.

`ppo_service.py` owns mission sessions and the `/api/ppo` endpoints. The simulator
and shared policy code live in `simulation/src/swarm_sar/`. Shipped checkpoints
live in `models/`; extracted handoffs and runtime output go to `training/runs/`.
