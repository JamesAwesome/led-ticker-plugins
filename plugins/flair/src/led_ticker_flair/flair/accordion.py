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

from led_ticker_flair.flair._deck_snapshot import DeckSnapshotMixin
from led_ticker_flair.flair.accordion_cards import (
    Deck,
    Plan,
)
from led_ticker_flair.flair.accordion_compose import compose
from led_ticker_flair.flair.accordion_motion import (
    stretch_in_decks,
    stretch_out_decks,
    sweep_in_decks,
    sweep_out_decks,
)

_DIRECTIONS = ("left", "right")
_OUT_END = 0.475  # outgoing phase [0, 0.475); beat [0.475, 0.5)
_IN_START = 0.5  # incoming phase [0.5, SNAP_THRESHOLD)


def _clamp01(k: float) -> float:
    return 0.0 if k < 0.0 else 1.0 if k > 1.0 else k


class _Accordion(DeckSnapshotMixin):
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
        self._init_deck_snapshot(direction == "right")
        self._last_t = 1.0
        # Immutable extracted data, built once per firing.
        self._out_plan: Plan | None = None
        self._in_plan: Plan | None = None

    # --- motion (bound by subclasses) ---------------------------------------

    # Each takes ALL of a plan's decks and returns one position list per
    # deck: the decks share one anchor trajectory, so they move in lockstep.

    def _out(self, decks: list[Deck], W: int, k: float) -> list[list[float]]:  # noqa: N803
        raise NotImplementedError

    def _in(self, decks: list[Deck], W: int, k: float) -> list[list[float]]:  # noqa: N803
        raise NotImplementedError

    # --- paint ----------------------------------------------------------------

    def _paint(self, real: Any, plan: Plan, motion: Any, k: float) -> None:
        decks, ring, under = plan
        w = real.width
        set_px = real.SetPixel
        # Border pixels the content covered: under the cards, so the ring
        # has no hole once a card moves off them.
        for x, y, (r, g, b) in under:
            set_px(x, y, r, g, b)
        for deck, positions in zip(decks, motion(decks, w, k), strict=True):
            if deck.cards:
                compose(deck, positions, w, set_px, mirror=self._mirror)
        # The ring stays put, painted over the cards (cards pass under it).
        for x, y, (r, g, b) in ring:
            set_px(x, y, r, g, b)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        # New firing -> fresh snapshots. t == 0.0 always starts a firing:
        # one cancelled right after its t=0 frame leaves _last_t == 0, and
        # the next firing's t=0 must not replay that stale outgoing plan.
        # Equal NON-zero t is a repeated frame, not a refire.
        if t == 0.0 or t < self._last_t:
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

    def _out(self, decks: list[Deck], W: int, k: float) -> list[list[float]]:  # noqa: N803
        return sweep_out_decks(decks, W, k)

    def _in(self, decks: list[Deck], W: int, k: float) -> list[list[float]]:  # noqa: N803
        return sweep_in_decks(decks, W, k)


class AccordionStretch(_Accordion):
    """Stretching accordion: the content moves as one piece, squeezing shut
    as it leaves and opening up as it lands, reaching full spacing exactly
    on arrival."""

    def _out(self, decks: list[Deck], W: int, k: float) -> list[list[float]]:  # noqa: N803
        return stretch_out_decks(decks, W, k)

    def _in(self, decks: list[Deck], W: int, k: float) -> list[list[float]]:  # noqa: N803
        return stretch_in_decks(decks, W, k)


class _AccordionAlternating:
    """Flips direction each firing (FairyAlternating / LaserAlternating
    convention). ``direction`` picks the first firing's side (default
    ``"left"``: left, right, left, ...). Holds one instance per direction and
    delegates, so each keeps its own plans and scratch rasters. A new
    firing is detected with the same rule as ``_Accordion.frame_at``
    (``t == 0.0`` or ``t`` went backwards), so the wrapper and the inner
    instance always agree on where a firing starts."""

    _motion: type[_Accordion]

    def __init__(self, direction: Any = "left") -> None:
        if direction not in _DIRECTIONS:
            raise ValueError(
                f"direction must be one of {_DIRECTIONS}; got {direction!r}"
            )
        start = _DIRECTIONS.index(direction)
        order = _DIRECTIONS[start:] + _DIRECTIONS[:start]
        self._transitions: list[_Accordion] = [self._motion(direction=d) for d in order]
        self._index: int = -1
        self._last_t: float = 1.0

    @property
    def min_frames(self) -> int:
        return self._transitions[0].min_frames

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t == 0.0 or t < self._last_t:
            self._index = (self._index + 1) % len(self._transitions)
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )


class AccordionSweepAlternating(_AccordionAlternating):
    """``flair.accordion.sweep`` with the direction flipped every firing."""

    _motion = AccordionSweep


class AccordionStretchAlternating(_AccordionAlternating):
    """``flair.accordion.stretch`` with the direction flipped every firing."""

    _motion = AccordionStretch
