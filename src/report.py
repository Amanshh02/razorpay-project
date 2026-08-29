"""Reconciliation report: what was flagged, what it costs, why.

Groups findings by anomaly type, orders both the groups and the rows
within them by rupee impact descending, and leads with total exposure -
the number a finance team acts on first.

Money handling follows CLAUDE.md §8. Every amount stays integer paise
through the whole pipeline; the rupee columns and the console output are
rendered at the last possible moment and nothing downstream reads them.

Exposure and surplus are reported separately and never netted. An
underpayment is money missing; an overpayment is money that may be
clawed back later. Summing them into one figure would let a large
overpayment mask a large shortfall, which is exactly the failure this
project exists to catch.
"""

from __future__ import annotations

import pandas as pd

from .detectors import rupees

#: CSV schema. Paise columns are authoritative; rupee columns are display.
REPORT_COLUMNS = (
    "order_id",
    "anomaly_type",
    "confidence",
    "expected_amount_paise",
    "actual_amount_paise",
    "delta_paise",
    "impact_paise",
    "impact_rupees",
    "direction",
    "agent_explanation",
    "reason",
)

UNDERPAID = "underpaid"
OVERPAID = "overpaid"


def build_report(findings, decisions=None):
    """Order findings for a human: worst type first, worst row first.

    Args:
        findings: The findings frame from the detectors, optionally
            already passed through the agent layer.
        decisions: The agent's decision list, when it ran. Supplies the
            ``agent_explanation`` column - the sentence a finance person
            actually acts on.

    Returns:
        A DataFrame with :data:`REPORT_COLUMNS`.
    """
    if findings.empty:
        return pd.DataFrame({column: [] for column in REPORT_COLUMNS})

    report = findings.copy()
    report["impact_paise"] = report["delta_paise"].abs()
    report["direction"] = report["delta_paise"].apply(
        lambda delta: OVERPAID if delta > 0 else UNDERPAID
    )
    report["impact_rupees"] = report["impact_paise"].apply(
        lambda paise: f"{paise / 100:.2f}"
    )
    report["agent_explanation"] = _explanations(report["order_id"], decisions)

    # Groups ordered by what they cost, rows inside them likewise.
    weight = report.groupby("anomaly_type")["impact_paise"].sum()
    report["_group_weight"] = report["anomaly_type"].map(weight)
    report = report.sort_values(
        ["_group_weight", "anomaly_type", "impact_paise"],
        ascending=[False, True, False],
    )
    return report[list(REPORT_COLUMNS)].reset_index(drop=True)


def _explanations(order_ids, decisions):
    """Map each order to the agent's sentence, blank where it did not run."""
    if not decisions:
        return ["" for _ in order_ids]
    by_order = {
        decision["order_id"]: decision.get("explanation") or ""
        for decision in decisions
    }
    return [by_order.get(order_id, "") for order_id in order_ids]


def summarise(report, matched, orders):
    """Headline figures. Exposure and surplus stay separate."""
    underpaid = report[report["direction"] == UNDERPAID]
    overpaid = report[report["direction"] == OVERPAID]

    unreconciled_orders = matched.unreconciled[
        matched.unreconciled["source_ledger"] == "orders"
    ]
    return {
        "orders": len(orders),
        "reconciled": len(matched.reconciled),
        "unreconciled": len(unreconciled_orders),
        "flagged": len(report),
        "clean": len(orders) - len(report),
        "exposure_paise": int(underpaid["impact_paise"].sum()),
        "exposure_count": len(underpaid),
        "surplus_paise": int(overpaid["impact_paise"].sum()),
        "surplus_count": len(overpaid),
    }


def render_console(report, summary, *, top=5):
    """The readable summary. Returns the text rather than printing it."""
    width = 74
    lines = [
        "=" * width,
        "RECONCILIATION REPORT",
        "=" * width,
        f"{'orders read':<24}{summary['orders']:>12}",
        f"{'matched through the chain':<24}{summary['reconciled']:>12}",
        f"{'could not be matched':<24}{summary['unreconciled']:>12}",
        f"{'flagged':<24}{summary['flagged']:>12}",
        f"{'clean':<24}{summary['clean']:>12}",
        "",
        f"{'TOTAL EXPOSURE':<24}{rupees(summary['exposure_paise']):>20}"
        f"   across {summary['exposure_count']} flags",
    ]
    if summary["surplus_count"]:
        lines.append(
            f"{'overpaid (not netted)':<24}"
            f"{rupees(summary['surplus_paise']):>20}"
            f"   across {summary['surplus_count']} flags"
        )
    lines += ["", "-" * width, "BY ANOMALY TYPE, rupee impact descending", "-" * width]

    if report.empty:
        lines.append("nothing flagged")
    else:
        lines.append(
            f"{'anomaly type':<26}{'flags':>7}{'impact':>20}{'largest single':>20}"
        )
        lines.append("-" * width)
        grouped = report.groupby("anomaly_type", sort=False)
        for anomaly_type, rows in grouped:
            lines.append(
                f"{anomaly_type:<26}{len(rows):>7}"
                f"{rupees(int(rows['impact_paise'].sum())):>20}"
                f"{rupees(int(rows['impact_paise'].max())):>20}"
            )
        lines += ["-" * width, "", f"LARGEST {top} FLAGS", "-" * width]
        for row in report.nlargest(top, "impact_paise").itertuples():
            lines.append(
                f"{row.order_id:<14}{row.anomaly_type:<24}"
                f"{rupees(row.impact_paise):>16}  {row.confidence}"
            )
            detail = row.agent_explanation or row.reason
            lines.append(f"    {detail[:66]}")

    lines.append("=" * width)
    return "\n".join(lines)


def write_csv(report, path):
    """Write the report. Paise columns are the record of truth."""
    path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(path, index=False, lineterminator="\n")
    return path
