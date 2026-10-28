from swarm_sar.learning.training_gates import evaluate_gate, iteration_health


DEFINITION = {
    "hard_abort": {"max_invalid_actions": 0, "max_collisions_per_evaluation": 10},
    "quality": {"max_dominant_action_ratio": 0.98, "plateau_evaluations": 3, "minimum_recall_improvement": 0.01},
    "stages": [{"name": "first", "env_steps": 100, "min_mean_recall": 0.4, "min_worst_recall": 0.2, "min_worst_coverage": 0.3}],
}


def report(**changes):
    summary = {"invalid_actions": 0, "collisions": 0, "maximum_dominant_action_ratio": 0.5, "mean_cohort_recall": 0.6, "minimum_cohort_recall": 0.4, "minimum_cohort_coverage": 0.5}
    summary.update(changes)
    return {"summary": summary}


def test_non_finite_iteration_is_hard_failure():
    row = {"env_steps": 1, "episode_return_mean": 1, "episode_length_mean": 2, "rover_policy_loss": float("nan"), "drone_policy_loss": 0}
    assert iteration_health(row) == ["non_finite:rover_policy_loss"]


def test_invalid_action_aborts_and_quality_failure_pauses():
    assert evaluate_gate(report(invalid_actions=1), env_steps=100, definition=DEFINITION, recall_history=[0.6])["status"] == "abort"
    decision = evaluate_gate(report(mean_cohort_recall=0.1), env_steps=100, definition=DEFINITION, recall_history=[0.1])
    assert decision["status"] == "pause"
    assert "stage_mean_recall" in decision["pause_reasons"]


def test_plateau_and_action_collapse_are_detected():
    decision = evaluate_gate(report(maximum_dominant_action_ratio=0.99), env_steps=0, definition=DEFINITION, recall_history=[0.5, 0.5, 0.5])
    assert decision["status"] == "pause"
    assert set(decision["pause_reasons"]) == {"policy_action_collapse", "recall_plateau"}
