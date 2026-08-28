"""Generate the 40-order hard fixture set in tests/fixtures/hard/.

Run from anywhere::

    python tests/gen_hard.py

Rerunning overwrites the five CSVs with byte-identical content. If the
output ever differs without this file changing, something is wrong.


Deterministic: no randomness, every amount computed from the order's net
value. Ledger arithmetic follows docs/data-model.md exactly -
net + gst == gross, payment == gross, fee == round(gross*0.02),
gst_on_fee == round(fee*0.18), settlement == expected - shortfall.

The anomalies are chosen to break the current rules on purpose. Nothing
here is tuned to let them pass.
"""

import csv
import datetime as dt
from pathlib import Path

# Resolved from this file, not the working directory, so the script
# regenerates the same set whatever it is invoked from.
OUT = Path(__file__).resolve().parent / "fixtures" / "hard"
OUT.mkdir(parents=True, exist_ok=True)

CHARGEBACK_FEE_DEFAULT = 50_000

# kind, net_paise, param, note
# param meaning depends on kind (see below)
SPEC = [
    # --- clean, no anomaly (14) ---
    ("clean", 1_240_000, None, ""),
    ("clean", 880_000, None, ""),
    ("clean", 3_150_000, None, ""),
    ("clean", 470_000, None, ""),
    ("clean", 2_060_000, None, ""),
    ("clean", 1_775_000, None, ""),
    ("clean", 640_000, None, ""),
    ("clean", 4_300_000, None, ""),
    ("clean", 925_000, None, ""),
    ("clean", 1_510_000, None, ""),
    ("clean", 385_000, None, ""),
    ("clean", 2_740_000, None, ""),
    ("clean", 1_105_000, None, ""),
    ("clean", 690_000, None, ""),

    # --- refunds at arbitrary amounts, above the 20% threshold (5) ---
    # param = absolute refund in paise. Not a whole-percent slice.
    ("refund_abs", 1_930_000, 611_837, "arbitrary partial refund, not a round percentage"),
    ("refund_abs", 2_480_000, 977_413, "arbitrary partial refund, not a round percentage"),
    ("refund_abs", 3_620_000, 1_099_251, "arbitrary partial refund, not a round percentage"),
    ("refund_abs", 845_000, 431_209, "arbitrary partial refund, not a round percentage"),
    ("refund_abs", 1_360_000, 507_663, "arbitrary partial refund, not a round percentage"),

    # --- refunds BELOW the 20% threshold: rules will call these shortfalls (3) ---
    ("refund_pct", 2_900_000, 0.12, "12% refund; below the 20% rule threshold"),
    ("refund_pct", 1_680_000, 0.15, "15% refund; below the 20% rule threshold"),
    ("refund_pct", 3_410_000, 0.08, "8% refund; well below the 20% rule threshold"),

    # --- shortfalls ABOVE 20%: rules will call these refunds (2) ---
    ("shortfall_pct", 1_240_000, 0.35, "unexplained bank shortfall of 35%; no refund occurred"),
    ("shortfall_pct", 2_215_000, 0.28, "unexplained bank shortfall of 28%; no refund occurred"),

    # --- chargebacks with a fee that is NOT Rs 500 (3) ---
    # param = chargeback fee in paise
    ("chargeback", 1_450_000, 25_000, "chargeback with a Rs 250 fee, not the Rs 500 the rule assumes"),
    ("chargeback", 2_030_000, 75_000, "chargeback with a Rs 750 fee, not the Rs 500 the rule assumes"),
    ("chargeback", 760_000, 100_000, "chargeback with a Rs 1000 fee, not the Rs 500 the rule assumes"),

    # --- chargebacks at exactly Rs 500 (control, rules should catch) (2) ---
    ("chargeback", 1_890_000, CHARGEBACK_FEE_DEFAULT, "chargeback with the standard Rs 500 fee"),
    ("chargeback", 540_000, CHARGEBACK_FEE_DEFAULT, "chargeback with the standard Rs 500 fee"),

    # --- two refunds on one order, summing to an odd total (2) ---
    # param = (first, second) in paise
    ("refund_two", 2_640_000, (409_118, 331_777), "two separate refunds on one order; ledger shows only the sum"),
    ("refund_two", 1_950_000, (216_443, 181_090), "two refunds summing below the 20% threshold"),

    # --- partial refund PLUS a small shortfall on the same order (2) ---
    # param = (refund_pct, shortfall_paise)
    ("refund_and_short", 2_310_000, (0.18, 88_407), "18% refund plus a separate unexplained shortfall"),
    ("refund_and_short", 1_580_000, (0.12, 41_255), "12% refund plus a small shortfall; combined still under threshold"),

    # --- overpayments (2) ---
    ("overpaid", 1_420_000, 63_500, "bank credited more than expected"),
    ("overpaid", 2_870_000, 118_240, "bank credited more than expected"),

    # --- missing payments (2) ---
    ("missing", 1_690_000, None, "merchant marked order paid; no record in payments.csv"),
    ("missing", 3_240_000, None, "merchant marked order paid; no record in payments.csv"),

    # --- easy refunds at whole percentages (control) (2) ---
    ("refund_pct", 2_150_000, 0.30, "30% refund, the easy case"),
    ("refund_pct", 1_270_000, 0.50, "50% refund, the easy case"),

    # --- easy small shortfall (control) (1) ---
    ("shortfall_pct", 1_840_000, 0.03, "small unexplained shortfall, the easy case"),
]

assert len(SPEC) == 40, len(SPEC)

METHODS = ["card", "netbanking", "upi", "wallet"]
BANKS = ["HDFC", "ICICI", "KOTAK", "AXIS", "SBIN"]

orders, payments, fees, settlements, truth = [], [], [], [], []
base = dt.datetime(2026, 4, 1, 9, 15)

for index, (kind, net, param, note) in enumerate(SPEC, start=1):
    oid = f"ord_h{index:04d}"
    pid = f"pay_h{index:04d}"
    gst = round(net * 0.18)
    gross = net + gst

    order_dt = base + dt.timedelta(days=index % 27, hours=index % 9, minutes=index % 47)
    orders.append({
        "order_id": oid,
        "order_date": order_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "customer_id": f"cust_{7000 + (index * 13) % 900}",
        "net_amount_paise": net,
        "gst_amount_paise": gst,
        "gross_amount_paise": gross,
        "payment_id": pid,
        "status": "paid",
    })

    if kind == "missing":
        truth.append({
            "order_id": oid, "payment_id": pid,
            "anomaly_type": "payment_not_received",
            "expected_amount_paise": gross,
            "actual_amount_paise": 0,
            "delta_paise": -gross,
            "notes": note,
        })
        continue

    fee = round(gross * 0.02)
    gst_on_fee = round(fee * 0.18)
    total_deduction = fee + gst_on_fee
    expected = gross - total_deduction

    captured = order_dt + dt.timedelta(minutes=18 + index % 40)
    payments.append({
        "payment_id": pid, "order_id": oid,
        "captured_at": captured.strftime("%Y-%m-%d %H:%M:%S"),
        "amount_paise": gross,
        "method": METHODS[index % 4],
        "status": "captured",
    })
    fees.append({
        "payment_id": pid, "fee_paise": fee,
        "gst_on_fee_paise": gst_on_fee,
        "total_deduction_paise": total_deduction,
    })

    if kind == "clean":
        shortfall, anomaly = 0, None
    elif kind == "refund_abs":
        shortfall, anomaly = param, "refund_not_reflected"
    elif kind == "refund_pct":
        shortfall, anomaly = round(gross * param), "refund_not_reflected"
    elif kind == "shortfall_pct":
        shortfall, anomaly = round(gross * param), "settlement_shortfall"
    elif kind == "chargeback":
        shortfall, anomaly = gross + param, "chargeback"
    elif kind == "refund_two":
        shortfall, anomaly = param[0] + param[1], "refund_not_reflected"
    elif kind == "refund_and_short":
        shortfall = round(gross * param[0]) + param[1]
        anomaly = "refund_not_reflected"
    elif kind == "overpaid":
        shortfall, anomaly = -param, "settlement_excess"
    else:
        raise AssertionError(kind)

    settled_amount = expected - shortfall
    settled_dt = (captured + dt.timedelta(days=1 + index % 4)).replace(
        hour=11, minute=30, second=0
    )
    settlements.append({
        "settlement_id": f"setl_h{(index // 8) + 1:04d}_{index:05d}",
        "payment_id": pid,
        "settled_at": settled_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "amount_paise": settled_amount,
        "utr": f"{BANKS[index % 5]}{4000000000 + index * 7919}",
        "status": "processed",
    })

    if anomaly:
        truth.append({
            "order_id": oid, "payment_id": pid,
            "anomaly_type": anomaly,
            "expected_amount_paise": expected,
            "actual_amount_paise": settled_amount,
            "delta_paise": settled_amount - expected,
            "notes": note,
        })


def write(name, rows, columns):
    with open(OUT / name, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {name}: {len(rows)} rows")


write("orders.csv", orders, ["order_id", "order_date", "customer_id",
                             "net_amount_paise", "gst_amount_paise",
                             "gross_amount_paise", "payment_id", "status"])
write("payments.csv", payments, ["payment_id", "order_id", "captured_at",
                                 "amount_paise", "method", "status"])
write("fees.csv", fees, ["payment_id", "fee_paise", "gst_on_fee_paise",
                         "total_deduction_paise"])
write("settlements.csv", settlements, ["settlement_id", "payment_id", "settled_at",
                                       "amount_paise", "utr", "status"])
write("ground_truth.csv", truth, ["order_id", "payment_id", "anomaly_type",
                                  "expected_amount_paise", "actual_amount_paise",
                                  "delta_paise", "notes"])

import collections
print("\nanomaly breakdown:")
for name, count in sorted(collections.Counter(r["anomaly_type"] for r in truth).items()):
    print(f"  {name:24} {count}")
print(f"  {'TOTAL':24} {len(truth)}  ({len(orders) - len(truth)} clean)")
