"""Database persistence, import workflow and transaction management."""
from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pytest

from core.data_validator import ValidationError
from core.database import Database
from core.transaction_manager import TransactionManager, filter_transactions, frame_for_display
from tests.conftest import SYNTHETIC_ROWS, build_workbook, txn_row

TODAY = date(2026, 3, 1)


def _import(manager, data: bytes, filename="file.xlsx", **options):
    result = manager.read_excel(io.BytesIO(data), filename=filename)
    preview = manager.preview_import(result, today=TODAY)
    return manager.commit_import(result, preview, **options), preview, result


# ------------------------------------------------------------------ import
def test_import_writes_records_and_history(manager, synthetic_xlsx):
    outcome, preview, result = _import(manager, synthetic_xlsx, "synthetic.xlsx")
    assert outcome.imported == 7 and outcome.failed == 0 and outcome.unclassified == 1
    assert manager.db.count_transactions() == 7
    history = manager.db.list_imports()
    assert len(history) == 1
    row = history.iloc[0]
    assert row["filename"] == "synthetic.xlsx" and row["imported_count"] == 7 and row["current_records"] == 7
    assert row["file_hash"] == result.file_hash
    frame = manager.load_frame()
    assert set(frame["import_id"].dropna().astype(int)) == {outcome.import_id}
    assert frame["source_row"].tolist() == list(range(2, 9))      # Excel row provenance kept


def test_reimport_same_file_adds_nothing(manager, synthetic_xlsx):
    _import(manager, synthetic_xlsx)
    outcome, preview, _ = _import(manager, synthetic_xlsx)
    assert preview.exists_count == 7 and preview.new_count == 0
    assert outcome.imported == 0 and outcome.skipped_existing == 7
    assert manager.db.count_transactions() == 7
    assert len(manager.previous_imports_of_file(preview_hash := _hash(synthetic_xlsx))) == 2


def _hash(data: bytes) -> str:
    from core.excel_reader import file_sha256
    return file_sha256(data)


def test_reimport_after_classification_still_detected(manager, synthetic_xlsx):
    _import(manager, synthetic_xlsx)
    frame = manager.load_frame()
    manager.set_direction(frame["id"].tolist(), "Incoming")
    _, preview, _ = _import(manager, synthetic_xlsx)
    assert preview.exists_count == 7


def test_existing_rows_can_be_imported_only_when_explicitly_allowed(manager, synthetic_xlsx):
    _import(manager, synthetic_xlsx)
    outcome, _, _ = _import(manager, synthetic_xlsx, include_existing=True)
    assert outcome.imported == 7
    assert manager.db.count_transactions() == 14


def test_invalid_rows_are_not_imported_but_reported(manager):
    rows = SYNTHETIC_ROWS[:2] + [txn_row(9, date(2026, 1, 1), None, "X", None, "Y", None, "USD", None)]
    outcome, preview, _ = _import(manager, build_workbook(rows))
    assert outcome.imported == 2 and outcome.failed == 1
    assert preview.rows[2].errors


def test_in_file_duplicates_excluded_when_requested(manager):
    rows = [txn_row(1, date(2026, 1, 1), None, "A", "1", "B", "2", "USD", 50),
            txn_row(2, date(2026, 1, 1), None, "A", "1", "B", "2", "USD", 50)]
    outcome, _, _ = _import(manager, build_workbook(rows), include_in_file_duplicates=False)
    assert outcome.imported == 1 and outcome.skipped_in_file_duplicates == 1
    outcome2, _, _ = _import(manager, build_workbook(rows), include_existing=False)
    assert outcome2.imported == 0           # both rows now match the stored record


def test_undo_import_removes_only_that_imports_records(manager, synthetic_xlsx):
    first, _, _ = _import(manager, synthetic_xlsx)
    manager.add_transaction({"txn_date": "2026-03-01", "sender_name": "Manual", "receiver_name": "Entry",
                             "amount_usd": "5", "currency": "USD"}, today=TODAY)
    removed = manager.undo_import(first.import_id)
    assert removed == 7
    assert manager.db.count_transactions() == 1


def test_replace_mode_deletes_everything_first(manager, synthetic_xlsx):
    _import(manager, synthetic_xlsx)
    manager.add_transaction({"txn_date": "2026-03-01", "sender_name": "Manual", "receiver_name": "Entry",
                             "amount_usd": "5", "currency": "USD"}, today=TODAY)
    assert manager.db.count_transactions() == 8 and manager.db.count_manual_transactions() == 1

    rows = [txn_row(1, date(2026, 2, 2), "Incoming", "New", "1", "Person", "2", "USD", 12.50)]
    result = manager.read_excel(io.BytesIO(build_workbook(rows)), filename="new.xlsx")
    preview = manager.preview_import(result, today=TODAY, replace_existing=True)
    outcome = manager.commit_import(result, preview, replace_existing=True)
    assert outcome.replaced_existing == 8 and outcome.imported == 1
    assert manager.db.count_transactions() == 1 and manager.db.count_manual_transactions() == 0
    assert manager.load_frame()["sender_name"].tolist() == ["New"]
    assert "replace mode" in str(manager.db.list_imports().iloc[0]["notes"])


def test_replace_mode_with_same_file_reloads_every_row(manager, synthetic_xlsx):
    _import(manager, synthetic_xlsx)
    result = manager.read_excel(io.BytesIO(synthetic_xlsx), filename="synthetic.xlsx")
    preview = manager.preview_import(result, today=TODAY, replace_existing=True)
    assert preview.exists_count == 0 and preview.new_count == 7   # nothing is "already in database"
    outcome = manager.commit_import(result, preview, replace_existing=True)
    assert outcome.replaced_existing == 7 and outcome.imported == 7 and outcome.skipped_existing == 0
    assert manager.db.count_transactions() == 7


def test_merge_mode_keeps_manual_records(manager, synthetic_xlsx):
    manager.add_transaction({"txn_date": "2026-03-01", "sender_name": "Manual", "receiver_name": "Entry",
                             "amount_usd": "5", "currency": "USD"}, today=TODAY)
    outcome, _, _ = _import(manager, synthetic_xlsx)
    assert outcome.replaced_existing == 0 and outcome.imported == 7
    assert manager.db.count_transactions() == 8 and manager.db.count_manual_transactions() == 1


def test_replace_is_atomic_when_insert_fails(loaded_manager):
    db = loaded_manager.db
    with pytest.raises(Exception):
        db.replace_transactions([{"sender_name": "broken row without required fields"}])
    assert db.count_transactions() == 7      # delete was rolled back together with the failed insert


# -------------------------------------------------------------- persistence
def test_data_persists_across_reopen(tmp_path, synthetic_xlsx):
    path = tmp_path / "persist.db"
    first = TransactionManager(Database(path))
    _import(first, synthetic_xlsx)
    first.db.set_setting("office_name", "Hargeisa Branch")
    reopened = Database(path)
    assert reopened.count_transactions() == 7
    assert reopened.get_setting("office_name") == "Hargeisa Branch"
    frame = reopened.fetch_transactions()
    assert frame.loc[frame["txn_no"] == 1, "sender_mobile"].iloc[0] == "+252611111111"
    assert frame.loc[frame["txn_no"] == 2, "sender_mobile"].iloc[0] == "0611000001"


def test_settings_defaults_and_updates(db):
    assert db.get_setting("allow_negative_amounts") == "0"
    assert db.allow_negative_amounts() is False
    db.set_setting("allow_negative_amounts", "1")
    assert db.allow_negative_amounts() is True
    assert db.all_settings()["local_currency_code"] == "SOS"


def test_signature_changes_on_write(loaded_manager):
    before = loaded_manager.signature()
    frame = loaded_manager.load_frame()
    loaded_manager.set_direction([int(frame["id"].iloc[0])], "Outgoing")
    assert loaded_manager.signature() != before


# -------------------------------------------------------------------- CRUD
def test_add_edit_delete_transaction(manager):
    new_id = manager.add_transaction({
        "txn_no": "7", "txn_date": "04-Nov-2026", "direction": "Incoming", "sender_name": "Test Sender",
        "sender_mobile": "0612345678", "receiver_name": "Me", "account_number": "0099",
        "currency": "sos", "amount_usd": "12.50", "exchange_rate": "28500", "notes": "ref-1",
    }, today=date(2026, 11, 4))
    record = manager.get_transaction(new_id)
    assert record["amount_cents"] == 1250 and record["currency"] == "SOS"
    assert record["amount_local"] == "356250.00" and record["sender_mobile"] == "0612345678"
    assert record["txn_no"] == 7 and record["import_id"] is None

    manager.update_transaction(new_id, {**manager.transaction_to_form(record), "amount_usd": "20",
                                        "direction": "Outgoing"}, today=date(2026, 11, 4))
    updated = manager.get_transaction(new_id)
    assert updated["amount_cents"] == 2000 and updated["direction"] == "Outgoing"
    assert updated["amount_local"] == "570000.00"
    assert updated["fingerprint"] != record["fingerprint"]       # fingerprint follows the data

    assert manager.delete_transaction(new_id) is True
    assert manager.get_transaction(new_id) is None
    assert manager.delete_transaction(new_id) is False


def test_add_rejects_invalid_input(manager):
    with pytest.raises(ValidationError) as excinfo:
        manager.add_transaction({"txn_date": "bad", "sender_name": "", "receiver_name": "x", "amount_usd": "-5"})
    joined = " ".join(excinfo.value.errors)
    assert "Date" in joined and "Sender" in joined and "negative" in joined
    assert manager.db.count_transactions() == 0


def test_negative_allowed_via_setting(manager):
    manager.db.set_setting("allow_negative_amounts", "1")
    new_id = manager.add_transaction({"txn_date": "2026-01-01", "direction": "Outgoing", "sender_name": "A",
                                      "receiver_name": "B", "amount_usd": "-3.00"})
    assert manager.get_transaction(new_id)["amount_cents"] == -300


def test_set_direction_validates_value(loaded_manager):
    with pytest.raises(ValidationError):
        loaded_manager.set_direction([1], "Sideways")
    frame = loaded_manager.load_frame()
    ids = frame["id"].tolist()[:2]
    assert loaded_manager.apply_classifications({ids[0]: "Incoming", ids[1]: None}) == 2
    frame = loaded_manager.load_frame()
    assert frame.loc[frame["id"] == ids[1], "direction"].iloc[0] is None


# ------------------------------------------------------------------ search
def test_filter_transactions(loaded_manager):
    frame = loaded_manager.load_frame()
    assert len(filter_transactions(frame, text="ali hassan", field="Sender name")) == 3
    assert len(filter_transactions(frame, text="Ali Hassan", field="Receiver name")) == 4   # rows 2, 3, 4, 7
    assert len(filter_transactions(frame, text="0611000001", field="Mobile number")) == 1
    assert len(filter_transactions(frame, text="0611 000 002", field="Account number")) == 2   # digits matched
    assert len(filter_transactions(frame, text="+252611111111", field="Any field")) == 3
    assert len(filter_transactions(frame, date_from=date(2026, 1, 6), date_to=date(2026, 1, 6))) == 2
    assert len(filter_transactions(frame, directions=["Incoming"])) == 4
    assert len(filter_transactions(frame, directions=["Unclassified"])) == 1
    assert len(filter_transactions(frame, directions=["Outgoing", "Unclassified"])) == 3
    assert len(filter_transactions(frame, currencies=["USD"])) == 7
    assert len(filter_transactions(frame, currencies=["SOS"])) == 0
    assert len(filter_transactions(frame, text="nobody")) == 0


def test_display_frame_formats(loaded_manager):
    view = frame_for_display(loaded_manager.load_frame())
    assert list(view.columns)[:4] == ["ID", "No.", "Date", "Direction"]
    assert "Unclassified" in view["Direction"].tolist()
    assert view["Amount (USD)"].sum() == pytest.approx(700.70)
