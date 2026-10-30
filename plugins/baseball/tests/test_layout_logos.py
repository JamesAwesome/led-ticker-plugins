"""Team logos on the physical score cards (bigsign two_row, longboi
scoreboard): placement, clearance, the per-side fallback and `logos=False`.

Text is asserted by extent (advance x span, em-box rows), never by pixels
(freetype differs macOS vs Linux).
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from led_ticker.plugin import HeadlessBackend, ScaledCanvas

from led_ticker_baseball import _logos
from led_ticker_baseball._models import GameInfo
from led_ticker_baseball.layouts import scoreboard as sb
from led_ticker_baseball.layouts import two_row as tr
from led_ticker_baseball.teams import MLB_TEAM_NAMES

TZ = ZoneInfo("America/New_York")
_MIN_GAP = 6
_DASH = (12, 10)  # series/challenge dash pair: 12 wide, 2 rows 5 apart


def _game(**over):
    kw = dict(
        away_abbr="WSH",
        home_abbr="CWS",
        away_score=10,
        home_score=12,
        state="live",
        inning="▼10",
        balls=3,
        strikes=2,
        outs=2,
        on_first=True,
        on_second=True,
        on_third=True,
        away_challenges=2,
        home_challenges=1,
        start_time=datetime(2026, 10, 30, 23, 5, tzinfo=UTC),
    )
    kw.update(over)
    g = GameInfo(**kw)
    g.series_away_wins, g.series_home_wins = 1, 1
    return g


def _canvas(width):
    real = HeadlessBackend(width, 64).create_canvas()
    return ScaledCanvas(real, scale=4, content_height=16)


def _render(monkeypatch, mod, width, game, **kw):
    """Render through `mod`, recording every logo / text / dash shape as
    (kind, label, x0, x1_excl, y0, y1_incl)."""
    shapes = []
    real_logo, real_hires = mod.paint_logo, mod.hires

    def logo_spy(real, sprite, x, y):
        shapes.append(("logo", sprite, x, x + sprite.size, y, y + sprite.size - 1))
        real_logo(real, sprite, x, y)

    def hires_spy(shim, text, x, y_top, color, size, **k):
        adv = real_hires(shim, text, x, y_top, color, size, **k)
        shapes.append(("text", text, x, x + adv, y_top, y_top + size))
        return adv

    def dash_spy(name):
        real_fn = getattr(mod, name)

        def spy(real, x, y, *a):
            shapes.append(("dash", name, x, x + _DASH[0], y, y + _DASH[1]))
            real_fn(real, x, y, *a)

        return spy

    monkeypatch.setattr(mod, "paint_logo", logo_spy)
    monkeypatch.setattr(mod, "hires", hires_spy)
    for name in ("series_dashes", "challenge_dashes"):
        if hasattr(mod, name):
            monkeypatch.setattr(mod, name, dash_spy(name))
    render = mod.render_two_row if mod is tr else mod.render_scoreboard
    render(_canvas(width), game, TZ, **kw)
    return shapes


def _logos_of(shapes):
    return [s for s in shapes if s[0] == "logo"]


def _assert_clear(shapes, width):
    """Every logo sits on the panel and keeps `_MIN_GAP` from any text or
    dash that shares its rows; the dashes keep it from each other."""
    for kind, _l, x0, x1, y0, y1 in shapes:
        if kind == "logo":
            assert x0 >= 0 and x1 <= width and y0 >= 0 and y1 < 64
    for i, a in enumerate(shapes):
        for b in shapes[i + 1 :]:
            if "logo" not in (a[0], b[0]) and not (a[0] == b[0] == "dash"):
                continue
            if a[5] < b[4] or b[5] < a[4]:
                continue  # different rows
            gap = max(b[2] - a[3], a[2] - b[3])
            assert gap >= _MIN_GAP, (a, b)


CARDS = [
    pytest.param(tr, 256, {}, id="two_row-live"),
    pytest.param(tr, 256, {"state": "final"}, id="two_row-final"),
    pytest.param(tr, 256, {"state": "preview"}, id="two_row-next"),
    pytest.param(sb, 512, {}, id="scoreboard-live"),
    pytest.param(sb, 512, {"state": "final"}, id="scoreboard-final"),
    pytest.param(
        sb,
        512,
        {"state": "preview", "away_abbr": "CLE", "home_abbr": "TOR"},
        id="scoreboard-next",
    ),
]


@pytest.mark.parametrize(("mod", "width", "over"), CARDS)
def test_logos_paint_both_teams_clear_of_everything(monkeypatch, mod, width, over):
    shapes = _render(monkeypatch, mod, width, _game(**over))
    assert len(_logos_of(shapes)) == 2
    _assert_clear(shapes, width)


@pytest.mark.parametrize(("mod", "width", "over"), CARDS)
def test_logos_false_paints_no_logo(monkeypatch, mod, width, over):
    game = _game(**over)
    with_logos = _render(monkeypatch, mod, width, game)
    without = _render(monkeypatch, mod, width, game, logos=False)
    assert not _logos_of(without)
    if game.state == "preview":
        return  # a centred run just recentres
    # The text beside the away logo moves back out to its logo-free spot.
    beside = game.away_abbr if mod is tr else str(game.away_score)
    x_with = next(s[2] for s in with_logos if s[1] == beside)
    x_without = next(s[2] for s in without if s[1] == beside)
    assert x_without < x_with


@pytest.mark.parametrize(("mod", "width", "over"), CARDS)
def test_one_missing_logo_keeps_the_other(monkeypatch, mod, width, over):
    game = _game(**over)
    full = _render(monkeypatch, mod, width, game)
    real_sprite = _logos.sprite
    monkeypatch.setattr(
        mod,
        "sprite",
        lambda abbr, size: None if abbr == game.away_abbr else real_sprite(abbr, size),
    )
    shapes = _render(monkeypatch, mod, width, game)
    logos = _logos_of(shapes)
    assert len(logos) == 1
    if mod is sb and game.state != "preview":
        # The longboi board's edges are fixed: the home logo doesn't move.
        home_logo = [s for s in _logos_of(full) if s[1] is logos[0][1]]
        assert logos[0][2:] == home_logo[0][2:]
    else:
        # Centred runs recentre and two_row's shared name size may grow back,
        # but the home logo still leads the home name by the gap.
        name = game.home_abbr if mod is tr else MLB_TEAM_NAMES[game.home_abbr]
        home_x = next(s[2] for s in shapes if s[0] == "text" and s[1] == name)
        assert logos[0][3] + _MIN_GAP == home_x
    _assert_clear(shapes, width)


@pytest.mark.parametrize(("mod", "width", "over"), CARDS)
def test_unknown_teams_render_without_logos(monkeypatch, mod, width, over):
    game = _game(**{**over, "away_abbr": "ZZZ", "home_abbr": ""})
    shapes = _render(monkeypatch, mod, width, game)
    assert not _logos_of(shapes)


def test_two_row_worst_case_shrinks_names_to_keep_dashes_apart(monkeypatch):
    shapes = _render(monkeypatch, tr, 256, _game())
    sizes = {s[1]: s[5] - s[4] for s in shapes if s[0] == "text"}
    assert sizes["WSH"] == sizes["CWS"] < 20  # both abbrevs shrank together
    assert sizes["10"] == sizes["12"] == 20  # scores keep their size
    _assert_clear(shapes, 256)


def test_two_row_typical_game_keeps_full_size_names(monkeypatch):
    shapes = _render(
        monkeypatch, tr, 256, _game(away_abbr="TB", home_abbr="SF", away_score=3)
    )
    sizes = {s[1]: s[5] - s[4] for s in shapes if s[0] == "text"}
    assert sizes["TB"] == sizes["SF"] == 20
