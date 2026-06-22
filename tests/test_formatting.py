"""Tests for src/utils/formatting.py"""

from src.utils import formatting


class TestFmt:
    def test_fmt_integer(self):
        result = formatting.fmt(1000)
        assert result == "1,000"

    def test_fmt_integer_with_unit(self):
        result = formatting.fmt(1000, " HP")
        assert result == "1,000 HP"

    def test_fmt_decimal(self):
        result = formatting.fmt(1234.567, decimals=2)
        assert result == "1,234.57"

    def test_fmt_decimal_with_unit(self):
        result = formatting.fmt(1234.567, " HP/s", decimals=2)
        assert result == "1,234.57 HP/s"

    def test_fmt_none_value(self):
        result = formatting.fmt(None)
        assert result == "?"

    def test_fmt_none_with_unit(self):
        result = formatting.fmt(None, " HP")
        assert result == "?"

    def test_fmt_zero(self):
        result = formatting.fmt(0)
        assert result == "0"

    def test_fmt_negative(self):
        result = formatting.fmt(-1000)
        assert result == "-1,000"

    def test_fmt_negative_with_unit(self):
        result = formatting.fmt(-1000, " HP/s")
        assert result == "-1,000 HP/s"

    def test_fmt_string_numeric(self):
        result = formatting.fmt("1000")
        assert result == "1,000"

    def test_fmt_string_numeric_decimal(self):
        result = formatting.fmt("1234.567", decimals=2)
        assert result == "1,234.57"

    def test_fmt_invalid_string(self):
        result = formatting.fmt("not a number")
        assert result == "not a number"

    def test_fmt_rounds_to_integer(self):
        result = formatting.fmt(1234.7)
        assert result == "1,235"

    def test_fmt_large_number(self):
        result = formatting.fmt(1_000_000)
        assert result == "1,000,000"

    def test_fmt_very_small_decimal(self):
        result = formatting.fmt(0.00123, decimals=5)
        assert result == "0.00123"


class TestConstants:
    def test_overheat_placeholder(self):
        assert formatting.OVERHEAT_PLACEHOLDER == 450_000

    def test_null_uuid(self):
        assert formatting.NULL_UUID == "00000000-0000-0000-0000-000000000000"
        assert len(formatting.NULL_UUID) == 36
        assert formatting.NULL_UUID.count("-") == 4
