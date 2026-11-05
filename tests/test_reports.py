"""Excel and PDF exports contain accurate totals and generation dates."""
from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal

import openpyxl

from core import calculations as calc
from core.report_generator import (
    daily_summary_to_excel,
    dashboard_to_pdf,
    monthly_summary_to_excel,
    save_export,
    timestamped_name,
    transactions_to_excel,
)

STAMP = datetime(2026, 3, 1, 9, 30, 0)
D = Decimal


def _sheet(data: bytes, name: str | None = None):
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    return wb[name] if name else wb.active


def _find_row(ws, label: str, col: int = 1):
    for row in ws.iter_rows(values_only=True):
        if row[col - 1] == label:
            return row
    raise AssertionError(f"{label!r} not found")


def test_transactions_export(loaded_manager):
    frame = loaded_manager.load_frame()
    data = transactions_to_excel(frame, office_name="Test Office", generated_at=STAMP)
    ws = _sheet(data, "Transactions")
    assert ws["A1"].value == "All Transactions"
    assert "Generated: 2026-03-01 09:30:00" in ws["A3"].value
    header = [c.value for c in ws[6]]
    assert header[:5] == ["ID", "No.", "Date", "Direction", "Sender Name"]
    body = list(ws.iter_rows(min_row=7, max_row=13, values_only=True))
    assert len(body) == 7
    amounts = [D(str(r[9])) for r in body]
    assert sum(amounts, D(0)) == D("700.70")
    assert "Unclassified" in {r[3] for r in body}
    # Phone numbers remain text with the leading '+' / '0'.
    assert {r[5] for r in body} >= {"+252611111111", "0611000001"}
    assert ws.cell(row=7, column=6).number_format == "@"
    # Totals block agrees with the calculation engine.
    assert D(str(_find_row(ws, "Total Incoming (USD)", 9)[9])) == D("350.40")
    assert D(str(_find_row(ws, "Total Outgoing (USD)", 9)[9])) == D("340.30")
    assert D(str(_find_row(ws, "Net Balance (USD)", 9)[9])) == D("10.10")
    assert D(str(_find_row(ws, "Sum of all amounts (USD)", 9)[9])) == D("700.70")
    info = _sheet(data, "Report Info")
    assert _find_row(info, "Generated at")[1] == "2026-03-01 09:30:00"


def test_daily_summary_export(loaded_manager):
    frame = loaded_manager.load_frame()
    ws = _sheet(daily_summary_to_excel(frame, office_name="Office", generated_at=STAMP))
    rows = {r[0]: r for r in ws.iter_rows(min_row=7, values_only=True) if r[0]}
    assert [D(str(v)) for v in rows["2026-01-05"][1:4]] == [D("100.10"), D("40.05"), D("60.05")]
    assert rows["2026-01-05"][4] == 3
    assert [D(str(v)) for v in rows["2026-01-06"][1:4]] == [D("250.00"), D("300.25"), D("-50.25")]
    total = rows["TOTAL"]
    assert [D(str(v)) for v in total[1:4]] == [D("350.40"), D("340.30"), D("10.10")]
    assert total[4] == 7 and total[7] == 1
    assert "Generated: 2026-03-01 09:30:00" in ws["A3"].value


def test_monthly_summary_export(loaded_manager):
    frame = loaded_manager.load_frame()
    ws = _sheet(monthly_summary_to_excel(frame, office_name="Office", generated_at=STAMP))
    rows = {r[0]: r for r in ws.iter_rows(min_row=7, values_only=True) if r[0]}
    assert [D(str(v)) for v in rows["2026-01"][1:4]] == [D("350.10"), D("340.30"), D("9.80")]
    assert rows["2026-01"][4] == 5
    assert [D(str(v)) for v in rows["2026-02"][1:4]] == [D("0.30"), D("0.00"), D("0.30")]
    assert [D(str(v)) for v in rows["TOTAL"][1:4]] == [D("350.40"), D("340.30"), D("10.10")]


def test_dashboard_pdf(loaded_manager):
    frame = loaded_manager.load_frame()
    today = date(2026, 1, 6)
    pdf = dashboard_to_pdf(frame, office_name="Office", generated_at=STAMP, as_of=today,
                           today_totals=calc.compute_totals_for_day(frame, today))
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1500
    assert b"/Title (Financial Dashboard Summary)" in pdf or b"Financial Dashboard Summary" in pdf


def test_exports_with_empty_database(db):
    frame = db.fetch_transactions()
    assert transactions_to_excel(frame, generated_at=STAMP)
    assert daily_summary_to_excel(frame, generated_at=STAMP)
    assert dashboard_to_pdf(frame, generated_at=STAMP).startswith(b"%PDF-")


def test_save_export_and_naming(tmp_path):
    name = timestamped_name("daily_summary", "xlsx", STAMP)
    assert name == "daily_summary_20260301_093000.xlsx"
    path = save_export(b"abc", tmp_path / "excel", name)
    assert path.read_bytes() == b"abc"
