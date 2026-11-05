"""Record validation, normalisation and duplicate detection.

The same :func:`validate_record` is used for spreadsheet rows and for the
manual add/edit forms, so every transaction in the database has passed exactly
the same rules.

Design points
-------------
* Errors make a row un-importable; warnings are shown but do not block.
* Missing amounts are errors, never silently treated as zero.
* Direction is only ever set from an explicit "Incoming"/"Outgoing" value;
  blank stays blank (unclassified) so the user can classify it later.
* Phone and account numbers are kept as text so leading zeros survive.
* The fingerprint used for duplicate detection excludes Direction and "No."
  so that a file re-imported after classification is still recognised.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from config import (
    COLUMN_HEADERS,
    COLUMN_KEYS,
    DIRECTIONS,
    EXCEL_SERIAL_MAX,
    EXCEL_SERIAL_MIN,
    FUTURE_DATE_WARNING_DAYS,
)
from core.money import (
    MoneyError,
    decimal_str,
    decimal_to_cents,
    is_blank,
    local_amount,
    parse_amount,
    parse_rate,
    quantize_money,
    to_decimal,
)

STATUS_NEW = "New"
STATUS_INVALID = "Invalid"
STATUS_DUPLICATE_IN_FILE = "Possible duplicate (in file)"
STATUS_EXISTS = "Already in database"

_DATE_FORMATS = (
    "%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%Y%m%d",
    "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",
)
_DIRECTION_LOOKUP = {d.lower(): d for d in DIRECTIONS}
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9 \-()]{3,}$")
_WS = re.compile(r"\s+")


class ValidationError(ValueError):
    """Raised by the transaction manager when a record fails validation."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class ValidatedRow:
    excel_row: int | None
    raw: dict[str, Any]
    record: dict[str, Any] | None = None   # DB-ready record (None when invalid)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = STATUS_NEW
    duplicate_of_row: int | None = None

    @property
    def is_valid(self) -> bool:
        return not self.errors and self.record is not None

    def issues_text(self) -> str:
        parts = [f"Error: {e}" for e in self.errors] + [f"Warning: {w}" for w in self.warnings]
        return " | ".join(parts)


# --------------------------------------------------------------------------
# Field parsers
# --------------------------------------------------------------------------
def parse_date(value: Any) -> date:
    """Interpret a spreadsheet/user date value. Raises ValueError."""
    if is_blank(value):
        raise ValueError("date is missing")
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, bool):
        raise ValueError("date is not valid")
    if isinstance(value, (int, float)):
        if not (EXCEL_SERIAL_MIN <= float(value) <= EXCEL_SERIAL_MAX):
            raise ValueError(f"'{value}' is not a recognisable date")
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    try:
        parsed = pd.to_datetime(text, dayfirst=True, errors="raise")
        if pd.isna(parsed):
            raise ValueError
        return parsed.to_pydatetime().date()
    except Exception as exc:
        raise ValueError(f"'{text}' is not a recognisable date") from exc


def clean_text(value: Any) -> str | None:
    """Strip outer whitespace; numbers become text without a trailing '.0'."""
    if is_blank(value):
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, Decimal):
        return str(value.to_integral()) if value == value.to_integral() else format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


def clean_identifier(value: Any) -> str | None:
    """Mobile/account numbers: always text, internal spaces preserved."""
    return clean_text(value)


def parse_direction(value: Any) -> str | None:
    if is_blank(value):
        return None
    key = str(value).strip().lower()
    if key in _DIRECTION_LOOKUP:
        return _DIRECTION_LOOKUP[key]
    raise ValueError(f"direction '{value}' must be Incoming or Outgoing (or left blank)")


def parse_currency(value: Any) -> str | None:
    if is_blank(value):
        return None
    code = str(value).strip().upper()
    if not _CURRENCY_RE.match(code):
        raise ValueError(f"currency '{value}' is not a 3-letter code such as USD or SOS")
    return code


def parse_txn_no(value: Any) -> int | None:
    if is_blank(value):
        return None
    try:
        number = to_decimal(value)
    except MoneyError as exc:
        raise ValueError(f"No. '{value}' is not a whole number") from exc
    if number is None or number != number.to_integral():
        raise ValueError(f"No. '{value}' is not a whole number")
    return int(number)


def normalise_for_fingerprint(value: str | None) -> str:
    return _WS.sub(" ", (value or "").strip().lower())


def digits_only(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def compute_fingerprint(record: dict[str, Any]) -> str:
    """Stable identity hash of the business fields (excludes Direction and No.)."""
    parts = [
        str(record.get("txn_date") or ""),
        normalise_for_fingerprint(record.get("sender_name")),
        digits_only(record.get("sender_mobile")),
        normalise_for_fingerprint(record.get("receiver_name")),
        digits_only(record.get("account_number")),
        (record.get("currency") or "").upper(),
        str(int(record.get("amount_cents") or 0)),
        normalise_for_fingerprint(record.get("notes")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Record validation
# --------------------------------------------------------------------------
def validate_record(
    raw: dict[str, Any],
    *,
    allow_negative: bool = False,
    today: date | None = None,
    excel_row: int | None = None,
) -> ValidatedRow:
    """Validate one raw record (spreadsheet row or form input).

    ``raw`` uses canonical keys from :data:`config.COLUMN_KEYS`. Returns a
    :class:`ValidatedRow` whose ``record`` is ready for the database when valid.
    """
    today = today or date.today()
    row = ValidatedRow(excel_row=excel_row, raw={k: raw.get(k) for k in COLUMN_KEYS})
    errors, warnings = row.errors, row.warnings
    rec: dict[str, Any] = {}

    # --- Date ------------------------------------------------------------
    try:
        txn_date = parse_date(raw.get("txn_date"))
        rec["txn_date"] = txn_date.isoformat()
        if txn_date > today + timedelta(days=FUTURE_DATE_WARNING_DAYS):
            warnings.append(f"Date {txn_date.isoformat()} is in the future")
        if txn_date.year < 2000:
            warnings.append(f"Date {txn_date.isoformat()} is unusually old")
    except ValueError as exc:
        errors.append(f"Date: {exc}")

    # --- Direction -------------------------------------------------------
    try:
        rec["direction"] = parse_direction(raw.get("direction"))
    except ValueError as exc:
        errors.append(str(exc))

    # --- Names -----------------------------------------------------------
    sender = clean_text(raw.get("sender_name"))
    receiver = clean_text(raw.get("receiver_name"))
    if not sender:
        errors.append("Sender Name is missing")
    if not receiver:
        errors.append("Receiver Name is missing")
    rec["sender_name"], rec["receiver_name"] = sender, receiver

    # --- Identifiers -----------------------------------------------------
    mobile = clean_identifier(raw.get("sender_mobile"))
    if mobile and not _PHONE_RE.match(mobile):
        warnings.append(f"Sender Mobile '{mobile}' has an unusual format")
    rec["sender_mobile"] = mobile
    account = clean_identifier(raw.get("account_number"))
    rec["account_number"] = account
    if not mobile and not account:
        warnings.append("No sender mobile or account number given")

    # --- Currency --------------------------------------------------------
    try:
        currency = parse_currency(raw.get("currency"))
        if currency is None:
            warnings.append("Currency is blank")
        rec["currency"] = currency
    except ValueError as exc:
        errors.append(str(exc))

    # --- Amount ----------------------------------------------------------
    amount: Decimal | None = None
    try:
        amount = parse_amount(raw.get("amount_usd"))
        if amount is None:
            errors.append("Amount (USD) is missing")
        elif amount == 0:
            errors.append("Amount (USD) is zero")
        elif amount < 0 and not allow_negative:
            errors.append(f"Amount (USD) {amount} is negative (negative amounts are not permitted)")
        else:
            rec["amount_cents"] = decimal_to_cents(amount)
    except MoneyError as exc:
        errors.append(f"Amount (USD): {exc}")

    # --- Exchange rate & local amount ------------------------------------
    rate: Decimal | None = None
    try:
        rate = parse_rate(raw.get("exchange_rate"))
    except MoneyError as exc:
        errors.append(f"Exchange Rate: {exc}")
    rec["exchange_rate"] = decimal_str(rate)

    file_local: Decimal | None = None
    try:
        file_local = to_decimal(raw.get("amount_local"))
    except MoneyError:
        warnings.append(f"Amount in Local Currency '{raw.get('amount_local')}' is not a number; ignored")
    if rate is not None and amount is not None:
        computed = local_amount(amount, rate)
        rec["amount_local"] = decimal_str(computed)
        if file_local is not None and abs(quantize_money(file_local) - computed) > Decimal("0.01"):
            warnings.append(
                f"Local amount in file ({file_local}) differs from Amount x Rate ({computed}); computed value used"
            )
    elif file_local is not None:
        rec["amount_local"] = decimal_str(quantize_money(file_local))
        warnings.append("Local amount given without an exchange rate; stored as supplied")
    else:
        rec["amount_local"] = None

    # --- Notes & number --------------------------------------------------
    rec["notes"] = clean_text(raw.get("notes"))
    try:
        rec["txn_no"] = parse_txn_no(raw.get("txn_no"))
    except ValueError as exc:
        warnings.append(str(exc))
        rec["txn_no"] = None

    if errors:
        row.status = STATUS_INVALID
        return row

    rec["fingerprint"] = compute_fingerprint(rec)
    rec["source_row"] = excel_row
    row.record = rec
    return row


# --------------------------------------------------------------------------
# Batch validation (import preview)
# --------------------------------------------------------------------------
@dataclass
class ImportPreview:
    rows: list[ValidatedRow]
    column_warnings: list[str] = field(default_factory=list)

    # -- counts -------------------------------------------------------------
    def _count(self, status: str) -> int:
        return sum(1 for r in self.rows if r.status == status)

    @property
    def new_count(self) -> int:
        return self._count(STATUS_NEW)

    @property
    def invalid_count(self) -> int:
        return self._count(STATUS_INVALID)

    @property
    def duplicate_in_file_count(self) -> int:
        return self._count(STATUS_DUPLICATE_IN_FILE)

    @property
    def exists_count(self) -> int:
        return self._count(STATUS_EXISTS)

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def unclassified_count(self) -> int:
        return sum(1 for r in self.rows if r.record is not None and r.record.get("direction") is None)

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.rows if r.warnings)

    # -- selection ----------------------------------------------------------
    def importable_rows(self, *, include_in_file_duplicates: bool = True,
                        include_existing: bool = False) -> list[ValidatedRow]:
        selected: list[ValidatedRow] = []
        for row in self.rows:
            if not row.is_valid:
                continue
            if row.status == STATUS_DUPLICATE_IN_FILE and not include_in_file_duplicates:
                continue
            if row.status == STATUS_EXISTS and not include_existing:
                continue
            selected.append(row)
        return selected

    def importable_amount_cents(self, **kwargs: Any) -> int:
        return sum(int(r.record["amount_cents"]) for r in self.importable_rows(**kwargs))

    # -- presentation -------------------------------------------------------
    def to_frame(self) -> pd.DataFrame:
        """Preview table: original values plus Status and Issues columns."""
        numeric_keys = {"txn_no", "amount_usd", "exchange_rate", "amount_local"}
        records = []
        for row in self.rows:
            item = {"Excel Row": row.excel_row, "Status": row.status}
            for key in COLUMN_KEYS:
                value = row.raw.get(key)
                if isinstance(value, (datetime, pd.Timestamp)):
                    value = value.date().isoformat()
                elif is_blank(value):
                    value = float("nan") if key in numeric_keys else ""
                elif key not in numeric_keys:
                    value = str(value)
                item[COLUMN_HEADERS[key]] = value
            if row.duplicate_of_row:
                item["Status"] = f"{row.status} of row {row.duplicate_of_row}"
            item["Issues"] = row.issues_text()
            records.append(item)
        columns = ["Excel Row", "Status"] + [COLUMN_HEADERS[k] for k in COLUMN_KEYS] + ["Issues"]
        return pd.DataFrame(records, columns=columns)


def validate_frame(
    frame: pd.DataFrame,
    *,
    existing_fingerprints: set[str] | None = None,
    allow_negative: bool = False,
    today: date | None = None,
) -> ImportPreview:
    """Validate every row of a raw canonical frame and flag duplicates."""
    existing = existing_fingerprints or set()
    rows: list[ValidatedRow] = []
    first_seen: dict[str, int] = {}
    for record in frame.to_dict("records"):
        excel_row = record.get("excel_row")
        excel_row = int(excel_row) if excel_row is not None and not is_blank(excel_row) else None
        row = validate_record(record, allow_negative=allow_negative, today=today, excel_row=excel_row)
        if row.is_valid:
            fp = row.record["fingerprint"]
            if fp in existing:
                row.status = STATUS_EXISTS
                row.warnings.append("An identical transaction already exists in the database")
            elif fp in first_seen:
                row.status = STATUS_DUPLICATE_IN_FILE
                row.duplicate_of_row = first_seen[fp]
                row.warnings.append(f"Identical to row {first_seen[fp]} of this file")
            else:
                first_seen[fp] = excel_row if excel_row is not None else len(rows) + 1
        rows.append(row)
    return ImportPreview(rows=rows)
