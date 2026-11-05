"""Financial calculation engine, checked against hand-computed expected values.

Synthetic data (tests/conftest.py SYNTHETIC_ROWS):

    date        direction   amount
    2026-01-05  Incoming    100.10
    2026-01-05  Outgoing     40.05
    2026-01-05  (blank)      10.00
    2026-01-06  Incoming    250.00
    2026-01-06  Outgoing    300.25
    2026-02-01  Incoming      0.10
    2026-02-01  Incoming      0.20   (rate 28500 -> local 5700.00)

Expected: incoming 350.40, outgoing 340.30, net 10.10, unclassified 10.00 (1 row).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from core import calculations as calc
from core.database import empty_frame
from core.money import local_amount

D = Decimal


def test_totals_match_hand_computed_values(loaded_manager):
    frame = loaded_manager.load_frame()
    totals = calc.compute_totals(frame)
    assert totals.total_incoming == D("350.40")
    assert totals.total_outgoing == D("340.30")
    assert totals.net_balance == D("10.10")
    assert totals.total_count == 7
    assert (totals.incoming_count, totals.outgoing_count, totals.unclassified_count) == (4, 2, 1)
    assert totals.unclassified_amount == D("10.00")
    # Unclassified excluded from totals but not lost: everything adds up to the independent sum.
    assert totals.total_incoming + totals.total_outgoing + totals.unclassified_amount == D("700.70")
    assert calc.verify_against_independent_sum(frame) == D("700.70")


def test_small_amounts_do_not_suffer_float_error(loaded_manager):
    frame = loaded_manager.load_frame()
    feb = calc.filter_by_date(frame, date(2026, 2, 1), date(2026, 2, 1))
    assert calc.compute_totals(feb).total_incoming == D("0.30")   # 0.1 + 0.2 exactly


def test_daily_summary(loaded_manager):
    daily = calc.daily_summary(loaded_manager.load_frame())
    assert daily["date"].tolist() == ["2026-01-05", "2026-01-06", "2026-02-01"]
    rows = {r["date"]: r for r in daily.to_dict("records")}
    assert (rows["2026-01-05"]["incoming"], rows["2026-01-05"]["outgoing"], rows["2026-01-05"]["net"]) == (D("100.10"), D("40.05"), D("60.05"))
    assert rows["2026-01-05"]["transfer_count"] == 3 and rows["2026-01-05"]["unclassified_count"] == 1
    assert (rows["2026-01-06"]["incoming"], rows["2026-01-06"]["outgoing"], rows["2026-01-06"]["net"]) == (D("250.00"), D("300.25"), D("-50.25"))
    assert rows["2026-01-06"]["transfer_count"] == 2
    assert (rows["2026-02-01"]["incoming"], rows["2026-02-01"]["outgoing"], rows["2026-02-01"]["net"]) == (D("0.30"), D("0.00"), D("0.30"))
    # Daily figures add up to the overall totals (no double counting).
    assert sum(daily["incoming"], D(0)) == D("350.40")
    assert sum(daily["outgoing"], D(0)) == D("340.30")
    assert int(daily["transfer_count"].sum()) == 7


def test_monthly_summary(loaded_manager):
    monthly = calc.monthly_summary(loaded_manager.load_frame())
    assert monthly["month"].tolist() == ["2026-01", "2026-02"]
    jan, feb = monthly.to_dict("records")
    assert (jan["incoming"], jan["outgoing"], jan["net"], jan["transfer_count"]) == (D("350.10"), D("340.30"), D("9.80"), 5)
    assert (feb["incoming"], feb["outgoing"], feb["net"], feb["transfer_count"]) == (D("0.30"), D("0.00"), D("0.30"), 2)


def test_today_totals(loaded_manager):
    frame = loaded_manager.load_frame()
    today = calc.compute_totals_for_day(frame, date(2026, 1, 6))
    assert (today.total_incoming, today.total_outgoing, today.net_balance, today.total_count) == (D("250.00"), D("300.25"), D("-50.25"), 2)
    none = calc.compute_totals_for_day(frame, date(2026, 1, 7))
    assert none == calc.EMPTY_TOTALS


def test_direction_distribution_and_currency_breakdown(loaded_manager):
    frame = loaded_manager.load_frame()
    dist = calc.direction_distribution(frame)
    assert dist["count"].tolist() == [4, 2, 1]
    assert dist["amount"].tolist() == [D("350.40"), D("340.30"), D("10.00")]
    currencies = calc.currency_breakdown(frame)
    assert currencies.loc[0, "currency"] == "USD" and currencies.loc[0, "count"] == 7


def test_local_currency_kept_separate(loaded_manager):
    frame = loaded_manager.load_frame()
    local = calc.local_currency_totals(frame)
    incoming = local[(local["currency"] == "USD") & (local["direction"] == "Incoming")].iloc[0]
    assert incoming["local_total"] == D("5700.00")      # only the row with a rate: 0.20 x 28500
    assert incoming["missing_rate_count"] == 3          # the other incoming rows have no rate
    # USD totals are unaffected by local amounts.
    assert calc.compute_totals(frame).total_incoming == D("350.40")


def test_local_amount_rule():
    assert local_amount(D("150"), D("28500")) == D("4275000.00")
    assert local_amount(D("126.25"), D("571.5")) == D("72151.88")
    assert local_amount(D("16"), D("0.0035")) == D("0.06")
    assert local_amount(D("16"), None) is None
    assert local_amount(None, D("2")) is None


def test_empty_frame_is_safe():
    frame = empty_frame()
    assert calc.compute_totals(frame) == calc.EMPTY_TOTALS
    assert calc.daily_summary(frame).empty
    assert calc.monthly_summary(frame).empty
    assert calc.local_currency_totals(frame).empty
    assert calc.direction_distribution(frame)["count"].tolist() == [0, 0, 0]


def test_totals_change_when_direction_assigned(loaded_manager):
    frame = loaded_manager.load_frame()
    unclassified_id = int(frame.loc[frame["direction"].isna(), "id"].iloc[0])
    loaded_manager.set_direction([unclassified_id], "Outgoing")
    totals = calc.compute_totals(loaded_manager.load_frame())
    assert totals.total_outgoing == D("350.30")
    assert totals.net_balance == D("0.10")
    assert totals.unclassified_count == 0


def test_scales_to_thousands_of_rows(db):
    """Performance sanity check: 5,000 rows aggregate quickly and exactly."""
    import time
    records = []
    for i in range(5000):
        records.append({
            "txn_no": i + 1, "txn_date": f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
            "direction": ["Incoming", "Outgoing", None][i % 3],
            "sender_name": f"S{i}", "sender_mobile": f"06{i:08d}", "receiver_name": f"R{i}",
            "account_number": None, "currency": "USD", "amount_cents": 1001,
            "exchange_rate": None, "amount_local": None, "notes": None,
            "fingerprint": f"fp{i}", "import_id": None, "source_row": None,
        })
    db.insert_transactions(records)
    start = time.perf_counter()
    frame = db.fetch_transactions()
    totals = calc.compute_totals(frame)
    daily = calc.daily_summary(frame)
    elapsed = time.perf_counter() - start
    assert totals.total_count == 5000
    assert totals.total_incoming == D("1001") * 1667 / 100          # 1667 incoming rows x 10.01
    assert totals.total_outgoing == D("1001") * 1667 / 100          # 1667 outgoing rows
    assert totals.unclassified_count == 1666
    assert int(daily["transfer_count"].sum()) == 5000
    assert elapsed < 5.0
