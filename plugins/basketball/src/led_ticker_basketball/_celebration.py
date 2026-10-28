"""Final-buzzer win celebration: the frame timeline plus the flash and
detail painters.

Timeline (engine tick = 50 ms): each final gets `CELEBRATION_FRAMES` (4 s).
The first `FLASH_FRAMES` are three on/off flashes (2 frames on, 2 off) of
the full panel in the winner's colour with `<NICKNAME> WIN` knocked out
(`<ABBREV> WIN` when the nickname does not fit); the rest is the detail
card: the winner's logo (or a colour chip), the final score with the
winner's number pulsing, `FINAL` / `FINAL/OT`, and the winner's points
leader on the bigger signs.

Every text is measured and placed with >= 6 px clearance. Sparse events
(no leader, unknown teams) render what they have and never raise.
"""

import math

from led_ticker.plugin import (
    FONT_SMALL,
    Color,
    Font,
    compute_baseline_for_band,
    draw_text,
    make_color,
    measure_width,
    resolve_font,
    safe_scale,
    unwrap_to_real,
)

from led_ticker_basketball import _palette as pal
from led_ticker_basketball._logos import LOGO_BIG, LOGO_LONG, paint_logo, sprite
from led_ticker_basketball._models import FinalEvent, GameInfo, leader_text
from led_ticker_basketball._paint import (
    fit_size,
    fit_text,
    hires,
    js_round,
    phys_wrap,
    rect,
    text_width,
)
from led_ticker_basketball.teams import team

FLASH_FRAMES = 12
CELEBRATION_FRAMES = 80
CELEBRATION_SECONDS = CELEBRATION_FRAMES * 0.05  # 4 s at the 50 ms tick
MAX_QUEUED = 1
HIGHLIGHT_FRAMES = 30

_GAP = 6
_FONT = "Inter-Bold"
_BLACK = make_color(0, 0, 0)


def phase_at(frame: int, n: int) -> tuple[int, str, int] | None:
    """`(index, phase, frame_in_event)`; None once the run is over."""
    if frame < 0 or frame >= n * CELEBRATION_FRAMES:
        return None
    idx, f = divmod(frame, CELEBRATION_FRAMES)
    if f < FLASH_FRAMES:
        return idx, ("flash_on" if (f // 2) % 2 == 0 else "flash_off"), f
    return idx, "detail", f


def pulse(frame: int) -> float:
    """The score pulse, 0.55-1.0."""
    return 0.55 + 0.45 * (0.5 + 0.5 * math.cos(frame * 50 / 180))


def _full_word(ev: FinalEvent) -> str:
    return f"{team(ev.winner).nickname.upper()} WIN".strip()


def _abbrev_word(ev: FinalEvent) -> str:
    return f"{ev.winner} WIN".strip()


def win_word(ev: FinalEvent, max_w: int, size: int) -> str:
    """`<NICKNAME> WIN`, or `<ABBREV> WIN` when it measures wider than
    `max_w` at hi-res `size`. `size <= 0` returns the full form unmeasured
    (the caller measures, e.g. with the bitmap font)."""
    full = _full_word(ev)
    if size <= 0 or text_width(size, full) <= max_w:
        return full
    return _abbrev_word(ev)


def _final_label(ev: FinalEvent) -> str:
    return "FINAL/OT" if ev.final_ot else "FINAL"


def _scores(game: GameInfo, ev: FinalEvent, frame: int):
    """[(abbrev, team colour, score text, score colour)] away then home; the
    winner's score pulses. Scores are the event's own snapshot."""
    hot = pal.dim(pal.WHITE, pulse(frame))
    return [
        (
            abbrev,
            pal.chip(abbrev)[0],
            str(score),
            hot if abbrev == ev.winner else pal.WHITE,
        )
        for abbrev, score in (
            (game.away, ev.away_score),
            (game.home, ev.home_score),
        )
    ]


# ------------------------------------------------------------- hi-res


def _base(shim, text: str, x: int, base: int, color: Color, size: int) -> int:
    """Paint with the baseline convention; return the advance."""
    if not text:
        return 0
    return hires(shim, text, x, base - resolve_font(_FONT, size).ascent, color, size)


def _centered_cap_base(size: int, height: int) -> int:
    return js_round((height + size * 0.72) / 2)


def render_flash(canvas, color: Color, on: bool, ev: FinalEvent, *, y_offset: int = 0):
    """Full-panel winner colour with the win word knocked out (unlit); dark
    when off. The word is fitted here: the nickname form when it fits the
    sign, else the abbreviation form."""
    real = unwrap_to_real(canvas)
    if not on:
        return
    scale = safe_scale(canvas)
    yo = y_offset * scale
    rect(real, 0, yo, real.width - 1, yo + real.height - 1, color)
    if scale <= 1:
        font = FONT_SMALL
        word = win_word(ev, canvas.width - 4, 0)
        if measure_width(font, word, canvas) > canvas.width - 4:
            word = _abbrev_word(ev)
        w = measure_width(font, word, canvas)
        base = compute_baseline_for_band(font, canvas.height, 1, valign="center")
        draw_text(canvas, font, word, (canvas.width - w) // 2, base + yo, _BLACK)
        return
    shim, _ = phys_wrap(canvas)
    sizes = (44, 40, 36, 32, 28) if real.width > 300 else (40, 36, 32, 28, 24)
    max_w = real.width - 8
    size = fit_size(_full_word(ev), sizes, max_w)
    word = win_word(ev, max_w, size)
    if word != _full_word(ev):
        size = fit_size(word, sizes, max_w)
    x = js_round((real.width - text_width(size, word)) / 2)
    _base(shim, word, x, _centered_cap_base(size, real.height) + yo, _BLACK, size)


def _right_run(shim, items, right: int, base_of) -> int:
    """Paint `(text, color, size)` items right-to-left ending at `right`
    with `_GAP` between; return the run's left edge."""
    x = right + _GAP
    for text, color, size in reversed([i for i in items if i[0]]):
        x -= text_width(size, text) + _GAP
        _base(shim, text, x, base_of(size), color, size)
    return x


def _final_line(shim, ev: FinalEvent, x: int, base: int, budget: int, sizes):
    """`FINAL` / `FINAL/OT` in amber, the ladder fitted to `budget`; an OT
    label that overflows even the floor shortens to `F/OT`."""
    word = _final_label(ev)
    size = fit_size(word, sizes, budget)
    if text_width(size, word) > budget and ev.final_ot:
        word = "F/OT"
        size = fit_size(word, sizes, budget)
    _base(shim, fit_text(word, budget, size), x, base, pal.AMBER, size)


def _leader_line(shim, ev: FinalEvent, x: int, base: int, budget: int, sizes):
    text = leader_text(ev.leader, style="full")
    if not text:
        return
    size = fit_size(text, sizes, budget)
    _base(shim, fit_text(text, budget, size), x, base, pal.CYAN, size)


def _logo_or_chip(
    real,
    ev: FinalEvent,
    logos: bool,
    size: int,
    x: int,
    y: int,
    chip: tuple[int, int, int, int],
) -> bool:
    """Paint the winner's logo at (x, y); True when it painted, else the
    chip rectangle `chip` = (x0, y0, x1, y1) and False."""
    spr = sprite(ev.winner, size) if logos else None
    if spr is not None:
        paint_logo(real, spr, x, y)
        return True
    cx0, cy0, cx1, cy1 = chip
    rect(real, cx0, cy0, cx1, cy1, pal.chip(ev.winner)[0])
    return False


def _detail_big(shim, real, game: GameInfo, ev: FinalEvent, frame, yo, logos):
    painted = _logo_or_chip(
        real, ev, logos, LOGO_BIG, 4, 14 + yo, (3, 5 + yo, 8, 26 + yo)
    )
    x0 = 4 + LOGO_BIG + _GAP if painted else 14
    items = []
    for abbrev, tcolor, score, scolor in _scores(game, ev, frame):
        items += [(abbrev, tcolor, 14), (score, scolor, 16)]
    right = real.width - 5
    run_x0 = _right_run(shim, items, right, lambda s: (20 if s == 14 else 21) + yo)
    _final_line(shim, ev, x0, 26 + yo, max(1, run_x0 - _GAP - x0), (22, 20, 18, 16))
    if 0 <= 32 + yo < real.height:
        for x in range(x0 if painted else 0, real.width, 3):
            real.SetPixel(x, 32 + yo, pal.DIM.red, pal.DIM.green, pal.DIM.blue)
    _leader_line(shim, ev, x0, 50 + yo, max(1, right - x0), (15, 13, 12, 11))


def _detail_long(shim, real, game: GameInfo, ev: FinalEvent, frame, yo, logos):
    painted = _logo_or_chip(
        real, ev, logos, LOGO_LONG, 8, 8 + yo, (6, 8 + yo, 13, 56 + yo)
    )
    x0 = 8 + LOGO_LONG + _GAP if painted else 22
    scores = _scores(game, ev, frame)
    right = real.width - 7
    # The stacked score column, measured, ends at `right`.
    col_w = max(
        text_width(18, abbrev) + _GAP + text_width(22, score)
        for abbrev, _, score, _ in scores
    )
    x_score = min(400, right - col_w)
    for (abbrev, tcolor, score, scolor), (ab, sb) in zip(
        scores, ((26, 28), (54, 56)), strict=True
    ):
        adv = _base(shim, abbrev, x_score, ab + yo, tcolor, 18)
        _base(shim, score, x_score + adv + _GAP, sb + yo, scolor, 22)
    col_max = max(1, x_score - _GAP - x0)
    _final_line(shim, ev, x0, 30 + yo, col_max, (34, 30, 26, 22))
    _leader_line(shim, ev, x0, 54 + yo, col_max, (20, 16, 14, 12))


# -------------------------------------------------------------- bitmap


def _detail_small(canvas, game: GameInfo, ev: FinalEvent, frame: int, yo: int, font):
    """One row: `PHI 112 NY 108 · FINAL`; the leader is dropped at this
    size, and `· FINAL` is dropped first when the run would overflow."""
    real = unwrap_to_real(canvas)
    width = canvas.width
    base = compute_baseline_for_band(font, canvas.height, 1, valign="center") + yo
    rect(real, 0, yo, 2, yo + canvas.height - 1, pal.chip(ev.winner)[0])

    def mw(text: str) -> int:
        return measure_width(font, text, canvas) if text else 0

    items: list[tuple[str, Color]] = []
    for abbrev, tcolor, score, scolor in _scores(game, ev, frame):
        items += [(abbrev, tcolor), (score, scolor)]
    items = [i for i in items if i[0]]
    tail = [("·", pal.DIM), ("F/OT" if ev.final_ot else "FINAL", pal.AMBER)]

    def run_w(run) -> int:
        return sum(mw(t) for t, _ in run) + _GAP * max(0, len(run) - 1)

    x = 5
    run = items + tail
    if x + run_w(run) > width:
        run = items
    for text, color in run:
        draw_text(canvas, font, text, x, base, color)
        x += mw(text) + _GAP


def render_detail(
    canvas,
    game: GameInfo,
    ev: FinalEvent,
    frame: int,
    *,
    y_offset: int = 0,
    font: Font | None = None,
    logos: bool = True,
) -> None:
    """The post-flash detail card for the sign `canvas` belongs to."""
    scale = safe_scale(canvas)
    if scale <= 1:
        _detail_small(
            canvas,
            game,
            ev,
            frame,
            y_offset,
            font if font is not None else FONT_SMALL,
        )
        return
    shim, real = phys_wrap(canvas)
    yo = y_offset * scale
    if real.width > 300:
        _detail_long(shim, real, game, ev, frame, yo, logos)
    else:
        _detail_big(shim, real, game, ev, frame, yo, logos)
