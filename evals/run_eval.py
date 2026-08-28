"""Accuracy harness. The source of truth for every number we report.

Runs the full pipeline over the four ledger CSVs in tests/fixtures/ and
scores its findings against ``ground_truth.csv``.

**This is the only file in the project permitted to read
``ground_truth.csv``** (CLAUDE.md §11 and §13). No loader, matcher or
detector may reference it. If detection logic ever needs the answer key
to work, the accuracy numbers it produces are meaningless.

Scoring
-------
The answer key labels four anomaly types. ``settlement_excess`` is a
fifth type the detectors can emit and the key has no labels for at all,
so it is **counted and reported separately, never scored**. Treating it
as a false positive would penalise the pipeline for finding something
the key was never built to describe.

Two different overall figures are printed, because they measure
different things:

- **match rate** - the share of input orders the matcher could join
  through the whole ID chain. A coverage measure. It moves when the
  matcher or the data changes, not when detection improves.
- **classification accuracy** - the share of all orders given the right
  label, counting correctly-unflagged clean orders as correct. This is
  the figure that should move as the agent layer lands.

Usage::

    python evals/run_eval.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Running this as a script puts evals/ on sys.path, not the project root,
# so `import config` and `import src...` would fail. Add the root first.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.detectors import (  # noqa: E402
    detect_chargebacks,
    detect_missing_payments,
    detect_overpayments,
    detect_refunds,
    detect_settlement_shortfalls,
)
from src.loaders import (  # noqa: E402
    load_fees,
    load_orders,
    load_payments,
    load_settlements,
)
from src.matching import match_ledgers  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
GROUND_TRUTH = FIXTURES / "ground_truth.csv"

#: Types the answer key labels. Only these are scored.
SCORED_TYPES = (
    "refund_not_reflected",
    "chargeback",
    "settlement_shortfall",
    "payment_not_received",
)

#: Types the detectors can emit that the answer key has no labels for.
UNSCORED_TYPES = ("settlement_excess",)


def run_pipeline(fixtures=FIXTURES):
    """Load, match and detect. Returns (findings, match_result, orders)."""
    orders = load_orders(fixtures / "orders.csv")
    payments = load_payments(fixtures / "payments.csv")
    fees = load_fees(fixtures / "fees.csv")
    settlements = load_settlements(fixtures / "settlements.csv")

    matched = match_ledgers(orders, payments, fees, settlements)
    findings = pd.concat(
        [
            detect_chargebacks(matched.reconciled),
            detect_refunds(matched.reconciled),
            detect_settlement_shortfalls(matched.reconciled),
            detect_overpayments(matched.reconciled),
            detect_missing_payments(matched.unreconciled, orders),
        ],
        ignore_index=True,
    )
    return findings, matched, orders


def load_ground_truth():
    """Read the answer key. Nothing outside this module may do this."""
    return pd.read_csv(GROUND_TRUTH, dtype=str, keep_default_na=False)


def score_type(predicted, truth, anomaly_type):
    """Precision, recall and F1 for one anomaly type, keyed on order_id."""
    got = {
        order_id
        for order_id, label in predicted.items()
        if label == anomaly_type
    }
    want = {
        order_id for order_id, label in truth.items() if label == anomaly_type
    }

    true_positives = len(got & want)
    false_positives = len(got - want)
    false_negatives = len(want - got)

    precision = (
        true_positives / (true_positives + false_positives)
        if true_positives + false_positives
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if true_positives + false_negatives
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "anomaly_type": anomaly_type,
        "support": len(want),
        "predicted": len(got),
        "tp": true_positives,
        "fp": false_positives,
        "fn": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def main():
    findings, matched, orders = run_pipeline()
    truth_frame = load_ground_truth()

    truth = dict(zip(truth_frame["order_id"], truth_frame["anomaly_type"]))
    scored = findings[findings["anomaly_type"].isin(SCORED_TYPES)]
    predicted = dict(zip(scored["order_id"], scored["anomaly_type"]))

    total_orders = len(orders)
    reconciled = len(matched.reconciled)
    match_rate = reconciled / total_orders if total_orders else 0.0

    print("=" * 72)
    print("AI Finance Controller - accuracy eval")
    print("=" * 72)
    print(f"fixture set : {total_orders} orders in {FIXTURES}")
    print(f"answer key  : {len(truth_frame)} labelled anomalies")
    print(f"pipeline    : {len(findings)} findings "
          f"({len(scored)} scored, {len(findings) - len(scored)} unscored)")
    print()

    print("-" * 72)
    print(f"{'anomaly type':<24}{'sup':>5}{'pred':>6}{'TP':>5}{'FP':>5}{'FN':>5}"
          f"{'prec':>9}{'recall':>9}{'F1':>9}")
    print("-" * 72)

    rows = [score_type(predicted, truth, name) for name in SCORED_TYPES]
    for row in rows:
        print(
            f"{row['anomaly_type']:<24}{row['support']:>5}{row['predicted']:>6}"
            f"{row['tp']:>5}{row['fp']:>5}{row['fn']:>5}"
            f"{row['precision']:>9.3f}{row['recall']:>9.3f}{row['f1']:>9.3f}"
        )

    total_tp = sum(row["tp"] for row in rows)
    total_fp = sum(row["fp"] for row in rows)
    total_fn = sum(row["fn"] for row in rows)
    micro_precision = (
        total_tp / (total_tp + total_fp) if total_tp + total_fp else 0.0
    )
    micro_recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 0.0
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if micro_precision + micro_recall
        else 0.0
    )
    print("-" * 72)
    print(
        f"{'MICRO AVERAGE':<24}{sum(r['support'] for r in rows):>5}"
        f"{sum(r['predicted'] for r in rows):>6}"
        f"{total_tp:>5}{total_fp:>5}{total_fn:>5}"
        f"{micro_precision:>9.3f}{micro_recall:>9.3f}{micro_f1:>9.3f}"
    )
    print("-" * 72)
    print()

    # Correctly leaving a clean order unflagged counts as correct.
    labelled = set(truth)
    flagged = set(predicted)
    correct = sum(
        1
        for order_id in orders["order_id"]
        if predicted.get(order_id) == truth.get(order_id)
    )
    accuracy = correct / total_orders if total_orders else 0.0

    print(f"match rate               : {match_rate:.3f}  "
          f"({reconciled}/{total_orders} orders joined through the ID chain)")
    print(f"classification accuracy  : {accuracy:.3f}  "
          f"({correct}/{total_orders} orders given the right label)")
    print(f"clean orders unflagged   : "
          f"{total_orders - len(labelled | flagged)}/{total_orders - len(labelled)}")
    print()

    unscored = findings[findings["anomaly_type"].isin(UNSCORED_TYPES)]
    print("unscored types (no labels exist in the answer key):")
    if unscored.empty:
        for name in UNSCORED_TYPES:
            print(f"  {name:<24} 0 findings")
    else:
        for name, count in unscored["anomaly_type"].value_counts().items():
            print(f"  {name:<24} {count} findings - reported, not scored")
    print()

    print("confidence split across scored findings:")
    for level in ("high", "medium", "low"):
        count = int((scored["confidence"] == level).sum())
        print(f"  {level:<24} {count}")
    print()

    misses = sorted(set(truth) - flagged)
    wrong = sorted(
        order_id
        for order_id in set(truth) & flagged
        if predicted[order_id] != truth[order_id]
    )
    spurious = sorted(flagged - set(truth))
    print(f"missed entirely   : {misses if misses else 'none'}")
    print(f"wrong label       : {wrong if wrong else 'none'}")
    print(f"flagged but clean : {spurious if spurious else 'none'}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
