"""MLBAttendanceCard — scale-dispatching, frame-aware story for one
attendance record (team game or league superlative). Sibling of
`_statcast_card.py`. Fill clock (`_fill_ticks`): advanced in `advance_frame`
gated on `not _frame_paused`, RESET on `reset_frame` (restart-on-visit — the
bar re-fills each appearance, like the statcast ball; OPPOSITE of
`_promo_card.py` whose clock survives). A record with no drawable attendance
(a game not yet Final: `paid is None`, or an off day) delegates to a
`HiresLine` built from `fallback_segments` + the card's own `legacy` line:
non-empty segments render a centered, per-segment-colored hires line at
scale>1; an empty list is the safety net that forwards to `legacy` instead
(BDF fits the 16px smallsign, and this never blanks or crashes). Generalizes
the v1.8.0 single-color `_draw_fallback_line` (removed) to multi-segment,
which also lets the fallback line carry the game-day weather segment."""

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

from led_ticker_baseball._hires_line import HiresLine
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
    # No-attendance fallback line (scale>1 only; see `_fallback_line`
    # and the `draw()` dispatch below). Empty list is the safety net that
    # forwards to `legacy` instead — never blank/crash (HiresLine itself
    # implements that fallback).
    fallback_segments: list[tuple[str, Color | ColorProvider]] = attrs.field(
        factory=list
    )
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    _fill_ticks: int = attrs.field(init=False, default=0)
    # The no-attendance fallback story, built once from `fallback_segments` +
    # the SAME `legacy` object the card wraps — so its own scale<=1 / empty-
    # segments forwarding lands on the one shared `legacy` instance, and the
    # frame hooks below can forward to it in place of `legacy` directly
    # without double-ticking `legacy` (see the hook overrides).
    _fallback_line: HiresLine = attrs.field(
        init=False,
        default=attrs.Factory(
            lambda self: HiresLine(self.fallback_segments, legacy=self.legacy),
            takes_self=True,
        ),
    )

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
            # No-attendance fallback (a team game not yet Final, or an off
            # day). We're already past the scale<=1 branch above, so this is
            # ALWAYS scale>1 here. `_fallback_line` renders `fallback_segments`
            # as a hires line (readable at native panel resolution, unlike
            # forwarding the legacy BDF line through the block-scaled
            # wrapper) — or forwards to `legacy` as a safety net when
            # `fallback_segments` is empty, so this state never blanks or
            # crashes.
            return self._fallback_line.draw(
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

    # Forward frame hooks to `_fallback_line` rather than `legacy` directly —
    # `_fallback_line.legacy IS self.legacy`, and HiresLine's own hooks
    # already cascade into it, so forwarding to `_fallback_line` ticks BOTH
    # its own frame-aware effects (rainbow / color_cycle font_color on the
    # fallback segments) AND `legacy` (for scale<=1), without double-ticking
    # `legacy`. Mirrors MLBStatcastCard's forwarding to its own `legacy`.
    def advance_frame(self, *, visit_id: int | None = None) -> None:
        super().advance_frame(visit_id=visit_id)
        # Mirrors super().advance_frame's own pause check — a paused
        # advance (transition compositing) must not tick the fill clock
        # forward.
        if not self._frame_paused:
            self._fill_ticks += 1
        self._fallback_line.advance_frame(visit_id=visit_id)

    def pause_frame(self) -> None:
        super().pause_frame()
        self._fallback_line.pause_frame()

    def resume_frame(self) -> None:
        super().resume_frame()
        self._fallback_line.resume_frame()

    def reset_frame(self) -> None:
        super().reset_frame()
        # Restart-on-visit: unlike MLBPromoCard's clock (never reset), the
        # capacity bar must fill FRESH every time this card reappears —
        # zero the fill clock on every reset_frame() call, including
        # core's documented double call per transitioned visit (0 -> 0 the
        # second time, harmless).
        self._fill_ticks = 0
        self._fallback_line.reset_frame()
