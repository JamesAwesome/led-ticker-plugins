"""Longboi dashboard layout: registration, panel bounds, watch-column neighbors."""

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_stocks.layouts import LAYOUTS, resolve_layout
from led_ticker_stocks.layouts.dashboard import draw_dashboard_story
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _quotes():
    q = {}
    for s, p in [("AAPL", 317.0), ("MSFT", 448.0), ("NVDA", 120.0), ("TSLA", 250.0)]:
        q[s] = SymbolQuote(sym=s, price=p, prev=p - 1, d=1.0, dp=0.3)
    return q


def test_dashboard_registered_and_resolved():
    assert LAYOUTS["dashboard"] is draw_dashboard_story
    c, _ = _longboi()
    assert resolve_layout(c, None) == "dashboard"


def test_dashboard_renders_within_panel():
    c, real = _longboi()
    qs = _quotes()
    draw_dashboard_story(
        c,
        qs["AAPL"],
        MarketState.OPEN,
        qs,
        ["AAPL", "MSFT", "NVDA", "TSLA"],
        focus_index=0,
        total=4,
        frame=0,
    )
    lit = {xy: v for xy, v in real._pixels.items() if v != (0, 0, 0)}
    assert lit and all(0 <= x < 512 and 0 <= y < 64 for (x, y) in lit)


def test_watch_column_shows_neighbors_not_focus():
    # Render focus=AAPL; the watch column must show MSFT/NVDA/TSLA glyphs.
    # Proxy assertion: rendering with a DIFFERENT neighbor set changes the
    # right-side pixels.
    c1, r1 = _longboi()
    qs = _quotes()
    draw_dashboard_story(
        c1,
        qs["AAPL"],
        MarketState.OPEN,
        qs,
        ["AAPL", "MSFT", "NVDA", "TSLA"],
        focus_index=0,
        total=4,
        frame=0,
    )
    c2, r2 = _longboi()
    qs2 = _quotes()
    draw_dashboard_story(
        c2,
        qs2["AAPL"],
        MarketState.OPEN,
        qs2,
        ["AAPL", "ZZZZ", "YYYY", "XXXX"],
        focus_index=0,
        total=4,
        frame=0,
    )
    right1 = {xy: v for xy, v in r1._pixels.items() if xy[0] >= 434}
    right2 = {xy: v for xy, v in r2._pixels.items() if xy[0] >= 434}
    assert right1 != right2  # watch column reflects the actual neighbor symbols


def test_watch_column_wraps_at_end_of_symbol_list():
    # focus_index=3 is the LAST symbol in a 4-symbol list. The watch column
    # formula (focus_index + 1 + r) % len(symbols) must wrap back to the
    # front of the list (indices 0, 1, 2) rather than IndexError past the end.
    symbols = ["AAPL", "MSFT", "NVDA", "TSLA"]
    c1, r1 = _longboi()
    qs = _quotes()
    draw_dashboard_story(
        c1,
        qs["TSLA"],
        MarketState.OPEN,
        qs,
        symbols,
        focus_index=3,
        total=4,
        frame=0,
    )

    # Same focus_index=3, but different symbols occupying the wrapped
    # neighbor slots (0, 1, 2) — if the modulo wraparound is actually
    # exercised, the watch column must reflect these new symbols and the
    # right-side pixels must differ from the run above.
    c2, r2 = _longboi()
    wrapped_symbols = ["ZZZZ", "YYYY", "XXXX", "TSLA"]
    qs2 = dict(qs)
    for s, p in [("ZZZZ", 10.0), ("YYYY", 20.0), ("XXXX", 30.0)]:
        qs2[s] = SymbolQuote(sym=s, price=p, prev=p - 1, d=1.0, dp=0.3)
    draw_dashboard_story(
        c2,
        qs2["TSLA"],
        MarketState.OPEN,
        qs2,
        wrapped_symbols,
        focus_index=3,
        total=4,
        frame=0,
    )

    lit1 = {xy: v for xy, v in r1._pixels.items() if v != (0, 0, 0)}
    lit2 = {xy: v for xy, v in r2._pixels.items() if v != (0, 0, 0)}
    assert lit1 and lit2

    right1 = {xy: v for xy, v in r1._pixels.items() if xy[0] >= 434}
    right2 = {xy: v for xy, v in r2._pixels.items() if xy[0] >= 434}
    assert right1 != right2  # wrapped neighbors (indices 0,1,2) actually drawn


def test_dashboard_green_up_false_flips_down_quote_to_green():
    """`green_up=False` flips a DOWN quote's change-line + sparkline (and
    watch-column pct) color from red to green — teeth: would fail if the
    dashboard ignored `green_up` (Phase 2 final-review Fix 1).

    Symbol-chip pixels are a deterministic per-symbol hash color unrelated
    to `green_up`, so diff the two renders rather than a plain presence
    check: pixels identical at the same (x, y) in both renders are
    unaffected by `green_up`; the ones that differ are exactly the
    change-line/sparkline/watch-column pixels it controls.
    """
    c_default, r_default = _longboi()
    qs = _quotes()
    down = SymbolQuote(sym="AAPL", price=310.0, prev=315.32, d=-5.32, dp=-1.69)
    qs["AAPL"] = down
    draw_dashboard_story(
        c_default,
        down,
        MarketState.OPEN,
        qs,
        ["AAPL", "MSFT", "NVDA", "TSLA"],
        focus_index=0,
        total=4,
        frame=0,
    )
    c_flipped, r_flipped = _longboi()
    qs2 = _quotes()
    qs2["AAPL"] = down
    draw_dashboard_story(
        c_flipped,
        down,
        MarketState.OPEN,
        qs2,
        ["AAPL", "MSFT", "NVDA", "TSLA"],
        focus_index=0,
        total=4,
        frame=0,
        green_up=False,
    )

    def red(v):
        return v[0] > v[1] and v[0] > v[2]

    def green(v):
        return v[1] > v[0] and v[1] > v[2]

    # Restrict to the hero/sparkline region (x < 434): the watch column
    # (x >= 434) shows the NEXT 3 symbols, which are UP quotes here, so
    # their flip runs the opposite direction (green -> red) and would
    # contaminate a single-direction assertion.
    diff_keys = {
        xy
        for xy in r_default._pixels
        if xy[0] < 434
        and xy in r_flipped._pixels
        and r_default._pixels[xy] != r_flipped._pixels[xy]
    }
    assert diff_keys  # green_up must actually change SOME pixels
    assert all(red(r_default._pixels[xy]) for xy in diff_keys)
    assert all(green(r_flipped._pixels[xy]) for xy in diff_keys)


def test_dashboard_accepts_y_offset():
    # CLAUDE.md: y_offset must be honored so PushUp/PushDown transitions
    # against a held layout don't break.
    c, real = _longboi()
    qs = _quotes()
    draw_dashboard_story(
        c,
        qs["AAPL"],
        MarketState.OPEN,
        qs,
        ["AAPL", "MSFT", "NVDA", "TSLA"],
        focus_index=0,
        total=4,
        frame=0,
        y_offset=2,
    )
    lit = {xy: v for xy, v in real._pixels.items() if v != (0, 0, 0)}
    assert lit and all(0 <= x < 512 and 0 <= y < 64 for (x, y) in lit)


def test_dashboard_no_data_does_not_crash():
    c, real = _longboi()
    qs = _quotes()
    q = SymbolQuote(sym="ZZZZ", price=0.0, prev=0.0)
    draw_dashboard_story(
        c,
        q,
        MarketState.OPEN,
        qs,
        ["ZZZZ", "AAPL", "MSFT", "NVDA"],
        focus_index=0,
        total=4,
        frame=0,
    )
    assert real._pixels


def test_hero_symbol_shrinks_to_clear_price_block():
    """A 7-char pair (EUR/USD) at the design size 26 runs into the fixed
    x=150 price block; the fit helper must shrink it. Short equity symbols
    keep the design size (no visual change)."""
    from led_ticker_stocks._paint import text_width
    from led_ticker_stocks.layouts.dashboard import (
        _HERO_SYM_GAP,
        _HERO_SYM_SIZES,
        _PRICE_BLOCK_X,
        _fit_hero_sym_size,
    )

    assert _fit_hero_sym_size("AAPL", 32) == _HERO_SYM_SIZES[0]
    size = _fit_hero_sym_size("EUR/USD", 32)
    assert size < _HERO_SYM_SIZES[0]
    # Invariant (platform-metric independent): the chosen size clears the
    # price block, unless it hit the ladder floor.
    assert (
        32 + text_width(size, "EUR/USD", bold=True) <= _PRICE_BLOCK_X - _HERO_SYM_GAP
        or size == _HERO_SYM_SIZES[-1]
    )


def test_watch_row_symbol_and_pct_never_overlap():
    """REGRESSION (hardware, longboi): the watch column drew a 7-char pair +
    its right-aligned pct with no collision guard — 'EUR/USD' and '-0.2%'
    touched/overlapped. The shared row size must fit both in the column."""
    from led_ticker_stocks._paint import text_width
    from led_ticker_stocks.layouts.dashboard import (
        _WATCH_GAP,
        _WATCH_SIZES,
        _fit_watch_size,
    )

    col = 74  # 512 - 434 - _MARGIN, the real longboi watch column
    for sym, pv in [
        ("EUR/USD", "−0.20%"),
        ("EUR/USD", "−10.55%"),
        ("BTC/USD", "−1.17%"),
    ]:
        size = _fit_watch_size(sym, pv, col)
        used = (
            text_width(size, sym, bold=True)
            + _WATCH_GAP
            + text_width(size, pv, bold=False)
        )
        assert used <= col or size == _WATCH_SIZES[-1]
    # Short equity rows keep the design size.
    assert _fit_watch_size("AAPL", "−0.69%", col) == _WATCH_SIZES[0]


def test_watch_row_renders_separated_pixels():
    """End-to-end: render a dashboard whose watch row is EUR/USD with a pct and
    assert the symbol and pct paint as two separated pixel blocks."""
    real = HeadlessBackend(512, 64).create_canvas()
    canvas = ScaledCanvas(real, scale=4, content_height=16)

    def q(sym, price, prev, dp):
        return SymbolQuote(
            sym=sym,
            price=price,
            prev=prev,
            dp=dp,
            dp_decimals=4,
            state=MarketState.OPEN,
        )

    quotes = {
        "BTC/USD": q("BTC/USD", 64906.62, 65043.98, -10.55),
        "EUR/USD": q("EUR/USD", 1.1467, 1.1490, -0.20),
    }
    syms = ["BTC/USD", "EUR/USD"]
    draw_dashboard_story(
        canvas,
        quotes["BTC/USD"],
        MarketState.OPEN,
        quotes,
        syms,
        focus_index=0,
        total=2,
        frame=0,
    )
    # Watch row 0 = EUR/USD. Collect lit columns in the watch band.
    cols = sorted(
        {
            x
            for y in range(6, 19)
            for x in range(430, 512)
            if real.get_pixel(x, y) != (0, 0, 0)
        }
    )
    assert cols, "watch row should have painted something"
    # There must be a gap of >2px somewhere between symbol and pct blocks.
    gaps = [b - a for a, b in zip(cols, cols[1:], strict=False) if b - a > 2]
    assert gaps, "symbol and pct rendered as one continuous block (overlap)"
