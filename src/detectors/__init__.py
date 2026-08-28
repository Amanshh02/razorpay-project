"""One function per anomaly type. See CLAUDE.md §10 for the contract.

Four of the five read the reconciled frame from ``src.matching``.
``detect_missing_payments`` reads ``unreconciled`` instead, because an
order with no payment row never joins far enough to be reconciled.

The reconciled-frame detectors partition every gap beyond tolerance:
chargeback, then refund, then shortfall for underpayments, and
settlement excess for the other direction. No order is claimed twice and
none falls through.
"""

from ._base import FINDING_COLUMNS, HIGH, LOW, MEDIUM, empty_findings
from .chargebacks import CHARGEBACK, detect_chargebacks
from .missing_payments import PAYMENT_NOT_RECEIVED, detect_missing_payments
from .overpayments import SETTLEMENT_EXCESS, detect_overpayments
from .refunds import REFUND_NOT_REFLECTED, detect_refunds
from .shortfalls import SETTLEMENT_SHORTFALL, detect_settlement_shortfalls

__all__ = [
    "CHARGEBACK",
    "FINDING_COLUMNS",
    "HIGH",
    "LOW",
    "MEDIUM",
    "PAYMENT_NOT_RECEIVED",
    "REFUND_NOT_REFLECTED",
    "SETTLEMENT_EXCESS",
    "SETTLEMENT_SHORTFALL",
    "detect_chargebacks",
    "detect_missing_payments",
    "detect_overpayments",
    "detect_refunds",
    "detect_settlement_shortfalls",
    "empty_findings",
]
