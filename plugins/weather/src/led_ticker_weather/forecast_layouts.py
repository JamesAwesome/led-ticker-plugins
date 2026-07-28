"""The three per-sign forecast renderers, ported from the handoff draw
functions (design/Weather Forecast.dc.html: weatherSmall / weatherBig /
weatherLong). Coordinates and sizes are handoff-normative; icons diverge
to packaged emoji (spec divergence 1: boxes snap to sprite sizes).
"""

import attrs
from led_ticker.plugin import FONT_SMALL, draw_emoji_at, draw_text, safe_scale

from led_ticker_weather.forecast_data import (
    KIND_SLUGS,
    DayForecast,
    ForecastData,
    display_temp,
)
from led_ticker_weather.paint import (
    blit_hires_downscaled,
    cap_top,
    dim,
    fit_text,
    hires,
    js_round,
    phys_wrap,
    spleen_center,
    spleen_segs,
    text_width,
    vdivider,
)
from led_ticker_weather.palette import AMBER, CYAN, HI, IDENT, LABEL, LO, RGB

# --- smallsign (160x16, BDF, logical coords) — handoff weatherSmall ---

_SMALL_CW = 53  # column width
_SMALL_X0 = 2
_SMALL_TEXT_DX = 13  # text block starts right of the icon slot: the
# handoff's 17 assumed its own 14px icon slot, but ours is the 8x8 sprite
# drawn at x+3 (ends x+10) — 13 keeps a 2px icon gap and gives the 7-char
# worst-case temp pair ("-99/-99" at FONT_SMALL's advance) clearance before
# the separator dots at x + _SMALL_CW - 3 (F1: the old 17 let a 7-char pair
# paint into the separator column).
# FONT_SMALL is 5x8 (nearest bundled BDF to the handoff's px7 Silkscreen —
# documented divergence 2): two 8-row bands stack exactly in 16 rows.
_SMALL_LABEL_BASELINE = 7
_SMALL_TEMP_BASELINE = 15
_SMALL_ICON_Y = 4  # centers the 8x8 sprite vertically


def render_strip_small(
    canvas, data: ForecastData, units: str, *, y_offset: int = 0
) -> None:
    """Today + next two days: icon | day label / hi-lo, dotted separators."""
    cur = data.current
    cells: list[tuple[str, DayForecast | None]] = [("TDY", None)]
    for d in data.days[:2]:
        cells.append((d.label, d))
    for i, (label, day) in enumerate(cells):
        x = _SMALL_X0 + i * _SMALL_CW
        kind = cur.kind if day is None else day.kind
        hi_f = cur.hi_f if day is None else day.hi_f
        lo_f = cur.lo_f if day is None else day.lo_f
        lowres, _ = KIND_SLUGS[kind]
        # max_emoji_height=8: the strip's column geometry assumes an
        # 8-logical-row icon slot, but core's hires gate is
        # `is_scaled(canvas)`, not `scale > 1` — a scale=1/2 ScaledCanvas
        # (e.g. an explicit `scale` override on a bigsign/longboi section)
        # still passes that gate, so without this cap a 32x32 hires sprite
        # would land in the slot instead of the curated 8x8 lowres one.
        draw_emoji_at(
            canvas, lowres, x + 3, _SMALL_ICON_Y + y_offset, max_emoji_height=8
        )
        tx = x + _SMALL_TEXT_DX
        draw_text(
            canvas,
            FONT_SMALL,
            label,
            tx,
            _SMALL_LABEL_BASELINE + y_offset,
            dim(AMBER),
        )
        temps = f"{display_temp(hi_f, units)}/{display_temp(lo_f, units)}"
        draw_text(
            canvas,
            FONT_SMALL,
            temps,
            tx,
            _SMALL_TEMP_BASELINE + y_offset,
            dim(IDENT),
        )
        if i < len(cells) - 1:
            sep_x = x + _SMALL_CW - 3
            for yy in range(2, 14, 2):
                canvas.SetPixel(
                    sep_x,
                    yy + y_offset,
                    int(LABEL[0] * 0.3),
                    int(LABEL[1] * 0.3),
                    int(LABEL[2] * 0.3),
                )


# --- hi-res strip cell (bigsign / longboi) — handoff stripCell ---


@attrs.frozen
class StripGeo:
    """One hires strip's geometry. All text is spleen (12px cell, no cap_top);
    icons are hires sprites downscaled to icon_px."""

    day_y: int
    icon_px: int  # downscaled hires icon size (16 big / 24 long)
    icon_y: int
    temp_y: int
    stack: bool  # True: hi over lo; False: horizontal hi/lo segs
    line_h: int = 12  # spleen cell advance for stacked temps
    pop_y: int | None = None  # precip % row (longboi only)


# bigsign: day(2-13) icon(15-30,16px) hi(33-44) lo(45-56) — fits 64 w/ headroom.
_BIG_GEO = StripGeo(day_y=2, icon_px=16, icon_y=15, temp_y=33, stack=True)
# longboi: day(1-12) icon(13-36,24px) temps(38-49) precip(51-62) — fits 64.
_LONG_GEO = StripGeo(day_y=1, icon_px=24, icon_y=13, temp_y=38, stack=False, pop_y=51)


def _center_segs(shim, segs, x, w, y_target, size, oy):
    """Center multi-color segments as one run (handoff centerSegs)."""
    total = sum(text_width(size, t) for t, _ in segs)
    cx = js_round(x + (w - total) / 2)
    for t, rgb in segs:
        cx += hires(shim, t, cx, cap_top(y_target, size) + oy, rgb, size)


def _temp_segs(hi_f, lo_f, units, *, degree) -> list[tuple[str, RGB]]:
    suffix = "°" if degree else ""
    return [
        (f"{display_temp(hi_f, units)}{suffix}", HI),
        ("/", LABEL),
        (f"{display_temp(lo_f, units)}{suffix}", LO),
    ]


def _strip_cell(shim, real, x, w, day: DayForecast, geo: StripGeo, units, oy):
    cx = x + w / 2
    spleen_center(shim, day.label, cx, geo.day_y + oy, AMBER)
    _, hires_slug = KIND_SLUGS[day.kind]
    blit_hires_downscaled(
        real, hires_slug, js_round(cx - geo.icon_px / 2), geo.icon_y + oy, geo.icon_px
    )
    if geo.stack:
        hi_txt = str(display_temp(day.hi_f, units))
        spleen_center(shim, hi_txt, cx, geo.temp_y + oy, HI)
        lo_txt = str(display_temp(day.lo_f, units))
        spleen_center(shim, lo_txt, cx, geo.temp_y + geo.line_h + oy, LO)
    else:
        segs = _temp_segs(day.hi_f, day.lo_f, units, degree=False)
        spleen_segs(shim, segs, cx, geo.temp_y + oy)
    if geo.pop_y is not None:
        rgb = CYAN if day.pop >= 50 else LABEL
        spleen_center(shim, f"{day.pop}%", cx, geo.pop_y + oy, rgb)


# --- hero layouts (bigsign / longboi) — handoff weatherBig / weatherLong ---

# Hero icon: 32x32 hires/pack sprite via draw_emoji_at at LOGICAL coords,
# so the physical position quantizes to scale multiples — (4,13) lands at
# (4,12), (4,15) at (4,16). <=3px drift, accepted (spec divergence 1).


def _hero_icon(canvas, kind: str, log_x: int, log_y: int, y_offset: int) -> None:
    _, hires_slug = KIND_SLUGS[kind]
    draw_emoji_at(canvas, hires_slug, log_x, log_y + y_offset)


def _strip(shim, real, days, x0, x1, n_slots, geo, units, oy):
    """Lay out up to n_slots day columns; a short feed widens the columns
    (cw = span / actual_n, the handoff's own formula with the real count)."""
    n = min(n_slots, len(days))
    if n == 0:
        return
    cw = (x1 - x0) / n
    for i in range(n):
        _strip_cell(shim, real, x0 + i * cw, cw, days[i], geo, units, oy)


def render_hero_big(
    canvas, data: ForecastData, units: str, *, y_offset: int = 0
) -> None:
    """256x64: today hero left of a dotted divider, 4-day strip right."""
    shim, real = phys_wrap(canvas)
    oy = y_offset * safe_scale(canvas)
    cur = data.current
    # render_hero_long clamps its location the same way (fit_text) — the
    # handoff's unclamped draw here assumed its hardcoded "BOSTON"; a real
    # API-resolved wide city name bleeds through the divider gap into the
    # strip's label row without this. Divider sits at x112; 102px keeps
    # >=4px clearance from it.
    hires(shim, fit_text(data.location, 102, 9), 6, cap_top(2, 9) + oy, LABEL, 9)
    _hero_icon(canvas, cur.kind, 1, 3, y_offset)
    temp = f"{display_temp(cur.temp_f, units)}°"
    hires(shim, temp, 44, cap_top(13, 27) + oy, IDENT, 27)
    _center_segs(
        shim, _temp_segs(cur.hi_f, cur.lo_f, units, degree=True), 44, 60, 41, 11, oy
    )
    hires(
        shim,
        f"FEELS {display_temp(cur.feels_f, units)}°",
        44,
        cap_top(53, 8) + oy,
        CYAN,
        8,
        bold=False,
    )
    vdivider(real, 112, 6 + oy, 58 + oy)
    _strip(shim, real, data.days, 118, 252, 4, _BIG_GEO, units, oy)


def render_hero_long(
    canvas, data: ForecastData, units: str, *, y_offset: int = 0
) -> None:
    """512x64: expanded hero (ellipsized location, temp pushed right),
    dotted divider, 6-day strip with precip %."""
    shim, real = phys_wrap(canvas)
    oy = y_offset * safe_scale(canvas)
    cur = data.current
    hires(shim, fit_text(data.location, 148, 11), 6, cap_top(2, 11) + oy, LABEL, 11)
    _hero_icon(canvas, cur.kind, 1, 4, y_offset)
    temp = f"{display_temp(cur.temp_f, units)}°"
    hires(shim, temp, 70, cap_top(14, 28) + oy, IDENT, 28)
    _center_segs(
        shim, _temp_segs(cur.hi_f, cur.lo_f, units, degree=True), 70, 80, 43, 11, oy
    )
    hires(
        shim,
        f"FEELS {display_temp(cur.feels_f, units)}°",
        70,
        cap_top(56, 8) + oy,
        CYAN,
        8,
        bold=False,
    )
    vdivider(real, 156, 6 + oy, 58 + oy)
    _strip(shim, real, data.days, 162, 506, 6, _LONG_GEO, units, oy)
