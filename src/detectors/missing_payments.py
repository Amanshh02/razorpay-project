"""Missing payment detector.

The merchant marked an order paid but Razorpay has no record of the
payment. These orders never reach the reconciled frame at all - the
matcher cannot join them past the first link in the chain - so this
detector reads ``unreconciled`` instead, which is why its signature
differs from the others.

Expected recovery is the **full gross**, per docs/data-model.md::

    expected_amount_paise = orders.gross_amount_paise

No fee is imputed. If the payment never reached Razorpay then no
commission was ever charged, and deducting a notional one would
understate the merchant's loss.
"""

from __future__ import annotations

from ._base import HIGH, build_findings, empty_findings, rupees
from ..matching.engine import MISSING_PAYMENT

PAYMENT_NOT_RECEIVED = "payment_not_received"


def detect_missing_payments(unreconciled, orders):
    """Flag orders marked paid that Razorpay never recorded.

    Args:
        unreconciled: The unreconciled frame from ``src.matching``.
        orders: The orders frame from ``load_orders``, for the gross
            amount, which ``unreconciled`` does not carry.

    Returns:
        A findings frame with the schema in ``_base.FINDING_COLUMNS``.
    """
    hits = unreconciled[
        (unreconciled["source_ledger"] == "orders")
        & (unreconciled["reason"] == MISSING_PAYMENT)
    ]
    if hits.empty:
        return empty_findings()

    gross_by_order = dict(zip(orders["order_id"], orders["gross_amount_paise"]))
    frame = hits.assign(
        expected_amount_paise=[
            int(gross_by_order[order_id]) for order_id in hits["order_id"]
        ],
        actual_amount_paise=0,
    )
    frame["delta_paise"] = (
        frame["actual_amount_paise"] - frame["expected_amount_paise"]
    )

    reasons = [
        f"Order marked paid for {rupees(row.expected_amount_paise)} but no row "
        f"exists in payments.csv for {row.payment_id}. Nothing was captured, "
        f"so nothing settled and no fee was charged; the full gross is at risk."
        for row in frame.itertuples()
    ]
    return build_findings(frame, PAYMENT_NOT_RECEIVED, HIGH, reasons)
