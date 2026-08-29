# AI Finance Controller — Technical Report

**Scope:** first commit (`1e77549`) to `beeb5a4`, 27 commits on `main`,
two tags. 193 tests. 2,440 lines under `src/`, 2,154 under `tests/`.

Every number in this report was produced by a command run against the
repository at `beeb5a4`, not quoted from memory. Where a figure comes
from a specific tool invocation, the invocation is named.

---

## 1. Problem statement

A merchant's money passes through four separate records before it lands
in their bank account:

| Ledger | Owner | What it claims |
|---|---|---|
| `orders.csv` | Merchant | What the customer was billed |
| `payments.csv` | Razorpay | What the gateway actually captured |
| `fees.csv` | Razorpay | Commission and GST deducted |
| `settlements.csv` | Bank | What was actually paid out |

These four should agree. When they don't, the gap is money that has
quietly left the merchant's account with no record of why. Four causes
recur:

- **A refund** was paid back to the customer and deducted from the
  payout, but no refund appears in any ledger the merchant holds.
- **A chargeback** reversed a payment and withheld a penalty on top, so
  the payout is *negative*.
- **A settlement shortfall** — the bank simply credited less than the
  arithmetic says it should have, with nothing to explain it.
- **A payment never received** — the merchant marked an order paid and
  the gateway has no record of it at all.

Today this is a spreadsheet job, done by hand, monthly. The work is
mechanical (join four files on an ID) but the volume makes it
error-prone, and the errors are asymmetric: a missed discrepancy is
money permanently lost, while a false alarm costs a human thirty
seconds. That asymmetry is why **recall is the priority metric**
throughout this project (CLAUDE.md §11).

Concretely, on the 130-order fixture set — measured by
`python -m src.main --data tests/fixtures --out reports/`:

```
orders read                      130
matched through the chain         127
could not be matched               3
flagged                           31
clean                             99

TOTAL EXPOSURE                 Rs 481,919.30   across 31 flags

anomaly type                flags              impact      largest single
refund_not_reflected           15       Rs 267,848.32        Rs 51,878.65
chargeback                      5       Rs 122,547.20        Rs 39,002.85
payment_not_received            3        Rs 88,423.82        Rs 53,835.03
settlement_shortfall            8         Rs 3,099.96           Rs 818.25
```

**Rs 481,919.30 at risk across 130 orders — 23.8% of orders carrying a
discrepancy.** A single order (`ord_00067`) accounts for Rs 53,835.03.

---

## 2. Architecture

### The deterministic/agent split

```
  orders.csv ─┐
payments.csv ─┼─> loaders ─> matcher ─> detectors ─> classifier ─> report ─> dashboard
    fees.csv ─┤   (pandas)   (pandas)    (pandas)     (Claude)     (pandas)  (streamlit)
settlements ─┘       │           │           │            │            │          │
                   dtype=str   ID chain   integer     label +      integer    reads CSV
                   IST dates   only       paise       reason       paise      only
                   int64 paise                        ONLY
                     │           │           │            │            │          │
                     └───────────┴───────────┴────────────┘            │          │
                          DETERMINISTIC LAYER              AGENT       │          │
                          no LLM, reproducible             LAYER       │          │
                                                                       │          │
                                                          PRESENTATION LAYER
                                                          no engine imports
```

Every number is computed by pandas. The LLM classifies and explains; it
never computes, adjusts, or corrects an amount.

### Why the split

Reconciliation arithmetic is exactly specified: `payment − fee − GST`.
An LLM adds nothing to it and takes away reproducibility and
auditability — a finance team cannot defend a number to an auditor if it
came from a sampled generative process. Conversely, deciding *why* a gap
exists is genuinely ambiguous, and that is where rules are weak and
judgement helps.

### How "no LLM touches a number" is enforced structurally

Not by convention. Four mechanisms, each tested:

1. **The agent's output schema cannot carry an amount.** It returns
   `{"label", "confidence", "explanation"}`. There is no numeric field
   to write into.
2. **`classify()` copies amount columns through untouched.**
   `tests/test_agent.py::test_no_amount_is_ever_modified` captures
   `expected_amount_paise`, `actual_amount_paise`, `delta_paise` before
   the call and asserts frame equality after — including
   `test_amounts_survive_even_when_every_label_is_overridden`, which
   forces an override on every routed row.
3. **The provider SDK is confined to one file.** Two tests assert the
   string `anthropic` appears nowhere in `src/` except
   `src/agent/client.py`.
4. **The dashboard cannot recompute.** `tests/test_dashboard.py` parses
   the AST of every file in `src/dashboard/` and asserts no import of
   `matching`, `detectors`, or `agent`. A viewer that can recompute is a
   viewer that can disagree with the report it displays.

### Money handling

Integer paise end to end. No float rupees anywhere in the pipeline.
Conversion to rupees happens only at display, in `src/report.py` and
`src/dashboard/data.py`, and no converted value is read back. Amounts
are never compared with `==`; every comparison goes through
`config.TOLERANCE_PAISE = 100`.

---

## 3. Data model

Full spec: [`docs/data-model.md`](data-model.md). Summary below.

### `orders.csv` — 130 rows

| Column | Type | Unit | Notes |
|---|---|---|---|
| `order_id` | string | — | PK, `ord_00001` |
| `order_date` | datetime | IST | `%Y-%m-%d %H:%M:%S` |
| `customer_id` | string | — | 111 distinct across 130; not a join key |
| `net_amount_paise` | int64 | paise | excl. customer GST |
| `gst_amount_paise` | int64 | paise | GST charged to customer |
| `gross_amount_paise` | int64 | paise | billed amount |
| `payment_id` | string | — | FK; **3 of 130 have no match** |
| `status` | string | — | `paid` 130/130 |

### `payments.csv` — 127 rows

| Column | Type | Unit | Notes |
|---|---|---|---|
| `payment_id` | string | — | PK |
| `order_id` | string | — | FK, all resolve |
| `captured_at` | datetime | IST | |
| `amount_paise` | int64 | paise | |
| `method` | string | — | upi 35, wallet 34, card 30, netbanking 28 |
| `status` | string | — | `captured` 127/127 |

### `fees.csv` — 127 rows

| Column | Type | Unit | Notes |
|---|---|---|---|
| `payment_id` | string | — | PK and FK, 1:1 |
| `fee_paise` | int64 | paise | commission |
| `gst_on_fee_paise` | int64 | paise | **distinct from `orders.gst_amount_paise`** |
| `total_deduction_paise` | int64 | paise | the two summed |

### `settlements.csv` — 127 rows

| Column | Type | Unit | Notes |
|---|---|---|---|
| `settlement_id` | string | — | PK, `setl_0001_00001` |
| `payment_id` | string | — | FK, 1:1 |
| `settled_at` | datetime | IST | always `11:30:00` — daily batch |
| `amount_paise` | int64 | **signed** paise | **12 of 127 negative** |
| `utr` | string | — | **not unique** — 4 UTRs on 2 rows each |
| `status` | string | — | `processed` 127/127 |

### Join keys

```
orders.payment_id   ──1:1──>  payments.payment_id
payments.payment_id ──1:1──>  fees.payment_id
payments.payment_id ──1:1──>  settlements.payment_id
```

Never by date. Settlement lag measured at **1.59 to 4.06 days**, varying
per order (whole-day buckets: 1 day ×36, 2 ×40, 3 ×46, 4 ×5). `utr` is
never a join key — it repeats across batched payouts.

### The three verified identities

Each was checked against every row, not sampled:

| Identity | Verified across | Result |
|---|---|---|
| `net + gst == gross` | 130/130 orders | exact, 0 mismatches |
| `fee + gst_on_fee == total_deduction` | 127/127 fee rows | exact, 0 mismatches |
| `payments.amount == orders.gross` | 127/127 matched pairs | exact, 0 mismatches |

Two further relationships hold across 127/127 and were derived from the
input ledgers alone, never the answer key:

- `fee_paise == round(payments.amount_paise * 0.02)`
- `gst_on_fee_paise == round(fee_paise * 0.18)`

### The settlement formula

```
expected_settlement_paise = payments.amount_paise − fees.total_deduction_paise
delta_paise               = settlements.amount_paise − expected_settlement_paise
```

**Verified, not assumed:** across the 99 orders carrying no anomaly,
`settlements.amount_paise` equals this expression with a **maximum
absolute delta of 0 paise**.

For the 3 orders with no payment row, the formula cannot be evaluated —
there is no payment amount and no fee row. For those:

```
expected_recovery_paise = orders.gross_amount_paise
```

**No fee is imputed.** If the payment never reached Razorpay, no
commission was charged, and deducting a notional 2% + 18% would
understate the loss.

### The three remaining UNKNOWNs

All concern production data; none blocks fixture work.

1. **Is 2% + 18% contractual or per-method?** The fixtures are flat
   across all four methods; real Razorpay pricing differs by method.
2. **Status domains.** Each status column has exactly one value in the
   fixtures. What else appears in real exports, and which values mean
   "do not reconcile this row"?
3. **Nullability.** Nothing is null in the fixtures. Which columns can
   actually be blank determines whether a loader rejects a row or
   buckets it as unreconciled.

---

## 4. Build history

Twenty-seven commits. Documentation and correctness work came before
any code — the data model was written and the formula corrected before
a single loader existed.

### Groundwork (`1e77549` … `00bc151`, 12 commits)

**`1e77549` `chore: add Python gitignore`** — `.gitignore` first, before
anything could be staged by accident.

**`f4be0d6` `docs: add project brief, working rules, and stage prompts`**
— baseline of `CLAUDE.md`, `README.md`, `stage-prompts.md`.

**`9f7e017` `test: add labelled 130-order reconciliation fixtures`** —
the four ledgers plus `ground_truth.csv`, moved out of the repo root.
Verified byte-identical after the move by MD5.

**`29373e9` `docs: forbid src/ from reading the eval answer key`** — the
rule that makes every later accuracy number meaningful, added to
CLAUDE.md §11 and §13 before any detection logic existed.

**`0f8d7ee` `chore: ignore all files in data/ except the README`** — the
`data/*.csv` rule left non-CSV exports stageable. Changed to `data/*`
plus a negation. *Verified rather than asserted:* `git check-ignore -v`
on `.xlsx`, `.json` and `.csv` probes, plus `git add -n` proving only
the README was stageable.

**`b334d73` `fix: correct expected payout for missing-payment ground
truth rows`** — see §5.

**`0dc74c2` `docs: add data model spec`** — 247 lines, every fact
measured. *Verified:* the three identities above, cardinality, the 0-paise
formula agreement, the negative-settlement count, the UTR duplication.

**`00bc151` `docs: correct settlement formula to match measured data`** —
the README's identity subtracted `refunds` and `chargebacks`, which no
ledger records. Corrected to `payment − fee − gst_on_fee`.

### Stage 1 — scaffold (`8bb65af`)

Package tree, `config.py` with `TOLERANCE_PAISE = 100` and
`TIMEZONE = "Asia/Kolkata"`, `requirements.txt`.

*Verified:* `config.py` imports and yields the expected values; all five
`src` packages import. *Failure found:* the timezone constant could not
be resolved at all — see §5.

**Judgement call:** `config.py` at the repo root rather than under
`src/`, matching how CLAUDE.md §8 and the stage prompt both refer to it.
Alternative was `src/config.py`; rejected because it would have
contradicted two existing documents.

### Stage 2 — loaders (`6fb087e`, 36 tests)

One loader per ledger over a shared reading policy in `_base.py`:
`dtype=str` on read, one explicit date format localised to
`config.TIMEZONE`, amounts parsed to signed `int64` paise **without
rescaling**.

*Verified:* dtypes on the real fixtures; exact fixture values on all four
ledgers; `pay_00008` stays at `-122433` with 12 negative payouts
surviving; `test_every_documented_column_is_required` drops **each**
documented column in turn across all four ledgers and asserts
`MissingColumnError` every time.

**Judgement call:** extra columns beyond the documented schema are
dropped so downstream sees one stable shape. Alternative was carrying
them through or erroring. Documented and tested rather than silent.

### Stage 3 — matching engine (`82c74d9`, 14 tests)

Joins on `payment_id` only. Returns `reconciled` plus `unreconciled`,
where every row names its source ledger and why it could not be placed.

The invariant is **per-ledger**, not global: each reconciled row consumes
exactly one row from each of the four files, so

```
len(ledger) == len(reconciled) + len(unreconciled[source == ledger])
```

must hold four times over, else `RowConservationError`.

*Verified:* 127 reconciled, 3 unreconciled, conservation holding on all
four ledgers; `test_match_is_unaffected_by_settlement_dates` reverses
every `settled_at` and asserts an identical match.

**Judgement call:** added an `order_id_mismatch` check beyond the four
required scenarios. `payments.order_id` is redundant with
`orders.payment_id`; rather than dropping it, it cross-checks the join.
Closes a silent-wrong-join path.

### Stage 4 — refunds and chargebacks (`da6db79`, then `d0f4717`)

A blocking question came first: nothing in the four ledgers separates a
large refund from a large shortfall. Rather than guess, the analysis was
put to the user with three options and measured evidence. The chosen
rule: a magnitude threshold at 20% of the captured payment, with
chargebacks excluded first by their arithmetic signature.

**Explicitly rejected alternative:** keying on "is the shortfall an exact
whole-percent slice of the payment", which separates the fixture set
perfectly. Rejected because it is a fingerprint of the generator, not a
property of refunds — it would score 1.000 here and collapse on real
data.

*Verified:* the three detectors partition every underpayment — union
equals all 28, pairwise intersections empty.

`d0f4717` then moved the high-confidence boundary off 0.25 — see §5.

### Stage 5 — shortfalls, missing payments, overpayments (`40b429f`)

`detect_settlement_shortfalls` **replaced** the stage 4
`unexplained_negative_delta` placeholder rather than running beside it;
keeping both would emit two findings per order and double-count.

`detect_missing_payments` reads `unreconciled`, not `reconciled` — those
orders never join past the first link — and takes `orders` separately for
the gross.

`detect_overpayments` closed a silent gap: every other detector gates on
`delta < -TOLERANCE`, so an excess credit produced **no finding at all**.
The user was asked before it was built, per the stage prompt.

### Stage 7 before Stage 6 — deliberate reordering

The user ordered the eval harness **before** the agent layer, to
establish a rules-only baseline to measure the agent against. This was
correct and immediately productive: it revealed that the baseline was at
1.000 and therefore useless as a baseline (§5), which prompted the hard
fixture set. Had stage 6 come first, the agent would have been built
against a target it could only damage.

### Stage 7 — eval harness (`53798b0`, 11 tests)

The only file permitted to read `ground_truth.csv`. Reports precision,
recall and F1 per type plus two distinct overall figures: **match rate**
(ID-chain coverage) and **classification accuracy** (label correctness,
counting correctly-unflagged clean orders as correct).

`tests/test_eval.py` pins the scoring maths against synthetic labels,
including that a wrong label costs both a false positive *and* a false
negative.

### Hard fixture set (`bb2398f`, `b171e1f`)

40 orders built to break the rules on purpose. `run_eval.py` now derives
which types to score from each set's own answer key, so
`settlement_excess` is reported-not-scored on easy and scored on hard
with no special case.

`b171e1f` committed the generator. *Verified:* run from two different
working directories, `git status` empty both times — byte-identical
output.

### Stage 6 — agent layer (`7c33ec4` prep, `63f3080`, 29 tests)

`7c33ec4` first fixed the confidence metric (§5), because confidence was
to be the routing signal and it was measured to run backwards.

The agent receives finding + ledger facts, returns label, confidence and
one sentence. Routing sends only medium/low confidence. An override
requires **high** confidence — see §5.

*Verified:* 43 live API calls, responses cached to `.llm_cache/` keyed by
model + prompt version + prompt text. A re-run reports `43 hit / 0 miss`.

### Stage 8 — report (`64b8b5a`, 20 tests)

Groups by anomaly type, orders groups and rows by rupee impact
descending, leads with total exposure. **Exposure and surplus are never
netted** — summing them would let a large overpayment mask a large
shortfall.

Added `src/main.py`, the CLI entry point the README had documented but
which did not exist.

### Stage 9 — dashboard (`93c73ac`, 36 tests)

Read-only Streamlit viewer. Logic in `data.py` (no Streamlit import, so
testable without a server), rendering in `app.py`.

*Verified:* uvicorn bound, HTTP 200, `/_stcore/health` → `ok`, no errors
in the log; Streamlit's own `AppTest` harness executed the script with
**0 exceptions**, 31 rows, correct columns, correct default sort. The
no-report state was verified by moving the CSV away and re-running: 0
exceptions, 0 dataframes, the command shown.

### Tags

| Tag | Commit | Contents |
|---|---|---|
| `v0.2` | `64b8b5a` | rules + agent + report |
| `v0.3` | `beeb5a4` | + dashboard; accuracy re-measured, unchanged |

---

## 5. What broke

Six incidents. Each is recorded with the mathematics, not a summary.

### 5.1 The timezone constant could not be resolved (stage 1)

**Symptom.** `config.TIMEZONE = "Asia/Kolkata"` imported fine, but
loading it raised:

```
zoneinfo._common.ZoneInfoNotFoundError: 'No time zone found with key Asia/Kolkata'
```

**Root cause.** Windows ships no system tz database. Python's stdlib
`zoneinfo` reads one from disk and finds nothing:

```
zoneinfo.TZPATH: ()
available_timezones(): 0
```

Zero timezones available — not a missing entry, an empty database.

**Why it mattered.** The constant was a value that *looked* correct and
could not be used. It would have surfaced as a Stage 2 loader crash, far
from its cause.

**Fix.** `tzdata` added to `requirements.txt` with the measurement in a
comment. After installation:

```
available_timezones(): 598 keys
ZoneInfo(config.TIMEZONE) -> Asia/Kolkata
2026-02-01 16:08:00+05:30   (utcoffset 5:30:00)
```

**Why this fix.** The alternative was to drop `zoneinfo` for pandas'
tz handling, which bundles its own database. Rejected: pandas 3.0
dropped `pytz` and declares `tzdata` as a hard dependency anyway, so the
explicit line documents a real requirement rather than relying on a
transitive one that a future pandas could drop.

**Correction to an earlier claim.** When adding it I said pandas bundles
`pytz` so it "would probably have worked anyway". That was wrong for
pandas 3.0 — `pytz` is not installed. Corrected in the session and
recorded here.

### 5.2 Confidence measured threshold distance, not certainty (`7c33ec4`)

**Symptom.** Confidence was to be the agent routing signal. Measured
against the hard set's answer key, it ran backwards:

```
confidence   correct  wrong  total  P(wrong)
high              12      5     17     0.294
medium             2      5      7     0.714
low                2      0      2     0.000
```

**The low-confidence bucket was 100% correct. Five of the ten errors were
marked high.**

**Root cause — the mathematics.** Confidence was computed from the
shortfall ratio's distance from the 20%/25% thresholds. But the
*threshold* is the error source. A chargeback carrying a fee other than
₹500 produces a shortfall of

```
shortfall = payment + fee
ratio     = (payment + fee) / payment  ≈ 1.05
```

— enormously above 0.25, so the refund rule fired at maximum confidence
**on a chargeback**. Distance from a line says nothing about whether the
line belongs there, and the line is exactly what these rules get wrong.

**Consequence for routing.** At the not-low bar:

```
low only     sends  2/26, catches  0/10 errors (0%)
low+medium   sends  9/26, catches  5/10 errors (50%)
everything   sends 26/26, catches 10/10 errors (100%)
```

Nothing between useless and send-everything.

**Fix.** Confidence became a property of the *detector*, not the row:

- `chargeback`, `payment_not_received`, `settlement_excess` → **high**.
  Each is an arithmetic identity that matches within tolerance or does
  not; there is no continuum to be wrong about.
- `refund_not_reflected`, `settlement_shortfall` → **never high**.
  Medium clear of the boundary band, low inside it.

After:

```
confidence   correct  wrong  total  P(wrong)
high               6      0      6     0.000
medium             9     10     19     0.526
low                1      0      1     0.000

route low+medium: 20/26 sent, catches 10/10 errors (100%)
```

**Classification did not change** — easy stayed 1.000, hard stayed 0.615.
Only the confidence field moved.

**Why this fix over the alternative.** The alternative signal considered
was routing by *rule provenance*: send everything the threshold decided,
never send the three sharp types. That also catches 100% of errors. It
was rejected as the primary mechanism because confidence is a field a
human reads — a field saying "high" on five wrong answers misleads a
reviewer exactly as it misleads a router. Fixing the field fixed both.

### 5.3 The 0.25 cluster point (`d0f4717`)

**Symptom.** With the boundary at 0.25, one of fifteen refunds came back
medium instead of high: `ord_00026`.

**Root cause — the mathematics.** The generator built refunds as exact
percentage slices, rounding to integer paise:

```
payment          = 5259413
round(payment × 0.25) = 1314853    ← the stored shortfall
exact ratio      = 1314853 / 5259413
                 = 0.2499999524661782598172077378
float ratio      = 0.24999995246617826
ratio >= 0.25    = False
```

An exact 25% refund computes to `0.2499999…` because `payment × 0.25`
was rounded *down*. The boundary sat precisely on a cluster point in the
data, so which side a true 25% refund landed on was decided by rounding
noise. Four of the five 25% refunds landed above; this one below.

**Fix.** Boundary moved to 0.22, documented as a narrow margin *above*
`REFUND_THRESHOLD_PCT` rather than an independent value, so it can never
coincide with a common refund percentage (25, 30, 50, 100).

```
ord_00026 ratio = 0.2499999525  ->  high   (was medium)
lowest real refund ratio = 0.250000
margin above the new 0.22 boundary = 0.030000
```

**Why this fix.** The alternative was rounding the ratio before
comparing. Rejected: it hides the problem for this dataset while leaving
the boundary on the cluster point, so any other rounding convention
resurfaces it. Moving the line off the cluster is structural.

### 5.4 Ground truth imputed a fee on payments that never happened (`b334d73`)

**Symptom.** Discovered while implementing the missing-payment rule. The
answer key's `expected_amount_paise` for the three missing-payment rows
did not equal `orders.gross_amount_paise`:

```
ord_00006: gross=1475793  gt_expected=1440964  diff=34829
ord_00065: gross=1983086  gt_expected=1936285  diff=46801
ord_00067: gross=5383503  gt_expected=5256452  diff=127051
```

**Root cause — the mathematics.** Every difference equals
`round(gross × 0.02 × 1.18)` exactly:

```
round(1475793 × 0.02 × 1.18) = 34829   ✓
round(1983086 × 0.02 × 1.18) = 46801   ✓
round(5383503 × 0.02 × 1.18) = 127051  ✓
```

The fixture generator applied the 2% + 18% deduction uniformly across
all orders, including three where **no payment ever reached Razorpay**
and therefore no commission was ever charged.

**Why it mattered.** The answer key was wrong, not the rule. Had this
gone unnoticed, the detector would have been "corrected" to match a key
that understated the merchant's loss by 2.36% on those rows — and doing
so would have meant shaping detection logic to the answer key, which
§11 forbids outright.

**Fix.** Three rows in `ground_truth.csv` corrected:

```
-ord_00065,...,1936285,0,-1936285,...
+ord_00065,...,1983086,0,-1983086,...
-ord_00067,...,5256452,0,-5256452,...
+ord_00067,...,5383503,0,-5383503,...
```

*Verified after:* still 31 rows with the same type split;
`actual − expected == delta` on all 31; all 3 missing-payment rows now
equal `orders.gross`; the 28 rows with payments still satisfy
`payment − total_deduction`.

**How it was caught.** By flagging a divergence between a rule and the
key *before* changing either, and asking rather than assuming the rule
was wrong. The initial handling documented the divergence in
`docs/data-model.md` and forbade tuning toward the key; the user
identified it as a generator bug and the key was fixed instead.

### 5.5 The agent regressed the easy set (during stage 6)

**Symptom.** First live agent run, override bar at "not low":

```
                easy     hard
micro F1       0.968    0.692     (rules-only: 1.000 / 0.615)
```

Easy fell from 1.000. Under the user's explicit instruction and
CLAUDE.md §11 the work stopped and was not committed.

**Root cause.** One order moved: `ord_00026`, `refund_not_reflected` →
`settlement_shortfall`. The agent's own words:

> "The shortfall is exactly 25.0% of the captured payment — a
> suspiciously clean fraction for a real customer refund, which by
> definition should be an arbitrary amount tied to a specific return."

The reasoning is correct about the real world and exactly backwards for
this data, **and the prompt caused it**. The system prompt asserted
*"Real refunds are arbitrary amounts."* In these fixtures, round
percentages *are* the refund signature. The model reasoned validly from a
false premise that the prompt supplied.

It is the same `ord_00026` from §5.3 — the exact-25% refund at
`0.2499999525`, which is why it sits at medium confidence and was routed
at all. The most fragile order in the set was the one that broke.

**Fix.** The override bar was raised from "not low" to **high**. The
evidence:

| Override | Confidence | Outcome |
|---|---|---|
| `ord_h0025` refund → chargeback | high | FIXED |
| `ord_h0026` refund → chargeback | high | FIXED |
| `ord_h0027` refund → chargeback | high | FIXED |
| `ord_h0032` refund → shortfall | medium | BROKE |
| `ord_00026` refund → shortfall | medium | BROKE |

Every correct override was confident; every damaging one was hedged.

**Why this fix over the alternative.** The alternative was deleting the
"real refunds are arbitrary amounts" sentence from the prompt. Rejected
by the user as the primary fix, and rightly: it would have been tuning
the prompt against the answer key, and it fixes one sentence rather than
the class of problem. The confidence gate is structural — it discards
hedged overrides regardless of what caused them.

**Result after:** easy back to 1.000, hard up to 0.731. Both breaks gone,
all three fixes retained.

**Side effect handled.** Raising the gate made a prompt sentence false
("say low and your override will be discarded"). It was replaced with an
instruction to report genuine certainty, and **the threshold is
deliberately not named** — telling a model which value unlocks an
override invites it to report that value instead of its actual
confidence, destroying the signal the gate depends on. A test asserts
`"high"` appears in the prompt only inside the JSON schema line.

### 5.6 grep-versus-AST false positives (recurring)

**Symptom.** Three times, a `grep`-based structural check reported a
violation that did not exist:

1. `grep -rn "ground_truth" src/` → flagged `overpayments.py`, which
   only *mentions* the answer key in a docstring explaining that the
   eval must report `settlement_excess` separately.
2. `grep -rnE "from src\.(matching|detectors|agent)" src/dashboard/` →
   flagged `app.py`, whose module docstring states the constraint.
3. `tests/test_dashboard.py::test_dashboard_never_reads_the_answer_key`
   failed on its own module's docstring.

**Root cause.** A file that *documents* a prohibition contains the
prohibited string. Text search cannot distinguish code from prose about
code, and the better a module documents its own constraint, the more
likely it is to trip its own check.

**Fix.** Structural checks now parse the AST. `_imported_modules()`
walks `ast.Import` / `ast.ImportFrom` nodes; the answer-key check walks
`ast.Constant` string nodes with docstrings excluded via
`_docstring_nodes()`. Actual imports in `src/dashboard/`:

```
app.py : sys, pathlib, pandas, streamlit, src.dashboard.data
data.py: pathlib, pandas
```

**Why this fix.** Narrowing the grep pattern (excluding comment lines,
say) was the alternative. Rejected: it is a heuristic that degrades as
prose changes, whereas the AST distinguishes an import from a mention by
construction.

**Note on the security audit.** The same lesson applied. The
high-entropy scan flagged four locations; all four were inspected and
proved benign (shields.io badge URLs, long Python identifiers). The
decisive check was not a pattern at all — it read the live key from
`.env` and searched for that literal string across all 210 objects in
the full history. Result: `NONE`.

---

## 6. Evaluation methodology

### Two labelled sets

**`tests/fixtures/` — "easy", 130 orders, 31 anomalies.** The regression
baseline. 15 refunds, 5 chargebacks, 8 shortfalls, 3 missing payments.

**`tests/fixtures/hard/` — "hard", 40 orders, 26 anomalies.** Built to
break the rules on purpose, generated deterministically by
`tests/gen_hard.py`. Composition: 14 refunds (5 at arbitrary amounts
above threshold, 3 below it, 2 summing from two separate refunds, 2
combined with a shortfall, 2 whole-percent controls), 5 chargebacks (3
with a non-₹500 fee, 2 controls), 3 shortfalls (2 above the threshold,
1 control), 2 overpayments, 2 missing payments.

### Why the hard set exists

The rules scored **1.000 on every type** on the easy set. That left the
agent layer no headroom: every outcome was neutral or a regression, and
§11's gate would block any commit that moved a number. The floor was at
the ceiling.

### Why 1.000 on the easy set is a statement about the fixtures

Two reasons, both measured:

1. **The rules were written by inspecting those same four ledgers.**
   The 20% threshold was chosen after looking at the ratio distribution.
2. **The set contains no case the threshold can get wrong.** Measured
   on the easy set:

```
largest shortfall : ord_00011 at 0.1818
smallest refund   : ord_00026 at 0.2500
empty band width  : 0.0682
```

A 6.8-point band with nothing in it. One production export with a 22%
refund lands inside it. Two of five detector branches
(medium-confidence refund, overpayment) have **no instance in the easy
set at all** and are exercised only by hand-built fixtures.

### The answer-key rule

`evals/run_eval.py` is the only file permitted to read
`ground_truth.csv` (CLAUDE.md §11, §13). No loader, matcher or detector
may reference it. If detection logic needs the key to work, every
accuracy number it produces is meaningless.

Verified at `beeb5a4`:

```
$ grep -rnE "(open|read_csv|import).*ground_truth" src/ evals/ --include=*.py
(no matches in src/)
```

Which types are scored is **derived per set from that set's own answer
key**, so `settlement_excess` — unlabelled on easy, labelled on hard — is
handled in both without a special case, and is never counted as a false
positive where no labels exist.

---

## 7. Results

Produced by `python evals/run_eval.py` and
`python evals/run_eval.py --agent` at `beeb5a4`. The agent run reported
`cache: 43 hit / 0 miss` — reproduced, not re-sampled.

### Rules only

```
SET: EASY   130 orders | 31 labelled anomalies | 31 findings
anomaly type              sup  pred   TP   FP   FN     prec   recall       F1
refund_not_reflected       15    15   15    0    0    1.000    1.000    1.000
chargeback                  5     5    5    0    0    1.000    1.000    1.000
settlement_shortfall        8     8    8    0    0    1.000    1.000    1.000
payment_not_received        3     3    3    0    0    1.000    1.000    1.000
MICRO AVERAGE              31    31   31    0    0    1.000    1.000    1.000
match rate 0.977 (127/130)   classification accuracy 1.000 (130/130)

SET: HARD    40 orders | 26 labelled anomalies | 26 findings
anomaly type              sup  pred   TP   FP   FN     prec   recall       F1
refund_not_reflected       14    14    9    5    5    0.643    0.643    0.643
chargeback                  5     2    2    0    3    1.000    0.400    0.571
settlement_shortfall        3     6    1    5    2    0.167    0.333    0.222
payment_not_received        2     2    2    0    0    1.000    1.000    1.000
settlement_excess           2     2    2    0    0    1.000    1.000    1.000
MICRO AVERAGE              26    26   16   10   10    0.615    0.615    0.615
match rate 0.950 (38/40)     classification accuracy 0.750 (30/40)
```

### With the agent layer

```
SET: EASY    23 findings routed | 23 confirmed | 0 overridden
MICRO AVERAGE              31    31   31    0    0    1.000    1.000    1.000
match rate 0.977             classification accuracy 1.000 (130/130)

SET: HARD    20 findings routed | 17 confirmed | 3 overridden
anomaly type              sup  pred   TP   FP   FN     prec   recall       F1
refund_not_reflected       14    11    9    2    5    0.818    0.643    0.720
chargeback                  5     5    5    0    0    1.000    1.000    1.000
settlement_shortfall        3     6    1    5    2    0.167    0.333    0.222
payment_not_received        2     2    2    0    0    1.000    1.000    1.000
settlement_excess           2     2    2    0    0    1.000    1.000    1.000
MICRO AVERAGE              26    26   19    7    7    0.731    0.731    0.731
match rate 0.950             classification accuracy 0.825 (33/40)

  ord_h0025: refund_not_reflected -> chargeback  [FIXED]
  ord_h0026: refund_not_reflected -> chargeback  [FIXED]
  ord_h0027: refund_not_reflected -> chargeback  [FIXED]
```

### Consolidated

| Metric | easy rules | easy agent | hard rules | hard agent |
|---|---|---|---|---|
| refund_not_reflected F1 | 1.000 | 1.000 | 0.643 | **0.720** |
| chargeback F1 | 1.000 | 1.000 | 0.571 | **1.000** |
| settlement_shortfall F1 | 1.000 | 1.000 | 0.222 | 0.222 |
| payment_not_received F1 | 1.000 | 1.000 | 1.000 | 1.000 |
| settlement_excess F1 | n/a | n/a | 1.000 | 1.000 |
| micro recall | 1.000 | 1.000 | 0.615 | **0.731** |
| micro F1 | 1.000 | 1.000 | 0.615 | **0.731** |
| classification accuracy | 1.000 | 1.000 | 0.750 | **0.825** |
| match rate | 0.977 | 0.977 | 0.950 | 0.950 |

### What the agent bought, precisely

Micro F1 on hard: **0.615 → 0.731**. The entire gain is one failure
class — chargebacks with a fee other than ₹500, **0.571 → 1.000** — which
the deterministic rules cannot see, because their signature assumes a
fixed penalty. The agent changed **nothing** on the easy set: 23 routed,
23 confirmed, 0 overridden.

`settlement_shortfall` F1 is **unchanged at 0.222**. The agent declines
to guess at the refund/shortfall boundary. §8 shows that is correct.

**On both sets, in both modes: `missed entirely: none` and
`flagged but clean: none`.** Every anomaly is detected and nothing clean
is ever flagged. All error is classification, never detection — which
matters given recall is the priority metric.

---

## 8. Honest exception list

Seven orders on the hard set carry the wrong label after the agent pass.
They are unchanged from the rules-only run.

| Order | Truth | Predicted | Shortfall ratio | Shortfall (paise) |
|---|---|---|---|---|
| `ord_h0022` | refund_not_reflected | settlement_shortfall | 0.0800 | 321,904 |
| `ord_h0020` | refund_not_reflected | settlement_shortfall | 0.1200 | 410,640 |
| `ord_h0033` | refund_not_reflected | settlement_shortfall | 0.1421 | 264,983 |
| `ord_h0021` | refund_not_reflected | settlement_shortfall | 0.1500 | 297,360 |
| `ord_h0031` | refund_not_reflected | settlement_shortfall | 0.1728 | 397,533 |
| `ord_h0024` | settlement_shortfall | refund_not_reflected | 0.2800 | 731,836 |
| `ord_h0023` | settlement_shortfall | refund_not_reflected | 0.3500 | 512,120 |

Five refunds fall below the 0.20 threshold; two shortfalls sit above it.

### Why this is an information problem, not a tuning problem

The obvious response is to move the threshold. **It does not work, and
this was tested rather than assumed.** Sweeping every candidate
threshold across both sets combined:

```
threshold-decided orders: 40 (29 refunds, 11 shortfalls)
refund ratio range   : 0.0800 .. 1.0000
shortfall ratio range: 0.0020 .. 0.3500
OVERLAP: refunds below the largest shortfall = 19

 threshold  errors   easy   hard
    0.0309       3      1      2      <- best possible
    0.0800       3      1      2
    0.0305       4      2      2
    0.1200       4      1      3
    0.0260       6      3      3

BEST POSSIBLE threshold 0.0309: 3 errors (easy 1, hard 2)
```

**The two classes overlap on this feature.** Refund ratios span
0.08–1.00; shortfall ratios span 0.002–0.35. **Nineteen refunds sit below
the largest shortfall.** They interleave:

```
0.1200 refund   0.1421 refund   0.1500 refund   0.1728 refund
0.2124 refund   0.2378 refund   0.2573 refund   0.2687 refund
0.2800 SHORTFALL
0.3000 refund   0.3163 refund   0.3340 refund
0.3500 SHORTFALL
```

No threshold on this axis separates them. The best achievable is **3
errors, not 0** — and reaching it would mean fitting the constant to the
answer key, which §11 forbids and which would move the overfitting
rather than remove it. The current 0.20 gives 7 errors; the theoretical
optimum gives 3. Neither is a solution.

The agent cannot close it either, and correctly does not try. Asked
about `ord_h0032` (a comparable case it did resolve conservatively), it
said a plain shortfall was *"at least equally plausible"* — an accurate
description of a case with no distinguishing evidence.

### What would actually close it

**A refund ledger.** A fifth file recording refunds — refund ID, payment
ID, amount, timestamp — turns the whole class from inference into a
join. A shortfall with a matching refund row *is* a refund; one without
*is* a shortfall. The ambiguity disappears entirely, because it was
never a modelling problem — the information simply is not in the four
files.

Failing that, weaker signals that would help but not resolve:
settlement-narration text from the bank, refund webhook events, or a
Razorpay refunds API pull.

### One further honest caveat

Two hard-set orders combine a refund *and* a separate shortfall. For
those, even a correct type label is not a fully correct answer: the delta
conflates two events, so the reported amount is wrong regardless of which
label wins. The eval scores types, not amounts, so these can pass while
still being wrong. Documented in `tests/fixtures/hard/README.md`.

---

## 9. Engineering practices

`CLAUDE.md` defines fifteen rules. Four did concrete work.

### Ask before committing (§3)

Every commit in this history was shown as a diff and approved before
landing. This caught real problems rather than being ceremony:

- The **`ord_00026` regression** (§5.5) surfaced at the diff stage, was
  reported with the agent's own reasoning, and the fix was chosen by the
  user rather than by the implementer.
- The **overpayment question** in stage 5 was put to the user before any
  code was written, because it changed whether a fifth detector existed.
- The **refund/shortfall rule** in stage 4 was a blocking question. The
  option that scored perfectly on the fixtures was explicitly presented
  as overfitting and rejected by the user.

### The regression gate (§11)

*"Before any commit that touches detection logic, run the eval. If
recall on any existing anomaly type drops, do not commit."*

This fired once, decisively. The stage 6 agent at the not-low override
bar dropped easy `refund_not_reflected` recall from 1.000 to 0.933. The
commit was blocked, the cause was investigated, the bar was raised, and
the eventual commit held easy at 1.000 while improving hard. **Without
the gate, a change that improved the headline hard number by 0.077 would
have silently damaged the baseline.**

### One commit per logical change (§3)

Applied even when inconvenient:

- The five stage checkboxes were ticked in their **own** commit
  (`c3998aa`) rather than folded into stage 7's.
- The `.gitignore` tightening (`0f8d7ee`) was separate from the `data/`
  README that motivated it (`087b3b5`).
- When the v0.3 accuracy rows were requested and the table was **already
  correct**, no commit was manufactured — the rows had landed with stage
  6, the eval was re-run to confirm, and the tag was applied directly.

### Never invent data (§6) and verify before claiming done (§12)

- The data model was written by reading actual header rows and measuring
  actual identities — hence "verified across 127/127" rather than
  "should hold".
- The `tzdata` failure (§5.1) was found *because* §12 required running
  the thing rather than asserting it worked.
- The hard fixture generator's reproducibility was proven by running it
  from two directories and checking `git status`, not by reasoning about
  determinism.
- The dashboard was verified with Streamlit's `AppTest` harness because
  an HTTP 200 only proves the shell loaded.

### Where the practices were imperfect

Stated plainly: the stage checkboxes went un-ticked for five
consecutive stages before anyone noticed, and were fixed in a catch-up
commit. §14 says to update them as each stage lands; that was not done
until prompted.

---

## 10. What's next

### Column mapping with LLM-assisted schema inference

The loaders currently require exact column names from
`docs/data-model.md` and raise `MissingColumnError` otherwise. Real
merchant exports will not match: `order_id` may be `Order ID`,
`order_ref`, or `merchant_order_no`, and amounts may be in rupees rather
than paise.

This is a genuinely good fit for the agent layer — it is a
classification problem over strings, not arithmetic. The design that
preserves the determinism boundary: the LLM proposes a **mapping**
(source column → documented column, plus a unit declaration), a human
approves it once, the mapping is stored as a config file, and the
deterministic loaders then run against the mapping. The LLM never sees a
value, only headers and a sample, and never participates in a
reconciliation run.

Open question this must answer first: UNKNOWN #3 from §3 — nullability
in real exports determines whether an unmapped column is a hard error or
a bucketed row.

### A refund ledger

The single highest-value addition, for the reasons in §8. It collapses
the largest remaining error class from inference to a join. It also
retires `REFUND_THRESHOLD_PCT` and `REFUND_NEAR_THRESHOLD_PCT` entirely,
removing two of the three heuristic constants that `config.py` currently
warns are "tuned on synthetic fixtures, not contractual values".

### Multi-PSP fee structures

`CHARGEBACK_FEE_PAISE = 50000` is a flat constant, and the hard set
already demonstrates what happens when it is wrong: chargeback F1 falls
to 0.571 under the rules alone. Real fees vary by payment method, card
network, merchant contract, and PSP.

Two directions, in order of robustness:

1. **Read the fee rather than assume it.** If a fee ledger records the
   chargeback penalty as its own line, the signature becomes exact and
   the constant disappears. This is the same shape as the refund-ledger
   fix: replace inference with data.
2. **Per-PSP config profiles.** Where the fee genuinely is not recorded,
   a per-merchant, per-method fee table keyed off `payments.method` at
   least makes the assumption explicit and auditable rather than global.

Answering UNKNOWN #1 from §3 — whether 2% + 18% is contractual or
per-method — is a precondition for either.

---

## Appendix: reproducing every number in this report

```bash
python -m pytest -q                                      # 193 tests
python evals/run_eval.py                                 # rules-only, both sets
python evals/run_eval.py --agent                         # + agent, both sets
python -m src.main --data tests/fixtures --out reports/  # easy report
python -m src.main --data tests/fixtures/hard --out reports/
python tests/gen_hard.py                                 # regenerates hard set, byte-identical
streamlit run src/dashboard/app.py                       # dashboard
```

`--agent` requires `ANTHROPIC_API_KEY` in `.env` (gitignored). Cached
responses in `.llm_cache/` make repeat runs free; delete the directory to
force a fresh billing run.
