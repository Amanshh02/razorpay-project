"""Refund-not-reflected detector.

A refund paid back to the customer is deducted from the merchant's
payout, but no refund row exists in any of the four ledgers
(docs/data-model.md). It therefore surfaces only as an unexplained
shortfall.

Nothing in the ledgers distinguishes a large refund from a large
shortfall, so the split is a magnitude heuristic, not a derivation:

- shortfall >= ``config.REFUND_HIGH_CONFIDENCE_PCT`` of the captured
  payment -> refund, high confidence
- shortfall >= ``config.REFUND_THRESHOLD_PCT`` -> refund, medium
  confidence. This is the grey zone where the rule is weakest.
- below that -> not claimed here at all; see
  ``src.detectors.unexplained``.

Chargebacks also clear the threshold, so they are excluded up front and
no order can carry both labels.
"""

from __future__ import annotations

import numpy as np

import config

from ._base import (
    HIGH,
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
        return build_findings(hits, REFUND_NOT_REFLECTED, HIGH, [])

    ratio = shortfall_ratio(hits)
    confidence = np.where(
        ratio >= config.REFUND_HIGH_CONFIDENCE_PCT, HIGH, MEDIUM
    )
    reasons = [
        f"Payout short by {rupees(-row.delta_paise)}, {pct:.1%} of the "
        f"{rupees(row.payment_amount_paise)} captured, with no refund recorded "
        f"in any ledger. Bank settled {rupees(row.actual_amount_paise)} against "
        f"an expected {rupees(row.expected_amount_paise)}."
        + (
            ""
            if pct >= config.REFUND_HIGH_CONFIDENCE_PCT
            else " Falls in the grey zone near the refund threshold, so the "
            "classification is provisional."
        )
        for row, pct in zip(hits.itertuples(), ratio)
    ]
    return build_findings(hits, REFUND_NOT_REFLECTED, confidence, reasons)
