"""Daily Money Transfer Manager 2026 - Streamlit entry point.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from config import APP_SHORT_TITLE, APP_TITLE, APP_VERSION
from core import calculations as calc
from ui import dashboard, daily_summary, reports_page, settings_page, transactions_page, upload_page
from ui.common import inject_css, load_transactions, money, settings

st.set_page_config(
    page_title=APP_TITLE,
    page_icon=":material/currency_exchange:",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()


def _sidebar() -> None:
    cfg = settings()
    with st.sidebar:
        st.markdown(
            f'<div class="dm-brand"><div class="title">{APP_TITLE}</div>'
            f'<div class="sub">{cfg["office_name"]}</div></div>',
            unsafe_allow_html=True,
        )
        st.divider()
        frame = load_transactions()
        totals = calc.compute_totals(frame)
        st.markdown(
            f'<div class="dm-sidestat"><span>Transactions</span><b>{totals.total_count:,}</b></div>'
            f'<div class="dm-sidestat"><span>Net balance</span><b>{money(totals.net_balance)}</b></div>'
            f'<div class="dm-sidestat"><span>Unclassified</span><b>{totals.unclassified_count:,}</b></div>',
            unsafe_allow_html=True,
        )
        st.divider()
        st.caption(f"{APP_SHORT_TITLE} v{APP_VERSION}")


pages = [
    st.Page(dashboard.render, title="Dashboard", icon=":material/dashboard:", default=True, url_path="dashboard"),
    st.Page(upload_page.render, title="Excel Upload", icon=":material/upload_file:", url_path="upload"),
    st.Page(transactions_page.render, title="Transactions", icon=":material/receipt_long:", url_path="transactions"),
    st.Page(daily_summary.render, title="Daily Summary", icon=":material/calendar_month:", url_path="daily-summary"),
    st.Page(reports_page.render, title="Reports", icon=":material/summarize:", url_path="reports"),
    st.Page(settings_page.render, title="Settings", icon=":material/settings:", url_path="settings"),
]

navigation = st.navigation(pages, position="sidebar")
_sidebar()
navigation.run()
