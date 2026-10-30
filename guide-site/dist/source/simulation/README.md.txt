# Simulation

- `src/swarm_sar/`: deterministic Python simulation, controllers, sensing,
  mapping, networking, visualization and shared learning interfaces.
- `scripts/`: viewers, manual control, baseline runs, audits and ROS probes.
- `ros2_ws/`: ROS 2 packages, Gazebo worlds, robot descriptions and launch files.

Run from the repository root after `python -m pip install -e .`:

```bash
python simulation/scripts/view_world.py
python simulation/scripts/play_manual.py
python simulation/scripts/run_frontier_baseline.py
```

Shared runtime settings are in `configs/`. Browser simulation code remains in
`frontend/src/simulation/`. See [the physics guide](../docs/guides/physics_demo.md)
for ROS setup and launch commands.
