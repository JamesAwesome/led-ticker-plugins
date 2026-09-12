"""tests/test_layout_scoreboard.py — the physical (scale>1) scoreboard.

Pixel-separation regression (CONTRIBUTING.md layout invariant): every
hi-res text is recorded through a spy on `hires()` as its ADVANCE-width
extent — the same measure `hires_text_width`/`fit_text_size` use and the
one the renderer's own right-to-left column math is built on (advance
width != visible glyph width, so lit-pixel scanning under-counts the true
collision surface; the flight/stocks precedent). Assertions are
invariant-based, never exact freetype pins.
"""

from datetime import datetime, timedelta

import pytest
from led_ticker.plugin import unwrap_to_real

import led_ticker_tennis.layouts.scoreboard as board
from led_ticker_tennis._models import MatchInfo
from led_ticker_tennis.layouts.scoreboard import (
    _BIG,
    _LONG,
    _MIN_GAP,
    geometry_for,
    render_scoreboard,
)

from .conftest import TZ, lit, live_match

# Worst case: long doubles pairings, five sets of two-digit games (10-point
# match tiebreaks), AD/40 points with a break point on, the longest fixed
# status vocabulary and a long tournament name.
WORST = live_match(
    p1="Bopanna/Kokkinakis",
    p2="Gonzalez/Molteni",
    is_doubles=True,
    sets=(2, 2),
    games=[(10, 10), (10, 10), (10, 10), (10, 10), (10, 10)],
    points=("40", "AD"),
    server=1,
    round_code="R128",
    tournament="Australian Open Championships",
)


_ORIG_HIRES = board.hires  # captured once: nested spies must not chain


def _spy_extents(monkeypatch, canvas, m, **kw):
    """Render, recording every hires() call as (text, x0, x1, y_top, size)."""
    calls = []

    def spy(shim, text, x, y_top, color, size):
        adv = _ORIG_HIRES(shim, text, x, y_top, color, size)
        calls.append((text, x, x + adv, y_top, size))
        return adv

    monkeypatch.setattr(board, "hires", spy)
    render_scoreboard(canvas, m, TZ, **kw)
    return calls


def _bands_overlap(a, b):
    return a[3] < b[3] + b[4] and b[3] < a[3] + a[4]


def _assert_separated(calls, real):
    """Any two texts sharing a vertical band keep >= _MIN_GAP px between
    their advance extents; nothing runs past the panel's right margin."""
    for i, a in enumerate(calls):
        assert a[1] >= 0, f"{a[0]!r} starts off-panel"
        assert a[2] <= real.width - _MIN_GAP, f"{a[0]!r} overflows the right margin"
        for b in calls[i + 1 :]:
            if not _bands_overlap(a, b):
                continue
            left, right = (a, b) if a[1] <= b[1] else (b, a)
            gap = right[1] - left[2]
            assert gap >= _MIN_GAP, (
                f"{left[0]!r} ends at {left[2]}, {right[0]!r} starts at {right[1]}: "
                f"gap {gap} < {_MIN_GAP}"
            )


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_worst_case_keeps_min_clearance(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls = _spy_extents(monkeypatch, canvas, WORST)
    _assert_separated(calls, unwrap_to_real(canvas))
    texts = [c[0] for c in calls]
    assert "BP" in texts and "SET 5" in texts and "R128" in texts


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_every_state_keeps_min_clearance(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    start = datetime.now(TZ) + timedelta(days=1)
    cases = [
        live_match(),
        live_match(games=[(6, 6)], points=("5", "6"), is_tiebreak=True, server=2),
        live_match(state="final", outcome="retired", winner=1, games=[(6, 2), (3, 1)]),
        live_match(state="upcoming", games=[], points=(None, None), start_time=start),
        live_match(state="upcoming", games=[], points=(None, None), start_time=None),
        live_match(event_status="Interrupted"),
        MatchInfo(),  # sparse: nothing known
    ]
    for m in cases:
        real = unwrap_to_real(canvas)
        real.Clear()
        calls = _spy_extents(monkeypatch, canvas, m)
        _assert_separated(calls, real)


def test_serve_pip_clears_the_name_on_both_geometries():
    for g in (_BIG, _LONG):
        assert g.name_x - (g.dot_cx + g.dot_r) >= _MIN_GAP


def test_geometry_picks_by_physical_width():
    assert geometry_for(256) is _BIG
    assert geometry_for(512) is _LONG
    assert geometry_for(399) is _BIG and geometry_for(400) is _LONG


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_names_are_row_uniform_and_short_names_keep_design_size(
    sign, request, monkeypatch
):
    canvas = request.getfixturevalue(sign)
    g = geometry_for(unwrap_to_real(canvas).width)
    calls = _spy_extents(monkeypatch, canvas, live_match())
    sizes = {c[0]: c[4] for c in calls if c[0] in ("LEHECKA", "FILS")}
    assert sizes == {"LEHECKA": g.row_size, "FILS": g.row_size}
    real = unwrap_to_real(canvas)
    real.Clear()
    calls = _spy_extents(monkeypatch, canvas, WORST)
    name_sizes = {c[4] for c in calls if c[0].startswith(("BOPANNA", "GONZALEZ"))}
    assert len(name_sizes) == 1, "both names must share one size"


def test_bigsign_shrinks_or_ellipsizes_an_overlong_name(bigsign, monkeypatch):
    calls = _spy_extents(monkeypatch, bigsign, WORST)
    names = [c for c in calls if c[0].startswith(("BOPANNA", "GONZALEZ"))]
    assert names and (names[0][4] < _BIG.row_size or names[0][0].endswith("…"))


def test_longboi_shows_every_set_bigsign_shows_sets_and_current_games(
    longboi, bigsign, monkeypatch
):
    m = live_match(games=[(6, 3), (4, 6), (2, 2)], points=("40", "AD"), sets=(1, 1))
    long_calls = _spy_extents(monkeypatch, longboi, m)
    row1 = [c[0] for c in long_calls if c[3] == long_calls[0][3] and c[0] != "LEHECKA"]
    assert row1[:4] == ["6", "4", "2", "40"]  # three sets + points
    big_calls = _spy_extents(monkeypatch, bigsign, m)
    row1 = [c[0] for c in big_calls if c[3] == big_calls[0][3] and c[0] != "LEHECKA"]
    assert row1[:3] == ["1", "2", "40"]  # sets won, current games, points


def test_bp_badge_only_on_receiver_row(longboi, monkeypatch):
    calls = _spy_extents(monkeypatch, longboi, live_match())  # server 1 -> receiver 2
    bp = [c for c in calls if c[0] == "BP"]
    fils = next(c for c in calls if c[0] == "FILS")
    assert len(bp) == 1 and _bands_overlap(bp[0], fils)
    real = unwrap_to_real(longboi)
    real.Clear()
    calls = _spy_extents(
        monkeypatch, longboi, live_match(server=2, points=("40", "15"))
    )
    bp = [c for c in calls if c[0] == "BP"]
    lehecka = next(c for c in calls if c[0] == "LEHECKA")
    assert len(bp) == 1 and _bands_overlap(bp[0], lehecka)


def test_no_bp_in_tiebreak_or_final(longboi, monkeypatch):
    tb = live_match(games=[(6, 6)], points=("6", "6"), is_tiebreak=True)
    texts = [c[0] for c in _spy_extents(monkeypatch, longboi, tb)]
    assert "BP" not in texts and "TB" in texts and "6" in texts
    unwrap_to_real(longboi).Clear()
    fin = live_match(
        state="final", outcome="completed", winner=2, games=[(4, 6), (3, 6)]
    )
    texts = [c[0] for c in _spy_extents(monkeypatch, longboi, fin)]
    assert "BP" not in texts and "FINAL" in texts and "R16" in texts
    assert not any(t in ("15", "40") for t in texts), "no points on a final"


def test_serve_pip_drawn_for_server_only(longboi):
    render_scoreboard(longboi, live_match(server=1), TZ)
    real = unwrap_to_real(longboi)
    yellow = {xy for xy, v in real._pixels.items() if v == (255, 217, 0)}
    assert yellow and all(x < _LONG.name_x for x, _ in yellow)
    ys = {y for _, y in yellow}
    assert max(ys) < _LONG.row_y[1], "pip sits in row 1 (server 1)"
    real.Clear()
    render_scoreboard(longboi, live_match(state="final", winner=1), TZ)
    assert not {xy for xy, v in real._pixels.items() if v == (255, 217, 0)}


def test_upcoming_shows_day_and_time_lines(bigsign, monkeypatch):
    start = datetime.now(TZ) + timedelta(days=1)
    m = live_match(state="upcoming", games=[], points=(None, None), start_time=start)
    texts = [c[0] for c in _spy_extents(monkeypatch, bigsign, m)]
    assert "Tmrw" in texts and any(t.endswith(("AM", "PM")) for t in texts)
    unwrap_to_real(bigsign).Clear()
    m.start_time = None
    texts = [c[0] for c in _spy_extents(monkeypatch, bigsign, m)]
    assert "NEXT" in texts and "TBD" in texts


def test_winner_rows_are_green_loser_dim(longboi):
    render_scoreboard(longboi, live_match(state="final", winner=1, games=[(6, 2)]), TZ)
    real = unwrap_to_real(longboi)
    green = {xy for xy, v in real._pixels.items() if v == (60, 220, 60)}
    dim = {xy for xy, v in real._pixels.items() if v == (165, 185, 220)}
    assert green and dim
    assert max(y for _, y in green if _ < 300) < min(y for _, y in dim if _ < 300)


def test_y_offset_shifts_everything(longboi, monkeypatch):
    a = _spy_extents(monkeypatch, longboi, live_match())
    unwrap_to_real(longboi).Clear()
    b = _spy_extents(monkeypatch, longboi, live_match(), y_offset=8)
    assert [(c[0], c[3] + 32) for c in a] == [(c[0], c[3]) for c in b]


def test_story_paging_args_do_not_change_output(longboi):
    render_scoreboard(longboi, live_match(), TZ, story_index=0, story_total=1)
    real = unwrap_to_real(longboi)
    one = lit(real)
    real.Clear()
    render_scoreboard(longboi, live_match(), TZ, story_index=1, story_total=5)
    assert lit(real) == one
