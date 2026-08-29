"""Tests for the agent layer.

Every test here uses a fake client. The suite must never make a network
call, never need an API key, and never cost money.
"""

import json
from pathlib import Path

import pytest

from src.agent import (
    CONFIRMED,
    OVERRIDDEN,
    OVERRIDE_REJECTED,
    UNPARSEABLE,
    LLMClient,
    ResponseCache,
    classify,
)
from src.agent import classifier
from src.detectors import (
    FINDING_COLUMNS,
    HIGH,
    LOW,
    MEDIUM,
    detect_chargebacks,
    detect_overpayments,
    detect_refunds,
    detect_settlement_shortfalls,
)
from src.loaders import load_fees, load_orders, load_payments, load_settlements
from src.matching import match_ledgers

import pandas as pd

FIXTURES = Path(__file__).parent / "fixtures"
DETECTOR_FIXTURES = FIXTURES / "detectors"


class FakeClient:
    """An :class:`LLMClient` that replays canned answers and counts calls."""

    model = "fake-model-1"

    def __init__(self, response=None, by_order=None):
        self.response = response
        self.by_order = by_order or {}
        self.calls = []

    def complete(self, *, system, user):
        self.calls.append({"system": system, "user": user})
        for order_id, canned in self.by_order.items():
            if f"order_id: {order_id}\n" in user:
                return canned
        return self.response if self.response is not None else "not json"


def verdict(label, confidence=HIGH, explanation="A stated reason for the call."):
    return json.dumps(
        {"label": label, "confidence": confidence, "explanation": explanation}
    )


@pytest.fixture
def bench():
    orders = load_orders(DETECTOR_FIXTURES / "orders.csv")
    matched = match_ledgers(
        orders,
        load_payments(DETECTOR_FIXTURES / "payments.csv"),
        load_fees(DETECTOR_FIXTURES / "fees.csv"),
        load_settlements(DETECTOR_FIXTURES / "settlements.csv"),
    )
    findings = pd.concat(
        [
            detect_chargebacks(matched.reconciled),
            detect_refunds(matched.reconciled),
            detect_settlement_shortfalls(matched.reconciled),
            detect_overpayments(matched.reconciled),
        ],
        ignore_index=True,
    )
    return findings, matched.reconciled


@pytest.fixture
def cache(tmp_path):
    return ResponseCache(directory=tmp_path / "cache")


# --------------------------------------------------------------------
# The agent must never touch a number
# --------------------------------------------------------------------

def test_no_amount_is_ever_modified(bench, cache):
    """Every amount field must be identical before and after."""
    findings, reconciled = bench
    before = findings[list(classifier.AMOUNT_COLUMNS)].copy()

    client = FakeClient(verdict("chargeback", HIGH))
    after, decisions = classify(findings, reconciled, client, cache)

    assert decisions, "nothing was routed, so this proves nothing"
    pd.testing.assert_frame_equal(before, after[list(classifier.AMOUNT_COLUMNS)])


def test_order_ids_and_row_order_are_preserved(bench, cache):
    findings, reconciled = bench
    client = FakeClient(verdict("chargeback", HIGH))
    after, _ = classify(findings, reconciled, client, cache)

    assert list(after["order_id"]) == list(findings["order_id"])
    assert list(after.columns) == list(FINDING_COLUMNS)
    assert len(after) == len(findings)


def test_amounts_survive_even_when_every_label_is_overridden(bench, cache):
    findings, reconciled = bench
    before = findings[list(classifier.AMOUNT_COLUMNS)].copy()

    client = FakeClient(verdict("payment_not_received", HIGH))
    after, decisions = classify(findings, reconciled, client, cache)

    assert any(d["action"] == OVERRIDDEN for d in decisions)
    pd.testing.assert_frame_equal(before, after[list(classifier.AMOUNT_COLUMNS)])


# --------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------

def test_only_medium_and_low_confidence_are_routed(bench, cache):
    findings, reconciled = bench
    client = FakeClient(verdict("settlement_shortfall", MEDIUM))
    _, decisions = classify(findings, reconciled, client, cache)

    routed = {d["order_id"] for d in decisions}
    expected = set(
        findings.loc[findings["confidence"].isin([MEDIUM, LOW]), "order_id"]
    )
    assert routed == expected
    assert len(client.calls) == len(expected)


def test_high_confidence_findings_are_never_sent(bench, cache):
    findings, reconciled = bench
    client = FakeClient(verdict("settlement_shortfall", MEDIUM))
    after, decisions = classify(findings, reconciled, client, cache)

    high = findings[findings["confidence"] == HIGH]
    assert len(high) > 0
    routed = {d["order_id"] for d in decisions}
    for order_id in high["order_id"]:
        assert order_id not in routed

    # And their labels come through untouched.
    for order_id in high["order_id"]:
        before = findings.set_index("order_id").loc[order_id, "anomaly_type"]
        assert after.set_index("order_id").loc[order_id, "anomaly_type"] == before


def test_nothing_routed_means_no_calls(bench, cache):
    findings, reconciled = bench
    only_high = findings[findings["confidence"] == HIGH]
    client = FakeClient(verdict("chargeback", HIGH))
    after, decisions = classify(only_high, reconciled, client, cache)

    assert decisions == []
    assert client.calls == []
    pd.testing.assert_frame_equal(after, only_high[list(FINDING_COLUMNS)])


# --------------------------------------------------------------------
# Deference: the rule stands unless the agent is both sure and specific
# --------------------------------------------------------------------

@pytest.mark.parametrize("hedged", [LOW, MEDIUM])
def test_only_a_high_confidence_override_is_applied(hedged, bench, cache):
    """Anything short of high keeps the rule's label AND its confidence.

    Both regressions measured against the answer key were medium-confidence
    overrides; all three correct overrides were high. The bar is high.
    """
    findings, reconciled = bench
    target = findings[findings["confidence"] == MEDIUM].iloc[0]
    client = FakeClient(
        by_order={target["order_id"]: verdict("chargeback", hedged)},
        response=verdict("settlement_shortfall", MEDIUM),
    )
    after, decisions = classify(findings, reconciled, client, cache)

    decision = next(d for d in decisions if d["order_id"] == target["order_id"])
    assert decision["action"] == OVERRIDE_REJECTED
    assert decision["applied_label"] == target["anomaly_type"]

    row = after.set_index("order_id").loc[target["order_id"]]
    assert row["anomaly_type"] == target["anomaly_type"]
    assert row["confidence"] == target["confidence"]
    assert row["reason"] == target["reason"]


def test_the_prompt_never_names_the_override_threshold(bench):
    """Naming it would invite the model to report it instead of its certainty."""
    prompt = classifier.SYSTEM_PROMPT
    assert "discarded" not in prompt
    # "high" may appear only in the JSON schema line, never as a rule.
    schema_line = '"confidence": "high|medium|low"'
    assert prompt.count("high") == prompt.count(schema_line)


def test_confident_override_is_applied(bench, cache):
    findings, reconciled = bench
    target = findings[findings["confidence"] == MEDIUM].iloc[0]
    client = FakeClient(
        by_order={target["order_id"]: verdict("chargeback", HIGH, "It is a reversal.")},
        response=verdict("settlement_shortfall", MEDIUM),
    )
    after, decisions = classify(findings, reconciled, client, cache)

    decision = next(d for d in decisions if d["order_id"] == target["order_id"])
    assert decision["action"] == OVERRIDDEN
    row = after.set_index("order_id").loc[target["order_id"]]
    assert row["anomaly_type"] == "chargeback"
    assert row["confidence"] == HIGH
    assert "It is a reversal." in row["reason"]


def test_agreement_is_recorded_as_confirmed(bench, cache):
    findings, reconciled = bench
    target = findings[findings["confidence"] == MEDIUM].iloc[0]
    client = FakeClient(
        by_order={target["order_id"]: verdict(target["anomaly_type"], LOW)},
        response=verdict("settlement_shortfall", MEDIUM),
    )
    after, decisions = classify(findings, reconciled, client, cache)

    decision = next(d for d in decisions if d["order_id"] == target["order_id"])
    assert decision["action"] == CONFIRMED
    # Agreeing at low confidence is not an override, so it is not rejected.
    assert after.set_index("order_id").loc[target["order_id"], "anomaly_type"] == (
        target["anomaly_type"]
    )


def test_the_rule_reason_is_kept_alongside_the_agent_sentence(bench, cache):
    findings, reconciled = bench
    target = findings[findings["confidence"] == MEDIUM].iloc[0]
    client = FakeClient(verdict(target["anomaly_type"], MEDIUM, "Agent sentence."))
    after, _ = classify(findings, reconciled, client, cache)

    reason = after.set_index("order_id").loc[target["order_id"], "reason"]
    assert target["reason"] in reason
    assert "Agent: Agent sentence." in reason


# --------------------------------------------------------------------
# Malformed responses never corrupt a finding
# --------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "not json at all",
    "",
    '{"label": "not_a_real_label", "confidence": "high", "explanation": "x"}',
    '{"label": "chargeback", "confidence": "certain", "explanation": "x"}',
    '{"label": "chargeback", "confidence": "high"}',
    '{"label": "chargeback", "confidence": "high", "explanation": ""}',
])
def test_malformed_response_keeps_the_rule_label(bad, bench, cache):
    findings, reconciled = bench
    client = FakeClient(bad)
    after, decisions = classify(findings, reconciled, client, cache)

    assert all(d["action"] == UNPARSEABLE for d in decisions)
    pd.testing.assert_frame_equal(after, findings[list(FINDING_COLUMNS)])


def test_json_embedded_in_prose_is_still_parsed(bench, cache):
    findings, reconciled = bench
    wrapped = 'Here is my answer:\n' + verdict("chargeback", HIGH) + '\nHope that helps.'
    client = FakeClient(wrapped)
    _, decisions = classify(findings, reconciled, client, cache)
    assert all(d["action"] in (CONFIRMED, OVERRIDDEN) for d in decisions)


# --------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------

def test_second_run_makes_no_calls(bench, cache):
    findings, reconciled = bench
    first = FakeClient(verdict("settlement_shortfall", MEDIUM))
    classify(findings, reconciled, first, cache)
    assert first.calls

    second = FakeClient(verdict("settlement_shortfall", MEDIUM))
    classify(findings, reconciled, second, cache)
    assert second.calls == [], "cache did not prevent re-billing"


def test_cached_run_produces_identical_output(bench, cache):
    findings, reconciled = bench
    client = FakeClient(verdict("chargeback", HIGH))
    first, _ = classify(findings, reconciled, client, cache)
    second, _ = classify(findings, reconciled, FakeClient("unused"), cache)
    pd.testing.assert_frame_equal(first, second)


def test_a_different_model_misses_the_cache(cache):
    key_a = cache.key(model="a", prompt_version=1, system="s", user="u")
    key_b = cache.key(model="b", prompt_version=1, system="s", user="u")
    assert key_a != key_b


def test_a_changed_prompt_misses_the_cache(cache):
    key_a = cache.key(model="m", prompt_version=1, system="s", user="u")
    key_b = cache.key(model="m", prompt_version=2, system="s", user="u")
    assert key_a != key_b


def test_disabled_cache_never_returns_anything(tmp_path):
    disabled = ResponseCache(directory=tmp_path / "c", enabled=False)
    key = disabled.key(model="m", prompt_version=1, system="s", user="u")
    disabled.put(key, "value")
    assert disabled.get(key) is None


def test_corrupt_cache_entry_is_a_miss_not_a_crash(cache):
    key = cache.key(model="m", prompt_version=1, system="s", user="u")
    cache.put(key, "value")
    (cache.directory / f"{key}.json").write_text("{ broken", encoding="utf-8")
    assert cache.get(key) is None


# --------------------------------------------------------------------
# The provider boundary
# --------------------------------------------------------------------

AGENT_DIR = Path(__file__).parent.parent / "src" / "agent"


def test_no_provider_sdk_detail_outside_client_py():
    """`anthropic` may only appear in client.py."""
    offenders = []
    for path in sorted(AGENT_DIR.glob("*.py")):
        if path.name == "client.py":
            continue
        if "anthropic" in path.read_text(encoding="utf-8").lower():
            offenders.append(path.name)
    assert offenders == [], f"provider detail leaked into {offenders}"


def test_no_provider_sdk_detail_anywhere_else_in_src():
    src = Path(__file__).parent.parent / "src"
    offenders = [
        str(path.relative_to(src))
        for path in sorted(src.rglob("*.py"))
        if path.name != "client.py"
        and "anthropic" in path.read_text(encoding="utf-8").lower()
    ]
    assert offenders == [], f"provider detail leaked into {offenders}"


def test_fake_client_satisfies_the_protocol():
    assert isinstance(FakeClient(), LLMClient)


def test_classify_needs_nothing_but_the_protocol(bench, cache):
    """A client with no SDK, no key and no network still works."""
    findings, reconciled = bench
    after, decisions = classify(findings, reconciled, FakeClient(verdict("chargeback")), cache)
    assert len(after) == len(findings)
    assert decisions
