"""Read-only reconciliation dashboard.

    streamlit run src/dashboard/app.py

Reads the CSV that ``python -m src.main`` writes into ``reports/`` and
renders it. **This layer imports nothing from src.matching,
src.detectors or src.agent**, never runs reconciliation, and never opens
``ground_truth.csv``. If there is no report, it says so and stops rather
than inventing data to fill the screen.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Running under `streamlit run` puts src/dashboard/ on sys.path, not the
# project root, so the sibling import below needs the root added first.
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard.data import (  # noqa: E402
    CHARGEBACK,
    DEFAULT_REPORT_DIR,
    ReportMalformed,
    ReportNotFound,
    apply_filters,
    by_type,
    find_report,
    format_indian,
    load_report,
    summarise,
    to_rupees,
)

BACKGROUND = "#0A0A0A"
NEON = "#39FF14"
ORANGE = "#FF6B00"
RED = "#FF3B30"
MUTED = "#8A8A8A"
SURFACE = "#141414"
MONO = "'JetBrains Mono', 'SF Mono', Consolas, 'Courier New', monospace"

st.set_page_config(
    page_title="AI Finance Controller",
    page_icon="::",
    layout="wide",
)

st.markdown(
    f"""
    <style>
      .stApp {{ background: {BACKGROUND}; }}
      section[data-testid="stSidebar"] {{
          background: {SURFACE};
          border-right: 1px solid #222;
      }}
      .fc-title {{
          font-size: 0.78rem; letter-spacing: 0.18em; text-transform: uppercase;
          color: {MUTED}; margin-bottom: 0.2rem;
      }}
      .fc-exposure {{
          font-family: {MONO}; font-size: 2.9rem; font-weight: 700;
          color: {NEON}; line-height: 1.1;
      }}
      .fc-surplus {{
          font-family: {MONO}; font-size: 1.15rem; color: {MUTED};
      }}
      .fc-sub {{ color: {MUTED}; font-size: 0.9rem; }}
      .fc-card {{
          background: {SURFACE}; border: 1px solid #222;
          border-left: 3px solid {ORANGE};
          border-radius: 6px; padding: 0.85rem 1rem; height: 100%;
      }}
      .fc-card.chargeback {{ border-left-color: {RED}; }}
      .fc-card .name {{
          font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase;
          color: {MUTED};
      }}
      .fc-card .amount {{
          font-family: {MONO}; font-size: 1.3rem; color: #EDEDED; font-weight: 600;
      }}
      .fc-card .count {{ font-size: 0.8rem; color: {ORANGE}; }}
      .fc-card.chargeback .count {{ color: {RED}; }}
      /* Monospace the grid so digits line up column to column. */
      div[data-testid="stDataFrame"] * {{ font-family: {MONO} !important; }}
      hr {{ border-color: #222; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def empty_state(message):
    """No report to show. Say what to run; do not fabricate anything."""
    st.markdown(
        f'<div class="fc-title">AI Finance Controller</div>', unsafe_allow_html=True
    )
    st.markdown(f"### No reconciliation report found")
    st.write(message)
    st.markdown("Generate one first:")
    st.code(
        "python -m src.main --data tests/fixtures --out reports/\n\n"
        "# or, with the agent classification pass\n"
        "python -m src.main --data tests/fixtures --out reports/ --agent",
        language="bash",
    )
    st.caption(
        "This dashboard is read-only. It renders the report the pipeline "
        "writes and never runs reconciliation itself."
    )
    st.stop()


try:
    report_path = find_report()
    frame = load_report(report_path)
except ReportNotFound:
    empty_state(
        f"Nothing to read in `{DEFAULT_REPORT_DIR}`. The pipeline has not "
        f"been run, or its output was written somewhere else."
    )
except ReportMalformed as exc:
    empty_state(str(exc))


# --- sidebar filters -------------------------------------------------
st.sidebar.markdown('<div class="fc-title">Filters</div>', unsafe_allow_html=True)

all_types = sorted(frame["anomaly_type"].unique())
chosen = st.sidebar.multiselect("Anomaly type", all_types, default=all_types)

largest = int(frame["impact_paise"].max()) if not frame.empty else 0
max_rupees = int(to_rupees(largest)) + 1
min_rupees = st.sidebar.slider(
    "Minimum absolute delta (Rs)",
    min_value=0,
    max_value=max_rupees,
    value=0,
    step=max(1, max_rupees // 200),
)

visible = apply_filters(frame, chosen, int(min_rupees * 100))

st.sidebar.markdown("---")
st.sidebar.caption(f"Source: `{report_path.name}`")
st.sidebar.caption(f"{len(visible)} of {len(frame)} flags shown")
st.sidebar.caption("Read-only. Amounts are stored in paise and shown in rupees.")


# --- header ----------------------------------------------------------
totals = summarise(frame)

st.markdown('<div class="fc-title">AI Finance Controller</div>', unsafe_allow_html=True)
left, right = st.columns([3, 2])
with left:
    st.markdown(
        f'<div class="fc-exposure">{format_indian(totals["exposure_paise"])}</div>'
        f'<div class="fc-sub">total exposure across '
        f'{totals["exposure_count"]} underpaid orders '
        f'&middot; {totals["flagged"]} flagged in all</div>',
        unsafe_allow_html=True,
    )
with right:
    if totals["surplus_count"]:
        st.markdown(
            f'<div class="fc-sub">overpaid, reported separately</div>'
            f'<div class="fc-surplus">{format_indian(totals["surplus_paise"])}</div>'
            f'<div class="fc-sub">{totals["surplus_count"]} orders &middot; '
            f'never netted against exposure</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="fc-sub">no overpayments in this report</div>',
            unsafe_allow_html=True,
        )

st.markdown("---")


# --- summary cards ---------------------------------------------------
groups = by_type(frame)
if groups:
    for row, chunk in enumerate(range(0, len(groups), 4)):
        for column, group in zip(st.columns(4), groups[chunk:chunk + 4]):
            variant = "chargeback" if group["anomaly_type"] == CHARGEBACK else ""
            with column:
                st.markdown(
                    f'<div class="fc-card {variant}">'
                    f'<div class="name">{group["anomaly_type"].replace("_", " ")}</div>'
                    f'<div class="amount">{format_indian(group["impact_paise"])}</div>'
                    f'<div class="count">{group["count"]} flags</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

st.markdown("")


# --- table -----------------------------------------------------------
st.markdown('<div class="fc-title">Flagged orders</div>', unsafe_allow_html=True)

if visible.empty:
    st.info("No flags match the current filters.")
else:
    table = pd.DataFrame({
        "Order": visible["order_id"],
        "Anomaly": visible["anomaly_type"].str.replace("_", " "),
        "Expected": visible["expected_amount_paise"].map(to_rupees),
        "Actual": visible["actual_amount_paise"].map(to_rupees),
        "Delta": visible["delta_paise"].map(to_rupees),
        "Confidence": visible["confidence"],
        "Explanation": visible["explanation"],
    })
    money = st.column_config.NumberColumn(format="%.2f", width="small")
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={
            "Expected": money,
            "Actual": money,
            "Delta": st.column_config.NumberColumn(format="%.2f", width="small"),
            "Explanation": st.column_config.TextColumn(width="large"),
        },
    )
    st.caption(
        "Sorted by absolute delta, largest first. Click any header to re-sort. "
        "Amounts are rupees, converted from integer paise for display only."
    )
