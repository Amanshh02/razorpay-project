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


#: Loader per ledger, in the order the pipeline reads them.
_LOADERS = (
    ("orders.csv", load_orders),
    ("payments.csv", load_payments),
    ("fees.csv", load_fees),
    ("settlements.csv", load_settlements),
)


def run(data_dir, out_dir, *, use_agent=False, use_cache=True, on_step=None):
    """Load, match, detect, optionally classify, then report.

    Args:
        on_step: Optional callback invoked with a dict after each real
            step completes — ``{"phase": ..., ...}``. It reports work
            already done, never work about to start, so a caller cannot
            display a step that did not happen. The pipeline is defined
            here once; observers watch it rather than restating it.

    Returns:
        ``(report, summary, csv_path)``.
    """
    def emit(phase, **detail):
        if on_step is not None:
            on_step({"phase": phase, **detail})

    data_dir = Path(data_dir)
    missing = [name for name in LEDGERS if not (data_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"{data_dir} is missing {', '.join(missing)}. "
            f"Expected all four ledgers: {', '.join(LEDGERS)}."
        )

    frames = {}
    for name, loader in _LOADERS:
        frames[name] = loader(data_dir / name)
        emit("load", ledger=name, rows=len(frames[name]))

    orders = frames["orders.csv"]
    matched = match_ledgers(
        orders,
        frames["payments.csv"],
        frames["fees.csv"],
        frames["settlements.csv"],
    )
    emit(
        "match",
        orders=len(orders),
        reconciled=len(matched.reconciled),
        unreconciled=len(matched.unreconciled),
    )

    detectors = (
        ("chargeback", lambda: detect_chargebacks(matched.reconciled)),
        ("refund_not_reflected", lambda: detect_refunds(matched.reconciled)),
        ("settlement_shortfall", lambda: detect_settlement_shortfalls(matched.reconciled)),
        ("settlement_excess", lambda: detect_overpayments(matched.reconciled)),
        ("payment_not_received", lambda: detect_missing_payments(matched.unreconciled, orders)),
    )
    parts = []
    for anomaly_type, detect in detectors:
        found = detect()
        parts.append(found)
        emit("detect", anomaly_type=anomaly_type, found=len(found))
    findings = pd.concat(parts, ignore_index=True)

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
        emit(
            "classify",
            routed=len(decisions),
            overridden=sum(1 for d in decisions if d["action"] == "overridden"),
        )

    report = build_report(findings, decisions, matched.reconciled)
    summary = summarise(report, matched, orders)
    csv_path = write_csv(report, Path(out_dir) / "reconciliation.csv")
    emit(
        "report",
        flagged=summary["flagged"],
        exposure_paise=summary["exposure_paise"],
        surplus_paise=summary["surplus_paise"],
        csv_path=str(csv_path),
    )
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
