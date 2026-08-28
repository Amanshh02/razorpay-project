"""Refund-not-reflected detector.

A refund paid back to the customer is deducted from the merchant's
payout, but no refund row exists in any of the four ledgers
(docs/data-model.md). It therefore surfaces only as an unexplained
shortfall.

Nothing in the ledgers distinguishes a large refund from a large
shortfall, so the split is a magnitude heuristic, not a derivation:

- shortfall >= ``config.REFUND_THRESHOLD_PCT`` of the captured payment
  -> refund
- below that -> not claimed here at all; see
  ``src.detectors.shortfalls``.

**A refund is never reported at high confidence**, however large the
shortfall. This is a threshold call on a continuum: a 105% shortfall is
further from the line than a 25% one but no more certain to be a refund
rather than a chargeback with an unusual fee. Confidence is medium when
the ratio is clear of the boundary band and low inside it - see the
note in config.py on why threshold distance is the wrong thing to
measure.

Chargebacks also clear the threshold, so they are excluded up front and
no order can carry both labels.
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

REFUND_NOT_REFLECTED = "refund_not_reflected"


def refund_mask(frame):
    """Rows short by at least the refund threshold, chargebacks removed."""
    return (
        is_short(frame)
        & ~chargeback_mask(frame)
        & (shortfall_ratio(frame) >= config.REFUND_THRESHOLD_PCT)
    )


def detect_refunds(reconciled):
    """Flag orders whose payout was reduced by an unrecorded refund.

    Args:
        reconciled: The reconciled frame from ``src.matching``.

    Returns:
        A findings frame with the schema in ``_base.FINDING_COLUMNS``.
    """
    frame = with_deltas(reconciled)
    hits = frame[refund_mask(frame)].copy()
    if hits.empty:
        return build_findings(hits, REFUND_NOT_REFLECTED, MEDIUM, [])

    ratio = shortfall_ratio(hits)
    near_boundary = ratio < config.REFUND_NEAR_THRESHOLD_PCT
    confidence = np.where(near_boundary, LOW, MEDIUM)
    reasons = [
        f"Payout short by {rupees(-row.delta_paise)}, {pct:.1%} of the "
        f"{rupees(row.payment_amount_paise)} captured, with no refund recorded "
        f"in any ledger. Bank settled {rupees(row.actual_amount_paise)} against "
        f"an expected {rupees(row.expected_amount_paise)}. Read as a refund on "
        f"size alone; no ledger evidence separates this from a shortfall."
        + (
            " The ratio also sits in the grey zone near the refund threshold."
            if near
            else ""
        )
        for row, pct, near in zip(hits.itertuples(), ratio, near_boundary)
    ]
    return build_findings(hits, REFUND_NOT_REFLECTED, confidence, reasons)
