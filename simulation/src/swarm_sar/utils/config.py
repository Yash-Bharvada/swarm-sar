"""YAML configuration helpers."""

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML mapping, rejecting empty or non-mapping files."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Configuration must be a mapping: {config_path}")
    return value
