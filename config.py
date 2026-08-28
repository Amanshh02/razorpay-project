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
# Below it, the gap is reported as a settlement shortfall instead.
REFUND_THRESHOLD_PCT = 0.20

# Where the "near the boundary" band ends. A refund ratio between
# REFUND_THRESHOLD_PCT and this value sits close enough to the line to be
# low confidence; at or above it, medium. The same width, mirrored below
# REFUND_THRESHOLD_PCT, marks the near-boundary band for shortfalls.
#
# This is a narrow MARGIN ABOVE REFUND_THRESHOLD_PCT, not an independent
# value, and it must stay that way. Real refunds cluster on round
# percentages - 25, 30, 50, 100 - and a boundary sitting on a cluster
# point gets decided by rounding noise rather than by the data: an exact
# 25% refund can compute to 0.2499999 and flip to the wrong side. Keep
# this just above the threshold, clear of any common refund percentage.
REFUND_NEAR_THRESHOLD_PCT = 0.22


# --- what confidence means -------------------------------------------
#
# Confidence rates HOW SHARP THE RULE'S SIGNATURE IS, not how far a
# value sits from a threshold. Those are different questions and only
# the first one is worth reporting.
#
# Confidence was previously derived from threshold distance, and it was
# confident about the wrong thing. Measured on the hard fixture set, a
# threshold-derived confidence marked five of its ten wrong answers
# HIGH, while the low-confidence bucket was 100% correct - the signal
# ran backwards. The reason is structural: a chargeback carrying a fee
# other than CHARGEBACK_FEE_PAISE produces a shortfall of ~105% of the
# captured payment, which is enormously far from the 20% refund line, so
# the refund rule fired at maximum confidence on a chargeback. Distance
# from a line says nothing about whether the line belongs there, and the
# line is exactly what these rules get wrong.
#
# So confidence is now a property of the detector, not of the row:
#
#   high    chargeback, payment_not_received, settlement_excess.
#           Each is an arithmetic identity that either matches within
#           TOLERANCE_PAISE or does not. There is no continuum to be
#           wrong about.
#
#   medium  refund_not_reflected and settlement_shortfall, when the
#           ratio is clear of the boundary band.
#
#   low     the same two, when the ratio sits inside the boundary band.
#
# refund_not_reflected and settlement_shortfall are NEVER high. Nothing
# in the four ledgers distinguishes a large refund from a large
# shortfall; the split is a guess on a continuum, and a guess should not
# announce itself as certain however far it lands from the line.
