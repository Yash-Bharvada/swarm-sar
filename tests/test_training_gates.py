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
    decision = evaluate_gate(report(maximum_dominant_action_ratio=0.99, mean_cohort_recall=0.1), env_steps=0, definition=DEFINITION, recall_history=[0.1, 0.1, 0.1])
    assert decision["status"] == "pause"
    assert set(decision["pause_reasons"]) == {"policy_action_collapse", "recall_plateau"}


def test_nan_evaluation_cannot_pass_by_comparison_with_stage_floor():
    decision = evaluate_gate(report(mean_cohort_recall=float("nan")), env_steps=100, definition=DEFINITION, recall_history=[])
    assert decision["status"] == "abort"
    assert "non_finite_evaluation:mean_cohort_recall" in decision["abort_reasons"]


def test_frontier_rank_zero_dominance_is_allowed_when_rescue_is_good():
    decision = evaluate_gate(report(maximum_dominant_action_ratio=0.999), env_steps=0, definition=DEFINITION, recall_history=[0.6])
    assert decision["status"] == "continue"


def test_bc_regression_and_generalization_gap_pause():
    decision = evaluate_gate(report(train_development_gap=0.5), env_steps=0, definition=DEFINITION, recall_history=[], reference_recall=0.9)
    assert decision["status"] == "pause"
    assert decision["pause_reasons"] == ["regression_from_behavior_cloning"]
    assert decision["warning_reasons"] == ["train_development_generalization_gap"]


def test_generalization_gap_requires_multiple_evaluations():
    decision = evaluate_gate(report(train_development_gap=0.5), env_steps=0, definition=DEFINITION, recall_history=[], gap_history=[0.5, 0.5])
    assert decision["status"] == "pause"
    assert "persistent_train_development_generalization_gap" in decision["pause_reasons"]


def test_fixed_shadow_and_history_nonfinite_or_out_of_range_abort():
    for changes in ({"fixed_mean_recall": float("nan")}, {"shadow_mean_recall": 1.1}, {"train_development_gap": float("inf")}):
        assert evaluate_gate(report(**changes), env_steps=0, definition=DEFINITION, recall_history=[])["status"] == "abort"
    assert evaluate_gate(report(), env_steps=0, definition=DEFINITION, recall_history=[float("nan")])["status"] == "abort"


def test_absent_policy_metric_is_distinguished_from_nan():
    row = {"env_steps": 10, "episode_return_mean": 1, "episode_length_mean": 2, "rover_policy_loss": 0, "drone_policy_loss": None}
    assert iteration_health(row) == []


def test_fixed_seed_improvement_without_transfer_pauses_only_when_persistent():
    values = report(fixed_mean_recall=0.8, shadow_mean_recall=0.3)
    first = evaluate_gate(values, env_steps=0, definition=DEFINITION, recall_history=[], shadow_gap_history=[0.5])
    assert first["status"] == "continue"
    assert "fixed_shadow_generalization_gap" in first["warning_reasons"]
    repeated = evaluate_gate(values, env_steps=0, definition=DEFINITION, recall_history=[], shadow_gap_history=[0.5, 0.5])
    assert repeated["status"] == "pause"
    assert "persistent_fixed_shadow_generalization_gap" in repeated["pause_reasons"]
