"""Application settings, database information and maintenance actions."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from config import APP_VERSION, DATA_DIR, DB_PATH, IS_FROZEN, IS_PORTABLE
from core.database import Database
from core.money import MoneyError, parse_rate
from ui.common import clear_data_cache, get_db, get_manager, page_header, section


@st.dialog("Remove imported records")
def _confirm_undo(manager, import_id: int, filename: str, count: int) -> None:
    st.write(f"Remove the **{count}** record(s) that were added by import **#{import_id}** ({filename})?")
    st.info("Only the records that this import added are removed. Records entered manually or added by other "
            "imports are kept. To start again from a file, use **Replace** mode on the Excel Upload page.",
            icon=":material/info:")
    st.warning("Records that were edited after the import are removed too. This cannot be undone.",
               icon=":material/warning:")
    c1, c2 = st.columns(2)
    if c1.button("Yes, remove them", type="primary", width="stretch"):
        removed = manager.undo_import(import_id)
        st.session_state["flash"] = f"Removed {removed} record(s) from import #{import_id}."
        st.rerun()
    if c2.button("Cancel", width="stretch"):
        st.rerun()


@st.dialog("Restore database from backup")
def _confirm_restore(db: Database, source: Path, label: str) -> None:
    info = Database.inspect_backup(source)
    if not info["ok"]:
        st.error(info["reason"], icon=":material/error:")
        return
    st.write(f"Restore **{label}**?")
    st.markdown(f"- The backup contains **{info['transactions']:,}** transaction(s) (schema version "
                f"{info['schema_version']}).\n- The current database has **{db.count_transactions():,}** "
                f"transaction(s) and will be replaced.\n- A safety copy of the current database is created first.")
    typed = st.text_input("Type RESTORE to confirm")
    c1, c2 = st.columns(2)
    if c1.button("Restore now", type="primary", disabled=typed != "RESTORE", width="stretch"):
        try:
            result = db.restore_from(source)
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
            return
        clear_data_cache()
        st.session_state["flash"] = (f"Database restored from {label}: {result['transactions']:,} transaction(s). "
                                     f"Previous data saved as {result['safety_backup'].name}.")
        st.rerun()
    if c2.button("Cancel", width="stretch"):
        st.rerun()


@st.dialog("Delete ALL transactions")
def _confirm_wipe(db) -> None:
    count = db.count_transactions()
    st.error(f"This permanently deletes all {count} transaction(s). Import history and settings are kept.",
             icon=":material/warning:")
    typed = st.text_input("Type DELETE to confirm")
    if st.button("Delete everything", type="primary", disabled=typed != "DELETE"):
        removed = db.delete_all_transactions()
        st.session_state["flash"] = f"Deleted {removed} transaction(s)."
        st.rerun()


def render() -> None:
    page_header("Settings", "Office details, financial rules and database maintenance.", icon=":material/settings:")
    db = get_db()
    manager = get_manager()
    if flash := st.session_state.pop("flash", None):
        st.success(flash, icon=":material/check_circle:")

    current = db.all_settings()
    section("Office and currency")
    with st.form("settings_form", border=True):
        c1, c2 = st.columns(2)
        office_name = c1.text_input("Office name (shown on reports)", value=current["office_name"])
        local_code = c2.text_input("Local currency code", value=current["local_currency_code"], max_chars=3,
                                   help="Three-letter code, e.g. SOS.")
        c3, c4 = st.columns(2)
        default_rate = c3.text_input("Default exchange rate for new entries (optional)",
                                     value=current.get("default_exchange_rate", ""),
                                     help="Pre-fills the Exchange Rate field on the Add form. Never applied to "
                                          "existing records.")
        allow_negative = c4.toggle("Allow negative amounts", value=current["allow_negative_amounts"] == "1",
                                   help="Off by default: negative amounts are rejected during import and entry.")
        if st.form_submit_button("Save settings", type="primary", icon=":material/save:"):
            errors = []
            code = local_code.strip().upper()
            if len(code) != 3 or not code.isalpha():
                errors.append("Local currency code must be three letters.")
            rate_text = default_rate.strip()
            if rate_text:
                try:
                    parsed = parse_rate(rate_text)
                    rate_text = format(parsed, "f") if parsed is not None else ""
                except MoneyError as exc:
                    errors.append(f"Default exchange rate: {exc}")
            if not office_name.strip():
                errors.append("Office name cannot be empty.")
            if errors:
                for err in errors:
                    st.error(err, icon=":material/error:")
            else:
                db.set_setting("office_name", office_name.strip())
                db.set_setting("local_currency_code", code)
                db.set_setting("default_exchange_rate", rate_text)
                db.set_setting("allow_negative_amounts", "1" if allow_negative else "0")
                st.success("Settings saved.", icon=":material/check_circle:")

    section("Database")
    size_kb = db.database_size_bytes() / 1024
    info = pd.DataFrame({
        "Item": ["Location", "Transactions", "Imports recorded", "File size", "Application version"],
        "Value": [str(DB_PATH), f"{db.count_transactions():,}", f"{len(db.list_imports()):,}",
                  f"{size_kb:,.0f} KB", APP_VERSION],
    })
    st.dataframe(info, hide_index=True, width="stretch")
    layout = "portable (data next to the program)" if IS_PORTABLE else ("installed application" if IS_FROZEN
                                                                            else "development")
    st.caption(f"Data is stored permanently in this SQLite file and survives restarts and updates. "
               f"Layout: {layout}. Data folder: `{DATA_DIR}`")

    section("Backups", "Copies of the database file. Restoring a backup replaces the current data.")
    st.caption(f"Backup folder: `{db.backup_dir}`")
    b1, b2, _ = st.columns([1.6, 1.6, 3])
    if b1.button("Create backup now", type="primary", icon=":material/save:", width="stretch"):
        path = db.create_backup("manual")
        st.session_state["flash"] = f"Backup created: {path.name}"
        st.rerun()
    if sys.platform == "win32" and b2.button("Open data folder", icon=":material/folder_open:", width="stretch"):
        os.startfile(str(DATA_DIR))  # noqa: S606 - opens Explorer on the user's own data folder
    backups = db.list_backups()
    if not backups:
        st.caption("No backups yet. Create one before importing a new file or installing an update.")
    else:
        for item in backups[:25]:
            c1, c2, c3, c4 = st.columns([3.4, 2.2, 1.3, 1.3])
            c1.markdown(f"**{item['name']}**")
            c2.caption(f"{item['modified'].replace('T', ' ')} - {item['size_bytes'] / 1024:,.0f} KB")
            c3.download_button("Download", data=item["path"].read_bytes(), file_name=item["name"],
                               mime="application/vnd.sqlite3", key=f"dl_{item['name']}", width="stretch")
            if c4.button("Restore", key=f"rs_{item['name']}", icon=":material/history:", width="stretch"):
                _confirm_restore(db, item["path"], item["name"])
        if len(backups) > 25:
            st.caption(f"{len(backups) - 25} older backup(s) not shown - open the data folder to see them.")
    uploaded = st.file_uploader("Restore from a backup file (.db)", type=["db", "sqlite", "sqlite3"],
                                key="restore_upload", help="Select a backup made by this application.")
    if uploaded is not None:
        incoming = db.backup_dir / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        candidate = incoming / Path(uploaded.name).name
        candidate.write_bytes(uploaded.getvalue())
        info = Database.inspect_backup(candidate)
        if not info["ok"]:
            st.error(f"{uploaded.name}: {info['reason']}", icon=":material/error:")
        else:
            st.info(f"{uploaded.name}: {info['transactions']:,} transaction(s), schema version "
                    f"{info['schema_version']}.", icon=":material/check_circle:")
            if st.button("Restore this file...", icon=":material/history:"):
                _confirm_restore(db, candidate, uploaded.name)

    section("Imports", "Undo an import by removing the records it added.")
    history = db.list_imports()
    manual_count = db.count_manual_transactions()
    st.caption(f"Records entered manually (not part of any import): **{manual_count:,}**. "
               "\"Remove records\" only removes what that import added; manual records stay. "
               "To replace everything with a file, use Replace mode on the Excel Upload page.")
    if history.empty:
        st.caption("No imports yet.")
    else:
        for rec in history.to_dict("records"):
            c1, c2, c3 = st.columns([4, 2, 1.6])
            c1.markdown(f"**#{rec['id']}** {rec['filename']} - sheet *{rec['sheet_name']}* - "
                        f"{str(rec['imported_at'])[:19].replace('T', ' ')}")
            c2.caption(f"{rec['imported_count']} imported, {rec['current_records']} still present")
            if c3.button("Remove records", key=f"undo_{rec['id']}", disabled=int(rec["current_records"]) == 0,
                         icon=":material/undo:", width="stretch"):
                _confirm_undo(manager, int(rec["id"]), rec["filename"], int(rec["current_records"]))

    section("Danger zone")
    if st.button("Delete all transactions...", icon=":material/delete_forever:"):
        _confirm_wipe(db)
