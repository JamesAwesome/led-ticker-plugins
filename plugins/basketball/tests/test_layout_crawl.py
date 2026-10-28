import dataclasses
import re

from led_ticker.plugin import unwrap_to_real

from led_ticker_basketball import _palette as pal
from led_ticker_basketball._models import build_demo_games
from led_ticker_basketball.layouts.crawl import render_crawl, segments

NOW = 1_700_000_000.0
LIVE, HALF, FINAL_OT, NEXT = build_demo_games(NOW)[0]


def _lit(real):
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}


def _line(game, now, tz, **kw):
    return "".join(t for t, _ in segments(game, now, tz, **kw))


def test_segments_live_wording(tz):
    assert (
        _line(LIVE, NOW, tz)
        == "PHI 98 · NY 101 · Q4 1:48 · J. EMBIID 31 · J. BRUNSON 28"
    )
    by_text = dict(segments(LIVE, NOW, tz))
    assert by_text["Q4"] == pal.AMBER
    assert by_text[" 1:48"] == pal.RED  # clutch
    assert by_text["J. EMBIID 31"] == pal.CYAN
    calm = dataclasses.replace(LIVE, clock="7:12")
    assert dict(segments(calm, NOW, tz))[" 7:12"] == pal.WHITE


def test_segments_omit_missing_leaders(tz):
    one = dataclasses.replace(LIVE, home_leader=None)
    assert _line(one, NOW, tz) == "PHI 98 · NY 101 · Q4 1:48 · J. EMBIID 31"
    none = dataclasses.replace(LIVE, away_leader=None, home_leader=None)
    assert _line(none, NOW, tz) == "PHI 98 · NY 101 · Q4 1:48"
    assert _line(HALF, NOW, tz) == "PHI 54 · NY 52 · HALF"
    assert _line(none, NOW, tz, stale=True) == "PHI 98 · NY 101 · Q4 1:48 STALE"


def test_segments_final_ot(tz):
    assert _line(FINAL_OT, NOW, tz) == "PHI 115 · NY 118 · FINAL/OT"
    assert _line(FINAL_OT, NOW, tz, stale=True) == "PHI 115 · NY 118 · FINAL/OT STALE"
    reg = dataclasses.replace(FINAL_OT, final_ot=False)
    assert _line(reg, NOW, tz) == "PHI 115 · NY 118 · FINAL"


def test_segments_future_with_records(tz):
    pattern = (
        r"NY 4-3 @ PHI 5-2 · [A-Z]{3} [A-Z]{3} \d{1,2} 7:30 PM · ESPN · "
        r"XFINITY MOBILE ARENA"
    )
    assert re.fullmatch(pattern, _line(NEXT, NOW, tz))
    by_text = dict(segments(NEXT, NOW, tz))
    assert by_text["NY"] == pal.chip("NY")[0]
    assert by_text[" 4-3"] == pal.GRAY
    neutral = dataclasses.replace(NEXT, neutral_site=True)
    assert " VS " in _line(neutral, NOW, tz)
    tbd = dataclasses.replace(NEXT, time_tbd=True)
    assert " TBD · " in _line(tbd, NOW, tz)


def test_render_crawl_held_when_fits(longboi, tz):
    # The final is the shortest line; at 28-30 px Inter it is wider than the
    # bigsign's 256 px, so the held case is exercised on the 512 px longboi.
    real = unwrap_to_real(longboi)
    w = render_crawl(longboi, FINAL_OT, NOW, tz, 0)
    assert 0 < w <= longboi.width - 6
    lit = _lit(real)
    assert lit
    assert min(x for x, _ in lit) > 0 and max(x for x, _ in lit) < real.width - 1


def test_render_crawl_scrolls_when_long(bigsign, tz):
    w = render_crawl(bigsign, LIVE, NOW, tz, 0)
    assert w > bigsign.width


def test_render_crawl_honours_cursor_pos(bigsign, tz):
    from led_ticker.plugin import HeadlessBackend, ScaledCanvas

    render_crawl(bigsign, LIVE, NOW, tz, 0)
    lit0 = _lit(unwrap_to_real(bigsign))
    assert lit0
    real = HeadlessBackend(256, 64).create_canvas()
    render_crawl(ScaledCanvas(real, scale=4, content_height=16), LIVE, NOW, tz, 10)
    assert _lit(real) == {(x + 40, y) for x, y in lit0 if x + 40 < 256}
