"""Tests for the dashboard's data layer and its isolation constraints.

``app.py`` is not imported here - importing a Streamlit script executes
it. Its structure is checked by parsing the source instead, which is
also the only way to prove the import constraint rather than assert it.
"""

import ast
from pathlib import Path

import pandas as pd
import pytest

from src.dashboard.data import (
    OVERPAID,
    UNDERPAID,
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

DASHBOARD = Path(__file__).parent.parent / "src" / "dashboard"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def report_csv(tmp_path):
    """A small report in the shape src.report writes."""
    frame = pd.DataFrame({
        "order_id": ["ord_1", "ord_2", "ord_3", "ord_4"],
        "anomaly_type": [
            "refund_not_reflected", "chargeback",
            "settlement_shortfall", "settlement_excess",
        ],
        "confidence": ["medium", "high", "low", "high"],
        "expected_amount_paise": [5000000, 900000, 300000, 700000],
        "actual_amount_paise": [1000000, -50000, 295000, 725000],
        "delta_paise": [-4000000, -950000, -5000, 25000],
        "impact_paise": [4000000, 950000, 5000, 25000],
        "impact_rupees": ["40000.00", "9500.00", "50.00", "250.00"],
        "direction": [UNDERPAID, UNDERPAID, UNDERPAID, OVERPAID],
        "agent_explanation": ["Agent said refund.", "", "", ""],
        "reason": ["Rule reason 1.", "Rule reason 2.", "Rule reason 3.", "Rule reason 4."],
    })
    path = tmp_path / "reconciliation.csv"
    frame.to_csv(path, index=False)
    return path


# --------------------------------------------------------------------
# The isolation constraint, proven from the AST
# --------------------------------------------------------------------

def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


@pytest.mark.parametrize("forbidden", ["matching", "detectors", "agent"])
def test_dashboard_imports_nothing_from_the_engine(forbidden):
    """A docstring saying so is not proof; the AST is."""
    offenders = []
    for path in sorted(DASHBOARD.glob("*.py")):
        for module in _imported_modules(path):
            if forbidden in module.split("."):
                offenders.append(f"{path.name} -> {module}")
    assert offenders == [], offenders


def _docstring_nodes(tree):
    """Constant nodes that are docstrings, so prose can be excluded."""
    holders = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, holders) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                found.add(id(first.value))
    return found


def test_dashboard_never_reads_the_answer_key():
    """No code path may open ground_truth.csv.

    Docstrings are excluded: both modules *describe* this rule in prose,
    and matching on that text would pass or fail on the wording rather
    than on what the code does.
    """
    for path in sorted(DASHBOARD.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or id(node) in docstrings:
                continue
            if isinstance(node.value, str):
                assert "ground_truth" not in node.value, f"{path.name}:{node.lineno}"


def test_data_layer_does_not_import_streamlit():
    """Keeps the logic testable without a server."""
    assert "streamlit" not in _imported_modules(DASHBOARD / "data.py")


# --------------------------------------------------------------------
# Indian digit grouping
# --------------------------------------------------------------------

@pytest.mark.parametrize("paise,expected", [
    (0, "Rs 0.00"),
    (5, "Rs 0.05"),
    (100, "Rs 1.00"),
    (99999, "Rs 999.99"),
    (100000, "Rs 1,000.00"),
    (10000000, "Rs 1,00,000.00"),        # one lakh
    (48191930, "Rs 4,81,919.30"),        # the real fixture exposure
    (1000000000, "Rs 1,00,00,000.00"),   # one crore
    (-4588449, "-Rs 45,884.49"),
])
def test_indian_grouping(paise, expected):
    assert format_indian(paise) == expected


def test_grouping_is_not_western():
    """481919.30 must not render as 481,919.30."""
    assert format_indian(48191930) == "Rs 4,81,919.30"
    assert "481,919" not in format_indian(48191930)


def test_to_rupees_is_display_only():
    assert to_rupees(48191930) == 481919.30
    assert to_rupees(-5000) == -50.0


# --------------------------------------------------------------------
# Finding and loading
# --------------------------------------------------------------------

def test_missing_directory_raises_not_found(tmp_path):
    with pytest.raises(ReportNotFound):
        find_report(tmp_path / "nope")


def test_empty_directory_raises_not_found(tmp_path):
    with pytest.raises(ReportNotFound, match="no CSV"):
        find_report(tmp_path)


def test_prefers_reconciliation_csv(tmp_path):
    (tmp_path / "other.csv").write_text("a\n", encoding="utf-8")
    (tmp_path / "reconciliation.csv").write_text("a\n", encoding="utf-8")
    assert find_report(tmp_path).name == "reconciliation.csv"


def test_falls_back_to_any_csv(tmp_path):
    (tmp_path / "older.csv").write_text("a\n", encoding="utf-8")
    assert find_report(tmp_path).name == "older.csv"


def test_malformed_csv_is_rejected_not_half_rendered(tmp_path):
    path = tmp_path / "reconciliation.csv"
    pd.DataFrame({"nonsense": [1]}).to_csv(path, index=False)
    with pytest.raises(ReportMalformed, match="order_id"):
        load_report(path)


def test_load_sorts_by_absolute_delta_descending(report_csv):
    frame = load_report(report_csv)
    assert frame["impact_paise"].is_monotonic_decreasing
    assert list(frame["order_id"]) == ["ord_1", "ord_2", "ord_4", "ord_3"]


def test_order_ids_stay_strings(report_csv):
    frame = load_report(report_csv)
    assert frame["order_id"].map(type).eq(str).all()


def test_paise_stay_integers(report_csv):
    frame = load_report(report_csv)
    for column in ("expected_amount_paise", "actual_amount_paise", "delta_paise"):
        assert frame[column].dtype == "int64"


def test_direction_is_derived_when_absent(tmp_path):
    frame = pd.DataFrame({
        "order_id": ["a", "b"], "anomaly_type": ["x", "y"],
        "confidence": ["high", "high"],
        "expected_amount_paise": [100, 100], "actual_amount_paise": [50, 150],
        "delta_paise": [-50, 50],
    })
    path = tmp_path / "reconciliation.csv"
    frame.to_csv(path, index=False)
    loaded = load_report(path).set_index("order_id")
    assert loaded.loc["a", "direction"] == UNDERPAID
    assert loaded.loc["b", "direction"] == OVERPAID


def test_explanation_prefers_the_agent_sentence(report_csv):
    frame = load_report(report_csv).set_index("order_id")
    assert frame.loc["ord_1", "explanation"] == "Agent said refund."
    assert frame.loc["ord_2", "explanation"] == "Rule reason 2."


# --------------------------------------------------------------------
# Summary and grouping
# --------------------------------------------------------------------

def test_exposure_excludes_the_overpayment(report_csv):
    totals = summarise(load_report(report_csv))
    assert totals["flagged"] == 4
    assert totals["exposure_count"] == 3
    assert totals["exposure_paise"] == 4000000 + 950000 + 5000
    assert totals["surplus_count"] == 1
    assert totals["surplus_paise"] == 25000


def test_surplus_is_never_netted_into_exposure(report_csv):
    totals = summarise(load_report(report_csv))
    netted = totals["exposure_paise"] - totals["surplus_paise"]
    assert totals["exposure_paise"] != netted


def test_by_type_is_ordered_by_impact(report_csv):
    groups = by_type(load_report(report_csv))
    assert [g["anomaly_type"] for g in groups] == [
        "refund_not_reflected", "chargeback", "settlement_excess",
        "settlement_shortfall",
    ]
    assert groups[0]["count"] == 1
    assert groups[0]["impact_paise"] == 4000000


def test_by_type_handles_an_empty_frame():
    assert by_type(pd.DataFrame({"anomaly_type": [], "impact_paise": []})) == []


# --------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------

def test_filter_by_type(report_csv):
    frame = load_report(report_csv)
    filtered = apply_filters(frame, types=["chargeback"])
    assert list(filtered["order_id"]) == ["ord_2"]


def test_filter_by_minimum_delta(report_csv):
    frame = load_report(report_csv)
    filtered = apply_filters(frame, min_delta_paise=100000)
    assert set(filtered["order_id"]) == {"ord_1", "ord_2"}


def test_filters_combine(report_csv):
    frame = load_report(report_csv)
    filtered = apply_filters(
        frame, types=["refund_not_reflected", "chargeback"], min_delta_paise=1000000
    )
    assert list(filtered["order_id"]) == ["ord_1"]


def test_no_filters_returns_everything(report_csv):
    frame = load_report(report_csv)
    assert len(apply_filters(frame)) == len(frame)


def test_filters_can_return_nothing(report_csv):
    frame = load_report(report_csv)
    assert apply_filters(frame, min_delta_paise=10**12).empty


# --------------------------------------------------------------------
# Against a real report
# --------------------------------------------------------------------

def test_reads_a_report_produced_by_the_pipeline(tmp_path):
    from src.main import run

    run(FIXTURES, tmp_path)
    frame = load_report(find_report(tmp_path))
    totals = summarise(frame)
    assert totals["flagged"] == 31
    assert totals["exposure_paise"] == 48191930
    assert format_indian(totals["exposure_paise"]) == "Rs 4,81,919.30"
