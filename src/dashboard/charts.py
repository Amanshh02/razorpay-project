"""Chart construction. Plotly figures only — no Streamlit, no engine.

Kept separate from ``app.py`` so the figures can be built and asserted
against in a test without starting a server, the same reason ``data.py``
is separate.

Every figure is built from the report CSV that the pipeline already
wrote. Nothing here computes a finding or reinterprets an amount; the
histogram's ratio is derived from the delta and the payment, both of
which are read, not recalculated.
"""

from __future__ import annotations

import plotly.graph_objects as go

BACKGROUND = "#0A0A0A"
SURFACE = "#141414"
NEON = "#39FF14"
ORANGE = "#FF6B00"
RED = "#FF3B30"
MUTED = "#8A8A8A"
GRID = "#222222"
MONO = "JetBrains Mono, SF Mono, Consolas, Courier New, monospace"

CHARGEBACK = "chargeback"


def _base_layout(fig, *, height=320, title=None):
    """Dark theme shared by every figure."""
    fig.update_layout(
        height=height,
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        font=dict(family=MONO, color=MUTED, size=12),
        margin=dict(l=10, r=20, t=40 if title else 12, b=10),
        title=dict(text=title, font=dict(color=NEON, size=13)) if title else None,
        showlegend=False,
        hoverlabel=dict(bgcolor=SURFACE, font=dict(family=MONO, color="#EDEDED")),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=NEON,
                     tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=NEON,
                     tickfont=dict(color=MUTED))
    return fig


def exposure_by_type(groups, format_money):
    """Horizontal bars of rupee impact per anomaly type, largest first.

    Args:
        groups: rows from ``data.by_type`` — already sorted by impact.
        format_money: callable rendering paise for the hover label.
    """
    ordered = list(reversed(groups))  # plotly draws bottom-up
    labels = [g["anomaly_type"].replace("_", " ") for g in ordered]
    values = [g["impact_paise"] / 100 for g in ordered]
    colours = [
        RED if g["anomaly_type"] == CHARGEBACK else ORANGE for g in ordered
    ]
    hover = [
        f"{g['anomaly_type'].replace('_', ' ')}<br>"
        f"{format_money(g['impact_paise'])}<br>{g['count']} flags"
        for g in ordered
    ]

    fig = go.Figure(
        go.Bar(
            x=values, y=labels, orientation="h",
            marker=dict(color=colours),
            hovertext=hover, hoverinfo="text",
            text=[format_money(g["impact_paise"]) for g in ordered],
            textposition="outside",
            textfont=dict(color=MUTED, family=MONO, size=11),
        )
    )
    _base_layout(fig, height=60 + 44 * max(len(ordered), 1),
                 title="Rupee exposure by anomaly type")
    fig.update_xaxes(title_text="rupees", rangemode="tozero")
    return fig


def shortfall_ratio_histogram(ratios, labels, threshold):
    """Distribution of shortfall-to-payment ratios, with the threshold marked.

    This is the figure that shows *why* the refund/shortfall split is a
    judgement rather than a fact: the two classes overlap, and the
    threshold line lands inside the overlap rather than between two
    separated groups.
    """
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=ratios, nbinsx=28,
            marker=dict(color=ORANGE, line=dict(color=BACKGROUND, width=1)),
            hovertemplate="ratio %{x:.2f}<br>%{y} orders<extra></extra>",
        )
    )
    fig.add_vline(
        x=threshold, line=dict(color=NEON, width=2, dash="dash"),
        annotation_text=f"refund threshold {threshold:.0%}",
        annotation_position="top right",
        annotation_font=dict(color=NEON, family=MONO, size=11),
    )
    _base_layout(fig, height=300,
                 title="Shortfall as a fraction of payment captured")
    fig.update_xaxes(title_text="shortfall / payment", tickformat=".0%")
    fig.update_yaxes(title_text="orders")
    return fig


def count_vs_impact(groups, format_money):
    """Scatter separating 'a few huge flags' from 'many small ones'.

    Position alone carries the meaning: far right is many flags, far up
    is expensive. A point high and left is the case worth opening first
    — few orders, large money.
    """
    fig = go.Figure()
    for g in groups:
        is_cb = g["anomaly_type"] == CHARGEBACK
        fig.add_trace(
            go.Scatter(
                x=[g["count"]], y=[g["impact_paise"] / 100],
                mode="markers+text",
                marker=dict(
                    size=18, color=RED if is_cb else ORANGE,
                    line=dict(color=BACKGROUND, width=2),
                ),
                text=[g["anomaly_type"].replace("_", " ")],
                textposition="middle right",
                textfont=dict(color=MUTED, family=MONO, size=10),
                hovertext=[
                    f"{g['count']} flags<br>{format_money(g['impact_paise'])}"
                ],
                hoverinfo="text",
            )
        )
    _base_layout(fig, height=320, title="Flag count against rupee impact")
    fig.update_xaxes(title_text="number of flags", rangemode="tozero")
    fig.update_yaxes(title_text="rupees", rangemode="tozero")
    return fig
