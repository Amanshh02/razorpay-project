"""Shared shape and arithmetic for every anomaly detector.

Each detector is a separate function taking the reconciled frame from
``src.matching`` and returning findings in one fixed schema
(CLAUDE.md §10)::

    order_id, anomaly_type, expected_amount_paise,
    actual_amount_paise, delta_paise, confidence, reason

All arithmetic here is integer paise. Amounts are never compared with
``==``; every comparison goes through ``config.TOLERANCE_PAISE``
(CLAUDE.md §8). Rounding happens only in the human-readable ``reason``
string, never in a value a later stage reads.
"""

from __future__ import annotations

import pandas as pd

import config

FINDING_COLUMNS = (
    "order_id",
    "anomaly_type",
    "expected_amount_paise",
    "actual_amount_paise",
    "delta_paise",
    "confidence",
    "reason",
)

HIGH = "high"
MEDIUM = "medium"
LOW = "low"


def with_deltas(reconciled):
    """Attach the expected payout and the signed delta to every order.

    ``expected_amount_paise`` is the formula verified in
    docs/data-model.md: the captured payment less Razorpay's total
    deduction. ``delta_paise`` is negative when the merchant was
    underpaid.
    """
    frame = reconciled.copy()
    frame["expected_amount_paise"] = (
        frame["payment_amount_paise"] - frame["total_deduction_paise"]
    )
    frame["actual_amount_paise"] = frame["settlement_amount_paise"]
    frame["delta_paise"] = (
        frame["actual_amount_paise"] - frame["expected_amount_paise"]
    )
    return frame


def is_short(frame):
    """Underpaid by more than the tolerance. Never an ``==`` comparison."""
    return frame["delta_paise"] < -config.TOLERANCE_PAISE


def shortfall_ratio(frame):
    """Shortfall as a fraction of the captured payment.

    Guards against a zero-amount payment rather than emitting inf.
    """
    payment = frame["payment_amount_paise"]
    return (-frame["delta_paise"]).where(payment > 0, 0) / payment.where(payment > 0, 1)


def empty_findings():
    """An empty findings frame with the documented columns and dtypes."""
    return pd.DataFrame({column: [] for column in FINDING_COLUMNS}).astype(
        {
            "order_id": "object",
            "anomaly_type": "object",
            "expected_amount_paise": "int64",
            "actual_amount_paise": "int64",
            "delta_paise": "int64",
            "confidence": "object",
            "reason": "object",
        }
    )


def build_findings(frame, anomaly_type, confidence, reasons):
    """Assemble findings rows in the fixed schema.

    Args:
        frame: Rows carrying the columns added by :func:`with_deltas`.
        anomaly_type: The label for every row in ``frame``.
        confidence: A scalar level, or a Series aligned to ``frame``.
        reasons: A sequence of reason strings aligned to ``frame``.
    """
    if frame.empty:
        return empty_findings()
    return pd.DataFrame(
        {
            "order_id": frame["order_id"].to_numpy(),
            "anomaly_type": anomaly_type,
            "expected_amount_paise": frame["expected_amount_paise"].astype("int64").to_numpy(),
            "actual_amount_paise": frame["actual_amount_paise"].astype("int64").to_numpy(),
            "delta_paise": frame["delta_paise"].astype("int64").to_numpy(),
            "confidence": confidence,
            "reason": list(reasons),
        },
        columns=list(FINDING_COLUMNS),
    )


def rupees(paise):
    """Render paise as rupees for a reason string. Display only."""
    return f"Rs {paise / 100:,.2f}"
