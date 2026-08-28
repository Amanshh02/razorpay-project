# data/

This directory holds **real merchant CSV exports** — the actual
ledgers pulled from the merchant's account and from Razorpay.

Everything in here is gitignored and is never committed. The
`.gitignore` rule is `data/*.csv`; this README is the only file in
the directory that is tracked.

Drop the four ledgers here to run the pipeline against real data:

```
data/
  orders.csv
  payments.csv
  fees.csv
  settlements.csv
```

```bash
python -m src.main --data data/ --out reports/
```

## This is not where fixtures live

Labelled synthetic fixtures live in [`tests/fixtures/`](../tests/fixtures/)
and **are** committed, so the eval is reproducible from a clean clone.
That set is 130 orders with `ground_truth.csv` as the answer key.

Never copy real merchant data into `tests/fixtures/`, and never rely
on a file in `data/` being present — it will not exist on another
machine.
