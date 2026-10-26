"""Goal celebration: the timeline, the flash + detail renderers per sign,
and the card's queue/consume/highlight lifecycle."""

import dataclasses
import unittest.mock as mock

import pytest
from led_ticker.plugin import make_color, unwrap_to_real

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
    boxes = _detail_boxes(canvas, GAME, long)
    real = unwrap_to_real(canvas)
    time_s = f"{GOAL.period_label} {GOAL.time_in_period}"
    (time_box,) = [b for b in boxes if b[0] == time_s]
    scorer = [b for b in boxes if b[0].startswith("VANDER")]
    assert scorer and scorer[0][0].endswith("…")
    for b in boxes:
        assert b[1] >= 0 and b[2] <= real.width
    # the name and its "(5)" share a baseline; the time is not part of it
    base = scorer[0][3][1]
    name_line = [b for b in boxes if b[3][1] == base and b is not time_box]
    name_right = max(b[2] for b in name_line)
    if sign == "longboi":
        # time sits in the bottom-right corner, below the name; the name's
        # right-hand neighbour is the stacked score column
        col_x = min(b[1] for b in boxes if b[0] in ("PHI", "NYI"))
        assert name_right <= col_x - 6
    else:
        (tt, tb), (st, sb) = time_box[3], scorer[0][3]
        assert tt <= sb and st <= tb  # shares the name's vertical band
        assert name_right <= time_box[1] - 6


def _detail_boxes(canvas, game, goal):
    """(text, x0, x1, (top, bottom)) per painted text: cap band for hi-res,
    the band row for the bitmap font."""
    from led_ticker.plugin import measure_width, resolve_font

    boxes = []
    if cel.safe_scale(canvas) <= 1:
        real_draw = cel.draw_text

        def spy_bmp(cv, font, text, x, y, color):
            w = measure_width(font, text, cv)
            boxes.append((text, x, x + w, (y - 7, y)))
            return real_draw(cv, font, text, x, y, color)

        with mock.patch.object(cel, "draw_text", spy_bmp):
            render_detail(canvas, game, goal, 30)
        return boxes
    real_hires = cel.hires

    def spy(shim, text, x, y_top, color, size):
        base = y_top + resolve_font("Inter-Bold", size).ascent
        w = cel.text_width(size, text)
        boxes.append((text, x, x + w, (base - round(size * 0.72), base)))
        return real_hires(shim, text, x, y_top, color, size)

    with mock.patch.object(cel, "hires", spy):
        render_detail(canvas, game, goal, 30)
    return boxes


def _assert_clearance(boxes):
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            (at, ab), (bt, bb) = a[3], b[3]
            if at > bb or bt > ab:
                continue  # different vertical bands
            gap = max(b[1] - a[2], a[1] - b[2])
            assert gap >= 6, (a, b)


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
def test_detail_texts_keep_clearance_two_digit_scores(sign, request):
    canvas = request.getfixturevalue(sign)
    game = dataclasses.replace(GAME, away_score=10, home_score=10)
    goal = _goal(
        away_score=10,
        home_score=10,
        period_label="3RD",
        time_in_period="19:59",
    )
    boxes = _detail_boxes(canvas, game, goal)
    assert any(b[0] == "3RD 19:59" for b in boxes)
    assert sum(1 for b in boxes if b[0] == "10") == 2
    _assert_clearance(boxes)


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
def test_detail_long_texts_keep_clearance(sign, request):
    canvas = request.getfixturevalue(sign)
    long = _goal(
        scorer="VANDERHOFSTADTENBERGERSONVILLE",
        assists=("AAAAAAAAAAAAAAAAAAAA", "BBBBBBBBBBBBBBBBBBBBBBBB"),
    )
    _assert_clearance(_detail_boxes(canvas, GAME, long))


# --------------------------------------------------------------- card


def test_detail_ignores_bg_color_at_scale_gt1(bigsign):
    # #105: bg_color is a scale-1 option; the hi-res detail card paints its
    # own palette like every other hi-res renderer.
    c = _card(bg_color=make_color(40, 0, 0))
    c.queue_goals([_goal()])
    c.reset_frame()
    for _ in range(FLASH_FRAMES):
        c.advance_frame()
    with mock.patch.object(
        card_mod, "render_detail", wraps=card_mod.render_detail
    ) as detail:
        c.advance_frame()  # frame FLASH_FRAMES + 1: the detail phase
        c.draw(bigsign)
    detail.assert_called_once()
    assert (40, 0, 0) not in set(_pixels(bigsign).values())


def test_detail_keeps_bg_color_at_scale_1(smallsign):
    # Scale 1 honours bg_color on the band board, so its detail card does too.
    c = _card(bg_color=make_color(40, 0, 0))
    c.queue_goals([_goal()])
    c.reset_frame()
    for _ in range(FLASH_FRAMES + 1):
        c.advance_frame()
    c.draw(smallsign)
    assert (40, 0, 0) in set(_pixels(smallsign).values())


def test_hold_time_extends_while_celebration_pending():
    # n x 4 s of celebration, THEN the board for max(base_hold, 4 s): the
    # celebration never eats the board's own hold.
    c = _card(base_hold=3.0)
    assert c.hold_time == 3.0
    c.queue_goals([_goal()])
    assert c.hold_time == pytest.approx(4.0 + 4.0)  # no visit yet: pending
    c.reset_frame()
    assert c.hold_time == pytest.approx(8.0)  # the visit's snapshot


@pytest.mark.parametrize(
    ("base", "n", "want"),
    [(0.0, 1, 8.0), (3.0, 2, 12.0), (10.0, 1, 14.0), (10.0, 3, 22.0)],
)
def test_hold_time_is_celebration_plus_board_floor(base, n, want):
    c = _card(base_hold=base)
    c.queue_goals([_goal(key=str(i), away_score=i + 1) for i in range(n)])
    assert abs(card_mod.CELEBRATION_SECONDS - 4.0) < 1e-9
    assert card_mod.BOARD_FLOOR == 4.0
    assert c.hold_time == pytest.approx(want)


def test_hold_time_without_goals_is_base_hold():
    c = _card(base_hold=6.0)
    c.reset_frame()
    assert c.hold_time == 6.0


def test_goal_queued_mid_visit_waits_for_next_turn(bigsign):
    c = _card(base_hold=3.0)
    c.reset_frame()
    for _ in range(30):
        c.advance_frame()
        c.draw(bigsign)
    c.queue_goals([_goal()])
    assert c.hold_time == 3.0  # this visit's hold is not stretched
    with mock.patch.object(card_mod, "render_scoreboard") as spy:
        for _ in range(30):
            c.advance_frame()
            c.draw(bigsign)
    assert spy.call_count == 30  # board, not a mid-timeline celebration
    c.reset_frame()
    assert len(c.pending) == 1
    assert c.hold_time == pytest.approx(8.0)
    with (
        mock.patch.object(
            card_mod, "render_flash", wraps=card_mod.render_flash
        ) as flash,
        mock.patch.object(
            card_mod, "render_detail", wraps=card_mod.render_detail
        ) as detail,
    ):
        for _ in range(CELEBRATION_FRAMES - 1):
            c.advance_frame()
            c.draw(bigsign)
    assert flash.call_count == FLASH_FRAMES - 1  # frames 1-11
    assert detail.call_count == CELEBRATION_FRAMES - FLASH_FRAMES
    c.reset_frame()
    assert c.pending == []


def test_no_visit_snapshot_renders_board(bigsign):
    # e.g. outgoing transition compositing before any visit entry
    c = _card()
    c.queue_goals([_goal()])
    with mock.patch.object(card_mod, "render_scoreboard") as spy:
        c.draw(bigsign)
    spy.assert_called_once()


def test_cap_eviction_mid_visit_does_not_shift_playing(bigsign):
    c = _card()
    goals = [_goal(key=str(i), away_score=i + 3) for i in range(3)]
    c.queue_goals(goals)
    c.reset_frame()
    for _ in range(CELEBRATION_FRAMES + 20):  # into goal 1
        c.advance_frame()
        c.draw(bigsign)
    c.queue_goals([_goal(key="x", away_score=10), _goal(key="y", away_score=11)])
    # ^ evicts "0", "1" (distinct scores: same-score goals are replacements)
    with mock.patch.object(
        card_mod, "render_detail", wraps=card_mod.render_detail
    ) as detail:
        c.advance_frame()
        c.draw(bigsign)
    assert detail.call_args.args[2].key == "1"
    c.reset_frame()
    assert [g.key for g in c.pending] == ["2", "x", "y"]


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
    goals = [_goal(key=str(i), away_score=i + 3) for i in range(5)]
    c.queue_goals(goals)
    assert c.pending == goals[-3:]
    c.queue_goals([_goal(key="x", away_score=20)])
    assert [g.key for g in c.pending] == ["3", "4", "x"]


def test_highlight_fades_and_clears(smallsign):
    c = _card(tracked=("PHI",), layout="scoreboard")
    c.queue_goals([_goal(team="NYI")])
    c.reset_frame()
    c.advance_frame()
    c.draw(smallsign)
    board = c._legacy
    assert board.highlight == ("NYI", 0.0)  # full amber first
    c.advance_frame()
    c.draw(smallsign)
    assert board.highlight[1] == pytest.approx(1 / HIGHLIGHT_FRAMES)
    for _ in range(HIGHLIGHT_FRAMES - 2):
        c.advance_frame()
        c.draw(smallsign)
    assert c.highlight is None
    c.advance_frame()
    c.draw(smallsign)
    assert board.highlight is None


def test_highlight_passed_to_hires_board(bigsign):
    c = _card(tracked=("PHI",))
    c.queue_goals([_goal(team="NYI")])
    with mock.patch.object(card_mod, "render_scoreboard") as spy:
        c.draw(bigsign)
    assert spy.call_args.kwargs["highlight"] == ("NYI", 0.0)


def test_highlight_does_not_tick_while_paused(bigsign):
    c = _card(tracked=())
    c.queue_goals([_goal()])
    c._frame_count = 3
    c.pause_frame()
    for _ in range(10):
        c.advance_frame()
        c.draw(bigsign)
    assert c.highlight == ("PHI", HIGHLIGHT_FRAMES)


def test_highlight_ticks_once_per_frame(bigsign):
    c = _card(tracked=())
    c.queue_goals([_goal()])
    c.reset_frame()
    c.advance_frame()
    for _ in range(5):
        c.draw(bigsign)
    assert c.highlight == ("PHI", HIGHLIGHT_FRAMES - 1)


def test_highlight_not_burned_without_drawing():
    c = _card(tracked=())
    c.queue_goals([_goal()])
    c.reset_frame()
    for _ in range(HIGHLIGHT_FRAMES + 5):
        c.advance_frame()
    c.reset_frame()
    assert c.highlight == ("PHI", HIGHLIGHT_FRAMES)


def test_highlight_not_burned_under_celebration(bigsign):
    # A tracked goal is celebrating; an untracked goal's highlight waits.
    c = _card(tracked=("PHI",))
    c.queue_goals([_goal(key="a")])
    c.reset_frame()
    c.queue_goals([_goal(key="b", team="NYI", home_score=2)])
    for _ in range(20):
        c.advance_frame()
        c.draw(bigsign)
    assert c.highlight == ("NYI", HIGHLIGHT_FRAMES)
    c.reset_frame()
    assert c.highlight == ("NYI", HIGHLIGHT_FRAMES)


def test_shown_highlight_cleared_on_visit_entry(bigsign):
    c = _card(tracked=())
    c.queue_goals([_goal()])
    c.reset_frame()  # not yet shown: kept
    assert c.highlight is not None
    c.advance_frame()
    c.reset_frame()  # advanced but never drawn: kept
    assert c.highlight is not None
    c.advance_frame()
    c.draw(bigsign)
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


# ------------------------------------------ transition compositing (M3)


def test_paused_card_draws_board_not_celebration(bigsign):
    c = _card()
    c.queue_goals([_goal()])
    c.reset_frame()
    for _ in range(3):
        c.advance_frame()
        c.draw(bigsign)
    c.pause_frame()
    with (
        mock.patch.object(card_mod, "render_flash") as flash,
        mock.patch.object(card_mod, "render_detail") as detail,
        mock.patch.object(card_mod, "render_scoreboard") as board_spy,
    ):
        c.draw(bigsign)
    assert flash.call_count == 0 and detail.call_count == 0
    board_spy.assert_called_once()
    c.resume_frame()
    with mock.patch.object(card_mod, "render_flash") as flash:
        c.advance_frame()
        c.draw(bigsign)
    assert flash.call_count == 1  # resumes where it was


# ------------------------------------------------ scoring changes (I6)


def test_card_queue_same_score_replaces_pending():
    c = _card()
    a = _goal(key="a", scorer="KONECNY", away_score=3, home_score=1)
    b = _goal(key="b", scorer="COUTURIER", away_score=3, home_score=1)
    c.queue_goals([a])
    c.queue_goals([b])
    assert c.pending == [b]


def test_replace_goals_swaps_playing_mid_visit(bigsign):
    c = _card()
    a = _goal(key="a", scorer="KONECNY", away_score=3, home_score=1)
    b = _goal(key="b", scorer="COUTURIER", away_score=3, home_score=1)
    c.queue_goals([a])
    c.reset_frame()
    for _ in range(FLASH_FRAMES + 2):
        c.advance_frame()
        c.draw(bigsign)
    c.replace_goals([b])
    with mock.patch.object(
        card_mod, "render_detail", wraps=card_mod.render_detail
    ) as detail:
        c.advance_frame()
        c.draw(bigsign)
    assert detail.call_args.args[2].scorer == "COUTURIER"
    c.reset_frame()
    assert c.pending == []  # consumed: it did reach the panel


def test_replace_goals_after_consumption_is_silent():
    c = _card()
    c.replace_goals([_goal(key="b", away_score=3, home_score=1)])
    assert c.pending == [] and c.highlight is None


def _scored(key, away, home, scorer="KONECNY"):
    return _goal(key=key, scorer=scorer, away_score=away, home_score=home)


async def test_widget_scoring_change_replaces_pending_goal():
    from .test_scores import FakeSource, _snap, game

    w = HockeyScoreMonitor(session=None, teams=["PHI"])
    w._tz = TZ
    w._source = FakeSource(_snap(game(1, "live", away_score=2)), {1: ()})
    await w.update()
    first = _scored("p3:1:00:11", 3, 1)
    w._source.goals[1] = (first,)
    w._source.snapshot = _snap(game(1, "live", away_score=3))
    await w.update()
    card = w.feed_stories[0]
    assert card.pending == [first]
    fixed = _scored("p3:1:00:22", 3, 1, scorer="COUTURIER")
    w._source.goals[1] = (fixed,)
    await w.update()
    assert card.pending == [fixed]


async def test_widget_scoring_change_after_celebration_does_not_replay(bigsign):
    from .test_scores import FakeSource, _snap, game

    w = HockeyScoreMonitor(session=None, teams=["PHI"])
    w._tz = TZ
    w._source = FakeSource(_snap(game(1, "live", away_score=2)), {1: ()})
    await w.update()
    w._source.goals[1] = (_scored("a", 3, 1),)
    w._source.snapshot = _snap(game(1, "live", away_score=3))
    await w.update()
    card = w.feed_stories[0]
    card.reset_frame()
    for _ in range(CELEBRATION_FRAMES):
        card.advance_frame()
        card.draw(bigsign)
    card.reset_frame()
    assert card.pending == []
    w._source.goals[1] = (_scored("b", 3, 1, scorer="COUTURIER"),)
    await w.update()
    assert card.pending == [] and card._playing == []


async def test_widget_baseline_goal_correction_is_silent():
    from .test_scores import FakeSource, _snap, game

    base = _scored("a", 1, 0)
    live = dataclasses.replace(game(1, "live", away_score=1, home_score=0))
    w = HockeyScoreMonitor(session=None, teams=["PHI"])
    w._tz = TZ
    w._source = FakeSource(_snap(dataclasses.replace(live, goals=(base,))), {1: ()})
    await w.update()
    fixed = _scored("b", 1, 0, scorer="COUTURIER")
    w._source.goals[1] = (fixed,)
    w._source.snapshot = _snap(dataclasses.replace(live, goals=(fixed,)))
    await w.update()
    assert w.feed_stories[0].pending == []


async def test_widget_goal_after_disallowed_one_still_celebrates():
    from .test_scores import FakeSource, _snap, game

    w = HockeyScoreMonitor(session=None, teams=["PHI"])
    w._tz = TZ
    w._source = FakeSource(_snap(game(1, "live", away_score=2)), {1: ()})
    await w.update()
    w._source.goals[1] = (_scored("a", 3, 1),)
    w._source.snapshot = _snap(game(1, "live", away_score=3))
    await w.update()
    w._source.goals[1] = ()
    w._source.snapshot = _snap(game(1, "live", away_score=2))  # disallowed
    await w.update()
    card = w.feed_stories[0]
    assert card.pending == []
    real = _scored("b", 3, 1, scorer="COUTURIER")
    w._source.goals[1] = (real,)
    w._source.snapshot = _snap(game(1, "live", away_score=3))
    await w.update()
    assert card.pending == [real]


# ------------------------------- scroll-mode sections (#106): no reset_frame


def _scroll_frames(card, canvas, n):
    """Tick like `_scroll_side_by_side`: advance then draw, never reset_frame."""
    out = []
    for _ in range(n):
        card.advance_frame()
        out.append(card.draw(canvas))
    return out


def test_scroll_mode_starts_pending_celebration_on_first_live_draw(bigsign):
    c = _card()
    c.queue_goals([_goal()])
    with (
        mock.patch.object(card_mod, "render_flash") as flash,
        mock.patch.object(card_mod, "render_scoreboard") as board,
    ):
        _scroll_frames(c, bigsign, 2)
    # 1st advance -> frame 1 -> the run self-starts at origin 1 -> phase 0
    # (flash_on); 2nd -> phase 1 (flash_on). Two flash paints, no board.
    assert [call.args[2] for call in flash.call_args_list] == [True, True]
    board.assert_not_called()
    assert c._run_start == 1


def test_scroll_mode_never_starts_on_frame_zero_draw(bigsign):
    # e.g. `_scroll_and_delay`'s initial draw before any advance
    c = _card()
    c.queue_goals([_goal()])
    with mock.patch.object(card_mod, "render_scoreboard") as board:
        c.draw(bigsign)
    board.assert_called_once()
    assert c._playing is None and c._run_start is None


def test_scroll_mode_run_plays_whole_timeline_then_consumes(bigsign):
    c = _card()
    c.queue_goals([_goal()])
    with (
        mock.patch.object(card_mod, "render_flash") as flash,
        mock.patch.object(card_mod, "render_detail") as detail,
        mock.patch.object(card_mod, "render_scoreboard") as board,
    ):
        _scroll_frames(c, bigsign, CELEBRATION_FRAMES + 1)
    assert flash.call_count == FLASH_FRAMES
    assert detail.call_count == CELEBRATION_FRAMES - FLASH_FRAMES
    board.assert_called_once()  # the run-ending draw shows the board
    assert c.pending == [] and c._playing is None and c._run_start is None


def test_scroll_mode_goal_queued_mid_run_waits_for_next_run(bigsign):
    c = _card()
    g1 = _goal(key="g1", away_score=1, home_score=0)
    g2 = _goal(key="g2", away_score=2, home_score=0)
    c.queue_goals([g1])
    _scroll_frames(c, bigsign, 10)  # frames 1-10: run started at 1
    c.queue_goals([g2])
    assert c._playing == [g1]
    _scroll_frames(c, bigsign, CELEBRATION_FRAMES - 10)  # frames 11-80
    assert c._playing == [g1]  # g1's timeline (phases 0-79) still playing
    with mock.patch.object(card_mod, "render_scoreboard") as board:
        _scroll_frames(c, bigsign, 1)  # frame 81: g1's run ends
    board.assert_called_once()
    assert c._playing is None and c.pending == [g2]
    _scroll_frames(c, bigsign, 1)  # the next live draw self-starts g2
    assert c._playing == [g2] and c._run_start == CELEBRATION_FRAMES + 2


def test_scroll_mode_paused_draws_do_not_advance_or_consume(bigsign):
    c = _card()
    c.queue_goals([_goal()])
    _scroll_frames(c, bigsign, 1)  # run self-started at frame 1 (shown)
    c.pause_frame()
    with (
        mock.patch.object(card_mod, "render_flash") as flash,
        mock.patch.object(card_mod, "render_detail") as detail,
    ):
        for _ in range(CELEBRATION_FRAMES + 5):
            c.advance_frame()  # no-op while paused
            c.draw(bigsign)  # transition compositing: the board
    assert flash.call_count == 0 and detail.call_count == 0
    c.resume_frame()
    assert c.pending and c._playing is not None  # nothing consumed
    _scroll_frames(c, bigsign, CELEBRATION_FRAMES)  # frames 2-81 finish it
    assert c.pending == [] and c._playing is None


def test_scroll_mode_paused_card_never_self_starts(bigsign):
    c = _card()
    c.queue_goals([_goal()])
    c._frame_count = 5
    c.pause_frame()
    c.draw(bigsign)
    assert c._playing is None and c._run_start is None


def test_scroll_mode_takes_over_full_panel(bigsign):
    c = _card(layout="ticker")
    c.queue_goals([_goal()])
    c.advance_frame()
    _, cursor = c.draw(bigsign, cursor_pos=-37)
    assert cursor == bigsign.width
    real = unwrap_to_real(bigsign)
    assert sum(1 for v in real._pixels.values() if v == PHI) > 0.5 * (
        real.width * real.height
    )


def test_scroll_mode_demo_rearms_after_rest(bigsign):
    # No visits to count in a scroll section: a demo card re-celebrates
    # DEMO_REST_FRAMES live frames after its self-started run ended.
    c = _card(demo_goals=(_goal(),))
    c.queue_goals(list(c.demo_goals))
    _scroll_frames(c, bigsign, CELEBRATION_FRAMES + 1)  # run 1, ends at 81
    assert c.pending == [] and c._playing is None
    with mock.patch.object(card_mod, "render_flash") as flash:
        _scroll_frames(c, bigsign, card_mod.DEMO_REST_FRAMES - 1)
    flash.assert_not_called()  # resting: the crawl, no celebration
    with mock.patch.object(card_mod, "render_flash") as flash:
        _scroll_frames(c, bigsign, 1)
    flash.assert_called_once()  # re-armed and self-started on this frame
    assert c._run_start == CELEBRATION_FRAMES + 1 + card_mod.DEMO_REST_FRAMES


def test_scroll_mode_demo_rest_paused_frames_do_not_rearm(bigsign):
    c = _card(demo_goals=(_goal(),))
    c.queue_goals(list(c.demo_goals))
    _scroll_frames(c, bigsign, CELEBRATION_FRAMES + 1)
    c._frame_count += card_mod.DEMO_REST_FRAMES
    c.pause_frame()
    c.draw(bigsign)
    assert c.pending == []  # transition compositing never re-arms


def test_non_demo_card_never_rests(bigsign):
    c = _card()
    c.queue_goals([_goal()])
    _scroll_frames(c, bigsign, CELEBRATION_FRAMES + 1 + card_mod.DEMO_REST_FRAMES)
    assert c._demo_rest_from is None and c.pending == [] and c._playing is None


def test_slideshow_path_unchanged_with_run_start(bigsign):
    c = _card()
    c.queue_goals([_goal()])
    c.reset_frame()
    assert c._run_start is None
    _scroll_frames(c, bigsign, 5)
    c.queue_goals([_goal(key="g2", away_score=3)])
    assert len(c._playing) == 1  # mid-visit goal waits (existing contract)
    _scroll_frames(c, bigsign, CELEBRATION_FRAMES)  # run over: board, no start
    assert c._run_start is None and len(c._playing) == 1
    assert len(c.pending) == 2  # nothing consumed until the next visit entry
    c.reset_frame()
    assert [g.key for g in c.pending] == ["g2"]


def test_reset_frame_clears_a_self_started_run(bigsign):
    # A scroll card entering a slideshow-style visit (e.g. a transition's
    # reset) restarts at origin 0 from the visit snapshot.
    c = _card()
    c.queue_goals([_goal()])
    _scroll_frames(c, bigsign, 3)
    assert c._run_start == 1
    c.reset_frame()
    assert c._run_start is None and c._frame_count == 0


# ------------------------------------------------ review fixes (#105/#106)

BG = (40, 0, 0)


def _core_tick(card, canvas, **draw_kw):
    """One engine tick as core runs it: advance, `reset_canvas` with the
    widget's `bg_color`, then draw."""
    from led_ticker.widgets._image_fit import reset_canvas

    card.advance_frame()
    reset_canvas(canvas, card.bg_color)
    return card.draw(canvas, **draw_kw)


@pytest.mark.parametrize("layout", ["scoreboard", "ticker"])
def test_core_never_fills_bg_color_at_scale_gt1(layout, bigsign):
    # #105: core fills `widget.bg_color` before every draw at every scale;
    # the card hands it None once a draw has seen a hi-res sign. (Core's
    # very first reset precedes any draw: the process's first frame only.)
    c = _card(layout=layout, bg_color=make_color(*BG))
    _core_tick(c, bigsign)
    for _ in range(3):
        _core_tick(c, bigsign)
        assert BG not in set(_pixels(bigsign).values())


def test_hires_seen_is_shared_so_new_cards_never_flash_bg(bigsign):
    memo = card_mod.ScaleMemo()
    a = _card(bg_color=make_color(*BG), scale_memo=memo)
    _core_tick(a, bigsign)
    b = _card(bg_color=make_color(*BG), scale_memo=memo)  # a new game's card
    _core_tick(b, bigsign)
    assert BG not in set(_pixels(bigsign).values())


@pytest.mark.parametrize("layout", ["scoreboard", "ticker"])
def test_core_still_fills_bg_color_at_scale_1(layout, smallsign):
    c = _card(layout=layout, bg_color=make_color(*BG))
    for _ in range(2):
        _core_tick(c, smallsign)
    assert BG in set(_pixels(smallsign).values())


def test_widget_cards_share_one_scale_memo():
    w = HockeyScoreMonitor(session=None, teams=["PHI"], demo=True)
    w._tz = TZ
    w._load_demo()
    memos = {id(c.scale_memo) for c in w.feed_stories}
    assert len(memos) == 1


def _paint_white(canvas):
    real = unwrap_to_real(canvas)
    for x in range(real.width):
        for y in range(real.height):
            real.SetPixel(x, y, 255, 255, 255)


@pytest.mark.parametrize("sign", ["smallsign", "bigsign"])
@pytest.mark.parametrize("frames", [3, FLASH_FRAMES + 1])  # flash_off, detail
def test_takeover_clears_preceding_widget(sign, frames, request):
    # Side-by-side: core resets once, a preceding widget paints, then the
    # card's takeover must own the whole panel.
    canvas = request.getfixturevalue(sign)
    c = _card()
    c.queue_goals([_goal()])
    for _ in range(frames):
        c.advance_frame()
        _paint_white(canvas)
        c.draw(canvas, cursor_pos=canvas.width - 10)
    real = unwrap_to_real(canvas)
    white = sum(1 for v in real._pixels.values() if v == WHITE)
    assert white < 0.05 * real.width * real.height


def test_takeover_clear_uses_bg_color_at_scale_1(smallsign):
    c = _card(bg_color=make_color(*BG))
    c.queue_goals([_goal()])
    for _ in range(3):  # frame 3 = flash_off
        c.advance_frame()
        _paint_white(smallsign)
        c.draw(smallsign)
    px = list(_pixels(smallsign).values())
    assert WHITE not in px and BG in px


def test_hidden_card_run_does_not_advance(bigsign):
    # Core advances every buffered widget each tick but stops drawing at
    # cursor >= width: B's run must advance only on frames B is drawn.
    a, b = _card(), _card()
    b.queue_goals([_goal(key="b")])
    b.advance_frame()
    a.advance_frame()
    b.draw(bigsign, cursor_pos=200)  # B self-starts: phase 0
    a.queue_goals([_goal(key="a")])
    for _ in range(CELEBRATION_FRAMES):
        a.advance_frame()
        b.advance_frame()  # buffered, advanced, but hidden behind A
        a.draw(bigsign)
    assert b._playing is not None and [g.key for g in b.pending] == ["b"]
    with mock.patch.object(card_mod, "render_flash") as flash:
        b.advance_frame()
        b.draw(bigsign)
    assert flash.call_args.args[2] is True  # phase 1: still flash_on
