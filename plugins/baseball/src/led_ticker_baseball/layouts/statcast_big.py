"""Held statcast hero card, 256px — port of `statcastBig` (dc.html
~557-573). No trajectory panel (matches the handoff — the arc is a
longboi-only feature); launch angle + distance render as the bottom text
row. Every hires y-target goes through `_t` (cap-top), same shape as the
other layouts.

Uppercasing: the result / player name / pitch name are upper()'d at RENDER
time here (never persisted upstream on `StatRecord` — see
`layouts/promo_card.py`'s module docstring for the same rationale, ported
verbatim to this widget's own fields).
"""

from led_ticker.plugin import safe_scale

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._paint import (
    cap_top,
    hires,
    paging_dots,
    phys_wrap,
    text_width,
)
from led_ticker_baseball.trajectory import res_color


def _t(shim, text, x, y_target, color, size, *, bold=True):
    return hires(shim, text, x, cap_top(y_target, size), color, size, bold=bold)


def _num(v, suffix=""):
    """Guard a possibly-missing numeric field to an em-dash placeholder
    (never raises on `None` — the empty-context contract, task-5 brief)."""
    return f"{v:g}{suffix}" if v is not None else "—"


def render_statcast_big(
    canvas,
    record,
    player_name: str,
    *,
    y_offset: int = 0,
    story_index: int = 0,
    story_total: int = 1,
) -> None:
    """Draw one statcast hero card (held layout, no scroll/animation clock
    of its own — the caller's rotation owns timing, same convention as the
    sibling `layouts/promo_card.render_promo_card`)."""
    shim, real = phys_wrap(canvas)
    yo = y_offset * safe_scale(canvas)

    _t(shim, "STATCAST", 4, 1 + yo, pal.LABEL, 8)
    res = (record.result or "").upper()
    rw = text_width(10, res)
    _t(shim, res, 206 - rw, 1 + yo, res_color(res), 10)

    _t(shim, (player_name or "").upper(), 4, 11 + yo, pal.IDENT, 15)

    ev = _num(record.exit_velo)
    nw = _t(shim, ev, 4, 26 + yo, pal.AMBER, 26)
    ux = 4 + nw + 7
    _t(shim, "MPH", ux, 28 + yo, pal.AMBER, 11)
    _t(shim, "EXIT VELO", ux, 44 + yo, pal.LABEL, 8)

    la = _num(record.launch_angle, "°")
    dist = f"{int(record.distance)} FT" if record.distance else "—"
    pitch = (
        f"{record.pitch_velo:g} {record.pitch_name}".strip()
        if record.pitch_velo is not None
        else (record.pitch_name or "")
    )
    mx, y = 4, 53
    mx += _t(shim, la, mx, y + yo, pal.CYAN, 11, bold=False) + 10
    mx += _t(shim, dist, mx, y + yo, pal.MAGENTA, 11, bold=False) + 10
    _t(shim, pitch.upper(), mx, y + yo, pal.WIN, 11, bold=False)

    if story_total > 1:
        paging_dots(
            real,
            story_total,
            story_index,
            256 - story_total * 8 - 4,
            real.height - 8 + yo,
        )
