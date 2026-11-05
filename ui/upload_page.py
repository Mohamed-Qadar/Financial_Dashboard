"""Excel upload, validation preview and confirmed import."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd
import streamlit as st

from config import COLUMN_HEADERS
from core.data_validator import STATUS_DUPLICATE_IN_FILE, STATUS_EXISTS, STATUS_INVALID, STATUS_NEW
from core.excel_reader import ExcelImportError, choose_sheet, file_sha256, list_sheets
from core.money import cents_to_decimal
from ui.common import cards_row, get_manager, load_transactions, metric_card, money_md, page_header, section

_STATE_KEY = "upload_state"
MODE_MERGE = "Merge with existing records"
MODE_REPLACE = "Replace all existing records"


def _reset_state() -> None:
    st.session_state.pop(_STATE_KEY, None)


def _status_style(frame: pd.DataFrame) -> "pd.io.formats.style.Styler":
    def colour(status: str) -> str:
        if status.startswith(STATUS_INVALID):
            return "background-color: #FDE2E1; color: #7f1d1d;"
        if status.startswith(STATUS_EXISTS):
            return "background-color: #EEF0F3; color: #374151;"
        if status.startswith(STATUS_DUPLICATE_IN_FILE):
            return "background-color: #FFF4D6; color: #7c4a03;"
        return "background-color: #E3F7EE; color: #065f46;"

    return frame.style.map(colour, subset=["Status"]).format({"Amount (USD)": "{:,.2f}"}, na_rep="")


def render() -> None:
    page_header("Excel Upload", "Import transfers from the Daily Money Transfer Manager workbook (.xlsx / .xls). "
                "Records are validated and previewed before anything is written. Choose **Merge** to add to what is "
                "already in the system, or **Replace** to start again from this file.", icon=":material/upload_file:")
    manager = get_manager()

    uploaded = st.file_uploader("Choose a workbook", type=["xlsx", "xlsm", "xls"], accept_multiple_files=False,
                                on_change=_reset_state, key="upload_widget")
    if uploaded is None:
        st.info("Select an Excel workbook to begin. The **Transactions** worksheet is detected automatically.",
                icon=":material/info:")
        _render_history(manager)
        return

    data = uploaded.getvalue()
    file_hash = file_sha256(data)
    try:
        sheets = list_sheets(io.BytesIO(data), filename=uploaded.name)
    except ExcelImportError as exc:
        st.error(str(exc), icon=":material/error:")
        return

    try:
        default_sheet = choose_sheet(sheets)
    except ExcelImportError:
        default_sheet = sheets[0]
    sheet = st.selectbox("Worksheet to import", sheets, index=sheets.index(default_sheet),
                         help="The sheet named 'Transactions' is selected automatically when present.")

    previous = manager.previous_imports_of_file(file_hash)
    if previous:
        last = previous[0]
        st.warning(
            f"**This exact file was already imported** on {last['imported_at'][:19].replace('T', ' ')} "
            f"({last['imported_count']} records added). Importing again will only add records that are not "
            "already in the database, unless you explicitly allow duplicates below.",
            icon=":material/history:",
        )

    try:
        read_result = manager.read_excel(io.BytesIO(data), sheet_name=sheet, filename=uploaded.name)
    except ExcelImportError as exc:
        st.error(str(exc), icon=":material/error:")
        return

    mapping = read_result.mapping
    with st.expander(f"Detected structure - sheet '{read_result.sheet_name}', header on row {read_result.header_row}, "
                     f"{read_result.row_count} data rows", expanded=not mapping.is_usable):
        found = pd.DataFrame(
            [{"Application column": COLUMN_HEADERS[k], "Found in file as": v} for k, v in mapping.found.items()]
        )
        st.dataframe(found, hide_index=True, width="stretch")
        if mapping.missing_required:
            st.error("Missing required columns: " + ", ".join(COLUMN_HEADERS[k] for k in mapping.missing_required),
                     icon=":material/error:")
        if mapping.missing_optional:
            st.caption("Optional columns not found: " + ", ".join(COLUMN_HEADERS[k] for k in mapping.missing_optional))
        if mapping.unmapped_headers:
            st.caption("Ignored columns: " + ", ".join(mapping.unmapped_headers))
    if not mapping.is_usable:
        st.stop()

    existing_total = manager.db.count_transactions()
    manual_count = manager.db.count_manual_transactions()
    section("Import mode", "Decide what happens to the records that are already in the system.")
    mode = st.radio(
        "Import mode", [MODE_MERGE, MODE_REPLACE], key="import_mode", label_visibility="collapsed",
        captions=[
            f"Keep all {existing_total:,} existing record(s) - imported or entered by hand - and add only the rows "
            "of this file that are not already in the database.",
            f"Delete all {existing_total:,} existing record(s) first ({manual_count:,} entered manually), "
            "then load this file. The database will contain exactly what this file contains.",
        ],
    )
    replace = mode == MODE_REPLACE

    preview = manager.preview_import(read_result, today=date.today(), replace_existing=replace)

    section("Validation preview", "Nothing has been saved yet. Review the status of every row below.")
    cards_row([
        metric_card("Rows in file", f"{preview.total:,}", f"{len(read_result.skipped_rows)} footer/total rows skipped"),
        metric_card("Ready to import", f"{preview.new_count:,}",
                    "Valid, database will be emptied first" if replace else "Valid, not yet in database",
                    tone="income"),
        metric_card("Already in database", f"{preview.exists_count:,}",
                    "Not applicable in Replace mode" if replace else "Skipped unless allowed"),
        metric_card("Possible duplicates in file", f"{preview.duplicate_in_file_count:,}", "Identical to another row",
                    tone="warn"),
        metric_card("Failed validation", f"{preview.invalid_count:,}", "Will not be imported", tone="expense"),
    ])
    if preview.unclassified_count:
        st.info(f"{preview.unclassified_count} valid row(s) have no Direction. They will be imported as "
                "**Unclassified** and excluded from totals until you classify them.", icon=":material/rule:")
    for warning in preview.column_warnings:
        st.caption(f"- {warning}")

    table = preview.to_frame()
    status_filter = st.multiselect(
        "Show rows with status", [STATUS_NEW, STATUS_INVALID, STATUS_DUPLICATE_IN_FILE, STATUS_EXISTS],
        default=[STATUS_NEW, STATUS_INVALID, STATUS_DUPLICATE_IN_FILE, STATUS_EXISTS],
    )
    shown = table[table["Status"].str.startswith(tuple(status_filter))] if status_filter else table
    st.dataframe(_status_style(shown), hide_index=True, width="stretch", height=min(520, 60 + 35 * max(len(shown), 1)))

    invalid_rows = [r for r in preview.rows if r.status == STATUS_INVALID]
    if invalid_rows:
        with st.expander(f"Why {len(invalid_rows)} row(s) failed"):
            for row in invalid_rows:
                st.markdown(f"- **Row {row.excel_row}**: " + "; ".join(row.errors))

    section("Confirm import")
    col1, col2 = st.columns(2)
    include_dups = col1.checkbox(
        "Import possible in-file duplicates", value=True,
        help="Rows identical to an earlier row of the same file (same date, parties, amount and notes). "
             "Genuine repeat transfers are common, so they are included by default.",
    )
    if replace:
        include_existing = True
        col2.caption("Every existing record is deleted first, so no row can be 'already in the database'.")
    else:
        include_existing = col2.checkbox(
            "Also import rows that already exist in the database (creates duplicates)", value=False,
        )
    selected = preview.importable_rows(include_in_file_duplicates=include_dups, include_existing=include_existing)
    total_cents = sum(int(r.record["amount_cents"]) for r in selected)
    total_text = money_md(cents_to_decimal(total_cents))
    if replace:
        st.error(f"**Replace mode.** All **{existing_total:,}** existing record(s) will be permanently deleted "
                 f"({manual_count:,} of them entered manually), then **{len(selected)}** record(s) totalling "
                 f"**{total_text}** will be loaded from this file. This cannot be undone.", icon=":material/warning:")
        confirmed = st.checkbox(f"I understand that {existing_total:,} existing record(s) will be deleted",
                                key="replace_confirm")
        button_label = f"Replace {existing_total:,} existing record(s) with {len(selected)} from this file"
    else:
        st.markdown(f"**Merge mode.** **{len(selected)} record(s)** totalling **{total_text}** will be added. "
                    f"The {existing_total:,} existing record(s) are kept and never modified by an import.")
        confirmed = True
        button_label = f"Confirm import of {len(selected)} record(s)"

    already_done = st.session_state.get(_STATE_KEY, {}).get("done_hash") == (file_hash, sheet, mode)
    if already_done:
        result = st.session_state[_STATE_KEY]["result"]
        replaced_text = (f"Deleted {result.replaced_existing} existing record(s) first. "
                         if result.replaced_existing else "")
        st.success(f"{replaced_text}Imported {result.imported} record(s) (import #{result.import_id}). "
                   f"Skipped {result.skipped_existing} existing and {result.skipped_in_file_duplicates} in-file "
                   f"duplicate(s); {result.failed} failed validation. {result.unclassified} record(s) are unclassified.",
                   icon=":material/check_circle:")
        st.caption("To import this file again, re-select it in the uploader above.")
    else:
        if st.button(button_label, type="primary", disabled=not selected or not confirmed,
                     icon=":material/delete_sweep:" if replace else ":material/database:"):
            result = manager.commit_import(read_result, preview, include_in_file_duplicates=include_dups,
                                           include_existing=include_existing, replace_existing=replace)
            st.session_state[_STATE_KEY] = {"done_hash": (file_hash, sheet, mode), "result": result}
            load_transactions.clear() if hasattr(load_transactions, "clear") else None
            st.rerun()

    _render_history(manager)


def _render_history(manager) -> None:
    section("Import history")
    history = manager.db.list_imports()
    if history.empty:
        st.caption("No imports yet.")
        return
    view = pd.DataFrame({
        "Import #": history["id"],
        "File": history["filename"],
        "Sheet": history["sheet_name"],
        "Imported at": history["imported_at"].str.slice(0, 19).str.replace("T", " "),
        "Rows in file": history["total_rows"],
        "Imported": history["imported_count"],
        "Skipped (existing)": history["skipped_existing"],
        "Skipped (in-file dup.)": history["skipped_duplicates"],
        "Failed": history["failed_count"],
        "Records still present": history["current_records"],
        "Notes": history["notes"],
    })
    st.dataframe(view, hide_index=True, width="stretch")
