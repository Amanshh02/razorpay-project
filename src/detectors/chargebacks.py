"""Chargeback detector.

A chargeback reverses the whole captured payment and withholds a flat
penalty on top, so the payout falls short by::

    payment_amount_paise + config.CHARGEBACK_FEE_PAISE

matched within ``config.TOLERANCE_PAISE`` rather than exactly. The
resulting settlement is frequently negative.

This is the one anomaly in stage 4 with a sharp arithmetic signature,
so it is reported at high confidence. The penalty itself is a heuristic
constant — see the warning in config.py.
"""

from __future__ import annotations

import config

from ._base import HIGH, build_findings, is_short, rupees, with_deltas

CHARGEBACK = "chargeback"


def chargeback_mask(frame):
    """Rows whose shortfall is the full payment plus the flat penalty.

    Exposed so the refund detector can exclude these rows: a chargeback
    also clears the refund threshold, and no order may carry both
    labels.
    """
    reversal = frame["payment_amount_paise"] + config.CHARGEBACK_FEE_PAISE
    return is_short(frame) & ((frame["delta_paise"] + reversal).abs() <= config.TOLERANCE_PAISE)


def detect_chargebacks(reconciled):
    """Flag orders whose payout was reversed and penalised.

    Args:
        reconciled: The reconciled frame from ``src.matching``.

    Returns:
        A findings frame with the schema in ``_base.FINDING_COLUMNS``.
    """
    frame = with_deltas(reconciled)
    hits = frame[chargeback_mask(frame)]

    reasons = [
        f"Payout short by {rupees(-row.delta_paise)}, which is the full captured "
        f"payment of {rupees(row.payment_amount_paise)} reversed plus a "
        f"{rupees(config.CHARGEBACK_FEE_PAISE)} chargeback fee withheld. "
        f"Bank settled {rupees(row.actual_amount_paise)} against an expected "
        f"{rupees(row.expected_amount_paise)}."
        for row in hits.itertuples()
    ]
    return build_findings(hits, CHARGEBACK, HIGH, reasons)
