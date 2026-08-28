"""Project-wide constants.

Every module reads its tolerance and timezone from here. Neither value
may be redefined anywhere else.
"""

# Amount comparison tolerance, in integer paise (CLAUDE.md section 8).
# Never compare two amounts with ==; compare abs(delta) against this.
# 100 paise = Rs 1, matching the figure quoted in README.md.
TOLERANCE_PAISE = 100

# One timezone project-wide (CLAUDE.md section 9). Ledger timestamps are
# naive and are localised to this on read, not scattered through the code.
TIMEZONE = "Asia/Kolkata"


# --- detection heuristics --------------------------------------------
#
# WARNING: the three constants below are HEURISTICS TUNED ON SYNTHETIC
# FIXTURES, not contractual values. They separate the fixture anomalies
# cleanly, which is not evidence that they separate real ones. Revisit
# every one against a real merchant export before trusting an accuracy
# number derived from them.

# Razorpay's flat chargeback penalty, withheld from the payout on top of
# the reversed payment. May vary by contract, card network or method.
CHARGEBACK_FEE_PAISE = 50_000

# A shortfall at or above this fraction of the captured payment is read
# as an unreflected refund rather than a plain settlement shortfall.
# Below it, the gap is reported as unexplained_negative_delta instead.
REFUND_THRESHOLD_PCT = 0.20

# At or above this fraction the refund call is high confidence; between
# REFUND_THRESHOLD_PCT and this value it is medium. The band between the
# two is the grey zone where the rule is least trustworthy.
REFUND_HIGH_CONFIDENCE_PCT = 0.25
