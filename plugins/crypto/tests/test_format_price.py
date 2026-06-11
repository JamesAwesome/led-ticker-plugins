from led_ticker_crypto._ticker_render import (
    FONT_VALUE,
    FONT_VALUE_SMALL,
    _format_price,
    _get_price_font,
)


def test_normal_price_keeps_four_decimals():
    assert _format_price(50000.1234) == "50,000.1234"
    assert _format_price(3000.5) == "3,000.5000"


def test_value_at_one_uses_four_decimals():
    assert _format_price(1.0) == "1.0000"


def test_sub_cent_shows_significant_figures_not_zero():
    s = _format_price(4.64e-06)
    assert s not in ("0.0000", "0")
    assert float(s.replace(",", "")) > 0
    assert "4640" in s.replace(".", "").replace(",", "")


def test_zero_is_zeroed():
    assert _format_price(0.0) == "0.0000"


def test_small_but_above_one_cent():
    assert _format_price(0.1234) == "0.1234"


# ---------------------------------------------------------------------------
# Boundary cases added by Phase-3 review
# ---------------------------------------------------------------------------

def test_sub_dollar_just_below_one():
    # 0.9999 < 1 → sub-dollar path: log10(0.9999) ≈ -4.3e-5, floor = -1,
    # decimals = 3 - (-1) = 4 → "0.9999"
    assert _format_price(0.9999) == "0.9999"


def test_sub_dollar_half():
    # 0.5 < 1 → sub-dollar path: log10(0.5) ≈ -0.301, floor = -1,
    # decimals = 4 → "0.5000"
    assert _format_price(0.5) == "0.5000"


def test_sub_dollar_just_below_one_rounds_up():
    # 0.999999 < 1 → 4 decimals; Python rounds to "1.0000"
    # (the >= 1 branch would also give 4 decimals, so the result is the same
    # from a user perspective — just confirm no crash and the exact output)
    assert _format_price(0.999999) == "1.0000"


def test_large_value_thousands_separated():
    # >= 1 branch: 4 decimals with thousands separator
    assert _format_price(1234567.89) == "1,234,567.8900"


# ---------------------------------------------------------------------------
# _get_price_font boundary: FONT_VALUE when len <= 10, FONT_VALUE_SMALL when > 10
# ---------------------------------------------------------------------------

def test_price_font_boundary_at_ten_chars():
    # "1234567890" is exactly 10 chars → FONT_VALUE
    assert len("1234567890") == 10
    assert _get_price_font("1234567890") is FONT_VALUE


def test_price_font_boundary_at_eleven_chars():
    # "12345678901" is exactly 11 chars → FONT_VALUE_SMALL
    assert len("12345678901") == 11
    assert _get_price_font("12345678901") is FONT_VALUE_SMALL
