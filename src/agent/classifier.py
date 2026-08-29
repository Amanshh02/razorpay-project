"""Route uncertain findings to the model and apply its judgement.

What this layer may and may not do (CLAUDE.md §7):

- It **classifies and explains**. It may change a finding's
  ``anomaly_type``, ``confidence`` and ``reason``.
- It **never touches a number**. ``expected_amount_paise``,
  ``actual_amount_paise`` and ``delta_paise`` are copied through
  untouched, and a test asserts every amount field is identical before
  and after.

Routing
-------
Only ``medium`` and ``low`` confidence findings are sent. ``high`` means
the rule matched an arithmetic identity - chargeback, missing payment,
settlement excess - and there is nothing for a language model to add.
Measured on the hard set, high-confidence findings are 100% correct and
every known error sits in medium or low, so this routing sees all of
them while leaving the sharp calls alone.

Deference
---------
On the easy set every routed finding is already correct, so the agent can
only regress there. Two guards:

1. The prompt requires the rule's label to stand unless the model has a
   specific, stated reason to disagree.
2. **Only a ``high`` confidence disagreement is applied.** Anything less
   is rejected: the rule's label and confidence are kept and the attempt
   is recorded as ``override_rejected``.

The bar is high rather than merely not-low because of what was measured.
At the not-low bar the agent fixed all three non-standard-fee chargebacks
on the hard set - each asserted at ``high`` - and broke two orders, both
asserted at ``medium``: an exact-25% refund it read as too round to be
genuine, and a combined refund-plus-shortfall it called "at least equally
plausible" either way. Every correct override was confident; every
damaging one was hedged. Requiring ``high`` keeps the fixes and discards
the coin flips.

The prompt does not name this threshold. Telling a model which
confidence value unlocks an override invites it to report that value
rather than its actual certainty, which would destroy the signal the
gate depends on.
"""

from __future__ import annotations

import json
import re

from ..detectors import FINDING_COLUMNS, HIGH, LOW, MEDIUM
from .cache import ResponseCache

#: Bump when the prompt changes; every cache entry then misses.
PROMPT_VERSION = 2

#: Confidence levels that get routed. High never is.
ROUTED_CONFIDENCE = (MEDIUM, LOW)

#: Amount fields the agent must never alter.
AMOUNT_COLUMNS = (
    "expected_amount_paise",
    "actual_amount_paise",
    "delta_paise",
)

VALID_LABELS = (
    "refund_not_reflected",
    "chargeback",
    "settlement_shortfall",
    "payment_not_received",
    "settlement_excess",
)

CONFIRMED = "confirmed"
OVERRIDDEN = "overridden"
OVERRIDE_REJECTED = "override_rejected"
UNPARSEABLE = "unparseable"

SYSTEM_PROMPT = """\
You are a reconciliation analyst for an Indian payment gateway. Four \
ledgers should agree: the merchant's orders, the gateway's payments, the \
gateway's fees, and the bank's settlements. Deterministic code has \
already matched them by ID and computed every amount. Your job is to \
judge WHY a gap exists - never to recompute it.

The expected payout for an order is:

    expected = payment_amount - razorpay_fee - gst_on_fee

A gap between that and what the bank actually settled is one of:

- refund_not_reflected: money was returned to the customer and deducted \
from the payout, but no refund appears in any ledger. Any size, from a \
few percent to the whole payment. Real refunds are arbitrary amounts.
- chargeback: the payment was reversed in full AND a penalty fee was \
withheld on top, so the shortfall EXCEEDS the captured payment. The \
penalty is contractual and varies - it is often Rs 500 but can be any \
amount. A shortfall larger than the full payment is the signature.
- settlement_shortfall: the bank simply credited less than expected, \
with no refund or reversal to explain it. Usually small, but not always.
- payment_not_received: the merchant recorded an order the gateway has \
no payment for.
- settlement_excess: the bank credited MORE than expected.

The rules that produced these findings are deterministic and good at \
arithmetic identities, but they separate refunds from shortfalls using a \
single magnitude threshold - a shortfall above 20% of the payment is \
guessed to be a refund, below it a shortfall. That threshold is a guess \
on a continuum and it is the rules' known weak point. It also assumes a \
fixed chargeback penalty, so a chargeback with an unusual penalty gets \
misread.

DEFER TO THE RULE. Return the rule's label unless you have a specific, \
statable reason it is wrong. Disagreeing without one makes the system \
worse.

Report your genuine certainty in the confidence field. The system \
weighs it when deciding whether to act on a disagreement, so an honest \
hedge is more useful than false certainty - if the evidence leaves the \
call a coin flip, say so and keep the rule's label.

Respond with JSON only, no prose around it:

{"label": "<one of the five labels>", "confidence": "high|medium|low", \
"explanation": "<one sentence, plain English, for a finance team>"}

Never state, recompute or correct any amount. The numbers are settled."""


def _facts(finding_row, ledger_row):
    """Render the order's ledger facts. Arithmetic done here, not by the model."""
    lines = [
        f"order_id: {finding_row['order_id']}",
        f"rule label: {finding_row['anomaly_type']}",
        f"rule confidence: {finding_row['confidence']}",
        f"rule reasoning: {finding_row['reason']}",
        "",
        f"expected payout (paise): {int(finding_row['expected_amount_paise'])}",
        f"bank actually settled (paise): {int(finding_row['actual_amount_paise'])}",
        f"delta (paise, negative = underpaid): {int(finding_row['delta_paise'])}",
    ]
    if ledger_row is None:
        return "\n".join(lines)

    payment = int(ledger_row["payment_amount_paise"])
    shortfall = -int(finding_row["delta_paise"])
    lines += [
        "",
        f"captured payment (paise): {payment}",
        f"razorpay fee (paise): {int(ledger_row['fee_paise'])}",
        f"gst on fee (paise): {int(ledger_row['gst_on_fee_paise'])}",
        f"total deduction (paise): {int(ledger_row['total_deduction_paise'])}",
        f"order gross (paise): {int(ledger_row['gross_amount_paise'])}",
        f"payment method: {ledger_row['payment_method']}",
    ]
    if payment:
        lines.append(
            f"shortfall as a fraction of the captured payment: "
            f"{shortfall / payment:.4f}"
        )
        lines.append(
            f"shortfall minus the full payment (paise): {shortfall - payment}"
        )
    return "\n".join(lines)


def _parse(text):
    """Pull the JSON verdict out of the response. None if unusable."""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    label = payload.get("label")
    confidence = str(payload.get("confidence", "")).lower()
    explanation = str(payload.get("explanation", "")).strip()
    if label not in VALID_LABELS or confidence not in (HIGH, MEDIUM, LOW):
        return None
    if not explanation:
        return None
    return {"label": label, "confidence": confidence, "explanation": explanation}


def classify(findings, reconciled, client, cache=None, prompt_version=PROMPT_VERSION):
    """Send uncertain findings to the model and apply its verdicts.

    Args:
        findings: Findings frame from the detectors.
        reconciled: Reconciled frame, for the order's ledger facts.
        client: Anything satisfying ``client.LLMClient``.
        cache: A :class:`ResponseCache`, or None to build the default.

    Returns:
        ``(findings, decisions)`` - a new findings frame with the same
        row order and identical amount columns, and a list of one
        decision dict per routed finding.
    """
    cache = ResponseCache() if cache is None else cache
    ledger = reconciled.set_index("order_id") if len(reconciled) else None

    updated = findings.copy()
    decisions = []

    for position, row in enumerate(findings.to_dict("records")):
        if row["confidence"] not in ROUTED_CONFIDENCE:
            continue

        ledger_row = None
        if ledger is not None and row["order_id"] in ledger.index:
            ledger_row = ledger.loc[row["order_id"]]

        user_prompt = _facts(row, ledger_row)
        key = cache.key(
            model=client.model,
            prompt_version=prompt_version,
            system=SYSTEM_PROMPT,
            user=user_prompt,
        )
        text = cache.get(key)
        if text is None:
            text = client.complete(system=SYSTEM_PROMPT, user=user_prompt)
            cache.put(key, text, metadata={"order_id": row["order_id"]})

        verdict = _parse(text)
        decision = {
            "order_id": row["order_id"],
            "rule_label": row["anomaly_type"],
            "rule_confidence": row["confidence"],
        }

        if verdict is None:
            decision.update(
                action=UNPARSEABLE, agent_label=None, agent_confidence=None,
                applied_label=row["anomaly_type"], explanation="",
            )
            decisions.append(decision)
            continue

        decision.update(
            agent_label=verdict["label"],
            agent_confidence=verdict["confidence"],
            explanation=verdict["explanation"],
        )

        disagrees = verdict["label"] != row["anomaly_type"]
        if disagrees and verdict["confidence"] != HIGH:
            # Only a confident disagreement displaces the rule. Every
            # hedged override measured so far made the answer worse.
            decision["action"] = OVERRIDE_REJECTED
            decision["applied_label"] = row["anomaly_type"]
            decisions.append(decision)
            continue

        decision["action"] = OVERRIDDEN if disagrees else CONFIRMED
        decision["applied_label"] = verdict["label"]

        updated.iat[position, updated.columns.get_loc("anomaly_type")] = verdict["label"]
        updated.iat[position, updated.columns.get_loc("confidence")] = verdict["confidence"]
        updated.iat[position, updated.columns.get_loc("reason")] = (
            f"{row['reason']} Agent: {verdict['explanation']}"
        )
        decisions.append(decision)

    return updated[list(FINDING_COLUMNS)], decisions
