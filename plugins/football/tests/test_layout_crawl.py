import re

from led_ticker.plugin import unwrap_to_real

from led_ticker_football import _palette as pal
from led_ticker_football._models import build_demo_games
from led_ticker_football.layouts.crawl import render_crawl, segments

NOW = 1_700_000_000.0
LIVE, HALF, FINAL_OT, NEXT, BYE = build_demo_games(NOW)[0]


def _lit(real):
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}


def _line(game, now, tz, **kw):
    return "".join(t for t, _ in segments(game, now, tz, **kw))


def test_segments_live_wording(tz):
    assert (
        _line(LIVE, NOW, tz)
        == "PHI 20 · NYG 17 · Q4 2:13 · NYG BALL 2ND & 7 · PHI 24 · TOL 1-2"
    )


def test_segments_halftime_and_final(tz):
    assert _line(HALF, NOW, tz) == "PHI 10 · NYG 10 · HALF"
    assert _line(FINAL_OT, NOW, tz) == "PHI 24 · NYG 27 · FINAL/OT"
    assert _line(FINAL_OT, NOW, tz, stale=True) == "PHI 24 · NYG 27 · FINAL/OT STALE"


def test_segments_future_tbd_and_bye(tz):
    pattern = (
        r"NYG 4-3 @ PHI 5-2 · SUN [A-Z]{3} \d{1,2} 1:00 PM · FOX · "
        r"LINCOLN FINANCIAL FIELD"
    )
    assert re.fullmatch(pattern, _line(NEXT, NOW, tz))
    assert "· BYE WEEK ·" in _line(BYE, NOW, tz, bye=True)
    import dataclasses

    tbd = dataclasses.replace(NEXT, time_tbd=True)
    assert " TBD · " in _line(tbd, NOW, tz)


def test_segment_colors(tz):
    by_text = dict(segments(LIVE, NOW, tz))
    assert by_text["2ND & 7"] == pal.CYAN
    assert by_text["Q4"] == pal.AMBER
    assert by_text[" 2:13"] == pal.WHITE
    import dataclasses

    red = dataclasses.replace(
        LIVE, situation=dataclasses.replace(LIVE.situation, red_zone=True)
    )
    assert dict(segments(red, NOW, tz))["2ND & 7"] == pal.RED


def test_render_crawl_held_when_fits(longboi, tz):
    real = unwrap_to_real(longboi)
    w = render_crawl(longboi, FINAL_OT, NOW, tz, 0)
    assert 0 < w <= longboi.width
    lit = _lit(real)
    assert lit
    assert min(x for x, _ in lit) > 0 and max(x for x, _ in lit) < real.width - 1


def test_render_crawl_scrolls_when_long(bigsign, tz):
    w = render_crawl(bigsign, LIVE, NOW, tz, 0)
    assert w > bigsign.width
