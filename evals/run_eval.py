"""Accuracy harness. The source of truth for every number we report.

Runs the full pipeline over a labelled fixture set and scores its
findings against that set's ``ground_truth.csv``.

**This is the only file in the project permitted to read
``ground_truth.csv``** (CLAUDE.md §11 and §13). No loader, matcher or
detector may reference it. If detection logic ever needs the answer key
to work, the accuracy numbers it produces are meaningless.

Two sets, scored separately
---------------------------
- **easy** - ``tests/fixtures/``, 130 orders. The regression baseline.
  The rules were written against these, and they score perfectly, which
  is a statement about the fixtures rather than the detectors.
- **hard** - ``tests/fixtures/hard/``, 40 orders built to break the
  current rules on purpose: refunds under the threshold, shortfalls over
  it, chargebacks with a non-standard fee. **These are meant to fail.**
  The gap between the two sets is the headroom the agent layer has to
  close, and tuning the rules to close it here would just move the
  overfitting from one set to the other.

Scoring
-------
Which types are scored is derived per set from that set's answer key. A
type the pipeline can emit but the key never labels is **counted and
reported separately, never scored** - treating it as a false positive
would penalise the pipeline for finding something the key was not built
to describe. ``settlement_excess`` is unlabelled in the easy set and
labelled in the hard one, and is handled correctly in both without a
special case.

Two overall figures are printed per set, because they measure different
things:

- **match rate** - the share of input orders the matcher could join
  through the whole ID chain. A coverage measure.
- **classification accuracy** - the share of all orders given the right
  label, counting correctly-unflagged clean orders as correct.

Usage::

    python evals/run_eval.py            # rules only (the v0.1 baseline)
    python evals/run_eval.py --agent    # + stage 6 agent classification

Without ``--agent`` no API key is needed and no network call is made, so
the rules-only numbers stay reproducible anywhere.
"""

from __future__ import annotations

import argparse
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

#: Canonical ordering of every type the pipeline can emit.
ANOMALY_TYPES = (
    "refund_not_reflected",
    "chargeback",
    "settlement_shortfall",
    "payment_not_received",
    "settlement_excess",
)

#: (label, directory) for each labelled set, scored independently.
SETS = (
    ("easy", FIXTURES),
    ("hard", FIXTURES / "hard"),
)


def run_pipeline(fixtures):
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


def load_ground_truth(fixtures):
    """Read a set's answer key. Nothing outside this module may do this."""
    return pd.read_csv(
        fixtures / "ground_truth.csv", dtype=str, keep_default_na=False
    )


def scored_types(truth):
    """The types this answer key actually labels, in canonical order.

    Derived rather than hardcoded so a type the key never mentions is
    never scored against labels that do not exist.
    """
    present = set(truth.values())
    return tuple(name for name in ANOMALY_TYPES if name in present)


def score_type(predicted, truth, anomaly_type):
    """Precision, recall and F1 for one anomaly type, keyed on order_id."""
    got = {
        order_id for order_id, label in predicted.items() if label == anomaly_type
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
        2 * precision * recall / (precision + recall) if precision + recall else 0.0
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


def evaluate(label, fixtures, agent=None, cache=None):
    """Score one fixture set and print its block. Returns a summary dict."""
    findings, matched, orders = run_pipeline(fixtures)
    decisions = []
    if agent is not None:
        from src.agent import classify

        findings, decisions = classify(findings, matched.reconciled, agent, cache)
    truth_frame = load_ground_truth(fixtures)
    truth = dict(zip(truth_frame["order_id"], truth_frame["anomaly_type"]))

    scored_names = scored_types(truth)
    unscored_names = tuple(n for n in ANOMALY_TYPES if n not in scored_names)

    scored = findings[findings["anomaly_type"].isin(scored_names)]
    predicted = dict(zip(scored["order_id"], scored["anomaly_type"]))

    total_orders = len(orders)
    reconciled = len(matched.reconciled)
    match_rate = reconciled / total_orders if total_orders else 0.0

    print("=" * 74)
    print(f"SET: {label.upper()}   {fixtures}")
    print("=" * 74)
    print(f"orders {total_orders} | labelled anomalies {len(truth_frame)} | "
          f"findings {len(findings)} ({len(scored)} scored)")
    print()
    print("-" * 74)
    print(f"{'anomaly type':<24}{'sup':>5}{'pred':>6}{'TP':>5}{'FP':>5}{'FN':>5}"
          f"{'prec':>9}{'recall':>9}{'F1':>9}")
    print("-" * 74)

    rows = [score_type(predicted, truth, name) for name in scored_names]
    for row in rows:
        print(
            f"{row['anomaly_type']:<24}{row['support']:>5}{row['predicted']:>6}"
            f"{row['tp']:>5}{row['fp']:>5}{row['fn']:>5}"
            f"{row['precision']:>9.3f}{row['recall']:>9.3f}{row['f1']:>9.3f}"
        )

    total_tp = sum(row["tp"] for row in rows)
    total_fp = sum(row["fp"] for row in rows)
    total_fn = sum(row["fn"] for row in rows)
    micro_p = total_tp / (total_tp + total_fp) if total_tp + total_fp else 0.0
    micro_r = total_tp / (total_tp + total_fn) if total_tp + total_fn else 0.0
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if micro_p + micro_r else 0.0

    print("-" * 74)
    print(
        f"{'MICRO AVERAGE':<24}{sum(r['support'] for r in rows):>5}"
        f"{sum(r['predicted'] for r in rows):>6}"
        f"{total_tp:>5}{total_fp:>5}{total_fn:>5}"
        f"{micro_p:>9.3f}{micro_r:>9.3f}{micro_f1:>9.3f}"
    )
    print("-" * 74)
    print()

    correct = sum(
        1
        for order_id in orders["order_id"]
        if predicted.get(order_id) == truth.get(order_id)
    )
    accuracy = correct / total_orders if total_orders else 0.0
    print(f"match rate              : {match_rate:.3f}  "
          f"({reconciled}/{total_orders} joined through the ID chain)")
    print(f"classification accuracy : {accuracy:.3f}  "
          f"({correct}/{total_orders} given the right label)")

    unscored = findings[findings["anomaly_type"].isin(unscored_names)]
    if unscored_names:
        print()
        print("unscored (no labels in this key):")
        for name in unscored_names:
            count = int((unscored["anomaly_type"] == name).sum())
            print(f"  {name:<24} {count} findings - reported, not scored")

    if decisions:
        _print_agent_block(decisions, truth)

    flagged = set(predicted)
    misses = sorted(set(truth) - flagged)
    wrong = sorted(
        order_id
        for order_id in set(truth) & flagged
        if predicted[order_id] != truth[order_id]
    )
    spurious = sorted(flagged - set(truth))
    print()
    print(f"missed entirely   ({len(misses):>2}): {', '.join(misses) if misses else 'none'}")
    print(f"wrong label       ({len(wrong):>2}): {', '.join(wrong) if wrong else 'none'}")
    print(f"flagged but clean ({len(spurious):>2}): {', '.join(spurious) if spurious else 'none'}")

    if wrong:
        print()
        print("  what the wrong labels became:")
        for order_id in wrong:
            print(f"    {order_id}: truth={truth[order_id]:<22} "
                  f"predicted={predicted[order_id]}")
    print()

    return {
        "label": label,
        "rows": {row["anomaly_type"]: row for row in rows},
        "match_rate": match_rate,
        "accuracy": accuracy,
        "micro_f1": micro_f1,
        "micro_recall": micro_r,
    }


def _print_agent_block(decisions, truth):
    """What the agent did, and whether each move helped or hurt."""
    from src.agent import CONFIRMED, OVERRIDDEN, OVERRIDE_REJECTED, UNPARSEABLE

    counts = {}
    for decision in decisions:
        counts[decision["action"]] = counts.get(decision["action"], 0) + 1

    print()
    print(f"agent: {len(decisions)} findings routed (medium/low confidence only)")
    for action in (CONFIRMED, OVERRIDDEN, OVERRIDE_REJECTED, UNPARSEABLE):
        if counts.get(action):
            print(f"  {action:<20} {counts[action]}")

    moved = [d for d in decisions if d["action"] == OVERRIDDEN]
    if moved:
        print()
        print("  overrides, and whether each was right:")
        for decision in moved:
            want = truth.get(decision["order_id"])
            before = decision["rule_label"] == want
            after = decision["applied_label"] == want
            verdict = (
                "FIXED" if after and not before
                else "BROKE" if before and not after
                else "no change"
            )
            print(f"    {decision['order_id']}: {decision['rule_label']} -> "
                  f"{decision['applied_label']}  [{verdict}]")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent", action="store_true",
        help="route medium/low confidence findings through the agent layer",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="ignore the response cache and re-bill every call",
    )
    args = parser.parse_args()

    agent = cache = None
    if args.agent:
        from src.agent import ResponseCache, build_client

        agent = build_client()
        cache = ResponseCache(enabled=not args.no_cache)
        print(f"agent enabled: model {agent.model}")
        print()

    summaries = [
        evaluate(label, directory, agent, cache) for label, directory in SETS
    ]
    if cache is not None:
        print(f"cache: {cache.summary()}")

    print("=" * 74)
    print("SUMMARY")
    print("=" * 74)
    header = f"{'metric':<26}" + "".join(f"{s['label']:>12}" for s in summaries)
    print(header)
    print("-" * 74)
    for name in ANOMALY_TYPES:
        cells = ""
        for summary in summaries:
            row = summary["rows"].get(name)
            # ASCII only: this table is read in terminals whose encoding
            # mangles anything else.
            cells += f"{row['f1']:>12.3f}" if row else f"{'n/a':>12}"
        print(f"{name + ' F1':<26}{cells}")
    print("-" * 74)
    for key, title in (
        ("micro_recall", "micro recall"),
        ("micro_f1", "micro F1"),
        ("accuracy", "classification accuracy"),
        ("match_rate", "match rate"),
    ):
        print(f"{title:<26}" + "".join(f"{s[key]:>12.3f}" for s in summaries))
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
