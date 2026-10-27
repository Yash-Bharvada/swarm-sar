"""Structured episode artifact export."""

import csv
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from swarm_sar.sim.engine import SwarmWorld


def _json_default(value: Any):
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Cannot JSON encode {type(value).__name__}")


def save_episode_artifacts(world: "SwarmWorld", output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "map": output / "map.json",
        "events": output / "events.json",
        "trajectories": output / "trajectories.csv",
        "metrics": output / "metrics.json",
    }
    map_payload = {
        "seed": world.seed,
        "width": int(world.grid.shape[1]),
        "height": int(world.grid.shape[0]),
        "grid": world.grid.tolist(),
        "survivors": world.victims,
        "agents": [robot.as_state() for robot in world.robots],
    }
    paths["map"].write_text(
        json.dumps(map_payload, indent=2, default=_json_default), encoding="utf-8"
    )
    paths["events"].write_text(
        json.dumps(world.events, indent=2, default=_json_default), encoding="utf-8"
    )
    fieldnames = list(world.trajectory[0]) if world.trajectory else []
    with paths["trajectories"].open("w", newline="", encoding="utf-8") as handle:
        if fieldnames:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(world.trajectory)
    paths["metrics"].write_text(
        json.dumps(world.metrics_snapshot(), indent=2, default=_json_default), encoding="utf-8"
    )
    return paths
