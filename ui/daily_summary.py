"""Daily financial summary page."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import COLOR_INCOMING, COLOR_NET, COLOR_OUTGOING, EXCEL_EXPORT_DIR
from core import calculations as calc
from core.report_generator import daily_summary_to_excel, save_export, timestamped_name
from ui.common import (
    SUMMARY_COLUMN_CONFIG,
    cards_row,
    empty_state,
    load_transactions,
    metric_card,
    money,
    page_header,
    section,
    settings,
    style_figure,
    summary_display,
)


def _net_chart(daily: pd.DataFrame) -> go.Figure:
    x = pd.to_datetime(daily["date"])
    net = [float(v) for v in daily["net"]]
    fig = go.Figure()
    fig.add_bar(x=x, y=[float(v) for v in daily["incoming"]], name="Incoming",
                marker=dict(color=COLOR_INCOMING), hovertemplate="%{x|%d %b %Y}<br>Incoming: $%{y:,.2f}<extra></extra>")
    fig.add_bar(x=x, y=[-float(v) for v in daily["outgoing"]], name="Outgoing",
                marker=dict(color=COLOR_OUTGOING), customdata=[float(v) for v in daily["outgoing"]],
                hovertemplate="%{x|%d %b %Y}<br>Outgoing: $%{customdata:,.2f}<extra></extra>")
    fig.add_scatter(x=x, y=net, name="Net", mode="lines+markers",
                    line=dict(color=COLOR_NET, width=2),
                    marker=dict(size=8, color="#FFFFFF", line=dict(color=COLOR_NET, width=2)),
                    hovertemplate="%{x|%d %b %Y}<br>Net: $%{y:,.2f}<extra></extra>")
    fig.update_layout(barmode="relative", title=dict(text="Daily incoming (above) and outgoing (below) with net line",
                                                     x=0, font=dict(size=14)))
    fig.update_traces(marker_cornerradius=3, selector=dict(type="bar"))
    fig.update_xaxes(tickformat="%d %b")
    return style_figure(fig, height=360)


def render() -> None:
    cfg = settings()
    page_header("Daily Summary", "Incoming, outgoing and net position per day. Transfer Count includes unclassified "
                "transfers; the USD columns exclude them.", icon=":material/calendar_month:")
    frame = load_transactions()
    if frame.empty:
        empty_state()
        return

    min_date = datetime.fromisoformat(str(frame["txn_date"].min())).date()
    max_date = datetime.fromisoformat(str(frame["txn_date"].max())).date()
    c1, c2 = st.columns([2, 3])
    date_range = c1.date_input("Period", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
    elif isinstance(date_range, tuple) and date_range:
        start = end = date_range[0]
    else:
        start = end = date_range
    scoped = calc.filter_by_date(frame, start, end)
    totals = calc.compute_totals(scoped)
    daily = calc.daily_summary(scoped)

    cards_row([
        metric_card("Incoming (USD)", money(totals.total_incoming), f"{start} to {end}", tone="income"),
        metric_card("Outgoing (USD)", money(totals.total_outgoing), f"{totals.outgoing_count} transfers", tone="expense"),
        metric_card("Net (USD)", money(totals.net_balance), "Incoming minus outgoing", tone="net",
                    negative=totals.net_balance < 0),
        metric_card("Days with activity", f"{len(daily):,}", f"{totals.total_count} transfers, "
                                                              f"{totals.unclassified_count} unclassified", tone="warn"),
    ])

    section("Summary table")
    table = summary_display(daily, "Date")
    st.dataframe(table, hide_index=True, width="stretch", column_config=SUMMARY_COLUMN_CONFIG,
                 height=min(500, 60 + 35 * max(len(table), 1)))
    total_row = pd.DataFrame({
        "Date": ["TOTAL"],
        "Incoming (USD)": [float(totals.total_incoming)],
        "Outgoing (USD)": [float(totals.total_outgoing)],
        "Net (USD)": [float(totals.net_balance)],
        "Transfers": [totals.total_count],
        "Unclassified": [totals.unclassified_count],
    })
    st.dataframe(total_row, hide_index=True, width="stretch", column_config=SUMMARY_COLUMN_CONFIG)

    if not daily.empty:
        st.plotly_chart(_net_chart(daily), width="stretch", config={"displayModeBar": False})

    section("Local currency (kept separate from USD figures)",
            "Sum of Amount in Local Currency where an exchange rate was supplied.")
    local = calc.local_currency_totals(scoped)
    if local.empty or (local["local_total"] == 0).all():
        st.caption("No local-currency amounts recorded in this period (no exchange rates entered).")
    else:
        view = pd.DataFrame({
            "Currency": local["currency"], "Direction": local["direction"], "Transfers": local["count"],
            "Local total": [float(v) for v in local["local_total"]],
            "Without rate": local["missing_rate_count"],
        })
        st.dataframe(view, hide_index=True, width="stretch",
                     column_config={"Local total": st.column_config.NumberColumn(format="%.2f")})

    section("Export")
    col1, col2 = st.columns([1, 3])
    data = daily_summary_to_excel(scoped, office_name=cfg["office_name"], generated_at=datetime.now())
    filename = timestamped_name("daily_summary", "xlsx")
    col1.download_button("Download daily summary (Excel)", data=data, file_name=filename,
                         mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         icon=":material/download:", width="stretch")
    if col2.button("Save a copy to the exports/excel folder", icon=":material/save:"):
        path = save_export(data, EXCEL_EXPORT_DIR, filename)
        st.success(f"Saved to {path}", icon=":material/check_circle:")
