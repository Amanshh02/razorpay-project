"""Loading, formatting and filtering for the dashboard. No Streamlit here.

This module and ``app.py`` are the whole dashboard, and neither imports
anything from ``src.matching``, ``src.detectors`` or ``src.agent``. The
dashboard is a **reader**: it opens the CSV that ``src.main`` wrote and
renders it. It never reconciles, never classifies, and never opens
``ground_truth.csv``.

That isolation is deliberate rather than incidental. A viewer that can
recompute is a viewer that can disagree with the report it is showing,
and a finance team looking at two different numbers for the same order
has no way to tell which one is real.

The report stores integer paise. Everything here converts to rupees for
display only (CLAUDE.md §8) - no converted value is written back or fed
into arithmetic.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_REPORT_DIR = ROOT / "reports"
PREFERRED_NAME = "reconciliation.csv"

#: Columns the dashboard needs. A CSV missing any of these is rejected
#: with a message rather than half-rendered.
REQUIRED_COLUMNS = (
    "order_id",
    "anomaly_type",
    "confidence",
    "expected_amount_paise",
    "actual_amount_paise",
    "delta_paise",
)

UNDERPAID = "underpaid"
OVERPAID = "overpaid"

#: Chargebacks get their own colour; everything else flagged is orange.
CHARGEBACK = "chargeback"


class ReportNotFound(FileNotFoundError):
    """No report CSV to read. The pipeline has not been run."""


class ReportMalformed(ValueError):
    """A CSV was found but does not carry the columns we need."""


def find_report(directory=DEFAULT_REPORT_DIR):
    """Locate the report CSV.

    Prefers ``reconciliation.csv``; falls back to the most recently
    modified CSV in the directory.

    Raises:
        ReportNotFound: The directory is absent or holds no CSV.
    """
    directory = Path(directory)
    if not directory.exists():
        raise ReportNotFound(f"{directory} does not exist")

    preferred = directory / PREFERRED_NAME
    if preferred.exists():
        return preferred

    candidates = sorted(
        directory.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        raise ReportNotFound(f"no CSV in {directory}")
    return candidates[0]


def load_report(path):
    """Read the report. IDs stay strings; paise stay integers.

    Raises:
        ReportMalformed: A required column is missing.
    """
    frame = pd.read_csv(path, dtype={"order_id": str}, keep_default_na=False)

    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ReportMalformed(
            f"{Path(path).name} is missing {', '.join(missing)}. "
            f"It does not look like a reconciliation report."
        )

    for column in (
        "expected_amount_paise",
        "actual_amount_paise",
        "delta_paise",
    ):
        frame[column] = pd.to_numeric(frame[column]).astype("int64")

    frame["impact_paise"] = frame["delta_paise"].abs()
    if "direction" not in frame.columns:
        frame["direction"] = frame["delta_paise"].apply(
            lambda d: OVERPAID if d > 0 else UNDERPAID
        )
    frame["explanation"] = _explanation(frame)
    return frame.sort_values("impact_paise", ascending=False).reset_index(drop=True)


def _explanation(frame):
    """The agent's sentence where it ran, the rule's reasoning otherwise."""
    agent = frame.get("agent_explanation")
    reason = frame.get("reason")
    if agent is None and reason is None:
        return ["" for _ in range(len(frame))]
    if agent is None:
        return reason.fillna("").tolist()
    if reason is None:
        return agent.fillna("").tolist()
    return [
        (a or "").strip() or (r or "").strip()
        for a, r in zip(agent.fillna(""), reason.fillna(""))
    ]


def summarise(frame):
    """Headline figures. Exposure and surplus are never netted."""
    underpaid = frame[frame["direction"] == UNDERPAID]
    overpaid = frame[frame["direction"] == OVERPAID]
    return {
        "flagged": len(frame),
        "exposure_paise": int(underpaid["impact_paise"].sum()),
        "exposure_count": len(underpaid),
        "surplus_paise": int(overpaid["impact_paise"].sum()),
        "surplus_count": len(overpaid),
    }


def by_type(frame):
    """Per-anomaly-type count and impact, heaviest first."""
    if frame.empty:
        return []
    grouped = frame.groupby("anomaly_type")["impact_paise"].agg(["count", "sum"])
    grouped = grouped.sort_values("sum", ascending=False)
    return [
        {
            "anomaly_type": name,
            "count": int(row["count"]),
            "impact_paise": int(row["sum"]),
        }
        for name, row in grouped.iterrows()
    ]


def apply_filters(frame, types=None, min_delta_paise=0):
    """Filter by anomaly type and minimum absolute delta."""
    filtered = frame
    if types:
        filtered = filtered[filtered["anomaly_type"].isin(types)]
    if min_delta_paise:
        filtered = filtered[filtered["impact_paise"] >= min_delta_paise]
    return filtered.reset_index(drop=True)


def to_rupees(paise):
    """Paise to rupees as a float. Display only - never fed back in."""
    return paise / 100


def format_indian(paise, *, symbol="Rs "):
    """Render paise as rupees with Indian digit grouping.

    ``48191930`` becomes ``Rs 4,81,919.30`` - last three digits, then
    pairs. Western grouping would read ``481,919.30``, which is wrong
    for the audience this is built for.
    """
    negative = paise < 0
    whole, fraction = divmod(abs(int(paise)), 100)
    digits = str(whole)

    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        pairs = []
        while len(head) > 2:
            pairs.insert(0, head[-2:])
            head = head[:-2]
        if head:
            pairs.insert(0, head)
        digits = ",".join(pairs) + "," + tail

    return f"{'-' if negative else ''}{symbol}{digits}.{fraction:02d}"
