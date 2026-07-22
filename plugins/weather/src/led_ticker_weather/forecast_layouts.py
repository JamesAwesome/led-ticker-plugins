"""The three per-sign forecast renderers, ported from the handoff draw
functions (design/Weather Forecast.dc.html: weatherSmall / weatherBig /
weatherLong). Coordinates and sizes are handoff-normative; icons diverge
to packaged emoji (spec divergence 1: boxes snap to sprite sizes).
"""

from led_ticker.plugin import FONT_SMALL, draw_emoji_at, draw_text

from led_ticker_weather.forecast_data import (
    KIND_SLUGS,
    DayForecast,
    ForecastData,
    display_temp,
)
from led_ticker_weather.paint import dim
from led_ticker_weather.palette import AMBER, IDENT, LABEL

# --- smallsign (160x16, BDF, logical coords) — handoff weatherSmall ---

_SMALL_CW = 53  # column width
_SMALL_X0 = 2
_SMALL_TEXT_DX = 17  # text block starts right of the icon slot
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
        draw_emoji_at(canvas, lowres, x + 3, _SMALL_ICON_Y + y_offset)
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
