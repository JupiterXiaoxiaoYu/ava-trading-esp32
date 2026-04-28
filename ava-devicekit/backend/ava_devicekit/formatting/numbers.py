from __future__ import annotations

import math
from typing import Any

SIGNIFICANT_DIGITS = 3
MANTISSA_DECIMALS = SIGNIFICANT_DIGITS - 1


def parse_number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    for char in ("$", ",", "%"):
        text = text.replace(char, "")
    for suffix in ("B", "b", "M", "m", "K", "k"):
        if text.endswith(suffix):
            try:
                base = float(text[:-1].strip() or "0")
            except ValueError:
                return default
            mult = {"b": 1_000_000_000, "m": 1_000_000, "k": 1_000}[suffix.lower()]
            return base * mult
    try:
        return float(text)
    except ValueError:
        return default


def format_number(value: Any, *, zero: str = "0") -> str:
    number = parse_number(value, default=math.nan)
    if math.isnan(number) or math.isinf(number):
        return "N/A"
    if number == 0:
        return zero
    sign = "-" if number < 0 else ""
    number = abs(number)
    exponent = int(math.floor(math.log10(number)))
    mantissa = number / (10**exponent)
    # Rounding 9.995 -> 10.00 would break scientific notation; normalize it.
    mantissa = round(mantissa, MANTISSA_DECIMALS)
    if mantissa >= 10:
        mantissa /= 10
        exponent += 1
    return f"{sign}{mantissa:.{MANTISSA_DECIMALS}f}e{exponent}"


def format_money(value: Any) -> str:
    text = format_number(value)
    if text.startswith("-"):
        return "-$" + text[1:]
    return "$" + text


def format_percent(value: Any, *, signed: bool = True) -> str:
    number = parse_number(value, default=math.nan)
    if math.isnan(number) or math.isinf(number):
        return "N/A"
    sign = "+" if signed and number >= 0 else ""
    return f"{sign}{format_number(number)}%"


def format_count(value: Any) -> str:
    number = parse_number(value, default=math.nan)
    if math.isnan(number) or math.isinf(number) or number < 0:
        return "N/A"
    return format_number(number)
