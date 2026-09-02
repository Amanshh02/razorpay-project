# AI Finance Controller — Technical Report

**Scope:** first commit (`1e77549`) to `5ee7329`, **38 commits** on
`main`, two tags. **214 tests.**

Every number in this report was produced by a command run against the
repository, not quoted from memory. Where a figure comes from a specific
tool invocation, the invocation is named.

**A note on timing figures.** Wall-clock measurements vary with machine
load. The pipeline over 130 orders has measured a median of **0.136 s**
and **0.189 s** on separate runs of 7 on the same machine. Both are
real; neither is authoritative to three significant figures. Where a
timing appears below, the run that produced it is named. Accuracy
figures do not vary — the pipeline is deterministic, and the agent pass
is served from cache.

---

## Track 04 traceability

Each phrase of the published brief, mapped to where it is satisfied.
Figures were re-measured at `1a33286`.

### The task

> *"Build an agent that closes one finance-ops loop across a 50+ record
> batch of synthetic data, reporting its match rate and the exceptions
> it could not resolve."*

| Brief phrase | Where | Evidence |
|---|---|---|
| "an agent" | `src/agent/` — `63f3080` | LLM classification pass over medium/low-confidence findings. One stateless call per finding, provider-agnostic behind `LLMClient`. **See "where the fit is partial" below.** |
| "closes one finance-ops loop" | `src/main.py` — `64b8b5a` | Ingest → match → detect → classify → report → dashboard. `python -m src.main --data … --out …` runs the whole loop in one command. **Ends at reporting, not remediation** — see below. |
| "50+ record batch" | `tests/fixtures/` — `9f7e017` | **130 orders / 511 ledger rows** across four files. Processed in one pass, nothing sampled. §1, README "Throughput". |
| "of synthetic data" | `tests/fixtures/`, `tests/gen_hard.py` — `9f7e017`, `b171e1f` | Both sets synthetic and labelled. The hard set is regenerable byte-identically from any working directory. |
| "reporting its match rate" | `evals/run_eval.py` — `53798b0` | Reported by name: **0.977** easy (127/130), **0.950** hard (38/40). Distinguished from classification accuracy, which measures a different thing. §8, §9. |
| "the exceptions it could not resolve" | §10; README "Honest exception list" | **7 orders named** with ratios. Threshold sweep proves the classes overlap and the best achievable is 3 errors, not 0. |

### Why now

> *"Verification capacity, not generation speed, is the bottleneck.
> Reconciliation, settlement and forecasting are still done by hand."*

| Brief phrase | Where | Evidence |
|---|---|---|
| "verification capacity … is the bottleneck" | §2; README "Meeting the Track 04 bar" | The deterministic layer is the verifier and is deliberately not an LLM. The eval harness makes the verification itself checkable. |
| "not generation speed" | §2 "How 'no LLM touches a number' is enforced structurally" | Four structural mechanisms, each tested: output schema carries no numeric field; `test_no_amount_is_ever_modified`; SDK confined to one file; the dashboard imports no engine code at module level (§5, stage 10). |
| "still done by hand" | §1 | Rs 481,919.30 exposure across 130 orders, 23.8% of orders carrying a discrepancy. |

### Example direction

> *"Multi-source reconciliation, settlement Q&A agent, forward cash
> forecaster, tax-line matcher."*

**This project is multi-source reconciliation** — four ledgers joined on
an ID chain (§4). The other three directions are not attempted.

### The bar

> *"Throughput plus measured accuracy plus an honest exception list.
> One cherry-picked match proves nothing."*

| Criterion | Where | Measured figure |
|---|---|---|
| **Throughput** | README "Throughput"; `src/matching/engine.py` — `82c74d9` | 130 orders / 511 rows, median **0.136–0.189 s** across two runs of 7 (see the timing note at the top). Cold start 1.27–2.15 s. Per-ledger row conservation asserted **four times** before any result returns; violation raises `RowConservationError`. |
| **Measured accuracy** | §9; README "Measured accuracy" | Per-type P/R/F1, both sets, both modes. Easy micro F1 **1.000**; hard micro F1 **0.615** rules-only, **0.731** with agent. Rules-only path needs no API key. |
| **Honest exception list** | §10; README "Honest exception list" | 7 orders named. Sweep: 29 refunds vs 11 shortfalls, **19 refunds below the largest shortfall**, best achievable **3 errors**. |
| **"One cherry-picked match proves nothing"** | §8; `bb2398f` | Whole-batch results only. Both sets scored in full, reported separately. The adversarial set exists so the numbers are not a self-report; the rules were **deliberately not tuned** to pass it. |

### Where the fit is partial

Stated here rather than left for a reader to discover.

1. **"Agent" is a classification step, not an agentic loop.** One
   stateless call per routed finding — no tools, no loop, no autonomy
   over control flow. This is a deliberate consequence of the
   determinism boundary (§2), not an omission, but a reader expecting
   tool use and multi-step reasoning will not find it.
2. **The loop closes at reporting, not remediation.** Nothing writes
   back, files a dispute, or actions a recovery. Discrepancies are
   identified, classified, costed and displayed; acting on them is a
   human's job.
3. **The adversarial set is 40 orders, under the 50+ bar on its own.**
   The primary batch is 130 and clears it. The 40 is an *additional*
   labelled set, not a second qualifying batch.
4. **The headline number is the weakest evidence.** Easy-set micro F1
   of 1.000 is the figure most likely to be skimmed and the one that
   means least — it is a statement about the fixtures (§8). The hard
   set's 0.615 / 0.731 is the honest measure.
5. **130 orders is not a throughput test.** 688–958 orders/second is real
   and reproducible; it is also measured on a batch that fits in memory
   trivially. Nothing here demonstrates behaviour at 100k orders.
6. **The adversarial set partly reproduces the artifact it was built to
   defeat.** Stage 4 rejected keying refund detection on "is the
   shortfall an exact whole-percent slice of the payment", because that
   is a fingerprint of the fixture generator rather than a property of
   refunds. `tests/gen_hard.py` was then written with **5 of its 14
   refunds constructed as exact percentage slices**:

   ```
   easy: 15 exact whole-percent, 0 arbitrary
   hard:  5 exact whole-percent, 9 arbitrary
     ord_h0020 (12%)  ord_h0021 (15%)  ord_h0022 (8%)
     ord_h0038 (30%)  ord_h0039 (50%)
   ```

   Nine of fourteen are genuinely arbitrary, which is why the set still
   functions as an adversarial test. **No reported figure depends on the
   artifact** — no detector or agent decision keys on the whole-percent
   property, verified by search, so nothing is inflated by its presence.
   But the set is **less adversarial than intended**: a rule keyed on
   the fingerprint would still score 5 of 14 on the set built to defeat
   it, and three of those five (`ord_h0020`, `ord_h0021`, `ord_h0022`)
   are among the seven orders in the exception list — precisely the
   sub-threshold refunds the shipped rule gets wrong.

   **Recorded rather than fixed, as a deliberate scope decision.**
   Regenerating those five as arbitrary amounts would change their
   ratios and therefore every hard-set number in §9, §10 and the README,
   requiring the full measurement chain to be re-run and re-documented
   before the submission deadline. The honest move at this point is to
   state the weakness precisely rather than to change the data and the
   reported results at the same time. See §7.8.

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
4. **The dashboard cannot recompute unless explicitly asked to.**
   Through stage 9 this was absolute: `tests/test_dashboard.py` parsed
   the AST of every file in `src/dashboard/` and asserted no import of
   `matching`, `detectors` or `agent`. Stage 10 added an opt-in "Run
   reconciliation" button, so the claim is now **conditional** — see
   §5, stage 10, for what replaced it and why the trade was made.
   Loading the page still executes no pipeline code.

### Money handling

Integer paise end to end. No float rupees anywhere in the pipeline.
Conversion to rupees happens only at display, in `src/report.py` and
`src/dashboard/data.py`, and no converted value is read back. Amounts
are never compared with `==`; every comparison goes through
`config.TOLERANCE_PAISE = 100`.

---

## 3. What AI and machine learning are actually doing here

Stated precisely, because "AI finance controller" invites a reading this
project does not support.

### What is not here

**No model was trained.** There are no weights in this repository, no
fitting step, no learning from data, no gradient anywhere. Nothing
observes the fixtures and adjusts a parameter. Verified:

```
$ grep -rniE "\.fit\(|sklearn|torch|tensorflow|xgboost|train_test_split|model\.train" src/ evals/ tests/
  no training/fitting API used anywhere in the project
```

The three tunable constants in `config.py` —
`CHARGEBACK_FEE_PAISE = 50000`, `REFUND_THRESHOLD_PCT = 0.20`,
`REFUND_NEAR_THRESHOLD_PCT = 0.22` — were set by a human reading a ratio
distribution and are documented in the file as *"heuristics tuned on
synthetic fixtures, not contractual values"*. **That is a person
choosing a number, not a model learning one.** Calling it machine
learning would be false.

### What is here

Two things, and they are different in kind:

1. **Deterministic rule-based detection.** Five detectors over pandas.
   Each is an arithmetic predicate — an identity matched within
   tolerance, or a ratio compared to a constant. Fully reproducible;
   the same input always gives the same output.
2. **Stateless calls to a pre-trained LLM** for classification and
   explanation. No fine-tuning, no embeddings, no retrieval, no vector
   store. The model is used as it ships.

### The LLM call surface, exactly

Measured from the live code:

| Property | Value |
|---|---|
| Model | `claude-sonnet-4-6` |
| Calls per full eval run, cold cache | **43** (23 easy + 20 hard) |
| Calls per run, warm cache | **0** — `cache: 43 hit / 0 miss` |
| `max_tokens` | 4000 |
| System prompt | 2,367 characters, one static string, `PROMPT_VERSION = 2` |
| Tools passed | **none** — no `tools`, `tool_choice` or `tool_runner` parameter |
| Conversation state | none; each call is independent |
| Routed | only findings at `medium` or `low` confidence |

**What the prompt contains:** the domain (four ledgers, the settlement
identity, the five anomaly types), an explicit statement that the rules'
threshold is their known weak point, an instruction to defer to the
rule absent a specific stated reason, and the finding itself — its rule
label, rule confidence, rule reasoning, and the order's ledger facts
with every amount **pre-computed in Python**. The model is given
arithmetic; it is never asked to perform any.

**Response schema:** `{"label", "confidence", "explanation"}` — one of
five labels, one of three confidence levels, one sentence. Parsed with
`json.loads` behind a regex; anything malformed keeps the rule's label
and is recorded as `unparseable`.

**Caching:** responses are written to `.llm_cache/` keyed by
SHA-256 of `(model, prompt_version, system_prompt, user_prompt)`. A
re-run is free and byte-identical. Editing the prompt changes the key
and correctly invalidates everything.

### What the LLM is structurally prevented from doing

- **Touching a number.** Its response schema has no numeric field.
  `classify()` copies `expected_amount_paise`, `actual_amount_paise` and
  `delta_paise` through untouched, and a test asserts frame equality
  before and after — including a variant that forces an override on
  every routed row.
- **Deciding what runs next.** No tools, no loop. `classify()` drives
  the iteration and calls the model once per finding.
- **Overriding a confident rule.** High-confidence findings are never
  routed. A disagreement is applied only at `high` confidence;
  otherwise the rule's label and confidence stand.
- **Reaching the answer key.** `ground_truth.csv` is readable only by
  `evals/run_eval.py`.

### What it actually contributes, measured

**Hard-set micro F1: 0.615 → 0.731.** The entire gain is one anomaly
class — chargebacks carrying a fee other than ₹500 — going 0.571 →
1.000. On the easy set it routed 23 findings, confirmed 23, and changed
nothing. At the refund/shortfall boundary it changed nothing, correctly
(§10).

So: **the LLM improved one of five anomaly classes on one of two fixture
sets, and left everything else where the rules put it.** That is a real
contribution to a real weakness, and it is not the system reconciling
the books. The deterministic layer does that.

---

## 4. Data model

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

## 5. Build history

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
truth rows`** — see §7.

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
be resolved at all — see §7.

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

`d0f4717` then moved the high-confidence boundary off 0.25 — see §7.

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
1.000 and therefore useless as a baseline (§7), which prompted the hard
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

`7c33ec4` first fixed the confidence metric (§7), because confidence was
to be the routing signal and it was measured to run backwards.

The agent receives finding + ledger facts, returns label, confidence and
one sentence. Routing sends only medium/low confidence. An override
requires **high** confidence — see §7.

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

The absolute isolation described here held until stage 10, which
deliberately relaxed it. See below.

### Stage 10 — live progress and charts (`5ee7329`, 21 new tests)

Two additions, one of which changed an architectural guarantee.

**Live progress.** `src.main.run` gained an `on_step` callback invoked
after each completed step with counts taken from the result. The
dashboard narrates those; it does not restate the pipeline. A test
asserts the per-detector counts sum to the report total, so a
fabricated step fails, and another asserts output is identical with and
without a callback. On the 130-order set the run emits 11 events —
four loads, one match, five detectors, one report — including
`settlement excess — 0 found`, because a step that ran and found
nothing is still work that happened.

**Charts.** Three plotly figures: exposure by anomaly type
(chargebacks red, others orange), a histogram of shortfall-to-payment
ratios with the refund threshold drawn on it, and a count-against-impact
scatter. The histogram is the substantive one — bars fall on **both**
sides of the threshold line, which is §6.6's overlap made visible
rather than argued.

**The isolation guarantee weakened, deliberately.** Stage 9's claim was
absolute: the dashboard could not recompute, full stop. Stage 10's is
"cannot recompute unless the button is pressed". That is strictly
weaker, and it was traded for the ability to demonstrate the pipeline
live rather than requiring a terminal.

The boundary moved rather than dissolving, and the stage 9 tests were
rewritten to encode where it now sits rather than deleted:

| Module | Constraint | How it is checked |
|---|---|---|
| `data.py`, `charts.py` | no engine import at all | `ast.walk` over all imports |
| `app.py` | no engine import **at module level** | `tree.body` only, so a lazy import inside the handler passes and a top-level one fails |
| `runner.py` | the single bridge | asserted to be the only file importing the engine, and to reach `src.main` without reaching past it into `matching`, `detectors` or `loaders` |

Measured at this commit: `app.py` imports the runner at line 135,
**inside** the button handler — so loading the page executes no pipeline
code, and a reader who never presses the button gets the stage 9
guarantee unchanged.

**One schema change.** The histogram needs shortfall ÷ payment and the
report CSV carried no payment column, so `payment_amount_paise` was
added, sourced from the reconciled frame. Orders whose payment never
arrived record `0` and are **excluded** from the histogram rather than
plotted at a fabricated ratio.

*Verified:* `AppTest` executed the app with **0 exceptions**, 3 charts,
31 table rows; pressing the button produced 11 real progress lines and 0
exceptions. Eval unchanged — no detection logic was touched.

### Documentation and alignment (`1b7be6a` … `72c14b6`, 5 commits)

No code changed in any of these; the eval output is identical before and
after all five.

**`1b7be6a` `docs: add comprehensive project report`** — the first
version of this document, 1,111 lines. Produced one analysis the project
did not previously have: the threshold sweep (§6.6), which converted the
claim that the refund/shortfall boundary is unfixable from an assertion
into a proof.

**`1a33286` `docs: document how the project meets the Track 04 bar`** —
README section addressing throughput, measured accuracy and the honest
exception list by name. 197 insertions, 0 deletions; the existing
caveats about the easy set were left untouched deliberately, because
they are the credibility of the rest.

**`d45639a` `docs: add Track 04 traceability to the project report`** —
the traceability tables at the top of this document, plus a "where the
fit is partial" list naming five caveats rather than leaving a reader to
find them. All cited commit hashes verified to resolve before commit.

**`30273fc` `docs: state the agent's deliberate lack of tool access`** —
two sentences in the README architecture section: the LLM has no tools,
no loop, and no control over program flow, and that is the determinism
boundary applied to control flow rather than only to arithmetic.
*Verified rather than asserted:* `client.py` passes no `tools`,
`tool_choice` or `tool_runner` parameter to the API.

**`72c14b6` `docs: explain where the reconciliation loop ends and why`**
— a README section defending the scope boundary: this closes the
identification loop, not remediation. Produced a measurement that
changed the recommendation it was written to support — see §7.6.

### Tags

| Tag | Commit | Contents |
|---|---|---|
| `v0.2` | `64b8b5a` | rules + agent + report |
| `v0.3` | `beeb5a4` | + dashboard; accuracy re-measured, unchanged |

Both tags predate the documentation commits above. Neither was moved:
a tag records a measured accuracy state, and none of the five changed a
number.

---

## 6. The mathematics

Everything the deterministic layer does, derived. Row counts are the
number of rows each statement was checked against, not a sample.

### 6.1 The settlement identity

For an order with a payment row and a fee row:

```
expected_settlement_paise = payments.amount_paise
                          − fees.fee_paise
                          − fees.gst_on_fee_paise

                          ≡ payments.amount_paise
                          − fees.total_deduction_paise

delta_paise = settlements.amount_paise − expected_settlement_paise
```

A negative delta means the merchant was underpaid. An order is flagged
when `abs(delta_paise) > TOLERANCE_PAISE`.

**Verified, not assumed.** Across the **99 orders carrying no anomaly**,
`settlements.amount_paise` equals the expression above with a maximum
absolute delta of **0 paise**. Not "within tolerance" — exactly zero.
The tolerance absorbs nothing on this data; it exists for real exports.

### 6.2 The sub-identities, with row counts

Each checked against every row, no sampling:

| Identity | Checked against | Result |
|---|---|---|
| `net + gst == gross` | 130 / 130 orders | exact, 0 mismatches |
| `fee + gst_on_fee == total_deduction` | 127 / 127 fee rows | exact, 0 mismatches |
| `payments.amount == orders.gross` | 127 / 127 matched pairs | exact, 0 mismatches |

Two further relationships, derived from the input ledgers alone and
never from the answer key:

| Relationship | Checked against | Result |
|---|---|---|
| `fee == round(amount × 0.02)` | 127 / 127 | exact |
| `gst_on_fee == round(fee × 0.18)` | 127 / 127 | exact |

The second pair is *observed structure in the fixtures*, not a
contractual rate. It is used to reason about the data, never to compute
a finding — the detectors read the actual per-row `fee_paise`.

### 6.3 Why integer paise, worked

The project stores every amount as an integer count of paise. The
alternative — floats denominated in rupees — fails on this data, and
here is a case from the fixtures rather than a textbook example.

`ord_00046` has `net_amount_paise = 2758875`. Computing 18% GST:

```
integer paise path (what the project does)
  2758875 × 0.18            = 496597.5
  round(...)                = 496598

float rupees path (the naive alternative)
  2758875 / 100             = 27588.75
  27588.75 × 0.18           = 4965.974999999999
      exact binary value    = 4965.9749999999994543031789362430572509765625
  round(..., 2)             = 4965.97          <- the .975 is already gone
  × 100                     = 496597.0
  round to paise            = 496597

  divergence                = 1 paisa
```

The multiplication lands *below* the true 4965.975 in binary floating
point, so rounding to two decimal places truncates a half-paisa that
should have rounded up.

Round-tripping fails independently of any arithmetic. **18 of the 127
payment amounts** do not survive paise → rupees → paise:

```
1911685 -> 19116.85 -> 1911684.9999999998   int() gives 1911684
3915609 -> 39156.09 -> 3915608.9999999995   int() gives 3915608
4087730 -> 40877.3  -> 4087730.0000000005   int() gives 4087730
```

Two of those three lose a paisa to truncation. Summing all **1,335
amounts** in both fixture sets as float rupees and converting back gives
`1700051271.0000012` against an exact `1700051271` — an error of
1.19 × 10⁻⁶ paise on this data, and unbounded in general.

Integer paise makes the whole class impossible: `10 + 20 == 30` is true
where `0.1 + 0.2 == 0.3` is false.

### 6.4 The shortfall ratio, and what it does not measure

```
shortfall_paise = −delta_paise                    (positive when underpaid)
ratio           = shortfall_paise / payment_amount_paise
```

The ratio is the **size of the gap relative to what was captured**. It
is the only feature available to separate a refund from a shortfall, and
that is the whole problem: it measures *magnitude*, not *cause*. A 30%
gap and a 30% gap look identical whether the money went back to a
customer or was never credited by the bank.

`shortfall_ratio()` guards a zero payment rather than emitting infinity.

### 6.5 The chargeback signature, derived

A chargeback reverses the entire captured payment **and** withholds a
penalty on top. So:

```
shortfall = payment + fee_cb

ratio     = shortfall / payment
          = (payment + fee_cb) / payment
          = 1 + fee_cb / payment
```

Because `fee_cb > 0`, the ratio is **always greater than 1** — the
merchant loses more than the sale was worth. Measured on the five
chargebacks in the adversarial set:

| Order | Payment (paise) | `fee_cb` (paise) | Ratio | vs the 0.20 threshold |
|---|---:|---:|---:|---:|
| `ord_h0025` | 1,711,000 | 25,000 | 1.0146 | 5.1× |
| `ord_h0026` | 2,395,400 | 75,000 | 1.0313 | 5.2× |
| `ord_h0027` | 896,800 | 100,000 | 1.1115 | 5.6× |
| `ord_h0028` | 2,230,200 | 50,000 | 1.0224 | 5.1× |
| `ord_h0029` | 637,200 | 50,000 | 1.0785 | 5.4× |

**This is why a chargeback with a non-standard fee is misread as a
refund.** The detector matches `|delta + payment + CHARGEBACK_FEE_PAISE|
≤ TOLERANCE_PAISE`, which fails when `fee_cb ≠ 50000`. The row then
falls through to the refund rule — and its ratio is *five times* the
refund threshold, so the refund rule claims it with room to spare. The
error is not marginal; it is the most confident possible wrong answer.
See §7.4.

### 6.6 The threshold sweep

The refund/shortfall split is a single constant compared against the
ratio. Is there a *better* constant? Sweeping every candidate across
both sets combined:

```
threshold-decided orders: 40 (29 refunds, 11 shortfalls)
refund ratio range   : 0.0800 .. 1.0000
shortfall ratio range: 0.0020 .. 0.3500
OVERLAP: refunds below the largest shortfall = 19

 threshold  errors   easy   hard
    0.0309       3      1      2      <- best achievable
    0.0800       3      1      2
    0.0305       4      2      2
    0.1200       4      1      3
    0.0260       6      3      3

BEST POSSIBLE threshold 0.0309: 3 errors (easy 1, hard 2)
errors remaining even there:
  ord_00011    easy  ratio=0.1818  shortfall called refund
  ord_h0024    hard  ratio=0.2800  shortfall called refund
  ord_h0023    hard  ratio=0.3500  shortfall called refund
```

**The two classes overlap on this axis.** Refund ratios run 0.0800 to
1.0000; shortfall ratios run 0.0020 to 0.3500. **Nineteen refunds sit
below the largest shortfall.** Sorted, they interleave:

```
0.1200 refund   0.1421 refund   0.1500 refund   0.1728 refund
0.2124 refund   0.2378 refund   0.2573 refund   0.2687 refund
0.2800 SHORTFALL
0.3000 refund   0.3163 refund   0.3340 refund
0.3500 SHORTFALL
```

**No constant separates two interleaved sets.** That is not a statement
about which constant was chosen; it is a statement about the feature.
The best achievable is 3 errors, not 0, and reaching even that would
mean fitting the constant to the answer key — forbidden by CLAUDE.md
§11, and it would move the overfitting rather than remove it. The
shipped 0.20 gives 7 errors. Neither is a solution; see §10.

### 6.7 Precision, recall and F1, computed by hand

So a reader can check the harness rather than trust it. Taking
**chargeback on the adversarial set, rules only**:

```
predicted chargeback : {ord_h0028, ord_h0029}
truth     chargeback : {ord_h0025, ord_h0026, ord_h0027, ord_h0028, ord_h0029}

TP = |predicted ∩ truth| = 2
FP = |predicted − truth| = 0
FN = |truth − predicted| = 3

precision = TP / (TP + FP) = 2 / (2 + 0) = 1.0000
recall    = TP / (TP + FN) = 2 / (2 + 3) = 0.4000
F1        = 2PR / (P + R)  = 2 × 1.0 × 0.4 / (1.0 + 0.4) = 0.5714
```

Which is exactly what the harness prints:

```
chargeback                  5     2    2    0    3    1.000    0.400    0.571
```

Note what the numbers say: **precision 1.000 with recall 0.400.** The
rule never calls a non-chargeback a chargeback — its signature is exact
— but it misses three of five, because those three carry a fee it does
not expect. Reporting only precision here would be flattering and
useless. Recall is the priority metric for exactly this reason.

**A wrong label costs twice.** Calling a shortfall a refund is a false
positive for `refund_not_reflected` *and* a false negative for
`settlement_shortfall`. `tests/test_eval.py` pins that behaviour so the
harness cannot quietly forgive a misclassification as a near-miss.

### 6.8 Tolerance

```
flagged  ⟺  abs(delta_paise) > TOLERANCE_PAISE        TOLERANCE_PAISE = 100
```

Never `==`. On the easy set, **99 orders fall within tolerance and the
largest `|delta|` among them is 0 paise** — every clean order is exactly
clean. The tolerance is absorbing nothing here; it is there for real
exports where rounding between systems is real.

---

## 7. What broke

Eight incidents. Each is given as symptom, detection, root cause, the
mathematics or logic that failed, the fix chosen, the fix rejected and
why, the measured before and after, and what it generalises to.

This is the longest section in the document deliberately. The failures
are more informative than the successes, and several of them changed the
design rather than just being patched.

---

### 7.1 The timezone constant could not be resolved

**Symptom.** `config.TIMEZONE = "Asia/Kolkata"` imported without error.
Loading it did not:

```
zoneinfo._common.ZoneInfoNotFoundError: 'No time zone found with key Asia/Kolkata'
```

**How it was detected.** CLAUDE.md §12 requires running a thing before
claiming it works. Stage 1 produced only constants and empty packages,
so the temptation was to assert the scaffold was fine. Actually
exercising the constant surfaced it.

**Root cause.** Windows ships no system tz database. Python's stdlib
`zoneinfo` reads one from disk and finds nothing:

```
zoneinfo.TZPATH:        ()
available_timezones():  0
```

**The logic that failed.** Not a missing *entry* — an empty *database*.
Zero timezones available. A lookup of any key would have failed
identically, so no amount of checking the spelling of "Asia/Kolkata"
would have found it.

**Fix chosen.** `tzdata` added to `requirements.txt`, with the
measurement recorded in a comment so the next reader knows why a
timezone package is a dependency of a reconciliation tool.

**Fix rejected.** Dropping `zoneinfo` for pandas' tz handling, which
bundles its own database. Rejected because pandas 3.0 dropped `pytz` and
declares `tzdata` as a hard dependency anyway — the explicit line
documents a real requirement instead of relying on a transitive one that
a future pandas could drop.

**Before and after.**

```
before:  available_timezones() -> 0 keys        ZoneInfo(...) -> raises
after:   available_timezones() -> 598 keys      ZoneInfo(...) -> Asia/Kolkata
         2026-02-01 16:08:00+05:30   (utcoffset 5:30:00)
```

**Generalises to.** A configuration value that *looks* correct can be
unusable. Validate config by using it, not by reading it. Had this
waited for stage 2, it would have surfaced as a loader crash far from
its cause.

---

### 7.2 The answer key imputed a fee on payments that never happened

**Symptom.** Implementing the missing-payment rule, the answer key's
`expected_amount_paise` for the three missing-payment rows did not equal
`orders.gross_amount_paise`:

```
ord_00006: gross=1475793  key=1440964  diff=34829
ord_00065: gross=1983086  key=1936285  diff=46801
ord_00067: gross=5383503  key=5256452  diff=127051
```

**How it was detected.** By comparing the rule against the key *before*
changing either, and treating a disagreement as a question rather than
as evidence the rule was wrong.

**Root cause.** The fixture generator applied the 2% + 18% deduction
uniformly across all orders — including three where no payment ever
reached the gateway, and therefore no commission was ever charged.

**The mathematics.** Every difference is the imputed fee, exactly:

```
round(1475793 × 0.02 × 1.18) = 34829   ✓
round(1983086 × 0.02 × 1.18) = 46801   ✓
round(5383503 × 0.02 × 1.18) = 127051  ✓
```

Three for three, to the paisa. That precision is what identified it as
systematic rather than coincidental.

**Fix chosen.** Correct the key. Three rows in `ground_truth.csv`:

```
-ord_00065,...,1936285,0,-1936285,...
+ord_00065,...,1983086,0,-1983086,...
```

**Fix rejected.** "Correcting" the detector to match the key. Rejected
twice over: it would have understated the merchant's loss by 2.36% on
those rows, and it would have meant shaping detection logic to the
answer key — which CLAUDE.md §11 forbids outright, and which would have
invalidated every accuracy number the project later reports.

**Before and after.** After the correction, re-verified: still 31 rows
with the same type distribution; `actual − expected == delta` on all 31;
all three missing-payment rows equal `orders.gross`; the 28 rows that do
have payments still satisfy `payment − total_deduction`.

**Generalises to.** The answer key is not automatically right. When a
rule and a label disagree, the question is which one is wrong — and the
label is not exempt. The first handling of this documented the
divergence and forbade tuning toward the key; identifying it as a
generator bug came from asking rather than assuming.

---

### 7.3 The confidence boundary sat on a cluster point

**Symptom.** With `REFUND_HIGH_CONFIDENCE_PCT = 0.25`, one of fifteen
refunds came back medium instead of high: `ord_00026`. The other
fourteen were high.

**How it was detected.** Reading the confidence split in the eval output
— 14 high / 1 medium — and noticing it was inconsistent with every
refund being at 25% or above.

**Root cause.** The boundary was placed exactly where the data clusters.

**The mathematics.** The generator built refunds as percentage slices,
rounding to integer paise:

```
payment                = 5259413
round(payment × 0.25)  = 1314853        <- the stored shortfall
exact ratio            = 1314853 / 5259413
                       = 0.2499999524661782598172077378
float ratio            = 0.24999995246617826
ratio >= 0.25          = False
```

`payment × 0.25 = 1314853.25`, which rounds **down**. The stored
shortfall is therefore a hair under a true quarter, and the ratio lands
below 0.25. Four of the five 25% refunds happened to round the other
way; this one did not. **Which side of the boundary a true 25% refund
fell on was decided by rounding noise, not by the data.**

**Fix chosen.** Move the boundary to 0.22, documented as a narrow margin
*above* `REFUND_THRESHOLD_PCT` rather than an independent value, so it
can never coincide with a common refund percentage (25, 30, 50, 100).
Renamed `REFUND_NEAR_THRESHOLD_PCT` to match what it now does.

**Fix rejected.** Rounding the ratio before comparing. Rejected because
it hides the problem for this dataset while leaving the boundary on the
cluster point — any other rounding convention, or any other payment
amount, resurfaces it. Moving the line off the cluster is structural;
rounding is a patch over one symptom.

**Before and after.**

```
before:  ord_00026 ratio 0.2499999525 -> medium   (14 high / 1 medium)
after:   ord_00026 ratio 0.2499999525 -> high     (15 high / 0 medium)
         lowest real refund ratio 0.250000, margin above 0.22 = 0.030000
```

**Generalises to.** Never put a decision boundary where the data
clusters. If a threshold sits on a common value, the comparison is
decided by floating-point representation rather than by meaning.

---

### 7.4 Confidence measured threshold distance, not certainty

**Symptom.** Confidence was to be the routing signal for the agent
layer. Cross-tabbed against correctness on the adversarial set, it ran
**backwards**:

```
confidence   correct  wrong  total  P(wrong)
high              12      5     17     0.294
medium             2      5      7     0.714
low                2      0      2     0.000
```

The low-confidence bucket was **100% correct**. Five of the ten errors
were marked **high**.

**How it was detected.** By asking whether confidence was usable as a
routing signal *before* designing around it, and measuring rather than
assuming. Had the agent been built first, this would have surfaced as
unexplained agent behaviour instead of a clean measurement.

**Root cause.** Confidence was computed from the shortfall ratio's
distance from the refund threshold. But the threshold *is* the error
source, so distance from it carries no information about correctness.

**The mathematics.** From §6.5, a chargeback's ratio is

```
ratio = 1 + fee_cb / payment  ≈ 1.01 to 1.11
```

— five times the 0.20 refund threshold. When `fee_cb ≠ 50000` the
chargeback signature does not match, the row falls to the refund rule,
and its enormous distance from the threshold is read as **certainty**.
The rule was structurally most confident exactly where it was most
wrong.

**What this did to routing.** At the old confidence:

```
low only     sends  2/26, catches  0/10 errors (0%)
low+medium   sends  9/26, catches  5/10 errors (50%)
everything   sends 26/26, catches 10/10 errors (100%)
```

Nothing between useless and send-everything.

**Fix chosen.** Confidence became a property of the **detector**, not of
the row:

- `chargeback`, `payment_not_received`, `settlement_excess` → **high**.
  Each matches an arithmetic identity within tolerance or does not;
  there is no continuum to be wrong about.
- `refund_not_reflected`, `settlement_shortfall` → **never high**,
  however large the gap. Medium clear of the boundary band, low inside
  it.

**Fix rejected.** Routing by *rule provenance* instead — send everything
the threshold decided, never send the three sharp types. That also
catches 100% of errors. Rejected as the primary mechanism because
confidence is a field a human reads: a field reading "high" on five
wrong answers misleads a reviewer exactly as it misleads a router.
Fixing the field fixed both consumers.

**Before and after.**

```
before:  high 12 correct /  5 wrong (0.294)   low+medium catches  5/10 (50%)
after:   high  6 correct /  0 wrong (0.000)   low+medium catches 10/10 (100%)
         medium 9 correct / 10 wrong (0.526)
         low     1 correct /  0 wrong (0.000)

classification UNCHANGED: easy 1.000, hard 0.615 micro F1
```

Only the confidence field moved. No order changed label.

**Generalises to.** A confidence score must measure uncertainty in the
thing being decided, not distance from the mechanism doing the deciding.
When those two are conflated, the score is most wrong exactly where the
mechanism is.

---

### 7.5 The agent regressed the easy set

**Symptom.** First live agent run, override bar at "not low":

```
                easy     hard
micro F1       0.968    0.692     (rules-only: 1.000 / 0.615)
```

Easy fell from 1.000.

**How it was detected.** The eval, run before committing, as CLAUDE.md
§11's regression gate requires. `refund_not_reflected` recall dropped
1.000 → 0.933 on the baseline set. The commit was blocked and the work
stopped.

**Root cause.** One order moved: `ord_00026`, `refund_not_reflected` →
`settlement_shortfall`. The agent's own explanation:

> "The shortfall is exactly 25.0% of the captured payment — a
> suspiciously clean fraction for a real customer refund, which by
> definition should be an arbitrary amount tied to a specific return."

**The logic that failed — and it was mine, not the model's.** The system
prompt asserted *"Real refunds are arbitrary amounts."* That is true of
the real world and **false of these fixtures**, where round percentages
are precisely the refund signature. The model reasoned validly from a
premise the prompt supplied. A false statement in a prompt produces
confidently wrong output, exactly as a false constant in code does.

It is the same `ord_00026` as §7.3 — the exact-25% refund at
`0.2499999525`, which is why it sat at medium confidence and was routed
at all. The most fragile order in the set was the one that broke.

**Fix chosen.** Raise the override bar from "not low" to **high**. The
evidence, from the same run:

| Override | Agent confidence | Outcome |
|---|---|---|
| `ord_h0025` refund → chargeback | high | FIXED |
| `ord_h0026` refund → chargeback | high | FIXED |
| `ord_h0027` refund → chargeback | high | FIXED |
| `ord_h0032` refund → shortfall | medium | BROKE |
| `ord_00026` refund → shortfall | medium | BROKE |

Every correct override was confident; every damaging one was hedged.

**Fix rejected.** Deleting the "real refunds are arbitrary amounts"
sentence from the prompt. Rejected because it would have been tuning the
prompt against the answer key, and because it fixes one sentence rather
than the class of problem. The confidence gate discards hedged overrides
regardless of what caused them.

**A consequence handled.** Raising the gate made another prompt sentence
false — it had told the model that a `low` override would be discarded.
It was replaced with an instruction to report genuine certainty, and
**the threshold is deliberately not named**: telling a model which value
unlocks an override invites it to report that value rather than its
actual confidence, destroying the signal the gate depends on. A test
asserts `"high"` appears in the prompt only inside the JSON schema line.

**Before and after.**

```
not-low bar:  easy 0.968 micro F1  |  hard 0.692  |  3 fixed, 2 broke
high bar:     easy 1.000 micro F1  |  hard 0.731  |  3 fixed, 0 broke
```

**Generalises to.** A prompt is code, and a false claim in it is a bug
with the same consequences. Also: when a system can only regress on one
dataset and improve on another, gate the change on the dataset it can
damage.

---

### 7.6 `ord_h0022` — confidence is safe going in, unsafe coming out

**Symptom.** None in production. This is a latent hazard caught before
anything was built on it, which is the reason it is worth recording.

While documenting where remediation would be appropriate, the natural
description was "action the findings where confidence is high by
construction". Checking that rather than writing it:

```
easy: threshold-decided findings marked HIGH by the agent: 12  -> 0 wrong
hard: threshold-decided findings marked HIGH by the agent:  1  -> 1 wrong (ord_h0022)
```

**How it was detected.** By testing a phrase before putting it in a
document. The claim was plausible, consistent with §7.4, and wrong.

**The logic that failed.** §7.4 made confidence trustworthy by making it
a property of the detector — a `refund_not_reflected` finding could
never be high. That guarantee holds **on the way into** the agent, which
is why routing on it is sound. It does **not** hold on the way out: the
agent returns *its own* confidence, and a confirmation or override at
high overwrites the detector's medium. After the agent pass, a refund
finding can carry high confidence, and on the adversarial set exactly
one does — with the wrong label.

The invariant was established at one stage and silently invalidated by a
later one.

**Fix chosen.** Specify the remediation filter as **anomaly type**, not
confidence. The exact-signature classes — `chargeback`,
`payment_not_received`, `settlement_excess` — measured across both sets
with the agent pass: 8 of 31 findings on easy (26%), 9 of 26 on hard
(35%), all high confidence, all scoring 1.000 precision and recall,
**zero wrong labels on either set**.

**Fix rejected.** Forbidding the agent from raising confidence, so the
detector's value survives. Rejected because the agent's certainty is
exactly what gates overrides (§7.5) — clamping it would break the
mechanism that keeps the easy set at 1.000. The agent's confidence is
genuine information about the agent's judgement; it simply is not the
same quantity as the detector's confidence, and the two share a field.

**Generalises to.** A field's guarantees can be invalidated by a later
stage that writes to it. Verify invariants at the point of *use*, not
the point of creation — and be suspicious when two stages write
different meanings into one column.

---

### 7.7 grep-versus-AST false positives

**Symptom.** Three times, a `grep`-based structural check reported a
violation that did not exist:

1. `grep -rn "ground_truth" src/` flagged `overpayments.py`, which only
   *mentions* the answer key in a docstring explaining that the eval
   must report `settlement_excess` separately.
2. `grep -rnE "from src\.(matching|detectors|agent)" src/dashboard/`
   flagged `app.py`, whose module docstring states the constraint.
3. `tests/test_dashboard.py::test_dashboard_never_reads_the_answer_key`
   failed on its own module's docstring.

**How it was detected.** By inspecting every hit instead of trusting the
exit code. A check that reports a violation is not automatically right.

**Root cause.** A file that *documents* a prohibition contains the
prohibited string. Text search cannot distinguish code from prose about
code — and the better a module documents its own constraint, the more
likely it is to trip its own check.

**Fix chosen.** Parse the AST. `_imported_modules()` walks `ast.Import`
and `ast.ImportFrom` nodes; the answer-key check walks `ast.Constant`
string nodes with docstrings excluded via `_docstring_nodes()`. Real
imports in `src/dashboard/`:

```
app.py : sys, pathlib, pandas, streamlit, src.dashboard.data
data.py: pathlib, pandas
```

**Fix rejected.** Narrowing the grep — excluding comment lines, or
requiring an `import` prefix. Rejected because it is a heuristic that
degrades as prose changes, whereas the AST distinguishes an import from
a mention by construction.

**Generalises to.** Structural claims need structural checks. This also
applied during the pre-publication security audit: a high-entropy scan
flagged four locations, all four benign on inspection (shields.io badge
URLs, long Python identifiers). The decisive check there was not a
pattern at all — it read the live key from `.env` and searched for that
literal string across all 210 objects in the full history. Result:
`NONE`.

---

### 7.8 My own errors

Not the code's. These are process failures, recorded because a report
that only lists the software's mistakes is not an honest one.

**The adversarial set reproduces the artifact it was built to avoid.**
Stage 4 explicitly rejected keying refund detection on "is the shortfall
an exact whole-percent slice", on the grounds that it is a fingerprint
of the generator rather than a property of refunds. I then wrote
`tests/gen_hard.py` and built five of its fourteen refunds as exact
percentage slices anyway:

```
easy: refunds that are EXACT whole-percent slices: 15, arbitrary: 0
hard: refunds that are EXACT whole-percent slices:  5, arbitrary: 9
```

Nine of fourteen are genuinely arbitrary, which is why the set still
works as an adversarial test — and the detectors do not key on the
artifact, so no reported number is invalidated. But **the hard set is
less adversarial than it should be**: a rule that did key on the
fingerprint would still score 5 of 14 on the set built to defeat it. The
right construction is arbitrary amounts throughout.

**A wrong claim about pandas, stated confidently.** When adding `tzdata`
I said pandas bundles `pytz`, so tz handling "would probably have worked
anyway". That is false for pandas 3.0, which dropped `pytz` — it is not
installed in this environment. The dependency was genuinely required,
not belt-and-braces. The claim was volunteered, not asked for, and was
wrong.

**Five stages of un-ticked checkboxes.** CLAUDE.md §14 requires updating
the README status checkboxes as each stage completes. Stages 1 through 5
all landed without it. It was caught only when stage 7 ticked its own
box and the inconsistency became visible, then fixed in a catch-up
commit (`c3998aa`). A rule followed four times out of five is a rule
that needs a check, not more diligence.

---

## 8. Evaluation methodology

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
CLAUDE.md §11's gate would block any commit that moved a number. The floor was at
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

## 9. Results

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
to guess at the refund/shortfall boundary. §10 shows that is correct.

**On both sets, in both modes: `missed entirely: none` and
`flagged but clean: none`.** Every anomaly is detected and nothing clean
is ever flagged. All error is classification, never detection — which
matters given recall is the priority metric.

---

## 10. Honest exception list

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
answer key, which CLAUDE.md §11 forbids and which would move the overfitting
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

## 11. Engineering practices

`CLAUDE.md` defines fifteen rules. Four did concrete work.

### Ask before committing (CLAUDE.md §3)

Every commit in this history was shown as a diff and approved before
landing. This caught real problems rather than being ceremony:

- The **`ord_00026` regression** (§7.5) surfaced at the diff stage, was
  reported with the agent's own reasoning, and the fix was chosen by the
  user rather than by the implementer.
- The **overpayment question** in stage 5 was put to the user before any
  code was written, because it changed whether a fifth detector existed.
- The **refund/shortfall rule** in stage 4 was a blocking question. The
  option that scored perfectly on the fixtures was explicitly presented
  as overfitting and rejected by the user.

### The regression gate (CLAUDE.md §11)

*"Before any commit that touches detection logic, run the eval. If
recall on any existing anomaly type drops, do not commit."*

This fired once, decisively. The stage 6 agent at the not-low override
bar dropped easy `refund_not_reflected` recall from 1.000 to 0.933. The
commit was blocked, the cause was investigated, the bar was raised, and
the eventual commit held easy at 1.000 while improving hard. **Without
the gate, a change that improved the headline hard number by 0.077 would
have silently damaged the baseline.**

### One commit per logical change (CLAUDE.md §3)

Applied even when inconvenient:

- The five stage checkboxes were ticked in their **own** commit
  (`c3998aa`) rather than folded into stage 7's.
- The `.gitignore` tightening (`0f8d7ee`) was separate from the `data/`
  README that motivated it (`087b3b5`).
- When the v0.3 accuracy rows were requested and the table was **already
  correct**, no commit was manufactured — the rows had landed with stage
  6, the eval was re-run to confirm, and the tag was applied directly.

### Never invent data (CLAUDE.md §6) and verify before claiming done (CLAUDE.md §12)

- The data model was written by reading actual header rows and measuring
  actual identities — hence "verified across 127/127" rather than
  "should hold".
- The `tzdata` failure (§7.1) was found *because* CLAUDE.md §12 required running
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

## 12. What's next

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

Open question this must answer first: UNKNOWN #3 from §4 — nullability
in real exports determines whether an unmapped column is a hard error or
a bucketed row.

### A refund ledger

The single highest-value addition, for the reasons in §10. It collapses
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

Answering UNKNOWN #1 from §4 — whether 2% + 18% is contractual or
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
