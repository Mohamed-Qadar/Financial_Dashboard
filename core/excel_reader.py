"""Excel import: locate the Transactions sheet, detect the header row, map the
columns to canonical keys and return the raw cell values untouched.

Nothing here interprets or cleans values - that is the validator's job - so
the original spreadsheet data is preserved exactly as read.
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

import pandas as pd

from config import (
    COLUMN_KEYS,
    COLUMN_SPECS,
    REQUIRED_COLUMN_KEYS,
    SUPPORTED_EXCEL_EXTENSIONS,
    TRANSACTIONS_SHEET_NAME,
)
from core.money import is_blank

_HEADER_SCAN_ROWS = 15
_NORMALISE = re.compile(r"[^a-z0-9]+")

_ALIAS_TO_KEY: dict[str, str] = {}
for _spec in COLUMN_SPECS:
    for _alias in _spec["aliases"]:
        _ALIAS_TO_KEY.setdefault(_alias, _spec["key"])
    _ALIAS_TO_KEY.setdefault(_NORMALISE.sub("", _spec["header"].lower()), _spec["key"])


class ExcelImportError(Exception):
    """Raised when a workbook cannot be read as a transactions sheet."""


@dataclass
class ColumnMapping:
    """Which spreadsheet header feeds each canonical column."""

    found: dict[str, str] = field(default_factory=dict)        # key -> original header
    missing_required: list[str] = field(default_factory=list)  # canonical keys
    missing_optional: list[str] = field(default_factory=list)  # canonical keys
    unmapped_headers: list[str] = field(default_factory=list)  # headers we ignored

    @property
    def is_usable(self) -> bool:
        return not self.missing_required


@dataclass
class SkippedRow:
    excel_row: int
    reason: str


@dataclass
class ExcelReadResult:
    frame: pd.DataFrame            # canonical columns + "excel_row"; raw values
    sheet_name: str
    sheet_names: list[str]
    header_row: int                # 1-based Excel row number of the header
    mapping: ColumnMapping
    skipped_rows: list[SkippedRow]
    filename: str
    file_hash: str

    @property
    def row_count(self) -> int:
        return int(len(self.frame))


def normalise_header(value: Any) -> str:
    return _NORMALISE.sub("", str(value).strip().lower()) if not is_blank(value) else ""


def header_to_key(value: Any) -> str | None:
    return _ALIAS_TO_KEY.get(normalise_header(value))


def _engine_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXCEL_EXTENSIONS:
        raise ExcelImportError(
            f"Unsupported file type '{suffix or '(none)'}'. "
            f"Supported: {', '.join(SUPPORTED_EXCEL_EXTENSIONS)}"
        )
    return "xlrd" if suffix == ".xls" else "openpyxl"


def _read_bytes(source: str | Path | bytes | BinaryIO) -> tuple[bytes, str]:
    """Return (content, filename) for a path, bytes or file-like object."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        return path.read_bytes(), path.name
    if isinstance(source, (bytes, bytearray)):
        return bytes(source), "upload.xlsx"
    name = getattr(source, "name", "upload.xlsx")
    if hasattr(source, "seek"):
        source.seek(0)
    data = source.read()
    return data, Path(str(name)).name


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def list_sheets(source: str | Path | bytes | BinaryIO, filename: str | None = None) -> list[str]:
    data, detected_name = _read_bytes(source)
    engine = _engine_for(filename or detected_name)
    try:
        with pd.ExcelFile(io.BytesIO(data), engine=engine) as book:
            return [str(s) for s in book.sheet_names]
    except Exception as exc:  # pragma: no cover - depends on corrupt input
        raise ExcelImportError(f"Could not open workbook: {exc}") from exc


def choose_sheet(sheet_names: list[str], requested: str | None = None) -> str:
    """Pick the Transactions sheet (case-insensitive), else a single sheet."""
    if requested:
        for name in sheet_names:
            if name == requested:
                return name
        raise ExcelImportError(f"Sheet '{requested}' not found. Available: {', '.join(sheet_names)}")
    for name in sheet_names:
        if name.strip().lower() == TRANSACTIONS_SHEET_NAME.lower():
            return name
    for name in sheet_names:
        if TRANSACTIONS_SHEET_NAME.lower() in name.strip().lower():
            return name
    if len(sheet_names) == 1:
        return sheet_names[0]
    raise ExcelImportError(
        f"No '{TRANSACTIONS_SHEET_NAME}' worksheet found. Available sheets: {', '.join(sheet_names)}. "
        "Please choose the sheet to import."
    )


def detect_header_row(raw: pd.DataFrame) -> int:
    """Index (0-based, within ``raw``) of the row that looks most like the header."""
    best_index, best_score = -1, 0
    for idx in range(min(_HEADER_SCAN_ROWS, len(raw))):
        keys = {header_to_key(v) for v in raw.iloc[idx].tolist()}
        keys.discard(None)
        score = len(keys)
        if score > best_score:
            best_index, best_score = idx, score
    if best_score < 2:
        raise ExcelImportError(
            "Could not find a header row. Expected headers such as 'Date', 'Sender Name', "
            "'Receiver Name' and 'Amount (USD)' within the first 15 rows."
        )
    return best_index


def build_mapping(headers: list[Any]) -> ColumnMapping:
    mapping = ColumnMapping()
    for header in headers:
        if is_blank(header):
            continue
        key = header_to_key(header)
        if key is None or key in mapping.found:
            mapping.unmapped_headers.append(str(header))
        else:
            mapping.found[key] = str(header)
    for key in COLUMN_KEYS:
        if key not in mapping.found:
            (mapping.missing_required if key in REQUIRED_COLUMN_KEYS else mapping.missing_optional).append(key)
    return mapping


def _looks_like_totals_row(record: dict[str, Any]) -> bool:
    """A row with an amount but no date and no parties is a SUM/footer row."""
    has_amount = not is_blank(record.get("amount_usd"))
    identity_blank = all(is_blank(record.get(k)) for k in ("txn_date", "sender_name", "receiver_name"))
    return has_amount and identity_blank


def read_transactions(
    source: str | Path | bytes | BinaryIO,
    *,
    sheet_name: str | None = None,
    filename: str | None = None,
) -> ExcelReadResult:
    """Read the transactions sheet of a workbook into a canonical raw frame."""
    data, detected_name = _read_bytes(source)
    filename = filename or detected_name
    engine = _engine_for(filename)
    try:
        with pd.ExcelFile(io.BytesIO(data), engine=engine) as book:
            sheet_names = [str(s) for s in book.sheet_names]
            chosen = choose_sheet(sheet_names, sheet_name)
            raw = book.parse(chosen, header=None, dtype=object)
    except ExcelImportError:
        raise
    except Exception as exc:
        raise ExcelImportError(f"Could not read workbook: {exc}") from exc

    if raw.empty:
        raise ExcelImportError(f"Sheet '{chosen}' is empty.")

    header_idx = detect_header_row(raw)
    headers = raw.iloc[header_idx].tolist()
    mapping = build_mapping(headers)

    body = raw.iloc[header_idx + 1:].copy()
    body.columns = list(range(raw.shape[1]))
    position_to_key = {pos: header_to_key(h) for pos, h in enumerate(headers)}
    seen: set[str] = set()
    rename: dict[int, str] = {}
    for pos, key in position_to_key.items():
        if key and key not in seen:
            rename[pos] = key
            seen.add(key)
    body = body[list(rename)].rename(columns=rename)
    for key in COLUMN_KEYS:
        if key not in body.columns:
            body[key] = None
    body = body[COLUMN_KEYS]
    body.insert(0, "excel_row", [header_idx + 2 + i for i in range(len(body))])

    # Drop completely empty rows silently; report footer/total rows explicitly.
    skipped: list[SkippedRow] = []
    keep: list[bool] = []
    for record in body.to_dict("records"):
        values = {k: v for k, v in record.items() if k != "excel_row"}
        if all(is_blank(v) for v in values.values()):
            keep.append(False)
            continue
        if _looks_like_totals_row(values):
            skipped.append(SkippedRow(int(record["excel_row"]),
                                      "Looks like a totals/footer row (amount only, no date or names); not imported."))
            keep.append(False)
            continue
        keep.append(True)
    body = body[keep].reset_index(drop=True)

    return ExcelReadResult(
        frame=body,
        sheet_name=chosen,
        sheet_names=sheet_names,
        header_row=header_idx + 1,
        mapping=mapping,
        skipped_rows=skipped,
        filename=filename,
        file_hash=file_sha256(data),
    )
