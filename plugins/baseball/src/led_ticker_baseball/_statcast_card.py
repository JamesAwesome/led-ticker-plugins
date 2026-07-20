"""MLBStatcastCard — the scale-dispatching, frame-aware story wrapping one
statcast record. Sibling of `_card.py` / `_promo_card.py` /
`_standings_card.py`.

At draw time it resolves (cfg_layout, scale, phys width) via
`layouts.resolve_statcast_layout`: scale <= 1 forwards verbatim to
`self.legacy` (the pre-built SegmentMessage line for this record — same
"only one legacy shape, built eagerly and passed in" convention as
`MLBPromoCard`). scale > 1 dispatches to the held big card (256,
`layouts.statcast_big.render_statcast_big`) or the held long card (512,
`layouts.statcast_long.render_statcast_long`); both are held layouts, so
`draw` returns `canvas.width` — the WRAPPER's LOGICAL width, not
`real.width` — same hold-vs-scroll lesson as every other card in this
plugin (core's `cursor_pos > canvas.width` check compares against that).

Flight clock (`_flight_ticks`): advanced in `advance_frame` gated on
`not self._frame_paused`, and — unlike `_promo_card.py`'s clock (survives
visits) and `_standings_card.py`'s arm/consume row cycling — RESET on
`reset_frame()`. The trajectory ball must fly FRESH each time the card is
shown, so the flight restarts on section re-entry. Core's documented
double-reset-per-transitioned-visit is harmless here (0 -> 0); no
arm/consume dance is needed (a monotonic clock zeroed on visit, not
discrete per-visit selection state like the standings board's row index).
"""

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

from led_ticker_baseball.layouts import resolve_statcast_layout
from led_ticker_baseball.layouts.statcast_big import render_statcast_big
from led_ticker_baseball.layouts.statcast_long import render_statcast_long

FLIGHT_MS = 1500


@attrs.define
class MLBStatcastCard(FrameAwareBase):
    record: Any
    player_name: str
    legacy: Any
    story_index: int = 0
    story_total: int = 1
    cfg_layout: str = "auto"
    padding: int = 6
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    _flight_ticks: int = attrs.field(init=False, default=0)

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
        layout = resolve_statcast_layout(self.cfg_layout, scale, real.width)
        if layout == "legacy":
            return self.legacy.draw(
                canvas, cursor_pos, y_offset=y_offset, font_color=font_color
            )
        progress = min(1.0, self._flight_ticks * ENGINE_TICK_MS / FLIGHT_MS)
        if layout == "big":
            render_statcast_big(
                canvas,
                self.record,
                self.player_name,
                progress,
                y_offset=y_offset,
                story_index=self.story_index,
                story_total=self.story_total,
            )
        else:
            render_statcast_long(
                canvas,
                self.record,
                self.player_name,
                progress,
                y_offset=y_offset,
                story_index=self.story_index,
                story_total=self.story_total,
            )
        # Held layout: return the WRAPPER's logical width (not real.width)
        # so the engine's `cursor_pos > canvas.width` hold-vs-scroll check
        # (core ticker.py) takes the hold branch — same phase-1/2/3 lesson
        # as MLBGameCard / MLBStandingsBoard / MLBPromoCard.
        return canvas, canvas.width

    # Forward frame hooks to the (always-present) legacy story so its
    # frame-aware effects (rainbow / color_cycle font_color) behave at
    # scale<=1, mirroring MLBPromoCard's forwarding to its own `legacy`.
    def advance_frame(self, *, visit_id: int | None = None) -> None:
        super().advance_frame(visit_id=visit_id)
        # Mirrors super().advance_frame's own pause check — a paused
        # advance (transition compositing) must not tick the flight clock
        # forward.
        if not self._frame_paused:
            self._flight_ticks += 1
        self.legacy.advance_frame(visit_id=visit_id)

    def pause_frame(self) -> None:
        super().pause_frame()
        self.legacy.pause_frame()

    def resume_frame(self) -> None:
        super().resume_frame()
        self.legacy.resume_frame()

    def reset_frame(self) -> None:
        super().reset_frame()
        # Restart-on-visit: unlike MLBPromoCard's `_clock_ticks` (never
        # reset, so a clipped name-scroll keeps running across visits),
        # the trajectory ball must fly FRESH every time this card
        # reappears — zero the flight clock on every reset_frame() call,
        # including core's documented double call per transitioned visit
        # (0 -> 0 the second time, harmless).
        self._flight_ticks = 0
        self.legacy.reset_frame()
