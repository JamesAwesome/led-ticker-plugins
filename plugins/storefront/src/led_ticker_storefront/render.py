"""Draw the active OPEN/CLOSED badge on the raw real canvas. Corner-anchored;
horizontal or vertical (stacked) layout; opaque or transparent background;
hi-res font at native size or BDF block-scaled up to font_size; flat or animated
color providers."""

import logging

from led_ticker.plugin import (
    HiresFont,
    ScaledCanvas,
    compute_baseline_for_band,
    draw_text,
    draw_text_per_char,
    font_line_height_logical,
    get_text_width,
    safe_scale,
)

_log = logging.getLogger("led_ticker_storefront")

# One-shot latch so the oversized-badge warning logs once per distinct
# oversized configuration instead of flooding the log every render tick
# (~20/sec). Keyed on the values that determine "does it fit".
_WARNED_OVERSIZED = set()


def _target(real_canvas, font, cfg):
    """Pick the draw target + report its logical scale. Hi-res and scale-1 BDF
    draw on the raw canvas; larger BDF wraps in a ScaledCanvas (no letterbox:
    content_height = real.height // scale keeps y_offset_real == 0)."""
    if isinstance(font, HiresFont):
        return real_canvas
    cell_h = font_line_height_logical(font, 1)
    scale = max(1, round(cfg.font_size / cell_h))
    if scale == 1:
        return real_canvas
    content_h = real_canvas.height // scale
    return ScaledCanvas(real_canvas, scale=scale, content_height=content_h)


def _fill_box(canvas, x0, y0, w, h, rgb):
    r, g, b = rgb
    for dy in range(h):
        for dx in range(w):
            canvas.SetPixel(x0 + dx, y0 + dy, r, g, b)


def _color(badge, frame, char_index, total):
    return badge.color.color_for(frame, char_index, total)


def _draw_text_run(canvas, font, text, x, baseline_y, badge, frame):
    if badge.color.per_char:
        draw_text_per_char(
            canvas,
            font,
            x,
            baseline_y,
            text,
            lambda idx, total: _color(badge, frame, idx, total),
        )
    else:
        color = _color(badge, frame, 0, max(1, len(text)))
        draw_text(canvas, font, text, x, baseline_y, color)


def draw_badge(real_canvas, cfg, badge, frame):
    text = badge.text
    if not text:
        return
    font = cfg.font
    canvas = _target(real_canvas, font, cfg)
    scale = safe_scale(canvas)
    pad = cfg.padding
    line_h = font_line_height_logical(font, scale)
    width, height = canvas.width, canvas.height

    if badge.orientation == "vertical":
        col_w = max(get_text_width(font, ch, padding=0, canvas=canvas) for ch in text)
        box_w = col_w + 2 * pad
        box_h = line_h * len(text) + 2 * pad
    else:
        tw = get_text_width(font, text, padding=0, canvas=canvas)
        box_w = tw + 2 * pad
        box_h = line_h + 2 * pad

    if box_w > width or box_h > height:
        key = (text, cfg.font_size, badge.orientation, width, height)
        if key not in _WARNED_OVERSIZED:
            _WARNED_OVERSIZED.add(key)
            _log.warning(
                "storefront: badge %r (%dx%d) does not fit the %dx%d panel at "
                "font_size=%d; skipping. Use a smaller font_size or a shorter "
                "label.",
                text,
                box_w,
                box_h,
                width,
                height,
                cfg.font_size,
            )
        return

    x0 = 0 if "left" in badge.corner else width - box_w
    y0 = 0 if "top" in badge.corner else height - box_h

    if cfg.background is not None:
        _fill_box(canvas, x0, y0, box_w, box_h, cfg.background)

    if badge.orientation == "vertical":
        band_baseline = compute_baseline_for_band(font, line_h, scale, valign="top")
        for i, ch in enumerate(text):
            cw = get_text_width(font, ch, padding=0, canvas=canvas)
            cx = x0 + pad + (col_w - cw) // 2
            band_top = y0 + pad + i * line_h
            baseline = band_top + band_baseline
            color = _color(badge, frame, i, len(text))
            draw_text(canvas, font, ch, cx, baseline, color)
    else:
        band_baseline = compute_baseline_for_band(font, line_h, scale, valign="top")
        baseline = y0 + pad + band_baseline
        _draw_text_run(canvas, font, text, x0 + pad, baseline, badge, frame)
