"""Central configuration for the Daily Money Transfer Manager.

Everything that other modules might need to agree on (paths, column names,
allowed values, numeric precision) lives here so it is defined exactly once.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_TITLE = "Daily Money Transfer Manager 2026"
APP_SHORT_TITLE = "Transfer Manager"
APP_VERSION = "1.0.0"
APP_PUBLISHER = "Daily Money Transfer Manager"
# Folder name used under %LOCALAPPDATA% for the installed desktop application.
APP_DATA_FOLDER_NAME = "DailyMoneyTransferManager"

# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
# Three layouts are supported and chosen automatically:
#
#   * Development (``streamlit run app.py``): everything lives in the project
#     folder - data/, exports/ - exactly as before.
#   * Installed desktop application (PyInstaller bundle): read-only program
#     files sit next to the executable; all user data goes to
#     %LOCALAPPDATA%\DailyMoneyTransferManager so it survives updates and is
#     never written inside the (replaceable) program folder.
#   * Portable desktop application: a ``portable.txt`` marker next to the
#     executable keeps the data in a ``data`` folder beside it (USB stick use).
#
# ``DMTM_DATA_DIR`` overrides the data folder and ``DMTM_DB_PATH`` overrides
# the database file (the automated tests use the latter).
IS_FROZEN = bool(getattr(sys, "frozen", False))
PROJECT_DIR = Path(__file__).resolve().parent
# Where bundled, read-only resources (app.py, .streamlit/, sample_data/) live.
BASE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))
EXECUTABLE_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else PROJECT_DIR
PORTABLE_MARKER = EXECUTABLE_DIR / "portable.txt"
IS_PORTABLE = IS_FROZEN and PORTABLE_MARKER.exists()


def _windows_local_appdata() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base)
    return Path.home() / "AppData" / "Local"


def _resolve_data_dir() -> Path:
    override = os.environ.get("DMTM_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if IS_PORTABLE:
        return EXECUTABLE_DIR / "data"
    if IS_FROZEN:
        return _windows_local_appdata() / APP_DATA_FOLDER_NAME
    return PROJECT_DIR / "data"


DATA_DIR = _resolve_data_dir()
# In development the export folder stays at the project root (unchanged
# behaviour); in every other layout it sits inside the data folder.
_DEV_LAYOUT = DATA_DIR == PROJECT_DIR / "data"
EXPORT_DIR = PROJECT_DIR / "exports" if _DEV_LAYOUT else DATA_DIR / "exports"
EXCEL_EXPORT_DIR = EXPORT_DIR / "excel"
REPORT_EXPORT_DIR = EXPORT_DIR / "reports"
BACKUP_DIR = DATA_DIR / "backups"
LOG_DIR = DATA_DIR / "logs"
SAMPLE_DATA_DIR = BASE_DIR / "sample_data"

# The database location can be overridden with an environment variable, which
# is how the automated tests point the application at a throw-away database.
DB_PATH = Path(os.environ.get("DMTM_DB_PATH", str(DATA_DIR / "database.db")))

# ---------------------------------------------------------------------------
# Excel structure
# ---------------------------------------------------------------------------
TRANSACTIONS_SHEET_NAME = "Transactions"
SUPPORTED_EXCEL_EXTENSIONS = (".xlsx", ".xlsm", ".xls")

# Canonical column keys used throughout the code base, in workbook order.
# "aliases" are normalised header spellings (lower-case, alphanumerics only)
# that the importer will accept for the column.
COLUMN_SPECS: list[dict] = [
    {"key": "txn_no", "header": "No.", "required": False,
     "aliases": ("no", "number", "sno", "serial", "id", "txnno", "transactionno")},
    {"key": "txn_date", "header": "Date", "required": True,
     "aliases": ("date", "transactiondate", "transferdate", "txndate")},
    {"key": "direction", "header": "Direction", "required": False,
     "aliases": ("direction", "type", "inout", "flow")},
    {"key": "sender_name", "header": "Sender Name", "required": True,
     "aliases": ("sendername", "sender", "from", "fromname", "payer")},
    {"key": "sender_mobile", "header": "Sender Mobile", "required": False,
     "aliases": ("sendermobile", "mobile", "senderphone", "phone", "sendertel", "mobilenumber")},
    {"key": "receiver_name", "header": "Receiver Name", "required": True,
     "aliases": ("receivername", "receiver", "to", "toname", "beneficiary", "payee")},
    {"key": "account_number", "header": "Account Number", "required": False,
     "aliases": ("accountnumber", "account", "accountno", "receiveraccount", "acc")},
    {"key": "currency", "header": "Currency", "required": False,
     "aliases": ("currency", "ccy", "cur")},
    {"key": "amount_usd", "header": "Amount (USD)", "required": True,
     "aliases": ("amountusd", "amount", "usd", "usdamount", "amountinusd")},
    {"key": "exchange_rate", "header": "Exchange Rate", "required": False,
     "aliases": ("exchangerate", "rate", "fxrate", "fx")},
    {"key": "amount_local", "header": "Amount in Local Currency", "required": False,
     "aliases": ("amountinlocalcurrency", "amountlocal", "localamount", "localcurrencyamount", "amountlocalcurrency")},
    {"key": "notes", "header": "Reference / Notes", "required": False,
     "aliases": ("referencenotes", "reference", "notes", "note", "remarks", "ref", "description", "comment")},
]
COLUMN_KEYS = [spec["key"] for spec in COLUMN_SPECS]
COLUMN_HEADERS = {spec["key"]: spec["header"] for spec in COLUMN_SPECS}
REQUIRED_COLUMN_KEYS = [spec["key"] for spec in COLUMN_SPECS if spec["required"]]

# ---------------------------------------------------------------------------
# Business rules
# ---------------------------------------------------------------------------
DIRECTION_INCOMING = "Incoming"
DIRECTION_OUTGOING = "Outgoing"
DIRECTIONS = (DIRECTION_INCOMING, DIRECTION_OUTGOING)
UNCLASSIFIED_LABEL = "Unclassified"

DEFAULT_CURRENCIES = ("USD", "SOS")

# Amounts in USD are kept to cents; exchange rates may carry more precision.
AMOUNT_DECIMALS = 2
RATE_DECIMALS = 6
# Dates further ahead than this produce a warning (not an error).
FUTURE_DATE_WARNING_DAYS = 1
# Excel serial dates are only accepted inside this window (1980-01-01 .. 2100).
EXCEL_SERIAL_MIN = 29221
EXCEL_SERIAL_MAX = 73415

DEFAULT_SETTINGS: dict[str, str] = {
    "office_name": "Money Transfer Office",
    "local_currency_code": "SOS",
    "allow_negative_amounts": "0",
    "default_exchange_rate": "",
}

# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------
# Chart colours (validated with the data-viz palette checker in light mode).
COLOR_INCOMING = "#1baf7a"
COLOR_OUTGOING = "#eb6834"
COLOR_UNCLASSIFIED = "#8a8884"
COLOR_NET = "#2a78d6"
COLOR_SURFACE = "#fcfcfb"
