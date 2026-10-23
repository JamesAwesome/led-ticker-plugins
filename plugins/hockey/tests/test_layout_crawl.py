import re

from led_ticker.plugin import unwrap_to_real

from led_ticker_hockey._models import build_demo_games
from led_ticker_hockey.layouts.crawl import render_crawl, segments

NOW = 1_700_000_000.0


def _lit(real):
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}


def _line(game, now, tz):
    return "".join(t for t, _ in segments(game, now, tz))


def test_segments_live_wording(tz):
    live = build_demo_games(NOW)[0]
    assert _line(live, NOW, tz) == "PHI 2 · NYI 1 · 2ND 12:34 · NYI PP 1:42 · SOG 18-22"


def test_segments_final_and_future(tz):
    _, _, final, future = build_demo_games(NOW)
    assert _line(final, NOW, tz) == "PHI 3 · NYI 2 · FINAL/OT"
    assert re.fullmatch(
        r"PHI @ NYI · [A-Z]{3} [A-Z]{3} \d{1,2} 7:00 PM · UBS ARENA",
        _line(future, NOW, tz),
    )


def test_segment_colors(tz):
    from led_ticker_hockey import _palette as pal

    live = build_demo_games(NOW)[0]
    by_text = dict(segments(live, NOW, tz))
    assert by_text["SOG 18-22"] == pal.CYAN
    assert by_text["2ND"] == pal.AMBER
    assert by_text["12:34"] == pal.WHITE


def test_render_returns_logical_advance_and_paints(bigsign, tz):
    live = build_demo_games(NOW)[0]
    adv = render_crawl(bigsign, live, NOW, tz, 0)
    assert adv > 64 and _lit(unwrap_to_real(bigsign))


def test_cursor_is_logical(longboi, tz):
    fut = build_demo_games(NOW)[3]
    render_crawl(longboi, fut, NOW, tz, 0)
    real = unwrap_to_real(longboi)
    a = min(x for x, _ in _lit(real))
    real.Clear()
    render_crawl(longboi, fut, NOW, tz, 5)
    assert min(x for x, _ in _lit(real)) - a == 20


def test_short_line_is_centered_when_held(longboi, tz):
    final = build_demo_games(NOW)[2]
    adv = render_crawl(longboi, final, NOW, tz, 0, hold_padding=6)
    assert adv + 6 <= longboi.width
    xs = [x for x, _ in _lit(unwrap_to_real(longboi))]
    assert min(xs) > 40 and max(xs) < 512 - 40


def test_y_offset_shifts_rows(bigsign, tz):
    live = build_demo_games(NOW)[0]
    render_crawl(bigsign, live, NOW, tz, 0)
    real = unwrap_to_real(bigsign)
    top = min(y for _, y in _lit(real))
    real.Clear()
    render_crawl(bigsign, live, NOW, tz, 0, y_offset=2)
    assert min(y for _, y in _lit(real)) == top + 8


LIVE_G, _INT_G, FINAL_G, NEXT_G = build_demo_games(NOW)


def test_segments_stale_follows_status(tz):
    from led_ticker_hockey import _palette as pal

    for g in (LIVE_G, FINAL_G, NEXT_G):
        plain = segments(g, NOW, tz)
        stale = segments(g, NOW, tz, stale=True)
        assert len(stale) == len(plain) + 1
        i = next(i for i, s in enumerate(stale) if s[0] == " STALE")
        assert stale[i][1] == pal.DIM
        assert stale[:i] + stale[i + 1 :] == plain
        # right after the status run: nothing but separators/detail follow
        assert i == len(plain) or stale[i + 1][0] == " · "
