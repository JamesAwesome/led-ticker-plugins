"""HiresLine — a status line that renders hi-res at scale>1 and forwards
to a BDF `TickerMessage` at scale<=1 (baseball's `_hires_line` pattern,
trimmed to the single-segment case this pack needs: "set the key",
"no matches", "key rejected")."""

from typing import Any

import attrs
from led_ticker.plugin import (
    Color,
    DrawResult,
    FrameAwareBase,
    safe_scale,
)

from led_ticker_tennis._paint import (
    cap_top,
    fit_size,
    fit_text,
    hires,
    js_round,
    phys_wrap,
    text_width,
)

_SIZES = (20, 18, 16, 14, 12)
_MARGIN = 8


@attrs.define
class HiresLine(FrameAwareBase):
    segments: list[tuple[str, Color]]
    legacy: Any
    center: bool = attrs.field(default=True, kw_only=True)

    def draw(
        self,
        canvas: Any,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        if not self.segments or safe_scale(canvas) <= 1:
            return self.legacy.draw(
                canvas, cursor_pos, y_offset=y_offset, font_color=font_color
            )
        scale = safe_scale(canvas)
        shim, real = phys_wrap(canvas)
        yo = y_offset * scale
        max_w = real.width - 2 * _MARGIN
        text = " ".join(t for t, _ in self.segments)
        color = self.segments[0][1]
        size = fit_size(text, _SIZES, max_w)
        text = fit_text(text, max_w, size)
        w = text_width(size, text)
        x = max(_MARGIN, js_round((real.width - w) / 2)) if self.center else _MARGIN
        glyph_h = js_round(size * 0.72)
        y = cap_top(js_round((real.height - glyph_h) / 2) + yo, size)
        hires(shim, text, x, y, color, size)
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
