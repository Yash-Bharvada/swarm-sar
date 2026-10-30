"""Backward-compatible import; use :mod:`robot_types` in new code."""

from swarm_sar.robots.robot_types import get_robot_type, load_robot_types

__all__ = ["get_robot_type", "load_robot_types"]
