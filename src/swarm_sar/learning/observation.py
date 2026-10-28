"""Stable policy-facing encoding that never includes simulator truth."""

from typing import Mapping

import numpy as np
from gymnasium import spaces

from swarm_sar.policy_contract import ENCODED_OBSERVATION_SIZE
from swarm_sar.sim.env import ACTION_COUNT


def encode_observation(observation: Mapping[str, np.ndarray]) -> np.ndarray:
    """Flatten and bound local fields for a shared feed-forward PPO policy."""
    local_map = np.asarray(observation["local_map"], dtype=np.float32)
    local_map = np.where(local_map < 0, -1.0, local_map / 2.0)
    values = np.concatenate(
        [
            local_map.reshape(-1),
            np.clip(observation["battery"], 0.0, 1.0),
            np.clip(observation["thermal"], 0.0, 1.0),
            np.clip(observation["acoustic"], 0.0, 1.0),
            np.clip(observation["prev_thermal"], 0.0, 1.0),
            np.clip(observation["prev_acoustic"], 0.0, 1.0),
            np.clip(np.asarray(observation["rel_pos"]) / 4.0, -1.0, 1.0),
            np.clip(np.asarray(observation["pose_uncertainty"]) / 4.0, 0.0, 1.0),
            np.clip(observation["collided"], 0.0, 1.0),
            np.clip(np.asarray(observation["frontier_features"]).reshape(-1), -1.0, 1.0),
            np.clip(observation["peer_summary"], -1.0, 1.0),
            np.clip(observation["previous_action"], 0.0, 1.0),
            np.clip(observation["active_goal"], -1.0, 1.0),
            np.clip(observation["mission_progress"], 0.0, 1.0),
            np.clip(np.asarray(observation["peer_features"]).reshape(-1), -1.0, 1.0),
        ]
    ).astype(np.float32)
    if values.shape != (ENCODED_OBSERVATION_SIZE,):
        raise ValueError(
            f"Expected {ENCODED_OBSERVATION_SIZE} policy features, got {values.shape}"
        )
    return values


def policy_observation_space() -> spaces.Dict:
    return spaces.Dict(
        {
            "action_mask": spaces.Box(
                0.0, 1.0, shape=(ACTION_COUNT,), dtype=np.float32
            ),
            "observations": spaces.Box(
                -1.0,
                1.0,
                shape=(ENCODED_OBSERVATION_SIZE,),
                dtype=np.float32,
            ),
        }
    )


def wrap_observation(observation: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    wrapped = {
        "action_mask": np.asarray(observation["action_mask"], dtype=np.float32),
        "observations": encode_observation(observation),
    }
    if not policy_observation_space().contains(wrapped):
        raise ValueError("Encoded policy observation is outside its declared space")
    return wrapped
