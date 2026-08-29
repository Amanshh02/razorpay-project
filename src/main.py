"""CLI entry point: run the pipeline and write a reconciliation report.

    python -m src.main --data data/ --out reports/
    python -m src.main --data tests/fixtures --out reports/ --agent

Rules-only by default, so it runs with no API key and no network call.
``--agent`` adds the stage 6 classification pass over the medium- and
low-confidence findings.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .detectors import (
    detect_chargebacks,
    detect_missing_payments,
    detect_overpayments,
    detect_refunds,
    detect_settlement_shortfalls,
)
from .loaders import load_fees, load_orders, load_payments, load_settlements
from .matching import match_ledgers
from .report import build_report, render_console, summarise, write_csv

LEDGERS = ("orders.csv", "payments.csv", "fees.csv", "settlements.csv")


def run(data_dir, out_dir, *, use_agent=False, use_cache=True):
    """Load, match, detect, optionally classify, then report.

    Returns:
        ``(report, summary, csv_path)``.
    """
    data_dir = Path(data_dir)
    missing = [name for name in LEDGERS if not (data_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"{data_dir} is missing {', '.join(missing)}. "
            f"Expected all four ledgers: {', '.join(LEDGERS)}."
        )

    orders = load_orders(data_dir / "orders.csv")
    matched = match_ledgers(
        orders,
        load_payments(data_dir / "payments.csv"),
        load_fees(data_dir / "fees.csv"),
        load_settlements(data_dir / "settlements.csv"),
    )
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

    decisions = None
    if use_agent:
        # Imported here so the default path needs no SDK and no API key.
        from .agent import ResponseCache, build_client, classify

        findings, decisions = classify(
            findings,
            matched.reconciled,
            build_client(),
            ResponseCache(enabled=use_cache),
        )

    report = build_report(findings, decisions)
    summary = summarise(report, matched, orders)
    csv_path = write_csv(report, Path(out_dir) / "reconciliation.csv")
    return report, summary, csv_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/", help="directory holding the four ledger CSVs")
    parser.add_argument("--out", default="reports/", help="directory to write the report into")
    parser.add_argument("--agent", action="store_true", help="run the agent classification pass")
    parser.add_argument("--no-cache", action="store_true", help="ignore the LLM response cache")
    args = parser.parse_args(argv)

    try:
        report, summary, csv_path = run(
            args.data, args.out, use_agent=args.agent, use_cache=not args.no_cache
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(render_console(report, summary))
    print(f"\nwritten: {csv_path}  ({len(report)} rows)")

    if summary["unreconciled"] > len(report[report["anomaly_type"] == "payment_not_received"]):
        print(
            "note: some unmatched rows produced no finding - "
            "see the unreconciled bucket from the matcher."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
