"""Settlement shortfall detector.

The bank credited less than the expected payout, and neither stage 4
signature explains it: the gap is not the chargeback arithmetic, and it
is too small a fraction of the payment to read as a refund.

This detector **replaces** the stage 4 ``unexplained_negative_delta``
bucket rather than sitting alongside it. That bucket was a placeholder
holding exactly these rows until this stage existed; keeping both would
emit two findings per order and double-count in the eval. Precedence
across the whole set is now: chargeback, then refund, then shortfall,
each mask excluding the ones before it, so every underpayment lands in
exactly one bucket.

Confidence reflects how safe the *label* is, not whether the gap is
real - the arithmetic is certain in every case:

- **low** when the shortfall sits in the narrow band just under
  ``config.REFUND_THRESHOLD_PCT``. A 19% gap and a 21% gap are not
  meaningfully different events; only the threshold separates them, so
  a call near it is provisional.
- **medium** otherwise. The gap is definite and the classification is
  sound by elimination, but no positive signature identifies the cause.

Nothing here is high confidence. A shortfall is what is left when the
explanations run out.
"""

from __future__ import annotations

import numpy as np

import config

from ._base import (
    LOW,
    MEDIUM,
    build_findings,
    is_short,
    rupees,
    shortfall_ratio,
    with_deltas,
)
from .chargebacks import chargeback_mask
from .refunds import refund_mask

SETTLEMENT_SHORTFALL = "settlement_shortfall"


def _grey_zone_width():
    """How far below the refund threshold a call is still provisional.

    Reuses the stage 4 grey zone rather than introducing a fourth
    constant: the band above the threshold and the band below it are the
    same kind of uncertainty, seen from either side.
    """
    return config.REFUND_HIGH_CONFIDENCE_PCT - config.REFUND_THRESHOLD_PCT


def shortfall_mask(frame):
    """Underpaid beyond tolerance, and not claimed by stage 4."""
    return is_short(frame) & ~chargeback_mask(frame) & ~refund_mask(frame)


def detect_settlement_shortfalls(reconciled):
    """Flag payouts short of expectation with no identifiable cause.

    Args:
        reconciled: The reconciled frame from ``src.matching``.

    Returns:
        A findings frame with the schema in ``_base.FINDING_COLUMNS``.
    """
    frame = with_deltas(reconciled)
    hits = frame[shortfall_mask(frame)]
    if hits.empty:
        return build_findings(hits, SETTLEMENT_SHORTFALL, MEDIUM, [])

    ratio = shortfall_ratio(hits)
    near_threshold = ratio >= config.REFUND_THRESHOLD_PCT - _grey_zone_width()
    confidence = np.where(near_threshold, LOW, MEDIUM)

    reasons = [
        f"Bank credited {rupees(row.actual_amount_paise)} against an expected "
        f"{rupees(row.expected_amount_paise)}, short by "
        f"{rupees(-row.delta_paise)} ({pct:.2%} of the "
        f"{rupees(row.payment_amount_paise)} captured). Fees and GST are "
        f"already accounted for and no refund or chargeback signature "
        f"matches, so the cause is unidentified."
        + (
            " The gap sits just under the refund threshold, so this could "
            "equally be a small unreflected refund."
            if near
            else ""
        )
        for row, pct, near in zip(hits.itertuples(), ratio, near_threshold)
    ]
    return build_findings(hits, SETTLEMENT_SHORTFALL, confidence, reasons)
