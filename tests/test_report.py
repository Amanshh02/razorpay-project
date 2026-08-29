"""Tests for the reconciliation report.

Uses the hand-built detector fixtures, which contain both an
underpayment and an overpayment, so exposure and surplus can be told
apart. No network, no API key.
"""

from pathlib import Path

import pandas as pd
import pytest

from src.detectors import (
    detect_chargebacks,
    detect_missing_payments,
    detect_overpayments,
    detect_refunds,
    detect_settlement_shortfalls,
)
from src.loaders import load_fees, load_orders, load_payments, load_settlements
from src.main import run
from src.matching import match_ledgers
from src.report import (
    OVERPAID,
    REPORT_COLUMNS,
    UNDERPAID,
    build_report,
    render_console,
    summarise,
    write_csv,
)

FIXTURES = Path(__file__).parent / "fixtures"
DETECTOR_FIXTURES = FIXTURES / "detectors"


def _pipeline(directory):
    orders = load_orders(directory / "orders.csv")
    matched = match_ledgers(
        orders,
        load_payments(directory / "payments.csv"),
        load_fees(directory / "fees.csv"),
        load_settlements(directory / "settlements.csv"),
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
    return findings, matched, orders


@pytest.fixture
def bench():
    return _pipeline(DETECTOR_FIXTURES)


@pytest.fixture
def real():
    return _pipeline(FIXTURES)


# --------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------

def test_report_schema(bench):
    findings, _, _ = bench
    report = build_report(findings)
    assert list(report.columns) == list(REPORT_COLUMNS)
    assert len(report) == len(findings)


def test_empty_findings_still_produce_a_shaped_report():
    empty = pd.DataFrame({
        "order_id": [], "anomaly_type": [], "expected_amount_paise": [],
        "actual_amount_paise": [], "delta_paise": [], "confidence": [], "reason": [],
    })
    report = build_report(empty)
    assert report.empty
    assert list(report.columns) == list(REPORT_COLUMNS)


def test_every_finding_appears_exactly_once(real):
    findings, _, _ = real
    report = build_report(findings)
    assert sorted(report["order_id"]) == sorted(findings["order_id"])


# --------------------------------------------------------------------
# Ordering
# --------------------------------------------------------------------

def test_rows_are_sorted_by_impact_within_each_group(real):
    findings, _, _ = real
    report = build_report(findings)
    for _, group in report.groupby("anomaly_type", sort=False):
        assert group["impact_paise"].is_monotonic_decreasing


def test_groups_are_ordered_by_total_impact(real):
    findings, _, _ = real
    report = build_report(findings)
    order = list(dict.fromkeys(report["anomaly_type"]))
    totals = [
        int(report.loc[report["anomaly_type"] == name, "impact_paise"].sum())
        for name in order
    ]
    assert totals == sorted(totals, reverse=True)


def test_each_type_forms_one_contiguous_block(real):
    """Grouping must not interleave types."""
    findings, _, _ = real
    report = build_report(findings)
    seen = []
    for name in report["anomaly_type"]:
        if not seen or seen[-1] != name:
            seen.append(name)
    assert len(seen) == len(set(seen))


# --------------------------------------------------------------------
# Money
# --------------------------------------------------------------------

def test_impact_is_the_absolute_delta(real):
    findings, _, _ = real
    report = build_report(findings)
    assert (report["impact_paise"] == report["delta_paise"].abs()).all()


def test_amounts_are_carried_through_untouched(real):
    findings, _, _ = real
    report = build_report(findings).set_index("order_id")
    source = findings.set_index("order_id")
    for column in ("expected_amount_paise", "actual_amount_paise", "delta_paise"):
        assert (report[column].sort_index() == source[column].sort_index()).all()


def test_rupee_column_is_display_only_and_derived(real):
    findings, _, _ = real
    report = build_report(findings)
    for row in report.itertuples():
        assert row.impact_rupees == f"{row.impact_paise / 100:.2f}"


def test_exposure_and_surplus_are_never_netted(bench):
    """An overpayment must not cancel out an underpayment."""
    findings, matched, orders = bench
    report = build_report(findings)
    summary = summarise(report, matched, orders)

    assert summary["surplus_count"] == 1
    assert summary["surplus_paise"] == 25000
    assert summary["exposure_count"] == len(report) - 1

    underpaid = report[report["direction"] == UNDERPAID]
    assert summary["exposure_paise"] == int(underpaid["impact_paise"].sum())
    # Netting would have subtracted the surplus. It must not.
    assert summary["exposure_paise"] > summary["exposure_paise"] - 25000


def test_direction_matches_the_sign_of_the_delta(bench):
    findings, _, _ = bench
    report = build_report(findings)
    for row in report.itertuples():
        expected = OVERPAID if row.delta_paise > 0 else UNDERPAID
        assert row.direction == expected


def test_exposure_on_the_real_set(real):
    findings, matched, orders = real
    report = build_report(findings)
    summary = summarise(report, matched, orders)
    assert summary["orders"] == 130
    assert summary["flagged"] == 31
    assert summary["clean"] == 99
    assert summary["unreconciled"] == 3
    assert summary["exposure_paise"] == 48191930
    assert summary["surplus_count"] == 0


# --------------------------------------------------------------------
# Agent explanations
# --------------------------------------------------------------------

def test_explanation_is_blank_without_the_agent(real):
    findings, _, _ = real
    report = build_report(findings)
    assert (report["agent_explanation"] == "").all()


def test_explanation_is_carried_through_when_the_agent_ran(real):
    findings, _, _ = real
    decisions = [
        {"order_id": "ord_00008", "explanation": "A refund the ledger never recorded."},
        {"order_id": "ord_00001", "explanation": ""},
    ]
    report = build_report(findings, decisions).set_index("order_id")
    assert report.loc["ord_00008", "agent_explanation"] == (
        "A refund the ledger never recorded."
    )
    assert report.loc["ord_00001", "agent_explanation"] == ""
    assert report.loc["ord_00045", "agent_explanation"] == ""


# --------------------------------------------------------------------
# Console and CSV output
# --------------------------------------------------------------------

def test_console_summary_leads_with_exposure(real):
    findings, matched, orders = real
    report = build_report(findings)
    text = render_console(report, summarise(report, matched, orders))
    assert "TOTAL EXPOSURE" in text
    assert "Rs 481,919.30" in text
    assert text.index("TOTAL EXPOSURE") < text.index("BY ANOMALY TYPE")


def test_console_names_every_anomaly_type_present(real):
    findings, matched, orders = real
    report = build_report(findings)
    text = render_console(report, summarise(report, matched, orders))
    for name in set(report["anomaly_type"]):
        assert name in text


def test_console_handles_an_empty_report(real):
    _, matched, orders = real
    empty = build_report(pd.DataFrame({
        "order_id": [], "anomaly_type": [], "expected_amount_paise": [],
        "actual_amount_paise": [], "delta_paise": [], "confidence": [], "reason": [],
    }))
    text = render_console(empty, summarise(empty, matched, orders))
    assert "nothing flagged" in text


def test_csv_roundtrips(real, tmp_path):
    findings, _, _ = real
    report = build_report(findings)
    path = write_csv(report, tmp_path / "sub" / "reconciliation.csv")
    assert path.exists()

    loaded = pd.read_csv(path)
    assert list(loaded.columns) == list(REPORT_COLUMNS)
    assert len(loaded) == len(report)
    assert int(loaded["impact_paise"].sum()) == int(report["impact_paise"].sum())


# --------------------------------------------------------------------
# The CLI, rules-only path
# --------------------------------------------------------------------

def test_run_without_the_agent_needs_no_key(tmp_path):
    report, summary, csv_path = run(FIXTURES, tmp_path)
    assert csv_path.exists()
    assert summary["flagged"] == 31
    assert (report["agent_explanation"] == "").all()


def test_run_rejects_a_directory_missing_a_ledger(tmp_path):
    (tmp_path / "orders.csv").write_text("order_id\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="payments.csv"):
        run(tmp_path, tmp_path / "out")
