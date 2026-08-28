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
