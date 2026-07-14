"""Bigsign quote card (held). Geometry from handoff LAYOUTS.bigA.

v1 is static — no flash/pulse (that's Phase 3). `frame` is accepted for the
uniform held-renderer signature but not read yet.
"""

from led_ticker.plugin import make_color

from led_ticker_stocks import _palette as pal
from led_ticker_stocks._chip import draw_chip
from led_ticker_stocks._paint import hires, paging_dots, phys_wrap, right_align_x
from led_ticker_stocks._sparkline import draw_sparkline
from led_ticker_stocks.layouts._common import arrow as _arrow
from led_ticker_stocks.layouts._common import chg_color as _chg_color
from led_ticker_stocks.model import format_change, format_pct, format_price
from led_ticker_stocks.state import STATE_META, MarketState

_MARGIN = 4


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
    scale = getattr(canvas, "scale", 1)
    yoff = y_offset * scale
    shim, real = phys_wrap(canvas)
    w = real.width

    x = _MARGIN
    draw_chip(canvas, x, 4 + yoff, 16, quote, dim=dim)
    x += 20

    hires(shim, quote.sym, x, 1 + yoff, pal.dim(pal.SYM, dim), 22, bold=True)
    # company name unknown in v1 (no metadata source) -> skip; symbol carries it

    if quote.has_data:
        price = format_price(quote.price, quote.dp_decimals)
        hires(
            shim,
            price,
            right_align_x(22, price, w, _MARGIN),
            1 + yoff,
            pal.dim(pal.PRICE, dim),
            22,
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
        draw_sparkline(canvas, 4, 41 + yoff, 178, 19, quote, dim=dim, green_up=green_up)
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

    # state chip label + paging dots (static; chip pulse is Phase 3)
    meta = STATE_META[state]
    state_color = pal.dim(make_color(*meta.chip_rgb), dim)
    hires(shim, meta.chip_label, 192, 42 + yoff, state_color, 9, bold=False)
    paging_dots(
        real,
        total,
        focus_index,
        w - total * 8 - 4,
        real.height - 6 + yoff,
        dim_color=pal.dim(pal.LABEL, dim),
        active_color=pal.dim(pal.SYM, dim),
    )
    if state is MarketState.CLOSED:
        hires(shim, "AT CLOSE", 192, 53 + yoff, pal.dim(pal.LABEL, dim), 8, bold=False)
