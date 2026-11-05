"""Shared UI helpers: cached data access, theme CSS and reusable widgets."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import (
    APP_TITLE,
    COLOR_INCOMING,
    COLOR_NET,
    COLOR_OUTGOING,
    COLOR_SURFACE,
    COLOR_UNCLASSIFIED,
    DB_PATH,
    DIRECTION_INCOMING,
    DIRECTION_OUTGOING,
    UNCLASSIFIED_LABEL,
)
from core.database import Database
from core.money import format_usd
from core.transaction_manager import TransactionManager

DIRECTION_COLORS = {
    DIRECTION_INCOMING: COLOR_INCOMING,
    DIRECTION_OUTGOING: COLOR_OUTGOING,
    UNCLASSIFIED_LABEL: COLOR_UNCLASSIFIED,
    "Net": COLOR_NET,
}


# --------------------------------------------------------------------------
# Data access
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _database(path: str) -> Database:
    return Database(path)


def get_db() -> Database:
    return _database(str(DB_PATH))


def get_manager() -> TransactionManager:
    return TransactionManager(get_db())


@st.cache_data(show_spinner=False, max_entries=4)
def _load_frame(path: str, signature: tuple) -> pd.DataFrame:
    # ``signature`` is part of the cache key so the frame is re-read only when
    # the database content has actually changed.
    return Database(path).fetch_transactions()


def load_transactions() -> pd.DataFrame:
    db = get_db()
    return _load_frame(str(db.path), db.signature())


def clear_data_cache() -> None:
    """Drop cached DataFrames after the database file itself was replaced."""
    _load_frame.clear()


def settings() -> dict[str, str]:
    return get_db().all_settings()


# --------------------------------------------------------------------------
# Theme
# --------------------------------------------------------------------------
_CSS = """
<style>
:root {
  --dm-navy: #1F3A5F;
  --dm-ink: #1B2430;
  --dm-muted: #5B6676;
  --dm-border: #E1E6EE;
  --dm-card: #FFFFFF;
  --dm-income: #1baf7a;
  --dm-expense: #eb6834;
  --dm-net: #2a78d6;
  --dm-warn: #c98500;
}
section.main > div { padding-top: 1rem; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1400px; }
h1, h2, h3 { color: var(--dm-ink); letter-spacing: -0.01em; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #1F3A5F 0%, #16304F 100%); }
[data-testid="stSidebar"] * { color: #EAF0F8; }
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] { border-radius: 8px; margin: 2px 0; }
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:hover { background: rgba(255,255,255,0.08); }
[data-testid="stSidebar"] a[aria-current="page"] { background: rgba(255,255,255,0.16) !important; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.15); }
.dm-brand { padding: 0.4rem 0 0.6rem 0; }
.dm-brand .title { font-weight: 700; font-size: 1.05rem; line-height: 1.2; }
.dm-brand .sub { font-size: 0.78rem; opacity: 0.75; margin-top: 2px; }
.dm-sidestat { display:flex; justify-content:space-between; font-size:0.82rem; padding: 3px 0; opacity: 0.9; }
.dm-sidestat b { font-variant-numeric: tabular-nums; }
.dm-card {
  background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: 14px;
  padding: 14px 16px 12px 16px; box-shadow: 0 1px 2px rgba(16,24,40,0.04); height: 100%;
  border-top: 4px solid var(--dm-navy);
}
.dm-card.income { border-top-color: var(--dm-income); }
.dm-card.expense { border-top-color: var(--dm-expense); }
.dm-card.net { border-top-color: var(--dm-net); }
.dm-card.warn { border-top-color: var(--dm-warn); }
.dm-card .label { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--dm-muted); font-weight: 600; }
.dm-card .value { font-size: 1.55rem; font-weight: 700; color: var(--dm-ink); margin-top: 4px; font-variant-numeric: tabular-nums; }
.dm-card .value.negative { color: #c0392b; }
.dm-card .caption { font-size: 0.78rem; color: var(--dm-muted); margin-top: 4px; }
.dm-section { margin-top: 1.4rem; margin-bottom: 0.4rem; }
.dm-section h3 { margin: 0; font-size: 1.1rem; }
.dm-section p { margin: 2px 0 0 0; color: var(--dm-muted); font-size: 0.85rem; }
.dm-note { background: #FFF7E6; border: 1px solid #F3D9A4; border-radius: 10px; padding: 10px 14px; font-size: 0.9rem; }
.dm-pill { display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
.dm-pill.income { background: #E3F7EE; color: #0d7a52; }
.dm-pill.expense { background: #FDE9E0; color: #b4471c; }
.dm-pill.neutral { background: #EEF0F3; color: #4b5563; }
div[data-testid="stMetric"] { background: var(--dm-card); border: 1px solid var(--dm-border); border-radius: 12px; padding: 10px 14px; }
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------
def page_header(title: str, subtitle: str | None = None, icon: str = "") -> None:
    st.markdown(f"## {icon} {title}".strip())
    if subtitle:
        st.caption(subtitle)


def section(title: str, subtitle: str | None = None) -> None:
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(f'<div class="dm-section"><h3>{title}</h3>{sub}</div>', unsafe_allow_html=True)


def metric_card(label: str, value: str, caption: str | None = None, tone: str = "neutral",
                negative: bool = False) -> str:
    cap = f'<div class="caption">{caption}</div>' if caption else ""
    neg = " negative" if negative else ""
    return (f'<div class="dm-card {tone}"><div class="label">{label}</div>'
            f'<div class="value{neg}">{value}</div>{cap}</div>')


def cards_row(cards: Iterable[str]) -> None:
    cards = list(cards)
    cols = st.columns(len(cards))
    for col, html in zip(cols, cards):
        col.markdown(html, unsafe_allow_html=True)


def money(value: Decimal | None) -> str:
    """Plain ``$1,234.56`` for HTML cards, labels and plain text."""
    return format_usd(value)


def money_md(value: Decimal | None) -> str:
    """Money for Markdown contexts (st.markdown/st.caption/st.success/...).

    A bare ``$`` pair would be interpreted as LaTeX by Streamlit's Markdown
    renderer, so the sign is escaped.
    """
    return format_usd(value).replace("$", "\\$")


def note(text: str) -> None:
    st.markdown(f'<div class="dm-note">{text}</div>', unsafe_allow_html=True)


def empty_state(message: str = "No transactions yet. Import an Excel file or add a transaction to get started.") -> None:
    st.info(message + " Use the sidebar to open **Excel Upload** or **Transactions**.", icon=":material/info:")


def style_figure(fig: go.Figure, height: int = 340, legend: bool = True) -> go.Figure:
    """Consistent, recessive chart chrome (thin marks, light grid, no clutter)."""
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=44, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=COLOR_SURFACE,
        font=dict(family="Segoe UI, Inter, sans-serif", size=12, color="#1B2430"),
        title=dict(x=0, xanchor="left", y=0.97, yanchor="top", font=dict(size=14)),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="left", x=0,
                    font=dict(size=11), title=None, traceorder="normal") if legend else dict(),
        showlegend=legend,
        hoverlabel=dict(bgcolor="white", font_size=12),
        bargap=0.35,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="#D5DBE5", tickfont=dict(size=11))
    fig.update_yaxes(showgrid=True, gridcolor="#E9EDF3", zeroline=True, zerolinecolor="#C9D1DC",
                     tickfont=dict(size=11), tickprefix="$", separatethousands=True)
    return fig


def direction_label(value: str | None) -> str:
    return value if value else UNCLASSIFIED_LABEL


def display_table(frame: pd.DataFrame, *, height: int | None = None, key: str | None = None) -> None:
    """Render a transactions display frame with sensible column formatting."""
    config = {
        "ID": st.column_config.NumberColumn("ID", width="small", format="%d"),
        "No.": st.column_config.NumberColumn("No.", width="small", format="%d"),
        "Date": st.column_config.TextColumn("Date", width="small"),
        "Direction": st.column_config.TextColumn("Direction", width="small"),
        "Amount (USD)": st.column_config.NumberColumn("Amount (USD)", format="dollar"),
        "Exchange Rate": st.column_config.NumberColumn("Exchange Rate", format="%.4f"),
        "Amount in Local Currency": st.column_config.NumberColumn("Amount (Local)", format="localized"),
        "Sender Mobile": st.column_config.TextColumn("Sender Mobile"),
        "Account Number": st.column_config.TextColumn("Account Number"),
    }
    kwargs = {"height": height} if height is not None else {}
    st.dataframe(frame, hide_index=True, width="stretch", column_config=config, key=key, **kwargs)


def summary_display(summary: pd.DataFrame, key_label: str) -> pd.DataFrame:
    """Convert a Decimal summary frame to a display frame (floats for formatting only)."""
    if summary is None or summary.empty:
        return pd.DataFrame(columns=[key_label, "Incoming (USD)", "Outgoing (USD)", "Net (USD)",
                                     "Transfers", "Unclassified"])
    key_col = summary.columns[0]
    return pd.DataFrame({
        key_label: summary[key_col].to_numpy(),
        "Incoming (USD)": [float(v) for v in summary["incoming"]],
        "Outgoing (USD)": [float(v) for v in summary["outgoing"]],
        "Net (USD)": [float(v) for v in summary["net"]],
        "Transfers": summary["transfer_count"].astype(int).to_numpy(),
        "Unclassified": summary["unclassified_count"].astype(int).to_numpy(),
    })


SUMMARY_COLUMN_CONFIG = {
    "Incoming (USD)": st.column_config.NumberColumn(format="dollar"),
    "Outgoing (USD)": st.column_config.NumberColumn(format="dollar"),
    "Net (USD)": st.column_config.NumberColumn(format="dollar"),
}

APP_NAME = APP_TITLE
