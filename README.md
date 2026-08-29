![status](https://img.shields.io/badge/status-in_development-39FF14?style=for-the-badge&labelColor=0A0A0A)
![track](https://img.shields.io/badge/track-04_AI_Finance_Controller-FF6B00?style=for-the-badge&labelColor=0A0A0A)
![python](https://img.shields.io/badge/python-3.11-39FF14?style=for-the-badge&labelColor=0A0A0A)

# AI Finance Controller

Automated multi-source reconciliation agent for merchant payments.
Built for the Razorpay Buildathon — Track 04.

> One line pitch: it reads four ledgers that should agree, finds
> every place they don't, and tells you why in plain English.

---

## The problem

A merchant's money passes through four separate records before it
lands in their bank:

1. What they billed the customer
2. What Razorpay actually received
3. What Razorpay charged in fees and GST
4. What the bank actually settled

These should reconcile. They frequently don't — and the gaps are
where money quietly disappears. A refund never accounted for. A
chargeback that silently reduced a payout. A settlement that came
up short. A payment the gateway never received at all.

Today this is a spreadsheet job done by hand, monthly, badly.

## Meeting the Track 04 bar

Of the four example directions in the brief, this is **multi-source
reconciliation**.

The brief's framing is that verification capacity, not generation
speed, is the bottleneck. That is the argument for the architecture
here rather than an aside to it: the deterministic layer *is* the
verifier, and it is deliberately not an LLM, because a number a
merchant defends to an auditor has to be reproducible. The LLM is
confined to the one job code is bad at — deciding what an unexplained
gap *was*. The eval harness then makes the verification itself
checkable, which is the part that usually goes missing: without it,
"the agent reconciled the books" is a claim, not a measurement.

Every figure below is a whole-batch result produced by a command in
[the appendix](#reproducing-every-number-here). Nothing is sampled.

### Throughput

| | easy set | adversarial set |
|---|---|---|
| Orders in the batch | **130** | 40 |
| Ledger rows across all four files | **511** | 154 |
| Processed per pass | all of them | all of them |
| Median wall clock, 7 runs | **0.189 s** | 0.159 s |
| Orders / second | 688 | 251 |
| Ledger rows / second | 2,704 | 968 |

The brief asks for a 50+ record batch. The primary batch is **130
orders / 511 ledger rows**, processed in a single pass — no sampling,
no subsetting, no early exit. The adversarial set is a *second*
labelled batch of 40 orders, added deliberately (see below); it is an
addition to the 130, not the batch itself.

Cold start from the shell, including interpreter startup and the pandas
import, is a median **2.15 s** over 3 runs. The 0.189 s figure is the
pipeline itself, measured in-process.

**Nothing is silently dropped.** The matcher asserts a row conservation
invariant *per ledger* before it returns anything:

```
len(ledger) == len(reconciled) + len(unreconciled[source == ledger])
```

That must hold four times over — once each for orders, payments, fees
and settlements — because every reconciled row consumes exactly one row
from each file. A violation raises `RowConservationError` rather than
returning a lossy result. Any input row that cannot be placed goes to
an explicit `unreconciled` bucket carrying the ledger it came from and
the reason.

### Measured accuracy

**Match rate — asked for by name in the brief:** **0.977** on the easy
set (127 of 130 orders joined through the full ID chain) and **0.950**
on the adversarial set (38 of 40). The three and two orders that do not
join are the missing-payment cases; they cannot join past the first
link by definition, and they are detected as anomalies rather than
discarded.

**Easy set — 130 orders, 31 labelled anomalies.** Identical rules-only
and with the agent; the agent routed 23 findings and confirmed all 23,
overriding nothing.

| Anomaly type | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| refund_not_reflected | 15 | 1.000 | 1.000 | 1.000 |
| chargeback | 5 | 1.000 | 1.000 | 1.000 |
| settlement_shortfall | 8 | 1.000 | 1.000 | 1.000 |
| payment_not_received | 3 | 1.000 | 1.000 | 1.000 |
| **micro average** | **31** | **1.000** | **1.000** | **1.000** |

**Read that row with suspicion, and see [Accuracy by
version](#accuracy-by-version) for why.** It is a statement about the
fixtures, not about the detectors: the rules were written by inspecting
these same four ledgers, and the set contains no case the 20% refund
threshold can get wrong — it sits in a 6.8-point empty band between the
largest shortfall (0.1818) and the smallest refund (0.2500). That is
exactly why the adversarial set exists.

**Adversarial set — 40 orders, 26 labelled anomalies.**

| Anomaly type | Support | Rules P | Rules R | Rules F1 | Agent P | Agent R | Agent F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| refund_not_reflected | 14 | 0.643 | 0.643 | 0.643 | 0.818 | 0.643 | **0.720** |
| chargeback | 5 | 1.000 | 0.400 | 0.571 | 1.000 | 1.000 | **1.000** |
| settlement_shortfall | 3 | 0.167 | 0.333 | 0.222 | 0.167 | 0.333 | 0.222 |
| payment_not_received | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| settlement_excess | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| **micro average** | **26** | **0.615** | **0.615** | **0.615** | **0.731** | **0.731** | **0.731** |

Classification accuracy — every order given the right label, counting
correctly-unflagged clean orders as correct — is 1.000 on easy and
**0.750 rules-only / 0.825 with the agent** on the adversarial set.

The agent's entire contribution is one failure class: chargebacks
carrying a fee other than ₹500, which the rules structurally cannot see
because their signature assumes a fixed penalty. **0.571 → 1.000.** It
changed nothing on the easy set and nothing at the refund/shortfall
boundary.

On both sets in both modes, the eval reports `missed entirely: none`
and `flagged but clean: none`. Every labelled anomaly is detected and
no clean order is ever flagged; all error is classification, never
detection. Given the brief's asymmetry — a missed discrepancy is money
lost, a false alarm is a human glance — that is the direction to fail
in.

**The rules-only path needs no API key and makes no network call.**
Every rules-only figure above is reproducible from a clean clone with
`python evals/run_eval.py`. Only `--agent` requires a key.

### Honest exception list

**Seven orders, all on the adversarial set, all after the agent pass.**
Named, with the measurement that makes each one hard:

| Order | Truth | Predicted | Shortfall / payment |
|---|---|---|---:|
| `ord_h0022` | refund_not_reflected | settlement_shortfall | 0.0800 |
| `ord_h0020` | refund_not_reflected | settlement_shortfall | 0.1200 |
| `ord_h0033` | refund_not_reflected | settlement_shortfall | 0.1421 |
| `ord_h0021` | refund_not_reflected | settlement_shortfall | 0.1500 |
| `ord_h0031` | refund_not_reflected | settlement_shortfall | 0.1728 |
| `ord_h0024` | settlement_shortfall | refund_not_reflected | 0.2800 |
| `ord_h0023` | settlement_shortfall | refund_not_reflected | 0.3500 |

Five refunds fall below the 0.20 threshold; two shortfalls sit above
it. **This is not fixable by moving the threshold, and that was tested
rather than assumed.** Sweeping every candidate threshold across both
sets combined:

```
threshold-decided orders: 40 (29 refunds, 11 shortfalls)
refund ratio range   : 0.0800 .. 1.0000
shortfall ratio range: 0.0020 .. 0.3500
OVERLAP: refunds below the largest shortfall = 19

BEST POSSIBLE threshold 0.0309: 3 errors (easy 1, hard 2)
```

The two classes **overlap on this feature**. Nineteen refunds sit below
the largest shortfall; the ratios interleave. The best achievable over
all candidate thresholds is **3 errors, not 0** — and reaching it would
mean fitting a constant to the answer key, which the project's own
rules forbid and which would move the overfitting rather than remove
it. The current 0.20 gives 7. Neither is a solution.

**What would actually close it: a refund ledger.** A fifth file
recording refunds turns the whole class from inference into a join — a
shortfall with a matching refund row *is* a refund; one without *is* a
shortfall. The ambiguity disappears, because it was never a modelling
problem. The information is not in the four files.

### "One cherry-picked match proves nothing"

Agreed, so none of the above is one match:

- **Every figure is a whole-batch result.** 130 orders and 40 orders,
  scored in full. No sampling, no filtering, no best-of-N.
- **Both sets are scored in full and reported separately**, never
  merged into one flattering average.
- **The adversarial set exists specifically so the numbers are not a
  self-report.** The rules score 1.000 on the set they were written
  against. On 40 orders built to break them — refunds under the
  threshold, shortfalls over it, chargebacks with a non-₹500 fee, two
  refunds on one order, a refund and a shortfall on the same order —
  they score 0.615. **The rules were deliberately not tuned to pass
  it**, and the gap between 1.000 and 0.615 is the honest measure of
  what they are worth.
- **The answer key is read by exactly one file.** `evals/run_eval.py`
  may open `ground_truth.csv`; no loader, matcher or detector may. If
  detection logic needed the key, every number here would be
  meaningless.
- **The failures are documented as thoroughly as the successes.**
  [`docs/PROJECT_REPORT.md`](docs/PROJECT_REPORT.md) §5 records six
  incidents with the mathematics that went wrong, including one where
  the agent regressed the easy set and the commit was blocked.

### Reproducing every number here

```bash
python evals/run_eval.py            # accuracy, both sets, no API key needed
python evals/run_eval.py --agent    # + the agent pass (needs a key)
python -m src.main --data tests/fixtures --out reports/        # 130-order batch
python -m src.main --data tests/fixtures/hard --out reports/   # 40-order batch
python -m pytest -q                 # 193 tests
```

Throughput figures come from timing `src.main.run()` in-process over 7
runs and taking the median; the cold-start figure times the same
command as a subprocess over 3 runs. The threshold sweep is the
analysis reported in
[`docs/PROJECT_REPORT.md`](docs/PROJECT_REPORT.md) §8.

## What it does

Ingests all four ledgers, matches them order by order, computes what
each settlement *should* have been, and flags every discrepancy with
a classified reason and a confidence score.

**Detects:**

| Anomaly | Signal |
|---|---|
| Refund not reflected | Order marked paid, settlement reduced, no refund record in merchant ledger |
| Chargeback | Negative adjustment against a previously settled order |
| Settlement shortfall | Bank credit < (payment − fees − GST) beyond tolerance |
| Payment never received | Merchant recorded payment, no matching Razorpay record |
| Unreconciled | Row that could not be matched, with reason |

## Architecture

```
CSV ledgers ──> loaders ──> normaliser ──> matcher ──> detectors ──> classifier ──> report
                                          (pandas)     (pandas)      (Claude)
                                          deterministic layer        agent layer
```

**Deliberate design choice:** all matching and arithmetic is
deterministic pandas. The LLM never touches a number. The agent
layer handles what code is bad at — classifying *why* a gap exists,
reasoning about messy or partial records, and writing the
human-readable explanation attached to each flag.

This means the numbers are reproducible and auditable, and the
intelligence sits exactly where it adds value.

The LLM has **no tools, no loop, and no control over program flow** —
it receives one finding, returns one label with a reason, and never
decides what runs next. That is the determinism boundary applied to
control flow rather than only to arithmetic, and it is a design choice
rather than a limitation: an agent that can act on a settlement
calculation is an agent that can corrupt one.

## Inputs

| File | Contents |
|---|---|
| `orders.csv` | Merchant order + payment records, incl. GST |
| `payments.csv` | Payments received by Razorpay |
| `fees.csv` | Razorpay fees and taxes |
| `settlements.csv` | Bank settlement records |

Full column-level spec: [`docs/data-model.md`](docs/data-model.md)

## The core identity

```
expected_settlement =
      payment_amount
    − razorpay_fee
    − gst_on_fee
```

Anything outside a configurable tolerance (default ₹1) is flagged.

Refunds and chargebacks are deliberately **not** terms in this
formula. No ledger records them — a refund or chargeback is what an
unexplained negative delta turns out to *be*, inferred downstream by
the classifier. Subtracting them here would mean subtracting the very
quantity being detected.

For an order with no payment record at all, there is no fee to deduct
and expected recovery is the full `gross_amount_paise`. Full
derivation, verified against the fixtures, is in
[`docs/data-model.md`](docs/data-model.md).

## Running it

```bash
# setup
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# run reconciliation, rules only
python -m src.main --data data/ --out reports/

# run it against the bundled fixtures instead
python -m src.main --data tests/fixtures --out reports/

# add the agent classification pass
python -m src.main --data tests/fixtures --out reports/ --agent

# run the eval suite, rules only — no API key needed, no network call
python evals/run_eval.py

# run it with the agent layer as well
python evals/run_eval.py --agent
```

`--agent` needs `ANTHROPIC_API_KEY` in `.env` (gitignored, never
committed). Responses are cached to `.llm_cache/` keyed by model, prompt
version and finding, so re-running the eval costs nothing; delete that
directory to force a fresh run. `LLM_PROVIDER` selects the provider and
defaults to `anthropic`.

## Running the dashboard

```bash
streamlit run src/dashboard/app.py
```

Opens on <http://localhost:8501>. It reads the CSV the pipeline wrote to
`reports/`, so **generate a report first** — with no CSV there it tells
you which command to run rather than crashing or showing sample data.

The dashboard is **read-only by construction**. It imports nothing from
`src/matching`, `src/detectors` or `src/agent`, never runs
reconciliation, and never opens `ground_truth.csv`; a test parses its
AST to prove that rather than trusting the docstring. A viewer that can
recompute is a viewer that can disagree with the report it is showing,
and a finance team looking at two different numbers for one order has no
way to tell which is real.

What it shows:

- Total exposure in rupees with Indian digit grouping, and the flagged
  count. Overpayments appear separately and are **never netted** against
  exposure.
- One card per anomaly type with its count and rupee impact.
- Every flag in a sortable table — order ID, anomaly type, expected,
  actual, delta, confidence, explanation — sorted by absolute delta
  descending by default. The explanation is the agent's sentence where
  it ran, the rule's reasoning otherwise.
- Sidebar filters for anomaly type and minimum absolute delta.

Amounts are stored as integer paise everywhere and converted to rupees
at render time only.

## Accuracy by version

Two labelled sets, scored separately by `evals/run_eval.py`:

- **easy** — `tests/fixtures/`, 130 orders containing 15 refunds,
  5 chargebacks, 8 shortfalls and 3 missing payments. The regression
  baseline.
- **hard** — `tests/fixtures/hard/`, 40 orders built to break the rules
  on purpose: refunds under the 20% threshold, shortfalls over it,
  chargebacks with a non-₹500 fee, two refunds on one order, a refund
  and a shortfall combined. See that directory's README.

| Version | Set | Match rate | Refunds F1 | Chargebacks F1 | Shortfalls F1 | Missing pmts F1 | Excess F1 | Notes |
|---|---|---|---|---|---|---|---|---|
| v0.1 | easy | 0.977 | 1.000 | 1.000 | 1.000 | 1.000 | n/a | rules only, no agent layer |
| v0.1-hard | hard | 0.950 | 0.643 | 0.571 | 0.222 | 1.000 | 1.000 | rules only, no agent layer |
| v0.2 | easy | 0.977 | 1.000 | 1.000 | 1.000 | 1.000 | n/a | + LLM classification |
| v0.2-hard | hard | 0.950 | 0.720 | **1.000** | 0.222 | 1.000 | 1.000 | + LLM classification |
| v0.3 | easy | 0.977 | 1.000 | 1.000 | 1.000 | 1.000 | n/a | + dashboard; detection unchanged |
| v0.3-hard | hard | 0.950 | 0.720 | 1.000 | 0.222 | 1.000 | 1.000 | + dashboard; detection unchanged |

The v0.3 rows are identical to v0.2 by design. The dashboard reads the
report and changes no detection logic, so the numbers cannot move — they
are recorded here because they were re-measured at that tag, not assumed
to be unchanged.

Recall is the priority metric — a missed discrepancy is money lost,
a false positive is a human glance.

**The easy row is not evidence the detectors work.** A perfect score
there is a statement about the fixtures: the rules were written by
inspecting those same four ledgers, and the set contains no case the
20% refund threshold can get wrong — it sits in a 6.8-point empty band
between the largest shortfall (18.18%) and the smallest refund (25%).

**The hard row is what the rules are actually worth.** Micro F1 falls
to 0.615 and classification accuracy to 0.750. Every error is a
mislabel rather than a miss — nothing is overlooked, but ten of
twenty-six anomalies get the wrong type:

- 5 refunds under the threshold are called shortfalls
- 2 shortfalls over it are called refunds
- 3 chargebacks with a non-standard fee are called refunds

`settlement_shortfall` collapses to 0.222 F1 because it absorbs the
refunds the threshold rejects while losing the ones it steals.

That gap — 1.000 to 0.615 — is the headroom the agent layer exists to
close. **The rules are deliberately not tuned to pass the hard set**;
doing so would move the overfitting rather than remove it.

**What the agent layer bought (v0.1-hard → v0.2-hard).** Micro F1 rises
0.615 → 0.731 on hard and holds at 1.000 on easy. The whole gain is one
failure class: chargebacks carrying a fee other than ₹500, which the
rules structurally cannot see and which go 0.571 → **1.000**. The agent
is routed only medium- and low-confidence findings, and may displace the
rule's label only when it disagrees at high confidence — a bar set
because every hedged override measured made the answer worse, while
every confident one was right.

The refund/shortfall boundary is **unchanged** at 0.222 shortfall F1.
Seven hard orders still carry the wrong label, all of them sitting where
a refund and a shortfall are indistinguishable from the four ledgers.
Nothing short of a fifth ledger recording refunds will fix those; the
agent correctly declines to guess.

`match rate` is the share of orders joined through the whole ID chain,
a coverage measure rather than a detection one. The eval also reports
classification accuracy, which counts correctly-unflagged clean orders
as correct.

## Tech stack

| Layer | Choice |
|---|---|
| Core | Python 3.11, pandas |
| Agent | Claude API (tool use) |
| Evals | Custom harness — see `/evals` |
| Interface | CLI + read-only Streamlit dashboard |

## Project structure

```
src/          reconciliation engine
  main.py     CLI entry point
  report.py   grouping, exposure, CSV + console output
  loaders/    one loader per ledger
  matching/   the join logic
  detectors/  one module per anomaly type
  agent/      LLM classification + explanation
  dashboard/  read-only Streamlit viewer
evals/        accuracy harness
tests/        unit tests + labelled fixtures
docs/         data model and business rules
data/         local CSVs (gitignored)
reports/      generated output (gitignored)
```

## Limitations

- Single currency (INR) only
- Assumes one settlement batch per order; split settlements are
  flagged as unreconciled rather than resolved
- Tolerance is global, not per-merchant

## Status

- [x] Stage 1 — project scaffold
- [x] Stage 2 — ledger loaders
- [x] Stage 3 — matching engine
- [x] Stage 4 — refund & chargeback detection
- [x] Stage 5 — shortfall & missing payment detection
- [x] Stage 6 — agent classification layer
- [x] Stage 7 — eval harness
- [x] Stage 8 — reporting output
