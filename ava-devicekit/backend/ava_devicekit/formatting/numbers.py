from __future__ import annotations

import math
from typing import Any

SCI_SIGNIFICANT_DIGITS = 3
SCI_DECIMALS = SCI_SIGNIFICANT_DIGITS - 1
NORMAL_MAX_CHARS = 8
SCI_SMALL_THRESHOLD = 0.0001
SCI_LARGE_THRESHOLD = 100_000_000


def parse_number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    for char in ("$", ",", "%"):
        text = text.replace(char, "")
    for suffix in ("T", "t", "B", "b", "M", "m", "K", "k"):
        if text.endswith(suffix):
            try:
                base = float(text[:-1].strip() or "0")
            except ValueError:
                return default
            mult = {
                "t": 1_000_000_000_000,
                "b": 1_000_000_000,
                "m": 1_000_000,
                "k": 1_000,
            }[suffix.lower()]
            return base * mult
    try:
        return float(text)
    except ValueError:
        return default


def _trim_decimal(text: str) -> str:
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    return text


def _format_scientific(number: float) -> str:
    if number == 0:
        return "0"
    sign = "-" if number < 0 else ""
    number = abs(number)
    exponent = int(math.floor(math.log10(number)))
    mantissa = number / (10**exponent)
    mantissa = round(mantissa, SCI_DECIMALS)
    if mantissa >= 10:
        mantissa /= 10
        exponent += 1
    return f"{sign}{mantissa:.{SCI_DECIMALS}f}e{exponent}"


def _normal_decimals(abs_number: float) -> int:
    if abs_number >= 1_000_000:
        return 0
    if abs_number >= 1_000:
        return 0
    if abs_number >= 100:
        return 1
    if abs_number >= 1:
        return 2
    if abs_number >= 0.01:
        return 4
    return 6


def _format_normal(number: float, *, max_chars: int = NORMAL_MAX_CHARS) -> str:
    if number == 0:
        return "0"
    abs_number = abs(number)
    if abs_number < SCI_SMALL_THRESHOLD or abs_number >= SCI_LARGE_THRESHOLD:
        return _format_scientific(number)

    decimals = _normal_decimals(abs_number)
    text = _trim_decimal(f"{number:.{decimals}f}")
    if len(text) <= max_chars:
        return text

    # Reduce fractional precision first. Only fall back to scientific when a
    # normal fixed representation cannot fit the small-screen budget.
    for decimals in range(decimals - 1, -1, -1):
        text = _trim_decimal(f"{number:.{decimals}f}")
        if len(text) <= max_chars:
            return text
    return _format_scientific(number)


def _format_compact(number: float, *, max_chars: int = NORMAL_MAX_CHARS) -> str:
    if number == 0:
        return "0"
    sign = "-" if number < 0 else ""
    abs_number = abs(number)
    for suffix, divisor in (("T", 1_000_000_000_000), ("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if abs_number >= divisor:
            value = abs_number / divisor
            for decimals in (1, 0):
                text = f"{sign}{_trim_decimal(f'{value:.{decimals}f}')}{suffix}"
                if len(text) <= max_chars:
                    return text
            return _format_scientific(number)
    return _format_normal(number, max_chars=max_chars)


def format_number(value: Any, *, zero: str = "0", max_chars: int = NORMAL_MAX_CHARS) -> str:
    number = parse_number(value, default=math.nan)
    if math.isnan(number) or math.isinf(number):
        return "N/A"
    if number == 0:
        return zero
    return _format_normal(number, max_chars=max_chars)


def format_money(value: Any, *, max_chars: int = NORMAL_MAX_CHARS) -> str:
    text = format_number(value, max_chars=max_chars)
    if text == "N/A":
        return text
    if text.startswith("-"):
        return "-$" + text[1:]
    return "$" + text


def format_compact_money(value: Any, *, max_chars: int = NORMAL_MAX_CHARS) -> str:
    number = parse_number(value, default=math.nan)
    if math.isnan(number) or math.isinf(number):
        return "N/A"
    text = _format_compact(number, max_chars=max_chars)
    if text.startswith("-"):
        return "-$" + text[1:]
    return "$" + text


def format_percent(value: Any, *, signed: bool = True, max_chars: int = NORMAL_MAX_CHARS) -> str:
    number = parse_number(value, default=math.nan)
    if math.isnan(number) or math.isinf(number):
        return "N/A"
    sign = "+" if signed and number >= 0 else ""
    text = _format_normal(number, max_chars=max(1, max_chars - len(sign) - 1))
    result = f"{sign}{text}%"
    if len(result) <= max_chars + 2:
        return result
    return f"{sign}{_format_scientific(number)}%"


def format_count(value: Any, *, max_chars: int = NORMAL_MAX_CHARS) -> str:
    number = parse_number(value, default=math.nan)
    if math.isnan(number) or math.isinf(number) or number < 0:
        return "N/A"
    return _format_compact(number, max_chars=max_chars)
