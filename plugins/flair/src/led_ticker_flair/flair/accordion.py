"""flair.accordion — the outgoing content bunches into an occluding card
deck that slides off one edge, then the incoming deck slides in from the
far edge and fans out into place, its spread coupled to its travel.

Spec: docs/superpowers/specs/2026-11-03-flair-accordion-transition-design.md

Design in one breath: each widget is snapshotted ONCE per firing into a
plugin-local readable raster (laser's pattern) and split into immutable
decks of cards (``build_decks``) plus a static border ring; every frame
positions each deck with the motion function for the phase and paints it
through the column-owner compositor. Unlike laser, the runner's default
``scale_switch_at`` (0.5) is kept and the incoming widget is snapshotted
LAZILY on the first ``t >= 0.5`` frame, from that frame's (possibly
re-wrapped) canvas, so a cross-scale incoming gets its native size for the
whole incoming phase.
"""

from typing import Any

from led_ticker.plugin import (
    SNAP_THRESHOLD,
    Canvas,
    is_scaled,
    snap_reset,
    unwrap_to_real,
)

from led_ticker_flair.flair._raster import Pixel, Raster, snapshot_into
from led_ticker_flair.flair.accordion_cards import Deck, build_decks
from led_ticker_flair.flair.accordion_compose import compose
from led_ticker_flair.flair.accordion_motion import (
    stretch_in,
    stretch_out,
    sweep_in,
    sweep_out,
)

_DIRECTIONS = ("left", "right")
_OUT_END = 0.475  # outgoing phase [0, 0.475); beat [0.475, 0.5)
_IN_START = 0.5  # incoming phase [0.5, SNAP_THRESHOLD)

_Plan = tuple[list[Deck], list[Pixel]]  # (decks, ring pixels in real coords)


def _clamp01(k: float) -> float:
    return 0.0 if k < 0.0 else 1.0 if k > 1.0 else k


class _Accordion:
    """Shared snapshot / deck / paint logic; subclasses bind the motion.

    ``direction="left"`` (default) exits left and enters from the right;
    ``"right"`` is the horizontal mirror (decks are built in mirrored
    column space and the compositor maps columns back).
    """

    min_frames = 30

    def __init__(self, direction: Any = "left") -> None:
        if direction not in _DIRECTIONS:
            raise ValueError(
                f"direction must be one of {_DIRECTIONS}; got {direction!r}"
            )
        self.direction: str = direction
        self._mirror: bool = direction == "right"
        self._last_t = 1.0
        # Immutable extracted data, built once per firing.
        self._out_plan: _Plan | None = None
        self._in_plan: _Plan | None = None
        # Scratch rasters, reused across frames/firings while the geometry
        # key matches. Re-keying never touches a plan already built.
        self._rasters: list[Raster | None] = [None, None]
        self._raster_key: tuple[int, int, int, int | None] | None = None

    # --- motion (bound by subclasses) ---------------------------------------

    def _out(self, deck: Deck, W: int, k: float) -> list[float]:  # noqa: N803
        raise NotImplementedError

    def _in(self, deck: Deck, W: int, k: float) -> list[float]:  # noqa: N803
        raise NotImplementedError

    # --- snapshot -------------------------------------------------------------

    def _plan(self, canvas: Any, widget: Any, cursor_pos: int, slot: int) -> _Plan:
        scaled = is_scaled(canvas)
        real = unwrap_to_real(canvas) if scaled else canvas
        key = (
            real.width,
            real.height,
            canvas.scale if scaled else 1,
            canvas.content_height if scaled else None,
        )
        if self._raster_key != key:
            self._rasters = [None, None]
            self._raster_key = key
        raster = self._rasters[slot]
        if raster is None:
            raster = Raster(real.width, real.height)
            self._rasters[slot] = raster
        snapshot_into(raster, canvas, widget, cursor_pos)
        return build_decks(raster, widget, canvas, mirror=self._mirror)

    # --- paint ----------------------------------------------------------------

    def _paint(self, real: Any, plan: _Plan, motion: Any, k: float) -> None:
        decks, ring = plan
        w = real.width
        set_px = real.SetPixel
        for deck in decks:
            if deck.cards:
                compose(deck, motion(deck, w, k), w, set_px, mirror=self._mirror)
        # The ring stays put, painted over the cards (cards pass under it).
        for x, y, (r, g, b) in ring:
            set_px(x, y, r, g, b)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t < self._last_t:  # new firing -> fresh snapshots
            self._out_plan = None
            self._in_plan = None
        self._last_t = t

        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        if self._out_plan is None:
            pos = kwargs.get("outgoing_scroll_pos", 0)
            self._out_plan = self._plan(canvas, outgoing, pos, 0)
        # `real` is re-derived EVERY call, never cached (constraint #1).
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas

        if t < _OUT_END:
            k = _clamp01(t / _OUT_END)
            self._paint(real, self._out_plan, self._out, k)
        elif t >= _IN_START:
            if self._in_plan is None:  # lazy: this frame's (re-wrapped) canvas
                self._in_plan = self._plan(canvas, incoming, 0, 1)
            k = _clamp01((t - _IN_START) / (SNAP_THRESHOLD - _IN_START))
            self._paint(real, self._in_plan, self._in, k)
        # else: the beat between decks — bg only, nothing painted.
        return canvas


class AccordionSweep(_Accordion):
    """Dealer's sweep: a hand scoops the outgoing cards up one by one and
    pushes the stack off; the incoming stack is laid down card by card,
    rightmost first."""

    def _out(self, deck: Deck, W: int, k: float) -> list[float]:  # noqa: N803
        return sweep_out(deck, W, k)

    def _in(self, deck: Deck, W: int, k: float) -> list[float]:  # noqa: N803
        return sweep_in(deck, W, k)


class AccordionStretch(_Accordion):
    """Stretching accordion: the content moves as one piece, squeezing shut
    as it leaves and opening up as it lands, reaching full spacing exactly
    on arrival."""

    def _out(self, deck: Deck, W: int, k: float) -> list[float]:  # noqa: N803
        return stretch_out(deck, W, k)

    def _in(self, deck: Deck, W: int, k: float) -> list[float]:  # noqa: N803
        return stretch_in(deck, W, k)
