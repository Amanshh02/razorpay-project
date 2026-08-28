# Data model

Column-level spec for the four CSV ledgers. Everything here was read
off the actual header rows and verified against the fixture set in
`tests/fixtures/` (130 orders). Where a fact could not be established
from the data it is marked **UNKNOWN** rather than guessed.

Conventions used throughout:

- **All amounts are integer paise.** No column anywhere in these four
  files is denominated in rupees. Nothing is a float.
- **All IDs are strings.** Read every ledger with `dtype=str` and
  convert amount columns explicitly afterwards.
- **All timestamps are naive** — no offset, no `Z`, no timezone name.
  Format is exactly `%Y-%m-%d %H:%M:%S`. Per CLAUDE.md §9 they are
  treated as **IST** and localised on read. This is a project
  decision, not something the files state.
- "Null?" below means *observed* nullability. No column in any of the
  four ledgers contains a blank in the current fixture set. That is
  not a schema guarantee for real exports — see the open questions.

---

## 1. `orders.csv` — merchant order ledger

130 rows. One row per order. What the merchant believes happened.

| Column | Type | Unit | Null? | Notes |
|---|---|---|---|---|
| `order_id` | string | — | none observed | Primary key. Unique across all 130 rows. Format `ord_00001` (`ord_` + 5 digits). |
| `order_date` | datetime | IST | none observed | `%Y-%m-%d %H:%M:%S`. Always at or before the matching `captured_at`. |
| `customer_id` | string | — | none observed | Format `cust_1276` (`cust_` + 4 digits). 111 distinct across 130 orders — customers repeat. Not a join key. |
| `net_amount_paise` | integer | paise | none observed | Order value excluding GST. |
| `gst_amount_paise` | integer | paise | none observed | GST charged to the customer. Distinct from GST on Razorpay's fee — see section 3. |
| `gross_amount_paise` | integer | paise | none observed | What the customer was billed. |
| `payment_id` | string | — | none observed | Foreign key to `payments.payment_id`. Unique — no order carries two payments. **3 of the 130 values have no matching row in `payments.csv`.** That is the signal, not a data error. |
| `status` | string | — | none observed | Only value present is `paid` (130/130). Full domain **UNKNOWN**. |

**Verified identity:** `net_amount_paise + gst_amount_paise ==
gross_amount_paise` holds for all 130 rows exactly, no tolerance
needed.

---

## 2. `payments.csv` — Razorpay payment ledger

127 rows. What Razorpay records as actually received.

| Column | Type | Unit | Null? | Notes |
|---|---|---|---|---|
| `payment_id` | string | — | none observed | Primary key. Unique. Format `pay_00001`. |
| `order_id` | string | — | none observed | Foreign key to `orders.order_id`. Every value resolves — there are no orphan payments. |
| `captured_at` | datetime | IST | none observed | `%Y-%m-%d %H:%M:%S`. |
| `amount_paise` | integer | paise | none observed | Amount captured. |
| `method` | string | — | none observed | Observed domain: `upi` (35), `wallet` (34), `card` (30), `netbanking` (28). Whether other values exist is **UNKNOWN**. |
| `status` | string | — | none observed | Only value present is `captured` (127/127). Full domain **UNKNOWN**. |

**Verified identity:** `payments.amount_paise ==
orders.gross_amount_paise` for all 127 matched pairs, exactly. The
customer is billed gross and Razorpay captures gross; fees come out
later, at settlement.

---

## 3. `fees.csv` — Razorpay fees and taxes

127 rows. One row per payment. Every payment has exactly one fee row.

| Column | Type | Unit | Null? | Notes |
|---|---|---|---|---|
| `payment_id` | string | — | none observed | Primary key **and** foreign key to `payments.payment_id`. 1:1. |
| `fee_paise` | integer | paise | none observed | Razorpay's commission. |
| `gst_on_fee_paise` | integer | paise | none observed | GST on the commission. **Keep separate from `fee_paise`** (CLAUDE.md §8) and separate from `orders.gst_amount_paise`, which is a different tax on a different base. |
| `total_deduction_paise` | integer | paise | none observed | Convenience column, equal to the two above summed. |

**Verified identities**, all exact across 127/127 rows:

- `fee_paise + gst_on_fee_paise == total_deduction_paise`
- `fee_paise == round(payments.amount_paise * 0.02)`
- `gst_on_fee_paise == round(fee_paise * 0.18)`

So the fixtures use a **flat 2% commission plus 18% GST on that
commission**. This was derived from `fees.csv` and `payments.csv`
alone — not from the answer key. Whether the real rate is flat or
varies by `method` is **UNKNOWN**; see open question 3.

---

## 4. `settlements.csv` — bank settlement ledger

127 rows. What the bank actually paid out.

| Column | Type | Unit | Null? | Notes |
|---|---|---|---|---|
| `settlement_id` | string | — | none observed | Primary key. Unique. Format `setl_0001_00001` — `setl_` + 4-digit batch + 5-digit sequence. |
| `payment_id` | string | — | none observed | Foreign key to `payments.payment_id`. **At most one settlement per payment** in this fixture set, so the join is 1:1. Split settlements are out of scope per README. |
| `settled_at` | datetime | IST | none observed | Every row is at `11:30:00` — settlement runs as a daily batch. |
| `amount_paise` | integer | **signed** paise | none observed | **Can be negative.** 12 of 127 rows are negative, where a chargeback exceeds the payout. Do not assume unsigned. |
| `utr` | string | — | none observed | Bank reference, e.g. `HDFC3226797778`. **Not unique** — 4 UTRs appear on 2 rows each, batched payouts sharing one bank transfer. **Never use as a join key.** |
| `status` | string | — | none observed | Only value present is `processed` (127/127). Full domain **UNKNOWN**. |

---

## Join keys

The ID chain, in order. Match on this and never on date proximity
(CLAUDE.md §9).

```
orders.payment_id   ──1:1──>  payments.payment_id
payments.payment_id ──1:1──>  fees.payment_id
payments.payment_id ──1:1──>  settlements.payment_id
```

`payments.order_id` back-references `orders.order_id` and is
redundant with `orders.payment_id`; the two agree on all 127 matched
rows. Either direction works.

Cardinality as measured:

| Relationship | Result |
|---|---|
| orders → payments | 127 of 130 resolve; **3 orders have no payment** |
| payments → orders | 127 of 127 resolve; no orphan payments |
| payments → fees | 127 of 127; every payment has exactly one fee row |
| payments → settlements | 127 of 127; every payment has exactly one settlement |
| settlements per payment | max 1 |

**Settlement lag:** 1.59 to 4.06 days after capture (whole-day
buckets: 1 day ×36, 2 ×40, 3 ×46, 4 ×5). The lag is real and
variable, which is exactly why matching is by ID and never by date.

---

## Expected settlement formula

For any order that has a payment row and a fee row:

```
expected_settlement_paise =
      payments.amount_paise
    − fees.fee_paise
    − fees.gst_on_fee_paise
```

equivalently `payments.amount_paise − fees.total_deduction_paise`.

**This is verified, not assumed.** Across the 99 orders carrying no
anomaly, `settlements.amount_paise` equals this expression with a
maximum absolute delta of **0 paise**. The formula is exact on clean
data.

The discrepancy for an order is:

```
delta_paise = settlements.amount_paise − expected_settlement_paise
```

A negative delta means the merchant was underpaid.

### Refunds and chargebacks are classifications, not terms

There is no refund column and no chargeback column in any of the four
ledgers, no refund ledger file exists, and none is coming. **They are
not inputs to the formula.**

A refund or chargeback is what a negative delta *turns out to be*. It
shows up only as an unexplained shortfall in
`settlements.amount_paise`, with nothing in the merchant ledger to
account for it. The deterministic layer computes the delta;
classifying that delta as a refund, a chargeback, or a plain
shortfall is a separate step downstream of the arithmetic.

An earlier version of the README stated the identity as
`payment − fee − GST − refunds − chargebacks`. That was wrong and has
been corrected — subtracting a refund that no ledger records would
mean subtracting the very quantity being detected.

### Orders with no payment row

For the 3 orders whose `payment_id` is absent from `payments.csv`
there is no payment amount and no fee row, so the formula above
cannot be evaluated at all. For these:

```
expected_recovery_paise = orders.gross_amount_paise
```

**No fee is imputed.** If the payment never reached Razorpay then no
commission was ever charged, so deducting a notional 2% + 18% would
understate the merchant's actual loss. The full gross is the exposure.

---

## Tolerance rule

- Never compare amounts with `==` (CLAUDE.md §8).
- One tolerance constant, defined once in `config.py`, default
  **100 paise (₹1)**, matching README.
- An order is flagged when `abs(delta_paise) > TOLERANCE_PAISE`.
- Round only at display time. All arithmetic stays in integer paise.

On this fixture set the clean rows are exact to 0 paise, so tolerance
is not currently absorbing any rounding noise. It exists for real
exports.

---

## `ground_truth.csv` is not an input ledger

`tests/fixtures/ground_truth.csv` is the eval answer key. Only
`evals/run_eval.py` may read it (CLAUDE.md §11 and §13). No loader,
matcher, or detector may reference it. It is documented here purely
so the harness has a contract.

| Column | Type | Unit |
|---|---|---|
| `order_id` | string | — |
| `payment_id` | string | — |
| `anomaly_type` | string | one of `refund_not_reflected` (15), `settlement_shortfall` (8), `chargeback` (5), `payment_not_received` (3) |
| `expected_amount_paise` | integer | paise |
| `actual_amount_paise` | integer | paise |
| `delta_paise` | integer | signed paise |
| `notes` | string | free text |

31 labelled anomalies across 130 orders.

---

## Open questions

These are open questions about **production** data. Nothing here
blocks work against the fixtures.

1. **Is 2% + 18% contractual or per-method?** The fixtures are flat
   across all four payment methods; real Razorpay pricing differs by
   method. This does not affect the formula, which reads the actual
   per-row fee from `fees.csv` rather than applying a rate — but it
   matters for any future sanity check on whether a fee row is
   plausible.
2. **Status domains.** Each status column has exactly one value in
   the fixtures (`paid`, `captured`, `processed`). What other values
   will real exports contain, and which mean "do not reconcile this
   row"?
3. **Nullability in real exports.** Nothing is null in the fixtures.
   Which columns can actually be blank? This determines whether a
   loader rejects a row or sends it to the `unreconciled` bucket.
