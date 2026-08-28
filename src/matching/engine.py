"""Join the four ledgers into one reconciled frame.

The chain is the one documented in docs/data-model.md, and it is walked
by ID only::

    orders.payment_id   -> payments.payment_id
    payments.payment_id -> fees.payment_id
    payments.payment_id -> settlements.payment_id

Settlement lags capture by 1.59 to 4.06 days and varies per order, so
date proximity is never used to associate rows. Dates are carried
through as data, never as join keys.

Row conservation
----------------
Every reconciled row consumes exactly one row from each of the four
ledgers. Any input row not consumed must appear in ``unreconciled``
with a reason. That gives one invariant per ledger, all four asserted
before the result is returned::

    len(ledger) == len(reconciled) + len(unreconciled[source == ledger])

If any of the four fails, :class:`RowConservationError` is raised
rather than a result being returned. Nothing is dropped silently.

Column naming
-------------
``orders``/``payments``/``settlements`` each carry a ``status``, and
``payments``/``settlements`` each carry an ``amount_paise``. The join
would collide on those names, so they are given explicit prefixes in
the output. The renames are listed in the ``_RENAMES`` mappings below
and are part of the documented output schema, not incidental suffixes.
``payments.order_id`` is not carried through: it is redundant with
``orders.payment_id`` per docs/data-model.md, and is instead used as a
cross-check (see ``ORDER_ID_MISMATCH``).
"""

from __future__ import annotations

import pandas as pd

# --- reasons recorded against an order ------------------------------
MISSING_PAYMENT = "missing_payment"
DUPLICATE_PAYMENT = "duplicate_payment"
MISSING_FEE = "missing_fee"
DUPLICATE_FEE = "duplicate_fee"
MISSING_SETTLEMENT = "missing_settlement"
DUPLICATE_SETTLEMENT = "duplicate_settlement"
ORDER_ID_MISMATCH = "order_id_mismatch"

# --- reasons recorded against a non-order ledger row -----------------
ORPHAN = "orphan"
DUPLICATE_KEY = "duplicate_key"
ORDER_UNRECONCILED = "order_unreconciled"

UNRECONCILED_COLUMNS = ("source_ledger", "order_id", "payment_id", "reason", "detail")

RECONCILED_COLUMNS = (
    "order_id",
    "order_date",
    "customer_id",
    "net_amount_paise",
    "gst_amount_paise",
    "gross_amount_paise",
    "order_status",
    "payment_id",
    "captured_at",
    "payment_amount_paise",
    "payment_method",
    "payment_status",
    "fee_paise",
    "gst_on_fee_paise",
    "total_deduction_paise",
    "settlement_id",
    "settled_at",
    "settlement_amount_paise",
    "utr",
    "settlement_status",
)

_ORDER_RENAMES = {"status": "order_status"}
_PAYMENT_RENAMES = {
    "amount_paise": "payment_amount_paise",
    "method": "payment_method",
    "status": "payment_status",
    "order_id": "_payment_order_id",
}
_SETTLEMENT_RENAMES = {
    "amount_paise": "settlement_amount_paise",
    "status": "settlement_status",
}


class RowConservationError(AssertionError):
    """Input rows were neither reconciled nor bucketed as unreconciled."""


class MatchResult:
    """The two frames a match produces.

    Attributes:
        reconciled: One row per fully joined order, schema
            :data:`RECONCILED_COLUMNS`.
        unreconciled: One row per input row that could not be placed,
            schema :data:`UNRECONCILED_COLUMNS`.
    """

    __slots__ = ("reconciled", "unreconciled")

    def __init__(self, reconciled, unreconciled):
        self.reconciled = reconciled
        self.unreconciled = unreconciled


def match_ledgers(orders, payments, fees, settlements):
    """Join the four ledgers by ID and bucket everything that will not join.

    Args:
        orders: Frame from ``load_orders``.
        payments: Frame from ``load_payments``.
        fees: Frame from ``load_fees``.
        settlements: Frame from ``load_settlements``.

    Returns:
        A :class:`MatchResult`.

    Raises:
        RowConservationError: A ledger's rows were not fully accounted
            for across the two output frames.
    """
    duplicate_payment_ids = _duplicate_keys(payments, "payment_id")
    duplicate_fee_ids = _duplicate_keys(fees, "payment_id")
    duplicate_settlement_ids = _duplicate_keys(settlements, "payment_id")

    joined = _join_by_id(
        orders,
        payments[~payments["payment_id"].isin(duplicate_payment_ids)],
        fees[~fees["payment_id"].isin(duplicate_fee_ids)],
        settlements[~settlements["payment_id"].isin(duplicate_settlement_ids)],
    )
    joined["_reason"] = _reason_per_order(
        joined,
        duplicate_payment_ids=duplicate_payment_ids,
        duplicate_fee_ids=duplicate_fee_ids,
        duplicate_settlement_ids=duplicate_settlement_ids,
    )

    reconciled = (
        joined[joined["_reason"].isna()]
        .loc[:, list(RECONCILED_COLUMNS)]
        .reset_index(drop=True)
    )
    matched_payment_ids = set(reconciled["payment_id"])

    unreconciled = pd.concat(
        [
            _unreconciled_orders(joined),
            _unreconciled_side_ledger(
                payments, "payments", orders, matched_payment_ids, duplicate_payment_ids
            ),
            _unreconciled_side_ledger(
                fees, "fees", orders, matched_payment_ids, duplicate_fee_ids
            ),
            _unreconciled_side_ledger(
                settlements,
                "settlements",
                orders,
                matched_payment_ids,
                duplicate_settlement_ids,
            ),
        ],
        ignore_index=True,
    )

    _assert_row_conservation(
        reconciled,
        unreconciled,
        orders=orders,
        payments=payments,
        fees=fees,
        settlements=settlements,
    )
    return MatchResult(reconciled, unreconciled)


# --------------------------------------------------------------------
# joining
# --------------------------------------------------------------------

def _duplicate_keys(frame, column):
    """Key values appearing more than once, which make a join ambiguous."""
    counts = frame[column].value_counts()
    return set(counts[counts > 1].index)


def _join_by_id(orders, payments, fees, settlements):
    """Left-join the chain onto orders, keeping a merge indicator per step."""
    joined = orders.rename(columns=_ORDER_RENAMES).merge(
        payments.rename(columns=_PAYMENT_RENAMES),
        on="payment_id",
        how="left",
        indicator="_payment_merge",
    )
    joined = joined.merge(
        fees, on="payment_id", how="left", indicator="_fee_merge"
    )
    joined = joined.merge(
        settlements.rename(columns=_SETTLEMENT_RENAMES),
        on="payment_id",
        how="left",
        indicator="_settlement_merge",
    )
    return joined


def _reason_per_order(joined, *, duplicate_payment_ids, duplicate_fee_ids,
                      duplicate_settlement_ids):
    """Return the reason each order failed to reconcile, NA where it did.

    Order matters: a duplicate key is reported as a duplicate, not as a
    miss, even though the ambiguous rows were held back from the join.
    """
    payment_id = joined["payment_id"]
    has_payment = joined["_payment_merge"] == "both"

    conditions = [
        payment_id.isin(duplicate_payment_ids),
        ~has_payment,
        has_payment & (joined["_payment_order_id"] != joined["order_id"]),
        payment_id.isin(duplicate_fee_ids),
        joined["_fee_merge"] != "both",
        payment_id.isin(duplicate_settlement_ids),
        joined["_settlement_merge"] != "both",
    ]
    reasons = [
        DUPLICATE_PAYMENT,
        MISSING_PAYMENT,
        ORDER_ID_MISMATCH,
        DUPLICATE_FEE,
        MISSING_FEE,
        DUPLICATE_SETTLEMENT,
        MISSING_SETTLEMENT,
    ]
    result = pd.Series(pd.NA, index=joined.index, dtype="object")
    for condition, reason in zip(conditions, reasons):
        result = result.where(result.notna() | ~condition, reason)
    return result


# --------------------------------------------------------------------
# bucketing
# --------------------------------------------------------------------

_ORDER_DETAIL = {
    MISSING_PAYMENT: "no row in payments.csv for payment_id {payment_id}",
    DUPLICATE_PAYMENT: "payment_id {payment_id} appears more than once in payments.csv",
    ORDER_ID_MISMATCH: "payments.order_id disagrees with orders.order_id for {payment_id}",
    MISSING_FEE: "no row in fees.csv for payment_id {payment_id}",
    DUPLICATE_FEE: "payment_id {payment_id} appears more than once in fees.csv",
    MISSING_SETTLEMENT: "no row in settlements.csv for payment_id {payment_id}",
    DUPLICATE_SETTLEMENT: "payment_id {payment_id} appears more than once in settlements.csv",
}


def _unreconciled_orders(joined):
    """Orders that did not reconcile, one row each, with the reason."""
    failed = joined[joined["_reason"].notna()]
    return pd.DataFrame(
        {
            "source_ledger": "orders",
            "order_id": failed["order_id"].to_numpy(),
            "payment_id": failed["payment_id"].to_numpy(),
            "reason": failed["_reason"].to_numpy(),
            "detail": [
                _ORDER_DETAIL[reason].format(payment_id=pid)
                for reason, pid in zip(failed["_reason"], failed["payment_id"])
            ],
        },
        columns=list(UNRECONCILED_COLUMNS),
    )


def _unreconciled_side_ledger(frame, name, orders, matched_payment_ids, duplicate_ids):
    """Rows of payments/fees/settlements that no reconciled row consumed.

    Three distinct situations, each named rather than lumped together:

    - ``duplicate_key``: the payment_id is ambiguous within this file.
    - ``orphan``: the payment_id is not referenced by any order, so the
      row cannot be traced back to an order at all.
    - ``order_unreconciled``: the row is fine, but the order it belongs
      to failed elsewhere in the chain.
    """
    leftover = frame[~frame["payment_id"].isin(matched_payment_ids)]
    order_payment_ids = set(orders["payment_id"])
    order_by_payment = dict(zip(orders["payment_id"], orders["order_id"]))

    reasons = []
    details = []
    for payment_id in leftover["payment_id"]:
        if payment_id in duplicate_ids:
            reasons.append(DUPLICATE_KEY)
            details.append(
                f"payment_id {payment_id} appears more than once in {name}.csv"
            )
        elif payment_id not in order_payment_ids:
            reasons.append(ORPHAN)
            details.append(
                f"payment_id {payment_id} is not referenced by any order"
            )
        else:
            reasons.append(ORDER_UNRECONCILED)
            details.append(
                f"the order for payment_id {payment_id} could not be reconciled"
            )

    return pd.DataFrame(
        {
            "source_ledger": name,
            "order_id": [
                order_by_payment.get(pid, "") for pid in leftover["payment_id"]
            ],
            "payment_id": leftover["payment_id"].to_numpy(),
            "reason": reasons,
            "detail": details,
        },
        columns=list(UNRECONCILED_COLUMNS),
    )


# --------------------------------------------------------------------
# the invariant
# --------------------------------------------------------------------

def _assert_row_conservation(reconciled, unreconciled, **ledgers):
    """Every input row is either consumed by a reconciled row or bucketed."""
    matched = len(reconciled)
    for name, frame in ledgers.items():
        bucketed = int((unreconciled["source_ledger"] == name).sum())
        if len(frame) != matched + bucketed:
            raise RowConservationError(
                f"{name}: {len(frame)} input rows but {matched} matched + "
                f"{bucketed} unreconciled = {matched + bucketed}. "
                f"Rows were dropped silently; this is a bug in the matcher."
            )
