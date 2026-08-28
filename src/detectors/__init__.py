"""One function per anomaly type. See CLAUDE.md §10 for the contract."""

from ._base import FINDING_COLUMNS, HIGH, LOW, MEDIUM, empty_findings
from .chargebacks import CHARGEBACK, detect_chargebacks
from .refunds import REFUND_NOT_REFLECTED, detect_refunds
from .unexplained import (
    UNEXPLAINED_NEGATIVE_DELTA,
    detect_unexplained_negative_deltas,
)

__all__ = [
    "CHARGEBACK",
    "FINDING_COLUMNS",
    "HIGH",
    "LOW",
    "MEDIUM",
    "REFUND_NOT_REFLECTED",
    "UNEXPLAINED_NEGATIVE_DELTA",
    "detect_chargebacks",
    "detect_refunds",
    "detect_unexplained_negative_deltas",
    "empty_findings",
]
