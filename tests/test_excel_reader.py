"""Excel reading: sheet selection, header detection, column mapping, footer rows."""
from __future__ import annotations

import io
from datetime import date

import pytest

from core.excel_reader import ExcelImportError, list_sheets, read_transactions
from tests.conftest import STANDARD_HEADERS, SYNTHETIC_ROWS, build_workbook, txn_row


def test_reads_standard_workbook_and_skips_footer(synthetic_xlsx):
    result = read_transactions(io.BytesIO(synthetic_xlsx), filename="synthetic.xlsx")
    assert result.sheet_name == "Transactions"
    assert result.header_row == 1
    assert result.row_count == len(SYNTHETIC_ROWS)
    assert result.mapping.is_usable
    assert not result.mapping.missing_optional
    assert set(result.frame.columns) == {"excel_row", *[k for k in result.mapping.found]}
    # The SUM footer row (amount only) is reported, not imported.
    assert len(result.skipped_rows) == 1
    assert result.skipped_rows[0].excel_row == len(SYNTHETIC_ROWS) + 2
    assert "totals" in result.skipped_rows[0].reason.lower()
    # Excel row numbers are preserved for traceability.
    assert result.frame["excel_row"].tolist() == list(range(2, len(SYNTHETIC_ROWS) + 2))


def test_lists_all_sheets(synthetic_xlsx):
    assert list_sheets(io.BytesIO(synthetic_xlsx), filename="x.xlsx") == [
        "Transactions", "Dashboard", "Daily Summary", "Instructions"
    ]


def test_header_row_detected_below_title_rows():
    data = build_workbook(SYNTHETIC_ROWS[:2], title_rows=3)
    result = read_transactions(io.BytesIO(data), filename="t.xlsx")
    assert result.header_row == 4
    assert result.row_count == 2
    assert result.frame["excel_row"].tolist() == [5, 6]


def test_header_aliases_are_accepted():
    headers = ["No", "Transaction Date", "Direction", "Sender", "Mobile", "Receiver", "Account No",
               "Currency", "Amount", "Rate", "Local Amount", "Notes"]
    data = build_workbook(SYNTHETIC_ROWS[:1], headers=headers)
    result = read_transactions(io.BytesIO(data), filename="a.xlsx")
    assert result.mapping.is_usable
    assert result.mapping.found["amount_usd"] == "Amount"
    assert result.mapping.found["txn_date"] == "Transaction Date"
    assert result.mapping.found["account_number"] == "Account No"


def test_missing_required_column_is_reported():
    headers = [h for h in STANDARD_HEADERS if h != "Amount (USD)"]
    rows = [r[:8] + r[9:] for r in SYNTHETIC_ROWS[:2]]
    data = build_workbook(rows, headers=headers)
    result = read_transactions(io.BytesIO(data), filename="m.xlsx")
    assert result.mapping.missing_required == ["amount_usd"]
    assert not result.mapping.is_usable


def test_unknown_columns_are_listed_not_fatal():
    headers = STANDARD_HEADERS + ["Agent"]
    rows = [r + ["Agent A"] for r in SYNTHETIC_ROWS[:1]]
    result = read_transactions(io.BytesIO(build_workbook(rows, headers=headers)), filename="u.xlsx")
    assert result.mapping.unmapped_headers == ["Agent"]
    assert result.mapping.is_usable


def test_blank_rows_are_dropped_silently():
    data = build_workbook(SYNTHETIC_ROWS[:3], blank_row_after=1)
    result = read_transactions(io.BytesIO(data), filename="b.xlsx")
    assert result.row_count == 3
    assert result.skipped_rows == []
    assert result.frame["excel_row"].tolist() == [2, 4, 5]


def test_single_sheet_workbook_is_used_when_not_named_transactions():
    data = build_workbook(SYNTHETIC_ROWS[:1], sheet_name="Sheet1", extra_sheets=())
    result = read_transactions(io.BytesIO(data), filename="s.xlsx")
    assert result.sheet_name == "Sheet1"


def test_multiple_sheets_without_transactions_requires_choice():
    data = build_workbook(SYNTHETIC_ROWS[:1], sheet_name="Data", extra_sheets=("Other",))
    with pytest.raises(ExcelImportError):
        read_transactions(io.BytesIO(data), filename="s.xlsx")
    result = read_transactions(io.BytesIO(data), filename="s.xlsx", sheet_name="Data")
    assert result.row_count == 1


def test_unsupported_extension_rejected():
    with pytest.raises(ExcelImportError):
        read_transactions(io.BytesIO(b"a,b,c"), filename="data.csv")


def test_phone_numbers_preserved_as_text_values():
    rows = [txn_row(1, date(2026, 1, 1), None, "A", "0612345678", "B", "0034", "USD", 10)]
    result = read_transactions(io.BytesIO(build_workbook(rows)), filename="p.xlsx")
    assert result.frame.loc[0, "sender_mobile"] == "0612345678"
    assert result.frame.loc[0, "account_number"] == "0034"


def test_sample_workbook_structure(sample_path):
    result = read_transactions(sample_path)
    assert result.sheet_names == ["Dashboard", "Transactions", "Daily Summary", "Instructions"]
    assert result.sheet_name == "Transactions"
    assert result.row_count == 16
    assert list(result.mapping.found.values()) == STANDARD_HEADERS
    assert [s.excel_row for s in result.skipped_rows] == [18]
    assert result.frame["direction"].isna().all()
