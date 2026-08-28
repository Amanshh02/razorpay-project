"""Loader for ``settlements.csv`` — the bank settlement ledger.

Returned schema, in this order:

=================== ================== ==============================
Column              dtype              Notes
=================== ================== ==============================
``settlement_id``   object (str)       Primary key
``payment_id``      object (str)       FK to payments.payment_id
``settled_at``      datetime64, IST    Parsed, tz-aware
``amount_paise``    int64              Paise, **signed**
``utr``             object (str)       Bank reference, *not unique*
``status``          object (str)       ``processed`` in the fixtures
=================== ================== ==============================

Two traps documented in docs/data-model.md section 4 and honoured here:

- ``amount_paise`` can be negative, where a chargeback exceeds the
  payout. int64 is signed; nothing clamps it.
- ``utr`` repeats across batched payouts and must never be used as a
  join key. It is loaded as an ordinary string column.
"""

from ._base import read_ledger

COLUMNS = (
    "settlement_id",
    "payment_id",
    "settled_at",
    "amount_paise",
    "utr",
    "status",
)
DATE_COLUMNS = ("settled_at",)
AMOUNT_COLUMNS = ("amount_paise",)


def load_settlements(path):
    """Read the bank settlement ledger.

    Args:
        path: Path to ``settlements.csv``.

    Returns:
        A DataFrame with the schema documented above.

    Raises:
        MissingColumnError: A documented column is absent from the file.
    """
    return read_ledger(
        path,
        columns=COLUMNS,
        date_columns=DATE_COLUMNS,
        amount_columns=AMOUNT_COLUMNS,
    )
