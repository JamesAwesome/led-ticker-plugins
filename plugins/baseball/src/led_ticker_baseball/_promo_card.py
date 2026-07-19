"""MLBPromoCard — the scale-dispatching story for one promotion, the Phase 3
(Task 4) sibling of `MLBGameCard` (`_card.py`) / `MLBStandingsBoard`
(`_standings_card.py`).

One card per `PromoInfo`. At draw time it resolves (cfg_layout, scale, phys
width) via `layouts.resolve_promo_layout`: scale <= 1 forwards verbatim to
`self.legacy` (the pre-built SegmentMessage for this promo — unlike
`MLBGameCard`, there is only ONE legacy shape here, so it's built eagerly by
`MLBPromotionsMonitor.update()` and passed in, not lazily constructed).
scale > 1 dispatches to the held card (`layouts.promo_card.render_promo_card`)
or the hires crawl (`layouts.promo_crawl.render_promo_crawl`). Held layouts
return cursor = `canvas.width` — the WRAPPER's LOGICAL width — same
hold-vs-scroll lesson as `MLBGameCard`'s module docstring (core's
`cursor_pos > canvas.width` check compares against that, not `real.width`).
The crawl works in logical units too: `cursor_pos` in is logical, the segment
run paints at physical `x = cursor_pos * scale`, and the returned advance is
ceil-divided back to logical (core's `get_text_width` hires convention).

Per-card clock (`_clock_ticks`): advanced in `advance_frame` gated on
`not self._frame_paused`, and deliberately NEVER reset — `reset_frame` fires
(possibly twice, see `_standings_card.py`'s module docstring for the
double-reset-per-visit lesson) on every section re-entry, but the clipped
name-scroll inside a held card must keep running smoothly across visits
rather than snapping back to its start each time this promo card reappears
(same "clock survives visits" lesson as `led_ticker_flight`'s per-card
clock, cited in the phase-3 plan).
"""

from typing import TYPE_CHECKING, Any

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

from led_ticker_baseball.layouts import resolve_promo_layout
from led_ticker_baseball.layouts.promo_card import render_promo_card
from led_ticker_baseball.layouts.promo_crawl import render_promo_crawl

if TYPE_CHECKING:
    # Deferred: quoted so PEP 649 introspection can't NameError on this
    # TYPE_CHECKING-only import — same guard as `_standings_card.py`'s
    # `TeamStanding` import. `promotions.py` imports `MLBPromoCard` back (to
    # build `feed_stories`), so this module must not import it at runtime.
    from led_ticker_baseball.promotions import PromoInfo


@attrs.define
class MLBPromoCard(FrameAwareBase):
    promo: "PromoInfo"  # noqa: UP037 — introspection-safe forward ref
    story_index: int
    story_total: int
    # The pre-built legacy SegmentMessage for this promo — see module
    # docstring for why this is eager, not lazy like MLBGameCard's `_legacy`.
    legacy: Any
    cfg_layout: str = "auto"
    padding: int = 6
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font_color: Color | ColorProvider | None = attrs.field(default=None, kw_only=True)
    _clock_ticks: int = attrs.field(init=False, default=0)

    def draw(
        self,
        canvas: Any,
        cursor_pos: int = 0,
        *,
        y_offset: int = 0,
        font_color: Any = None,
    ) -> DrawResult:
        scale = safe_scale(canvas)
        if scale <= 1:
            return self.legacy.draw(
                canvas, cursor_pos, y_offset=y_offset, font_color=font_color
            )
        real = unwrap_to_real(canvas)
        layout = resolve_promo_layout(self.cfg_layout, scale, real.width)
        if layout == "ticker":
            w = render_promo_crawl(
                canvas,
                self.promo,
                cursor_pos,
                y_offset=y_offset,
                hold_padding=self.padding,
            )
            return canvas, w + self.padding
        render_promo_card(
            canvas,
            self.promo,
            self._clock_ticks * ENGINE_TICK_MS,
            y_offset=y_offset,
            story_index=self.story_index,
            story_total=self.story_total,
        )
        # Held layout: return the WRAPPER's logical width (not real.width)
        # so the engine's `cursor_pos > canvas.width` hold-vs-scroll check
        # (core ticker.py) takes the hold branch — same phase-1/2 lesson as
        # MLBGameCard / MLBStandingsBoard.
        return canvas, canvas.width

    # Forward frame hooks to the (always-present) legacy story so its
    # frame-aware effects (rainbow / color_cycle font_color) behave at
    # scale<=1, exactly mirroring MLBGameCard's forwarding to its cached
    # `_legacy` story — the only difference is `self.legacy` is never None
    # here, so no guard is needed before forwarding.
    def advance_frame(self, *, visit_id: int | None = None) -> None:
        super().advance_frame(visit_id=visit_id)
        # Mirrors super().advance_frame's own pause check — a paused advance
        # (transition compositing) must not tick the clipped name-scroll
        # clock forward.
        if not self._frame_paused:
            self._clock_ticks += 1
        self.legacy.advance_frame(visit_id=visit_id)

    def pause_frame(self) -> None:
        super().pause_frame()
        self.legacy.pause_frame()

    def resume_frame(self) -> None:
        super().resume_frame()
        self.legacy.resume_frame()

    # Deliberately NO reset_frame override. Two consequences, both
    # intentional: (1) `_clock_ticks` is untouched by the base
    # implementation, so it survives `reset_frame()` — including the
    # documented double-call-per-transitioned-visit (see
    # `_standings_card.py`'s module docstring) — and the clipped name-scroll
    # never snaps back to its start on section re-entry. (2)
    # `self.legacy.reset_frame()` is NOT forwarded — unlike MLBGameCard /
    # MLBStandingsBoard, `self.legacy` here isn't a per-visit-selected
    # story (it's the one fixed SegmentMessage for this card, present for
    # the card's whole lifetime), so there's no stale per-visit state on it
    # that a reset would need to clear.
