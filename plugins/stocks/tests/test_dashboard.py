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
