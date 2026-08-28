"""Tests for the detectors.

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
    PAYMENT_NOT_RECEIVED,
    REFUND_NOT_REFLECTED,
    SETTLEMENT_EXCESS,
    SETTLEMENT_SHORTFALL,
    detect_chargebacks,
    detect_missing_payments,
    detect_overpayments,
    detect_refunds,
    detect_settlement_shortfalls,
)
from src.loaders import load_fees, load_orders, load_payments, load_settlements
from src.matching import match_ledgers

FIXTURES = Path(__file__).parent / "fixtures"
DETECTOR_FIXTURES = FIXTURES / "detectors"

#: Detectors reading the reconciled frame. These must partition it.
RECONCILED_DETECTORS = [
    detect_refunds,
    detect_chargebacks,
    detect_settlement_shortfalls,
    detect_overpayments,
]


def _load(directory):
    return (
        load_orders(directory / "orders.csv"),
        load_payments(directory / "payments.csv"),
        load_fees(directory / "fees.csv"),
        load_settlements(directory / "settlements.csv"),
    )


@pytest.fixture
def bench_match():
    """The hand-built detector fixtures, matched."""
    return match_ledgers(*_load(DETECTOR_FIXTURES))


@pytest.fixture
def bench(bench_match):
    return bench_match.reconciled


@pytest.fixture
def bench_orders():
    return load_orders(DETECTOR_FIXTURES / "orders.csv")


@pytest.fixture
def real_match():
    """The 130-order fixture set, matched."""
    return match_ledgers(*_load(FIXTURES))


@pytest.fixture
def real(real_match):
    return real_match.reconciled


@pytest.fixture
def real_orders():
    return load_orders(FIXTURES / "orders.csv")


# --------------------------------------------------------------------
# Contract: every detector returns the same schema
# --------------------------------------------------------------------

@pytest.mark.parametrize("detector", RECONCILED_DETECTORS)
def test_finding_schema(detector, bench):
    findings = detector(bench)
    assert list(findings.columns) == list(FINDING_COLUMNS)
    for column in ("expected_amount_paise", "actual_amount_paise", "delta_paise"):
        assert findings[column].dtype == "int64", column


def test_missing_payment_finding_schema(bench_match, bench_orders):
    findings = detect_missing_payments(bench_match.unreconciled, bench_orders)
    assert list(findings.columns) == list(FINDING_COLUMNS)
    for column in ("expected_amount_paise", "actual_amount_paise", "delta_paise"):
        assert findings[column].dtype == "int64", column


@pytest.mark.parametrize("detector", RECONCILED_DETECTORS)
def test_every_finding_carries_a_reason(detector, bench):
    assert detector(bench)["reason"].str.len().gt(20).all()


@pytest.mark.parametrize("detector", RECONCILED_DETECTORS)
def test_delta_is_actual_minus_expected(detector, bench):
    findings = detector(bench)
    computed = findings["actual_amount_paise"] - findings["expected_amount_paise"]
    assert (computed == findings["delta_paise"]).all()


# --------------------------------------------------------------------
# Refunds and chargebacks (stage 4, still passing)
# --------------------------------------------------------------------

def test_refund_positive_high_confidence(bench):
    row = detect_refunds(bench).set_index("order_id").loc["ord_refund_30"]
    assert row["anomaly_type"] == REFUND_NOT_REFLECTED
    assert row["confidence"] == HIGH
    assert row["delta_paise"] == -708000
    assert row["expected_amount_paise"] == 2304304
    assert row["actual_amount_paise"] == 1596304


def test_refund_positive_medium_confidence_in_grey_zone(bench):
    row = detect_refunds(bench).set_index("order_id").loc["ord_refund_22"]
    assert row["confidence"] == MEDIUM
    assert row["delta_paise"] == -371700
    assert "grey zone" in row["reason"]


def test_refund_negative_fixtures(bench):
    flagged = set(detect_refunds(bench)["order_id"])
    for order_id in (
        "ord_clean_01",
        "ord_tolerance_edge",
        "ord_small_gap",
        "ord_chargeback_01",
        "ord_shortfall_19",
        "ord_overpaid",
    ):
        assert order_id not in flagged


def test_chargeback_positive(bench):
    row = detect_chargebacks(bench).set_index("order_id").loc["ord_chargeback_01"]
    assert row["anomaly_type"] == CHARGEBACK
    assert row["confidence"] == HIGH
    assert row["delta_paise"] == -994000
    assert row["actual_amount_paise"] == -72278
    assert "chargeback fee" in row["reason"]


def test_chargeback_negative_fixtures(bench):
    assert set(detect_chargebacks(bench)["order_id"]) == {"ord_chargeback_01"}


# --------------------------------------------------------------------
# Settlement shortfall
# --------------------------------------------------------------------

def test_shortfall_positive_medium_confidence(bench):
    row = detect_settlement_shortfalls(bench).set_index("order_id").loc["ord_small_gap"]
    assert row["anomaly_type"] == SETTLEMENT_SHORTFALL
    assert row["confidence"] == MEDIUM
    assert row["delta_paise"] == -17700


def test_shortfall_near_threshold_is_low_confidence(bench):
    """19% is just under the 20% refund threshold, so the call is provisional."""
    row = (
        detect_settlement_shortfalls(bench).set_index("order_id").loc["ord_shortfall_19"]
    )
    assert row["confidence"] == LOW
    assert row["delta_paise"] == -269040
    assert "just under the refund threshold" in row["reason"]


def test_shortfall_negative_fixtures(bench):
    flagged = set(detect_settlement_shortfalls(bench)["order_id"])
    for order_id in (
        "ord_clean_01",
        "ord_tolerance_edge",
        "ord_refund_30",
        "ord_refund_22",
        "ord_chargeback_01",
        "ord_overpaid",
    ):
        assert order_id not in flagged


def test_shortfall_never_high_confidence(bench, real):
    """A shortfall is what is left when the explanations run out."""
    for frame in (bench, real):
        assert HIGH not in set(detect_settlement_shortfalls(frame)["confidence"])


# --------------------------------------------------------------------
# Overpayment
# --------------------------------------------------------------------

def test_overpayment_positive(bench):
    row = detect_overpayments(bench).set_index("order_id").loc["ord_overpaid"]
    assert row["anomaly_type"] == SETTLEMENT_EXCESS
    assert row["confidence"] == LOW
    assert row["delta_paise"] == 25000
    assert row["expected_amount_paise"] == 691291
    assert row["actual_amount_paise"] == 716291


def test_overpayment_negative_fixtures(bench):
    assert set(detect_overpayments(bench)["order_id"]) == {"ord_overpaid"}


def test_no_overpayment_in_the_real_fixture_set(real):
    """Documented as empty; if this ever fails the eval needs revisiting."""
    assert detect_overpayments(real).empty


# --------------------------------------------------------------------
# Missing payment
# --------------------------------------------------------------------

def test_missing_payment_positive(bench_match, bench_orders):
    findings = detect_missing_payments(bench_match.unreconciled, bench_orders)
    row = findings.set_index("order_id").loc["ord_missing_payment"]
    assert row["anomaly_type"] == PAYMENT_NOT_RECEIVED
    assert row["confidence"] == HIGH
    assert row["expected_amount_paise"] == 1062000
    assert row["actual_amount_paise"] == 0
    assert row["delta_paise"] == -1062000


def test_missing_payment_imputes_no_fee(bench_match, bench_orders):
    """Expected recovery is the full gross, per docs/data-model.md."""
    findings = detect_missing_payments(bench_match.unreconciled, bench_orders)
    gross = int(
        bench_orders.set_index("order_id").loc["ord_missing_payment", "gross_amount_paise"]
    )
    expected = int(findings.set_index("order_id").loc["ord_missing_payment", "expected_amount_paise"])
    assert expected == gross
    # A 2% + 18% fee would have been deducted here; it must not be.
    assert expected != gross - round(gross * 0.02 * 1.18)


def test_missing_payments_on_the_real_set(real_match, real_orders):
    findings = detect_missing_payments(real_match.unreconciled, real_orders)
    assert sorted(findings["order_id"]) == ["ord_00006", "ord_00065", "ord_00067"]

    gross = real_orders.set_index("order_id")["gross_amount_paise"]
    for row in findings.itertuples():
        assert row.expected_amount_paise == int(gross.loc[row.order_id])
        assert row.actual_amount_paise == 0


def test_missing_payment_never_appears_in_reconciled(bench, bench_match, bench_orders):
    assert "ord_missing_payment" not in set(bench["order_id"])
    findings = detect_missing_payments(bench_match.unreconciled, bench_orders)
    assert "ord_missing_payment" in set(findings["order_id"])


# --------------------------------------------------------------------
# Partition: exactly one bucket per gap, nothing claimed twice
# --------------------------------------------------------------------

def test_no_order_is_both_refund_and_chargeback(bench, real):
    for frame in (bench, real):
        assert set(detect_refunds(frame)["order_id"]) & set(
            detect_chargebacks(frame)["order_id"]
        ) == set()


def test_shortfall_does_not_overlap_stage_four(bench, real):
    for frame in (bench, real):
        shortfalls = set(detect_settlement_shortfalls(frame)["order_id"])
        assert shortfalls & set(detect_refunds(frame)["order_id"]) == set()
        assert shortfalls & set(detect_chargebacks(frame)["order_id"]) == set()


def test_clean_orders_produce_zero_flags(real):
    """The 99 orders inside tolerance must not be flagged by anything."""
    expected = real["payment_amount_paise"] - real["total_deduction_paise"]
    delta = real["settlement_amount_paise"] - expected
    clean = set(real.loc[delta.abs() <= config.TOLERANCE_PAISE, "order_id"])
    assert len(clean) == 99

    flagged = set()
    for detector in RECONCILED_DETECTORS:
        flagged |= set(detector(real)["order_id"])
    assert clean & flagged == set()


@pytest.mark.parametrize("which", ["bench", "real"])
def test_detectors_partition_every_gap_beyond_tolerance(which, request):
    frame = request.getfixturevalue(which)
    expected = frame["payment_amount_paise"] - frame["total_deduction_paise"]
    delta = frame["settlement_amount_paise"] - expected
    off = set(frame.loc[delta.abs() > config.TOLERANCE_PAISE, "order_id"])

    buckets = [set(detector(frame)["order_id"]) for detector in RECONCILED_DETECTORS]
    assert set.union(*buckets) == off
    for left in range(len(buckets)):
        for right in range(left + 1, len(buckets)):
            assert buckets[left] & buckets[right] == set()


def test_every_reconciled_order_is_either_clean_or_flagged_once(real):
    buckets = [set(detector(real)["order_id"]) for detector in RECONCILED_DETECTORS]
    flagged = set.union(*buckets)
    assert len(flagged) == sum(len(bucket) for bucket in buckets)
    assert flagged <= set(real["order_id"])


# --------------------------------------------------------------------
# Tolerance is honoured, never ==
# --------------------------------------------------------------------

def test_tolerance_edge_produces_no_flag_at_all(bench):
    for detector in RECONCILED_DETECTORS:
        assert "ord_tolerance_edge" not in set(detector(bench)["order_id"])


def test_gap_just_inside_tolerance_is_ignored(bench):
    frame = bench.copy()
    target = frame["order_id"] == "ord_clean_01"
    frame.loc[target, "settlement_amount_paise"] -= config.TOLERANCE_PAISE
    for detector in RECONCILED_DETECTORS:
        assert "ord_clean_01" not in set(detector(frame)["order_id"])


def test_gap_just_outside_tolerance_is_flagged(bench):
    frame = bench.copy()
    target = frame["order_id"] == "ord_clean_01"
    frame.loc[target, "settlement_amount_paise"] -= config.TOLERANCE_PAISE + 1
    assert "ord_clean_01" in set(detect_settlement_shortfalls(frame)["order_id"])


def test_overpayment_just_inside_tolerance_is_ignored(bench):
    frame = bench.copy()
    target = frame["order_id"] == "ord_clean_01"
    frame.loc[target, "settlement_amount_paise"] += config.TOLERANCE_PAISE
    assert "ord_clean_01" not in set(detect_overpayments(frame)["order_id"])


def test_overpayment_just_outside_tolerance_is_flagged(bench):
    frame = bench.copy()
    target = frame["order_id"] == "ord_clean_01"
    frame.loc[target, "settlement_amount_paise"] += config.TOLERANCE_PAISE + 1
    assert "ord_clean_01" in set(detect_overpayments(frame)["order_id"])


def test_empty_input_returns_empty_findings(bench, bench_match, bench_orders):
    empty = bench.iloc[0:0]
    for detector in RECONCILED_DETECTORS:
        findings = detector(empty)
        assert findings.empty
        assert list(findings.columns) == list(FINDING_COLUMNS)

    findings = detect_missing_payments(bench_match.unreconciled.iloc[0:0], bench_orders)
    assert findings.empty
    assert list(findings.columns) == list(FINDING_COLUMNS)
