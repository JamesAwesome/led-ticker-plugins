"""Scoring celebration: the frame timeline plus the flash and detail painters.

Timeline (engine tick = 50 ms): each play gets `CELEBRATION_FRAMES` (4 s).
The first `FLASH_FRAMES` are three on/off flashes (2 frames on, 2 off) of
the full panel in the scoring team's colour with the kind word
(`TOUCHDOWN` / `FIELD GOAL` / `SAFETY`) knocked out; the rest is the detail
card (kind, the new score with the scoring team's number pulsing, the play
text, `+PAT` / `+2PT`, quarter + clock).

Every text is measured and placed with >= 6 px clearance; the play text
ellipsizes. Sparse plays (no text, no extra, no clock) render what they
have and never raise.
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

from led_ticker_football import _palette as pal
from led_ticker_football._logos import LOGO_LONG, LOGO_ROW, paint_logo, sprite
from led_ticker_football._models import GameInfo, ScoringPlay
from led_ticker_football._paint import (
    fit_size,
    fit_text,
    hires,
    js_round,
    phys_wrap,
    rect,
    text_width,
)

FLASH_FRAMES = 12
CELEBRATION_FRAMES = 80
CELEBRATION_SECONDS = CELEBRATION_FRAMES * 0.05  # 4 s at the 50 ms tick
MAX_QUEUED = 3
HIGHLIGHT_FRAMES = 40

_GAP = 6
_FONT = "Inter-Bold"
_BLACK = make_color(0, 0, 0)
_WORDS = {"TD": "TOUCHDOWN", "FG": "FIELD GOAL", "SAFETY": "SAFETY"}
_SHORT = {"TOUCHDOWN": "TD!", "FIELD GOAL": "FG!"}


def flash_word(kind: str) -> str:
    return _WORDS.get(kind, "SCORE")


def phase_at(frame: int, n_plays: int) -> tuple[int, str, int] | None:
    """`(play_index, phase, frame_in_play)`; None once the run is over."""
    if frame < 0 or frame >= n_plays * CELEBRATION_FRAMES:
        return None
    idx, f = divmod(frame, CELEBRATION_FRAMES)
    if f < FLASH_FRAMES:
        return idx, ("flash_on" if (f // 2) % 2 == 0 else "flash_off"), f
    return idx, "detail", f


def pulse(frame: int) -> float:
    """The score pulse, 0.55-1.0."""
    return 0.55 + 0.45 * (0.5 + 0.5 * math.cos(frame * 50 / 180))


def _time_label(play: ScoringPlay) -> str:
    return f"{play.period_label} {play.clock}".strip()


def _scores(game: GameInfo, play: ScoringPlay, frame: int):
    """[(abbrev, team colour, score text, score colour)] away then home; the
    scoring team's score pulses. Scores are the play's own snapshot."""
    hot = pal.dim(pal.WHITE, pulse(frame))
    return [
        (
            abbrev,
            pal.chip(abbrev)[0],
            str(score),
            hot if abbrev == play.team else pal.WHITE,
        )
        for abbrev, score in (
            (game.away, play.away_score),
            (game.home, play.home_score),
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


def render_flash(canvas, color: Color, on: bool, word: str, *, y_offset: int = 0):
    """Full-panel team colour with `word` knocked out (unlit); dark when off."""
    real = unwrap_to_real(canvas)
    if not on:
        return
    scale = safe_scale(canvas)
    yo = y_offset * scale
    rect(real, 0, yo, real.width - 1, yo + real.height - 1, color)
    if scale <= 1:
        font = FONT_SMALL
        if measure_width(font, word, canvas) > canvas.width - 4:
            word = _SHORT.get(word, word[:6])
        w = measure_width(font, word, canvas)
        base = compute_baseline_for_band(font, canvas.height, 1, valign="center")
        draw_text(canvas, font, word, (canvas.width - w) // 2, base + yo, _BLACK)
        return
    shim, _ = phys_wrap(canvas)
    sizes = (44, 40, 36, 32, 28) if real.width > 300 else (40, 36, 32, 28, 24)
    size = fit_size(word, sizes, real.width - 8)
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


def _kind_line(shim, play, x: int, base: int, budget: int, sizes, extra_size: int):
    """Kind word (ladder) then `+PAT`/`+2PT` in amber; both inside `budget`."""
    word = flash_word(play.kind)
    extra_w = text_width(extra_size, play.extra) + _GAP if play.extra else 0
    size = fit_size(word, sizes, max(1, budget - extra_w))
    word = fit_text(word, max(1, budget - extra_w), size)
    adv = _base(shim, word, x, base, pal.chip(play.team)[0], size)
    if play.extra:
        _base(shim, play.extra, x + adv + _GAP, base, pal.AMBER, extra_size)


def _logo_or_chip(
    real,
    play: ScoringPlay,
    logos: bool,
    size: int,
    x: int,
    y: int,
    chip: tuple[int, int, int, int],
) -> bool:
    """Paint the scoring team's logo at (x, y); True when it painted, else
    the chip rectangle `chip` = (x0, y0, x1, y1) and False."""
    spr = sprite(play.team, size) if logos and play.team else None
    if spr is not None:
        paint_logo(real, spr, x, y)
        return True
    cx0, cy0, cx1, cy1 = chip
    rect(real, cx0, cy0, cx1, cy1, pal.chip(play.team)[0])
    return False


def _detail_big(shim, real, game: GameInfo, play: ScoringPlay, frame, yo, logos):
    primary = pal.chip(play.team)[0]
    # The logo sits in the BOTTOM row (beside the play): `TOUCHDOWN` needs
    # the top row's full width left of the score run. Chip path: the chip
    # stays top-left (x 3..8) and text at 14 keeps _GAP (6) clear of it.
    painted = _logo_or_chip(
        real, play, logos, LOGO_ROW, 2, 34 + yo, (3, 5 + yo, 8, 26 + yo)
    )
    x0 = 14  # the kind word, beside the chip or alone
    x1 = 2 + LOGO_ROW + _GAP if painted else 14  # the bottom row's text
    items = []
    for abbrev, tcolor, score, scolor in _scores(game, play, frame):
        items += [(abbrev, tcolor, 14), (score, scolor, 16)]
    right = real.width - 5
    run_x0 = _right_run(shim, items, right, lambda s: (20 if s == 14 else 21) + yo)
    # The kind word alone on row 1 (the score run owns the right); the try
    # result sits on the free bottom row so TOUCHDOWN never ellipsizes.
    budget = max(1, run_x0 - _GAP - x0)
    word = flash_word(play.kind)
    size = fit_size(word, (26, 22, 20, 18, 16), budget)
    _base(shim, fit_text(word, budget, size), x0, 26 + yo, primary, size)
    if play.extra:
        _base(shim, play.extra, x1, 61 + yo, pal.AMBER, 10)
    for x in range(0, real.width, 3):
        if 0 <= 32 + yo < real.height:
            real.SetPixel(x, 32 + yo, pal.DIM.red, pal.DIM.green, pal.DIM.blue)
    time_s = _time_label(play)
    time_w = text_width(11, time_s) if time_s else 0
    if time_s:
        _base(shim, time_s, right - time_w, 50 + yo, pal.DIM, 11)
    text_max = right - x1 - (time_w + _GAP if time_s else 0)
    if play.text:
        size = fit_size(play.text, (17, 15, 13, 12), text_max)
        _base(shim, fit_text(play.text, text_max, size), x1, 50 + yo, pal.WHITE, size)


def _detail_long(shim, real, game: GameInfo, play: ScoringPlay, frame, yo, logos):
    painted = _logo_or_chip(
        real, play, logos, LOGO_LONG, 8, 8 + yo, (6, 8 + yo, 13, 56 + yo)
    )
    scores = _scores(game, play, frame)
    time_s = _time_label(play)
    right = real.width - 7
    time_x = right - text_width(10, time_s) if time_s else right + _GAP
    # The stacked score column ends >= 6 px left of the time (which shares
    # its bottom rows), measured, so two-digit scores never crowd it.
    col_w = max(
        text_width(18, abbrev) + _GAP + text_width(22, score)
        for abbrev, _, score, _ in scores
    )
    x_score = min(400, time_x - _GAP - col_w)
    for (abbrev, tcolor, score, scolor), (ab, sb) in zip(
        scores, ((26, 28), (54, 56)), strict=True
    ):
        adv = _base(shim, abbrev, x_score, ab + yo, tcolor, 18)
        _base(shim, score, x_score + adv + _GAP, sb + yo, scolor, 22)
    x0 = 8 + LOGO_LONG + _GAP if painted else 22
    col_max = x_score - _GAP - x0
    _kind_line(shim, play, x0, 30 + yo, col_max, (34, 30, 26, 22), 14)
    if play.text:
        size = fit_size(play.text, (20, 16, 14, 12), col_max)
        _base(shim, fit_text(play.text, col_max, size), x0, 54 + yo, pal.WHITE, size)
    if time_s:
        _base(shim, time_s, time_x, 60 + yo, pal.DIM, 10)


# -------------------------------------------------------------- bitmap


def _detail_small(canvas, game: GameInfo, play: ScoringPlay, frame: int, yo: int, font):
    real = unwrap_to_real(canvas)
    width = canvas.width
    half = canvas.height // 2
    base = compute_baseline_for_band(font, half, 1, valign="center")
    y0, y1 = base + yo, half + base + yo
    primary = pal.chip(play.team)[0]
    rect(real, 0, yo, 2, yo + half - 2, primary)

    def mw(text: str) -> int:
        return measure_width(font, text, canvas) if text else 0

    kind = play.kind if play.kind in _WORDS else "SCORE"
    x = draw_text(canvas, font, kind, 5, y0, primary)
    if play.extra:
        x = draw_text(canvas, font, play.extra, x + _GAP, y0, pal.AMBER)
    items: list[tuple[str, Color]] = []
    for abbrev, tcolor, score, scolor in _scores(game, play, frame):
        items += [(abbrev, tcolor), (score, scolor)]
    run = sum(mw(t) for t, _ in items) + _GAP * (len(items) - 1)
    if width - run >= x + _GAP:
        rx = width - run
        for text, color in items:
            draw_text(canvas, font, text, rx, y0, color)
            rx += mw(text) + _GAP

    time_s = _time_label(play)
    time_w = mw(time_s)
    if time_s:
        draw_text(canvas, font, time_s, width - time_w, y1, pal.DIM)
    max_w = width - 5 - (time_w + _GAP if time_s else 0)
    line = play.text
    if line and mw(line) > max_w:
        # Ellipsize at the floor (the bitmap font carries U+2026).
        while len(line) > 1 and mw(line.rstrip() + "…") > max_w:
            line = line[:-1]
        line = line.rstrip() + "…"
    if line:
        draw_text(canvas, font, line, 5, y1, pal.WHITE)


def render_detail(
    canvas,
    game: GameInfo,
    play: ScoringPlay,
    frame: int,
    *,
    y_offset: int = 0,
    font: Font | None = None,
    logos: bool = True,
) -> None:
    """The post-flash detail card for the sign `canvas` belongs to.
    `logos=False` paints the scoring team's chip instead of its logo."""
    scale = safe_scale(canvas)
    if scale <= 1:
        _detail_small(
            canvas,
            game,
            play,
            frame,
            y_offset,
            font if font is not None else FONT_SMALL,
        )
        return
    shim, real = phys_wrap(canvas)
    yo = y_offset * scale
    if real.width > 300:
        _detail_long(shim, real, game, play, frame, yo, logos)
    else:
        _detail_big(shim, real, game, play, frame, yo, logos)
