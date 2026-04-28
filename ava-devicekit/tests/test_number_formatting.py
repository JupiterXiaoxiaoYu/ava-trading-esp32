from ava_devicekit.formatting.numbers import (
    format_compact_money,
    format_count,
    format_money,
    format_number,
    format_percent,
    parse_number,
)


def test_numeric_policy_uses_fixed_until_screen_threshold():
    assert format_number(0) == "0"
    assert format_number(12.34) == "12.34"
    assert format_number(0.123456) == "0.1235"
    assert format_number(-0.00007956) == "-7.96e-5"
    assert format_number(123456789) == "1.23e8"
    assert format_money(-0.00007956) == "-$7.96e-5"
    assert format_money(999) == "$999"
    assert format_percent(1.5) == "+1.5%"
    assert format_percent(-74.7345) == "-74.73%"


def test_compact_count_and_volume_policy():
    assert format_count("12345") == "12.3K"
    assert format_count("1234567") == "1.2M"
    assert format_compact_money("1490000") == "$1.5M"
    assert format_compact_money("404000") == "$404K"


def test_parse_number_accepts_previous_compact_units():
    assert parse_number("$1.2M") == 1_200_000
    assert parse_number("-$7.96e-5") == -7.96e-5
