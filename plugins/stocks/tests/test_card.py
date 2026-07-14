from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_stocks.layouts import LAYOUTS, resolve_layout
from led_ticker_stocks.layouts.card import draw_card_story
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _up():
    return SymbolQuote(sym="AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)


def _down():
    return SymbolQuote(sym="AAPL", price=310.0, prev=315.32, d=-5.32, dp=-1.69)


def test_card_registered_and_resolved_by_width():
    assert LAYOUTS["card"] is draw_card_story
    c, _ = _bigsign()
    assert resolve_layout(c, None) == "card"


def test_card_renders_content_within_panel():
    c, real = _bigsign()
    draw_card_story(
        c, _up(), MarketState.OPEN, {}, ["AAPL"], focus_index=0, total=4, frame=0
    )
    lit = {xy: v for xy, v in real._pixels.items() if v != (0, 0, 0)}
    assert lit
    assert all(0 <= x < 256 and 0 <= y < 64 for (x, y) in lit)  # no overflow off-canvas


def test_card_up_green_down_red():
    cu, ru = _bigsign()
    draw_card_story(
        cu, _up(), MarketState.OPEN, {}, ["AAPL"], focus_index=0, total=4, frame=0
    )
    cd, rd = _bigsign()
    draw_card_story(
        cd, _down(), MarketState.OPEN, {}, ["AAPL"], focus_index=0, total=4, frame=0
    )

    def has(real, pred):
        return any(pred(v) for v in real._pixels.values())

    assert has(ru, lambda v: v[1] > v[0] and v[1] > v[2])  # green present (up)
    assert has(rd, lambda v: v[0] > v[1] and v[0] > v[2])  # red present (down)


def test_card_closed_dims_vs_open():
    co, ro = _bigsign()
    draw_card_story(
        co, _up(), MarketState.OPEN, {}, ["AAPL"], focus_index=0, total=4, frame=0
    )
    cc, rc = _bigsign()
    draw_card_story(
        cc, _up(), MarketState.CLOSED, {}, ["AAPL"], focus_index=0, total=4, frame=0
    )

    def brightness(real):
        return sum(sum(v) for v in real._pixels.values())

    assert brightness(rc) < brightness(ro)


def test_card_no_data_does_not_crash():
    c, real = _bigsign()
    q = SymbolQuote(sym="ZZZZ", price=0.0, prev=0.0)
    draw_card_story(
        c, q, MarketState.OPEN, {}, ["ZZZZ"], focus_index=0, total=1, frame=0
    )
    assert real._pixels  # the em-dash placeholder + chip still paint something


def test_card_ignores_unused_quotes_and_symbols_args():
    """quotes/symbols are accepted (uniform held signature for Task 5's
    dashboard) but the card itself doesn't read them — passing garbage
    values must not affect the render or raise."""
    c1, r1 = _bigsign()
    draw_card_story(
        c1, _up(), MarketState.OPEN, {}, ["AAPL"], focus_index=0, total=4, frame=0
    )
    c2, r2 = _bigsign()
    draw_card_story(
        c2,
        _up(),
        MarketState.OPEN,
        {"garbage": "value"},
        ["MSFT", "TSLA"],
        focus_index=0,
        total=4,
        frame=0,
    )
    assert r1._pixels == r2._pixels


def test_card_green_up_false_flips_down_quote_to_green():
    """`green_up=False` flips a DOWN quote's change-line + sparkline color
    from red to green (non-US convention) — teeth: would fail if the card
    ignored `green_up` (Phase 2 final-review Fix 1: card/dashboard were
    crawl-only).

    The symbol chip is a deterministic per-symbol hash color (`_chip.py`)
    that, for "AAPL", happens to be red-dominant — so a plain "is there any
    red pixel" presence check would pass even with `green_up` ignored.
    Instead, diff the two renders: chip/price/label pixels are IDENTICAL at
    the same (x, y) in both (same symbol, same position, unaffected by
    `green_up`), so the pixels that differ between the two dicts are
    exactly the change-line/sparkline pixels `green_up` controls.
    """
    c_default, r_default = _bigsign()
    draw_card_story(
        c_default,
        _down(),
        MarketState.OPEN,
        {},
        ["AAPL"],
        focus_index=0,
        total=4,
        frame=0,
    )
    c_flipped, r_flipped = _bigsign()
    draw_card_story(
        c_flipped,
        _down(),
        MarketState.OPEN,
        {},
        ["AAPL"],
        focus_index=0,
        total=4,
        frame=0,
        green_up=False,
    )

    def red(v):
        return v[0] > v[1] and v[0] > v[2]

    def green(v):
        return v[1] > v[0] and v[1] > v[2]

    diff_keys = {
        xy
        for xy in r_default._pixels
        if xy in r_flipped._pixels and r_default._pixels[xy] != r_flipped._pixels[xy]
    }
    assert diff_keys  # green_up must actually change SOME pixels
    assert all(red(r_default._pixels[xy]) for xy in diff_keys)
    assert all(green(r_flipped._pixels[xy]) for xy in diff_keys)


def test_card_accepts_y_offset():
    c, real = _bigsign()
    # Non-zero y_offset must not raise and must still paint on-canvas
    # (CLAUDE.md: y_offset must be honored so PushUp/PushDown transitions
    # against a held layout don't break).
    draw_card_story(
        c,
        _up(),
        MarketState.OPEN,
        {},
        ["AAPL"],
        focus_index=0,
        total=4,
        frame=0,
        y_offset=2,
    )
    lit = {xy: v for xy, v in real._pixels.items() if v != (0, 0, 0)}
    assert lit
    assert all(0 <= x < 256 and 0 <= y < 64 for (x, y) in lit)
