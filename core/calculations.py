"""Financial calculation engine.

Every function here is a *pure* function of the transactions DataFrame
produced by :func:`core.database.Database.fetch_transactions` (or any frame
with the same columns). Nothing touches the database or Streamlit, which is
what makes the figures reproducible and unit-testable.

Rules implemented (from the project brief):

* Total Incoming  = sum of Amount (USD) where Direction = Incoming.
* Total Outgoing  = sum of Amount (USD) where Direction = Outgoing.
* Net Balance     = Total Incoming - Total Outgoing.
* Unclassified transactions are *excluded* from incoming/outgoing totals and
  reported separately so they are never silently ignored.
* Local currency amounts are kept completely separate from USD figures.
* All arithmetic is exact: amounts are integer cents converted to Decimal.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from config import DIRECTION_INCOMING, DIRECTION_OUTGOING, UNCLASSIFIED_LABEL
from core.money import ZERO, cents_to_decimal, local_amount, to_decimal


@dataclass(frozen=True)
class Totals:
    total_incoming: Decimal
    total_outgoing: Decimal
    net_balance: Decimal
    total_count: int
    incoming_count: int
    outgoing_count: int
    unclassified_count: int
    unclassified_amount: Decimal

    def as_dict(self) -> dict:
        return asdict(self)


EMPTY_TOTALS = Totals(ZERO, ZERO, ZERO, 0, 0, 0, 0, ZERO)


def _cents(series: pd.Series) -> int:
    """Exact integer sum of a cents column (0 for an empty selection)."""
    if series.empty:
        return 0
    return int(series.to_numpy(dtype="int64").sum())


def compute_totals(frame: pd.DataFrame) -> Totals:
    """Headline figures for a set of transactions."""
    if frame is None or frame.empty:
        return EMPTY_TOTALS
    direction = frame["direction"]
    incoming_mask = (direction == DIRECTION_INCOMING).to_numpy()
    outgoing_mask = (direction == DIRECTION_OUTGOING).to_numpy()
    unclassified_mask = ~(incoming_mask | outgoing_mask)
    cents = frame["amount_cents"]
    incoming = _cents(cents[incoming_mask])
    outgoing = _cents(cents[outgoing_mask])
    unclassified = _cents(cents[unclassified_mask])
    return Totals(
        total_incoming=cents_to_decimal(incoming),
        total_outgoing=cents_to_decimal(outgoing),
        net_balance=cents_to_decimal(incoming - outgoing),
        total_count=int(len(frame)),
        incoming_count=int(incoming_mask.sum()),
        outgoing_count=int(outgoing_mask.sum()),
        unclassified_count=int(unclassified_mask.sum()),
        unclassified_amount=cents_to_decimal(unclassified),
    )


def filter_by_date(frame: pd.DataFrame, start: date | None = None,
                   end: date | None = None) -> pd.DataFrame:
    """Rows whose txn_date falls inside [start, end] (inclusive, ISO strings)."""
    if frame is None or frame.empty:
        return frame
    mask = np.ones(len(frame), dtype=bool)
    dates = frame["txn_date"].astype(str).to_numpy()
    if start is not None:
        mask &= dates >= start.isoformat()
    if end is not None:
        mask &= dates <= end.isoformat()
    return frame[mask]


def compute_totals_for_day(frame: pd.DataFrame, day: date) -> Totals:
    """Totals restricted to one calendar day (used for the "Today" cards)."""
    return compute_totals(filter_by_date(frame, day, day))


def _period_summary(frame: pd.DataFrame, key: pd.Series, key_name: str) -> pd.DataFrame:
    columns = [key_name, "incoming", "outgoing", "net", "transfer_count",
               "incoming_count", "outgoing_count", "unclassified_count", "unclassified_amount"]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)
    direction = frame["direction"].to_numpy(dtype=object)
    cents = frame["amount_cents"].to_numpy(dtype="int64")
    is_in = direction == DIRECTION_INCOMING
    is_out = direction == DIRECTION_OUTGOING
    is_unc = ~(is_in | is_out)
    work = pd.DataFrame({
        key_name: key.to_numpy(),
        "incoming_c": np.where(is_in, cents, 0),
        "outgoing_c": np.where(is_out, cents, 0),
        "unclassified_c": np.where(is_unc, cents, 0),
        "incoming_count": is_in.astype("int64"),
        "outgoing_count": is_out.astype("int64"),
        "unclassified_count": is_unc.astype("int64"),
        "transfer_count": np.ones(len(frame), dtype="int64"),
    })
    grouped = work.groupby(key_name, sort=True).sum(numeric_only=True).reset_index()
    result = pd.DataFrame({
        key_name: grouped[key_name],
        "incoming": [cents_to_decimal(v) for v in grouped["incoming_c"]],
        "outgoing": [cents_to_decimal(v) for v in grouped["outgoing_c"]],
        "net": [cents_to_decimal(i - o) for i, o in zip(grouped["incoming_c"], grouped["outgoing_c"])],
        "transfer_count": grouped["transfer_count"].astype("int64"),
        "incoming_count": grouped["incoming_count"].astype("int64"),
        "outgoing_count": grouped["outgoing_count"].astype("int64"),
        "unclassified_count": grouped["unclassified_count"].astype("int64"),
        "unclassified_amount": [cents_to_decimal(v) for v in grouped["unclassified_c"]],
    })
    return result[columns]


def daily_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar day: Date, Incoming, Outgoing, Net, Transfer Count.

    ``transfer_count`` counts *all* transfers on the day (matching the Excel
    workbook's COUNTIF), while incoming/outgoing exclude unclassified rows.
    """
    key = frame["txn_date"].astype(str) if frame is not None and not frame.empty else pd.Series(dtype=str)
    return _period_summary(frame, key, "date")


def monthly_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar month (``YYYY-MM``)."""
    key = frame["txn_date"].astype(str).str.slice(0, 7) if frame is not None and not frame.empty else pd.Series(dtype=str)
    return _period_summary(frame, key, "month")


def direction_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    """Count and USD amount per direction, including Unclassified."""
    totals = compute_totals(frame)
    return pd.DataFrame({
        "direction": [DIRECTION_INCOMING, DIRECTION_OUTGOING, UNCLASSIFIED_LABEL],
        "count": [totals.incoming_count, totals.outgoing_count, totals.unclassified_count],
        "amount": [totals.total_incoming, totals.total_outgoing, totals.unclassified_amount],
    })


def currency_breakdown(frame: pd.DataFrame) -> pd.DataFrame:
    """Transfers per currency column value (USD figures only)."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["currency", "count", "amount"])
    currency = frame["currency"].fillna("(blank)").astype(str)
    work = pd.DataFrame({"currency": currency.to_numpy(),
                         "cents": frame["amount_cents"].to_numpy(dtype="int64")})
    grouped = work.groupby("currency").agg(count=("cents", "size"), cents=("cents", "sum")).reset_index()
    grouped["amount"] = [cents_to_decimal(v) for v in grouped["cents"]]
    return grouped[["currency", "count", "amount"]].sort_values("count", ascending=False).reset_index(drop=True)


def local_currency_totals(frame: pd.DataFrame) -> pd.DataFrame:
    """Sum of *stored* local-currency amounts per currency and direction.

    Kept separate from the USD engine on purpose; rows without a local amount
    are reported in ``missing_rate_count`` rather than treated as zero.
    """
    columns = ["currency", "direction", "count", "local_total", "missing_rate_count"]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)
    records: dict[tuple, dict] = {}
    for currency, direction, local in zip(frame["currency"], frame["direction"], frame["amount_local"]):
        key = (currency or "(blank)", direction or UNCLASSIFIED_LABEL)
        bucket = records.setdefault(key, {"count": 0, "local_total": ZERO, "missing": 0})
        bucket["count"] += 1
        value = to_decimal(local) if local not in (None, "") else None
        if value is None:
            bucket["missing"] += 1
        else:
            bucket["local_total"] += value
    rows = [
        {"currency": k[0], "direction": k[1], "count": v["count"],
         "local_total": v["local_total"], "missing_rate_count": v["missing"]}
        for k, v in sorted(records.items())
    ]
    return pd.DataFrame(rows, columns=columns)


def recompute_local_amount(amount_usd: Decimal | None, rate: Decimal | None) -> Decimal | None:
    """Public alias so callers import the local-currency rule from one place."""
    return local_amount(amount_usd, rate)


def verify_against_independent_sum(frame: pd.DataFrame) -> Decimal:
    """Cross-check helper: naive Decimal sum of every amount (all directions).

    Used by tests and the dashboard footnote to prove the cents engine agrees
    with a straightforward Decimal addition.
    """
    total = ZERO
    for cents in frame["amount_cents"].tolist() if frame is not None else []:
        total += cents_to_decimal(cents)
    return total
