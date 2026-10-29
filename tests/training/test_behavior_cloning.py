import numpy as np
import pytest
import torch

from swarm_sar.learning.behavior_cloning import (
    ExpertArrays,
    class_weights,
    expert_seed_split,
    trajectory_windows,
    initial_state_for_batch,
    with_burn_in,
    sequence_batch,
    clone_summary_passed,
)


def arrays_for_test():
    rows = 28
    return ExpertArrays(
        observations=np.zeros((rows, 229), dtype=np.float32),
        action_masks=np.ones((rows, 7), dtype=np.uint8),
        actions=np.tile(np.arange(7, dtype=np.int8), 4),
        policy_ids=np.repeat([0, 1], 14).astype(np.int8),
        episode_seeds=np.repeat([1, 2, 3, 4], 7).astype(np.int32),
        steps=np.tile(np.arange(7), 4).astype(np.int32),
        agent_indices=np.repeat([0, 0, 1, 1], 7).astype(np.int16),
    )


def test_expert_seed_split_is_trajectory_disjoint():
    manifest = {"episodes": [{"seed": seed} for seed in range(10)]}
    train, validation = expert_seed_split(manifest, 0.2)
    assert train == set(range(8))
    assert validation == {8, 9}
    assert not train.intersection(validation)


def test_trajectory_windows_never_cross_episode_or_agent():
    arrays = arrays_for_test()
    windows = trajectory_windows(
        arrays, policy_id=0, seeds={1, 2}, max_seq_len=4
    )
    assert [len(window) for window in windows] == [4, 3, 4, 3]
    for window in windows:
        assert len(set(arrays.episode_seeds[window])) == 1
        assert len(set(arrays.agent_indices[window])) == 1
        assert np.all(np.diff(arrays.steps[window]) == 1)


def test_class_weights_upweight_rare_actions_and_reject_missing_classes():
    actions = np.array([0] * 70 + [1] * 7 + [2] * 7 + [3] * 7 + [4] * 7 + [5] * 7 + [6])
    weights = class_weights(actions)
    assert weights[6] > weights[1] > weights[0]
    assert np.all(np.isfinite(weights))
    counts = np.bincount(actions, minlength=7)
    assert np.allclose(counts * weights, np.full(7, len(actions) / 7))
    with pytest.raises(ValueError, match="missing actions"):
        class_weights(np.zeros(10, dtype=int))


def test_recurrent_initial_state_is_batch_major():
    class Module:
        def is_stateful(self):
            return True

        def get_initial_state(self):
            return {"actor": {"h": torch.zeros(1, 8), "c": torch.zeros(1, 8)}}

    state = initial_state_for_batch(Module(), 5, torch.device("cpu"))
    assert state["actor"]["h"].shape == (5, 1, 8)


def test_burn_in_provides_prior_context_without_duplicate_loss():
    arrays = arrays_for_test()
    windows = trajectory_windows(arrays, policy_id=0, seeds={1, 2}, max_seq_len=4)
    contextual = with_burn_in(arrays, windows, burn_in=2)
    assert contextual[1].indices.tolist() == [2, 3, 4, 5, 6]
    assert contextual[1].loss_start == 2
    _, _, mask = sequence_batch(arrays, contextual, [1], max_seq_len=6, device=torch.device("cpu"))
    assert mask.tolist() == [[0, 0, 1, 1, 1, 0]]
    assert len(set(arrays.episode_seeds[contextual[2].indices])) == 1


def test_clone_quality_rejects_nan_missing_class_and_hidden_rare_action_failure():
    import copy
    validation = {
        "balanced_accuracy": 0.7, "first_valid_balanced_accuracy": 0.2,
        "per_action_recall": {str(action): 0.7 for action in range(7)},
        "per_action_total": {str(action): 10 for action in range(7)},
    }
    reports = {name: {"best_validation": copy.deepcopy(validation), "overfit_gap": 0.1} for name in ("rover_policy", "drone_policy")}
    def passed():
        return clone_summary_passed(reports, minimum_balanced_accuracy=0.4, maximum_overfit_gap=0.15)
    assert passed()
    reports["rover_policy"]["best_validation"]["per_action_recall"]["5"] = 0.0
    assert not passed()
    reports["rover_policy"]["best_validation"] = copy.deepcopy(validation)
    reports["rover_policy"]["best_validation"]["per_action_total"]["6"] = 0
    assert not passed()
    reports["rover_policy"]["best_validation"] = copy.deepcopy(validation)
    reports["rover_policy"]["overfit_gap"] = float("nan")
    assert not passed()
