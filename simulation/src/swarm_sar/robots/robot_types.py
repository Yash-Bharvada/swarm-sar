"""Robot-type configuration loading."""

from pathlib import Path
from typing import Any

from swarm_sar.utils.config import load_config


def load_robot_types(path: str | Path) -> dict[str, dict[str, Any]]:
    values = load_config(path)
    for name, config in values.items():
        if not isinstance(config, dict):
            raise ValueError(f"Robot type {name!r} must be a mapping")
    return values


def get_robot_type(types: dict[str, dict[str, Any]], name: str = "rover") -> dict[str, Any]:
    try:
        return types[name]
    except KeyError as error:
        raise ValueError(f"Unknown robot type: {name}") from error
