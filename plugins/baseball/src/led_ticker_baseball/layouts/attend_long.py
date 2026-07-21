"""Held attendance hero card, 512px — port of `attendLong` (dc.html
~617-634). Two variants dispatched by duck-type (team-vs-league), same
shape as the sibling `layouts/attend_big.py` (see that module's docstring
for the full dispatch/import-cycle rationale — this module deliberately
does NOT import `AttendanceGame`/`CrowdRecord` for the same reason). Every
hires y-target goes through `_t` (cap-top), same shape as the other
`layouts/*_long.py` modules.

Uppercasing: `venue`/`home_abbr`/`label` are upper()'d at render time here
(never persisted upstream — same rationale as the sibling `_big`/`_long`
layouts).

Empty-context contract: every optional field (`paid`/`avg`/`capacity`) is
guarded so a fully-empty record renders without raising — no bar when
`capacity == 0`, no `% FULL`/`VS AVG` columns when `paid is None`, no tick
when `avg is None` (or `capacity` is 0, which would otherwise divide by
zero), no `CAP` readout when `capacity == 0`.

Fixed columns (task-5 brief): unlike the big card, the "% FULL"/"VS AVG"
columns here sit at FIXED x-origins (`cx = 228 + i*96`) rather than flowing
off the paid number's measured width — the extra width of the 512px card
means even the widest realistic crowd number never reaches x=228, so there
is no flow-collision risk to guard against (contrast with attend_big's
`_VX_MAX` belt).

Venue slot (task-5 uplift — promoted + "PAID ATTENDANCE" label removed):
the venue name now IS the row-40 band's left element (no dc.html
coordinate beyond "belted venue name", same gap as attend_big's venue
placement). The redundant "PAID ATTENDANCE" caption is gone — the big
amber paid number plus the capacity bar already say "this is attendance";
the venue identifies the park and reads better big. Bar sits at y=52,h=10
-> real rows 52-61; the promoted venue (px14 at y=40, empirically rows
~39-49 — see `test_long_team_venue_bigger_and_no_clip`) clears the bar
with room to spare, same headroom margin the old px8 venue had.

Weather slot (task-5 uplift): the paid number ends ~x109 and the fixed
`% FULL`/`VS AVG` columns start at x228 — the ~100px gap between them
(x122-223, after the paid number's `y0-40` height) was dead space at
every crowd size. `"72° CLEAR"`-style weather (only when the record has a
temp or condition) fills it, `fit_text`-belted so it can never reach into
either neighbor regardless of condition-string length.
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

# Panel geometry (512 physical px) — right margin used for every
# right-anchored readout (CAP, chip+abbr block) and the venue belt's
# maxw. `506` (the brief's literal CAP right-anchor target) = 512 - 6.
_PANEL_W = 512
_RIGHT_MARGIN = 6
_X0 = 6

# Team-mode fixed columns (task-5 brief): `cx = 228 + i*96`.
_COL_X = (228, 324)

# Team-card row y's (dc.html handoff, cap-top space).
_Y_PAID = 3
_PAID_SIZE = 30
_Y_COL_LABEL = 4
_COL_LABEL_SIZE = 10
_Y_COL_VAL = 18
_COL_VAL_SIZE = 20
_Y_ROW40 = 40
_CAP_SIZE = 9
_Y_BAR = 52
_BAR_W = 500
_BAR_H = 10

# Weather slot (task-5 uplift): fills the dead gap between the paid number
# (ends ~x109) and the fixed columns (start x228). `_WEATHER_X = 122`
# leaves a 13px margin off the paid number; `_WEATHER_MAXW = 100` is
# `_COL_X[0] - _WEATHER_GAP - _WEATHER_X` (228 - 6 - 122) so a long
# condition string belts before ever reaching the column start rather than
# relying on string length staying short. `_WEATHER_Y = 10` sits the line
# in the paid number's own y0-40 vertical band (empirically rows 9-18 at
# this size — see `test_long_team_weather_in_gap_no_overlap`), reading as
# the same "top line" as the paid number and column labels.
_WEATHER_X = 122
_WEATHER_GAP = 6
_WEATHER_MAXW = _COL_X[0] - _WEATHER_GAP - _WEATHER_X
_WEATHER_Y = 10
_WEATHER_SIZE = 13

# Venue slot (task-5 uplift — promoted, replaces the removed "PAID
# ATTENDANCE" label): takes the row-40 band's left side, belted so it
# can't run into the right-anchored "NN,NNN CAP" readout. `_VENUE_SIZE`
# raised from the old 8px label-adjacent size to 14px now that it's the
# band's headline element (empirically rows ~39-49 at y=40 — see
# `test_long_team_venue_bigger_and_no_clip` — well clear of the y=52 bar).
_VENUE_Y = 40
_VENUE_SIZE = 14
_VENUE_GAP = 10

# League-card rows (no dc.html coordinate beyond label/value/bar — same gap
# as attend_big's league layout). The label sits ABOVE the value in its own
# row-disjoint stack, mirroring attend_big's league spacing (label y=1/px9,
# value y=14/px22) — NOT the team card's y=3/px30 paid slot, whose px30 value
# cap-top (`cap_top(3, 30) = -5`, glyph span ~-5..24) paints THROUGH the y=1
# label (span ~-2..6) at overlapping x. With label px9 y=1 (`cap_top = -2`,
# span ~-2..6) and value px22 y=14 (`cap_top = 8`, span ~8..29) the two are
# row-disjoint (gap at row 7) and the value clears BOTH the label above and
# the venue/bar below (venue at row-40 band, `cap_top(40, 8) = 38`, spans
# ~38..45; bar at rows 52-61). px22 (not px30) is the size that fits this
# window — same as attend_big's league value. venue+chip share the row-40
# band, mirroring the team card's row-40/42 band and attend_big's league
# layout. Tripwire: test_league_label_and_value_are_row_disjoint.
_Y_LEAGUE_LABEL = 1
_LEAGUE_LABEL_SIZE = 9
_Y_LEAGUE_VALUE = 14
_LEAGUE_VALUE_SIZE = 22
_Y_LEAGUE_ROW = _Y_ROW40
_LEAGUE_CHIP_H = 8
_Y_LEAGUE_BAR = _Y_BAR

# MLB weather conditions are a small stable set; the two multi-word ones
# overflow the compact weather slot, so abbreviate them (all others fit and
# pass through unchanged). fit_text remains the final belt for anything
# unexpected a future feed adds.
_CONDITION_ABBR = {
    "PARTLY CLOUDY": "P CLOUDY",
    "ROOF CLOSED": "ROOF",
}


def _abbrev_condition(condition: str) -> str:
    c = (condition or "").upper()
    return _CONDITION_ABBR.get(c, c)


def _t(shim, text, x, y_target, color, size, *, bold=True):
    return hires(shim, text, x, cap_top(y_target, size), color, size, bold=bold)


def render_attend_long(
    canvas,
    record,
    progress: float,
    *,
    label: str = "",
    y_offset: int = 0,
    story_index: int = 0,
    story_total: int = 1,
) -> None:
    """Draw one attendance hero card at the longboi (512px) geometry.
    `progress` drives the capacity/fill bar's animated fill (`frac *
    progress`, grows toward the resting frac as progress -> 1.0), same
    convention as `layouts/attend_big.py`. `label` is the league-superlative
    header text (e.g. "BIGGEST CROWD") — team mode ignores it."""
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
    temp, condition = record.temp, record.condition

    paid_text = f"{paid:,}" if paid is not None else "—"
    _t(shim, paid_text, _X0, _Y_PAID + yo, pal.AMBER, _PAID_SIZE)

    if temp or condition:
        weather_text = f"{temp} {_abbrev_condition(condition)}".strip()
        weather_belted = fit_text(weather_text, _WEATHER_MAXW, _WEATHER_SIZE)
        _t(shim, weather_belted, _WEATHER_X, _WEATHER_Y + yo, pal.CYAN, _WEATHER_SIZE)

    if paid is not None:
        pct = paid / capacity * 100 if capacity else 0.0
        cx0, cx1 = _COL_X
        _t(shim, "% FULL", cx0, _Y_COL_LABEL + yo, pal.LABEL, _COL_LABEL_SIZE)
        _t(shim, f"{pct:.1f}%", cx0, _Y_COL_VAL + yo, pal.WIN, _COL_VAL_SIZE)

        if avg is not None:
            vs = paid - avg
            vs_text = ("+" if vs >= 0 else "") + f"{vs:,}"
            vs_color = pal.WIN if vs >= 0 else pal.LOSS
            _t(shim, "VS AVG", cx1, _Y_COL_LABEL + yo, pal.LABEL, _COL_LABEL_SIZE)
            _t(shim, vs_text, cx1, _Y_COL_VAL + yo, vs_color, _COL_VAL_SIZE)

    cap_x = None
    if capacity:
        cap_text = f"{capacity:,} CAP"
        capw = text_width(_CAP_SIZE, cap_text)
        cap_x = _PANEL_W - _RIGHT_MARGIN - capw
        _t(shim, cap_text, cap_x, _Y_ROW40 + yo, pal.LABEL, _CAP_SIZE)

    venue_right = (cap_x if cap_x is not None else _PANEL_W - _RIGHT_MARGIN) - (
        _VENUE_GAP
    )
    venue_maxw = venue_right - _X0
    venue_belted = fit_text((venue or "").upper(), max(venue_maxw, 0), _VENUE_SIZE)
    _t(shim, venue_belted, _X0, _VENUE_Y + yo, pal.LABEL, _VENUE_SIZE)

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

    _t(
        shim,
        (label or "").upper(),
        _X0,
        _Y_LEAGUE_LABEL + yo,
        pal.LABEL,
        _LEAGUE_LABEL_SIZE,
    )
    _t(shim, value_text, _X0, _Y_LEAGUE_VALUE + yo, value_color, _LEAGUE_VALUE_SIZE)

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
