from ava_devicekit.formatting.numbers import format_count, format_money, format_number, format_percent, parse_number


def test_scientific_number_policy_is_consistent():
    assert format_number(0) == "0"
    assert format_number(12.34) == "1.23e1"
    assert format_number(-0.00007956) == "-7.96e-5"
    assert format_number(123456789) == "1.23e8"
    assert format_money(-0.00007956) == "-$7.96e-5"
    assert format_percent(1.5) == "+1.50e0%"
    assert format_count("12345") == "1.23e4"


def test_parse_number_accepts_previous_compact_units():
    assert parse_number("$1.2M") == 1_200_000
    assert parse_number("-$7.96e-5") == -7.96e-5
