"""Crawl layout: one scrolling equity segment `SYM  price  ▲ chg%` per story."""

from led_ticker.plugin import FONT_DEFAULT, compute_baseline, draw_text

from led_ticker_stocks import _palette as pal
from led_ticker_stocks.model import SymbolQuote, format_change, format_pct, format_price
from led_ticker_stocks.state import STATE_META, MarketState

_GAP = 4  # logical px between fields


def _arrow(change):
    if change is None or change == 0:
        return "·"  # middle dot (flat / no-data)
    return "▲" if change > 0 else "▼"


def draw_crawl_story(
    canvas,
    quote: SymbolQuote,
    state: MarketState,
    x: int,
    *,
    frame: int,
    y_offset: int = 0,
    end_padding: int = 6,
    green_up: bool = True,
) -> int:
    dim = STATE_META[state].dim
    baseline = compute_baseline(FONT_DEFAULT, canvas) + y_offset
    cursor = x

    # symbol (white)
    cursor = draw_text(
        canvas, FONT_DEFAULT, quote.sym, cursor, baseline, pal.dim(pal.SYM, dim)
    )
    cursor += _GAP

    if not quote.has_data:
        return (
            draw_text(
                canvas, FONT_DEFAULT, "—", cursor, baseline, pal.dim(pal.LABEL, dim)
            )
            + end_padding
        )

    # price (amber)  — flash handled in Phase 3; Phase 1 draws steady amber
    price_str = format_price(quote.price, quote.dp_decimals)
    cursor = draw_text(
        canvas, FONT_DEFAULT, price_str, cursor, baseline, pal.dim(pal.PRICE, dim)
    )
    cursor += _GAP

    # arrow + change + pct (green/red, or flipped for non-US markets)
    chg = quote.change
    up_color = pal.UP if green_up else pal.DOWN
    down_color = pal.DOWN if green_up else pal.UP
    chg_color = pal.dim(
        up_color if (chg or 0) > 0 else down_color if (chg or 0) < 0 else pal.FLAT, dim
    )
    cursor = draw_text(canvas, FONT_DEFAULT, _arrow(chg), cursor, baseline, chg_color)
    cursor += 2
    cursor = draw_text(
        canvas,
        FONT_DEFAULT,
        format_change(chg, quote.dp_decimals),
        cursor,
        baseline,
        chg_color,
    )
    cursor += _GAP
    cursor = draw_text(
        canvas, FONT_DEFAULT, format_pct(quote.pct), cursor, baseline, chg_color
    )

    return cursor + end_padding
