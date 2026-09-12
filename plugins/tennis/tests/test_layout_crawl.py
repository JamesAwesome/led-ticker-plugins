"""Hi-res crawl: wording shared with the legacy ticker, the engine cursor
contract (logical units), held-line centering."""

from datetime import datetime, timedelta

from led_ticker.plugin import unwrap_to_real

from led_ticker_tennis.layouts.crawl import render_crawl, segments

from .conftest import TZ, lit, live_match


def _texts(m, **kw):
    return [t for t, _ in segments(m, TZ, **kw)]


def test_live_segments_read_as_tennis_notation():
    assert _texts(live_match()) == [
        "LEHECKA", "*", "v", "FILS", "4-6 3-4", "(15-40)", "BP", "·", "SET 2", "·",
        "R16 CINCINNATI OPEN",
    ]  # fmt: skip


def test_server_marker_follows_the_serving_player():
    assert _texts(live_match(server=2))[:5] == ["LEHECKA", "v", "FILS", "*", "4-6 3-4"]


def test_tiebreak_and_no_bp():
    m = live_match(games=[(6, 6)], points=("5", "6"), is_tiebreak=True)
    t = _texts(m)
    assert "TB" in t and "BP" not in t and "(5-6)" in t


def test_final_and_upcoming_wording():
    fin = live_match(state="final", outcome="walkover", winner=2, games=[])
    t = _texts(fin)
    assert "W/O" in t and "*" not in t and not any(s.startswith("(") for s in t)
    start = (datetime.now(TZ) + timedelta(days=1)).replace(hour=15, minute=0)
    up = live_match(state="upcoming", games=[], points=(None, None), start_time=start)
    assert _texts(up)[:5] == [
        "ALCARAZ" if False else "LEHECKA",
        "v",
        "FILS",
        "·",
        "Tmrw 3:00 PM",
    ]


def test_show_ranking_appends_rank():
    assert _texts(live_match(), show_ranking=True)[0] == "LEHECKA (21)"
    assert _texts(live_match(p1_rank=None), show_ranking=True)[0] == "LEHECKA"


def test_sparse_match_never_raises(bigsign):
    from led_ticker_tennis._models import MatchInfo

    assert render_crawl(bigsign, MatchInfo(), TZ, 0) > 0


def test_render_returns_logical_advance_and_paints(bigsign):
    adv = render_crawl(bigsign, live_match(), TZ, 0)
    real = unwrap_to_real(bigsign)
    assert adv > 64 and lit(real)  # wider than the 64-logical bigsign: scrolls


def test_cursor_is_logical_and_shifts_paint(longboi):
    m = live_match(state="upcoming", games=[], points=(None, None))
    render_crawl(longboi, m, TZ, 0)
    real = unwrap_to_real(longboi)
    a = min(x for x, _ in lit(real))
    real.Clear()
    render_crawl(longboi, m, TZ, 5)
    b = min(x for x, _ in lit(real))
    assert b - a == 20  # 5 logical * scale 4


def test_short_line_is_centered_when_held(longboi):
    m = live_match(
        state="upcoming", games=[], points=(None, None), tournament="", round_code=""
    )
    adv = render_crawl(longboi, m, TZ, 0, hold_padding=6)
    assert adv + 6 <= longboi.width
    xs = [x for x, _ in lit(unwrap_to_real(longboi))]
    assert min(xs) > 40 and max(xs) < 512 - 40


def test_y_offset_shifts_rows(bigsign):
    render_crawl(bigsign, live_match(), TZ, 0)
    real = unwrap_to_real(bigsign)
    top = min(y for _, y in lit(real))
    real.Clear()
    render_crawl(bigsign, live_match(), TZ, 0, y_offset=2)
    assert min(y for _, y in lit(real)) == top + 8
