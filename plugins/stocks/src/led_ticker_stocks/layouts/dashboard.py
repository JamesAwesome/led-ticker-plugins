"""Longboi trading dashboard (held). Geometry from handoff LAYOUTS.longA.

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
from led_ticker_stocks.state import STATE_META

_MARGIN = 6


def draw_dashboard_story(
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
    """Paint one symbol's longboi trading-dashboard view (a held layout).

    Unlike the card, the dashboard reads `quotes` (the shared sym->SymbolQuote
    dict) and `symbols` (the ordered display-symbol list) to render a
    watch column showing the NEXT 3 symbols after `focus_index`.

    `green_up` flips the change-line + sparkline + watch-column COLORS only
    (arrow glyph stays directional) for non-US market conventions.
    """
    dim = STATE_META[state].dim
    scale = getattr(canvas, "scale", 1)
    yoff = y_offset * scale
    shim, real = phys_wrap(canvas)
    w = real.width
    meta = STATE_META[state]

    # hero
    x = 6
    draw_chip(canvas, x, 6 + yoff, 20, quote, dim=dim)
    x += 26
    hires(shim, quote.sym, x, 2 + yoff, pal.dim(pal.SYM, dim), 26, bold=True)
    hires(
        shim,
        meta.chip_label,
        x,
        48 + yoff,
        pal.dim(make_color(*meta.chip_rgb), dim),
        9,
        bold=False,
    )

    # price block @ x=150
    if quote.has_data:
        hires(
            shim,
            format_price(quote.price, quote.dp_decimals),
            150,
            4 + yoff,
            pal.dim(pal.PRICE, dim),
            24,
            bold=True,
        )
        chg_line = (
            f"{_arrow(quote.change)} {format_change(quote.change, quote.dp_decimals)}"
            f"  {format_pct(quote.pct)}"
        )
        hires(
            shim,
            chg_line,
            150,
            34 + yoff,
            _chg_color(quote, dim, green_up=green_up),
            13,
            bold=False,
        )
        hires(
            shim,
            f"PREV {format_price(quote.prev, quote.dp_decimals)}",
            150,
            51 + yoff,
            pal.dim(pal.LABEL, dim),
            8,
            bold=False,
        )
        draw_sparkline(
            canvas, 288, 8 + yoff, 132, 48, quote, dim=dim, green_up=green_up
        )
    else:
        hires(shim, "—", 150, 4 + yoff, pal.dim(pal.LABEL, dim), 24, bold=True)

    # watch column: next 3 symbols
    for r in range(3):
        g_sym = symbols[(focus_index + 1 + r) % len(symbols)]
        g = quotes.get(g_sym)
        y = 6 + r * 18 + yoff
        hires(shim, g_sym, 434, y, pal.dim(pal.SYM, dim), 10, bold=True)
        if g is not None:
            pv = format_pct(g.pct)
            hires(
                shim,
                pv,
                right_align_x(10, pv, w, _MARGIN, bold=False),
                y,
                _chg_color(g, dim, green_up=green_up),
                10,
                bold=False,
            )

    paging_dots(
        real,
        total,
        focus_index,
        434,
        58 + yoff,
        dim_color=pal.dim(pal.LABEL, dim),
        active_color=pal.dim(pal.SYM, dim),
    )
