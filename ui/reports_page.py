"""Reports page: Excel and PDF exports."""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from config import EXCEL_EXPORT_DIR, REPORT_EXPORT_DIR
from core import calculations as calc
from core.report_generator import (
    daily_summary_to_excel,
    dashboard_to_pdf,
    monthly_summary_to_excel,
    save_export,
    timestamped_name,
    transactions_to_excel,
)
from ui.common import empty_state, load_transactions, money_md, page_header, section, settings

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PDF_MIME = "application/pdf"

_REPORTS = [
    {
        "key": "transactions",
        "title": "All transactions (Excel)",
        "description": "Every record with direction, parties, amounts, exchange rate and notes, plus Decimal-exact totals.",
        "prefix": "transactions", "ext": "xlsx", "mime": _XLSX_MIME, "folder": EXCEL_EXPORT_DIR,
        "icon": ":material/table_view:",
    },
    {
        "key": "daily",
        "title": "Daily financial summary (Excel)",
        "description": "Incoming, outgoing, net and transfer count for each day, with a totals row.",
        "prefix": "daily_summary", "ext": "xlsx", "mime": _XLSX_MIME, "folder": EXCEL_EXPORT_DIR,
        "icon": ":material/calendar_view_day:",
    },
    {
        "key": "monthly",
        "title": "Monthly financial summary (Excel)",
        "description": "The same figures aggregated per calendar month.",
        "prefix": "monthly_summary", "ext": "xlsx", "mime": _XLSX_MIME, "folder": EXCEL_EXPORT_DIR,
        "icon": ":material/calendar_view_month:",
    },
    {
        "key": "pdf",
        "title": "Financial dashboard summary (PDF)",
        "description": "Headline figures, today's position, monthly and daily tables in a printable PDF.",
        "prefix": "dashboard_summary", "ext": "pdf", "mime": _PDF_MIME, "folder": REPORT_EXPORT_DIR,
        "icon": ":material/picture_as_pdf:",
    },
]


def _build(key: str, frame, office_name: str) -> bytes:
    now = datetime.now()
    if key == "transactions":
        return transactions_to_excel(frame, office_name=office_name, generated_at=now)
    if key == "daily":
        return daily_summary_to_excel(frame, office_name=office_name, generated_at=now)
    if key == "monthly":
        return monthly_summary_to_excel(frame, office_name=office_name, generated_at=now)
    today = date.today()
    return dashboard_to_pdf(frame, office_name=office_name, generated_at=now, as_of=today,
                            today_totals=calc.compute_totals_for_day(frame, today))


def render() -> None:
    cfg = settings()
    page_header("Reports", "Generate Excel and PDF reports. Every report carries its generation date and totals "
                "calculated by the same engine as the dashboard.", icon=":material/summarize:")
    frame = load_transactions()
    if frame.empty:
        empty_state()
        return

    totals = calc.compute_totals(frame)
    st.caption(f"Database: {totals.total_count:,} transactions | Incoming {money_md(totals.total_incoming)} | "
               f"Outgoing {money_md(totals.total_outgoing)} | Net {money_md(totals.net_balance)} | "
               f"{totals.unclassified_count} unclassified")

    store = st.session_state.setdefault("prepared_reports", {})
    for spec in _REPORTS:
        section(spec["title"], spec["description"])
        c1, c2, c3 = st.columns([1.3, 1.3, 2])
        if c1.button("Prepare report", key=f"prep_{spec['key']}", icon=spec["icon"], width="stretch"):
            with st.spinner("Generating..."):
                data = _build(spec["key"], frame, cfg["office_name"])
            store[spec["key"]] = (timestamped_name(spec["prefix"], spec["ext"]), data, datetime.now())
        prepared = store.get(spec["key"])
        if prepared:
            filename, data, when = prepared
            c2.download_button("Download", data=data, file_name=filename, mime=spec["mime"],
                               key=f"dl_{spec['key']}", icon=":material/download:", width="stretch")
            if c3.button("Save a copy to the exports folder", key=f"save_{spec['key']}", icon=":material/save:"):
                path = save_export(data, spec["folder"], filename)
                st.success(f"Saved to {path}", icon=":material/check_circle:")
            st.caption(f"Prepared {when.strftime('%Y-%m-%d %H:%M:%S')} - {len(data) / 1024:,.0f} KB - {filename}")
        else:
            c2.caption("Click *Prepare report* first.")
