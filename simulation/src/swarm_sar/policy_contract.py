"""Versioned policy observation and action contract."""

from __future__ import annotations

import hashlib
import json
from typing import Any


POLICY_OBSERVATION_VERSION = "gpu-v1"
ACTION_NAMES = (
    "frontier_0",
    "frontier_1",
    "frontier_2",
    "frontier_3",
    "frontier_4",
    "investigate",
    "hold",
)
MAX_PEER_SLOTS = 8
PEER_FEATURE_NAMES = (
    "valid",
    "is_rover",
    "is_drone",
    "relative_pose_x",
    "relative_pose_y",
    "pose_uncertainty",
    "goal_valid",
    "relative_goal_x",
    "relative_goal_y",
    "thermal_evidence",
    "acoustic_evidence",
)
ACTIVE_GOAL_FEATURE_NAMES = (
    "relative_x",
    "relative_y",
    "distance",
    "valid",
)
PREVIOUS_ACTION_SIZE = len(ACTION_NAMES)
PEER_FEATURE_WIDTH = len(PEER_FEATURE_NAMES)
BASE_ENCODED_OBSERVATION_SIZE = 129
ENCODED_OBSERVATION_SIZE = (
    BASE_ENCODED_OBSERVATION_SIZE
    + PREVIOUS_ACTION_SIZE
    + len(ACTIVE_GOAL_FEATURE_NAMES)
    + 1
    + MAX_PEER_SLOTS * PEER_FEATURE_WIDTH
)


def policy_contract() -> dict[str, Any]:
    payload = {
        "observation_version": POLICY_OBSERVATION_VERSION,
        "encoded_observation_size": ENCODED_OBSERVATION_SIZE,
        "actions": list(ACTION_NAMES),
        "new_fields": {
            "previous_action": [PREVIOUS_ACTION_SIZE],
            "active_goal": [len(ACTIVE_GOAL_FEATURE_NAMES)],
            "mission_progress": [1],
            "peer_features": [MAX_PEER_SLOTS, PEER_FEATURE_WIDTH],
        },
        "peer_feature_names": list(PEER_FEATURE_NAMES),
        "active_goal_feature_names": list(ACTIVE_GOAL_FEATURE_NAMES),
        "semantics": {
            "previous_action": "one-hot previous high-level policy action; all zero at reset",
            "active_goal": "goal relative to drifting odometry, normalized to map dimensions",
            "mission_progress": "elapsed environment steps divided by configured step limit",
            "peer_features": "latest delivered, TTL-valid peer advertisements sorted by sender ID",
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload
