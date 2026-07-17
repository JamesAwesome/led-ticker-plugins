"""tests/test_card_dispatch.py — MLBGameCard scale dispatch.

HeadlessBackend takes (width, height) positionally (see
led_ticker/backends/headless.py) — there is no rows/cols/chain_length kwarg
surface (that's an RgbMatrixBackend shape); mirrors the precedent already
established in test_layout_two_row.py.
"""

from zoneinfo import ZoneInfo

from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball._card import MLBGameCard
from led_ticker_baseball._models import GameInfo

TZ = ZoneInfo("America/New_York")


def _card(layout="auto", **g_over):
    g = GameInfo(
        away_abbr="TB",
        home_abbr="BOS",
        away_score=0,
        home_score=10,
        state="live",
        inning="▼8",
        balls=1,
        strikes=2,
        outs=1,
        on_first=True,
        on_second=False,
        on_third=False,
        **g_over,
    )
    return MLBGameCard(
        game=g, team_abbr="BOS", tz=TZ, cfg_layout=layout, story_index=0, story_total=3
    )


def _bigsign():
    real = HeadlessBackend(256, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _longboi():
    real = HeadlessBackend(512, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16), real


def _smallsign():
    return HeadlessBackend(160, 16).create_canvas()


def test_auto_on_bigsign_holds_two_row_card():
    canvas, real = _bigsign()
    out, cursor = _card().draw(canvas)
    assert cursor == 256  # held: cursor = physical width
    assert any(real.get_pixel(x, 31) != (0, 0, 0) for x in range(4, 252))  # divider


def test_auto_on_longboi_holds_scoreboard():
    canvas, real = _longboi()
    out, cursor = _card().draw(canvas)
    assert cursor == 512


def test_ticker_on_bigsign_scrolls_hires_crawl():
    canvas, real = _bigsign()
    out, cursor = _card(layout="ticker").draw(canvas)
    assert cursor > 256  # advance width, engine will scroll


def test_scale1_delegates_to_legacy():
    real = _smallsign()
    out, cursor = _card(layout="ticker").draw(real)
    assert cursor > 0  # legacy SegmentMessage cursor contract


def test_frame_hooks_never_raise_before_first_draw():
    c = _card()
    c.advance_frame()
    c.pause_frame()
    c.resume_frame()
    c.reset_frame()
