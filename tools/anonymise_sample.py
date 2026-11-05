"""Replace personal data in the sample workbook with clearly synthetic values.

Keeps everything else: sheet layout, formulas (local-currency column, totals,
dashboard), number formats, data validations, column widths, dates, amounts,
currencies and the repeat-transfer scenarios (the same real person is always
mapped to the same synthetic person, so duplicates stay duplicates).

Usage:  python tools/anonymise_sample.py [workbook.xlsx]
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "sample_data" / "Daily_Money_Transfer_Manager 2026.xlsx"

# Column letters in the Transactions sheet.
SENDER, MOBILE, RECEIVER, ACCOUNT, NOTES = "D", "E", "F", "G", "L"


class Mapper:
    def __init__(self) -> None:
        self.people: dict[str, str] = {}
        self.phones: dict[str, str] = {}
        self.accounts: dict[str, str] = {}

    def person(self, value: str) -> str:
        key = value.strip()
        if key not in self.people:
            self.people[key] = f"Demo Person {len(self.people) + 1:02d}"
        return self.people[key]

    def phone(self, value: str) -> str:
        key = value.strip()
        if key not in self.phones:
            n = len(self.phones) + 1
            # +252 000 000 0NN is not an allocatable number; keep the "+" style of the original.
            self.phones[key] = f"+25200000000{n}" if key.startswith("+") else f"25200000000{n}"
        return self.phones[key]

    def account(self, value: str) -> str:
        key = value.strip()
        if key not in self.accounts:
            # all-zero prefix with a leading zero: obviously synthetic, still exercises leading-zero handling
            self.accounts[key] = f"{len(self.accounts) + 1:09d}"
        return self.accounts[key]


def anonymise(path: Path) -> dict:
    wb = openpyxl.load_workbook(path)
    ws = wb["Transactions"]
    m = Mapper()
    changed = 0
    for row in range(2, ws.max_row + 1):
        if ws[f"{SENDER}{row}"].value is None and ws[f"{RECEIVER}{row}"].value is None:
            continue
        for col, fn in ((SENDER, m.person), (RECEIVER, m.person), (MOBILE, m.phone), (ACCOUNT, m.account)):
            cell = ws[f"{col}{row}"]
            if cell.value not in (None, ""):
                cell.value = fn(str(cell.value))
                changed += 1
        if ws[f"{NOTES}{row}"].value not in (None, ""):
            ws[f"{NOTES}{row}"].value = "sample note"
            changed += 1
    wb.save(path)
    return {"people": len(m.people), "phones": len(m.phones), "accounts": len(m.accounts), "cells": changed}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    print(anonymise(target))
