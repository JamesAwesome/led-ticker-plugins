"""The physical (scale>1) held scoreboard.

Every hi-res text is recorded through a spy on `hires()` as its ADVANCE
extent plus its cap band (baseline - 0.72*size .. baseline), the same
measure the renderer lays out with; shapes (chips, triangle, pips, divider)
through spies on `rect` / `triangle` / `pips` / `_dotted`. Assertions are
invariant-based (extents, bands, colors), never exact freetype pins.
"""

import dataclasses
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from led_ticker.plugin import resolve_font, unwrap_to_real

import led_ticker_football.layouts.scoreboard as board
from led_ticker_football import _palette as pal
from led_ticker_football._models import GameInfo, Situation, build_demo_games
from led_ticker_football.layouts.scoreboard import (
    _BIG,
    _LONG,
    _MIN_GAP,
    geometry_for,
    render_scoreboard,
)

from .conftest import TZ

NOW = 1_700_000_000.0  # 2023-11-14 17:13 America/New_York
GAMES, TD = build_demo_games(NOW)
LIVE, HALF, FINAL_OT, NEXT, BYE = GAMES

WORST_SIT = Situation(
    possession="JAX",
    down_distance="1ST & GOAL",
    spot="WSH 50",
    red_zone=True,
    away_timeouts=3,
    home_timeouts=3,
    last_play=None,
)
WORST_LIVE = dataclasses.replace(
    LIVE, away="WSH", home="JAX", away_score=48, home_score=48, clock="14:59",
    situation=WORST_SIT,
)  # fmt: skip
WORST_ENDQ = dataclasses.replace(
    WORST_LIVE, status="STATUS_END_PERIOD", period=3, clock="0:00", situation=None
)
WORST_FINAL = dataclasses.replace(
    WORST_LIVE, state="final", status="STATUS_FINAL", period=5, final_ot=True,
    situation=None,
)  # fmt: skip
WORST_NEXT = dataclasses.replace(
    NEXT,
    away="WSH",
    home="JAX",
    away_record="10-7",
    home_record="10-7",
    time_tbd=True,
    venue="EverBank Stadium at the Jacksonville Sports Complex",
)
SPARSE = GameInfo(
    game_id="9",
    state="live",
    status="",
    away="PHI",
    home="NYG",
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
    week=None,
)

_ORIG_HIRES = board.hires


def _spy(monkeypatch, canvas, game, **kw):
    """Render; record (text, x0, x1, cap_top, base, color) per hires call."""
    calls = []

    def spy(shim, text, x, y_top, color, size):
        adv = _ORIG_HIRES(shim, text, x, y_top, color, size)
        base = y_top + resolve_font("Inter-Bold", size).ascent
        calls.append((text, x, x + adv, base - round(size * 0.72), base, color))
        return adv

    monkeypatch.setattr(board, "hires", spy)
    render_scoreboard(canvas, game, NOW, TZ, **kw)
    return calls


def _spy_all(monkeypatch, canvas, game, **kw):
    """Texts (as `_spy`) plus filled shapes, each as
    (label, x0, x1_excl, y_top, y_bottom)."""
    shapes = []
    orig_rect, orig_dotted = board.rect, board._dotted
    orig_tri, orig_pips = board.triangle, board.pips

    def rect_spy(real, x0, y0, x1, y1, color):
        shapes.append((f"rect@{x0}", x0, x1 + 1, y0, y1))
        orig_rect(real, x0, y0, x1, y1, color)

    def dotted_spy(real, y, x1):
        shapes.append(("divider", 0, x1 + 1, y, y))
        orig_dotted(real, y, x1)

    def tri_spy(real, x, cy, h, color, *, point_left):
        w = orig_tri(real, x, cy, h, color, point_left=point_left)
        shapes.append((f"triangle@{x}", x, x + w, cy - h // 2, cy + h // 2))
        return w

    def pips_spy(real, x, y, remaining, *, size, gap, lit, spent):
        w = orig_pips(real, x, y, remaining, size=size, gap=gap, lit=lit, spent=spent)
        if w:
            shapes.append((f"pips@{x}", x, x + w, y, y + size - 1))
        return w

    monkeypatch.setattr(board, "rect", rect_spy)
    monkeypatch.setattr(board, "_dotted", dotted_spy)
    monkeypatch.setattr(board, "triangle", tri_spy)
    monkeypatch.setattr(board, "pips", pips_spy)
    return _spy(monkeypatch, canvas, game, **kw), shapes


def _assert_shapes_clear(calls, shapes, real):
    """Every shape on-panel; every text >= _MIN_GAP from any shape sharing
    its rows, unless the text sits INSIDE it (a knocked-out label)."""
    for name, x0, x1, top, bottom in shapes:
        assert x0 >= 0 and x1 <= real.width, f"{name} off-panel"
        assert top >= 0 and bottom < real.height, f"{name} off-panel vertically"
    for text, tx0, tx1, cap, base, _ in calls:
        assert cap >= 0, f"{text!r} cap top {cap} above the panel"
        assert base < real.height, f"{text!r} baseline {base} below the panel"
        for name, x0, x1, top, bottom in shapes:
            if cap > bottom or top > base:
                continue  # different rows
            if x0 <= tx0 and tx1 <= x1:
                continue  # knocked out of the shape
            gap = x0 - tx1 if tx0 < x0 else tx0 - x1
            assert gap >= _MIN_GAP, f"{text!r} {tx0}..{tx1} vs {name} {x0}..{x1}"
    for i, a in enumerate(shapes):
        for b in shapes[i + 1 :]:
            if a[3] > b[4] or b[3] > a[4]:
                continue
            left, right = (a, b) if a[1] <= b[1] else (b, a)
            if left[0] == "divider" or right[0] == "divider":
                continue  # the divider underlines a row; chips sit on it
            if left[0].startswith("rect") and right[0].startswith("rect"):
                continue  # two-tone chip halves overlap by design
            assert right[1] - left[2] >= _MIN_GAP, (a, b)


def _assert_separated(calls, real):
    for i, a in enumerate(calls):
        assert a[1] >= 0, f"{a[0]!r} starts off-panel"
        assert a[2] <= real.width, f"{a[0]!r} overflows the panel"
        for b in calls[i + 1 :]:
            if a[3] > b[4] or b[3] > a[4]:
                continue  # different vertical bands
            left, right = (a, b) if a[1] <= b[1] else (b, a)
            gap = right[1] - left[2]
            assert gap >= _MIN_GAP, (
                f"{left[0]!r} ends {left[2]}, {right[0]!r} starts {right[1]}: "
                f"gap {gap} < {_MIN_GAP}"
            )


def _texts(calls):
    return [c[0] for c in calls]


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
@pytest.mark.parametrize(
    "game", [WORST_LIVE, WORST_ENDQ, WORST_FINAL, WORST_NEXT], ids=str
)
@pytest.mark.parametrize("stale", [False, True])
def test_worst_case_keeps_min_clearance(sign, game, stale, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    bye = game is WORST_NEXT
    calls, shapes = _spy_all(monkeypatch, canvas, game, stale=stale, bye=bye)
    assert calls and shapes
    real = unwrap_to_real(canvas)
    _assert_separated(calls, real)
    _assert_shapes_clear(calls, shapes, real)


def test_worst_live_shows_everything(bigsign, longboi, monkeypatch):
    for canvas in (bigsign, longboi):
        texts = _texts(_spy(monkeypatch, canvas, WORST_LIVE))
        assert texts.count("48") == 2
        assert "Q4" in texts and "14:59" in texts
        assert any(t.startswith("1ST & GOAL") for t in texts)


def test_geometry_picks_by_physical_width():
    assert geometry_for(256) is _BIG
    assert geometry_for(399) is _BIG
    assert geometry_for(400) is _LONG
    assert geometry_for(512) is _LONG


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_possession_triangle_on_possessing_row(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    _, shapes = _spy_all(monkeypatch, canvas, LIVE)  # NYG (home) has the ball
    tris = [s for s in shapes if s[0].startswith("triangle")]
    assert len(tris) == 1
    real = unwrap_to_real(canvas)
    if sign == "bigsign":
        assert tris[0][3] >= 32  # the home row is the lower half
    else:
        assert tris[0][1] > real.width // 2  # the home side is the right half
    away_ball = dataclasses.replace(
        LIVE, situation=dataclasses.replace(LIVE.situation, possession="PHI")
    )
    real.Clear()
    _, shapes = _spy_all(monkeypatch, canvas, away_ball)
    tris = [s for s in shapes if s[0].startswith("triangle")]
    assert len(tris) == 1
    if sign == "bigsign":
        assert tris[0][4] < 32
    else:
        assert tris[0][2] < real.width // 2
    # No possession known → no triangle.
    real.Clear()
    none = dataclasses.replace(
        LIVE, situation=dataclasses.replace(LIVE.situation, possession=None)
    )
    _, shapes = _spy_all(monkeypatch, canvas, none)
    assert not [s for s in shapes if s[0].startswith("triangle")]


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_pips_reflect_timeouts(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    seen = []
    orig = board.pips

    def spy(real, x, y, remaining, **kw):
        seen.append(remaining)
        return orig(real, x, y, remaining, **kw)

    monkeypatch.setattr(board, "pips", spy)
    render_scoreboard(canvas, LIVE, NOW, TZ)
    assert sorted(seen) == [1, 2]
    seen.clear()
    unknown = dataclasses.replace(
        LIVE,
        situation=dataclasses.replace(
            LIVE.situation, away_timeouts=None, home_timeouts=None
        ),
    )
    render_scoreboard(canvas, unknown, NOW, TZ)
    assert seen == [None, None]
    seen.clear()
    render_scoreboard(canvas, FINAL_OT, NOW, TZ)
    assert seen == []


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_red_zone_situation_is_red(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls = _spy(monkeypatch, canvas, LIVE)
    sit = next(c for c in calls if c[0].startswith("2ND & 7"))
    assert sit[5] == pal.CYAN
    unwrap_to_real(canvas).Clear()
    red = dataclasses.replace(
        LIVE, situation=dataclasses.replace(LIVE.situation, red_zone=True)
    )
    calls = _spy(monkeypatch, canvas, red)
    sit = next(c for c in calls if c[0].startswith("2ND & 7"))
    assert sit[5] == pal.RED


def test_halftime_and_end_period_hide_situation(bigsign, monkeypatch):
    texts = _texts(_spy(monkeypatch, bigsign, HALF))
    assert "HALF" in texts
    assert not any("&" in t for t in texts)
    texts = _texts(_spy(monkeypatch, bigsign, WORST_ENDQ))
    assert "END Q3" in texts and "0:00" not in texts


def _box_colors(real, call):
    _, x0, x1, top, base, _ = call
    return {
        real.get_pixel(x, y) for x in range(x0, x1) for y in range(top, base + 1)
    } - {(0, 0, 0)}


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_final_scores_colored(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls = _spy(monkeypatch, canvas, FINAL_OT)  # PHI 24, NYG 27
    real = unwrap_to_real(canvas)
    by = {c[0]: c for c in calls}
    green = (pal.GREEN.red, pal.GREEN.green, pal.GREEN.blue)
    loser = (pal.LOSER.red, pal.LOSER.green, pal.LOSER.blue)
    assert _box_colors(real, by["27"]) == {green}
    assert _box_colors(real, by["24"]) == {loser}
    texts = _texts(calls)
    assert "FINAL" in texts and "OT" in texts


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_highlight_fades_score_toward_white(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls = _spy(monkeypatch, canvas, LIVE, highlight=("PHI", 0.0))
    by = {c[0]: c for c in calls}
    assert by["20"][5] == pal.AMBER  # PHI's score
    assert by["17"][5] == pal.WHITE
    unwrap_to_real(canvas).Clear()
    calls = _spy(monkeypatch, canvas, FINAL_OT, highlight=("NYG", 0.5))
    by = {c[0]: c for c in calls}
    assert by["27"][5] == pal.lerp(pal.AMBER, pal.WHITE, 0.5)
    assert by["24"][5] == pal.LOSER


def _tonight_game():
    start = datetime(2023, 11, 14, 20, 15, tzinfo=ZoneInfo("America/New_York"))
    return dataclasses.replace(NEXT, start_utc=start.astimezone(UTC))


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_next_game_shows_records_day_and_bye(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    texts = _texts(_spy(monkeypatch, canvas, _tonight_game()))
    assert "TONIGHT" in texts and "8:15 PM" in texts
    assert "LINCOLN FINANCIAL FIELD" in texts
    assert "NYG" in texts and "PHI" in texts
    assert "4-3" in texts and "5-2" in texts
    assert "NEXT GAME" in texts and "BYE WEEK" not in texts
    unwrap_to_real(canvas).Clear()
    texts = _texts(_spy(monkeypatch, canvas, BYE, bye=True))
    assert "BYE WEEK" in texts and "NEXT GAME" not in texts
    assert any(t.startswith("SUN") for t in texts)
    unwrap_to_real(canvas).Clear()
    texts = _texts(_spy(monkeypatch, canvas, WORST_NEXT))
    assert "TBD" in texts


def test_next_game_longboi_nicknames(longboi, monkeypatch):
    texts = _texts(_spy(monkeypatch, longboi, NEXT))
    assert "EAGLES" in texts and "GIANTS" in texts


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
@pytest.mark.parametrize("game", [LIVE, FINAL_OT, NEXT], ids=str)
def test_stale_label_beside_status(sign, game, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls = _spy(monkeypatch, canvas, game, stale=True)
    texts = _texts(calls)
    assert "STALE" in texts
    status = {LIVE: "Q4", FINAL_OT: "FINAL", NEXT: "1:00 PM"}[game]
    assert status in texts
    stale = next(c for c in calls if c[0] == "STALE")
    assert stale[5] == pal.DIM


def test_not_stale_has_no_label(bigsign, monkeypatch):
    assert "STALE" not in _texts(_spy(monkeypatch, bigsign, LIVE))


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
@pytest.mark.parametrize("state", ["live", "final", "future"])
def test_sparse_game_never_raises(sign, state, request):
    canvas = request.getfixturevalue(sign)
    game = dataclasses.replace(SPARSE, state=state)
    render_scoreboard(canvas, game, NOW, TZ, stale=True, bye=True)
    odd = dataclasses.replace(game, away="", home="ZZZ")
    render_scoreboard(canvas, odd, NOW, TZ)


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_y_offset_shifts_content(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    a = {c[0]: c for c in _spy(monkeypatch, canvas, LIVE)}
    b = {c[0]: c for c in _spy(monkeypatch, canvas, LIVE, y_offset=2)}
    assert b["PHI"][4] - a["PHI"][4] == 8  # 2 logical rows at scale 4


def test_situation_drops_spot_before_shrinking_too_far(bigsign, monkeypatch):
    calls = _spy(monkeypatch, bigsign, WORST_LIVE)
    sit = next(c for c in calls if c[0].startswith("1ST & GOAL"))
    # Either the full line fits or the spot was dropped; never an ellipsis
    # inside the down & distance itself.
    assert sit[0] in ("1ST & GOAL · WSH 50", "1ST & GOAL")


def test_divider_clears_a_wide_status_line(bigsign, monkeypatch):
    monkeypatch.setattr(board, "status_lines", lambda *a: ("Q4", "88:88:88"))
    calls, shapes = _spy_all(monkeypatch, bigsign, WORST_LIVE)
    line2 = next(c for c in calls if c[0].startswith("88"))
    div = next(s for s in shapes if s[0] == "divider")
    assert line2[1] - div[2] >= _MIN_GAP
    _assert_shapes_clear(calls, shapes, unwrap_to_real(bigsign))
