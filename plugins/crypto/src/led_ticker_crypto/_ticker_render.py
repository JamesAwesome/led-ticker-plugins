"""Shared price-ticker renderer for crypto widgets.

Ported from led-ticker core's `widgets/crypto/coinbase._draw_price_ticker`
(coinbase was removed from core; the renderer travels with the plugin).
Lives as a shared module so a future `crypto.coinbase` could reuse it.

Adapted to the public `led_ticker.plugin` surface: the public `draw_text`
returns the ABSOLUTE next-x (and routes inline emoji), so core's
`cursor_pos += draw_text(canvas, font, x, y, color, text)` became
`cursor_pos = draw_text(canvas, font, text, x, y, color)` — pixel-identical
for plain text (proven by the led-ticker-baseball migration).
"""

import math

from led_ticker.plugin import (
    FONT_DEFAULT,
    FONT_SMALL,
    Canvas,
    Color,
    ColorProvider,
    ColorProviderBase,
    DrawResult,
    Font,
    compute_baseline,
    compute_cursor,
    draw_text,
    get_text_width,
    make_color,
    resolve_font,
)

from led_ticker_crypto._colors import (
    DOWN_TREND_COLOR,
    NEUTRAL_TREND_COLOR,
    UP_TREND_COLOR,
)

# Core FONT_VALUE/FONT_VALUE_SMALL == 6x12/5x8 (FONT_DEFAULT/FONT_SMALL);
# FONT_LABEL/FONT_DELTA are the general 7x13/6x10 BDF faces.
FONT_LABEL: Font = resolve_font("7x13")
FONT_VALUE: Font = FONT_DEFAULT
FONT_VALUE_SMALL: Font = FONT_SMALL
FONT_DELTA: Font = resolve_font("6x10")


class _ConstantColor(ColorProviderBase):
    """Wraps a single Color so a plain `font_color = [r,g,b]` routes through
    the same `color_for` interface as effects. (Core's _ConstantColor is private.)"""

    per_char: bool = False
    frame_invariant: bool = True

    def __init__(self, color: Color) -> None:
        self._color = color

    def color_for(self, frame: int, char_index: int, total_chars: int) -> Color:
        return self._color


def make_default_font_color() -> ColorProvider:
    """Core's default font_color: DEFAULT_COLOR == (255, 255, 0) (yellow)."""
    return _ConstantColor(make_color(255, 255, 0))


def _get_change_color(change_str: str) -> Color:
    try:
        value = float(change_str.rstrip("%"))
    except (ValueError, AttributeError):
        return NEUTRAL_TREND_COLOR
    if value < 0:
        return DOWN_TREND_COLOR
    if value > 0:
        return UP_TREND_COLOR
    return NEUTRAL_TREND_COLOR


def _get_price_font(price_str: str) -> Font:
    if len(price_str) > 10:
        return FONT_VALUE_SMALL
    return FONT_VALUE


def _format_price(value: float) -> str:
    """Format a price with adaptive precision.

    Normal coins (>= 1) keep the historical 4-decimal, thousands-separated form.
    Sub-dollar coins get extra decimals so cheap tokens (e.g. SHIB ~4.6e-06)
    don't collapse to "0.0000".
    """
    if value >= 1 or value == 0:
        return f"{value:,.4f}"
    decimals = min(12, max(4, 3 - int(math.floor(math.log10(abs(value))))))
    return f"{value:.{decimals}f}"


def draw_price_ticker(
    canvas: Canvas,
    symbol: str,
    price_str: str,
    change_str: str,
    cursor_pos: int = 0,
    center: bool = True,
    padding: int = 6,
    end_padding: int = 6,
    y_offset: int = 0,
    font_color: ColorProvider | None = None,
    frame_count: int = 0,
) -> DrawResult:
    change_color = _get_change_color(change_str)
    font_price = _get_price_font(price_str)
    label_color = (
        font_color.color_for(frame_count, 0, 1)
        if font_color is not None
        else make_color(255, 255, 0)
    )

    content_width = (
        get_text_width(FONT_LABEL, symbol, padding=6, canvas=canvas)
        + get_text_width(font_price, price_str, padding=6, canvas=canvas)
        + get_text_width(FONT_DELTA, change_str, padding=0, canvas=canvas)
    )

    cursor_pos, end_padding = compute_cursor(
        canvas.width, content_width, cursor_pos, end_padding, center=center
    )

    baseline_y = compute_baseline(FONT_LABEL, canvas, valign="center") + y_offset
    cursor_pos = draw_text(canvas, FONT_LABEL, symbol, cursor_pos, baseline_y, label_color)
    cursor_pos += padding
    cursor_pos = draw_text(canvas, font_price, price_str, cursor_pos, baseline_y, label_color)
    cursor_pos += padding
    cursor_pos = draw_text(canvas, FONT_DELTA, change_str, cursor_pos, baseline_y, change_color)
    cursor_pos += end_padding

    return canvas, cursor_pos
