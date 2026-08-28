# Hard fixture set

**40 labelled orders built to break the current rules on purpose.**
This is not the regression baseline — `tests/fixtures/` is, and stays
untouched. This set exists because the rules score 1.000 on that
baseline, leaving the agent layer no headroom to demonstrate value.

**The rules are expected to fail here. Do not tune them to pass.**
Doing so would move the overfitting from one set to the other rather
than removing it. The gap between the two sets *is* the measurement.

Same four ledgers plus `ground_truth.csv`. Every row is internally
consistent with docs/data-model.md: `net + gst == gross`,
`payment.amount == order.gross`, `fee == round(gross × 0.02)`,
`gst_on_fee == round(fee × 0.18)`, and
`settlement == expected − shortfall`.

## Composition

| Count | Case | Labelled | What the rules do |
|---:|---|---|---|
| 14 | Clean, settles exactly as expected | — | Correctly unflagged |
| 5 | Refund at an arbitrary amount, above 20% | `refund_not_reflected` | **Correct.** Proves the rules key on magnitude, not on whole-percent slices |
| 3 | Refund at 12%, 15%, 8% — below the threshold | `refund_not_reflected` | **Fail** → `settlement_shortfall` |
| 2 | Unexplained shortfall at 35%, 28% — above the threshold | `settlement_shortfall` | **Fail** → `refund_not_reflected` |
| 3 | Chargeback with a ₹250 / ₹750 / ₹1000 fee | `chargeback` | **Fail** → `refund_not_reflected`; the signature assumes ₹500 |
| 2 | Chargeback with the standard ₹500 fee | `chargeback` | **Correct.** Control |
| 2 | Two refunds on one order, summing to an odd total | `refund_not_reflected` | One correct (sum ≥ 20%), one **fails** (sum below it) |
| 2 | Partial refund *plus* a separate small shortfall | `refund_not_reflected` | One correct on type, one **fails**; neither gets the amount right |
| 2 | Overpayment | `settlement_excess` | **Correct.** Gives the fifth type a labelled case |
| 2 | Order marked paid, no payment row | `payment_not_received` | **Correct** |
| 2 | Refund at 30% and 50% | `refund_not_reflected` | **Correct.** Control |
| 1 | Small unexplained shortfall at 3% | `settlement_shortfall` | **Correct.** Control |

26 labelled anomalies, 14 clean.

## Why each failure class matters

**Refunds below the threshold and shortfalls above it** are the same
failure seen from both sides. Nothing in the four ledgers distinguishes
them; the 20% line is a guess, and these eight orders are the ones it
guesses wrong. This is the single biggest source of error in the set.

**Chargebacks with a non-standard fee** expose `CHARGEBACK_FEE_PAISE`
as a contractual assumption rather than a fact. When the fee is not
₹500 the arithmetic signature does not match, the shortfall exceeds the
full payment, and the refund rule claims it instead.

**The combined refund-plus-shortfall orders** are the cases where even
a correct type label is not a correct answer: the delta conflates two
events, so the reported amount is wrong regardless of which label wins.
The eval scores types, not amounts, so these can pass while still being
wrong — worth remembering before reading any F1 as success.

**`settlement_excess`** has no labelled instance in the baseline set at
all. Without the two here, the fifth detector would never be scored.

## Generation

Built by a deterministic script with no randomness; every amount is
derived from the order's net value. The script is not committed, in
keeping with the baseline set. The CSVs are the artefact.
