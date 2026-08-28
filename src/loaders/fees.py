"""Loader for ``fees.csv`` — Razorpay fees and taxes.

Returned schema, in this order:

========================== ============ ================================
Column                     dtype        Notes
========================== ============ ================================
``payment_id``             object (str) Primary key and FK to payments
``fee_paise``              int64        Paise, Razorpay's commission
``gst_on_fee_paise``       int64        Paise, GST on that commission
``total_deduction_paise``  int64        Paise, the two above summed
========================== ============ ================================

``gst_on_fee_paise`` is kept as its own column and is never merged into
``fee_paise`` (CLAUDE.md §8). It is also a different tax on a different
base from ``orders.gst_amount_paise``. There are no date columns in this
ledger.

See docs/data-model.md section 3.
"""

from ._base import read_ledger

COLUMNS = (
    "payment_id",
    "fee_paise",
    "gst_on_fee_paise",
    "total_deduction_paise",
)
AMOUNT_COLUMNS = ("fee_paise", "gst_on_fee_paise", "total_deduction_paise")


def load_fees(path):
    """Read the Razorpay fee ledger.

    Args:
        path: Path to ``fees.csv``.

    Returns:
        A DataFrame with the schema documented above.

    Raises:
        MissingColumnError: A documented column is absent from the file.
    """
    return read_ledger(path, columns=COLUMNS, amount_columns=AMOUNT_COLUMNS)
