"""Goal celebration: the frame timeline plus the flash and detail painters.

Timeline (engine tick = 50 ms): each goal gets `CELEBRATION_FRAMES` (4 s).
The first `FLASH_FRAMES` are three on/off flashes (2 frames on, 2 off) of
the full panel in the scoring team's color with `GOAL` knocked out; the
rest is the detail card (scorer, season count, assists, new score with the
scorer's number pulsing, period + time).

Layouts follow the `states.html` §1 mockup per sign (`goalSmall`,
`goalBig`, `goalLong`); the mockup's hi-res y is a BASELINE, converted here
via the font's ascent. Every text is measured and placed with >= 6 px
clearance; names ellipsize. Sparse goals (no scorer, no season total, no
assists, no time) render what they have and never raise.
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

from led_ticker_hockey import _palette as pal
from led_ticker_hockey._models import GameInfo, Goal
from led_ticker_hockey._paint import (
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


def phase_at(frame: int, n_goals: int) -> tuple[int, str, int] | None:
    """`(goal_index, phase, frame_in_goal)`; None once the run is over."""
    if frame < 0 or frame >= n_goals * CELEBRATION_FRAMES:
        return None
    idx, f = divmod(frame, CELEBRATION_FRAMES)
    if f < FLASH_FRAMES:
        return idx, ("flash_on" if (f // 2) % 2 == 0 else "flash_off"), f
    return idx, "detail", f


def pulse(frame: int) -> float:
    """The mockup's score pulse, 0.55-1.0."""
    return 0.55 + 0.45 * (0.5 + 0.5 * math.cos(frame * 50 / 180))


def _time_label(goal: Goal) -> str:
    return f"{goal.period_label} {goal.time_in_period}".strip()


def _scores(game: GameInfo, goal: Goal, frame: int):
    """[(abbrev, team color, score text, score color)] away then home; the
    scoring team's score pulses. Scores are the goal's own snapshot."""
    hot = pal.dim(pal.WHITE, pulse(frame))
    return [
        (
            abbrev,
            pal.chip(abbrev)[0],
            str(score),
            hot if abbrev == goal.team else pal.WHITE,
        )
        for abbrev, score in (
            (game.away, goal.away_score),
            (game.home, goal.home_score),
        )
    ]


# ------------------------------------------------------------- hi-res


def _base(shim, text: str, x: int, base: int, color: Color, size: int) -> int:
    """Paint with the mockup's baseline convention; return the advance."""
    if not text:
        return 0
    return hires(shim, text, x, base - resolve_font(_FONT, size).ascent, color, size)


def _centered_cap_base(size: int, height: int) -> int:
    return js_round((height + size * 0.72) / 2)


def render_flash(canvas, color: Color, on: bool, *, y_offset: int = 0) -> None:
    """Full-panel team color with GOAL knocked out (unlit); dark when off."""
    real = unwrap_to_real(canvas)
    if not on:
        return
    scale = safe_scale(canvas)
    yo = y_offset * scale
    rect(real, 0, yo, real.width - 1, yo + real.height - 1, color)
    if scale <= 1:
        font = FONT_SMALL
        w = measure_width(font, "GOAL", canvas)
        base = compute_baseline_for_band(font, canvas.height, 1, valign="center")
        draw_text(canvas, font, "GOAL", (canvas.width - w) // 2, base + yo, _BLACK)
        return
    shim, _ = phys_wrap(canvas)
    size = 44 if real.width > 300 else 40
    x = js_round((real.width - text_width(size, "GOAL")) / 2)
    _base(shim, "GOAL", x, _centered_cap_base(size, real.height) + yo, _BLACK, size)


def _right_run(shim, items, right: int, base_of) -> None:
    """Paint `(text, color, size)` items right-to-left ending at `right`
    with `_GAP` between."""
    x = right + _GAP
    for text, color, size in reversed([i for i in items if i[0]]):
        x -= text_width(size, text) + _GAP
        _base(shim, text, x, base_of(size), color, size)


def _scorer_line(
    shim, goal: Goal, x: int, base: int, max_w: int, size: int, total_size: int
) -> None:
    total = f"({goal.season_total})" if goal.season_total is not None else ""
    total_w = text_width(total_size, total) + _GAP if total else 0
    name = fit_text(goal.scorer, max(1, max_w - total_w), size) if goal.scorer else ""
    adv = _base(shim, name, x, base, pal.WHITE, size)
    if total:
        tx = x + adv + _GAP if name else x
        _base(shim, total, tx, base, pal.GRAY, total_size)


def _assists_line(shim, goal: Goal, x: int, base: int, max_w: int, size: int):
    if not goal.assists:
        return
    text = fit_text(" · ".join(goal.assists), max_w, size)
    _base(shim, text, x, base, pal.CYAN, size)


def _detail_big(shim, real, game: GameInfo, goal: Goal, frame: int, yo: int):
    primary = pal.chip(goal.team)[0]
    rect(real, 3, 5 + yo, 8, 26 + yo, primary)
    _base(shim, "GOAL", 14, 26 + yo, primary, 26)
    items = []
    for abbrev, tcolor, score, scolor in _scores(game, goal, frame):
        items += [(abbrev, tcolor, 14), (score, scolor, 16)]
    # Four short tokens (~90 px) end at the right edge; GOAL ends ~x85.
    _right_run(shim, items, real.width - 5, lambda s: (20 if s == 14 else 21) + yo)
    for x in range(0, real.width, 3):
        if 0 <= 32 + yo < real.height:
            real.SetPixel(x, 32 + yo, pal.DIM.red, pal.DIM.green, pal.DIM.blue)
    time_s = _time_label(goal)
    time_w = text_width(11, time_s) if time_s else 0
    right = real.width - 5
    if time_s:
        _base(shim, time_s, right - time_w, 50 + yo, pal.DIM, 11)
    name_max = right - 14 - (time_w + _GAP if time_s else 0)
    _scorer_line(shim, goal, 14, 50 + yo, name_max, 17, 12)
    _assists_line(shim, goal, 14, 61 + yo, right - 14, 9)


def _detail_long(shim, real, game: GameInfo, goal: Goal, frame: int, yo: int):
    primary = pal.chip(goal.team)[0]
    rect(real, 6, 8 + yo, 13, 56 + yo, primary)
    _base(shim, "GOAL", 22, 48 + yo, primary, 40)
    scores = _scores(game, goal, frame)
    time_s = _time_label(goal)
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
    x0 = 160
    col_max = x_score - _GAP - x0
    _scorer_line(shim, goal, x0, 32 + yo, col_max, 24, 14)
    _assists_line(shim, goal, x0, 52 + yo, col_max, 12)
    if time_s:
        _base(shim, time_s, time_x, 60 + yo, pal.DIM, 10)


# -------------------------------------------------------------- bitmap


def _detail_small(canvas, game: GameInfo, goal: Goal, frame: int, yo: int, font):
    real = unwrap_to_real(canvas)
    width = canvas.width
    half = canvas.height // 2
    base = compute_baseline_for_band(font, half, 1, valign="center")
    y0, y1 = base + yo, half + base + yo
    primary = pal.chip(goal.team)[0]
    rect(real, 0, yo, 2, yo + half - 2, primary)
    goal_end = draw_text(canvas, font, "GOAL", 5, y0, primary)

    def mw(text: str) -> int:
        return measure_width(font, text, canvas) if text else 0

    items: list[tuple[str, Color]] = []
    for abbrev, tcolor, score, scolor in _scores(game, goal, frame):
        items += [(abbrev, tcolor), (score, scolor)]
    run = sum(mw(t) for t, _ in items) + _GAP * (len(items) - 1)
    if width - run >= goal_end + _GAP:
        x = width - run
        for text, color in items:
            draw_text(canvas, font, text, x, y0, color)
            x += mw(text) + _GAP

    time_s = _time_label(goal)
    time_w = mw(time_s)
    if time_s:
        draw_text(canvas, font, time_s, width - time_w, y1, pal.DIM)
    max_w = width - 5 - (time_w + _GAP if time_s else 0)
    total = f" ({goal.season_total})" if goal.season_total is not None else ""
    line = f"{goal.scorer}{total}".strip()
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
    goal: Goal,
    frame: int,
    *,
    y_offset: int = 0,
    font: Font | None = None,
) -> None:
    """The post-flash detail card for the sign `canvas` belongs to."""
    scale = safe_scale(canvas)
    if scale <= 1:
        _detail_small(
            canvas,
            game,
            goal,
            frame,
            y_offset,
            font if font is not None else FONT_SMALL,
        )
        return
    shim, real = phys_wrap(canvas)
    yo = y_offset * scale
    if real.width > 300:
        _detail_long(shim, real, game, goal, frame, yo)
    else:
        _detail_big(shim, real, game, goal, frame, yo)
