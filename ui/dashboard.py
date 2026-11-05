"""Financial dashboard page."""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import DIRECTION_INCOMING, DIRECTION_OUTGOING, UNCLASSIFIED_LABEL
from core import calculations as calc
from core.transaction_manager import frame_for_display
from ui.common import (
    DIRECTION_COLORS,
    cards_row,
    display_table,
    empty_state,
    load_transactions,
    metric_card,
    money,
    money_md,
    page_header,
    section,
    settings,
    style_figure,
)


def _kpi_cards(totals: calc.Totals, today_totals: calc.Totals, today: date) -> None:
    cards_row([
        metric_card("Total Incoming (USD)", money(totals.total_incoming),
                    f"{totals.incoming_count:,} classified transfers", tone="income"),
        metric_card("Total Outgoing (USD)", money(totals.total_outgoing),
                    f"{totals.outgoing_count:,} classified transfers", tone="expense"),
        metric_card("Net Balance (USD)", money(totals.net_balance), "Incoming minus outgoing",
                    tone="net", negative=totals.net_balance < 0),
        metric_card("Total Transactions", f"{totals.total_count:,}", "All records in the database"),
    ])
    st.write("")
    cards_row([
        metric_card("Unclassified Transactions", f"{totals.unclassified_count:,}",
                    f"{money(totals.unclassified_amount)} excluded from totals", tone="warn"),
        metric_card(f"Today's Incoming", money(today_totals.total_incoming),
                    today.strftime("%d %b %Y"), tone="income"),
        metric_card("Today's Outgoing", money(today_totals.total_outgoing),
                    f"{today_totals.total_count:,} transfers today", tone="expense"),
        metric_card("Today's Net Balance", money(today_totals.net_balance),
                    f"{today_totals.unclassified_count:,} unclassified today",
                    tone="net", negative=today_totals.net_balance < 0),
    ])


def _chart_in_vs_out(totals: calc.Totals) -> go.Figure:
    labels = [DIRECTION_INCOMING, DIRECTION_OUTGOING, UNCLASSIFIED_LABEL]
    values = [float(totals.total_incoming), float(totals.total_outgoing), float(totals.unclassified_amount)]
    counts = [totals.incoming_count, totals.outgoing_count, totals.unclassified_count]
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker=dict(color=[DIRECTION_COLORS[l] for l in labels], line=dict(width=0)),
        text=[money(totals.total_incoming), money(totals.total_outgoing), money(totals.unclassified_amount)],
        textposition="outside", cliponaxis=False,
        customdata=counts,
        hovertemplate="<b>%{x}</b><br>$%{y:,.2f}<br>%{customdata} transfers<extra></extra>",
        width=0.55,
    ))
    fig.update_layout(title=dict(text="Incoming vs Outgoing (USD)", x=0, font=dict(size=14)))
    fig.update_traces(marker_cornerradius=4)
    return style_figure(fig, legend=False)


def _chart_daily_volume(daily: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not daily.empty:
        x = pd.to_datetime(daily["date"])
        for key, label in (("incoming", DIRECTION_INCOMING), ("outgoing", DIRECTION_OUTGOING),
                           ("unclassified_amount", UNCLASSIFIED_LABEL)):
            fig.add_bar(
                x=x, y=[float(v) for v in daily[key]], name=label,
                marker=dict(color=DIRECTION_COLORS[label], line=dict(color="#FFFFFF", width=1)),
                customdata=daily["transfer_count"],
                hovertemplate="%{x|%d %b %Y}<br>" + label + ": $%{y:,.2f}<br>%{customdata} transfers that day<extra></extra>",
            )
    fig.update_layout(barmode="stack", title=dict(text="Daily transaction volume (USD)", x=0, font=dict(size=14)))
    fig.update_traces(marker_cornerradius=3)
    fig.update_xaxes(tickformat="%d %b")
    return style_figure(fig)


def _chart_monthly(monthly: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not monthly.empty:
        x = monthly["month"].tolist()
        fig.add_bar(x=x, y=[float(v) for v in monthly["incoming"]], name=DIRECTION_INCOMING,
                    marker=dict(color=DIRECTION_COLORS[DIRECTION_INCOMING]),
                    hovertemplate="%{x}<br>Incoming: $%{y:,.2f}<extra></extra>")
        fig.add_bar(x=x, y=[float(v) for v in monthly["outgoing"]], name=DIRECTION_OUTGOING,
                    marker=dict(color=DIRECTION_COLORS[DIRECTION_OUTGOING]),
                    hovertemplate="%{x}<br>Outgoing: $%{y:,.2f}<extra></extra>")
        fig.add_scatter(x=x, y=[float(v) for v in monthly["net"]], name="Net", mode="lines+markers",
                        line=dict(color=DIRECTION_COLORS["Net"], width=2),
                        marker=dict(size=9, color="#FFFFFF", line=dict(color=DIRECTION_COLORS["Net"], width=2)),
                        hovertemplate="%{x}<br>Net: $%{y:,.2f}<extra></extra>")
    fig.update_layout(barmode="group", title=dict(text="Monthly financial trend (USD)", x=0, font=dict(size=14)))
    fig.update_traces(marker_cornerradius=3, selector=dict(type="bar"))
    return style_figure(fig)


def _chart_distribution(totals: calc.Totals) -> go.Figure:
    slices = [
        (DIRECTION_INCOMING, totals.incoming_count, float(totals.total_incoming)),
        (DIRECTION_OUTGOING, totals.outgoing_count, float(totals.total_outgoing)),
        (UNCLASSIFIED_LABEL, totals.unclassified_count, float(totals.unclassified_amount)),
    ]
    slices = [s for s in slices if s[1] > 0]   # zero slices would only add "0%" clutter
    labels = [s[0] for s in slices]
    counts = [s[1] for s in slices]
    amounts = [s[2] for s in slices]
    fig = go.Figure(go.Pie(
        labels=labels, values=counts, hole=0.62, sort=False,
        marker=dict(colors=[DIRECTION_COLORS[l] for l in labels], line=dict(color="#FFFFFF", width=2)),
        customdata=amounts, textinfo="percent",
        hovertemplate="<b>%{label}</b><br>%{value} transfers<br>$%{customdata:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text="Transaction distribution (count)", x=0, font=dict(size=14)),
        annotations=[dict(text=f"<b>{totals.total_count:,}</b><br><span style='font-size:11px'>transfers</span>",
                          x=0.5, y=0.5, showarrow=False, font=dict(size=18))],
    )
    return style_figure(fig)


def render() -> None:
    cfg = settings()
    page_header("Financial Dashboard", f"{cfg['office_name']} - all figures are calculated live from the database.",
                icon=":material/dashboard:")
    frame = load_transactions()
    if frame.empty:
        empty_state()
        return

    today = date.today()
    totals = calc.compute_totals(frame)
    today_totals = calc.compute_totals_for_day(frame, today)
    _kpi_cards(totals, today_totals, today)

    if totals.unclassified_count:
        st.warning(
            f"**{totals.unclassified_count} transaction(s) totalling {money_md(totals.unclassified_amount)} have no "
            "direction yet.** They are excluded from Incoming, Outgoing and Net Balance until you classify them "
            "on the Transactions page (Classify tab).",
            icon=":material/rule:",
        )

    daily = calc.daily_summary(frame)
    monthly = calc.monthly_summary(frame)

    section("Charts")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(_chart_in_vs_out(totals), width="stretch", config={"displayModeBar": False})
    with right:
        st.plotly_chart(_chart_distribution(totals), width="stretch", config={"displayModeBar": False})
    left2, right2 = st.columns(2)
    with left2:
        st.plotly_chart(_chart_daily_volume(daily), width="stretch", config={"displayModeBar": False})
    with right2:
        st.plotly_chart(_chart_monthly(monthly), width="stretch", config={"displayModeBar": False})

    section("Recent transactions", "The 10 most recently dated records.")
    recent = frame.sort_values(["txn_date", "id"], ascending=[False, False]).head(10)
    display_table(frame_for_display(recent))

    with st.expander("How these figures are calculated"):
        st.markdown(
            """
            * **Total Incoming** = sum of *Amount (USD)* where Direction = Incoming.
            * **Total Outgoing** = sum of *Amount (USD)* where Direction = Outgoing.
            * **Net Balance** = Total Incoming - Total Outgoing.
            * **Unclassified** transfers are counted and shown separately; they never enter the totals.
            * All sums use exact decimal arithmetic (amounts are stored in cents).
            * Local-currency amounts (Amount x Exchange Rate) are kept separate from USD figures and
              are shown on the Daily Summary page.
            """
        )
        st.caption(
            f"Cross-check: straightforward decimal sum of every amount = "
            f"{money_md(calc.verify_against_independent_sum(frame))} "
            f"(engine: {money_md(totals.total_incoming + totals.total_outgoing + totals.unclassified_amount)})."
        )
