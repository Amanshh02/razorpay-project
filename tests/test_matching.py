"""Tests for the matching engine.

Scenarios are derived in memory from the real fixtures in
tests/fixtures/ rather than added as new CSVs, so the labelled eval
fixture set stays exactly as it is. Each helper below states plainly
what it breaks.
"""

from pathlib import Path

import pandas as pd
import pytest

from src.loaders import load_fees, load_orders, load_payments, load_settlements
from src.matching import (
    RECONCILED_COLUMNS,
    UNRECONCILED_COLUMNS,
    RowConservationError,
    match_ledgers,
)
from src.matching import engine

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def ledgers():
    """The four fixture ledgers, loaded and untouched."""
    return (
        load_orders(FIXTURES / "orders.csv"),
        load_payments(FIXTURES / "payments.csv"),
        load_fees(FIXTURES / "fees.csv"),
        load_settlements(FIXTURES / "settlements.csv"),
    )


def assert_conservation(result, orders, payments, fees, settlements):
    """Every input row is either consumed by a match or bucketed."""
    matched = len(result.reconciled)
    for name, frame in [
        ("orders", orders),
        ("payments", payments),
        ("fees", fees),
        ("settlements", settlements),
    ]:
        bucketed = int((result.unreconciled["source_ledger"] == name).sum())
        assert len(frame) == matched + bucketed, name


# --------------------------------------------------------------------
# Clean match
# --------------------------------------------------------------------

def test_clean_match_on_the_fixtures(ledgers):
    orders, payments, fees, settlements = ledgers
    result = match_ledgers(orders, payments, fees, settlements)

    assert len(result.reconciled) == 127
    assert len(result.unreconciled) == 3
    assert_conservation(result, orders, payments, fees, settlements)


def test_reconciled_schema(ledgers):
    result = match_ledgers(*ledgers)
    assert list(result.reconciled.columns) == list(RECONCILED_COLUMNS)
    assert list(result.unreconciled.columns) == list(UNRECONCILED_COLUMNS)


def test_reconciled_row_carries_all_four_ledgers(ledgers):
    """One known order, checked field by field back to each source file."""
    result = match_ledgers(*ledgers)
    row = result.reconciled.set_index("order_id").loc["ord_00001"]

    assert row["gross_amount_paise"] == 2311396          # orders.csv
    assert row["payment_amount_paise"] == 2311396        # payments.csv
    assert row["payment_method"] == "card"
    assert row["fee_paise"] == 46228                     # fees.csv
    assert row["gst_on_fee_paise"] == 8321
    assert row["total_deduction_paise"] == 54549
    assert row["settlement_id"] == "setl_0001_00001"     # settlements.csv
    assert row["settlement_amount_paise"] == 2186389
    assert row["utr"] == "HDFC3226797778"


def test_every_order_appears_exactly_once(ledgers):
    orders, payments, fees, settlements = ledgers
    result = match_ledgers(orders, payments, fees, settlements)

    from_orders = result.unreconciled[result.unreconciled["source_ledger"] == "orders"]
    seen = list(result.reconciled["order_id"]) + list(from_orders["order_id"])
    assert sorted(seen) == sorted(orders["order_id"])
    assert len(seen) == len(set(seen))


# --------------------------------------------------------------------
# Missing payment
# --------------------------------------------------------------------

def test_missing_payment_is_bucketed_with_a_reason(ledgers):
    orders, payments, fees, settlements = ledgers
    result = match_ledgers(orders, payments, fees, settlements)

    missing = result.unreconciled[result.unreconciled["reason"] == engine.MISSING_PAYMENT]
    assert sorted(missing["order_id"]) == ["ord_00006", "ord_00065", "ord_00067"]
    assert missing["payment_id"].tolist() == ["pay_00006", "pay_00065", "pay_00067"]
    for detail in missing["detail"]:
        assert "payments.csv" in detail
    assert not result.reconciled["order_id"].isin(missing["order_id"]).any()


def test_missing_fee_is_bucketed(ledgers):
    orders, payments, fees, settlements = ledgers
    fees = fees[fees["payment_id"] != "pay_00001"]
    result = match_ledgers(orders, payments, fees, settlements)

    row = result.unreconciled[
        (result.unreconciled["source_ledger"] == "orders")
        & (result.unreconciled["order_id"] == "ord_00001")
    ]
    assert row["reason"].tolist() == [engine.MISSING_FEE]

    # The payment and settlement for that order are now unconsumed too,
    # and must be reported rather than quietly discarded.
    for ledger in ("payments", "settlements"):
        other = result.unreconciled[
            (result.unreconciled["source_ledger"] == ledger)
            & (result.unreconciled["payment_id"] == "pay_00001")
        ]
        assert other["reason"].tolist() == [engine.ORDER_UNRECONCILED]

    assert_conservation(result, orders, payments, fees, settlements)


def test_missing_settlement_is_bucketed(ledgers):
    orders, payments, fees, settlements = ledgers
    settlements = settlements[settlements["payment_id"] != "pay_00001"]
    result = match_ledgers(orders, payments, fees, settlements)

    row = result.unreconciled[result.unreconciled["order_id"] == "ord_00001"]
    assert engine.MISSING_SETTLEMENT in row["reason"].tolist()
    assert_conservation(result, orders, payments, fees, settlements)


# --------------------------------------------------------------------
# Duplicate payment
# --------------------------------------------------------------------

def test_duplicate_payment_is_not_silently_picked(ledgers):
    """Two rows share a payment_id, so the join is ambiguous and refused."""
    orders, payments, fees, settlements = ledgers
    duplicated = pd.concat(
        [payments, payments[payments["payment_id"] == "pay_00001"]],
        ignore_index=True,
    )
    result = match_ledgers(orders, duplicated, fees, settlements)

    assert "ord_00001" not in set(result.reconciled["order_id"])
    order_row = result.unreconciled[
        (result.unreconciled["source_ledger"] == "orders")
        & (result.unreconciled["order_id"] == "ord_00001")
    ]
    assert order_row["reason"].tolist() == [engine.DUPLICATE_PAYMENT]

    # Both ambiguous payment rows are reported, not just one.
    payment_rows = result.unreconciled[
        (result.unreconciled["source_ledger"] == "payments")
        & (result.unreconciled["payment_id"] == "pay_00001")
    ]
    assert len(payment_rows) == 2
    assert set(payment_rows["reason"]) == {engine.DUPLICATE_KEY}

    assert_conservation(result, orders, duplicated, fees, settlements)


def test_duplicate_payment_leaves_its_fee_and_settlement_accounted_for(ledgers):
    orders, payments, fees, settlements = ledgers
    duplicated = pd.concat(
        [payments, payments[payments["payment_id"] == "pay_00001"]],
        ignore_index=True,
    )
    result = match_ledgers(orders, duplicated, fees, settlements)

    for ledger in ("fees", "settlements"):
        row = result.unreconciled[
            (result.unreconciled["source_ledger"] == ledger)
            & (result.unreconciled["payment_id"] == "pay_00001")
        ]
        assert row["reason"].tolist() == [engine.ORDER_UNRECONCILED]


# --------------------------------------------------------------------
# Orphan settlement
# --------------------------------------------------------------------

def test_orphan_settlement_is_bucketed(ledgers):
    """A payout no order can account for must surface, not vanish."""
    orders, payments, fees, settlements = ledgers
    orphan = settlements.iloc[[0]].copy()
    orphan["settlement_id"] = "setl_9999_99999"
    orphan["payment_id"] = "pay_99999"
    with_orphan = pd.concat([settlements, orphan], ignore_index=True)

    result = match_ledgers(orders, payments, fees, with_orphan)

    row = result.unreconciled[result.unreconciled["payment_id"] == "pay_99999"]
    assert row["source_ledger"].tolist() == ["settlements"]
    assert row["reason"].tolist() == [engine.ORPHAN]
    assert "not referenced by any order" in row["detail"].iloc[0]
    assert_conservation(result, orders, payments, fees, with_orphan)


def test_orphan_settlement_does_not_reduce_the_clean_matches(ledgers):
    orders, payments, fees, settlements = ledgers
    orphan = settlements.iloc[[0]].copy()
    orphan["settlement_id"] = "setl_9999_99999"
    orphan["payment_id"] = "pay_99999"
    with_orphan = pd.concat([settlements, orphan], ignore_index=True)

    assert len(match_ledgers(orders, payments, fees, with_orphan).reconciled) == 127


# --------------------------------------------------------------------
# Matching is by ID, never by date
# --------------------------------------------------------------------

def test_match_is_unaffected_by_settlement_dates(ledgers):
    """Reverse every settled_at; the ID chain must produce the same match."""
    orders, payments, fees, settlements = ledgers
    baseline = match_ledgers(orders, payments, fees, settlements)

    shuffled = settlements.copy()
    shuffled["settled_at"] = shuffled["settled_at"].to_numpy()[::-1]
    result = match_ledgers(orders, payments, fees, shuffled)

    assert list(result.reconciled["payment_id"]) == list(baseline.reconciled["payment_id"])
    assert list(result.reconciled["settlement_id"]) == list(
        baseline.reconciled["settlement_id"]
    )


# --------------------------------------------------------------------
# Cross-check and the invariant itself
# --------------------------------------------------------------------

def test_order_id_disagreement_is_not_joined_over(ledgers):
    orders, payments, fees, settlements = ledgers
    tampered = payments.copy()
    tampered.loc[tampered["payment_id"] == "pay_00001", "order_id"] = "ord_09999"

    result = match_ledgers(orders, tampered, fees, settlements)

    row = result.unreconciled[
        (result.unreconciled["source_ledger"] == "orders")
        & (result.unreconciled["order_id"] == "ord_00001")
    ]
    assert row["reason"].tolist() == [engine.ORDER_ID_MISMATCH]
    assert_conservation(result, orders, tampered, fees, settlements)


def test_row_conservation_error_is_raised_when_the_invariant_breaks(ledgers):
    """The guard fires rather than returning a lossy result."""
    orders, _, _, _ = ledgers
    reconciled = pd.DataFrame({"payment_id": []})
    empty = pd.DataFrame({"source_ledger": []})

    with pytest.raises(RowConservationError, match="dropped silently"):
        engine._assert_row_conservation(reconciled, empty, orders=orders)
