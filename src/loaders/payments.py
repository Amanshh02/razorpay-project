"""Loader for ``payments.csv`` — the Razorpay payment ledger.

Returned schema, in this order:

================== ================== ============================
Column             dtype              Notes
================== ================== ============================
``payment_id``     object (str)       Primary key
``order_id``       object (str)       FK to orders.order_id
``captured_at``    datetime64, IST    Parsed, tz-aware
``amount_paise``   int64              Paise captured
``method``         object (str)       upi / wallet / card / netbanking
``status``         object (str)       ``captured`` in the fixtures
================== ================== ============================

See docs/data-model.md section 2. Razorpay captures the gross amount;
fees are deducted later, at settlement.
"""

from ._base import read_ledger

COLUMNS = (
    "payment_id",
    "order_id",
    "captured_at",
    "amount_paise",
    "method",
    "status",
)
DATE_COLUMNS = ("captured_at",)
AMOUNT_COLUMNS = ("amount_paise",)


def load_payments(path):
    """Read the Razorpay payment ledger.

    Args:
        path: Path to ``payments.csv``.

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
