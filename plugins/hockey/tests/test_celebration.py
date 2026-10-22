"""Goal celebration: the timeline, the flash + detail renderers per sign,
and the card's queue/consume/highlight lifecycle."""

import dataclasses
import unittest.mock as mock

import pytest
from led_ticker.plugin import unwrap_to_real

import led_ticker_hockey._card as card_mod
from led_ticker_hockey import _celebration as cel
from led_ticker_hockey import _palette as pal
from led_ticker_hockey._card import HockeyGameCard
from led_ticker_hockey._celebration import (
    CELEBRATION_FRAMES,
    FLASH_FRAMES,
    HIGHLIGHT_FRAMES,
    MAX_QUEUED,
    phase_at,
    pulse,
    render_detail,
    render_flash,
)
from led_ticker_hockey._models import build_demo_games
from led_ticker_hockey.scores import HockeyScoreMonitor

from .conftest import TZ

NOW = 1_700_000_000.0
GAME = build_demo_games(NOW)[0]  # PHI 2 @ NYI 1, live
GOAL = GAME.goals[0]  # KONECNY (5), PHI, 2ND 7:26
PHI = (255, 90, 0)
WHITE = (255, 255, 255)


def _goal(key="k", team="PHI", **over):
    return dataclasses.replace(GOAL, key=key, team=team, **over)


def _card(layout="auto", tracked=("PHI",), **kw):
    return HockeyGameCard(
        game=GAME,
        tz=TZ,
        cfg_layout=layout,
        now_fn=lambda: NOW,
        tracked=frozenset(tracked),
        **kw,
    )


def _pixels(canvas):
    return unwrap_to_real(canvas)._pixels


# ------------------------------------------------------------ timeline


def test_constants():
    assert (FLASH_FRAMES, CELEBRATION_FRAMES, MAX_QUEUED, HIGHLIGHT_FRAMES) == (
        12,
        80,
        3,
        40,
    )


def test_phase_timeline():
    assert phase_at(0, 1) == (0, "flash_on", 0)
    assert phase_at(1, 1) == (0, "flash_on", 1)
    assert phase_at(2, 1) == (0, "flash_off", 2)
    assert phase_at(4, 1) == (0, "flash_on", 4)
    assert phase_at(11, 1) == (0, "flash_off", 11)
    assert phase_at(12, 1) == (0, "detail", 12)
    assert phase_at(79, 1) == (0, "detail", 79)
    assert phase_at(80, 1) is None
    assert phase_at(80, 2) == (1, "flash_on", 0)
    assert phase_at(0, 0) is None
    assert phase_at(-1, 1) is None


def test_pulse_range():
    assert pulse(0) == pytest.approx(1.0)
    vals = [pulse(f) for f in range(80)]
    assert min(vals) >= 0.55 - 1e-9 and max(vals) <= 1.0 + 1e-9
    assert min(vals) < 0.6


# ------------------------------------------------------------- render


def test_flash_fills_team_color_and_knocks_out_goal(bigsign):
    render_flash(bigsign, pal.chip("PHI")[0], True)
    real = unwrap_to_real(bigsign)
    px = real._pixels
    total = real.width * real.height
    orange = sum(1 for v in px.values() if v == PHI)
    assert orange > total * 0.7
    band = [
        (x, y)
        for x in range(real.width // 4, 3 * real.width // 4)
        for y in range(16, 48)
    ]
    assert any(px.get(p, (0, 0, 0)) == (0, 0, 0) for p in band)
    # corners stay lit: the knock-out is central
    assert px[(0, 0)] == PHI and px[(real.width - 1, real.height - 1)] == PHI


@pytest.mark.parametrize("sign", ["smallsign", "longboi"])
def test_flash_other_signs(sign, request):
    canvas = request.getfixturevalue(sign)
    render_flash(canvas, pal.chip("PHI")[0], True)
    real = unwrap_to_real(canvas)
    unlit = real.width * real.height - sum(1 for v in real._pixels.values() if v == PHI)
    assert 0 < unlit < real.width * real.height * 0.3


def test_flash_off_is_dark(bigsign):
    render_flash(bigsign, pal.chip("PHI")[0], False)
    assert unwrap_to_real(bigsign).count_nonzero() == 0


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
def test_detail_draws_scorer_band(sign, request):
    canvas = request.getfixturevalue(sign)
    render_detail(canvas, GAME, GOAL, 20)
    real = unwrap_to_real(canvas)
    px = real._pixels
    whites = [p for p, v in px.items() if v == WHITE]
    assert whites
    if sign == "smallsign":
        assert any(8 <= y <= 15 for _, y in whites)
        assert any(v == PHI for (x, y), v in px.items() if y < 8)
    elif sign == "bigsign":
        # scorer sits below the divider, left half
        assert any(y > 33 and x < 128 for x, y in whites)
        # cyan assists line at the bottom
        assert any(v == (0, 200, 220) for v in px.values())
    else:
        # scorer in the center column
        assert any(150 <= x < 400 for x, _ in whites)


def test_detail_pulses_scoring_team_score(bigsign):
    # At a dim pulse phase, no pixel of the scoring team's score is full white;
    # the other team's score still is.
    f = min(range(12, 80), key=pulse)
    render_detail(bigsign, GAME, GOAL, f)
    px = _pixels(bigsign)
    k = pulse(f)
    dimmed = tuple(int(255 * k) for _ in range(3))
    assert any(v == dimmed for v in px.values())


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
def test_detail_sparse_goal_never_raises(sign, request):
    canvas = request.getfixturevalue(sign)
    sparse = _goal(
        scorer="",
        season_total=None,
        assists=(),
        period_label="",
        time_in_period="",
        team="",
    )
    render_detail(canvas, GAME, sparse, 30)
    render_flash(canvas, pal.chip("")[0], True)


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
def test_detail_long_name_stays_clear_of_time(sign, request):
    canvas = request.getfixturevalue(sign)
    long = _goal(
        scorer="VANDERHOFSTADTENBERGERSONVILLE",
        assists=("AAAAAAAAAAAAAAAAAAAA", "BBBBBBBBBBBBBBBBBBBBBBBB"),
    )
    render_detail(canvas, GAME, long, 30)
    real = unwrap_to_real(canvas)
    assert all(0 <= x < real.width for x, _ in real._pixels)


# --------------------------------------------------------------- card


def test_hold_time_extends_while_celebration_pending():
    c = _card(base_hold=3.0)
    assert c.hold_time == 3.0
    c.queue_goals([_goal()])
    assert c.hold_time == pytest.approx(7.0)


def test_celebration_consumed_after_one_visit(bigsign):
    c = _card()
    c.queue_goals([_goal()])
    c.reset_frame()
    for _ in range(5):
        c.advance_frame()
        c.draw(bigsign)
    c.reset_frame()
    assert c.pending == []
    with mock.patch.object(card_mod, "render_scoreboard") as spy:
        c.advance_frame()
        c.draw(bigsign)
    spy.assert_called_once()


def test_celebration_renders_instead_of_board(bigsign):
    c = _card()
    c.queue_goals([_goal()])
    c.reset_frame()
    with mock.patch.object(card_mod, "render_scoreboard") as spy:
        c.advance_frame()
        _, cursor = c.draw(bigsign)
    spy.assert_not_called()
    assert cursor == bigsign.width


@pytest.mark.parametrize("layout", ["ticker", "scoreboard"])
@pytest.mark.parametrize("sign", ["smallsign", "bigsign"])
def test_celebration_on_every_layout_is_held(layout, sign, request):
    canvas = request.getfixturevalue(sign)
    c = _card(layout=layout)
    c.queue_goals([_goal()])
    c.reset_frame()
    c.advance_frame()
    _, cursor = c.draw(canvas)
    assert cursor == canvas.width
    real = unwrap_to_real(canvas)
    assert sum(1 for v in real._pixels.values() if v == PHI) > 0.5 * (
        real.width * real.height
    )


def test_celebration_ends_then_board_within_visit(bigsign):
    c = _card()
    c.queue_goals([_goal()])
    c.reset_frame()
    for _ in range(CELEBRATION_FRAMES):
        c.advance_frame()
        c.draw(bigsign)
    with mock.patch.object(card_mod, "render_scoreboard") as spy:
        c.advance_frame()
        c.draw(bigsign)
    spy.assert_called_once()


def test_reset_without_drawing_keeps_pending():
    c = _card()
    c.queue_goals([_goal()])
    c.reset_frame()
    assert len(c.pending) == 1


def test_stale_frame_count_from_prior_visit_does_not_consume(bigsign):
    # The card ran a whole visit (frame_count > 0) BEFORE the goal arrived;
    # the next visit-entry reset must not eat the unseen celebration.
    c = _card()
    c.reset_frame()
    for _ in range(10):
        c.advance_frame()
        c.draw(bigsign)
    c.queue_goals([_goal()])
    c.reset_frame()
    assert len(c.pending) == 1


def test_paused_draw_does_not_consume(bigsign):
    # Being composited in a transition is not "shown".
    c = _card()
    c.queue_goals([_goal()])
    c._frame_count = 5
    c.pause_frame()
    c.draw(bigsign)
    c.resume_frame()
    c.reset_frame()
    assert len(c.pending) == 1


def test_untracked_goal_highlights_instead():
    c = _card(tracked=("PHI",))
    c.queue_goals([_goal(team="NYI")])
    assert c.pending == []
    assert c.highlight is not None and c.highlight[0] == "NYI"
    assert c.highlight[1] == HIGHLIGHT_FRAMES


def test_empty_tracked_highlights_everything():
    c = _card(tracked=())
    c.queue_goals([_goal(team="PHI")])
    assert c.pending == [] and c.highlight == ("PHI", HIGHLIGHT_FRAMES)


def test_queue_caps_at_three():
    c = _card()
    goals = [_goal(key=str(i)) for i in range(5)]
    c.queue_goals(goals)
    assert c.pending == goals[-3:]
    c.queue_goals([_goal(key="x")])
    assert [g.key for g in c.pending] == ["3", "4", "x"]


def test_highlight_fades_and_clears(smallsign):
    c = _card(tracked=("PHI",), layout="scoreboard")
    c.queue_goals([_goal(team="NYI")])
    c.reset_frame()
    c.advance_frame()
    c.draw(smallsign)
    board = c._legacy
    assert board.highlight[0] == "NYI"
    assert board.highlight[1] == pytest.approx(1 / HIGHLIGHT_FRAMES)
    for _ in range(HIGHLIGHT_FRAMES):
        c.advance_frame()
    assert c.highlight is None
    c.draw(smallsign)
    assert board.highlight is None


def test_highlight_passed_to_hires_board(bigsign):
    c = _card(tracked=("PHI",))
    c.queue_goals([_goal(team="NYI")])
    with mock.patch.object(card_mod, "render_scoreboard") as spy:
        c.draw(bigsign)
    assert spy.call_args.kwargs["highlight"] == ("NYI", 0.0)


def test_highlight_does_not_tick_while_paused():
    c = _card(tracked=())
    c.queue_goals([_goal()])
    c.pause_frame()
    for _ in range(10):
        c.advance_frame()
    assert c.highlight == ("PHI", HIGHLIGHT_FRAMES)


def test_shown_highlight_cleared_on_visit_entry():
    c = _card(tracked=())
    c.queue_goals([_goal()])
    c.reset_frame()  # not yet shown: kept
    assert c.highlight is not None
    c.advance_frame()
    c.reset_frame()
    assert c.highlight is None


def test_paused_frames_do_not_advance_celebration():
    c = _card()
    c.queue_goals([_goal()])
    c._frame_count = 3
    c.pause_frame()
    for _ in range(10):
        c.advance_frame()
    assert c._frame_count == 3


def test_drop_overturned():
    c = _card()
    c.queue_goals([_goal(key="a", away_score=2, home_score=1)])
    c.queue_goals([_goal(key="b", away_score=3, home_score=1)])
    c.game = dataclasses.replace(GAME, away_score=2, home_score=1)
    c.drop_overturned()
    assert [g.key for g in c.pending] == ["a"]


async def test_overturned_goal_drops_pending():
    from .test_scores import FakeSource, _snap, game

    g = _goal(key="g3", away_score=3, home_score=1)
    w = HockeyScoreMonitor(session=None, teams=["PHI"])
    w._tz = TZ
    w._source = FakeSource(_snap(game(1, "live", away_score=2)), {1: ()})
    await w.update()
    w._source.goals[1] = (g,)
    w._source.snapshot = _snap(game(1, "live", away_score=3))
    await w.update()
    card = w.feed_stories[0]
    assert card.pending == [g]
    w._source.snapshot = _snap(game(1, "live", away_score=2))
    await w.update()
    assert card.pending == []


def test_module_exports():
    for name in ("phase_at", "pulse", "render_flash", "render_detail"):
        assert callable(getattr(cel, name))
