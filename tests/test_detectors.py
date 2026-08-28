"""Tests for the stage 4 detectors.

Runs against the hand-built fixtures in tests/fixtures/detectors/, whose
expected outcomes are tabulated in that directory's README, and against
the real 130-order ledgers for the whole-set assertions. The eval answer
key is not read here; that is evals/run_eval.py's job alone.
"""

from pathlib import Path

import pytest

import config
from src.detectors import (
    CHARGEBACK,
    FINDING_COLUMNS,
    HIGH,
    LOW,
    MEDIUM,
    REFUND_NOT_REFLECTED,
    UNEXPLAINED_NEGATIVE_DELTA,
    detect_chargebacks,
    detect_refunds,
    detect_unexplained_negative_deltas,
)
from src.loaders import load_fees, load_orders, load_payments, load_settlements
from src.matching import match_ledgers

FIXTURES = Path(__file__).parent / "fixtures"
DETECTOR_FIXTURES = FIXTURES / "detectors"

DETECTORS = [detect_refunds, detect_chargebacks, detect_unexplained_negative_deltas]


def _reconcile(directory):
    return match_ledgers(
        load_orders(directory / "orders.csv"),
        load_payments(directory / "payments.csv"),
        load_fees(directory / "fees.csv"),
        load_settlements(directory / "settlements.csv"),
    ).reconciled


@pytest.fixture
def bench():
    """The six hand-built detector fixtures, reconciled."""
    return _reconcile(DETECTOR_FIXTURES)


@pytest.fixture
def real():
    """The 130-order fixture set, reconciled."""
    return _reconcile(FIXTURES)


# --------------------------------------------------------------------
# Contract: every detector returns the same schema
# --------------------------------------------------------------------

@pytest.mark.parametrize("detector", DETECTORS)
def test_finding_schema(detector, bench):
    findings = detector(bench)
    assert list(findings.columns) == list(FINDING_COLUMNS)
    for column in ("expected_amount_paise", "actual_amount_paise", "delta_paise"):
        assert findings[column].dtype == "int64", column


@pytest.mark.parametrize("detector", DETECTORS)
def test_every_finding_carries_a_reason(detector, bench):
    findings = detector(bench)
    assert findings["reason"].str.len().gt(20).all()


@pytest.mark.parametrize("detector", DETECTORS)
def test_delta_is_actual_minus_expected(detector, bench):
    findings = detector(bench)
    computed = findings["actual_amount_paise"] - findings["expected_amount_paise"]
    assert (computed == findings["delta_paise"]).all()


# --------------------------------------------------------------------
# Positive and negative fixtures
# --------------------------------------------------------------------

def test_refund_positive_high_confidence(bench):
    findings = detect_refunds(bench).set_index("order_id")
    row = findings.loc["ord_refund_30"]
    assert row["anomaly_type"] == REFUND_NOT_REFLECTED
    assert row["confidence"] == HIGH
    assert row["delta_paise"] == -708000
    assert row["expected_amount_paise"] == 2304304
    assert row["actual_amount_paise"] == 1596304


def test_refund_positive_medium_confidence_in_grey_zone(bench):
    findings = detect_refunds(bench).set_index("order_id")
    row = findings.loc["ord_refund_22"]
    assert row["confidence"] == MEDIUM
    assert row["delta_paise"] == -371700
    assert "grey zone" in row["reason"]


def test_refund_negative_fixtures(bench):
    """Clean, within-tolerance and below-threshold orders are not refunds."""
    flagged = set(detect_refunds(bench)["order_id"])
    assert "ord_clean_01" not in flagged
    assert "ord_tolerance_edge" not in flagged
    assert "ord_small_gap" not in flagged
    assert "ord_chargeback_01" not in flagged


def test_chargeback_positive(bench):
    findings = detect_chargebacks(bench).set_index("order_id")
    row = findings.loc["ord_chargeback_01"]
    assert row["anomaly_type"] == CHARGEBACK
    assert row["confidence"] == HIGH
    assert row["delta_paise"] == -994000
    assert row["actual_amount_paise"] == -72278
    assert "chargeback fee" in row["reason"]


def test_chargeback_negative_fixtures(bench):
    flagged = set(detect_chargebacks(bench)["order_id"])
    assert flagged == {"ord_chargeback_01"}


def test_below_threshold_is_unexplained_not_refund(bench):
    findings = detect_unexplained_negative_deltas(bench).set_index("order_id")
    row = findings.loc["ord_small_gap"]
    assert row["anomaly_type"] == UNEXPLAINED_NEGATIVE_DELTA
    assert row["confidence"] == LOW
    assert row["delta_paise"] == -17700


def test_tolerance_edge_produces_no_flag_at_all(bench):
    """A 50-paise gap is inside the 100-paise tolerance."""
    for detector in DETECTORS:
        assert "ord_tolerance_edge" not in set(detector(bench)["order_id"])


# --------------------------------------------------------------------
# The two assertions requested for this stage
# --------------------------------------------------------------------

def test_no_order_is_both_refund_and_chargeback(bench, real):
    for frame in (bench, real):
        refunds = set(detect_refunds(frame)["order_id"])
        chargebacks = set(detect_chargebacks(frame)["order_id"])
        assert refunds & chargebacks == set()


def test_clean_orders_produce_zero_flags(real):
    """The 99 orders inside tolerance must not be flagged by anything."""
    expected = real["payment_amount_paise"] - real["total_deduction_paise"]
    delta = real["settlement_amount_paise"] - expected
    clean = set(real.loc[delta.abs() <= config.TOLERANCE_PAISE, "order_id"])
    assert len(clean) == 99

    flagged = set()
    for detector in DETECTORS:
        flagged |= set(detector(real)["order_id"])
    assert clean & flagged == set()


def test_the_three_detectors_partition_every_underpayment(real):
    """Nothing short beyond tolerance escapes all three buckets."""
    expected = real["payment_amount_paise"] - real["total_deduction_paise"]
    delta = real["settlement_amount_paise"] - expected
    short = set(real.loc[delta < -config.TOLERANCE_PAISE, "order_id"])

    buckets = [set(detector(real)["order_id"]) for detector in DETECTORS]
    assert set.union(*buckets) == short
    for left in range(len(buckets)):
        for right in range(left + 1, len(buckets)):
            assert buckets[left] & buckets[right] == set()


# --------------------------------------------------------------------
# Tolerance is honoured, never ==
# --------------------------------------------------------------------

def test_gap_just_inside_tolerance_is_ignored(bench):
    """Shrink a settlement by exactly the tolerance; still no flag."""
    frame = bench.copy()
    target = frame["order_id"] == "ord_clean_01"
    frame.loc[target, "settlement_amount_paise"] -= config.TOLERANCE_PAISE

    for detector in DETECTORS:
        assert "ord_clean_01" not in set(detector(frame)["order_id"])


def test_gap_just_outside_tolerance_is_flagged(bench):
    frame = bench.copy()
    target = frame["order_id"] == "ord_clean_01"
    frame.loc[target, "settlement_amount_paise"] -= config.TOLERANCE_PAISE + 1

    flagged = set(detect_unexplained_negative_deltas(frame)["order_id"])
    assert "ord_clean_01" in flagged


def test_empty_input_returns_empty_findings(bench):
    empty = bench.iloc[0:0]
    for detector in DETECTORS:
        findings = detector(empty)
        assert findings.empty
        assert list(findings.columns) == list(FINDING_COLUMNS)
