"""Overpayment detector.

The bank credited *more* than the expected payout, beyond tolerance.
The 130-order fixture set contains no such case - every anomaly there is
an underpayment - so this detector fires zero times against it and can
neither help nor hurt the measured accuracy of the other four types.

It exists because real exports will contain overpayments, and until now
they fell through every bucket silently: the other detectors all gate on
``delta < -TOLERANCE``, so a positive delta produced no finding at all.
That was a gap in coverage, not a decision.

Confidence is **high**, because confidence rates how sharp the rule's
signature is and this one is sharp: the settlement either exceeds the
expected payout beyond ``config.TOLERANCE_PAISE`` or it does not. There
is no threshold on a continuum to be wrong about.

That is a claim about the *detection*, not about the cause. Whether the
excess is a duplicate payout, a reversed deduction or a correction for
an earlier shortfall is not knowable from these four ledgers, and the
reason string says so. Rating that uncertainty as low confidence would
conflate "we are unsure this happened" with "we are unsure why", and
only the first belongs in this field - see the note in config.py.

Note that ``settlement_excess`` is not one of the four anomaly types in
``ground_truth.csv``. The eval must report it separately rather than
scoring it against labels that do not exist.
"""

from __future__ import annotations

import config

from ._base import HIGH, build_findings, rupees, with_deltas

SETTLEMENT_EXCESS = "settlement_excess"


def overpayment_mask(frame):
    """Overpaid beyond the tolerance. Never an ``==`` comparison."""
    return frame["delta_paise"] > config.TOLERANCE_PAISE


def detect_overpayments(reconciled):
    """Flag payouts larger than the expected settlement.

    Args:
        reconciled: The reconciled frame from ``src.matching``.

    Returns:
        A findings frame with the schema in ``_base.FINDING_COLUMNS``.
    """
    frame = with_deltas(reconciled)
    hits = frame[overpayment_mask(frame)]

    reasons = [
        f"Bank credited {rupees(row.actual_amount_paise)} against an expected "
        f"{rupees(row.expected_amount_paise)}, an excess of "
        f"{rupees(row.delta_paise)}. Fees and GST are already accounted for, "
        f"so the surplus is unexplained and may be recovered later."
        for row in hits.itertuples()
    ]
    return build_findings(hits, SETTLEMENT_EXCESS, HIGH, reasons)
