"""Print the CHANGELOG.md section for one version (used by the release workflow).

Usage:  python tools/release_notes.py v1.0.0
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def section_for(version: str, text: str) -> str:
    version = version.lstrip("v").strip()
    pattern = re.compile(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", re.S | re.M)
    match = pattern.search(text)
    if not match:
        return f"Release {version}.\n\nSee CHANGELOG.md for details."
    body = match.group(1).strip()
    return body or f"Release {version}."


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    notes = section_for(sys.argv[1], CHANGELOG.read_text(encoding="utf-8"))
    checks = ("\n\n**Verify your download** with the SHA-256 values in `SHA256SUMS.txt` "
              "(`Get-FileHash -Algorithm SHA256 DailyMoneyTransferManager-Setup.exe` in PowerShell).")
    sys.stdout.write(notes + checks + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
