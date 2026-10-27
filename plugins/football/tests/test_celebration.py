"""Scoring celebration: the timeline, the flash + detail renderers per sign,
and the card's queue/consume/highlight lifecycle."""

import dataclasses
import unittest.mock as mock

import pytest
from led_ticker.plugin import make_color, measure_width, resolve_font, unwrap_to_real

import led_ticker_football._card as card_mod
from led_ticker_football import _celebration as cel
from led_ticker_football import _palette as pal
from led_ticker_football._card import FootballGameCard
from led_ticker_football._celebration import (
    CELEBRATION_FRAMES,
    FLASH_FRAMES,
    HIGHLIGHT_FRAMES,
    MAX_QUEUED,
    flash_word,
    phase_at,
    pulse,
    render_detail,
    render_flash,
)
from led_ticker_football._models import build_demo_games
from led_ticker_football.scores import FootballScoreMonitor

from .conftest import TZ

NOW = 1_700_000_000.0
GAMES, TD = build_demo_games(NOW)
GAME = GAMES[0]  # PHI 20 @ NYG 17, live Q4
PHI = (0, 150, 130)
WHITE = (255, 255, 255)


def _play(key="k", team="PHI", **over):
    return dataclasses.replace(TD, key=key, team=team, **over)


def _card(layout="auto", tracked=("PHI",), **kw):
    return FootballGameCard(
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
    assert card_mod.MAX_QUEUED == MAX_QUEUED
    assert card_mod.HIGHLIGHT_FRAMES == HIGHLIGHT_FRAMES


def test_phase_timeline():
    assert phase_at(0, 1) == (0, "flash_on", 0)
    assert phase_at(2, 1) == (0, "flash_off", 2)
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


def test_flash_word_by_kind():
    assert flash_word("TD") == "TOUCHDOWN"
    assert flash_word("FG") == "FIELD GOAL"
    assert flash_word("SAFETY") == "SAFETY"
    assert flash_word("???") == "SCORE"


# ------------------------------------------------------------- render


def test_flash_knocks_out_word(bigsign):
    render_flash(bigsign, pal.chip("PHI")[0], True, "TOUCHDOWN")
    real = unwrap_to_real(bigsign)
    px = real._pixels
    total = real.width * real.height
    teal = sum(1 for v in px.values() if v == PHI)
    assert teal > total * 0.6
    band = [
        (x, y)
        for x in range(real.width // 8, 7 * real.width // 8)
        for y in range(16, 48)
    ]
    assert any(px.get(p, (0, 0, 0)) == (0, 0, 0) for p in band)
    assert px[(0, 0)] == PHI and px[(real.width - 1, real.height - 1)] == PHI


@pytest.mark.parametrize("sign", ["smallsign", "longboi"])
def test_flash_other_signs(sign, request):
    canvas = request.getfixturevalue(sign)
    render_flash(canvas, pal.chip("PHI")[0], True, "FIELD GOAL")
    real = unwrap_to_real(canvas)
    unlit = real.width * real.height - sum(1 for v in real._pixels.values() if v == PHI)
    assert 0 < unlit < real.width * real.height * 0.4


def test_small_flash_shortens_word(smallsign):
    calls = []
    orig = cel.draw_text

    def spy(cv, font, text, x, y, color):
        calls.append(text)
        return orig(cv, font, text, x, y, color)

    with mock.patch.object(cel, "draw_text", spy):
        render_flash(smallsign, pal.chip("PHI")[0], True, "TOUCHDOWN")
        render_flash(smallsign, pal.chip("PHI")[0], True, "FIELD GOAL")
        render_flash(smallsign, pal.chip("PHI")[0], True, "SAFETY")
    # 160 px fits all three words in the 5x8 font; the shortening kicks in
    # only when a word would not fit (checked against a narrow canvas).
    assert calls == ["TOUCHDOWN", "FIELD GOAL", "SAFETY"]
    from led_ticker.plugin import HeadlessBackend

    narrow = HeadlessBackend(40, 16).create_canvas()
    calls.clear()
    with mock.patch.object(cel, "draw_text", spy):
        render_flash(narrow, pal.chip("PHI")[0], True, "TOUCHDOWN")
        render_flash(narrow, pal.chip("PHI")[0], True, "FIELD GOAL")
    assert calls == ["TD!", "FG!"]


def test_flash_off_is_dark(bigsign):
    render_flash(bigsign, pal.chip("PHI")[0], False, "TOUCHDOWN")
    assert unwrap_to_real(bigsign).count_nonzero() == 0


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
def test_detail_draws_play_text(sign, request):
    canvas = request.getfixturevalue(sign)
    boxes = _detail_boxes(canvas, GAME, TD)
    texts = [b[0] for b in boxes]
    assert "TOUCHDOWN" in texts or "TD" in texts
    assert any(t.startswith("JALEN HURTS") for t in texts)
    assert "+PAT" in texts
    assert "Q4 9:41" in texts
    assert texts.count("20") == 1 and texts.count("17") == 1
    real = unwrap_to_real(canvas)
    for b in boxes:
        assert b[1] >= 0 and b[2] <= real.width, b


def test_detail_pulses_scoring_team_score(bigsign):
    f = min(range(12, 80), key=pulse)
    render_detail(bigsign, GAME, TD, f)
    px = _pixels(bigsign)
    k = pulse(f)
    dimmed = tuple(int(255 * k) for _ in range(3))
    assert any(v == dimmed for v in px.values())


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
def test_detail_sparse_play_never_raises(sign, request):
    canvas = request.getfixturevalue(sign)
    sparse = _play(text="", extra="", period_label="", clock="", team="")
    render_detail(canvas, GAME, sparse, 30)
    render_flash(canvas, pal.chip("")[0], True, flash_word(sparse.kind))


def _detail_boxes(canvas, game, play):
    """(text, x0, x1, (top, bottom)) per painted text: cap band for hi-res,
    the band row for the bitmap font."""
    boxes = []
    if cel.safe_scale(canvas) <= 1:
        real_draw = cel.draw_text

        def spy_bmp(cv, font, text, x, y, color):
            w = measure_width(font, text, cv)
            boxes.append((text, x, x + w, (y - 7, y)))
            return real_draw(cv, font, text, x, y, color)

        with mock.patch.object(cel, "draw_text", spy_bmp):
            render_detail(canvas, game, play, 30)
        return boxes
    real_hires = cel.hires

    def spy(shim, text, x, y_top, color, size):
        base = y_top + resolve_font("Inter-Bold", size).ascent
        w = cel.text_width(size, text)
        boxes.append((text, x, x + w, (base - round(size * 0.72), base)))
        return real_hires(shim, text, x, y_top, color, size)

    with mock.patch.object(cel, "hires", spy):
        render_detail(canvas, game, play, 30)
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
def test_detail_texts_keep_clearance_worst_case(sign, request):
    canvas = request.getfixturevalue(sign)
    game = dataclasses.replace(
        GAME, away="WSH", home="JAX", away_score=48, home_score=48
    )
    play = _play(
        team="WSH",
        away_score=48,
        home_score=48,
        extra="+2PT",
        period_label="2OT",
        clock="14:59",
        text="MARQUISE BROWN-WILLIAMSON 99 YD PASS FROM JAYDEN DANIELS-OKONKWO",
    )
    boxes = _detail_boxes(canvas, game, play)
    assert any(b[0] == "2OT 14:59" for b in boxes)
    assert sum(1 for b in boxes if b[0] == "48") == 2
    long_text = [b for b in boxes if b[0].startswith("MARQUISE")]
    assert long_text and long_text[0][0].endswith("…")
    _assert_clearance(boxes)


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
def test_detail_typical_keeps_clearance(sign, request):
    canvas = request.getfixturevalue(sign)
    _assert_clearance(_detail_boxes(canvas, GAME, TD))


# --------------------------------------------------------------- card


def test_detail_ignores_bg_color_at_scale_gt1(bigsign):
    # #105: bg_color is a scale-1 option; the hi-res detail card paints its
    # own palette like every other hi-res renderer.
    c = _card(bg_color=make_color(40, 0, 0))
    c.queue_plays([_play()])
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
    c.queue_plays([_play()])
    c.reset_frame()
    for _ in range(FLASH_FRAMES + 1):
        c.advance_frame()
    c.draw(smallsign)
    assert (40, 0, 0) in set(_pixels(smallsign).values())


def test_hold_time_extends_while_celebration_pending():
    c = _card(base_hold=3.0)
    assert c.hold_time == 3.0
    c.queue_plays([_play()])
    assert c.hold_time == pytest.approx(4.0 + 4.0)  # no visit yet: pending
    c.reset_frame()
    assert c.hold_time == pytest.approx(8.0)  # the visit's snapshot


@pytest.mark.parametrize(
    ("base", "n", "want"),
    [(0.0, 1, 8.0), (3.0, 2, 12.0), (10.0, 1, 14.0), (10.0, 3, 22.0)],
)
def test_hold_time_is_celebration_plus_board_floor(base, n, want):
    c = _card(base_hold=base)
    c.queue_plays([_play(key=str(i), away_score=20 + 7 * (i + 1)) for i in range(n)])
    assert abs(card_mod.CELEBRATION_SECONDS - 4.0) < 1e-9
    assert card_mod.BOARD_FLOOR == 4.0
    assert c.hold_time == pytest.approx(want)


def test_hold_time_without_plays_is_base_hold():
    c = _card(base_hold=6.0)
    c.reset_frame()
    assert c.hold_time == 6.0


def test_play_queued_mid_visit_waits_for_next_turn(bigsign):
    c = _card(base_hold=3.0)
    c.reset_frame()
    for _ in range(30):
        c.advance_frame()
        c.draw(bigsign)
    c.queue_plays([_play()])
    assert c.hold_time == 3.0
    with mock.patch.object(card_mod, "render_scoreboard") as spy:
        for _ in range(30):
            c.advance_frame()
            c.draw(bigsign)
    assert spy.call_count == 30
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
    assert flash.call_count == FLASH_FRAMES - 1
    assert detail.call_count == CELEBRATION_FRAMES - FLASH_FRAMES
    c.reset_frame()
    assert c.pending == []


def test_flash_uses_kind_word(bigsign):
    c = _card()
    c.queue_plays([_play(kind="FG", extra="", away_score=23)])
    c.reset_frame()
    with mock.patch.object(card_mod, "render_flash") as flash:
        c.advance_frame()
        c.draw(bigsign)
    assert flash.call_args.args[3] == "FIELD GOAL"


def test_no_visit_snapshot_renders_board(bigsign):
    c = _card()
    c.queue_plays([_play()])
    with mock.patch.object(card_mod, "render_scoreboard") as spy:
        c.draw(bigsign)
    spy.assert_called_once()


def test_celebration_consumed_after_one_visit(bigsign):
    c = _card()
    c.queue_plays([_play()])
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


@pytest.mark.parametrize("layout", ["ticker", "scoreboard"])
@pytest.mark.parametrize("sign", ["smallsign", "bigsign"])
def test_celebration_on_every_layout_is_held(layout, sign, request):
    canvas = request.getfixturevalue(sign)
    c = _card(layout=layout)
    c.queue_plays([_play()])
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
    c.queue_plays([_play()])
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
    c.queue_plays([_play()])
    c.reset_frame()
    assert len(c.pending) == 1


def test_untracked_score_highlights_instead(bigsign):
    c = _card(tracked=("PHI",))
    c.queue_plays([_play(team="NYG", away_score=20, home_score=24)])
    assert c.pending == []
    assert c.highlight == ("NYG", HIGHLIGHT_FRAMES)
    c.reset_frame()
    with mock.patch.object(card_mod, "render_scoreboard") as spy:
        c.advance_frame()
        c.draw(bigsign)
    assert spy.call_args.kwargs["highlight"] == ("NYG", 0.0)
    c.reset_frame()
    assert c.highlight is None  # shown once: consumed


def test_empty_tracked_never_celebrates():
    c = _card(tracked=())
    c.queue_plays([_play()])
    assert c.pending == [] and c.highlight == ("PHI", HIGHLIGHT_FRAMES)


def test_queue_caps_at_three():
    c = _card()
    c.queue_plays([_play(key=str(i), away_score=20 + 3 * (i + 1)) for i in range(5)])
    assert [p.key for p in c.pending] == ["2", "3", "4"]


def test_follow_up_replaces_pending_snapshot():
    c = _card()
    c.queue_plays([_play(key="a", extra="", away_score=26)])
    c.queue_plays([_play(key="b", extra="+PAT", away_score=27)])
    assert [(p.key, p.extra) for p in c.pending] == [("b", "+PAT")]
    c.replace_plays([_play(key="c", extra="+2PT", away_score=28)])
    assert [(p.key, p.extra) for p in c.pending] == [("c", "+2PT")]
    c.replace_plays([_play(key="d", away_score=40)])  # nothing to replace
    assert [p.key for p in c.pending] == ["c"]


def test_overturned_play_drops_pending():
    c = _card()
    c.queue_plays([_play(away_score=27)])
    c.game = dataclasses.replace(GAME, away_score=20)
    c.drop_overturned()
    assert c.pending == []


def test_paused_frames_do_not_advance_celebration(bigsign):
    c = _card()
    c.queue_plays([_play()])
    c.reset_frame()
    c.pause_frame()
    before = c._frame_count
    with mock.patch.object(card_mod, "render_scoreboard") as spy:
        for _ in range(10):
            c.advance_frame()
            c.draw(bigsign)
    assert c._frame_count == before
    assert spy.call_count == 10  # paused = compositing: the board, never the flash
    c.resume_frame()
    c.reset_frame()
    assert len(c.pending) == 1  # never shown live: not consumed


def test_demo_rearms_every_third_visit(bigsign):
    c = _card(demo_plays=(TD,))
    c.queue_plays([TD])
    for visit in range(1, 8):
        c.reset_frame()
        had = bool(c.pending)
        for _ in range(3):
            c.advance_frame()
            c.draw(bigsign)
        # Visit 1 celebrates; 2, 3 do not; 4 does again; then 7.
        assert had is (visit in (1, 4, 7)), visit
    assert card_mod.DEMO_EVERY == 3


# ------------------------------------------- bg_color is scale-1 only (#105)

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
    w = FootballScoreMonitor(session=None, teams=["PHI"], demo=True)
    w._tz = TZ
    w._load_demo()
    memos = {id(c.scale_memo) for c in w.feed_stories}
    assert len(memos) == 1


def _paint_panel(canvas, rgb=WHITE):
    real = unwrap_to_real(canvas)
    for x in range(real.width):
        for y in range(real.height):
            real.SetPixel(x, y, *rgb)


# A preceding widget's color that no football renderer paints (the
# smallsign detail draws its play text white).
MAGENTA = (255, 0, 255)


@pytest.mark.parametrize("layout", ["scoreboard", "ticker"])
@pytest.mark.parametrize("scoring", [False, True])
def test_slideshow_visit_cached_bg_never_shows_at_scale_gt1(layout, scoring, bigsign):
    # Core reads `bg_color` ONCE per slideshow visit (`_swap_and_scroll`)
    # and fills with that cached value every tick: a widget's first hi-res
    # visit caches the configured color before any draw has set the memo.
    c = _card(layout=layout, bg_color=make_color(*BG))
    if scoring:
        c.queue_plays([_play()])
    c.reset_frame()
    cached = c.bg_color
    assert cached is not None  # the residual this test exists for
    real = unwrap_to_real(bigsign)
    for _ in range(CELEBRATION_FRAMES + 20):
        c.advance_frame()
        bigsign.Fill(cached.red, cached.green, cached.blue)
        c.draw(bigsign)
        assert BG not in set(real._pixels.values())


@pytest.mark.parametrize("layout", ["scoreboard", "ticker"])
def test_hires_draw_right_of_another_widget_keeps_it(layout, bigsign):
    # Side-by-side: at cursor_pos > 0 a preceding widget owns the left of
    # the panel; the board/crawl must not wipe it.
    c = _card(layout=layout, bg_color=make_color(*BG))
    c.advance_frame()
    _paint_panel(bigsign)
    c.draw(bigsign, cursor_pos=40)
    assert unwrap_to_real(bigsign)._pixels.get((0, 0)) == WHITE


def test_paused_hires_draw_never_clears(bigsign):
    # Transition compositing paints outgoing and incoming into one canvas.
    c = _card(bg_color=make_color(*BG))
    c.pause_frame()
    _paint_panel(bigsign)
    c.draw(bigsign)
    assert unwrap_to_real(bigsign)._pixels.get((0, 0)) == WHITE


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
    c.queue_plays([_play()])
    with (
        mock.patch.object(card_mod, "render_flash") as flash,
        mock.patch.object(card_mod, "render_scoreboard") as board,
    ):
        _scroll_frames(c, bigsign, 2)
    # 1st advance -> frame 1 -> the run self-starts at origin 1 -> phase 0
    # (flash_on); 2nd -> phase 1 (flash_on). Two flash paints, no board.
    assert [call.args[2] for call in flash.call_args_list] == [True, True]
    assert [call.args[3] for call in flash.call_args_list] == ["TOUCHDOWN"] * 2
    board.assert_not_called()
    assert c._run_start == 1


def test_scroll_mode_never_starts_on_frame_zero_draw(bigsign):
    # e.g. `_scroll_and_delay`'s initial draw before any advance
    c = _card()
    c.queue_plays([_play()])
    with mock.patch.object(card_mod, "render_scoreboard") as board:
        c.draw(bigsign)
    board.assert_called_once()
    assert c._playing is None and c._run_start is None


def test_scroll_mode_run_plays_whole_timeline_then_consumes(bigsign):
    c = _card()
    c.queue_plays([_play()])
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


def test_scroll_mode_play_queued_mid_run_waits_for_next_run(bigsign):
    c = _card()
    # Distinct pre-try snapshots, so the second never folds into the first.
    p1 = _play(key="p1", extra="", away_score=26)
    p2 = _play(key="p2", kind="FG", extra="", away_score=29)
    c.queue_plays([p1])
    _scroll_frames(c, bigsign, 10)  # frames 1-10: run started at 1
    c.queue_plays([p2])
    assert c._playing == [p1]
    _scroll_frames(c, bigsign, CELEBRATION_FRAMES - 10)  # frames 11-80
    assert c._playing == [p1]  # p1's timeline (phases 0-79) still playing
    with mock.patch.object(card_mod, "render_scoreboard") as board:
        _scroll_frames(c, bigsign, 1)  # frame 81: p1's run ends
    board.assert_called_once()
    assert c._playing is None and c.pending == [p2]
    _scroll_frames(c, bigsign, 1)  # the next live draw self-starts p2
    assert c._playing == [p2] and c._run_start == CELEBRATION_FRAMES + 2


def test_scroll_mode_extra_point_folds_into_running_touchdown(bigsign):
    # The +PAT follow-up swaps the running snapshot (same pre-try score),
    # never a second run.
    c = _card()
    c.queue_plays([_play(key="td", extra="", away_score=26)])
    _scroll_frames(c, bigsign, 5)
    c.queue_plays([_play(key="pat", extra="+PAT", away_score=27)])
    assert [p.key for p in c._playing] == ["pat"]
    assert [p.key for p in c.pending] == ["pat"]
    _scroll_frames(c, bigsign, CELEBRATION_FRAMES)  # frames 6-85: run ends
    assert c.pending == [] and c._playing is None


def test_scroll_mode_paused_draws_do_not_advance_or_consume(bigsign):
    c = _card()
    c.queue_plays([_play()])
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
    c.queue_plays([_play()])
    c._frame_count = 5
    c.pause_frame()
    c.draw(bigsign)
    assert c._playing is None and c._run_start is None


def test_scroll_mode_takes_over_full_panel(bigsign):
    c = _card(layout="ticker")
    c.queue_plays([_play()])
    c.advance_frame()
    _, cursor = c.draw(bigsign, cursor_pos=-37)
    assert cursor == bigsign.width
    real = unwrap_to_real(bigsign)
    assert sum(1 for v in real._pixels.values() if v == PHI) > 0.5 * (
        real.width * real.height
    )


def test_scroll_mode_bye_card_without_plays_draws_board(bigsign):
    # A bye-week next-game card never has plays: the scroll draws its board.
    c = _card(bye=True)
    with mock.patch.object(card_mod, "render_scoreboard") as board:
        _scroll_frames(c, bigsign, 3)
    assert board.call_count == 3 and board.call_args.kwargs["bye"] is True
    assert c._playing is None and c._run_start is None


def test_scroll_mode_demo_rearms_after_rest(bigsign):
    # No visits to count in a scroll section: a demo card re-celebrates
    # DEMO_REST_FRAMES live frames after its self-started run ended.
    c = _card(demo_plays=(TD,))
    c.queue_plays(list(c.demo_plays))
    _scroll_frames(c, bigsign, CELEBRATION_FRAMES + 1)  # run 1, ends at 81
    assert c.pending == [] and c._playing is None
    with mock.patch.object(card_mod, "render_flash") as flash:
        _scroll_frames(c, bigsign, card_mod.DEMO_REST_FRAMES - 1)
    flash.assert_not_called()  # resting: the board, no celebration
    with mock.patch.object(card_mod, "render_flash") as flash:
        _scroll_frames(c, bigsign, 1)
    flash.assert_called_once()  # re-armed and self-started on this frame
    assert c._run_start == CELEBRATION_FRAMES + 1 + card_mod.DEMO_REST_FRAMES


def test_scroll_mode_demo_rest_paused_frames_do_not_rearm(bigsign):
    c = _card(demo_plays=(TD,))
    c.queue_plays(list(c.demo_plays))
    _scroll_frames(c, bigsign, CELEBRATION_FRAMES + 1)
    c._frame_count += card_mod.DEMO_REST_FRAMES
    c.pause_frame()
    c.draw(bigsign)
    assert c.pending == []  # transition compositing never re-arms


def test_non_demo_card_never_rests(bigsign):
    c = _card()
    c.queue_plays([_play()])
    _scroll_frames(c, bigsign, CELEBRATION_FRAMES + 1 + card_mod.DEMO_REST_FRAMES)
    assert c._demo_rest_from is None and c.pending == [] and c._playing is None


def test_slideshow_path_unchanged_with_run_start(bigsign):
    c = _card()
    c.queue_plays([_play()])
    c.reset_frame()
    assert c._run_start is None
    _scroll_frames(c, bigsign, 5)
    c.queue_plays([_play(key="p2", kind="FG", extra="", away_score=23)])
    assert len(c._playing) == 1  # mid-visit play waits (existing contract)
    _scroll_frames(c, bigsign, CELEBRATION_FRAMES)  # run over: board, no start
    assert c._run_start is None and len(c._playing) == 1
    assert len(c.pending) == 2  # nothing consumed until the next visit entry
    c.reset_frame()
    assert [p.key for p in c.pending] == ["p2"]


def test_reset_frame_clears_a_self_started_run(bigsign):
    # A scroll card entering a slideshow-style visit (e.g. a transition's
    # reset) restarts at origin 0 from the visit snapshot.
    c = _card()
    c.queue_plays([_play()])
    _scroll_frames(c, bigsign, 3)
    assert c._run_start == 1
    c.reset_frame()
    assert c._run_start is None and c._frame_count == 0


@pytest.mark.parametrize("sign", ["smallsign", "bigsign"])
@pytest.mark.parametrize("frames", [3, FLASH_FRAMES + 1])  # flash_off, detail
def test_takeover_clears_preceding_widget(sign, frames, request):
    # Side-by-side: core resets once, a preceding widget paints, then the
    # card's takeover must own the whole panel.
    canvas = request.getfixturevalue(sign)
    c = _card()
    c.queue_plays([_play()])
    for _ in range(frames):
        c.advance_frame()
        _paint_panel(canvas, MAGENTA)
        c.draw(canvas, cursor_pos=canvas.width - 10)
    assert MAGENTA not in set(_pixels(canvas).values())


def test_takeover_clear_uses_bg_color_at_scale_1(smallsign):
    c = _card(bg_color=make_color(*BG))
    c.queue_plays([_play()])
    for _ in range(3):  # frame 3 = flash_off
        c.advance_frame()
        _paint_panel(smallsign, MAGENTA)
        c.draw(smallsign)
    px = list(_pixels(smallsign).values())
    assert MAGENTA not in px and BG in px


def test_hidden_card_run_does_not_advance(bigsign):
    # Core advances every buffered widget each tick but stops drawing at
    # cursor >= width: B's run must advance only on frames B is drawn.
    a, b = _card(), _card()
    b.queue_plays([_play(key="b")])
    b.advance_frame()
    a.advance_frame()
    b.draw(bigsign, cursor_pos=200)  # B self-starts: phase 0
    a.queue_plays([_play(key="a")])
    for _ in range(CELEBRATION_FRAMES):
        a.advance_frame()
        b.advance_frame()  # buffered, advanced, but hidden behind A
        a.draw(bigsign)
    assert b._playing is not None and [p.key for p in b.pending] == ["b"]
    with mock.patch.object(card_mod, "render_flash") as flash:
        b.advance_frame()
        b.draw(bigsign)
    assert flash.call_args.args[2] is True  # phase 1: still flash_on
