"""The physical (scale>1) horizontal arena scoreboard with team logos.

Every hi-res text is recorded through a spy on `hires()` as its ADVANCE
extent plus its cap band (baseline - 0.72*size .. baseline), the same
measure the renderer lays out with; shapes (logo sprites, fallback chips)
through spies on `paint_logo` / `rect`. Assertions are invariant-based
(extents, bands, colors), never exact freetype pins.
"""

import dataclasses
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from led_ticker.plugin import resolve_font, unwrap_to_real

import led_ticker_basketball.layouts.scoreboard as board
from led_ticker_basketball import _palette as pal
from led_ticker_basketball._logos import LOGO_BIG, LOGO_LONG
from led_ticker_basketball._models import GameInfo, Leader, build_demo_games
from led_ticker_basketball.layouts.scoreboard import (
    _BIG,
    _LONG,
    _MIN_GAP,
    geometry_for,
    render_scoreboard,
)

from .conftest import TZ

NOW = 1_700_000_000.0  # 2023-11-14 17:13 America/New_York
GAMES, _CELEBRATION = build_demo_games(NOW)
LIVE, HALF, FINAL_OT, NEXT = GAMES

WORST_LIVE = dataclasses.replace(
    LIVE,
    away="UTAH",
    home="WSH",
    away_score=148,
    home_score=148,
    period=4,
    clock="0:00.0",
    status="STATUS_IN_PROGRESS",
    away_leader=Leader("G. ANTETOKOUNMPO", 50),
    home_leader=Leader("S. GILGEOUS-ALEXANDER", 49),
    away_linescores=(30, 30, 30, 30, 14, 14),
    home_linescores=(30, 30, 30, 30, 14, 14),
)
WORST_ENDQ = dataclasses.replace(
    WORST_LIVE, status="STATUS_END_PERIOD", period=3, clock="0:00"
)
WORST_FINAL = dataclasses.replace(
    WORST_LIVE,
    state="final",
    status="STATUS_FINAL",
    period=6,
    home_score=147,
    final_ot=True,
)
WORST_NEXT = dataclasses.replace(
    NEXT,
    away="UTAH",
    home="WSH",
    away_record="10-7",
    home_record="10-7",
    time_tbd=True,
    venue="Capital One Arena at Gallery Place Chinatown",
)
WORST = {
    "live": (WORST_LIVE, True),
    "endq": (WORST_ENDQ, False),
    "final": (WORST_FINAL, True),
    "next": (WORST_NEXT, False),
}
SPARSE = GameInfo(
    game_id="9",
    state="live",
    status="",
    away="PHI",
    home="NY",
    away_score=0,
    home_score=0,
    period=0,
    clock="",
    start_utc=None,
    time_tbd=False,
    venue="",
    broadcast="",
    away_record="",
    home_record="",
    final_ot=False,
    neutral_site=False,
)

_ORIG_HIRES = board.hires
_ORIG_RECT = board.rect
_ORIG_LOGO = board.paint_logo


def _spy(monkeypatch, canvas, game, **kw):
    """Render; record (text, x0, x1, cap_top, base, color, size) per hires call."""
    calls = []

    def spy(shim, text, x, y_top, color, size):
        adv = _ORIG_HIRES(shim, text, x, y_top, color, size)
        base = y_top + resolve_font("Inter-Bold", size).ascent
        calls.append((text, x, x + adv, base - round(size * 0.72), base, color, size))
        return adv

    monkeypatch.setattr(board, "hires", spy)
    render_scoreboard(canvas, game, NOW, TZ, **kw)
    return calls


def _spy_all(monkeypatch, canvas, game, **kw):
    """Texts (as `_spy`) plus shapes, each as (label, x0, x1_excl, top, bottom)."""
    shapes = []
    orig_rect, orig_logo = _ORIG_RECT, _ORIG_LOGO

    def rect_spy(real, x0, y0, x1, y1, color):
        shapes.append((f"rect@{x0}", x0, x1 + 1, y0, y1))
        orig_rect(real, x0, y0, x1, y1, color)

    def logo_spy(real, sprite, x, y):
        shapes.append(("LOGO", x, x + sprite.size, y, y + sprite.size))
        orig_logo(real, sprite, x, y)

    monkeypatch.setattr(board, "rect", rect_spy)
    monkeypatch.setattr(board, "paint_logo", logo_spy)
    return _spy(monkeypatch, canvas, game, **kw), shapes


def _assert_clear(calls, shapes, real):
    """Every box on-panel; >= _MIN_GAP between any two boxes (texts AND
    shapes) whose vertical bands overlap. A chip's two tone rects overlap
    by design."""
    boxes = [(c[0], c[1], c[2], c[3], c[4]) for c in calls] + list(shapes)
    for name, x0, x1, top, bottom in boxes:
        assert x0 >= 0 and x1 <= real.width, f"{name!r} {x0}..{x1} off-panel"
        assert top >= 0 and bottom < real.height + 1, f"{name!r} off-panel vertically"
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            if a[3] > b[4] or b[3] > a[4]:
                continue  # different rows
            if a[0].startswith("rect@") and b[0] == a[0]:
                continue  # one chip's two tones
            left, right = (a, b) if a[1] <= b[1] else (b, a)
            gap = right[1] - left[2]
            assert gap >= _MIN_GAP, (
                f"{left[0]!r} ends {left[2]}, {right[0]!r} starts {right[1]}: "
                f"gap {gap} < {_MIN_GAP}"
            )


def _texts(calls):
    return [c[0] for c in calls]


def _by(calls):
    return {c[0]: c for c in calls}


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
@pytest.mark.parametrize("case", list(WORST))
@pytest.mark.parametrize("logos", [True, False])
def test_worst_case_keeps_min_clearance(sign, case, logos, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    game, stale = WORST[case]
    calls, shapes = _spy_all(monkeypatch, canvas, game, stale=stale, logos=logos)
    assert calls and shapes
    if stale:
        assert "STALE" in _texts(calls)
    _assert_clear(calls, shapes, unwrap_to_real(canvas))


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
@pytest.mark.parametrize("game", GAMES, ids=lambda g: g.game_id)
@pytest.mark.parametrize("logos", [True, False])
def test_demo_cards_keep_min_clearance(sign, game, logos, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls, shapes = _spy_all(monkeypatch, canvas, game, stale=True, logos=logos)
    _assert_clear(calls, shapes, unwrap_to_real(canvas))


def test_worst_live_shows_the_essentials(bigsign, longboi, monkeypatch):
    for canvas in (bigsign, longboi):
        texts = _texts(_spy(monkeypatch, canvas, WORST_LIVE))
        assert texts.count("148") == 2
        assert "Q4" in texts and "0:00.0" in texts


def test_geometry_picks_by_physical_width():
    assert geometry_for(256) is _BIG
    assert geometry_for(399) is _BIG
    assert geometry_for(400) is _LONG
    assert geometry_for(512) is _LONG


@pytest.mark.parametrize(
    ("sign", "geom", "size"),
    [("bigsign", _BIG, LOGO_BIG), ("longboi", _LONG, LOGO_LONG)],
)
def test_logos_painted_on_both_sides(sign, geom, size, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    for game in (LIVE, NEXT):
        _, shapes = _spy_all(monkeypatch, canvas, game)
        logos = [s for s in shapes if s[0] == "LOGO"]
        assert [s[1] for s in logos] == [geom.logo_x[0], geom.logo_x[1]]
        assert all(s[2] - s[1] == size for s in logos)
        assert not [s for s in shapes if s[0].startswith("rect")]


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_logos_false_paints_chips_and_abbrevs(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls, shapes = _spy_all(monkeypatch, canvas, LIVE, logos=False)
    assert not [s for s in shapes if s[0] == "LOGO"]
    chips = {s[0] for s in shapes if s[0].startswith("rect")}
    assert len(chips) == 2  # one (two-tone) chip per side
    by = _by(calls)
    assert by["PHI"][5] == pal.chip("PHI")[0]
    assert by["NY"][5] == pal.chip("NY")[0]
    real = unwrap_to_real(canvas)
    assert by["PHI"][2] <= real.width // 2 < by["NY"][1]


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_missing_sprite_falls_back_to_chip(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    monkeypatch.setattr(board, "sprite", lambda abbrev, size: None)
    calls, shapes = _spy_all(monkeypatch, canvas, LIVE)
    assert not [s for s in shapes if s[0] == "LOGO"]
    assert len({s[0] for s in shapes if s[0].startswith("rect")}) == 2
    assert "PHI" in _texts(calls) and "NY" in _texts(calls)


def test_logo_helper_reports_whether_it_painted(bigsign):
    real = unwrap_to_real(bigsign)
    assert board._logo(real, "PHI", LOGO_BIG, 4, 14, True) is True
    assert board._logo(real, "PHI", LOGO_BIG, 4, 14, False) is False
    assert board._logo(real, "ZZZ", LOGO_BIG, 4, 14, True) is False


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_clutch_clock_is_red(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    by = _by(_spy(monkeypatch, canvas, LIVE))  # Q4 1:48, 98-101: clutch
    assert by["1:48"][5] == pal.RED
    assert by["Q4"][5] == pal.AMBER
    unwrap_to_real(canvas).Clear()
    calm = dataclasses.replace(LIVE, clock="9:12")
    by = _by(_spy(monkeypatch, canvas, calm))
    assert by["9:12"][5] == pal.WHITE


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_no_clock_statuses_take_the_clock_slot_in_amber(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    by = _by(_spy(monkeypatch, canvas, HALF))
    assert by["HALF"][5] == pal.AMBER
    assert "Q2" not in by and "0.0" not in by
    unwrap_to_real(canvas).Clear()
    by = _by(_spy(monkeypatch, canvas, WORST_ENDQ))
    assert by["END Q3"][5] == pal.AMBER and "0:00" not in by


def _box_colors(real, call):
    _, x0, x1, top, base, _, _ = call
    return {
        real.get_pixel(x, y) for x in range(x0, x1) for y in range(top, base + 1)
    } - {(0, 0, 0)}


def _rgb(c):
    return (c.red, c.green, c.blue)


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_final_scores_colored_and_ot_shown(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls = _spy(monkeypatch, canvas, FINAL_OT)  # PHI 115 @ NY 118, OT
    real = unwrap_to_real(canvas)
    by = _by(calls)
    assert _box_colors(real, by["118"]) == {_rgb(pal.GREEN)}
    assert _box_colors(real, by["115"]) == {_rgb(pal.LOSER)}
    assert by["FINAL"][5] == pal.WHITE
    assert by["OT"][5] == pal.AMBER
    assert by["OT"][3] > by["FINAL"][4]  # beneath
    unwrap_to_real(canvas).Clear()
    texts = _texts(_spy(monkeypatch, canvas, WORST_FINAL))  # period 6
    assert "2OT" in texts


@pytest.mark.parametrize(
    ("sign", "away", "home"),
    [
        ("bigsign", "EMBIID 31", "BRUNSON 28"),
        ("longboi", "J. EMBIID 31 PTS", "J. BRUNSON 28 PTS"),
    ],
)
def test_leader_lines_present_and_cyan(sign, away, home, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    by = _by(_spy(monkeypatch, canvas, LIVE))
    assert by[away][5] == pal.CYAN and by[home][5] == pal.CYAN
    real = unwrap_to_real(canvas)
    assert by[away][2] <= real.width // 2 <= by[home][1]


def test_longboi_side_line_carries_abbrev_and_record(longboi, monkeypatch):
    by = _by(_spy(monkeypatch, longboi, LIVE))
    assert by["5-2"][5] == pal.GRAY and by["4-3"][5] == pal.GRAY
    assert by["PHI"][5] == pal.chip("PHI")[0]


def test_bigsign_leader_dropped_rather_than_tiny(bigsign, monkeypatch):
    huge = dataclasses.replace(
        LIVE, away_leader=Leader("X. " + "W" * 30, 50), home_leader=None
    )
    calls = _spy(monkeypatch, bigsign, huge)
    assert not [c for c in calls if c[5] == pal.CYAN]


def test_longboi_side_line_ellipsizes_leader_then_drops():
    """Shrinking budgets walk the fit order: full line -> leader ellipsized
    (record kept) -> record dropped -> leader dropped (record back) -> abbrev."""
    leader = "X. WWWWWWWWWWWW 50 PTS"

    def texts(budget):
        return [t for t, _ in board._side_pieces("PHI", "5-2", leader, budget)]

    assert texts(300) == ["PHI", "5-2", "·", leader]
    cut = texts(120)
    assert cut[:3] == ["PHI", "5-2", "·"] and len(cut) == 4
    assert cut[3].endswith("…") and len(cut[3].rstrip("…")) >= board._LEADER_KEEP
    no_rec = texts(100)
    assert no_rec[:2] == ["PHI", "·"] and len(no_rec) == 3
    assert no_rec[2].endswith("…") and len(no_rec[2].rstrip("…")) >= board._LEADER_KEEP
    assert texts(80) == ["PHI", "5-2"]
    assert texts(20) == ["PHI"]
    for budget in (300, 120, 100, 80, 20):
        pieces = board._side_pieces("PHI", "5-2", leader, budget)
        w = sum(board.text_width(board._SIDE_SIZE, t) for t, _ in pieces)
        assert w + _MIN_GAP * (len(pieces) - 1) <= budget


def test_longboi_linescore_strip_orange_and_dropped_when_narrow(longboi, monkeypatch):
    by = _by(_spy(monkeypatch, longboi, LIVE))
    strip = "24-28 · 26-24 · 25-27 · 23-22"
    assert by[strip][5] == pal.ORANGE
    unwrap_to_real(longboi).Clear()
    texts = _texts(_spy(monkeypatch, longboi, WORST_LIVE))  # six periods
    assert not [t for t in texts if "30-30" in t]
    unwrap_to_real(longboi).Clear()
    none = dataclasses.replace(LIVE, away_linescores=(), home_linescores=())
    calls = _spy(monkeypatch, longboi, none)
    assert not [c for c in calls if c[5] == pal.ORANGE]


def test_bigsign_has_no_linescore_strip(bigsign, monkeypatch):
    calls = _spy(monkeypatch, bigsign, LIVE)
    assert not [c for c in calls if c[5] == pal.ORANGE]


def _tonight_game():
    start = datetime(2023, 11, 14, 20, 15, tzinfo=ZoneInfo("America/New_York"))
    return dataclasses.replace(NEXT, start_utc=start.astimezone(UTC))


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_next_game_shows_records_day_and_label(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls = _spy(monkeypatch, canvas, _tonight_game())
    by = _by(calls)
    assert by["TONIGHT"][5] == pal.AMBER and by["8:15 PM"][5] == pal.WHITE
    assert "XFINITY MOBILE ARENA" in by
    assert "NY" in by and "PHI" in by
    assert by["4-3"][5] == pal.GRAY and by["5-2"][5] == pal.GRAY
    assert by["NEXT GAME"][5] == pal.GRAY
    assert not [c for c in calls if c[0].isdigit()]  # no scores
    unwrap_to_real(canvas).Clear()
    by = _by(_spy(monkeypatch, canvas, WORST_NEXT))
    assert by["TBD"][5] == pal.DIM
    unwrap_to_real(canvas).Clear()
    ppd = dataclasses.replace(NEXT, status="STATUS_POSTPONED")
    texts = _texts(_spy(monkeypatch, canvas, ppd))
    assert "PPD" in texts and "NEXT GAME" not in texts


def test_longboi_next_day_clears_the_label(longboi, monkeypatch):
    """No names to narrow the centre column: the day line, whose band
    touches the label's, still starts >= _MIN_GAP past the label."""
    game = dataclasses.replace(
        WORST_NEXT, away="", home="", away_record="", home_record=""
    )
    monkeypatch.setattr(
        board, "status_lines", lambda *a: ("WEDNESDAY NOVEMBER 15TH " * 3, "TBD")
    )
    by = _by(_spy(monkeypatch, longboi, game, logos=False))
    label = by["NEXT GAME"]
    day = next(c for c in by.values() if c[0].startswith("WEDNESDAY"))
    assert day[1] - label[2] >= _MIN_GAP


def test_next_game_longboi_nicknames(longboi, monkeypatch):
    by = _by(_spy(monkeypatch, longboi, NEXT))
    assert by["KNICKS"][5] == pal.dim(pal.chip("NY")[0], 0.65)
    assert "76ERS" in by


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
@pytest.mark.parametrize("game", [LIVE, FINAL_OT, NEXT], ids=lambda g: g.game_id)
def test_stale_label(sign, game, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls = _spy(monkeypatch, canvas, game, stale=True)
    stale = _by(calls)["STALE"]
    assert stale[5] == pal.DIM
    unwrap_to_real(canvas).Clear()
    assert "STALE" not in _texts(_spy(monkeypatch, canvas, game))


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
@pytest.mark.parametrize("state", ["live", "final", "future"])
def test_sparse_game_never_raises(sign, state, request):
    canvas = request.getfixturevalue(sign)
    game = dataclasses.replace(SPARSE, state=state)
    render_scoreboard(canvas, game, NOW, TZ, stale=True)
    render_scoreboard(canvas, game, NOW, TZ, logos=False)
    odd = dataclasses.replace(game, away="", home="ZZZ")
    render_scoreboard(canvas, odd, NOW, TZ)
    canc = dataclasses.replace(game, state="final", status="STATUS_CANCELED")
    render_scoreboard(canvas, canc, NOW, TZ)


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_sparse_live_paints_something(sign, request):
    canvas = request.getfixturevalue(sign)
    render_scoreboard(canvas, SPARSE, NOW, TZ)
    real = unwrap_to_real(canvas)
    assert any(v != (0, 0, 0) for v in real._pixels.values())


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_y_offset_shifts_content(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    a = _by(_spy(monkeypatch, canvas, LIVE))
    b = _by(_spy(monkeypatch, canvas, LIVE, y_offset=2))
    assert b["101"][4] - a["101"][4] == 8  # 2 logical rows at scale 4
    assert b["Q4"][4] - a["Q4"][4] == 8
    _, sa = _spy_all(monkeypatch, canvas, LIVE)
    _, sb = _spy_all(monkeypatch, canvas, LIVE, y_offset=2)
    assert [s[3] + 8 for s in sa] == [s[3] for s in sb]


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_highlight_fades_score_toward_rest(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    by = _by(_spy(monkeypatch, canvas, LIVE, highlight={"PHI": 0.0}))
    assert by["98"][5] == pal.chip("PHI")[0]  # PHI's score starts in its primary
    assert by["101"][5] == pal.WHITE
    unwrap_to_real(canvas).Clear()
    by = _by(_spy(monkeypatch, canvas, LIVE, highlight={"PHI": 0.5, "NY": 1.0}))
    assert by["98"][5] == pal.lerp(pal.chip("PHI")[0], pal.WHITE, 0.5)
    assert by["101"][5] == pal.WHITE
    unwrap_to_real(canvas).Clear()
    by = _by(_spy(monkeypatch, canvas, FINAL_OT, highlight={"NY": 0.5}))
    assert by["118"][5] == pal.lerp(pal.chip("NY")[0], pal.GREEN, 0.5)
    assert by["115"][5] == pal.LOSER
