# Tests

Tests are grouped by responsibility: `backend/`, `simulation/`, `training/`, and
`ros2/`. Run `python -m pytest -q` from the repository root. Frontend tests live
in `frontend/src/tests/` and run with `npm --prefix frontend test`.

ROS tests inspect package and model definitions; they do not launch Gazebo.
