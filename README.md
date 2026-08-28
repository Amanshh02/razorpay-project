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
    − refunds
    − chargebacks
```

Anything outside a configurable tolerance (default ₹1) is flagged.

## Running it

```bash
# setup
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# run reconciliation
python -m src.main --data data/ --out reports/

# run the eval suite
python evals/run_eval.py
```

## Accuracy by version

Measured against a labelled fixture set of 130 orders containing
15 refunds, 5 chargebacks, 8 shortfalls, and 3 missing payments.

| Version | Match rate | Refunds F1 | Chargebacks F1 | Shortfalls F1 | Missing pmts F1 | Notes |
|---|---|---|---|---|---|---|
| v0.1 | — | — | — | — | — | rules only, no agent layer |
| v0.2 | — | — | — | — | — | + LLM classification |

Recall is the priority metric — a missed discrepancy is money lost,
a false positive is a human glance.

## Tech stack

| Layer | Choice |
|---|---|
| Core | Python 3.11, pandas |
| Agent | Claude API (tool use) |
| Evals | Custom harness — see `/evals` |
| Interface | CLI first; dashboard if time allows |

## Project structure

```
src/          reconciliation engine
  loaders/    one loader per ledger
  matching/   the join logic
  detectors/  one module per anomaly type
  agent/      LLM classification + explanation
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

- [ ] Stage 1 — project scaffold
- [ ] Stage 2 — ledger loaders
- [ ] Stage 3 — matching engine
- [ ] Stage 4 — refund & chargeback detection
- [ ] Stage 5 — shortfall & missing payment detection
- [ ] Stage 6 — agent classification layer
- [ ] Stage 7 — eval harness
- [ ] Stage 8 — reporting output
