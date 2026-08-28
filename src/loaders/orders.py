"""Loader for ``orders.csv`` — the merchant order ledger.

Returned schema, in this order:

===================== ================== =========================
Column                dtype              Notes
===================== ================== =========================
``order_id``          object (str)       Primary key
``order_date``        datetime64, IST    Parsed, tz-aware
``customer_id``       object (str)       Not a join key
``net_amount_paise``  int64              Paise, excl. customer GST
``gst_amount_paise``  int64              Paise, GST charged to customer
``gross_amount_paise``int64              Paise, what was billed
``payment_id``        object (str)       FK to payments.payment_id
``status``            object (str)       ``paid`` in the fixtures
===================== ================== =========================

See docs/data-model.md section 1 for units, nullability and the
verified identity ``net + gst == gross``.
"""

from ._base import read_ledger

COLUMNS = (
    "order_id",
    "order_date",
    "customer_id",
    "net_amount_paise",
    "gst_amount_paise",
    "gross_amount_paise",
    "payment_id",
    "status",
)
DATE_COLUMNS = ("order_date",)
AMOUNT_COLUMNS = ("net_amount_paise", "gst_amount_paise", "gross_amount_paise")


def load_orders(path):
    """Read the merchant order ledger.

    Args:
        path: Path to ``orders.csv``.

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
