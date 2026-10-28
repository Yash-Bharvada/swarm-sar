"""Sequence-aware, class-balanced behavior cloning for GPU-v1 policies."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import torch
import torch.nn.functional as functional
from ray.rllib.core.columns import Columns

from swarm_sar.learning.demonstrations import POLICY_IDS, validate_dataset
from swarm_sar.policy_contract import ENCODED_OBSERVATION_SIZE
from swarm_sar.sim.env import ACTION_COUNT


@dataclass
class ExpertArrays:
    observations: np.ndarray
    action_masks: np.ndarray
    actions: np.ndarray
    policy_ids: np.ndarray
    episode_seeds: np.ndarray
    steps: np.ndarray
    agent_indices: np.ndarray


def load_expert_arrays(path: str | Path) -> tuple[ExpertArrays, dict[str, Any]]:
    root = Path(path).resolve()
    manifest = validate_dataset(root)
    fields = (
        "observations",
        "action_masks",
        "actions",
        "policy_ids",
        "episode_seeds",
        "steps",
        "agent_indices",
    )
    parts: dict[str, list[np.ndarray]] = {field: [] for field in fields}
    for chunk in manifest["chunks"]:
        with np.load(root / chunk["path"]) as data:
            for field in fields:
                parts[field].append(data[field])
    arrays = ExpertArrays(
        **{field: np.concatenate(parts[field], axis=0) for field in fields}
    )
    if arrays.observations.shape != (
        int(manifest["rows"]),
        ENCODED_OBSERVATION_SIZE,
    ):
        raise ValueError("Expert arrays do not match the GPU-v1 contract")
    return arrays, manifest


def expert_seed_split(
    manifest: dict[str, Any], validation_fraction: float = 0.10
) -> tuple[set[int], set[int]]:
    if not 0.0 < validation_fraction < 0.5:
        raise ValueError("validation_fraction must be between 0 and 0.5")
    seeds = sorted({int(item["seed"]) for item in manifest["episodes"]})
    if len(seeds) < 2:
        raise ValueError("Behavior cloning requires at least two episode seeds")
    validation_count = max(1, int(round(len(seeds) * validation_fraction)))
    train = set(seeds[:-validation_count])
    validation = set(seeds[-validation_count:])
    if not train or train.intersection(validation):
        raise ValueError("Expert train/validation seed split is invalid")
    return train, validation


def trajectory_windows(
    arrays: ExpertArrays,
    *,
    policy_id: int,
    seeds: set[int],
    max_seq_len: int,
) -> list[np.ndarray]:
    if max_seq_len < 1:
        raise ValueError("max_seq_len must be positive")
    selected = np.flatnonzero(
        (arrays.policy_ids == int(policy_id))
        & np.isin(arrays.episode_seeds, np.fromiter(seeds, dtype=np.int32))
    )
    trajectories: dict[tuple[int, int], list[int]] = {}
    for index in selected:
        key = (int(arrays.episode_seeds[index]), int(arrays.agent_indices[index]))
        trajectories.setdefault(key, []).append(int(index))
    windows: list[np.ndarray] = []
    for key in sorted(trajectories):
        indices = np.asarray(trajectories[key], dtype=np.int64)
        order = np.argsort(arrays.steps[indices], kind="stable")
        indices = indices[order]
        steps = arrays.steps[indices]
        if len(steps) > 1 and np.any(np.diff(steps) != 1):
            raise ValueError(f"Non-contiguous expert trajectory: {key}")
        windows.extend(
            indices[start : start + max_seq_len]
            for start in range(0, len(indices), max_seq_len)
        )
    if not windows:
        raise ValueError(f"No expert sequences for policy {policy_id}")
    return windows


def class_weights(actions: np.ndarray) -> np.ndarray:
    counts = np.bincount(actions.astype(int), minlength=ACTION_COUNT).astype(np.float64)
    if np.any(counts == 0):
        raise ValueError(f"Expert split is missing actions: {np.flatnonzero(counts == 0)}")
    weights = np.sqrt(counts.sum() / (ACTION_COUNT * counts))
    weights /= weights.mean()
    return np.clip(weights, 0.25, 4.0).astype(np.float32)


def initial_state_for_batch(module, batch_size: int, device: torch.device):
    if not module.is_stateful():
        return None
    return {
        branch: {
            name: value.unsqueeze(0).expand(batch_size, -1, -1).contiguous().to(device)
            for name, value in values.items()
        }
        for branch, values in module.get_initial_state().items()
    }


def sequence_batch(
    arrays: ExpertArrays,
    windows: list[np.ndarray],
    selected: Iterable[int],
    *,
    max_seq_len: int,
    device: torch.device,
) -> tuple[dict, torch.Tensor, torch.Tensor]:
    chosen = [windows[int(index)] for index in selected]
    batch_size = len(chosen)
    observations = np.zeros(
        (batch_size, max_seq_len, ENCODED_OBSERVATION_SIZE), dtype=np.float32
    )
    action_masks = np.ones(
        (batch_size, max_seq_len, ACTION_COUNT), dtype=np.float32
    )
    actions = np.zeros((batch_size, max_seq_len), dtype=np.int64)
    valid = np.zeros((batch_size, max_seq_len), dtype=np.float32)
    for row, indices in enumerate(chosen):
        length = len(indices)
        observations[row, :length] = arrays.observations[indices]
        action_masks[row, :length] = arrays.action_masks[indices]
        actions[row, :length] = arrays.actions[indices]
        valid[row, :length] = 1.0
    batch = {
        Columns.OBS: {
            "observations": torch.as_tensor(observations, device=device),
            "action_mask": torch.as_tensor(action_masks, device=device),
        }
    }
    return (
        batch,
        torch.as_tensor(actions, device=device),
        torch.as_tensor(valid, device=device),
    )


def _empty_metrics() -> dict[str, Any]:
    return {
        "loss_sum": 0.0,
        "tokens": 0,
        "correct": 0,
        "per_action_total": np.zeros(ACTION_COUNT, dtype=np.int64),
        "per_action_correct": np.zeros(ACTION_COUNT, dtype=np.int64),
        "prediction_counts": np.zeros(ACTION_COUNT, dtype=np.int64),
    }


def _finish_metrics(values: dict[str, Any]) -> dict[str, Any]:
    totals = values["per_action_total"]
    correct = values["per_action_correct"]
    recalls = np.divide(correct, totals, out=np.zeros_like(correct, dtype=float), where=totals > 0)
    present = totals > 0
    return {
        "loss": values["loss_sum"] / max(1, values["tokens"]),
        "accuracy": values["correct"] / max(1, values["tokens"]),
        "balanced_accuracy": float(recalls[present].mean()) if np.any(present) else 0.0,
        "tokens": int(values["tokens"]),
        "per_action_recall": {str(index): float(recalls[index]) for index in range(ACTION_COUNT)},
        "per_action_total": {str(index): int(totals[index]) for index in range(ACTION_COUNT)},
        "prediction_counts": {
            str(index): int(values["prediction_counts"][index])
            for index in range(ACTION_COUNT)
        },
    }


def run_epoch(
    module,
    arrays: ExpertArrays,
    windows: list[np.ndarray],
    *,
    weights: torch.Tensor,
    batch_size: int,
    max_seq_len: int,
    rng: np.random.Generator,
    optimizer: torch.optim.Optimizer | None,
    max_batches: int | None = None,
) -> dict[str, Any]:
    training = optimizer is not None
    module.train(training)
    device = next(module.parameters()).device
    order = rng.permutation(len(windows)) if training else np.arange(len(windows))
    metrics = _empty_metrics()
    for batch_number, start in enumerate(range(0, len(order), batch_size)):
        if max_batches is not None and batch_number >= max_batches:
            break
        selected = order[start : start + batch_size]
        batch, actions, valid = sequence_batch(
            arrays,
            windows,
            selected,
            max_seq_len=max_seq_len,
            device=device,
        )
        state = initial_state_for_batch(module, len(selected), device)
        if state is not None:
            batch[Columns.STATE_IN] = state
        if training:
            optimizer.zero_grad(set_to_none=True)
        with torch.set_grad_enabled(training):
            output = module.forward_train(batch)
            logits = output[Columns.ACTION_DIST_INPUTS]
            losses = functional.cross_entropy(
                logits.reshape(-1, ACTION_COUNT),
                actions.reshape(-1),
                weight=weights,
                reduction="none",
            ).reshape_as(valid)
            loss = (losses * valid).sum() / valid.sum().clamp_min(1.0)
            if not torch.isfinite(loss):
                raise FloatingPointError("Non-finite behavior-cloning loss")
            if training:
                loss.backward()
                torch.nn.utils.clip_grad_norm_(module.parameters(), max_norm=5.0)
                optimizer.step()
        with torch.no_grad():
            predictions = torch.argmax(logits, dim=-1)
            active = valid.bool()
            active_actions = actions[active].detach().cpu().numpy()
            active_predictions = predictions[active].detach().cpu().numpy()
            tokens = int(active.sum().item())
            metrics["loss_sum"] += float((losses * valid).sum().item())
            metrics["tokens"] += tokens
            metrics["correct"] += int(np.sum(active_actions == active_predictions))
            metrics["per_action_total"] += np.bincount(
                active_actions, minlength=ACTION_COUNT
            )
            metrics["per_action_correct"] += np.bincount(
                active_actions[active_actions == active_predictions], minlength=ACTION_COUNT
            )
            metrics["prediction_counts"] += np.bincount(
                active_predictions, minlength=ACTION_COUNT
            )
    return _finish_metrics(metrics)


def train_policy_clone(
    module,
    arrays: ExpertArrays,
    *,
    policy_id: int,
    train_seeds: set[int],
    validation_seeds: set[int],
    epochs: int,
    batch_size: int,
    learning_rate: float,
    max_seq_len: int,
    seed: int,
    patience: int,
    max_batches: int | None = None,
) -> dict[str, Any]:
    train_windows = trajectory_windows(
        arrays,
        policy_id=policy_id,
        seeds=train_seeds,
        max_seq_len=max_seq_len,
    )
    validation_windows = trajectory_windows(
        arrays,
        policy_id=policy_id,
        seeds=validation_seeds,
        max_seq_len=max_seq_len,
    )
    train_actions = np.concatenate([arrays.actions[window] for window in train_windows])
    weight_values = class_weights(train_actions)
    device = next(module.parameters()).device
    weights = torch.as_tensor(weight_values, device=device)
    optimizer = torch.optim.Adam(module.parameters(), lr=float(learning_rate))
    rng = np.random.default_rng(seed + policy_id * 10_000)
    history = []
    best_score = -1.0
    best_epoch = 0
    best_state = None
    stale = 0
    for epoch in range(1, epochs + 1):
        train_metrics = run_epoch(
            module,
            arrays,
            train_windows,
            weights=weights,
            batch_size=batch_size,
            max_seq_len=max_seq_len,
            rng=rng,
            optimizer=optimizer,
            max_batches=max_batches,
        )
        validation_metrics = run_epoch(
            module,
            arrays,
            validation_windows,
            weights=weights,
            batch_size=batch_size,
            max_seq_len=max_seq_len,
            rng=rng,
            optimizer=None,
            max_batches=max_batches,
        )
        record = {
            "epoch": epoch,
            "train": train_metrics,
            "validation": validation_metrics,
        }
        history.append(record)
        score = float(validation_metrics["balanced_accuracy"])
        if score > best_score + 1e-6:
            best_score = score
            best_epoch = epoch
            best_state = {
                key: value.detach().cpu().clone()
                for key, value in module.state_dict().items()
            }
            stale = 0
        else:
            stale += 1
        if stale >= patience:
            break
    if best_state is None:
        raise RuntimeError("Behavior cloning did not produce a best state")
    module.load_state_dict(best_state)
    final_validation = run_epoch(
        module,
        arrays,
        validation_windows,
        weights=weights,
        batch_size=batch_size,
        max_seq_len=max_seq_len,
        rng=rng,
        optimizer=None,
        max_batches=max_batches,
    )
    return {
        "policy_id": int(policy_id),
        "train_sequences": len(train_windows),
        "validation_sequences": len(validation_windows),
        "class_weights": {
            str(index): float(weight_values[index]) for index in range(ACTION_COUNT)
        },
        "best_epoch": best_epoch,
        "best_validation": final_validation,
        "overfit_gap": float(
            history[best_epoch - 1]["train"]["balanced_accuracy"]
            - final_validation["balanced_accuracy"]
        ),
        "history": history,
    }


def clone_summary_passed(
    reports: dict[str, dict[str, Any]],
    *,
    minimum_balanced_accuracy: float,
    maximum_overfit_gap: float,
) -> bool:
    return all(
        report["best_validation"]["balanced_accuracy"]
        >= minimum_balanced_accuracy
        and report["overfit_gap"] <= maximum_overfit_gap
        for report in reports.values()
    )
