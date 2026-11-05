"""Database backup, restore, validation and pre-migration safety copies."""
from __future__ import annotations

import sqlite3

import pytest

from core import database as database_module
from core.database import SCHEMA_VERSION, Database, timestamped_backup_name


def _add(db: Database, sender: str = "A", amount_cents: int = 100, fp: str = "fp") -> int:
    return db.insert_transaction({
        "txn_date": "2026-01-01", "sender_name": sender, "receiver_name": "B",
        "amount_cents": amount_cents, "currency": "USD", "fingerprint": fp,
    })


def test_backup_name_is_safe_and_timestamped():
    name = timestamped_backup_name("pre migration/v1")
    assert name.startswith("database-pre-migration-v1-") and name.endswith(".db")
    assert "/" not in name and " " not in name


def test_create_backup_is_a_valid_copy(db):
    _add(db, fp="1")
    _add(db, sender="C", fp="2")
    path = db.create_backup("manual")
    assert path.exists() and path.parent == db.backup_dir
    info = Database.inspect_backup(path)
    assert info["ok"] and info["transactions"] == 2 and info["schema_version"] == SCHEMA_VERSION
    listed = db.list_backups()
    assert [b["name"] for b in listed] == [path.name]
    assert listed[0]["size_bytes"] > 0


def test_restore_replaces_data_and_keeps_safety_copy(db):
    _add(db, fp="1")
    backup = db.create_backup("before")
    db.delete_all_transactions()
    _add(db, sender="Later", fp="9")
    result = db.restore_from(backup)
    assert result["transactions"] == 1
    assert db.count_transactions() == 1
    assert db.fetch_transactions()["sender_name"].tolist() == ["A"]
    safety = result["safety_backup"]
    assert safety.exists() and "pre-restore" in safety.name
    assert Database.inspect_backup(safety)["transactions"] == 1   # the "Later" record is preserved there


def test_restore_rejects_invalid_files(db, tmp_path):
    missing = tmp_path / "missing.db"
    assert not Database.inspect_backup(missing)["ok"]
    text = tmp_path / "text.db"
    text.write_text("hello")
    assert "Not an SQLite" in Database.inspect_backup(text)["reason"]
    other = tmp_path / "other.db"
    conn = sqlite3.connect(other)
    conn.execute("CREATE TABLE something(x)")
    conn.commit()
    conn.close()
    assert "not a Daily Money Transfer Manager database" in Database.inspect_backup(other)["reason"]
    with pytest.raises(ValueError):
        db.restore_from(other)
    assert db.count_transactions() == 0           # untouched


def test_restore_rejects_newer_schema(db, tmp_path):
    newer = tmp_path / "newer.db"
    Database(newer)
    conn = sqlite3.connect(newer)
    conn.execute("UPDATE schema_info SET value = ? WHERE key = 'version'", (str(SCHEMA_VERSION + 5),))
    conn.commit()
    conn.close()
    info = Database.inspect_backup(newer)
    assert not info["ok"] and "newer version" in info["reason"]


def test_pre_migration_backup_is_written(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    Database(path)
    conn = sqlite3.connect(path)
    conn.execute("UPDATE schema_info SET value = '0' WHERE key = 'version'")
    conn.commit()
    conn.close()

    applied = []

    def migrate_to_1(conn):
        conn.execute("CREATE TABLE IF NOT EXISTS migrated(x INTEGER)")
        applied.append(1)

    monkeypatch.setattr(database_module, "_MIGRATIONS", {1: migrate_to_1})
    monkeypatch.setattr(database_module, "SCHEMA_VERSION", 1)
    db = Database(path)                             # re-open triggers the migration
    assert applied == [1]
    backups = db.list_backups()
    assert len(backups) == 1 and "pre-migration-v0" in backups[0]["name"]
    conn = db.connect()
    assert conn.execute("SELECT value FROM schema_info WHERE key='version'").fetchone()[0] == "1"
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='migrated'").fetchone()
    conn.close()


def test_backup_dir_defaults_next_to_database(tmp_path):
    db = Database(tmp_path / "nested" / "app.db")
    assert db.backup_dir == tmp_path / "nested" / "backups"
    custom = Database(tmp_path / "b.db", backup_dir=tmp_path / "elsewhere")
    assert custom.create_backup().parent == tmp_path / "elsewhere"
