"""Validation rules: dates, amounts, directions, identifiers and duplicates."""
from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from core.data_validator import (
    STATUS_DUPLICATE_IN_FILE,
    STATUS_EXISTS,
    STATUS_INVALID,
    STATUS_NEW,
    compute_fingerprint,
    parse_date,
    validate_frame,
    validate_record,
)
from core.excel_reader import read_transactions
from core.money import MoneyError, parse_amount, parse_rate
from tests.conftest import build_workbook, txn_row

TODAY = date(2026, 11, 4)


def base_record(**overrides):
    record = {
        "txn_no": 1, "txn_date": datetime(2026, 11, 2), "direction": None,
        "sender_name": "Demo Person 01", "sender_mobile": "+252000000001",
        "receiver_name": "Demo Person 02", "account_number": None,
        "currency": "USD", "amount_usd": 150, "exchange_rate": None, "amount_local": None, "notes": None,
    }
    record.update(overrides)
    return record


# ---------------------------------------------------------------- dates
@pytest.mark.parametrize("value,expected", [
    (datetime(2026, 11, 2, 0, 0), date(2026, 11, 2)),
    (date(2026, 11, 2), date(2026, 11, 2)),
    (pd.Timestamp("2026-11-02"), date(2026, 11, 2)),
    ("2026-11-02", date(2026, 11, 2)),
    ("02-Nov-2026", date(2026, 11, 2)),
    ("02/11/2026", date(2026, 11, 2)),          # day-first, as the workbook uses
    ("2 November 2026", date(2026, 11, 2)),
    (45658, date(2025, 1, 1)),                  # Excel serial number
    ("2026-11-02 00:00:00", date(2026, 11, 2)),
])
def test_parse_date_accepts_common_forms(value, expected):
    assert parse_date(value) == expected


@pytest.mark.parametrize("value", ["", None, "yesterday", "32/13/2026", True, 5])
def test_parse_date_rejects_invalid(value):
    with pytest.raises(ValueError):
        parse_date(value)


def test_missing_date_is_error():
    row = validate_record(base_record(txn_date=None), today=TODAY)
    assert not row.is_valid and any("Date" in e for e in row.errors)


def test_future_date_is_warning_not_error():
    row = validate_record(base_record(txn_date=date(2027, 1, 1)), today=TODAY)
    assert row.is_valid
    assert any("future" in w for w in row.warnings)


# ---------------------------------------------------------------- amounts
def test_amount_parsing_precision():
    assert parse_amount(126.25) == Decimal("126.25")
    assert parse_amount("1,250.50") == Decimal("1250.50")
    assert parse_amount("$ 15") == Decimal("15.00")
    assert parse_amount(126.25000000000001) == Decimal("126.25")  # float noise tolerated
    with pytest.raises(MoneyError):
        parse_amount("12.345")                                     # genuine third decimal
    with pytest.raises(MoneyError):
        parse_amount("abc")
    with pytest.raises(MoneyError):
        parse_amount(True)


def test_missing_amount_is_error_not_zero():
    row = validate_record(base_record(amount_usd=None), today=TODAY)
    assert not row.is_valid
    assert any("missing" in e.lower() for e in row.errors)


def test_zero_amount_is_error():
    row = validate_record(base_record(amount_usd=0), today=TODAY)
    assert not row.is_valid


def test_negative_amount_rejected_unless_permitted():
    rejected = validate_record(base_record(amount_usd=-20), today=TODAY)
    assert not rejected.is_valid
    allowed = validate_record(base_record(amount_usd=-20), allow_negative=True, today=TODAY)
    assert allowed.is_valid
    assert allowed.record["amount_cents"] == -2000


def test_amount_stored_as_exact_cents():
    row = validate_record(base_record(amount_usd=126.25), today=TODAY)
    assert row.record["amount_cents"] == 12625


# ---------------------------------------------------------------- rates
def test_exchange_rate_and_local_amount():
    row = validate_record(base_record(amount_usd=150, exchange_rate=28500), today=TODAY)
    assert row.record["exchange_rate"] == "28500"
    assert row.record["amount_local"] == "4275000.00"
    row2 = validate_record(base_record(amount_usd=126.25, exchange_rate="571.5"), today=TODAY)
    assert row2.record["amount_local"] == "72151.88"   # 72151.875 rounded half-up
    row3 = validate_record(base_record(amount_usd=16, exchange_rate=0.0035), today=TODAY)
    assert row3.record["amount_local"] == "0.06"       # 0.056 -> 0.06


def test_invalid_exchange_rate_is_error():
    assert not validate_record(base_record(exchange_rate=0), today=TODAY).is_valid
    assert not validate_record(base_record(exchange_rate=-5), today=TODAY).is_valid
    assert not validate_record(base_record(exchange_rate="x"), today=TODAY).is_valid
    with pytest.raises(MoneyError):
        parse_rate("1.23456789")


def test_local_amount_mismatch_in_file_is_warned_and_recomputed():
    row = validate_record(base_record(amount_usd=100, exchange_rate=2, amount_local=999), today=TODAY)
    assert row.is_valid
    assert row.record["amount_local"] == "200.00"
    assert any("differs" in w for w in row.warnings)


def test_local_amount_without_rate_is_kept_with_warning():
    row = validate_record(base_record(amount_local=500), today=TODAY)
    assert row.record["exchange_rate"] is None
    assert row.record["amount_local"] == "500.00"
    assert any("without an exchange rate" in w for w in row.warnings)


# ---------------------------------------------------------------- direction
@pytest.mark.parametrize("value,expected", [
    (None, None), ("", None), ("  ", None), ("Incoming", "Incoming"), ("incoming", "Incoming"),
    ("OUTGOING", "Outgoing"), (" outgoing ", "Outgoing"),
])
def test_direction_only_from_explicit_values(value, expected):
    row = validate_record(base_record(direction=value), today=TODAY)
    assert row.is_valid
    assert row.record["direction"] == expected


@pytest.mark.parametrize("value", ["In", "Out", "Credit", "Yes", 1])
def test_unknown_direction_is_error(value):
    row = validate_record(base_record(direction=value), today=TODAY)
    assert not row.is_valid


# ---------------------------------------------------------------- identifiers
def test_phone_and_account_preserved_as_strings():
    row = validate_record(base_record(sender_mobile="0612000001", account_number="000000006"), today=TODAY)
    assert row.record["sender_mobile"] == "0612000001"          # leading zeros kept as text
    assert row.record["account_number"] == "000000006"
    row2 = validate_record(base_record(sender_mobile=252000000003, account_number=30000123.0), today=TODAY)
    assert row2.record["sender_mobile"] == "252000000003"        # numeric cells become plain digit strings
    assert row2.record["account_number"] == "30000123"


def test_names_required():
    assert not validate_record(base_record(sender_name=None), today=TODAY).is_valid
    assert not validate_record(base_record(receiver_name="   "), today=TODAY).is_valid


def test_currency_rules():
    assert validate_record(base_record(currency="sos"), today=TODAY).record["currency"] == "SOS"
    blank = validate_record(base_record(currency=None), today=TODAY)
    assert blank.is_valid and blank.record["currency"] is None and any("Currency" in w for w in blank.warnings)
    assert not validate_record(base_record(currency="Dollars"), today=TODAY).is_valid


# ---------------------------------------------------------------- fingerprints & duplicates
def test_fingerprint_ignores_direction_and_number_and_formatting():
    a = validate_record(base_record(direction=None, txn_no=1), today=TODAY).record
    b = validate_record(base_record(direction="Incoming", txn_no=99, sender_name="  demo   person 01 "),
                        today=TODAY).record
    c = validate_record(base_record(amount_usd=150.01), today=TODAY).record
    assert compute_fingerprint(a) == compute_fingerprint(b) == a["fingerprint"]
    assert compute_fingerprint(c) != compute_fingerprint(a)


def test_validate_frame_flags_in_file_and_database_duplicates():
    rows = [
        txn_row(1, date(2026, 11, 2), None, "A", "0611", "B", "1", "USD", 50),
        txn_row(2, date(2026, 11, 2), None, "A", "0611", "B", "1", "USD", 50),     # duplicate of row 2
        txn_row(3, date(2026, 11, 2), None, "A", "0611", "B", "1", "USD", 51),     # distinct
        txn_row(4, date(2026, 11, 2), None, "", "0611", "B", "1", "USD", 51),      # invalid (no sender)
    ]
    result = read_transactions(io.BytesIO(build_workbook(rows)), filename="d.xlsx")
    first = validate_frame(result.frame, today=TODAY)
    assert [r.status for r in first.rows] == [STATUS_NEW, STATUS_DUPLICATE_IN_FILE, STATUS_NEW, STATUS_INVALID]
    assert first.rows[1].duplicate_of_row == 2
    assert first.new_count == 2 and first.duplicate_in_file_count == 1 and first.invalid_count == 1
    assert len(first.importable_rows()) == 3
    assert len(first.importable_rows(include_in_file_duplicates=False)) == 2

    existing = {first.rows[2].record["fingerprint"]}
    second = validate_frame(result.frame, existing_fingerprints=existing, today=TODAY)
    assert second.rows[2].status == STATUS_EXISTS
    assert len(second.importable_rows()) == 2
    assert len(second.importable_rows(include_existing=True)) == 3


def test_preview_frame_has_status_and_issue_columns():
    rows = [txn_row(1, date(2026, 11, 2), None, "A", "0611", "B", "1", "USD", None)]
    result = read_transactions(io.BytesIO(build_workbook(rows)), filename="d.xlsx")
    preview = validate_frame(result.frame, today=TODAY)
    table = preview.to_frame()
    assert table.loc[0, "Status"] == STATUS_INVALID
    assert "Amount (USD) is missing" in table.loc[0, "Issues"]
    assert table.loc[0, "Excel Row"] == 2


def test_sample_workbook_validation(sample_path):
    result = read_transactions(sample_path)
    preview = validate_frame(result.frame, today=TODAY)
    assert preview.total == 16
    assert preview.invalid_count == 0
    assert preview.unclassified_count == 16          # directions are never assumed
    assert preview.duplicate_in_file_count == 1      # workbook rows 14 and 17 are identical
    dup = [r for r in preview.rows if r.status == STATUS_DUPLICATE_IN_FILE][0]
    assert (dup.excel_row, dup.duplicate_of_row) == (17, 14)
    mobiles = [r.record["sender_mobile"] for r in preview.rows]
    assert "+252000000001" in mobiles and "252000000003" in mobiles
    accounts = [r.record["account_number"] for r in preview.rows]
    assert "000000003" in accounts                   # leading zero preserved
