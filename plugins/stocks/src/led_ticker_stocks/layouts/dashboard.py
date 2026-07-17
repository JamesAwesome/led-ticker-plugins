"""Longboi trading dashboard (held). Geometry from handoff LAYOUTS.longA.

The hero price flashes whiter on a recent price change (Bloomberg-style,
wall-clock decay — see `layouts._common.flash_price_color`). `frame` (the
held renderer's own frame counter) drives two pulses: the LIVE state chip
breathes while the market is OPEN (`layouts._common.live_pulse`), and the
sparkline endpoint twinkles regardless of state
(`layouts._common.endpoint_pulse`, applied inside `draw_sparkline`).
"""

import time

from led_ticker.plugin import make_color

from led_ticker_stocks import _palette as pal
from led_ticker_stocks._chip import draw_chip
from led_ticker_stocks._paint import (
    hires,
    paging_dots,
    phys_wrap,
    right_align_x,
    text_width,
)
from led_ticker_stocks._sparkline import draw_sparkline
from led_ticker_stocks.layouts._common import arrow as _arrow
from led_ticker_stocks.layouts._common import chg_color as _chg_color
from led_ticker_stocks.layouts._common import flash_price_color, live_pulse
from led_ticker_stocks.model import format_change, format_pct, format_price
from led_ticker_stocks.state import STATE_META

_MARGIN = 6

# The hero symbol (from x=32) runs toward the price block at fixed x=150; the
# watch rows pack a symbol (x=434) + a right-aligned pct into the ~74px column.
# Both were tuned for <=5-char equity symbols — a 7-char pair (EUR/USD) needs a
# guard or the later-drawn text lands on the earlier. Shrink-to-fit ladders,
# measured with the same metrics the paint uses (text_width), platform-exact.
_PRICE_BLOCK_X = 150
_HERO_SYM_GAP = 6
_HERO_SYM_SIZES = (26, 22, 20, 18)
_WATCH_GAP = 4
_WATCH_SIZES = (10, 9, 8)


def _fit_hero_sym_size(sym: str, x: int) -> int:
    """Largest hero-symbol size that ends before the fixed price block."""
    budget = _PRICE_BLOCK_X - _HERO_SYM_GAP - x
    for size in _HERO_SYM_SIZES:
        if text_width(size, sym, bold=True) <= budget:
            return size
    return _HERO_SYM_SIZES[-1]


def _fit_watch_size(sym: str, pv: str, col_width: int) -> int:
    """Largest shared size at which a watch row's symbol + gap + pct fit the
    column (uniform shrink reads better than mixed sizes)."""
    for size in _WATCH_SIZES:
        used = text_width(size, sym, bold=True) + _WATCH_GAP
        used += text_width(size, pv, bold=False)
        if used <= col_width:
            return size
    return _WATCH_SIZES[-1]


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
    dim_by_state: bool = True,
    y_offset: int = 0,
) -> None:
    """Paint one symbol's longboi trading-dashboard view (a held layout).

    Unlike the card, the dashboard reads `quotes` (the shared sym->SymbolQuote
    dict) and `symbols` (the ordered display-symbol list) to render a
    watch column showing the NEXT 3 symbols after `focus_index`.

    `green_up` flips the change-line + sparkline + watch-column COLORS only
    (arrow glyph stays directional) for non-US market conventions.
    """
    # dim_by_state=False: full brightness regardless of market state (the
    # state CHIP still reads LIVE/CLSD — information stays, the dim goes).
    dim = STATE_META[state].dim if dim_by_state else 1.0
    now = time.monotonic()
    scale = getattr(canvas, "scale", 1)
    yoff = y_offset * scale
    shim, real = phys_wrap(canvas)
    w = real.width
    meta = STATE_META[state]

    # hero — symbol shrinks (26 -> 18) if it would run into the price block.
    x = 6
    draw_chip(canvas, x, 6 + yoff, 20, quote, dim=dim)
    x += 26
    sym_size = _fit_hero_sym_size(quote.sym, x)
    hires(shim, quote.sym, x, 2 + yoff, pal.dim(pal.SYM, dim), sym_size, bold=True)
    # LIVE chip pulses (frame-driven breathing) only while the market is
    # OPEN; every other state renders steady.
    chip_dim = dim * live_pulse(frame) if meta.pulses else dim
    hires(
        shim,
        meta.chip_label,
        x,
        48 + yoff,
        pal.dim(make_color(*meta.chip_rgb), chip_dim),
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
            flash_price_color(quote.flash_t, dim, now=now),
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
            canvas,
            288,
            8 + yoff,
            132,
            48,
            quote,
            dim=dim,
            green_up=green_up,
            frame=frame,
        )
    else:
        hires(shim, "—", 150, 4 + yoff, pal.dim(pal.LABEL, dim), 24, bold=True)

    # watch column: next 3 symbols. Per row, symbol + right-aligned pct share
    # ~74px — pick a shared size that fits both (a 7-char pair like EUR/USD at
    # 10px collides with its pct; uniform shrink keeps the row readable).
    for r in range(3):
        g_sym = symbols[(focus_index + 1 + r) % len(symbols)]
        g = quotes.get(g_sym)
        y = 6 + r * 18 + yoff
        pv = format_pct(g.pct) if g is not None else ""
        row_size = _fit_watch_size(g_sym, pv, w - _MARGIN - 434) if pv else 10
        hires(shim, g_sym, 434, y, pal.dim(pal.SYM, dim), row_size, bold=True)
        if g is not None:
            hires(
                shim,
                pv,
                right_align_x(row_size, pv, w, _MARGIN, bold=False),
                y,
                _chg_color(g, dim, green_up=green_up),
                row_size,
                bold=False,
            )

    paging_dots(
        real,
        total,
        focus_index,
        434,
        real.height - scale - 1 + yoff,
        scale=scale,
        dim_color=pal.dim(pal.LABEL, dim),
        active_color=pal.dim(pal.SYM, dim),
    )
