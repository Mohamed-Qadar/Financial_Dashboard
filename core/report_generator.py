"""Excel and PDF report generation.

All exporters return ``bytes`` so the Streamlit pages can offer them as
downloads and/or save them into the ``exports`` folders. Totals written into
reports are computed with the Decimal engine in :mod:`core.calculations` -
never re-summed with floats. Phone and account numbers are written as text.
"""
from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import APP_TITLE, APP_VERSION
from core.calculations import Totals, compute_totals, daily_summary, monthly_summary
from core.money import cents_to_decimal, format_usd

MONEY_FORMAT = '"$"#,##0.00'
NUMBER_FORMAT = "#,##0.00"
RATE_FORMAT = "#,##0.000000"
TEXT_FORMAT = "@"

_HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_TITLE_FONT = Font(bold=True, size=14, color="1F3A5F")
_META_FONT = Font(italic=True, size=9, color="666666")
_TOTAL_FONT = Font(bold=True)
_TOTAL_FILL = PatternFill("solid", fgColor="E8EEF6")
_THIN = Side(style="thin", color="C9D3E0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _stamp(generated_at: datetime | None) -> str:
    return (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


def _write_title(ws: Worksheet, title: str, generated_at: datetime | None, office_name: str,
                 width: int, extra: list[str] | None = None) -> int:
    """Write the report banner; returns the next free row number."""
    ws.cell(row=1, column=1, value=title).font = _TITLE_FONT
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    lines = [f"Office: {office_name}", f"Generated: {_stamp(generated_at)}  |  {APP_TITLE} v{APP_VERSION}"]
    lines += extra or []
    row = 2
    for line in lines:
        cell = ws.cell(row=row, column=1, value=line)
        cell.font = _META_FONT
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=width)
        row += 1
    return row + 1


def _write_header(ws: Worksheet, row: int, headers: list[str]) -> None:
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col, value=header)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _BORDER
    ws.row_dimensions[row].height = 28


def _autosize(ws: Worksheet, widths: dict[int, float]) -> None:
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


def _as_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


# --------------------------------------------------------------------------
# Transactions export
# --------------------------------------------------------------------------
TRANSACTION_HEADERS = [
    "ID", "No.", "Date", "Direction", "Sender Name", "Sender Mobile", "Receiver Name",
    "Account Number", "Currency", "Amount (USD)", "Exchange Rate",
    "Amount in Local Currency", "Reference / Notes",
]


def transactions_to_excel(frame: pd.DataFrame, *, office_name: str = "",
                          generated_at: datetime | None = None,
                          title: str = "All Transactions") -> bytes:
    totals: Totals = compute_totals(frame)
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    width = len(TRANSACTION_HEADERS)
    start = _write_title(
        ws, title, generated_at, office_name, width,
        extra=[f"Records: {totals.total_count}  |  Unclassified: {totals.unclassified_count}"],
    )
    _write_header(ws, start, TRANSACTION_HEADERS)
    row = start + 1
    for rec in frame.to_dict("records") if frame is not None and not frame.empty else []:
        values = [
            int(rec["id"]),
            None if pd.isna(rec.get("txn_no")) else int(rec["txn_no"]),
            rec.get("txn_date"),
            rec.get("direction") or "Unclassified",
            rec.get("sender_name"),
            rec.get("sender_mobile"),
            rec.get("receiver_name"),
            rec.get("account_number"),
            rec.get("currency"),
            cents_to_decimal(rec["amount_cents"]),
            _as_decimal(rec.get("exchange_rate")),
            _as_decimal(rec.get("amount_local")),
            rec.get("notes"),
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.border = _BORDER
            if col in (6, 8):
                cell.number_format = TEXT_FORMAT
            elif col == 10:
                cell.number_format = MONEY_FORMAT
            elif col == 11:
                cell.number_format = RATE_FORMAT
            elif col == 12:
                cell.number_format = NUMBER_FORMAT
        row += 1

    # Totals block (values computed by the Decimal engine, not spreadsheet formulas)
    row += 1
    summary = [
        ("Total Incoming (USD)", totals.total_incoming),
        ("Total Outgoing (USD)", totals.total_outgoing),
        ("Net Balance (USD)", totals.net_balance),
        ("Unclassified amount (USD, excluded from totals)", totals.unclassified_amount),
        ("Sum of all amounts (USD)", totals.total_incoming + totals.total_outgoing + totals.unclassified_amount),
    ]
    for label, value in summary:
        ws.cell(row=row, column=9, value=label).font = _TOTAL_FONT
        cell = ws.cell(row=row, column=10, value=value)
        cell.number_format = MONEY_FORMAT
        cell.font = _TOTAL_FONT
        cell.fill = _TOTAL_FILL
        row += 1

    _autosize(ws, {1: 7, 2: 7, 3: 12, 4: 13, 5: 28, 6: 17, 7: 28, 8: 16, 9: 10, 10: 15, 11: 14, 12: 20, 13: 30})
    ws.freeze_panes = ws.cell(row=start + 1, column=1)
    _add_metadata_sheet(wb, generated_at, office_name, {"Report": title, "Records": totals.total_count})
    return _workbook_bytes(wb)


# --------------------------------------------------------------------------
# Daily / monthly summaries
# --------------------------------------------------------------------------
def _summary_to_excel(summary: pd.DataFrame, key_label: str, title: str, *, office_name: str,
                      generated_at: datetime | None) -> bytes:
    headers = [key_label, "Incoming (USD)", "Outgoing (USD)", "Net (USD)", "Transfer Count",
               "Incoming Count", "Outgoing Count", "Unclassified Count", "Unclassified Amount (USD)"]
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    start = _write_title(ws, title, generated_at, office_name, len(headers),
                         extra=["Incoming/Outgoing exclude unclassified transfers; Transfer Count includes them."])
    _write_header(ws, start, headers)
    row = start + 1
    key_col = summary.columns[0] if not summary.empty else key_label
    tot_in = tot_out = tot_unc = Decimal("0.00")
    tot_count = tot_in_c = tot_out_c = tot_unc_c = 0
    for rec in summary.to_dict("records"):
        values = [rec[key_col], rec["incoming"], rec["outgoing"], rec["net"], int(rec["transfer_count"]),
                  int(rec["incoming_count"]), int(rec["outgoing_count"]), int(rec["unclassified_count"]),
                  rec["unclassified_amount"]]
        tot_in += rec["incoming"]
        tot_out += rec["outgoing"]
        tot_unc += rec["unclassified_amount"]
        tot_count += int(rec["transfer_count"])
        tot_in_c += int(rec["incoming_count"])
        tot_out_c += int(rec["outgoing_count"])
        tot_unc_c += int(rec["unclassified_count"])
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.border = _BORDER
            if col in (2, 3, 4, 9):
                cell.number_format = MONEY_FORMAT
        row += 1
    totals_row = ["TOTAL", tot_in, tot_out, tot_in - tot_out, tot_count, tot_in_c, tot_out_c, tot_unc_c, tot_unc]
    for col, value in enumerate(totals_row, start=1):
        cell = ws.cell(row=row, column=col, value=value)
        cell.font = _TOTAL_FONT
        cell.fill = _TOTAL_FILL
        cell.border = _BORDER
        if col in (2, 3, 4, 9):
            cell.number_format = MONEY_FORMAT
    _autosize(ws, {1: 14, 2: 16, 3: 16, 4: 16, 5: 14, 6: 14, 7: 14, 8: 16, 9: 22})
    ws.freeze_panes = ws.cell(row=start + 1, column=1)
    _add_metadata_sheet(wb, generated_at, office_name, {"Report": title, "Periods": len(summary)})
    return _workbook_bytes(wb)


def daily_summary_to_excel(frame: pd.DataFrame, *, office_name: str = "",
                           generated_at: datetime | None = None) -> bytes:
    return _summary_to_excel(daily_summary(frame), "Date", "Daily Financial Summary",
                             office_name=office_name, generated_at=generated_at)


def monthly_summary_to_excel(frame: pd.DataFrame, *, office_name: str = "",
                             generated_at: datetime | None = None) -> bytes:
    return _summary_to_excel(monthly_summary(frame), "Month", "Monthly Financial Summary",
                             office_name=office_name, generated_at=generated_at)


def _add_metadata_sheet(wb: Workbook, generated_at: datetime | None, office_name: str, extra: dict) -> None:
    ws = wb.create_sheet("Report Info")
    rows = [("Application", f"{APP_TITLE} v{APP_VERSION}"), ("Office", office_name),
            ("Generated at", _stamp(generated_at))] + list(extra.items())
    for r, (k, v) in enumerate(rows, start=1):
        ws.cell(row=r, column=1, value=k).font = _TOTAL_FONT
        ws.cell(row=r, column=2, value=v)
    _autosize(ws, {1: 18, 2: 50})


def _workbook_bytes(wb: Workbook) -> bytes:
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# PDF dashboard summary
# --------------------------------------------------------------------------
def dashboard_to_pdf(frame: pd.DataFrame, *, office_name: str = "", generated_at: datetime | None = None,
                     as_of: date | None = None, today_totals: Totals | None = None,
                     max_daily_rows: int = 40) -> bytes:
    generated_at = generated_at or datetime.now()
    as_of = as_of or generated_at.date()
    totals = compute_totals(frame)
    daily = daily_summary(frame)
    monthly = monthly_summary(frame)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=18, textColor=colors.HexColor("#1F3A5F"),
                                 alignment=TA_LEFT, spaceAfter=4)
    meta_style = ParagraphStyle("m", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#666666"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#1F3A5F"),
                        spaceBefore=10, spaceAfter=4)
    body = styles["Normal"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title="Financial Dashboard Summary")
    story = [
        Paragraph("Financial Dashboard Summary", title_style),
        Paragraph(f"{office_name or APP_TITLE} &nbsp;|&nbsp; Generated {generated_at.strftime('%Y-%m-%d %H:%M:%S')}"
                  f" &nbsp;|&nbsp; Figures as of {as_of.isoformat()}", meta_style),
        Spacer(1, 8),
        Paragraph("Overall position (USD)", h2),
    ]
    kpi_rows = [
        ["Metric", "Value"],
        ["Total Incoming", format_usd(totals.total_incoming)],
        ["Total Outgoing", format_usd(totals.total_outgoing)],
        ["Net Balance", format_usd(totals.net_balance)],
        ["Total Transactions", f"{totals.total_count:,}"],
        ["Unclassified Transactions", f"{totals.unclassified_count:,} ({format_usd(totals.unclassified_amount)} excluded from totals)"],
    ]
    if today_totals is not None:
        kpi_rows += [
            [f"Today's Incoming ({as_of.isoformat()})", format_usd(today_totals.total_incoming)],
            ["Today's Outgoing", format_usd(today_totals.total_outgoing)],
            ["Today's Net Balance", format_usd(today_totals.net_balance)],
        ]
    story.append(_pdf_table(kpi_rows, col_widths=[80 * mm, 95 * mm], align_right_cols=[1]))

    story.append(Paragraph("Monthly summary (USD)", h2))
    month_rows = [["Month", "Incoming", "Outgoing", "Net", "Transfers", "Unclassified"]]
    for rec in monthly.to_dict("records"):
        month_rows.append([rec["month"], format_usd(rec["incoming"]), format_usd(rec["outgoing"]),
                           format_usd(rec["net"]), str(int(rec["transfer_count"])), str(int(rec["unclassified_count"]))])
    if len(month_rows) == 1:
        month_rows.append(["(no data)", "", "", "", "", ""])
    story.append(_pdf_table(month_rows, col_widths=[28 * mm, 32 * mm, 32 * mm, 32 * mm, 24 * mm, 27 * mm],
                            align_right_cols=[1, 2, 3, 4, 5]))

    story.append(Paragraph("Daily summary (USD)", h2))
    daily_rows = [["Date", "Incoming", "Outgoing", "Net", "Transfers", "Unclassified"]]
    tail = daily.tail(max_daily_rows)
    for rec in tail.to_dict("records"):
        daily_rows.append([rec["date"], format_usd(rec["incoming"]), format_usd(rec["outgoing"]),
                           format_usd(rec["net"]), str(int(rec["transfer_count"])), str(int(rec["unclassified_count"]))])
    if len(daily_rows) == 1:
        daily_rows.append(["(no data)", "", "", "", "", ""])
    story.append(_pdf_table(daily_rows, col_widths=[28 * mm, 32 * mm, 32 * mm, 32 * mm, 24 * mm, 27 * mm],
                            align_right_cols=[1, 2, 3, 4, 5]))
    if len(daily) > max_daily_rows:
        story.append(Paragraph(f"Showing the most recent {max_daily_rows} of {len(daily)} days.", meta_style))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Net Balance = Total Incoming - Total Outgoing. Unclassified transfers are excluded from incoming and "
        "outgoing totals until a direction is assigned. This report is not a bank or mobile-wallet verified balance.",
        meta_style))
    doc.build(story)
    return buffer.getvalue()


def _pdf_table(rows: list[list[str]], col_widths: list[float], align_right_cols: list[int]) -> Table:
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D3E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FB")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for col in align_right_cols:
        style.append(("ALIGN", (col, 1), (col, -1), "RIGHT"))
    table.setStyle(TableStyle(style))
    return table


# --------------------------------------------------------------------------
# Saving
# --------------------------------------------------------------------------
def save_export(data: bytes, directory: Path, filename: str) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    target.write_bytes(data)
    return target


def timestamped_name(prefix: str, extension: str, when: datetime | None = None) -> str:
    when = when or datetime.now()
    return f"{prefix}_{when.strftime('%Y%m%d_%H%M%S')}.{extension.lstrip('.')}"
