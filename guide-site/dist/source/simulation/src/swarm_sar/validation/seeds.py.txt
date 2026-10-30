"""Immutable, disjoint seed ranges for training and evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from swarm_sar.utils.config import load_config


def load_seed_splits(path: str | Path | None = None) -> dict[str, range]:
    root = Path(__file__).resolve().parents[4]
    selected = Path(path) if path is not None else root / "training/configs/seed_splits.yaml"
    if not selected.is_absolute():
        selected = root / selected
    payload: dict[str, Any] = load_config(selected)
    result: dict[str, range] = {}
    for name in ("train", "development", "final"):
        if name not in payload:
            raise ValueError(f"Missing seed split: {name}")
        start = int(payload[name]["start"])
        stop = int(payload[name]["stop"])
        if start < 0 or stop <= start:
            raise ValueError(f"Invalid seed split {name}: [{start}, {stop})")
        result[name] = range(start, stop)
    names = list(result)
    for index, name in enumerate(names):
        values = set(result[name])
        for other in names[index + 1 :]:
            if values.intersection(result[other]):
                raise ValueError(f"Seed splits overlap: {name} and {other}")
    return result


def scheduled_training_seed(
    seed_range: range,
    *,
    worker_index: int,
    runner_count: int,
    episode_index: int,
) -> int:
    if runner_count < 1:
        raise ValueError("runner_count must be positive")
    if not 0 <= worker_index < runner_count:
        raise ValueError(
            f"worker_index {worker_index} is outside runner_count {runner_count}"
        )
    offset = worker_index + episode_index * runner_count
    return seed_range.start + offset % len(seed_range)
