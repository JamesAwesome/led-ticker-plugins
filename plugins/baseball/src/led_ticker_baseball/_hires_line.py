"""HiresLine — a status line that renders hi-res at scale>1 and BDF at
scale<=1.

The single home for baseball's scale-dispatched non-hero lines (scores
series-title, no-data / off-day / next-game). Below the hero-card threshold
every widget forwarded these to a BDF SegmentMessage/TickerMessage, which
ScaledCanvas block-scales into chunky lores on a bigsign/longboi. This draws
the same content in hi-res Inter at scale>1 (centered, fit-to-width,
per-segment color) and forwards verbatim to the BDF `legacy` line at
scale<=1 (smallsign unchanged). Generalizes the single-color
`_attendance_card._draw_fallback_line` (v1.8.0) to multi-segment.
"""

from typing import Any

import attrs
from led_ticker.plugin import (
    ColorProvider,
    DrawResult,
    FrameAwareBase,
    make_color,
    safe_scale,
)

from led_ticker_baseball._paint import (
    cap_top,
    fit_text,
    hires,
    js_round,
    phys_wrap,
    text_width,
)

_MIN_SIZE = 12
_MARGIN = 8  # physical px kept clear on each side


@attrs.define
class HiresLine(FrameAwareBase):
    segments: list[tuple[str, Any]]  # (text, Color | ColorProvider)
    legacy: Any
    size: int = attrs.field(default=20, kw_only=True)
    center: bool = attrs.field(default=True, kw_only=True)

    def draw(
        self,
        canvas: Any,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        # Empty content or smallsign -> the BDF legacy path (unchanged).
        if not self.segments or safe_scale(canvas) <= 1:
            return self.legacy.draw(
                canvas, cursor_pos, y_offset=y_offset, font_color=font_color
            )
        scale = safe_scale(canvas)
        shim, real = phys_wrap(canvas)
        yo = y_offset * scale
        max_w = real.width - 2 * _MARGIN

        # Fit: shrink the size until the whole line fits; floor at _MIN_SIZE.
        size = self.size
        texts = [t for t, _ in self.segments]
        while size > _MIN_SIZE and sum(text_width(size, t) for t in texts) > max_w:
            size -= 1

        # If still over at the floor, ellipsize the trailing segment on its
        # own remaining width budget (fit_text appends the ellipsis).
        drawn = list(self.segments)
        if sum(text_width(size, t) for t, _ in drawn) > max_w:
            head_w = sum(text_width(size, t) for t, _ in drawn[:-1])
            last_text, last_color = drawn[-1]
            drawn[-1] = (fit_text(last_text, max(0, max_w - head_w), size), last_color)

        total = sum(text_width(size, t) for t, _ in drawn)
        # A line too wide to fit even after the shrink + trailing-ellipsize
        # passes above centers to a negative start, clipping the LEADING
        # segment off the left edge. Clamp to the left margin instead -- the
        # line left-aligns and the per-segment right clamp below ellipsizes
        # the TAIL, preserving reading order. No-op for a normal (fitting)
        # line, whose centered start is already >= _MARGIN.
        x = max(_MARGIN, js_round((real.width - total) / 2)) if self.center else _MARGIN
        # Center by the glyphs' visible cap-height, matching the attend_* `_t`
        # convention (js_round(size * 0.72) approximates the cap box).
        glyph_h = js_round(size * 0.72)
        y = cap_top(js_round((real.height - glyph_h) / 2) + yo, size)

        # Final safety clamp: the shrink + trailing-ellipsize passes above
        # minimize truncation in the common case, but only ellipsize the
        # LAST segment — if a non-last (head) segment alone already exceeds
        # `max_w` even at the floor size, its glyphs would still draw at
        # full width here, potentially past the right margin. Clip against
        # the actual cursor position per segment so head overflow can never
        # push later glyphs (or itself) off the right edge.
        right = real.width - _MARGIN
        for text, color in drawn:
            if x >= right:
                break
            clipped = False
            if text_width(size, text) > right - x:
                text = fit_text(text, right - x, size)
                clipped = True
            if isinstance(color, ColorProvider):
                c = color.color_for(self._frame_count, 0, 1)
            elif isinstance(color, tuple):
                # Raw (r, g, b) tuple, not a Color -- coerce so `.red`
                # access in the draw path below doesn't crash.
                c = make_color(*color)
            else:
                c = color
            x += hires(shim, text, x, y, c, size)
            if clipped:
                break
        # Logical wrapper width -> engine takes the HOLD branch (same lesson
        # as the hero cards).
        return canvas, canvas.width

    def advance_frame(self, *, visit_id: int | None = None) -> None:
        super().advance_frame(visit_id=visit_id)
        self.legacy.advance_frame(visit_id=visit_id)

    def pause_frame(self) -> None:
        super().pause_frame()
        self.legacy.pause_frame()

    def resume_frame(self) -> None:
        super().resume_frame()
        self.legacy.resume_frame()

    def reset_frame(self) -> None:
        super().reset_frame()
        self.legacy.reset_frame()
