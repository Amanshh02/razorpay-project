# Detector fixtures

**These are hand-built test fixtures, not real data and not the eval
set.** They live in their own directory so the labelled 130-order eval
fixtures at `tests/fixtures/` stay exactly as they are. Nothing here is
read by `evals/run_eval.py`.

Six orders, each constructed to exercise one branch of the stage 4
detectors. Every row is internally consistent: `net + gst == gross`,
`payment.amount == order.gross`, `fee + gst_on_fee == total_deduction`,
and the settlement is `expected − shortfall` where
`expected = payment − total_deduction`.

| Order | Shortfall | As % of payment | Expected result |
|---|---|---|---|
| `ord_clean_01` | 0 | 0% | No flag. Negative fixture for every detector. |
| `ord_refund_30` | 708000 | 30% | Refund, **high** confidence. |
| `ord_refund_22` | 371700 | 21% | Refund, **medium** confidence — sits in the 0.20–0.22 grey zone. |
| `ord_chargeback_01` | 994000 | 105.3% | Chargeback: full reversal plus the ₹500 fee. Settlement is negative. |
| `ord_small_gap` | 17700 | 3% | Settlement shortfall, **medium** confidence. Below the refund threshold. |
| `ord_shortfall_19` | 269040 | 19% | Settlement shortfall, **low** confidence — just under the 0.20 refund threshold, so it could plausibly be a refund. |
| `ord_tolerance_edge` | 50 | 0.01% | Within the 100-paise tolerance. No flag. |
| `ord_overpaid` | −25000 | −3.5% | Settlement **excess**: paid 25000 paise *more* than expected. |
| `ord_missing_payment` | n/a | n/a | Order marked paid with no row in payments.csv. Never reaches `reconciled`; surfaces via `unreconciled`. Expected recovery is the full gross of 1062000, **no fee imputed**. |

`ord_refund_22` exists because the real fixture set contains no refund
in the 0.20–0.22 grey zone at all — every genuine refund there is at
25% or above. Without this row the medium-confidence branch would never
be exercised.

Its name records the order it was added as, not its current shortfall:
it was built at 22% when the high-confidence boundary was 0.25, and
moved to 21% when that boundary came down to 0.22. The shortfall in the
table above is authoritative.

`ord_chargeback_01` settles to **−72278 paise**. A chargeback can drive
a payout negative, and the loaders and detectors must carry the sign
through rather than clamping at zero.

`ord_shortfall_19` sits at 19%, inside the 2-point band just below the
refund threshold. It is the only fixture exercising the low-confidence
shortfall branch, which exists because a 19% gap and a 21% gap are not
meaningfully different events — only the threshold separates them.

`ord_overpaid` and `ord_missing_payment` have no counterpart in the
130-order eval set: that set contains no overpayment at all, and its
three missing payments are reachable only through `unreconciled`. Both
branches would otherwise go untested.
