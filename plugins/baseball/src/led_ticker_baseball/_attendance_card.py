"""MLBAttendanceCard — scale-dispatching, frame-aware story for one
attendance record (team game or league superlative). Sibling of
`_statcast_card.py`. Fill clock (`_fill_ticks`): advanced in `advance_frame`
gated on `not _frame_paused`, RESET on `reset_frame` (restart-on-visit — the
bar re-fills each appearance, like the statcast ball; OPPOSITE of
`_promo_card.py` whose clock survives). A record with no drawable attendance
(a game not yet Final: `paid is None`) forwards to the legacy line rather
than drawing an empty bar."""

from typing import Any

import attrs
from led_ticker.plugin import (
    ENGINE_TICK_MS,
    Color,
    ColorProvider,
    DrawResult,
    FrameAwareBase,
    safe_scale,
    unwrap_to_real,
)

from led_ticker_baseball.layouts import resolve_attendance_layout
from led_ticker_baseball.layouts.attend_big import render_attend_big
from led_ticker_baseball.layouts.attend_long import render_attend_long

FILL_MS = 1000


def _has_attendance(record) -> bool:
    """True when the record has something to draw a bar for. Team game
    (`AttendanceGame`) needs `paid`; league record (`CrowdRecord`) always
    renders."""
    if hasattr(record, "paid"):  # AttendanceGame (team)
        return record.paid is not None
    return True  # CrowdRecord (league) always renders


@attrs.define
class MLBAttendanceCard(FrameAwareBase):
    record: Any
    legacy: Any
    label: str = ""
    story_index: int = 0
    story_total: int = 1
    cfg_layout: str = "auto"
    padding: int = 6
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    _fill_ticks: int = attrs.field(init=False, default=0)

    def draw(
        self,
        canvas: Any,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        scale = safe_scale(canvas)
        real = unwrap_to_real(canvas)
        layout = resolve_attendance_layout(self.cfg_layout, scale, real.width)
        if layout == "legacy":
            # scale <= 1 (resolve_attendance_layout only returns "legacy"
            # there) — forward the wrapper verbatim, matching the sibling
            # cards' scale<=1 dispatch (_statcast_card.py / _promo_card.py).
            return self.legacy.draw(
                canvas, cursor_pos, y_offset=y_offset, font_color=font_color
            )
        if not _has_attendance(self.record):
            # No-attendance fallback (a team game not yet Final) can fire at
            # ANY scale. Forward the WRAPPER, not the unwrapped real canvas:
            # at scale>1 the engine draws every SegmentMessage/TickerMessage
            # THROUGH the ScaledCanvas wrapper, whose draw_bdf_text expands
            # each SetPixel to a scale×scale block, so the fallback line
            # renders large and readable. Forwarding `real` would paint it at
            # native physical resolution — tiny/unreadable on a bigsign. This
            # is the same reason the scale<=1 legacy branch above forwards the
            # wrapper, and how the engine draws every text widget on the sign.
            return self.legacy.draw(
                canvas, cursor_pos, y_offset=y_offset, font_color=font_color
            )
        progress = min(1.0, self._fill_ticks * ENGINE_TICK_MS / FILL_MS)
        if layout == "big":
            render_attend_big(
                canvas,
                self.record,
                progress,
                label=self.label,
                y_offset=y_offset,
                story_index=self.story_index,
                story_total=self.story_total,
            )
        else:
            render_attend_long(
                canvas,
                self.record,
                progress,
                label=self.label,
                y_offset=y_offset,
                story_index=self.story_index,
                story_total=self.story_total,
            )
        # Held layout: return the WRAPPER's logical width (not real.width)
        # so the engine's `cursor_pos > canvas.width` hold-vs-scroll check
        # (core ticker.py) takes the hold branch — same phase-1/2/3 lesson
        # as MLBGameCard / MLBStandingsBoard / MLBPromoCard / MLBStatcastCard.
        return canvas, canvas.width

    # Forward frame hooks to the (always-present) legacy story so its
    # frame-aware effects (rainbow / color_cycle font_color) behave at
    # scale<=1, mirroring MLBStatcastCard's forwarding to its own `legacy`.
    def advance_frame(self, *, visit_id: int | None = None) -> None:
        super().advance_frame(visit_id=visit_id)
        # Mirrors super().advance_frame's own pause check — a paused
        # advance (transition compositing) must not tick the fill clock
        # forward.
        if not self._frame_paused:
            self._fill_ticks += 1
        self.legacy.advance_frame(visit_id=visit_id)

    def pause_frame(self) -> None:
        super().pause_frame()
        self.legacy.pause_frame()

    def resume_frame(self) -> None:
        super().resume_frame()
        self.legacy.resume_frame()

    def reset_frame(self) -> None:
        super().reset_frame()
        # Restart-on-visit: unlike MLBPromoCard's clock (never reset), the
        # capacity bar must fill FRESH every time this card reappears —
        # zero the fill clock on every reset_frame() call, including
        # core's documented double call per transitioned visit (0 -> 0 the
        # second time, harmless).
        self._fill_ticks = 0
        self.legacy.reset_frame()
