"""Precision-safe money helpers.

All financial arithmetic in the application goes through ``decimal.Decimal``.
USD amounts are stored in the database as integer cents so that SQL sums are
exact and sorting works; these helpers convert between the two representations
and parse user / spreadsheet input safely.
"""
from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from config import AMOUNT_DECIMALS, RATE_DECIMALS

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
_RATE_QUANTUM = Decimal(1).scaleb(-RATE_DECIMALS)
# Float noise smaller than this is treated as a representation artefact rather
# than genuine extra precision (e.g. 126.25000000000001 from a spreadsheet).
_FLOAT_NOISE = Decimal("1e-7")
_STRIP_CHARS = re.compile(r"[,\s$]|USD|usd", re.UNICODE)


class MoneyError(ValueError):
    """Raised when a value cannot be interpreted as a monetary number."""


def is_blank(value: Any) -> bool:
    """True for None, NaN/NA and empty or whitespace-only strings."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("", "nan", "none", "nat", "null")
    if isinstance(value, float) and math.isnan(value):
        return True
    try:  # pandas.NA / pandas.NaT without importing pandas here
        import pandas as pd  # noqa: WPS433 (local import keeps module light)

        if value is pd.NA or value is pd.NaT:
            return True
    except Exception:  # pragma: no cover - defensive
        pass
    return False


def to_decimal(value: Any) -> Decimal | None:
    """Parse ``value`` into a Decimal without going through float arithmetic.

    Returns ``None`` for blank input. Raises :class:`MoneyError` for anything
    that is not a number (including booleans).
    """
    if is_blank(value):
        return None
    if isinstance(value, bool):
        raise MoneyError("a true/false value is not a number")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        if math.isinf(value):
            raise MoneyError("infinite value")
        result = Decimal(repr(value))
    else:
        text = _STRIP_CHARS.sub("", str(value))
        if text in ("", "-", "+"):
            return None
        try:
            result = Decimal(text)
        except InvalidOperation as exc:
            raise MoneyError(f"'{value}' is not a number") from exc
    if not result.is_finite():
        raise MoneyError(f"'{value}' is not a finite number")
    return result


def quantize_money(value: Decimal) -> Decimal:
    """Round to cents using banker-free HALF_UP rounding."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def quantize_rate(value: Decimal) -> Decimal:
    """Normalise an exchange rate to at most RATE_DECIMALS decimals."""
    return value.quantize(_RATE_QUANTUM, rounding=ROUND_HALF_UP).normalize() if value != 0 else Decimal(0)


def parse_amount(value: Any) -> Decimal | None:
    """Parse a USD amount and enforce the two-decimal rule.

    Values with more than two genuine decimals are rejected (we never round
    financial input silently); tiny float artefacts are tolerated.
    """
    number = to_decimal(value)
    if number is None:
        return None
    quantized = quantize_money(number)
    if quantized != number and abs(number - quantized) > _FLOAT_NOISE:
        raise MoneyError(
            f"amount {number} has more than {AMOUNT_DECIMALS} decimal places"
        )
    return quantized


def parse_rate(value: Any) -> Decimal | None:
    """Parse an exchange rate (must be positive, max RATE_DECIMALS decimals)."""
    number = to_decimal(value)
    if number is None:
        return None
    if number <= 0:
        raise MoneyError("exchange rate must be greater than zero")
    rounded = number.quantize(_RATE_QUANTUM, rounding=ROUND_HALF_UP)
    if rounded != number and abs(number - rounded) > _FLOAT_NOISE:
        raise MoneyError(
            f"exchange rate {number} has more than {RATE_DECIMALS} decimal places"
        )
    return rounded.normalize() if rounded == rounded.to_integral() else rounded


def decimal_to_cents(value: Decimal) -> int:
    """Convert a two-decimal USD amount into integer cents (exact)."""
    return int(quantize_money(value) * 100)


def cents_to_decimal(cents: int | None) -> Decimal:
    """Convert integer cents back into a two-decimal Decimal."""
    if cents is None:
        return ZERO
    return (Decimal(int(cents)) / 100).quantize(CENT)


def local_amount(amount_usd: Decimal | None, rate: Decimal | None) -> Decimal | None:
    """Amount in local currency = USD amount x exchange rate, rounded to cents."""
    if amount_usd is None or rate is None:
        return None
    return quantize_money(amount_usd * rate)


def format_usd(value: Decimal | int | None, *, cents: bool = False) -> str:
    """Format as ``$1,234.56``; negative values as ``-$1,234.56``."""
    if value is None:
        return "—"
    amount = cents_to_decimal(value) if cents else quantize_money(Decimal(value))
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def format_number(value: Decimal | None, decimals: int = 2) -> str:
    if value is None:
        return "—"
    return f"{Decimal(value):,.{decimals}f}"


def decimal_str(value: Decimal | None) -> str | None:
    """Canonical string form for storing a Decimal in SQLite TEXT columns."""
    if value is None:
        return None
    return format(value, "f")
