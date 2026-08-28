"""The residual bucket: underpaid, but too small to call a refund.

These orders are short beyond tolerance yet below
``config.REFUND_THRESHOLD_PCT`` of the captured payment, so the refund
heuristic explicitly declines to claim them. They are reported as
``unexplained_negative_delta`` at low confidence rather than being
dropped or silently folded into refunds.

Stage 5 builds the settlement-shortfall detector over this bucket.
"""

from __future__ import annotations

from ._base import LOW, build_findings, is_short, rupees, shortfall_ratio, with_deltas
from .chargebacks import chargeback_mask
from .refunds import refund_mask

UNEXPLAINED_NEGATIVE_DELTA = "unexplained_negative_delta"


def detect_unexplained_negative_deltas(reconciled):
    """Flag underpayments that neither stage 4 detector claims.

    Args:
        reconciled: The reconciled frame from ``src.matching``.

    Returns:
        A findings frame with the schema in ``_base.FINDING_COLUMNS``.
    """
    frame = with_deltas(reconciled)
    hits = frame[is_short(frame) & ~chargeback_mask(frame) & ~refund_mask(frame)]

    ratio = shortfall_ratio(hits)
    reasons = [
        f"Payout short by {rupees(-row.delta_paise)}, {pct:.2%} of the "
        f"{rupees(row.payment_amount_paise)} captured. Too small to attribute "
        f"to a refund and it does not match the chargeback signature, so the "
        f"cause is unidentified."
        for row, pct in zip(hits.itertuples(), ratio)
    ]
    return build_findings(hits, UNEXPLAINED_NEGATIVE_DELTA, LOW, reasons)
