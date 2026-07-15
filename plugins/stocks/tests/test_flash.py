"""Layout-level Bloomberg price flash: recent price change renders whiter."""

import time

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_stocks.layouts.card import draw_card_story
from led_ticker_stocks.layouts.crawl import draw_crawl_story
from led_ticker_stocks.layouts.dashboard import draw_dashboard_story
from led_ticker_stocks.model import SymbolQuote
from led_ticker_stocks.state import MarketState


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _smallsign():
    return HeadlessBackend(160, 16).create_canvas()


def _q(flash_t):
    q = SymbolQuote(sym="AAPL", price=317.31, prev=315.32, d=1.99, dp=0.6311)
    for p in [315.0, 316.0, 317.31]:
        q.spark.append(p)
    q.flash_t = flash_t
    return q


def _white_ish(real):
    # count pixels bright on all three channels (flash pushes price toward white)
    return sum(
        1 for v in real._pixels.values() if v[0] > 200 and v[1] > 200 and v[2] > 150
    )


def test_card_price_flashes_whiter_on_recent_change():
    cf, rf = _bigsign()
    draw_card_story(
        cf,
        _q(time.monotonic()),
        MarketState.OPEN,
        {},
        [],
        focus_index=0,
        total=1,
        frame=0,
    )
    cn, rn = _bigsign()
    draw_card_story(
        cn, _q(None), MarketState.OPEN, {}, [], focus_index=0, total=1, frame=0
    )
    assert _white_ish(rf) > _white_ish(
        rn
    )  # a fresh flash lights more white-ish (price) pixels


def test_dashboard_price_flashes_whiter_on_recent_change():
    cf, rf = _longboi()
    qf = _q(time.monotonic())
    draw_dashboard_story(
        cf,
        qf,
        MarketState.OPEN,
        {"AAPL": qf},
        ["AAPL"],
        focus_index=0,
        total=1,
        frame=0,
    )
    cn, rn = _longboi()
    qn = _q(None)
    draw_dashboard_story(
        cn,
        qn,
        MarketState.OPEN,
        {"AAPL": qn},
        ["AAPL"],
        focus_index=0,
        total=1,
        frame=0,
    )
    assert _white_ish(rf) > _white_ish(rn)


def test_crawl_price_flashes_whiter_on_recent_change():
    rf = _smallsign()
    draw_crawl_story(rf, _q(time.monotonic()), MarketState.OPEN, 0, frame=0)
    rn = _smallsign()
    draw_crawl_story(rn, _q(None), MarketState.OPEN, 0, frame=0)
    assert _white_ish(rf) > _white_ish(rn)
