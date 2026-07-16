"""Bigsign quote card (held). Geometry from handoff LAYOUTS.bigA.

The price line flashes whiter on a recent price change (Bloomberg-style,
wall-clock decay — see `layouts._common.flash_price_color`). `frame`
(the held renderer's own frame counter) drives two pulses: the LIVE state
chip breathes while the market is OPEN (`layouts._common.live_pulse`), and
the sparkline endpoint twinkles regardless of state
(`layouts._common.endpoint_pulse`, applied inside `draw_sparkline`).
"""

import time

from led_ticker.plugin import make_color

from led_ticker_stocks import _palette as pal
from led_ticker_stocks._chip import draw_chip
from led_ticker_stocks._paint import hires, paging_dots, phys_wrap, right_align_x
from led_ticker_stocks._sparkline import draw_sparkline
from led_ticker_stocks.layouts._common import arrow as _arrow
from led_ticker_stocks.layouts._common import chg_color as _chg_color
from led_ticker_stocks.layouts._common import flash_price_color, live_pulse
from led_ticker_stocks.model import format_change, format_pct, format_price
from led_ticker_stocks.state import STATE_META, MarketState

_MARGIN = 4

# The symbol (left) and price (right) share the card's top row. Min real-px gap
# between them, and the ladder of hi-res sizes the price may shrink to so a wide
# value (crypto magnitudes, or a negative's leading minus) never overlaps a long
# symbol. 22 is the design size; 11 is the floor (matches the change line).
_SYM_PRICE_GAP = 6
_PRICE_SIZES = (22, 18, 16, 14, 12, 11)


def _fit_price_size(price: str, sym_end: int, real_width: int) -> int:
    """Largest size in `_PRICE_SIZES` whose right-aligned price clears the
    symbol's right edge (`sym_end`) by `_SYM_PRICE_GAP` — so the two never
    overlap. Falls back to the smallest size (still far better than a fixed-22
    collision) if even that would touch."""
    for size in _PRICE_SIZES:
        if right_align_x(size, price, real_width, _MARGIN) >= sym_end + _SYM_PRICE_GAP:
            return size
    return _PRICE_SIZES[-1]


def draw_card_story(
    canvas,
    quote,
    state,
    quotes,
    symbols,
    *,
    focus_index: int,
    total: int,
    frame: int,
    green_up: bool = True,
    y_offset: int = 0,
) -> None:
    """Paint one symbol's bigsign quote card in place (a held layout).

    `quotes` (the shared sym->SymbolQuote dict) and `symbols` (the ordered
    display-symbol list) are accepted but unused here — they exist so
    `_StockStory.draw` can call every held layout (this card, and the
    dashboard added in Task 5) through one uniform signature.

    `green_up` flips the change-line + sparkline COLORS only (arrow glyph
    stays directional) for non-US market conventions; see CLAUDE.md.
    """
    dim = STATE_META[state].dim
    now = time.monotonic()
    scale = getattr(canvas, "scale", 1)
    yoff = y_offset * scale
    shim, real = phys_wrap(canvas)
    w = real.width

    x = _MARGIN
    draw_chip(canvas, x, 4 + yoff, 16, quote, dim=dim)
    x += 20

    # hires() returns the advance width, so this is the symbol's right edge.
    sym_end = x + hires(
        shim, quote.sym, x, 1 + yoff, pal.dim(pal.SYM, dim), 22, bold=True
    )
    # company name unknown in v1 (no metadata source) -> skip; symbol carries it

    if quote.has_data:
        price = format_price(quote.price, quote.dp_decimals)
        # Shrink the price to the largest size that clears the symbol, so a wide
        # value (crypto, or a negative's minus) can't land on the symbol's last
        # letter (the price is drawn after, so it would win the overlap).
        price_size = _fit_price_size(price, sym_end, w)
        hires(
            shim,
            price,
            right_align_x(price_size, price, w, _MARGIN),
            1 + yoff,
            flash_price_color(quote.flash_t, dim, now=now),
            price_size,
            bold=True,
        )
        chg_line = (
            f"{_arrow(quote.change)} {format_change(quote.change, quote.dp_decimals)}"
            f"  {format_pct(quote.pct)}"
        )
        hires(
            shim,
            chg_line,
            right_align_x(11, chg_line, w, _MARGIN, bold=False),
            26 + yoff,
            _chg_color(quote, dim, green_up=green_up),
            11,
            bold=False,
        )
        draw_sparkline(
            canvas,
            4,
            41 + yoff,
            178,
            19,
            quote,
            dim=dim,
            green_up=green_up,
            frame=frame,
        )
    else:
        hires(
            shim,
            "—",
            right_align_x(22, "—", w, _MARGIN),
            1 + yoff,
            pal.dim(pal.LABEL, dim),
            22,
            bold=True,
        )

    # Right-hand state zone, stacked top->bottom so nothing overlaps:
    #   [state label]   (+ "AT CLOSE" below it when closed)
    #   [paging dots]   flight-shaped, bottom-right corner
    # LIVE chip pulses (frame-driven breathing) only while the market is
    # OPEN; every other state renders steady.
    meta = STATE_META[state]
    chip_dim = dim * live_pulse(frame) if meta.pulses else dim
    state_color = pal.dim(make_color(*meta.chip_rgb), chip_dim)
    if state is MarketState.CLOSED:
        hires(shim, meta.chip_label, 192, 37 + yoff, state_color, 9, bold=False)
        hires(shim, "AT CLOSE", 192, 47 + yoff, pal.dim(pal.LABEL, dim), 8, bold=False)
    else:
        hires(shim, meta.chip_label, 192, 47 + yoff, state_color, 9, bold=False)
    paging_dots(
        real,
        total,
        focus_index,
        w - total * (2 * scale) - 4,
        real.height - scale - 1 + yoff,
        scale=scale,
        dim_color=pal.dim(pal.LABEL, dim),
        active_color=pal.dim(pal.SYM, dim),
    )
