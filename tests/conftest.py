"""Shared fixtures and synthetic data builders for the test-suite."""
from __future__ import annotations

import io
import sys
from datetime import date, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import COLUMN_HEADERS, COLUMN_KEYS  # noqa: E402
from core.database import Database  # noqa: E402
from core.transaction_manager import TransactionManager  # noqa: E402

SAMPLE_WORKBOOK = ROOT / "sample_data" / "Daily_Money_Transfer_Manager 2026.xlsx"
STANDARD_HEADERS = [COLUMN_HEADERS[k] for k in COLUMN_KEYS]


def build_workbook(
    rows: list[list],
    *,
    headers: list[str] | None = None,
    title_rows: int = 0,
    footer_sum: bool = False,
    sheet_name: str = "Transactions",
    extra_sheets: tuple[str, ...] = ("Dashboard", "Daily Summary", "Instructions"),
    blank_row_after: int | None = None,
) -> bytes:
    """Create an in-memory .xlsx workbook that mimics the supplied template."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    for name in extra_sheets:
        wb.create_sheet(name)
    row_index = 1
    for _ in range(title_rows):
        ws.cell(row=row_index, column=1, value="DAILY MONEY TRANSFER MANAGER")
        row_index += 1
    for col, header in enumerate(headers or STANDARD_HEADERS, start=1):
        ws.cell(row=row_index, column=col, value=header)
    row_index += 1
    for i, values in enumerate(rows):
        if blank_row_after is not None and i == blank_row_after:
            row_index += 1
        for col, value in enumerate(values, start=1):
            if value is not None:
                ws.cell(row=row_index, column=col, value=value)
        row_index += 1
    if footer_sum:
        ws.cell(row=row_index, column=9, value=sum(float(r[8]) for r in rows if r[8] is not None))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def txn_row(no, day: date, direction, sender, mobile, receiver, account, currency, amount, rate=None,
            local=None, notes=None) -> list:
    return [no, datetime(day.year, day.month, day.day), direction, sender, mobile, receiver, account,
            currency, amount, rate, local, notes]


# Synthetic data set with hand-computed expected results (see test_calculations).
SYNTHETIC_ROWS = [
    txn_row(1, date(2026, 1, 5), "Incoming", "Ali Hassan", "+252611111111", "Omar Farah", "0611000001", "USD", 100.10),
    txn_row(2, date(2026, 1, 5), "Outgoing", "Omar Farah", "0611000001", "Ali Hassan", "36000001", "USD", 40.05),
    txn_row(3, date(2026, 1, 5), None, "Hodan Ahmed", "+252622222222", "Ali Hassan", "36000001", "USD", 10.00),
    txn_row(4, date(2026, 1, 6), "Incoming", "Faduma Nur", "+252633333333", "Ali Hassan", "36000001", "USD", 250.00),
    txn_row(5, date(2026, 1, 6), "Outgoing", "Ali Hassan", "+252611111111", "Said Abdi", "0611000002", "USD", 300.25),
    txn_row(6, date(2026, 2, 1), "Incoming", "Ali Hassan", "+252611111111", "Said Abdi", "0611000002", "USD", 0.10),
    txn_row(7, date(2026, 2, 1), "Incoming", "Said Abdi", "0611000002", "Ali Hassan", "36000001", "USD", 0.20, 28500),
]


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(tmp_path / "test.db")


@pytest.fixture
def manager(db) -> TransactionManager:
    return TransactionManager(db)


@pytest.fixture
def synthetic_xlsx() -> bytes:
    return build_workbook(SYNTHETIC_ROWS, footer_sum=True)


@pytest.fixture
def loaded_manager(manager, synthetic_xlsx) -> TransactionManager:
    result = manager.read_excel(io.BytesIO(synthetic_xlsx), filename="synthetic.xlsx")
    preview = manager.preview_import(result, today=date(2026, 3, 1))
    manager.commit_import(result, preview)
    return manager


@pytest.fixture
def sample_path() -> Path:
    if not SAMPLE_WORKBOOK.exists():
        pytest.skip("sample workbook not available")
    return SAMPLE_WORKBOOK
