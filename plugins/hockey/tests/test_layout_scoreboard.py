"""tests/test_layout_scoreboard.py — the physical (scale>1) held scoreboard.

Every hi-res text is recorded through a spy on `hires()` as its ADVANCE
extent plus its cap band (baseline - 0.72*size .. baseline), the same
measure the renderer lays out with. Assertions are invariant-based
(extents, bands, colors), never exact freetype pins.
"""

import dataclasses
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from led_ticker.plugin import resolve_font, unwrap_to_real

import led_ticker_hockey.layouts.scoreboard as board
from led_ticker_hockey import _palette as pal
from led_ticker_hockey._models import GameInfo, Situation, build_demo_games
from led_ticker_hockey.layouts.scoreboard import (
    _BIG,
    _LONG,
    _MIN_GAP,
    geometry_for,
    render_scoreboard,
)

from .conftest import TZ

NOW = 1_700_000_000.0  # 2023-11-14 17:13 America/New_York
LIVE, INTERMISSION, FINAL_OT, NEXT = build_demo_games(NOW)

WORST_LIVE = dataclasses.replace(
    LIVE,
    away_score=10,
    home_score=10,
    away_sog=99,
    home_sog=99,
    period=3,
    clock_seconds=1199,
    situation=Situation(pp_team="NYI", pp_seconds=119, en_team="PHI"),
)
WORST_FINAL = dataclasses.replace(
    FINAL_OT,
    away_score=10,
    home_score=9,
    away_sog=99,
    home_sog=99,
    period=5,
    period_type="SO",
    final_type="SO",
)
WORST_NEXT = dataclasses.replace(
    NEXT, away="CBJ", home="VGK", venue="Scotiabank Saddledome Arena"
)
WORST_INT = dataclasses.replace(
    INTERMISSION,
    period=5,
    period_type="OT",
    away_sog=99,
    home_sog=99,
    away_score=10,
    home_score=10,
)
SPARSE = GameInfo(
    game_id=9,
    state="live",
    away="PHI",
    home="NYI",
    away_score=0,
    home_score=0,
    away_sog=None,
    home_sog=None,
    period=0,
    period_type="REG",
    clock_seconds=None,
    clock_running=False,
    in_intermission=False,
    start_utc=None,
    venue="",
    final_type=None,
    goals=(),
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
    """Texts (as `_spy`) plus filled shapes: chips, badges (`rect`) and
    the dotted divider, each as (label, x0, x1_excl, y_top, y_bottom)."""
    shapes = []
    orig_rect, orig_dotted = board.rect, board._dotted
    orig_logo = board.paint_logo

    def rect_spy(real, x0, y0, x1, y1, color):
        shapes.append((f"rect@{x0}", x0, x1 + 1, y0, y1))
        orig_rect(real, x0, y0, x1, y1, color)

    def dotted_spy(real, y, x1):
        shapes.append(("divider", 0, x1 + 1, y, y))
        orig_dotted(real, y, x1)

    def logo_spy(real, sprite, x, y):
        shapes.append(("LOGO", x, x + sprite.size, y, y + sprite.size - 1))
        orig_logo(real, sprite, x, y)

    monkeypatch.setattr(board, "rect", rect_spy)
    monkeypatch.setattr(board, "_dotted", dotted_spy)
    monkeypatch.setattr(board, "paint_logo", logo_spy)
    return _spy(monkeypatch, canvas, game, **kw), shapes


def _assert_shapes_clear(calls, shapes, real):
    """Every shape on-panel; every text >= _MIN_GAP from any shape sharing
    its rows, unless the text sits INSIDE it (a badge's knocked-out label)."""
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
    "game", [WORST_LIVE, WORST_FINAL, WORST_NEXT, WORST_INT], ids=str
)
@pytest.mark.parametrize("stale", [False, True])
@pytest.mark.parametrize("logos", [True, False])
def test_worst_case_keeps_min_clearance(sign, game, stale, logos, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls, shapes = _spy_all(monkeypatch, canvas, game, stale=stale, logos=logos)
    assert calls and shapes
    real = unwrap_to_real(canvas)
    _assert_separated(calls, real)
    _assert_shapes_clear(calls, shapes, real)


def test_worst_live_shows_everything(bigsign, longboi, monkeypatch):
    for canvas in (bigsign, longboi):
        texts = _texts(_spy(monkeypatch, canvas, WORST_LIVE))
        assert texts.count("10") == 2
        assert texts.count("SOG 99") == 2
        assert "PP" in texts and "EN" in texts
        assert "3RD" in texts and "19:59" in texts


def test_worst_next_nickname_on_longboi(longboi, monkeypatch):
    texts = _texts(_spy(monkeypatch, longboi, WORST_NEXT))
    assert any(t.startswith("BLUE JACKETS") or t == "BLUE JACKETS" for t in texts)
    assert any(t.startswith("GOLDEN") for t in texts)


def test_geometry_picks_by_physical_width():
    assert geometry_for(256) is _BIG
    assert geometry_for(399) is _BIG
    assert geometry_for(400) is _LONG
    assert geometry_for(512) is _LONG


def _amber_in(real, x0, x1, y0, y1):
    amber = (pal.AMBER.red, pal.AMBER.green, pal.AMBER.blue)
    return any(
        real.get_pixel(x, y) == amber
        for x in range(x0, x1 + 1)
        for y in range(y0, y1 + 1)
    )


def test_pp_badge_on_pp_team_row(bigsign):
    render_scoreboard(bigsign, LIVE, NOW, TZ)  # NYI (home) on the PP
    real = unwrap_to_real(bigsign)
    assert _amber_in(real, 114, 136, 33, 63)
    assert not _amber_in(real, 114, 136, 0, 31)


def test_en_badge_on_en_team_row(bigsign):
    game = dataclasses.replace(
        LIVE, situation=Situation(pp_team=None, pp_seconds=None, en_team="PHI")
    )
    render_scoreboard(bigsign, game, NOW, TZ)
    real = unwrap_to_real(bigsign)
    assert _amber_in(real, 114, 136, 0, 31)
    assert not _amber_in(real, 114, 136, 33, 63)


def test_en_wins_badge_but_pp_clock_stays(bigsign, monkeypatch):
    game = dataclasses.replace(
        LIVE, situation=Situation(pp_team="NYI", pp_seconds=102, en_team="NYI")
    )
    calls = _spy(monkeypatch, bigsign, game)
    texts = _texts(calls)
    assert "EN" in texts and "PP" not in texts
    assert "PP 1:42" in texts


def test_intermission_has_no_pp_line(bigsign, monkeypatch):
    game = dataclasses.replace(
        INTERMISSION, situation=Situation(pp_team="NYI", pp_seconds=50, en_team=None)
    )
    texts = _texts(_spy(monkeypatch, bigsign, game))
    assert "1ST INT" in texts and "17:00" in texts
    assert not any(t.startswith("PP") for t in texts)


def _box_colors(real, call):
    _, x0, x1, top, base, _ = call
    return {
        real.get_pixel(x, y) for x in range(x0, x1) for y in range(top, base + 1)
    } - {(0, 0, 0)}


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_final_scores_colored(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls = _spy(monkeypatch, canvas, FINAL_OT)  # PHI 3, NYI 2
    real = unwrap_to_real(canvas)
    by = {c[0]: c for c in calls}
    green = (pal.GREEN.red, pal.GREEN.green, pal.GREEN.blue)
    loser = (pal.LOSER.red, pal.LOSER.green, pal.LOSER.blue)
    assert _box_colors(real, by["3"]) == {green}
    assert _box_colors(real, by["2"]) == {loser}
    texts = _texts(calls)
    assert "FINAL" in texts and "OT" in texts


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_highlight_fades_score_toward_white(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls = _spy(monkeypatch, canvas, LIVE, highlight=("PHI", 0.0))
    by = {c[0]: c for c in calls}
    assert by["2"][5] == pal.AMBER  # PHI's score
    assert by["1"][5] == pal.WHITE
    real = unwrap_to_real(canvas)
    real.Clear()
    calls = _spy(monkeypatch, canvas, FINAL_OT, highlight=("NYI", 0.5))
    by = {c[0]: c for c in calls}
    assert by["2"][5] == pal.lerp(pal.AMBER, pal.WHITE, 0.5)
    assert by["3"][5] == pal.GREEN


def _tonight_game():
    start = datetime(2023, 11, 14, 19, 0, tzinfo=ZoneInfo("America/New_York"))
    return dataclasses.replace(NEXT, start_utc=start.astimezone(UTC))


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_next_game_shows_day_and_venue(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    texts = _texts(_spy(monkeypatch, canvas, _tonight_game()))
    assert "TONIGHT" in texts
    assert "UBS ARENA" in texts
    assert "7:00 PM" in texts
    assert "PHI" in texts and "NYI" in texts


def test_next_game_dated_uses_same_layout(bigsign, monkeypatch):
    texts = _texts(_spy(monkeypatch, bigsign, NEXT))
    assert "NEXT GAME" in texts and "@" in texts
    assert any(t.startswith(("MON", "TUE", "WED", "THU", "FRI")) for t in texts)


def test_next_game_longboi_nicknames(longboi, monkeypatch):
    texts = _texts(_spy(monkeypatch, longboi, NEXT))
    assert "FLYERS" in texts and "ISLANDERS" in texts


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
@pytest.mark.parametrize("game", [LIVE, FINAL_OT, NEXT], ids=str)
def test_stale_label_beside_status(sign, game, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls = _spy(monkeypatch, canvas, game, stale=True)
    texts = _texts(calls)
    assert "STALE" in texts
    status = {LIVE: "2ND", FINAL_OT: "FINAL", NEXT: "7:00 PM"}[game]
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
    render_scoreboard(canvas, game, NOW, TZ, stale=True)
    odd = dataclasses.replace(game, away="", home="ZZZ")
    render_scoreboard(canvas, odd, NOW, TZ)


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_y_offset_shifts_content(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    a = {c[0]: c for c in _spy(monkeypatch, canvas, LIVE)}
    b = {c[0]: c for c in _spy(monkeypatch, canvas, LIVE, y_offset=2)}
    assert b["PHI"][4] - a["PHI"][4] == 8  # 2 logical rows at scale 4


def test_divider_clears_a_wide_status_line(bigsign, monkeypatch):
    # The status column's second line shares the divider's row: however
    # wide it gets (here forced to its fit budget), the dotted divider
    # stops >= _MIN_GAP short of its MEASURED left edge.
    monkeypatch.setattr(board, "status_lines", lambda *a: ("2ND", "88:88:88"))
    calls, shapes = _spy_all(monkeypatch, bigsign, WORST_LIVE)
    line2 = next(c for c in calls if c[0].startswith("88"))
    div = next(s for s in shapes if s[0] == "divider")
    assert line2[1] - div[2] >= _MIN_GAP
    _assert_shapes_clear(calls, shapes, unwrap_to_real(bigsign))


def test_divider_keeps_full_length_when_status_is_narrow(bigsign, monkeypatch):
    _, shapes = _spy_all(monkeypatch, bigsign, LIVE)
    div = next(s for s in shapes if s[0] == "divider")
    assert div[2] == board._BIG_DIVIDER_X1 + 1


# ------------------------------------------------------------------ logos


def _logos(shapes):
    return [s for s in shapes if s[0] == "LOGO"]


def _chips(shapes):
    return [s for s in shapes if s[0].startswith("rect@")]


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_logos_replace_both_chips(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    g = geometry_for(unwrap_to_real(canvas).width)
    for game in (LIVE, NEXT):
        calls, shapes = _spy_all(monkeypatch, canvas, game)
        logos = _logos(shapes)
        assert len(logos) == 2, game.state
        assert all(s[2] - s[1] == g.logo_size for s in logos)
        assert logos[0][1] == g.logo_x
        assert not [c for c in _chips(shapes) if c[1] in (g.chip_x[0],)]
        # Each abbrev sits beside its logo, not where the chip's abbrev went.
        by = {c[0]: c for c in calls}
        assert by[game.away][1] == g.logo_x + g.logo_size + _MIN_GAP


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_logos_false_paints_chips(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    g = geometry_for(unwrap_to_real(canvas).width)
    calls, shapes = _spy_all(monkeypatch, canvas, LIVE, logos=False)
    assert not _logos(shapes)
    assert {c[1] for c in _chips(shapes)} >= {g.chip_x[0]}
    by = {c[0]: c for c in calls}
    assert by[LIVE.away][1] == g.name_x


@pytest.mark.parametrize("sign", ["bigsign", "longboi"])
def test_missing_sprite_falls_back_to_chip(sign, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    monkeypatch.setattr(board, "sprite", lambda abbrev, size: None)
    calls, shapes = _spy_all(monkeypatch, canvas, LIVE)
    assert not _logos(shapes)
    assert _chips(shapes)
    assert LIVE.away in _texts(calls) and LIVE.home in _texts(calls)


def test_one_missing_logo_keeps_the_other(longboi, monkeypatch):
    real_sprite = board.sprite
    monkeypatch.setattr(
        board,
        "sprite",
        lambda abbrev, size: None if abbrev == LIVE.home else real_sprite(abbrev, size),
    )
    calls, shapes = _spy_all(monkeypatch, longboi, LIVE)
    assert len(_logos(shapes)) == 1
    by = {c[0]: c for c in calls}
    assert by[LIVE.home][2] == board._LONG_HOME_NAME_R  # back beside its chip
    _assert_separated(calls, unwrap_to_real(longboi))
    _assert_shapes_clear(calls, shapes, unwrap_to_real(longboi))


def test_logo_helper_reports_whether_it_painted(bigsign):
    real = unwrap_to_real(bigsign)
    assert board._logo(real, "PHI", 28, 2, 2, True) is True
    assert board._logo(real, "PHI", 28, 2, 2, False) is False
    assert board._logo(real, "ZZZ", 28, 2, 2, True) is False
