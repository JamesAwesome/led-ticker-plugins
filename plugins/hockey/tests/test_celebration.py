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
