"""Tests for the four ledger loaders, run against the real fixtures.

Row counts and sample values below come from tests/fixtures/ and are
recorded in docs/data-model.md. Nothing here is fabricated to make a
test pass.
"""

from pathlib import Path

import pandas as pd
import pytest

import config
from src.loaders import (
    MissingColumnError,
    load_fees,
    load_orders,
    load_payments,
    load_settlements,
)
from src.loaders import fees, orders, payments, settlements

FIXTURES = Path(__file__).parent / "fixtures"

# (loader, filename, module holding COLUMNS, expected row count)
LEDGERS = [
    (load_orders, "orders.csv", orders, 130),
    (load_payments, "payments.csv", payments, 127),
    (load_fees, "fees.csv", fees, 127),
    (load_settlements, "settlements.csv", settlements, 127),
]
LEDGER_IDS = ["orders", "payments", "fees", "settlements"]


# --------------------------------------------------------------------
# Shape and schema, per loader
# --------------------------------------------------------------------

@pytest.mark.parametrize("loader,filename,module,rows", LEDGERS, ids=LEDGER_IDS)
def test_loader_returns_documented_schema(loader, filename, module, rows):
    frame = loader(FIXTURES / filename)
    assert list(frame.columns) == list(module.COLUMNS)
    assert len(frame) == rows


@pytest.mark.parametrize("loader,filename,module,rows", LEDGERS, ids=LEDGER_IDS)
def test_amount_columns_are_int64(loader, filename, module, rows):
    frame = loader(FIXTURES / filename)
    for column in module.AMOUNT_COLUMNS:
        assert frame[column].dtype == "int64", column


@pytest.mark.parametrize("loader,filename,module,rows", LEDGERS, ids=LEDGER_IDS)
def test_date_columns_are_tz_aware_ist(loader, filename, module, rows):
    frame = loader(FIXTURES / filename)
    for column in getattr(module, "DATE_COLUMNS", ()):
        assert str(frame[column].dt.tz) == config.TIMEZONE, column


@pytest.mark.parametrize("loader,filename,module,rows", LEDGERS, ids=LEDGER_IDS)
def test_non_amount_non_date_columns_stay_strings(loader, filename, module, rows):
    """IDs and enums must never be coerced to a numeric type."""
    frame = loader(FIXTURES / filename)
    typed = set(module.AMOUNT_COLUMNS) | set(getattr(module, "DATE_COLUMNS", ()))
    for column in module.COLUMNS:
        if column in typed:
            continue
        assert frame[column].map(type).eq(str).all(), column


# --------------------------------------------------------------------
# Missing columns are a hard error, never a silent fill
# --------------------------------------------------------------------

@pytest.mark.parametrize("loader,filename,module,rows", LEDGERS, ids=LEDGER_IDS)
def test_missing_column_raises(loader, filename, module, rows, tmp_path):
    dropped = module.COLUMNS[0]
    source = pd.read_csv(FIXTURES / filename, dtype=str)
    mangled = tmp_path / filename
    source.drop(columns=[dropped]).to_csv(mangled, index=False)

    with pytest.raises(MissingColumnError) as excinfo:
        loader(mangled)

    message = str(excinfo.value)
    assert dropped in message
    assert "docs/data-model.md" in message


@pytest.mark.parametrize("loader,filename,module,rows", LEDGERS, ids=LEDGER_IDS)
def test_every_documented_column_is_required(loader, filename, module, rows, tmp_path):
    """Dropping any single column must fail, not just the first."""
    source = pd.read_csv(FIXTURES / filename, dtype=str)
    for column in module.COLUMNS:
        mangled = tmp_path / f"without_{column}_{filename}"
        source.drop(columns=[column]).to_csv(mangled, index=False)
        with pytest.raises(MissingColumnError):
            loader(mangled)


# --------------------------------------------------------------------
# Amounts are read, never rescaled
# --------------------------------------------------------------------

def test_orders_amounts_match_the_file_exactly():
    frame = load_orders(FIXTURES / "orders.csv").set_index("order_id")
    row = frame.loc["ord_00001"]
    assert row["net_amount_paise"] == 1958810
    assert row["gst_amount_paise"] == 352586
    assert row["gross_amount_paise"] == 2311396


def test_payments_amount_matches_the_file_exactly():
    frame = load_payments(FIXTURES / "payments.csv").set_index("payment_id")
    assert frame.loc["pay_00001", "amount_paise"] == 2311396


def test_fees_amounts_match_the_file_exactly():
    frame = load_fees(FIXTURES / "fees.csv").set_index("payment_id")
    row = frame.loc["pay_00001"]
    assert row["fee_paise"] == 46228
    assert row["gst_on_fee_paise"] == 8321
    assert row["total_deduction_paise"] == 54549


def test_settlements_amount_matches_the_file_exactly():
    frame = load_settlements(FIXTURES / "settlements.csv").set_index("payment_id")
    assert frame.loc["pay_00001", "amount_paise"] == 2186389


def test_negative_settlement_amounts_survive():
    """A chargeback can push a payout negative; int64 is signed."""
    frame = load_settlements(FIXTURES / "settlements.csv").set_index("payment_id")
    assert frame.loc["pay_00008", "amount_paise"] == -122433
    assert (frame["amount_paise"] < 0).sum() == 12


# --------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------

def test_order_date_parses_to_the_expected_instant():
    frame = load_orders(FIXTURES / "orders.csv").set_index("order_id")
    expected = pd.Timestamp("2026-02-01 16:08:00", tz=config.TIMEZONE)
    assert frame.loc["ord_00001", "order_date"] == expected


def test_settled_at_parses_to_the_expected_instant():
    frame = load_settlements(FIXTURES / "settlements.csv").set_index("payment_id")
    expected = pd.Timestamp("2026-02-03 11:30:00", tz=config.TIMEZONE)
    assert frame.loc["pay_00001", "settled_at"] == expected


def test_ist_offset_is_five_thirty():
    frame = load_orders(FIXTURES / "orders.csv")
    assert frame["order_date"].iloc[0].utcoffset() == pd.Timedelta(hours=5, minutes=30)


def test_unparseable_date_raises(tmp_path):
    source = pd.read_csv(FIXTURES / "orders.csv", dtype=str)
    source.loc[0, "order_date"] = "01/02/2026"
    mangled = tmp_path / "orders.csv"
    source.to_csv(mangled, index=False)

    with pytest.raises(ValueError, match="order_date"):
        load_orders(mangled)


# --------------------------------------------------------------------
# IDs stay strings
# --------------------------------------------------------------------

def test_ids_are_strings_not_numbers():
    frame = load_orders(FIXTURES / "orders.csv")
    assert frame["order_id"].iloc[0] == "ord_00001"
    assert frame["payment_id"].iloc[0] == "pay_00001"


def test_all_digit_ids_keep_leading_zeros(tmp_path):
    """A future export using bare numeric IDs must not become int/float."""
    source = pd.read_csv(FIXTURES / "orders.csv", dtype=str)
    source["order_id"] = "0012345"
    mangled = tmp_path / "orders.csv"
    source.to_csv(mangled, index=False)

    frame = load_orders(mangled)
    assert frame["order_id"].iloc[0] == "0012345"


# --------------------------------------------------------------------
# Extra columns
# --------------------------------------------------------------------

def test_extra_columns_are_dropped_not_carried(tmp_path):
    source = pd.read_csv(FIXTURES / "fees.csv", dtype=str)
    source["settlement_batch"] = "batch_01"
    mangled = tmp_path / "fees.csv"
    source.to_csv(mangled, index=False)

    frame = load_fees(mangled)
    assert list(frame.columns) == list(fees.COLUMNS)
