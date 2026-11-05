"""Transaction management: the application-level operations that combine the
validator, the database and the Excel reader.

The Streamlit pages call into this module only; they never touch SQL.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, BinaryIO, Iterable

import numpy as np
import pandas as pd

from config import COLUMN_KEYS, DIRECTIONS
from core.data_validator import (
    ImportPreview,
    ValidatedRow,
    ValidationError,
    compute_fingerprint,
    validate_frame,
    validate_record,
)
from core.database import Database
from core.excel_reader import ExcelReadResult, read_transactions
from core.money import cents_to_decimal


@dataclass
class ImportResult:
    import_id: int
    imported: int
    skipped_existing: int
    skipped_in_file_duplicates: int
    failed: int
    unclassified: int
    inserted_ids: list[int]
    replaced_existing: int = 0      # records deleted first when importing in "replace" mode


SEARCH_FIELDS = {
    "Any field": ("sender_name", "receiver_name", "sender_mobile", "account_number", "notes"),
    "Sender name": ("sender_name",),
    "Receiver name": ("receiver_name",),
    "Mobile number": ("sender_mobile",),
    "Account number": ("account_number",),
    "Reference / notes": ("notes",),
}


class TransactionManager:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------- settings
    @property
    def allow_negative(self) -> bool:
        return self.db.allow_negative_amounts()

    # ---------------------------------------------------------------- CRUD
    def add_transaction(self, raw: dict[str, Any], *, today: date | None = None) -> int:
        """Validate and insert a manually entered transaction. Returns its id."""
        validated = validate_record(raw, allow_negative=self.allow_negative, today=today)
        if not validated.is_valid:
            raise ValidationError(validated.errors)
        record = dict(validated.record)
        record["import_id"] = None
        record["source_row"] = None
        return self.db.insert_transaction(record)

    def update_transaction(self, txn_id: int, raw: dict[str, Any], *, today: date | None = None) -> ValidatedRow:
        existing = self.db.get_transaction(txn_id)
        if existing is None:
            raise ValidationError([f"Transaction {txn_id} no longer exists"])
        validated = validate_record(raw, allow_negative=self.allow_negative, today=today)
        if not validated.is_valid:
            raise ValidationError(validated.errors)
        record = dict(validated.record)
        record.pop("source_row", None)   # keep the original provenance
        self.db.update_transaction(txn_id, record)
        return validated

    def delete_transaction(self, txn_id: int) -> bool:
        return self.db.delete_transaction(txn_id)

    def set_direction(self, txn_ids: Iterable[int], direction: str | None) -> int:
        if direction is not None and direction not in DIRECTIONS:
            raise ValidationError([f"Direction must be one of {', '.join(DIRECTIONS)} or blank"])
        return self.db.set_direction(txn_ids, direction)

    def apply_classifications(self, changes: dict[int, str | None]) -> int:
        """Apply {transaction id: direction or None} in bulk."""
        updated = 0
        by_direction: dict[str | None, list[int]] = {}
        for txn_id, direction in changes.items():
            by_direction.setdefault(direction, []).append(int(txn_id))
        for direction, ids in by_direction.items():
            updated += self.set_direction(ids, direction)
        return updated

    def get_transaction(self, txn_id: int) -> dict | None:
        return self.db.get_transaction(txn_id)

    def transaction_to_form(self, record: dict) -> dict[str, Any]:
        """Convert a DB record into canonical raw form values for editing."""
        return {
            "txn_no": record.get("txn_no"),
            "txn_date": record.get("txn_date"),
            "direction": record.get("direction"),
            "sender_name": record.get("sender_name"),
            "sender_mobile": record.get("sender_mobile"),
            "receiver_name": record.get("receiver_name"),
            "account_number": record.get("account_number"),
            "currency": record.get("currency"),
            "amount_usd": cents_to_decimal(record.get("amount_cents")),
            "exchange_rate": record.get("exchange_rate"),
            "amount_local": record.get("amount_local"),
            "notes": record.get("notes"),
        }

    # -------------------------------------------------------------- import
    def read_excel(self, source: str | BinaryIO | bytes, *, sheet_name: str | None = None,
                   filename: str | None = None) -> ExcelReadResult:
        return read_transactions(source, sheet_name=sheet_name, filename=filename)

    def preview_import(self, read_result: ExcelReadResult, *, today: date | None = None,
                       replace_existing: bool = False) -> ImportPreview:
        """Validate the file. In replace mode nothing can be "already in the
        database" because every existing record is deleted on commit."""
        preview = validate_frame(
            read_result.frame,
            existing_fingerprints=set() if replace_existing else self.db.existing_fingerprints(),
            allow_negative=self.allow_negative,
            today=today,
        )
        mapping = read_result.mapping
        if mapping.missing_optional:
            from config import COLUMN_HEADERS  # local import avoids a cycle in type checkers
            names = ", ".join(COLUMN_HEADERS[k] for k in mapping.missing_optional)
            preview.column_warnings.append(f"Optional columns not found (left blank): {names}")
        if mapping.unmapped_headers:
            preview.column_warnings.append(
                "Ignored columns: " + ", ".join(mapping.unmapped_headers)
            )
        for skipped in read_result.skipped_rows:
            preview.column_warnings.append(f"Row {skipped.excel_row}: {skipped.reason}")
        return preview

    def previous_imports_of_file(self, file_hash: str) -> list[dict]:
        return self.db.find_imports_by_hash(file_hash)

    def commit_import(
        self,
        read_result: ExcelReadResult,
        preview: ImportPreview,
        *,
        include_in_file_duplicates: bool = True,
        include_existing: bool = False,
        replace_existing: bool = False,
    ) -> ImportResult:
        """Write the selected preview rows to the database in one transaction.

        ``replace_existing=True`` ("Replace" mode) deletes every transaction in
        the database - imported or entered by hand - and then loads this file,
        all inside one SQL transaction. The default ("Merge" mode) keeps every
        existing record and only adds rows that are not already present.
        """
        selected = preview.importable_rows(
            include_in_file_duplicates=include_in_file_duplicates,
            include_existing=include_existing or replace_existing,
        )
        skipped_existing = preview.exists_count if not (include_existing or replace_existing) else 0
        skipped_dups = preview.duplicate_in_file_count if not include_in_file_duplicates else 0
        import_id = self.db.add_import(
            filename=read_result.filename,
            file_hash=read_result.file_hash,
            sheet_name=read_result.sheet_name,
            total_rows=preview.total,
            imported_count=0,
            skipped_existing=skipped_existing,
            skipped_duplicates=skipped_dups,
            failed_count=preview.invalid_count,
            notes=None,
        )
        records = []
        for row in selected:
            record = dict(row.record)
            record["import_id"] = import_id
            records.append(record)
        replaced = 0
        try:
            if replace_existing:
                replaced, ids = self.db.replace_transactions(records)
                self.db.update_import(import_id, imported_count=len(ids),
                                      notes=f"replace mode: {replaced} existing record(s) deleted first")
            else:
                ids = self.db.insert_transactions(records)
                self.db.update_import(import_id, imported_count=len(ids))
        except Exception as exc:
            # The insert itself is atomic (nothing was written); keep the history
            # row as an audit trail of the failed attempt instead of an orphan.
            self.db.update_import(import_id, imported_count=0, notes=f"FAILED - nothing imported: {exc}")
            raise
        unclassified = sum(1 for r in records if r.get("direction") is None)
        return ImportResult(
            import_id=import_id,
            imported=len(ids),
            skipped_existing=skipped_existing,
            skipped_in_file_duplicates=skipped_dups,
            failed=preview.invalid_count,
            unclassified=unclassified,
            inserted_ids=ids,
            replaced_existing=replaced,
        )

    def undo_import(self, import_id: int) -> int:
        return self.db.delete_import_records(import_id)

    # --------------------------------------------------------------- loads
    def load_frame(self) -> pd.DataFrame:
        return self.db.fetch_transactions()

    def signature(self) -> tuple:
        return self.db.signature()


# --------------------------------------------------------------------------
# Pure search / filter helpers (operate on the loaded DataFrame)
# --------------------------------------------------------------------------
def filter_transactions(
    frame: pd.DataFrame,
    *,
    text: str | None = None,
    field: str = "Any field",
    date_from: date | None = None,
    date_to: date | None = None,
    directions: Iterable[str] | None = None,
    currencies: Iterable[str] | None = None,
    unclassified_only: bool = False,
) -> pd.DataFrame:
    """Apply the Transactions page filters without touching the database."""
    if frame is None or frame.empty:
        return frame
    mask = np.ones(len(frame), dtype=bool)
    if text:
        needle = text.strip().lower()
        digits = "".join(ch for ch in needle if ch.isdigit())
        columns = SEARCH_FIELDS.get(field, SEARCH_FIELDS["Any field"])
        text_mask = np.zeros(len(frame), dtype=bool)
        for col in columns:
            values = frame[col].fillna("").astype(str).str.lower()
            text_mask |= values.str.contains(needle, regex=False).to_numpy()
            if digits and col in ("sender_mobile", "account_number"):
                compact = values.str.replace(r"\D", "", regex=True)
                text_mask |= compact.str.contains(digits, regex=False).to_numpy()
        mask &= text_mask
    dates = frame["txn_date"].astype(str).to_numpy()
    if date_from is not None:
        mask &= dates >= date_from.isoformat()
    if date_to is not None:
        mask &= dates <= date_to.isoformat()
    if directions:
        wanted = set(directions)
        direction = frame["direction"].to_numpy(dtype=object)
        dir_mask = np.zeros(len(frame), dtype=bool)
        for d in wanted:
            if d in DIRECTIONS:
                dir_mask |= direction == d
            else:  # "Unclassified"
                dir_mask |= np.array([v is None for v in direction])
        mask &= dir_mask
    if unclassified_only:
        mask &= np.array([v is None for v in frame["direction"].to_numpy(dtype=object)])
    if currencies:
        wanted_c = set(currencies)
        currency = frame["currency"].to_numpy(dtype=object)
        cur_mask = np.zeros(len(frame), dtype=bool)
        for c in wanted_c:
            if c == "(blank)":
                cur_mask |= np.array([v is None for v in currency])
            else:
                cur_mask |= currency == c
        mask &= cur_mask
    return frame[mask]


def frame_for_display(frame: pd.DataFrame) -> pd.DataFrame:
    """Human-friendly column names and float amounts for on-screen tables.

    Floats are *only* used for display formatting; all calculations use the
    integer-cents / Decimal engine.
    """
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["ID", "No.", "Date", "Direction", "Sender Name", "Sender Mobile",
                                     "Receiver Name", "Account Number", "Currency", "Amount (USD)",
                                     "Exchange Rate", "Amount in Local Currency", "Reference / Notes"])
    out = pd.DataFrame({
        "ID": frame["id"].to_numpy(),
        "No.": frame["txn_no"].astype(object).where(frame["txn_no"].notna(), None).to_numpy(),
        "Date": frame["txn_date"].to_numpy(),
        "Direction": [d if d else "Unclassified" for d in frame["direction"].tolist()],
        "Sender Name": frame["sender_name"].to_numpy(),
        "Sender Mobile": frame["sender_mobile"].to_numpy(),
        "Receiver Name": frame["receiver_name"].to_numpy(),
        "Account Number": frame["account_number"].to_numpy(),
        "Currency": frame["currency"].to_numpy(),
        "Amount (USD)": (frame["amount_cents"].to_numpy(dtype="int64") / 100.0),
        "Exchange Rate": [float(v) if v not in (None, "") else None for v in frame["exchange_rate"].tolist()],
        "Amount in Local Currency": [float(v) if v not in (None, "") else None for v in frame["amount_local"].tolist()],
        "Reference / Notes": frame["notes"].to_numpy(),
    })
    return out


__all__ = [
    "TransactionManager", "ImportResult", "filter_transactions", "frame_for_display",
    "SEARCH_FIELDS", "compute_fingerprint", "COLUMN_KEYS",
]
