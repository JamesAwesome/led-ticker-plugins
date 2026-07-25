"""Procedural pixel-art primitives, ported from design/…dc.html.

Coordinate-for-coordinate ports; geometry changes require a design review.
All painting goes through `_paint.px` (bounds-checked) with `_palette.dim`
for the prototype's brightness args.
"""

from led_ticker.plugin import Color, make_color

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._paint import hires, js_round, px
from led_ticker_baseball._palette import (
    CHALLENGE,
    CHALLENGE_USED,
    LABEL,
    LOSS,
    ORANGE,
    WIN,
    dim,
)
from led_ticker_baseball.teams import MLB_TEAM_CHIPS

_GREY_C1 = (150, 160, 175)  # prototype unknown-team chip fallback
_GREY_C2 = (90, 100, 115)


def chip(real, x: int, y: int, h: int, team: str) -> None:
    c1_t, c2_t = MLB_TEAM_CHIPS.get(team, (_GREY_C1, _GREY_C2))
    c1, c2 = make_color(*c1_t), make_color(*c2_t)
    rad = 2 if h >= 10 else 1
    for r in range(h):
        for cx in range(h):
            corner = (
                (cx < rad and r < rad)
                or (cx >= h - rad and r < rad)
                or (cx < rad and r >= h - rad)
                or (cx >= h - rad and r >= h - rad)
            )
            if corner:
                continue
            px(real, x + cx, y + r, c2 if (cx - r) > 0 else c1)


def diamond(
    real, cx: int, cy: int, r: int, filled: bool, color: Color, brightness: float = 1.0
) -> None:
    c = dim(color, brightness)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            m = abs(dx) + abs(dy)
            if (m <= r) if filled else (r - 1 <= m <= r):
                px(real, cx + dx, cy + dy, c)


def pip(
    real, cx: int, cy: int, r: int, filled: bool, color: Color, brightness: float = 1.0
) -> None:
    c = dim(color, brightness)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            d = round((dx * dx + dy * dy) ** 0.5)
            if (d <= r) if filled else (d == r):
                px(real, cx + dx, cy + dy, c)


def dash(real, x: int, y: int, w: int, color: Color, brightness: float = 1.0) -> None:
    c = dim(color, brightness)
    for i in range(w):
        px(real, x + i, y, c)
        px(real, x + i, y + 1, c)


def series_dashes(real, x: int, y: int, won: int, team_color: Color) -> None:
    """2 slots (best-of-3 regular-season series): won slots ORANGE full,
    unwon LABEL at 0.5. `team_color` accepted for API parity with the
    prototype call sites (it passes the team tint but paints ORANGE)."""
    for i in range(2):
        w = i < won
        dash(real, x, y + i * 5, 12, ORANGE if w else LABEL, 1.0 if w else 0.5)


def challenge_dashes(real, x: int, y: int, remaining: int) -> None:
    """2 slots (ABS automated ball-strike challenges): the first `remaining`
    slots CHALLENGE (orange, unused), the rest CHALLENGE_USED (grey). Live
    games only; the caller guards on a non-None count (None = ABS not
    equipped / hydration pending -> draw nothing). Mirrors `series_dashes`'
    2-slot geometry so a per-team challenge indicator beside the score reads
    the same as the series-win dashes beside the name."""
    n = min(max(remaining, 0), 2)
    for i in range(2):
        unused = i < n
        dash(real, x, y + i * 5, 12, CHALLENGE if unused else CHALLENGE_USED, 1.0)


def dotted_divider(real, x0: int, x1: int, y: int) -> None:
    c = dim(LABEL, 0.35)
    for x in range(x0, x1, 3):
        px(real, x, y, c)


def draw_record(
    shim, x: int, y: int, wins: int, losses: int, size: int, *, bold: bool = True
) -> int:
    """WIN wins, LABEL "-", LOSS losses (port of `drawRecord`, dc.html
    237-243). The one text-COMPOSITE primitive in this module — every other
    primitive here paints raw pixel geometry, but this one calls
    `_paint.hires` three times, so it needs the scale-1 `shim` (from
    `_paint.phys_wrap`) rather than the real canvas. `y` is forwarded to
    `hires` UNMODIFIED — same convention as every other primitive taking a
    caller-supplied coordinate; any dc.html visual-top -> ascent-box-top
    conversion is the CALLER'S job (see `_paint.cap_top` and
    `layouts/standings_board.py`'s `_t`), applied once before this call, not
    duplicated here.

    Returns the total physical-px advance (call sites do
    `x += draw_record(...)`)."""
    cx = x
    cx += hires(shim, str(wins), cx, y, WIN, size, bold=bold)
    cx += hires(shim, "-", cx, y, LABEL, size, bold=bold)
    cx += hires(shim, str(losses), cx, y, LOSS, size, bold=bold)
    return cx - x


def draw_bar(
    real,
    x: int,
    y: int,
    w: int,
    h: int,
    frac: float,
    fill,
    *,
    tick_frac: float | None = None,
) -> None:
    """Port of dc.html `drawBar` (~251): a dim full-width track, a bright
    `fill`-colored bar to `frac` with a subtle left-to-right brightness ramp,
    and an optional tick at `tick_frac`. The tick's x is clamped to stay
    within [x, x+w) (its y deliberately bleeds 1px above/below, matching the
    statcast wall-tick full-bleed). Never raises; `frac`/`tick_frac` clamp."""
    track = pal.dim(pal.LABEL, 0.32)
    for i in range(w):
        for yy in range(h):
            px(real, x + i, y + yy, track)
    fw = js_round(w * max(0.0, min(1.0, frac)))
    for i in range(fw):
        b = 0.85 + 0.15 * (i / max(1, fw))
        col = pal.dim(fill, b)
        for yy in range(h):
            px(real, x + i, y + yy, col)
    if tick_frac is not None:
        tx = min(x + js_round(w * max(0.0, min(1.0, tick_frac))), x + w - 1)
        for yy in range(-1, h + 1):
            px(real, tx, y + yy, pal.IDENT)
