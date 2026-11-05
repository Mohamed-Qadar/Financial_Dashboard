"""SQLite persistence layer.

The :class:`Database` class owns the schema and every SQL statement in the
application. Other modules work with plain dictionaries / pandas DataFrames
and never build SQL themselves.

Storage conventions
-------------------
* ``txn_date`` is an ISO ``YYYY-MM-DD`` string (sorts chronologically).
* ``amount_cents`` is the USD amount in integer cents (exact arithmetic).
* ``exchange_rate`` and ``amount_local`` are canonical Decimal strings or NULL.
* ``fingerprint`` is a SHA-256 of the business fields used for duplicate
  detection; it is indexed but deliberately *not* unique so a user can choose
  to import a genuine repeat transfer.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

import pandas as pd

from config import DEFAULT_SETTINGS

SCHEMA_VERSION = 1

TRANSACTION_COLUMNS = [
    "id", "txn_no", "txn_date", "direction", "sender_name", "sender_mobile",
    "receiver_name", "account_number", "currency", "amount_cents",
    "exchange_rate", "amount_local", "notes", "fingerprint", "import_id",
    "source_row", "created_at", "updated_at",
]

# Fields a caller may supply when inserting or updating a transaction.
WRITABLE_FIELDS = [
    "txn_no", "txn_date", "direction", "sender_name", "sender_mobile",
    "receiver_name", "account_number", "currency", "amount_cents",
    "exchange_rate", "amount_local", "notes", "fingerprint", "import_id",
    "source_row",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_info (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_history (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    filename           TEXT NOT NULL,
    file_hash          TEXT NOT NULL,
    sheet_name         TEXT,
    imported_at        TEXT NOT NULL,
    total_rows         INTEGER NOT NULL DEFAULT 0,
    imported_count     INTEGER NOT NULL DEFAULT 0,
    skipped_existing   INTEGER NOT NULL DEFAULT 0,
    skipped_duplicates INTEGER NOT NULL DEFAULT 0,
    failed_count       INTEGER NOT NULL DEFAULT 0,
    notes              TEXT
);
CREATE INDEX IF NOT EXISTS idx_import_history_hash ON import_history(file_hash);

CREATE TABLE IF NOT EXISTS transactions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    txn_no         INTEGER,
    txn_date       TEXT    NOT NULL,
    direction      TEXT    CHECK (direction IS NULL OR direction IN ('Incoming', 'Outgoing')),
    sender_name    TEXT    NOT NULL,
    sender_mobile  TEXT,
    receiver_name  TEXT    NOT NULL,
    account_number TEXT,
    currency       TEXT,
    amount_cents   INTEGER NOT NULL,
    exchange_rate  TEXT,
    amount_local   TEXT,
    notes          TEXT,
    fingerprint    TEXT    NOT NULL,
    import_id      INTEGER REFERENCES import_history(id) ON DELETE SET NULL,
    source_row     INTEGER,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_txn_date        ON transactions(txn_date);
CREATE INDEX IF NOT EXISTS idx_txn_direction   ON transactions(direction);
CREATE INDEX IF NOT EXISTS idx_txn_fingerprint ON transactions(fingerprint);
CREATE INDEX IF NOT EXISTS idx_txn_sender      ON transactions(sender_name);
CREATE INDEX IF NOT EXISTS idx_txn_receiver    ON transactions(receiver_name);
CREATE INDEX IF NOT EXISTS idx_txn_mobile      ON transactions(sender_mobile);
CREATE INDEX IF NOT EXISTS idx_txn_account     ON transactions(account_number);
CREATE INDEX IF NOT EXISTS idx_txn_import      ON transactions(import_id);
CREATE INDEX IF NOT EXISTS idx_txn_updated     ON transactions(updated_at);
"""


# Schema migrations keyed by the version they upgrade *to*. Each callable
# receives an open connection inside a transaction. Version 1 is the initial
# schema, so the registry starts empty.
_MIGRATIONS: dict[int, Any] = {}


def timestamped_backup_name(label: str = "manual") -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in label).strip("-") or "backup"
    return f"database-{safe}-{stamp}.db"


def now_iso() -> str:
    """Local timestamp with microseconds; used for audit columns and cache keys."""
    return datetime.now().isoformat(timespec="microseconds")


class Database:
    """Thin wrapper around a SQLite file."""

    def __init__(self, path: str | Path, backup_dir: str | Path | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Backups live next to the database unless told otherwise.
        self.backup_dir = Path(backup_dir) if backup_dir else self.path.parent / "backups"
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, detect_types=0, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager that commits on success and rolls back on error."""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create missing tables and apply schema migrations.

        A copy of the database file is written to ``backup_dir`` *before* any
        migration runs, so an interrupted upgrade can always be recovered.
        """
        existing_version = self._stored_schema_version()
        if existing_version is not None and existing_version < SCHEMA_VERSION:
            self.backup_to(self.backup_dir / timestamped_backup_name(f"pre-migration-v{existing_version}"))
        with self.transaction() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR IGNORE INTO schema_info(key, value) VALUES ('version', ?)",
                (str(SCHEMA_VERSION),),
            )
            if existing_version is not None and existing_version < SCHEMA_VERSION:
                for version in range(existing_version + 1, SCHEMA_VERSION + 1):
                    _MIGRATIONS[version](conn)
                conn.execute("UPDATE schema_info SET value = ? WHERE key = 'version'", (str(SCHEMA_VERSION),))
            stamp = now_iso()
            for key, value in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
                    (key, value, stamp),
                )

    def _stored_schema_version(self) -> int | None:
        """Schema version recorded in an existing file, or None for a new one."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return None
        conn = self.connect()
        try:
            has_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_info'"
            ).fetchone()
            if not has_table:
                return None
            row = conn.execute("SELECT value FROM schema_info WHERE key = 'version'").fetchone()
            return int(row[0]) if row else None
        finally:
            conn.close()

    # --------------------------------------------------------------- backups
    def backup_to(self, destination: str | Path) -> Path:
        """Write a consistent copy of the live database to ``destination``.

        Uses SQLite's online backup API, so the copy is valid even while the
        application is running. Returns the path written.
        """
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".part")
        source = self.connect()
        try:
            target = sqlite3.connect(tmp)
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
        tmp.replace(destination)
        return destination

    def create_backup(self, label: str = "manual") -> Path:
        """Create a timestamped backup in ``backup_dir`` and return its path."""
        return self.backup_to(self.backup_dir / timestamped_backup_name(label))

    def list_backups(self) -> list[dict]:
        """Backups in ``backup_dir``, newest first: name, path, size, modified."""
        if not self.backup_dir.exists():
            return []
        items = []
        for file in self.backup_dir.glob("*.db"):
            stat = file.stat()
            items.append({
                "name": file.name,
                "path": file,
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            })
        items.sort(key=lambda item: item["modified"], reverse=True)
        return items

    @staticmethod
    def inspect_backup(candidate: str | Path) -> dict:
        """Validate that ``candidate`` is a healthy database of this application.

        Returns ``{"ok": bool, "reason": str, "transactions": int, "schema_version": int|None}``.
        Never modifies the file.
        """
        candidate = Path(candidate)
        result = {"ok": False, "reason": "", "transactions": 0, "schema_version": None}
        if not candidate.exists() or candidate.stat().st_size == 0:
            result["reason"] = "File does not exist or is empty."
            return result
        with open(candidate, "rb") as fh:
            if fh.read(16) != b"SQLite format 3\x00":
                result["reason"] = "Not an SQLite database file."
                return result
        uri = f"file:{candidate.resolve().as_posix()}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
        except sqlite3.Error as exc:
            result["reason"] = f"Cannot open file: {exc}"
            return result
        try:
            check = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                result["reason"] = f"Integrity check failed: {check}"
                return result
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if "transactions" not in tables or "schema_info" not in tables:
                result["reason"] = "The file is an SQLite database but not a Daily Money Transfer Manager database."
                return result
            row = conn.execute("SELECT value FROM schema_info WHERE key = 'version'").fetchone()
            version = int(row[0]) if row else None
            if version is not None and version > SCHEMA_VERSION:
                result["reason"] = (f"The backup was made by a newer version of the application "
                                    f"(schema {version} > {SCHEMA_VERSION}). Update the application first.")
                result["schema_version"] = version
                return result
            result["schema_version"] = version
            result["transactions"] = int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
            result["ok"] = True
            return result
        except sqlite3.Error as exc:
            result["reason"] = f"Cannot read file: {exc}"
            return result
        finally:
            conn.close()

    def restore_from(self, source: str | Path) -> dict:
        """Replace the live database with ``source`` (a backup file).

        The current database is saved as a ``pre-restore`` backup first, the
        candidate is validated, and the copy is made with SQLite's backup API
        so the live file is never left half-written. Returns
        ``{"safety_backup": Path, "transactions": int}``.
        """
        info = self.inspect_backup(source)
        if not info["ok"]:
            raise ValueError(info["reason"])
        safety = self.create_backup("pre-restore")
        src = sqlite3.connect(f"file:{Path(source).resolve().as_posix()}?mode=ro", uri=True)
        try:
            dest = self.connect()
            try:
                src.backup(dest)
            finally:
                dest.close()
        finally:
            src.close()
        self.initialize()           # apply migrations if the backup is older
        return {"safety_backup": safety, "transactions": info["transactions"]}

    # -------------------------------------------------------------- settings
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.transaction() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return DEFAULT_SETTINGS.get(key, default)
        return row["value"]

    def set_setting(self, key: str, value: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, str(value), now_iso()),
            )

    def all_settings(self) -> dict[str, str]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        merged = dict(DEFAULT_SETTINGS)
        merged.update({r["key"]: r["value"] for r in rows})
        return merged

    def allow_negative_amounts(self) -> bool:
        return self.get_setting("allow_negative_amounts", "0") == "1"

    # -------------------------------------------------------- import history
    def add_import(self, **fields: Any) -> int:
        fields.setdefault("imported_at", now_iso())
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with self.transaction() as conn:
            cur = conn.execute(
                f"INSERT INTO import_history({cols}) VALUES ({marks})",
                tuple(fields.values()),
            )
            return int(cur.lastrowid)

    def update_import(self, import_id: int, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE import_history SET {assignments} WHERE id = ?",
                (*fields.values(), import_id),
            )

    def find_imports_by_hash(self, file_hash: str) -> list[dict]:
        with self.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM import_history WHERE file_hash = ? ORDER BY imported_at DESC",
                (file_hash,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_imports(self) -> pd.DataFrame:
        with self.transaction() as conn:
            rows = conn.execute(
                "SELECT h.*, (SELECT COUNT(*) FROM transactions t WHERE t.import_id = h.id) "
                "AS current_records FROM import_history h ORDER BY h.imported_at DESC"
            ).fetchall()
        columns = [
            "id", "filename", "file_hash", "sheet_name", "imported_at", "total_rows",
            "imported_count", "skipped_existing", "skipped_duplicates", "failed_count",
            "notes", "current_records",
        ]
        return pd.DataFrame([dict(r) for r in rows], columns=columns)

    def delete_import_records(self, import_id: int) -> int:
        """Remove every transaction that came from one import (undo)."""
        with self.transaction() as conn:
            cur = conn.execute("DELETE FROM transactions WHERE import_id = ?", (import_id,))
            conn.execute(
                "UPDATE import_history SET notes = COALESCE(notes || ' | ', '') || ? WHERE id = ?",
                (f"records removed on {now_iso()[:19]}", import_id),
            )
            return cur.rowcount

    # ----------------------------------------------------------- transactions
    @staticmethod
    def _insert_rows(conn: sqlite3.Connection, records: list[dict]) -> list[int]:
        stamp = now_iso()
        cols = WRITABLE_FIELDS + ["created_at", "updated_at"]
        placeholders = ", ".join("?" for _ in cols)
        sql = f"INSERT INTO transactions({', '.join(cols)}) VALUES ({placeholders})"
        ids: list[int] = []
        for rec in records:
            values = [rec.get(c) for c in WRITABLE_FIELDS] + [stamp, stamp]
            cur = conn.execute(sql, values)
            ids.append(int(cur.lastrowid))
        return ids

    def insert_transactions(self, records: Iterable[dict]) -> list[int]:
        """Bulk insert inside one transaction; returns new ids in input order."""
        records = list(records)
        if not records:
            return []
        with self.transaction() as conn:
            return self._insert_rows(conn, records)

    def replace_transactions(self, records: Iterable[dict]) -> tuple[int, list[int]]:
        """Delete every transaction, then insert ``records`` - atomically.

        Returns ``(deleted_count, new_ids)``. Either both steps happen or
        neither does, so a failed insert never leaves the table empty.
        """
        records = list(records)
        with self.transaction() as conn:
            deleted = conn.execute("DELETE FROM transactions").rowcount
            return int(deleted), self._insert_rows(conn, records)

    def insert_transaction(self, record: dict) -> int:
        return self.insert_transactions([record])[0]

    def update_transaction(self, txn_id: int, record: dict) -> bool:
        fields = {k: record[k] for k in WRITABLE_FIELDS if k in record}
        if not fields:
            return False
        fields["updated_at"] = now_iso()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self.transaction() as conn:
            cur = conn.execute(
                f"UPDATE transactions SET {assignments} WHERE id = ?",
                (*fields.values(), int(txn_id)),
            )
            return cur.rowcount == 1

    def set_direction(self, txn_ids: Iterable[int], direction: str | None) -> int:
        ids = [int(i) for i in txn_ids]
        if not ids:
            return 0
        stamp = now_iso()
        with self.transaction() as conn:
            cur = conn.executemany(
                "UPDATE transactions SET direction = ?, updated_at = ? WHERE id = ?",
                [(direction, stamp, i) for i in ids],
            )
            return cur.rowcount if cur.rowcount and cur.rowcount > 0 else len(ids)

    def delete_transaction(self, txn_id: int) -> bool:
        with self.transaction() as conn:
            cur = conn.execute("DELETE FROM transactions WHERE id = ?", (int(txn_id),))
            return cur.rowcount == 1

    def delete_all_transactions(self) -> int:
        with self.transaction() as conn:
            cur = conn.execute("DELETE FROM transactions")
            return cur.rowcount

    def get_transaction(self, txn_id: int) -> dict | None:
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE id = ?", (int(txn_id),)
            ).fetchone()
        return dict(row) if row else None

    def existing_fingerprints(self) -> set[str]:
        with self.transaction() as conn:
            rows = conn.execute("SELECT DISTINCT fingerprint FROM transactions").fetchall()
        return {r["fingerprint"] for r in rows}

    def count_manual_transactions(self) -> int:
        """Records entered by hand (not belonging to any import)."""
        with self.transaction() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE import_id IS NULL"
            ).fetchone()[0])

    def count_transactions(self) -> int:
        with self.transaction() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])

    def next_txn_no(self) -> int:
        with self.transaction() as conn:
            value = conn.execute(
                "SELECT COALESCE(MAX(txn_no), 0) FROM transactions"
            ).fetchone()[0]
        return int(value) + 1

    def signature(self) -> tuple:
        """Cheap change-detection key: changes whenever any record changes.

        Used as the cache key for expensive DataFrame loads so the UI never
        re-reads the whole table unless something was actually written.
        """
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(MAX(updated_at), ''), COALESCE(MAX(id), 0) "
                "FROM transactions"
            ).fetchone()
        return (int(row[0]), str(row[1]), int(row[2]))

    def fetch_transactions(self) -> pd.DataFrame:
        """Load every transaction into a typed DataFrame (see module docstring)."""
        with self.transaction() as conn:
            rows = conn.execute(
                f"SELECT {', '.join(TRANSACTION_COLUMNS)} FROM transactions "
                "ORDER BY txn_date, id"
            ).fetchall()
        return rows_to_frame(rows)

    def database_size_bytes(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0


def rows_to_frame(rows: list) -> pd.DataFrame:
    """Build the canonical transactions DataFrame from sqlite rows."""
    data = {col: [row[idx] for row in rows] for idx, col in enumerate(TRANSACTION_COLUMNS)}
    frame = pd.DataFrame(data, columns=TRANSACTION_COLUMNS)
    frame["id"] = frame["id"].astype("int64")
    frame["amount_cents"] = frame["amount_cents"].astype("int64")
    for col in ("txn_no", "import_id", "source_row"):
        frame[col] = pd.array(frame[col].tolist(), dtype="Int64")
    text_columns = (
        "direction", "sender_mobile", "account_number", "currency", "exchange_rate",
        "amount_local", "notes", "txn_date", "sender_name", "receiver_name",
        "fingerprint", "created_at", "updated_at",
    )
    for col in text_columns:
        frame[col] = pd.Series(
            [None if _is_missing(v) else str(v) for v in data[col]],
            dtype=object, index=frame.index,
        )
    return frame


def _is_missing(value) -> bool:
    if value is None:
        return True
    try:
        return bool(value != value)  # NaN is the only value not equal to itself
    except Exception:  # pragma: no cover - defensive
        return False


def empty_frame() -> pd.DataFrame:
    return rows_to_frame([])
