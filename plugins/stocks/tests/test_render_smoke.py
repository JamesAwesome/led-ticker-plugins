"""Render-correctness smoke tests for the crawl layout using a REAL canvas.

These supersede the Mock-based unit tests in ``test_crawl.py`` for the
specific question those tests cannot answer: does the pixel output actually
change when state dimming or the up/down change color should differ? A
Mock-based test would pass identically whether or not ``pal.dim(...)`` was
applied, or whether up/down colors were swapped — it only ever inspects
``cursor_pos`` arithmetic, never pixels.

Assertions here compare AGGREGATE / RELATIVE properties (pixel counts,
summed brightness, presence of green-dominant vs red-dominant lit pixels) —
never exact coordinates or exact pixel counts — so they stay robust across
machines with different freetype/rasterization output.
"""

from led_ticker.plugin import HeadlessBackend

from led_ticker_stocks.layouts.crawl import draw_crawl_story
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState

# Smallsign geometry: 160 wide x 16 tall, scale 1 (matches config.example.toml).
_WIDTH = 160
_HEIGHT = 16


def _canvas():
    return HeadlessBackend(_WIDTH, _HEIGHT).create_canvas()


def _lit_pixels(canvas):
    """Non-black pixels as a dict, for aggregate inspection."""
    return {xy: rgb for xy, rgb in canvas._pixels.items() if rgb != (0, 0, 0)}


def _brightness_sum(canvas) -> int:
    """Sum of every channel of every lit pixel — a real "how bright overall"
    signal that a dim() scale factor directly moves."""
    return sum(sum(rgb) for rgb in _lit_pixels(canvas).values())


def _up_quote():
    return SymbolQuote(sym="AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)


def _down_quote():
    return SymbolQuote(sym="AAPL", price=310.0, prev=315.32, d=-5.32, dp=-1.69)


def test_lights_pixels_and_advances_cursor():
    canvas = _canvas()
    quote = _up_quote()

    end = draw_crawl_story(canvas, quote, MarketState.OPEN, 0, frame=0)

    lit = _lit_pixels(canvas)
    assert len(lit) > 0, "expected draw_crawl_story to light real pixels"
    assert end > 0


def test_state_dimming_lowers_total_brightness():
    """Same quote, OPEN (dim=1.0) vs CLOSED (dim=0.45) on fresh canvases.

    Proves pal.dim(...) is actually applied to the rendered colors — a
    Mock-based test can't observe this because it never inspects pixel
    values, only cursor arithmetic.
    """
    quote_open = _up_quote()
    quote_closed = _up_quote()

    canvas_open = _canvas()
    canvas_closed = _canvas()

    draw_crawl_story(canvas_open, quote_open, MarketState.OPEN, 0, frame=0)
    draw_crawl_story(canvas_closed, quote_closed, MarketState.CLOSED, 0, frame=0)

    pixels_open = canvas_open._pixels
    pixels_closed = canvas_closed._pixels
    assert pixels_open != pixels_closed, (
        "OPEN and CLOSED renders should differ — dimming isn't being applied"
    )

    brightness_open = _brightness_sum(canvas_open)
    brightness_closed = _brightness_sum(canvas_closed)

    assert brightness_open > 0
    assert brightness_closed > 0
    assert brightness_closed < brightness_open, (
        f"expected CLOSED (dim=0.45) brightness ({brightness_closed}) to be "
        f"measurably lower than OPEN (dim=1.0) brightness ({brightness_open})"
    )
    # Roughly matches the 0.45/1.0 palette dim ratio; loose bound to tolerate
    # font antialiasing / rounding — just confirms it's not a no-op scale.
    assert brightness_closed < brightness_open * 0.75


def test_up_vs_down_change_color_flips():
    """Up-quote should render green-dominant change pixels; down-quote
    should render red-dominant change pixels, under the identical state.
    """
    canvas_up = _canvas()
    canvas_down = _canvas()

    draw_crawl_story(canvas_up, _up_quote(), MarketState.OPEN, 0, frame=0)
    draw_crawl_story(canvas_down, _down_quote(), MarketState.OPEN, 0, frame=0)

    assert canvas_up._pixels != canvas_down._pixels

    lit_up = _lit_pixels(canvas_up)
    lit_down = _lit_pixels(canvas_down)

    green_dominant_up = any(rgb[1] > rgb[0] for rgb in lit_up.values())
    red_dominant_down = any(rgb[0] > rgb[1] for rgb in lit_down.values())

    assert green_dominant_up, (
        "expected the up-quote render to contain at least one green-dominant "
        "(G>R) lit pixel from the change/pct text"
    )
    assert red_dominant_down, (
        "expected the down-quote render to contain at least one red-dominant "
        "(R>G) lit pixel from the change/pct text"
    )

    # The down-quote render must NOT contain any green-dominant pixel — SYM
    # (white, R==G) and PRICE (amber, R>G) are the only shared colors, so a
    # green-dominant pixel appearing here would mean the up color leaked in.
    green_dominant_down = any(rgb[1] > rgb[0] for rgb in lit_down.values())
    assert not green_dominant_down, (
        "down-quote render should have no green-dominant pixels — found some, "
        "meaning the change color isn't actually flipping"
    )


def test_green_up_false_flips_up_quote_color():
    """`green_up=False` must flip the UP-quote's change color from green to
    red — proving the flag actually reaches the color choice rather than
    being threaded through and ignored (the Phase-1 review finding this
    closes).
    """
    canvas_default = _canvas()
    canvas_flipped = _canvas()
    quote = _up_quote()

    draw_crawl_story(canvas_default, quote, MarketState.OPEN, 0, frame=0, green_up=True)
    draw_crawl_story(
        canvas_flipped, quote, MarketState.OPEN, 0, frame=0, green_up=False
    )

    assert canvas_default._pixels != canvas_flipped._pixels

    lit_default = _lit_pixels(canvas_default)
    lit_flipped = _lit_pixels(canvas_flipped)

    # NOTE: PRICE is amber (255, 180, 0) — R>G — so it's expected to
    # contribute red-dominant pixels in BOTH renders. We only assert on
    # green-dominant presence/absence, since UP (60, 220, 60) is the one
    # color with G>R and no other field in the segment produces that.
    green_dominant_default = any(rgb[1] > rgb[0] for rgb in lit_default.values())
    assert green_dominant_default, (
        "expected green_up=True (default) to render the up-quote change as "
        "green-dominant (UP color)"
    )

    red_dominant_flipped = any(rgb[0] > rgb[1] for rgb in lit_flipped.values())
    green_dominant_flipped = any(rgb[1] > rgb[0] for rgb in lit_flipped.values())
    assert red_dominant_flipped, (
        "expected green_up=False to render the SAME up-quote change as "
        "red-dominant (DOWN color) — the flag should invert the up/down "
        "colors"
    )
    assert not green_dominant_flipped, (
        "green_up=False render should have no green-dominant pixels — found "
        "some, meaning the flag isn't actually flipping the change color "
        "(the UP color leaked through)"
    )


def test_no_data_placeholder_renders_without_raising():
    canvas = _canvas()
    quote = SymbolQuote(sym="ZZZZ", price=0.0, prev=0.0)

    end = draw_crawl_story(canvas, quote, MarketState.OPEN, 0, frame=0)

    lit = _lit_pixels(canvas)
    assert len(lit) > 0, "expected the 'SYM —' placeholder to light pixels"
    assert end > 0
