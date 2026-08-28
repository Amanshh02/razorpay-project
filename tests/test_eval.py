"""Tests for the eval harness's scoring maths.

A harness that scores itself wrong is worse than no harness, so
``score_type`` is exercised against hand-built label dictionaries where
the right answer is obvious by inspection. These use synthetic labels,
not the answer key.
"""

import pytest

from evals.run_eval import SCORED_TYPES, UNSCORED_TYPES, score_type


def test_perfect_agreement():
    truth = {"a": "chargeback", "b": "chargeback"}
    predicted = {"a": "chargeback", "b": "chargeback"}
    row = score_type(predicted, truth, "chargeback")
    assert (row["tp"], row["fp"], row["fn"]) == (2, 0, 0)
    assert row["precision"] == 1.0
    assert row["recall"] == 1.0
    assert row["f1"] == 1.0


def test_a_miss_costs_recall_not_precision():
    truth = {"a": "chargeback", "b": "chargeback"}
    predicted = {"a": "chargeback"}
    row = score_type(predicted, truth, "chargeback")
    assert (row["tp"], row["fp"], row["fn"]) == (1, 0, 1)
    assert row["precision"] == 1.0
    assert row["recall"] == 0.5


def test_a_false_alarm_costs_precision_not_recall():
    truth = {"a": "chargeback"}
    predicted = {"a": "chargeback", "b": "chargeback"}
    row = score_type(predicted, truth, "chargeback")
    assert (row["tp"], row["fp"], row["fn"]) == (1, 1, 0)
    assert row["precision"] == 0.5
    assert row["recall"] == 1.0


def test_wrong_label_is_both_a_false_positive_and_a_false_negative():
    """Calling a shortfall a refund must hurt twice, not once."""
    truth = {"a": "settlement_shortfall"}
    predicted = {"a": "refund_not_reflected"}

    refunds = score_type(predicted, truth, "refund_not_reflected")
    assert (refunds["tp"], refunds["fp"], refunds["fn"]) == (0, 1, 0)

    shortfalls = score_type(predicted, truth, "settlement_shortfall")
    assert (shortfalls["tp"], shortfalls["fp"], shortfalls["fn"]) == (0, 0, 1)


def test_unscored_type_is_never_a_false_positive():
    """settlement_excess has no labels; predicting it must not be punished."""
    truth = {"a": "settlement_shortfall"}
    predicted = {"a": "settlement_shortfall", "b": "settlement_excess"}
    for anomaly_type in SCORED_TYPES:
        row = score_type(predicted, truth, anomaly_type)
        assert row["fp"] == 0, anomaly_type


def test_no_support_and_no_predictions_scores_zero_not_nan():
    row = score_type({}, {}, "chargeback")
    assert row["precision"] == 0.0
    assert row["recall"] == 0.0
    assert row["f1"] == 0.0


def test_f1_is_the_harmonic_mean():
    truth = {"a": "chargeback", "b": "chargeback", "c": "chargeback"}
    predicted = {"a": "chargeback", "d": "chargeback"}
    row = score_type(predicted, truth, "chargeback")
    assert row["precision"] == pytest.approx(0.5)
    assert row["recall"] == pytest.approx(1 / 3)
    assert row["f1"] == pytest.approx(2 * 0.5 * (1 / 3) / (0.5 + 1 / 3))


def test_scored_and_unscored_types_do_not_overlap():
    assert set(SCORED_TYPES) & set(UNSCORED_TYPES) == set()
