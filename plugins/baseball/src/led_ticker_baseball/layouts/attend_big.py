"""Held attendance hero card, 256px — port of `attendBig` (dc.html
~601-616). Two variants dispatched by duck-type (team-vs-league) rather than
an isinstance check on the attendance dataclasses — see the module's
dispatch note below for why. Every hires y-target goes through `_t`
(cap-top), same shape as the other `layouts/*_big.py` modules.

Dispatch: `is_team = hasattr(record, "paid")` — only `AttendanceGame` (team
mode) has a `.paid` field; the league mode `CrowdRecord` does not. This
module deliberately does NOT import either dataclass from
`led_ticker_baseball.attendance` — that module will eventually build this
layout's caller (the attendance card), which would create an
attendance -> card -> layouts -> attendance import cycle (the same shape
`layouts/promo_card.py` and `layouts/statcast_big.py` avoid via a
`TYPE_CHECKING`-only forward ref; here we go one step further and don't
even need the forward ref since nothing in this module is typed against the
dataclass).

Uppercasing: `venue`/`home_abbr`/`label` are upper()'d at render time here
(never persisted upstream — same rationale as the sibling `_big` layouts).

Empty-context contract: every optional field (`paid`/`avg`/`capacity`) is
guarded so a fully-empty record renders without raising — no bar when
`capacity == 0`, no `% FULL`/`VS AVG` columns when `paid is None`, no tick
when `avg is None` (or `capacity` is 0, which would otherwise divide by
zero), no `CAP` readout when `capacity == 0`.
"""

from led_ticker.plugin import safe_scale

from led_ticker_baseball import _palette as pal
from led_ticker_baseball._paint import (
    cap_top,
    fit_text,
    hires,
    paging_dots,
    phys_wrap,
    text_width,
)
from led_ticker_baseball._primitives import chip, draw_bar
from led_ticker_baseball.teams import _team_color

# Panel geometry (256 physical px) — right margin used for every
# right-anchored readout (CAP, chip+abbr block) and the venue belt's <maxw>
# ("panel width minus x-origin minus a 6px margin", task-4 brief).
_PANEL_W = 256
_RIGHT_MARGIN = 4  # symmetric with the 4px left x-origin used throughout
_X0 = 4

# Team-mode column flow constants (dc.html handoff, task-4 brief): the
# "% FULL"/"VS AVG" columns sit at fixed offsets from the paid number's
# right edge. `_VX_MAX` is the belt: the widest realistic crowd ("56,000")
# already fits inside this at the spec offset (verified: nw=87 px24 ->
# ux=101 -> vx=171 -> value width ~53 -> extent 224 < 248), but a future
# wider fixture (more digits, a bigger font) is guarded rather than assumed.
_VX_MAX = _PANEL_W - _RIGHT_MARGIN - 4

# Team-card row y's (dc.html handoff, cap-top space).
_Y_LABEL = 1
_Y_PAID = 12
_Y_COLVAL = 22
_Y_ROW40 = 40
_Y_BAR = 49
_BAR_H = 8
_BAR_W = 248

# The team-card venue slot has no dc.html coordinate (task-4 brief note).
# Placed BELOW the capacity bar (y49-57) in the bigsign card's free space —
# the real canvas here is the full 64-physical-row panel (phys_wrap unwraps
# to scale=1), so rows 58-63 are clear of every other fixed element (the
# columns end well above y40, the bar ends at y57). Chosen over the brief's
# suggested "between columns and bar" slot because that band is already
# fully occupied end-to-end by the "PAID ATTENDANCE" / "NN,NNN CAP" row.
_Y_TEAM_VENUE = 60
_TEAM_VENUE_SIZE = 8

# League-card rows (no dc.html coordinate beyond label/value/bar — task-4
# brief leaves the venue/chip row's exact y to the implementer). Venue +
# team chip/abbr share one row (mirrors the team card's label/CAP row
# shape) so both have a concrete, non-overlapping position.
_Y_LEAGUE_LABEL = 1
_Y_LEAGUE_VALUE = 14
_Y_LEAGUE_ROW = 40
_Y_LEAGUE_BAR = 52
_LEAGUE_CHIP_H = 8


def _t(shim, text, x, y_target, color, size, *, bold=True):
    return hires(shim, text, x, cap_top(y_target, size), color, size, bold=bold)


def render_attend_big(
    canvas,
    record,
    progress: float,
    *,
    label: str = "",
    y_offset: int = 0,
    story_index: int = 0,
    story_total: int = 1,
) -> None:
    """Draw one attendance hero card. `progress` drives the capacity/fill
    bar's animated fill (`frac * progress`, grows toward the resting frac as
    progress -> 1.0), same convention as the trajectory arc in
    `layouts/statcast_big.py`. `label` is the league-superlative header text
    (e.g. "BIGGEST CROWD") — team mode ignores it (team cards have their own
    static "ATTENDANCE" header)."""
    shim, real = phys_wrap(canvas)
    yo = y_offset * safe_scale(canvas)
    is_team = hasattr(record, "paid")
    if is_team:
        _render_team(shim, real, record, progress, yo)
    else:
        _render_league(shim, real, record, progress, label, yo)
    if story_total > 1:
        paging_dots(
            real,
            story_total,
            story_index,
            _PANEL_W - story_total * 8 - _RIGHT_MARGIN,
            2 + yo,
        )


def _render_team(shim, real, record, progress, yo):
    paid, capacity, avg = record.paid, record.capacity, record.avg
    venue, home_abbr = record.venue, record.home_abbr

    _t(shim, "ATTENDANCE", _X0, _Y_LABEL + yo, pal.LABEL, 8)

    paid_text = f"{paid:,}" if paid is not None else "—"
    nw = _t(shim, paid_text, _X0, _Y_PAID + yo, pal.AMBER, 24)

    if paid is not None:
        ux = _X0 + nw + 10
        pct = paid / capacity * 100 if capacity else 0.0
        _t(shim, "% FULL", ux, _Y_PAID + yo, pal.LABEL, 8)
        _t(shim, f"{pct:.1f}%", ux, _Y_COLVAL + yo, pal.WIN, 13)

        if avg is not None:
            vs = paid - avg
            vs_text = ("+" if vs >= 0 else "") + f"{vs:,}"
            vs_color = pal.WIN if vs >= 0 else pal.LOSS
            # Belt (task-4 brief): the widest realistic crowd already fits
            # at the spec offset (`ux + 70`), but a wider future fixture is
            # guarded — right-anchor the whole column against `_VX_MAX`
            # rather than assume the flowed position always fits.
            col_w = max(text_width(8, "VS AVG"), text_width(13, vs_text))
            vx = ux + 70
            if vx + col_w > _VX_MAX:
                vx = _VX_MAX - col_w
            _t(shim, "VS AVG", vx, _Y_PAID + yo, pal.LABEL, 8)
            _t(shim, vs_text, vx, _Y_COLVAL + yo, vs_color, 13)

    _t(shim, "PAID ATTENDANCE", _X0, _Y_ROW40 + yo, pal.LABEL, 8)

    if capacity:
        cap_text = f"{capacity:,} CAP"
        capw = text_width(8, cap_text)
        cap_x = _PANEL_W - _RIGHT_MARGIN - capw
        _t(shim, cap_text, cap_x, _Y_ROW40 + yo, pal.LABEL, 8)

    venue_maxw = _PANEL_W - _X0 - 6
    venue_belted = fit_text((venue or "").upper(), venue_maxw, _TEAM_VENUE_SIZE)
    _t(shim, venue_belted, _X0, _Y_TEAM_VENUE + yo, pal.LABEL, _TEAM_VENUE_SIZE)

    if capacity:
        frac = (paid / capacity) if paid is not None else 0.0
        tick_frac = (avg / capacity) if (avg is not None) else None
        draw_bar(
            real,
            _X0,
            _Y_BAR + yo,
            _BAR_W,
            _BAR_H,
            frac * progress,
            _team_color(home_abbr),
            tick_frac=tick_frac,
        )


def _render_league(shim, real, record, progress, label, yo):
    value_text = f"{record.value}%" if record.is_pct else f"{record.value:,}"
    value_color = pal.WIN if record.is_pct else pal.AMBER

    _t(shim, (label or "").upper(), _X0, _Y_LEAGUE_LABEL + yo, pal.LABEL, 9)
    _t(shim, value_text, _X0, _Y_LEAGUE_VALUE + yo, value_color, 22)

    abbr = (record.home_abbr or "").upper()
    abbr_w = text_width(8, abbr) if abbr else 0
    block_w = _LEAGUE_CHIP_H + 3 + abbr_w
    chip_x = _PANEL_W - _RIGHT_MARGIN - block_w
    chip(real, chip_x, _Y_LEAGUE_ROW + yo, _LEAGUE_CHIP_H, record.home_abbr or "")
    _t(shim, abbr, chip_x + _LEAGUE_CHIP_H + 3, _Y_LEAGUE_ROW + yo, pal.IDENT, 8)

    venue_maxw = chip_x - _X0 - 6
    venue_belted = fit_text((record.venue or "").upper(), max(venue_maxw, 0), 8)
    _t(shim, venue_belted, _X0, _Y_LEAGUE_ROW + yo, pal.LABEL, 8)

    draw_bar(
        real,
        _X0,
        _Y_LEAGUE_BAR + yo,
        _BAR_W,
        _BAR_H,
        record.fill_frac * progress,
        _team_color(record.home_abbr or ""),
    )
