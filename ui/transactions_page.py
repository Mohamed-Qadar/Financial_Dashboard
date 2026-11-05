"""Transaction management: browse/search, classify, add, edit and delete."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import streamlit as st

from config import DEFAULT_CURRENCIES, DIRECTIONS, UNCLASSIFIED_LABEL
from core import calculations as calc
from core.data_validator import ValidationError
from core.money import cents_to_decimal
from core.transaction_manager import SEARCH_FIELDS, filter_transactions, frame_for_display
from ui.common import (
    cards_row,
    display_table,
    empty_state,
    get_manager,
    load_transactions,
    metric_card,
    money,
    money_md,
    page_header,
    section,
    settings,
)

_DIRECTION_OPTIONS = [UNCLASSIFIED_LABEL, *DIRECTIONS]


def _currency_options(frame: pd.DataFrame, cfg: dict) -> list[str]:
    options = list(DEFAULT_CURRENCIES)
    if cfg.get("local_currency_code"):
        options.append(cfg["local_currency_code"].upper())
    if not frame.empty:
        options += [c for c in frame["currency"].dropna().unique().tolist()]
    seen: list[str] = []
    for item in options:
        if item and item not in seen:
            seen.append(item)
    return seen


def _parse_date_value(value) -> date:
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


# --------------------------------------------------------------------------
# Browse & search
# --------------------------------------------------------------------------
def _browse(frame: pd.DataFrame, cfg: dict) -> None:
    section("Search and filter")
    c1, c2 = st.columns([3, 1.4])
    text = c1.text_input("Search", placeholder="Name, mobile number, account number or reference...")
    field = c2.selectbox("Search in", list(SEARCH_FIELDS.keys()))
    c3, c4, c5, c6 = st.columns([1.3, 1.3, 1.6, 1.4])
    min_date = _parse_date_value(frame["txn_date"].min())
    max_date = _parse_date_value(frame["txn_date"].max())
    use_dates = c3.toggle("Filter by date", value=False)
    date_range = c4.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date,
                               disabled=not use_dates)
    directions = c5.multiselect("Direction", _DIRECTION_OPTIONS, default=[])
    currencies = c6.multiselect("Currency", _currency_options(frame, cfg) + ["(blank)"], default=[])

    date_from = date_to = None
    if use_dates:
        if isinstance(date_range, tuple) and len(date_range) == 2:
            date_from, date_to = date_range
        elif isinstance(date_range, tuple) and len(date_range) == 1:
            date_from = date_to = date_range[0]
        else:
            date_from = date_to = date_range

    result = filter_transactions(frame, text=text, field=field, date_from=date_from, date_to=date_to,
                                 directions=directions, currencies=currencies)
    totals = calc.compute_totals(result)
    cards_row([
        metric_card("Matching transactions", f"{totals.total_count:,}", f"of {len(frame):,} total"),
        metric_card("Incoming (USD)", money(totals.total_incoming), f"{totals.incoming_count} transfers", tone="income"),
        metric_card("Outgoing (USD)", money(totals.total_outgoing), f"{totals.outgoing_count} transfers", tone="expense"),
        metric_card("Net (USD)", money(totals.net_balance), f"{totals.unclassified_count} unclassified excluded",
                    tone="net", negative=totals.net_balance < 0),
    ])
    st.write("")
    ordered = result.sort_values(["txn_date", "id"], ascending=[False, False])
    display_table(frame_for_display(ordered), height=min(600, 60 + 35 * max(len(ordered), 1)))


# --------------------------------------------------------------------------
# Classify
# --------------------------------------------------------------------------
def _classify(frame: pd.DataFrame, manager) -> None:
    section("Assign Incoming / Outgoing",
            "Directions are never guessed. Choose a value for each transfer, then save.")
    show_all = st.toggle("Show already classified transactions too", value=False)
    subset = frame if show_all else frame[frame["direction"].isna()]
    if subset.empty:
        st.success("Every transaction has a direction. Nothing to classify.", icon=":material/check_circle:")
        return

    editor_df = pd.DataFrame({
        "ID": subset["id"].to_numpy(),
        "Date": subset["txn_date"].to_numpy(),
        "Sender Name": subset["sender_name"].to_numpy(),
        "Receiver Name": subset["receiver_name"].to_numpy(),
        "Account Number": [v or "" for v in subset["account_number"].tolist()],
        "Amount (USD)": subset["amount_cents"].to_numpy(dtype="int64") / 100.0,
        "Direction": pd.array([d if d else pd.NA for d in subset["direction"].tolist()], dtype="string"),
        "Reference / Notes": [v or "" for v in subset["notes"].tolist()],
    }).sort_values(["Date", "ID"]).reset_index(drop=True)

    st.caption(f"{len(editor_df)} transaction(s) listed. Pick a direction in the **Direction** column.")
    edited = st.data_editor(
        editor_df,
        hide_index=True,
        width="stretch",
        num_rows="fixed",
        disabled=["ID", "Date", "Sender Name", "Receiver Name", "Account Number", "Amount (USD)", "Reference / Notes"],
        column_config={
            "ID": st.column_config.NumberColumn(width="small", format="%d"),
            "Amount (USD)": st.column_config.NumberColumn(format="dollar"),
            "Direction": st.column_config.SelectboxColumn("Direction", options=list(DIRECTIONS), required=False,
                                                          help="Incoming = money received by you; Outgoing = money sent."),
        },
        key="classify_editor",
    )

    changes: dict[int, str | None] = {}
    for original, new in zip(editor_df.to_dict("records"), edited.to_dict("records")):
        before = original["Direction"] if isinstance(original["Direction"], str) else None
        after = new["Direction"] if isinstance(new["Direction"], str) and new["Direction"] in DIRECTIONS else None
        if before != after:
            changes[int(original["ID"])] = after

    col1, col2, col3 = st.columns([1.6, 1.6, 3])
    if col1.button(f"Save {len(changes)} change(s)", type="primary", disabled=not changes, icon=":material/save:"):
        updated = manager.apply_classifications(changes)
        st.success(f"Updated {updated} transaction(s).", icon=":material/check_circle:")
        st.rerun()
    with col2.popover("Bulk assign all listed", icon=":material/done_all:", disabled=subset.empty):
        st.write(f"Set the direction of **all {len(subset)} listed** transactions.")
        bulk = st.radio("Direction", list(DIRECTIONS), horizontal=True, key="bulk_direction")
        st.caption("Only do this if you are certain every listed transfer has the same direction.")
        if st.button(f"Apply '{bulk}' to {len(subset)} transaction(s)", key="bulk_apply"):
            manager.set_direction(subset["id"].tolist(), bulk)
            st.rerun()
    col3.caption("Unsaved edits are highlighted in the table until you click Save.")


# --------------------------------------------------------------------------
# Add / edit form
# --------------------------------------------------------------------------
def _transaction_form(key: str, cfg: dict, frame: pd.DataFrame, initial: dict | None = None) -> dict | None:
    initial = initial or {}
    currencies = _currency_options(frame, cfg)
    with st.form(key=key, clear_on_submit=False, border=True):
        c1, c2, c3 = st.columns(3)
        txn_no = c1.text_input("No.", value="" if initial.get("txn_no") in (None, "") else str(initial["txn_no"]),
                               help="Optional sequence number as used in the workbook.")
        initial_date = initial.get("txn_date")
        txn_date = c2.date_input("Date", value=_parse_date_value(initial_date) if initial_date else date.today())
        direction_default = initial.get("direction") or UNCLASSIFIED_LABEL
        direction = c3.selectbox("Direction", _DIRECTION_OPTIONS, index=_DIRECTION_OPTIONS.index(direction_default),
                                 help="Leave as Unclassified if you are not certain.")
        c4, c5 = st.columns(2)
        sender_name = c4.text_input("Sender Name *", value=initial.get("sender_name") or "")
        sender_mobile = c5.text_input("Sender Mobile", value=initial.get("sender_mobile") or "",
                                      help="Stored as text so leading zeros and '+' are kept.")
        c6, c7 = st.columns(2)
        receiver_name = c6.text_input("Receiver Name *", value=initial.get("receiver_name") or "")
        account_number = c7.text_input("Account Number", value=initial.get("account_number") or "")
        c8, c9, c10 = st.columns(3)
        currency_default = (initial.get("currency") or "USD").upper()
        if currency_default not in currencies:
            currencies = [currency_default] + currencies
        currency = c8.selectbox("Currency", currencies, index=currencies.index(currency_default),
                                accept_new_options=True)
        amount_initial = initial.get("amount_usd")
        amount_usd = c9.text_input("Amount (USD) *", value="" if amount_initial in (None, "") else str(amount_initial),
                                   placeholder="e.g. 150.00")
        rate_initial = initial.get("exchange_rate") or cfg.get("default_exchange_rate") or ""
        exchange_rate = c10.text_input("Exchange Rate", value=str(rate_initial),
                                       help="Local currency units per 1 USD. Optional.")
        notes = st.text_input("Reference / Notes", value=initial.get("notes") or "")
        submitted = st.form_submit_button("Save transaction", type="primary", icon=":material/save:")
    if not submitted:
        return None
    return {
        "txn_no": txn_no.strip() or None,
        "txn_date": txn_date,
        "direction": None if direction == UNCLASSIFIED_LABEL else direction,
        "sender_name": sender_name,
        "sender_mobile": sender_mobile,
        "receiver_name": receiver_name,
        "account_number": account_number,
        "currency": currency,
        "amount_usd": amount_usd,
        "exchange_rate": exchange_rate,
        "amount_local": None,
        "notes": notes,
    }


def _add(frame: pd.DataFrame, manager, cfg: dict) -> None:
    section("Add a new transaction", "Fields marked * are required. Amounts use exact decimal arithmetic.")
    if flash := st.session_state.pop("flash", None):
        st.success(flash, icon=":material/check_circle:")
    suggested_no = manager.db.next_txn_no()
    raw = _transaction_form("add_form", cfg, frame, initial={"txn_no": suggested_no})
    if raw is None:
        return
    try:
        new_id = manager.add_transaction(raw)
    except ValidationError as exc:
        for err in exc.errors:
            st.error(err, icon=":material/error:")
        return
    record = manager.get_transaction(new_id)
    st.session_state["flash"] = (f"Transaction #{new_id} saved: {record['sender_name']} -> {record['receiver_name']}, "
                                 f"{money_md(cents_to_decimal(record['amount_cents']))} on {record['txn_date']}.")
    st.rerun()


@st.dialog("Delete transaction")
def _confirm_delete(manager, record: dict) -> None:
    st.write(f"Delete transaction **#{record['id']}**?")
    st.write(f"{record['txn_date']} - {record['sender_name']} -> {record['receiver_name']} - "
             f"{money_md(cents_to_decimal(record['amount_cents']))}")
    st.warning("This cannot be undone.", icon=":material/warning:")
    col1, col2 = st.columns(2)
    if col1.button("Yes, delete", type="primary", width="stretch"):
        manager.delete_transaction(int(record["id"]))
        st.session_state["flash"] = f"Transaction #{record['id']} deleted."
        st.rerun()
    if col2.button("Cancel", width="stretch"):
        st.rerun()


def _edit(frame: pd.DataFrame, manager, cfg: dict) -> None:
    section("Edit or delete a transaction")
    if flash := st.session_state.pop("flash", None):
        st.success(flash, icon=":material/check_circle:")
    options = frame.sort_values(["txn_date", "id"], ascending=[False, False])
    labels = {
        int(r["id"]): f"#{int(r['id'])} | {r['txn_date']} | {r['sender_name']} -> {r['receiver_name']} | "
                      f"{money(cents_to_decimal(r['amount_cents']))} | {r['direction'] or UNCLASSIFIED_LABEL}"
        for r in options.to_dict("records")
    }
    chosen = st.selectbox("Select a transaction", list(labels.keys()), format_func=lambda i: labels[i],
                          index=None, placeholder="Type to search by id, date, name or amount...")
    if chosen is None:
        return
    record = manager.get_transaction(chosen)
    if record is None:
        st.error("That transaction no longer exists.")
        return
    initial = manager.transaction_to_form(record)
    raw = _transaction_form(f"edit_form_{chosen}", cfg, frame, initial=initial)
    if st.button("Delete this transaction", icon=":material/delete:"):
        _confirm_delete(manager, record)
    if raw is None:
        return
    try:
        manager.update_transaction(chosen, raw)
    except ValidationError as exc:
        for err in exc.errors:
            st.error(err, icon=":material/error:")
        return
    st.success(f"Transaction #{chosen} updated.", icon=":material/check_circle:")
    st.rerun()


# --------------------------------------------------------------------------
def render() -> None:
    cfg = settings()
    page_header("Transactions", "View, search, classify, add, edit and delete money transfers.",
                icon=":material/receipt_long:")
    manager = get_manager()
    frame = load_transactions()

    tabs = st.tabs([":material/search: Browse & search", ":material/rule: Classify",
                    ":material/add_circle: Add", ":material/edit: Edit / delete"])
    with tabs[0]:
        if frame.empty:
            empty_state()
        else:
            _browse(frame, cfg)
    with tabs[1]:
        if frame.empty:
            empty_state()
        else:
            _classify(frame, manager)
    with tabs[2]:
        _add(frame, manager, cfg)
    with tabs[3]:
        if frame.empty:
            empty_state()
        else:
            _edit(frame, manager, cfg)
