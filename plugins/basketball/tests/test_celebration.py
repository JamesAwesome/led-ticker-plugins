"""Final-buzzer win celebration: the timeline, the flash + detail renderers
per sign, and the card's queue/consume/self-start lifecycle."""

import dataclasses
import unittest.mock as mock

import pytest
from led_ticker.plugin import make_color, measure_width, resolve_font, unwrap_to_real

import led_ticker_basketball._card as card_mod
from led_ticker_basketball import _celebration as celeb
from led_ticker_basketball import _palette as pal
from led_ticker_basketball._card import BasketballGameCard
from led_ticker_basketball._celebration import (
    CELEBRATION_FRAMES,
    FLASH_FRAMES,
    MAX_QUEUED,
    phase_at,
    pulse,
    render_detail,
    render_flash,
    win_word,
)
from led_ticker_basketball._models import FinalEvent, Leader, build_demo_games

from .conftest import TZ

NOW = 1_700_000_000.0
GAMES, FINAL = build_demo_games(NOW)
GAME = GAMES[0]  # PHI @ NY, live Q4; FINAL: PHI beats NY 112-108
PHI = (0, 107, 182)
WHITE = (255, 255, 255)


def _ev(**over):
    return dataclasses.replace(FINAL, **over)


def _card(layout="auto", tracked=("PHI",), **kw):
    return BasketballGameCard(
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
    assert (FLASH_FRAMES, CELEBRATION_FRAMES, MAX_QUEUED) == (12, 80, 1)
    assert card_mod.MAX_QUEUED == MAX_QUEUED


def test_phase_timeline():
    assert phase_at(0, 1) == (0, "flash_on", 0)
    assert phase_at(2, 1) == (0, "flash_off", 2)
    assert phase_at(12, 1) == (0, "detail", 12)
    assert phase_at(79, 1) == (0, "detail", 79)
    assert phase_at(80, 1) is None
    assert phase_at(80, 2) == (1, "flash_on", 0)
    assert phase_at(0, 0) is None
    assert phase_at(-1, 1) is None


def test_win_word_falls_back_to_abbrev():
    assert win_word(FINAL, 30, 24) == "PHI WIN"
    assert win_word(FINAL, 1000, 24) == "76ERS WIN"
    assert win_word(FINAL, 1, 0) == "76ERS WIN"  # size 0: the caller measures


# ------------------------------------------------------------- render


def test_flash_knocks_out_word(bigsign):
    render_flash(bigsign, pal.chip("PHI")[0], True, FINAL)
    real = unwrap_to_real(bigsign)
    px = real._pixels
    total = real.width * real.height
    assert sum(1 for v in px.values() if v == PHI) > total * 0.6
    band = [
        (x, y)
        for x in range(real.width // 8, 7 * real.width // 8)
        for y in range(16, 48)
    ]
    assert any(px.get(p, (0, 0, 0)) == (0, 0, 0) for p in band)
    assert px[(0, 0)] == PHI and px[(real.width - 1, real.height - 1)] == PHI


def test_flash_knocks_out_word_smallsign(smallsign):
    calls = []
    orig = celeb.draw_text

    def spy(cv, font, text, x, y, color):
        calls.append(text)
        return orig(cv, font, text, x, y, color)

    with mock.patch.object(celeb, "draw_text", spy):
        render_flash(smallsign, pal.chip("PHI")[0], True, FINAL)
    assert calls == ["76ERS WIN"]
    real = unwrap_to_real(smallsign)
    unlit = real.width * real.height - sum(1 for v in real._pixels.values() if v == PHI)
    assert 0 < unlit < real.width * real.height * 0.4


def test_flash_long_nickname_falls_back_on_every_sign(smallsign, longboi):
    from led_ticker.plugin import HeadlessBackend

    narrow = HeadlessBackend(60, 16).create_canvas()
    calls = []
    orig = celeb.draw_text

    def spy(cv, font, text, x, y, color):
        calls.append(text)
        return orig(cv, font, text, x, y, color)

    ev = _ev(winner="MIN", loser="NY")
    with mock.patch.object(celeb, "draw_text", spy):
        render_flash(narrow, pal.chip("MIN")[0], True, ev)
    assert calls == ["MIN WIN"]
    words = []
    orig_h = celeb.hires

    def hspy(shim, text, x, y_top, color, size):
        words.append(text)
        return orig_h(shim, text, x, y_top, color, size)

    with mock.patch.object(celeb, "hires", hspy):
        render_flash(longboi, pal.chip("MIN")[0], True, ev)  # 512 px: fits
    assert words == ["TIMBERWOLVES WIN"]


@pytest.mark.parametrize("sign", ["smallsign", "longboi"])
def test_flash_other_signs(sign, request):
    canvas = request.getfixturevalue(sign)
    render_flash(canvas, pal.chip("PHI")[0], True, FINAL)
    real = unwrap_to_real(canvas)
    unlit = real.width * real.height - sum(1 for v in real._pixels.values() if v == PHI)
    assert 0 < unlit < real.width * real.height * 0.4


def test_flash_off_is_dark(bigsign):
    render_flash(bigsign, pal.chip("PHI")[0], False, FINAL)
    assert unwrap_to_real(bigsign).count_nonzero() == 0


def _rgb(color):
    return (color.red, color.green, color.blue)


def _colors(boxes):
    """text -> the set of (r, g, b) it was painted in."""
    out = {}
    for b in boxes:
        out.setdefault(b[0], set()).add(b[4])
    return out


def _detail_boxes(canvas, game, ev, frame=30, **kw):
    """(text, x0, x1, (top, bottom), rgb) per painted text: cap band for hi-res,
    the band row for the bitmap font."""
    boxes = []
    if celeb.safe_scale(canvas) <= 1:
        real_draw = celeb.draw_text

        def spy_bmp(cv, font, text, x, y, color):
            w = measure_width(font, text, cv)
            boxes.append((text, x, x + w, (y - 7, y), _rgb(color)))
            return real_draw(cv, font, text, x, y, color)

        with mock.patch.object(celeb, "draw_text", spy_bmp):
            render_detail(canvas, game, ev, frame, **kw)
        return boxes
    real_hires = celeb.hires

    def spy(shim, text, x, y_top, color, size):
        base = y_top + resolve_font("Inter-Bold", size).ascent
        w = celeb.text_width(size, text)
        boxes.append((text, x, x + w, (base - round(size * 0.72), base), _rgb(color)))
        return real_hires(shim, text, x, y_top, color, size)

    with mock.patch.object(celeb, "hires", spy):
        render_detail(canvas, game, ev, frame, **kw)
    return boxes


def _assert_clearance(boxes, width):
    for b in boxes:
        assert b[1] >= 0 and b[2] <= width, b
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            (at, ab), (bt, bb) = a[3], b[3]
            if at > bb or bt > ab:
                continue  # different vertical bands
            gap = max(b[1] - a[2], a[1] - b[2])
            assert gap >= 6, (a, b)


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
@pytest.mark.parametrize("ot", [False, True])
def test_detail_draws_scores_final_and_leader(sign, ot, request):
    canvas = request.getfixturevalue(sign)
    boxes = _detail_boxes(canvas, GAME, _ev(final_ot=ot))
    texts = [b[0] for b in boxes]
    colors = _colors(boxes)
    assert texts.count("112") == 1 and texts.count("108") == 1
    assert "PHI" in texts and "NY" in texts
    # Each abbreviation in its team's primary; the loser's score white.
    assert colors["PHI"] == {_rgb(pal.chip("PHI")[0])}
    assert colors["NY"] == {_rgb(pal.chip("NY")[0])}
    assert colors["108"] == {_rgb(pal.WHITE)}
    if sign == "smallsign":
        label = "F/OT" if ot else "FINAL"
        assert not any("EMBIID" in t for t in texts)  # dropped at this size
    else:
        label = "FINAL/OT" if ot else "FINAL"
        assert colors["J. EMBIID 31 PTS"] == {_rgb(pal.CYAN)}
    assert colors[label] == {_rgb(pal.AMBER)}


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
@pytest.mark.parametrize("frame", [40, 60])
def test_detail_pulses_winner_score(sign, frame, request):
    canvas = request.getfixturevalue(sign)
    assert pulse(40) != pulse(60)  # the two frames really differ
    colors = _colors(_detail_boxes(canvas, GAME, FINAL, frame))
    # PHI (winner, away) 112 pulses; NY (loser) 108 stays white.
    assert colors["112"] == {_rgb(pal.dim(pal.WHITE, pulse(frame)))}
    assert colors["108"] == {_rgb(pal.WHITE)}


@pytest.mark.parametrize(
    ("sign", "chip"),
    [
        ("smallsign", (0, 0, 2, 15)),
        ("bigsign", (3, 5, 8, 26)),
        ("longboi", (6, 8, 13, 56)),
    ],
)
def test_chip_fallback_painted_in_winner_primary(sign, chip, request, monkeypatch):
    canvas = request.getfixturevalue(sign)
    calls = []
    real_rect = celeb.rect

    def rect_spy(real, x0, y0, x1, y1, color):
        calls.append(((x0, y0, x1, y1), _rgb(color)))
        return real_rect(real, x0, y0, x1, y1, color)

    monkeypatch.setattr(celeb, "rect", rect_spy)
    monkeypatch.setattr(celeb, "sprite", lambda a, s: None)
    render_detail(canvas, GAME, FINAL, 30)
    assert (chip, _rgb(pal.chip("PHI")[0])) in calls


def test_detail_uses_logo_when_available_and_chip_when_not(bigsign, monkeypatch):
    logo_calls = []
    rect_calls = []
    real_rect = celeb.rect

    def logo_spy(real, spr, x, y):
        logo_calls.append((spr, x, y))

    def rect_spy(real, x0, y0, x1, y1, color):
        rect_calls.append((x0, y0, x1, y1))
        return real_rect(real, x0, y0, x1, y1, color)

    monkeypatch.setattr(celeb, "paint_logo", logo_spy)
    monkeypatch.setattr(celeb, "rect", rect_spy)
    render_detail(bigsign, GAME, FINAL, 30, logos=True)
    assert len(logo_calls) == 1 and logo_calls[0][1] == 4
    assert (3, 5, 8, 26) not in rect_calls

    logo_calls.clear()
    monkeypatch.setattr(celeb, "sprite", lambda a, s: None)
    render_detail(bigsign, GAME, FINAL, 30, logos=True)
    assert logo_calls == []
    assert (3, 5, 8, 26) in rect_calls


def test_detail_logos_false_draws_chip(bigsign, monkeypatch):
    logo_calls = []
    monkeypatch.setattr(celeb, "paint_logo", lambda *a: logo_calls.append(a))
    texts = _detail_boxes(bigsign, GAME, FINAL, logos=False)
    assert logo_calls == []
    final = next(b for b in texts if b[0] == "FINAL")
    assert final[1] == 14  # the chip's content edge


WORST_GAME = dataclasses.replace(GAME, away="UTAH", home="WSH")
WORST = FinalEvent(
    key="w",
    game_id="w",
    winner="UTAH",
    loser="WSH",
    away_score=148,
    home_score=147,
    final_ot=True,
    leader=Leader("G. ANTETOKOUNMPO", 50),
)


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
@pytest.mark.parametrize("logos", [True, False])
def test_detail_texts_keep_clearance_worst_case(sign, logos, request):
    canvas = request.getfixturevalue(sign)
    boxes = _detail_boxes(canvas, WORST_GAME, WORST, logos=logos)
    texts = [b[0] for b in boxes]
    assert "148" in texts and "147" in texts
    if sign != "smallsign":
        assert any("ANTETOKOUNMPO" in t for t in texts)
    _assert_clearance(boxes, unwrap_to_real(canvas).width)


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
def test_detail_typical_keeps_clearance(sign, request):
    canvas = request.getfixturevalue(sign)
    _assert_clearance(_detail_boxes(canvas, GAME, FINAL), unwrap_to_real(canvas).width)


@pytest.mark.parametrize("sign", ["smallsign", "bigsign", "longboi"])
def test_detail_sparse_event_never_raises(sign, request):
    canvas = request.getfixturevalue(sign)
    game = dataclasses.replace(GAME, away="ZZZ", home="")
    sparse = FinalEvent(
        key="s",
        game_id="s",
        winner="ZZZ",
        loser="",
        away_score=0,
        home_score=0,
        final_ot=False,
        leader=None,
    )
    render_detail(canvas, game, sparse, 30)
    render_flash(canvas, pal.chip("ZZZ")[0], True, sparse)
    render_flash(canvas, pal.chip("")[0], True, dataclasses.replace(sparse, winner=""))


# --------------------------------------------------------------- card


def test_hold_time_extends_while_celebration_pending():
    c = _card(base_hold=3.0)
    assert c.hold_time == 3.0
    c.queue_final(FINAL)
    # one 4 s celebration + max(base_hold, BOARD_FLOOR = 4 s) for the board
    assert c.hold_time == pytest.approx(4.0 + 4.0)
    c.reset_frame()
    assert c.hold_time == pytest.approx(8.0)  # the visit's snapshot


def test_card_calls_flash_with_the_event(bigsign):
    c = _card()
    c.queue_final(FINAL)
    c.reset_frame()
    with mock.patch.object(celeb, "render_flash") as flash:
        c.advance_frame()
        c.draw(bigsign)
    args = flash.call_args.args
    assert args[1] == pal.chip("PHI")[0] and args[2] is True and args[3] is FINAL


def test_celebration_consumed_after_one_visit(bigsign):
    c = _card()
    c.queue_final(FINAL)
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


def test_celebration_plays_flash_then_detail(bigsign):
    c = _card()
    c.queue_final(FINAL)
    c.reset_frame()
    with (
        mock.patch.object(celeb, "render_flash", wraps=celeb.render_flash) as flash,
        mock.patch.object(celeb, "render_detail", wraps=celeb.render_detail) as det,
    ):
        for _ in range(CELEBRATION_FRAMES - 1):
            c.advance_frame()
            c.draw(bigsign)
    assert flash.call_count == FLASH_FRAMES - 1
    assert det.call_count == CELEBRATION_FRAMES - FLASH_FRAMES


def test_reset_without_drawing_keeps_pending():
    c = _card()
    c.queue_final(FINAL)
    c.reset_frame()
    assert len(c.pending) == 1


def test_queue_caps_at_one():
    c = _card()
    c.queue_final(_ev(key="a"))
    c.queue_final(_ev(key="b"))
    assert len(c.pending) == 1 and c.pending[0].key == "b"


def test_paused_frames_do_not_advance_celebration(bigsign):
    c = _card()
    c.queue_final(FINAL)
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
    c = _card(demo_final=FINAL)
    c.queue_final(FINAL)
    for visit in range(1, 8):
        c.reset_frame()
        had = bool(c.pending)
        for _ in range(3):
            c.advance_frame()
            c.draw(bigsign)
        # Visit 1 celebrates; 2, 3 do not; 4 does again; then 7.
        assert had is (visit in (1, 4, 7)), visit
    assert card_mod.DEMO_EVERY == 3


def _scroll_frames(card, canvas, n):
    """Tick like `_scroll_side_by_side`: advance then draw, never reset_frame."""
    out = []
    for _ in range(n):
        card.advance_frame()
        out.append(card.draw(canvas))
    return out


def test_scroll_mode_starts_pending_celebration_on_first_live_draw(bigsign):
    c = _card()
    c.queue_final(FINAL)
    with (
        mock.patch.object(celeb, "render_flash") as flash,
        mock.patch.object(card_mod, "render_scoreboard") as board,
    ):
        _scroll_frames(c, bigsign, 2)
    assert [call.args[2] for call in flash.call_args_list] == [True, True]
    assert [call.args[3] for call in flash.call_args_list] == [FINAL] * 2
    board.assert_not_called()
    assert c._run_start == 1


def test_scroll_mode_run_freezes_cursor_until_next_pass(bigsign):
    c = _card()
    c.queue_final(FINAL)
    pos = bigsign.width
    with (
        mock.patch.object(celeb, "render_flash"),
        mock.patch.object(celeb, "render_detail"),
        mock.patch.object(card_mod, "render_scoreboard") as board,
    ):
        for _ in range(CELEBRATION_FRAMES):  # self-starts on the first draw
            c.advance_frame()
            c.draw(bigsign, pos)
            pos -= 1
        c.advance_frame()
        _, cursor = c.draw(bigsign, pos)  # run ends: the board draws
    assert pos == bigsign.width - CELEBRATION_FRAMES
    assert cursor == bigsign.width + bigsign.width  # frozen at the takeover
    assert board.call_args.kwargs["x_offset"] == bigsign.width
    c.advance_frame()
    with mock.patch.object(card_mod, "render_scoreboard") as board:
        _, cursor = c.draw(bigsign, 30)
    assert cursor == 30 + bigsign.width
    assert board.call_args.kwargs["x_offset"] == 30


def _paint_panel(canvas, rgb=WHITE):
    real = unwrap_to_real(canvas)
    for x in range(real.width):
        for y in range(real.height):
            real.SetPixel(x, y, *rgb)


MAGENTA = (255, 0, 255)  # no basketball renderer paints it
BG = (40, 0, 0)


@pytest.mark.parametrize("sign", ["smallsign", "bigsign"])
@pytest.mark.parametrize("frames", [3, FLASH_FRAMES + 1])  # flash_off, detail
def test_takeover_clears_preceding_widget(sign, frames, request):
    canvas = request.getfixturevalue(sign)
    c = _card()
    c.queue_final(FINAL)
    for _ in range(frames):
        c.advance_frame()
        _paint_panel(canvas, MAGENTA)
        c.draw(canvas, cursor_pos=canvas.width - 10)
    assert MAGENTA not in set(_pixels(canvas).values())


@pytest.mark.parametrize("sign", ["smallsign", "bigsign"])
@pytest.mark.parametrize("frames", [3, FLASH_FRAMES + 1])
def test_takeover_clear_uses_bg_color_at_every_scale(sign, frames, request):
    canvas = request.getfixturevalue(sign)
    c = _card(bg_color=make_color(*BG))
    c.queue_final(FINAL)
    for _ in range(frames):
        c.advance_frame()
        _paint_panel(canvas, MAGENTA)
        c.draw(canvas)
    px = list(_pixels(canvas).values())
    assert MAGENTA not in px and BG in px


def _core_tick(card, canvas, **draw_kw):
    """One engine tick as core runs it: advance, `reset_canvas` with the
    widget's `bg_color`, then draw."""
    from led_ticker.widgets._image_fit import reset_canvas

    card.advance_frame()
    reset_canvas(canvas, card.bg_color)
    return card.draw(canvas, **draw_kw)


@pytest.mark.parametrize("layout", ["scoreboard", "ticker"])
@pytest.mark.parametrize("sign", ["smallsign", "bigsign"])
@pytest.mark.parametrize("celebrating", [False, True])
def test_core_fill_of_bg_color_survives_every_scale(layout, sign, celebrating, request):
    canvas = request.getfixturevalue(sign)
    c = _card(layout=layout, bg_color=make_color(*BG))
    if celebrating:
        c.queue_final(FINAL)
        c.reset_frame()
    for i in range(FLASH_FRAMES + 2):
        _core_tick(c, canvas)
        f = i + 1  # the frame this tick drew
        if celebrating and f < FLASH_FRAMES and (f // 2) % 2 == 0:
            continue  # flash_on: the full panel is the team colour by design
        assert BG in set(_pixels(canvas).values()), i
