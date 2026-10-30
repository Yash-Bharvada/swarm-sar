import pytest

from swarm_sar.validation.seeds import load_seed_splits, scheduled_training_seed
from swarm_sar.learning.training import training_config


def test_checked_in_seed_splits_are_disjoint_and_expected_sizes():
    splits = load_seed_splits()
    assert len(splits["train"]) == 10000
    assert len(splits["development"]) == 100
    assert len(splits["final"]) == 200
    assert not set(splits["train"]).intersection(splits["development"])
    assert not set(splits["development"]).intersection(splits["final"])


def test_parallel_worker_schedule_has_no_early_duplicates_and_wraps():
    values = [
        scheduled_training_seed(
            range(0, 12), worker_index=worker, runner_count=3, episode_index=episode
        )
        for episode in range(4)
        for worker in range(3)
    ]
    assert values == list(range(12))
    assert scheduled_training_seed(
        range(0, 12), worker_index=0, runner_count=3, episode_index=4
    ) == 0


@pytest.mark.parametrize(
    "worker, runners", [(-1, 2), (2, 2), (0, 0)]
)
def test_invalid_worker_schedule_is_rejected(worker, runners):
    with pytest.raises(ValueError):
        scheduled_training_seed(
            range(0, 10), worker_index=worker, runner_count=runners, episode_index=0
        )


def test_gpu_evaluation_ranges_stay_inside_development_split():
    splits = load_seed_splits()
    config = training_config("training/configs/training_gpu_a5000.yaml")
    evaluation = range(config["evaluation_seeds"][0], config["evaluation_seeds"][1] + 1)
    generalization = range(
        config["generalization_seeds"][0], config["generalization_seeds"][1] + 1
    )
    assert set(evaluation) <= set(splits["development"])
    assert set(generalization) <= set(splits["development"])
    assert not set(evaluation).intersection(generalization)
