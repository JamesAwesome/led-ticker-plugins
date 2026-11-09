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

import warnings
from typing import Any

import attrs
from led_ticker.plugin import (
    SNAP_THRESHOLD,
    Canvas,
    FrameAwareBase,
    ScaledCanvas,
    is_scaled,
    snap_reset,
    unwrap_to_real,
)

from led_ticker_flair.flair._raster import Raster, snapshot_into
from led_ticker_flair.flair.accordion_cards import (
    Deck,
    Plan,
    build_decks,
    is_image_widget,
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


# The two-row fields a solo-row copy blanks, and the ones it drops so only
# text is measured (the ring is excluded separately; band fills would light
# a whole band in both renders).
_ROW_FIELDS = ("top_text", "bottom_text")
_DROP_FIELDS = ("border", "top_bg_color", "bottom_bg_color")


def _attrs_widget(widget: Any) -> Any:
    """The attrs widget behind ``widget``: itself, or the one a core
    transition draw guard wraps (its ``_widget`` slot). ``None`` if there
    is none."""
    for _ in range(4):
        if attrs.has(type(widget)):
            return widget
        widget = getattr(widget, "_widget", None)
        if widget is None:
            return None
    return None


def _copy_frame_state(live: Any, copy: Any, keep: str) -> None:
    """Give ``copy`` the live widget's frame counters and paused state (so
    animated effects paint the same frame), plus the live widget's FROZEN
    resolved text/segments for the row it keeps (``"top"`` or ``"bottom"``).
    The copy must draw exactly what the live widget draws, so it never
    resolves tokens against the registry itself; it stays locked. Raises
    ``AttributeError`` when ``live`` lacks the resolved-state attributes (the
    caller falls back to the nominal split)."""
    if isinstance(live, FrameAwareBase):
        for f in attrs.fields(FrameAwareBase):
            value = getattr(live, f.name)
            setattr(copy, f.name, dict(value) if isinstance(value, dict) else value)
    resolved = getattr(live, f"_resolved_{keep}")
    segments = getattr(live, f"_{keep}_segments")
    setattr(copy, f"_resolved_{keep}", resolved)
    setattr(copy, f"_{keep}_segments", segments)
    copy._resolution_locked = True


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
        self._out_plan: Plan | None = None
        self._in_plan: Plan | None = None
        # Scratch rasters (outgoing, incoming, border-only, top-only,
        # bottom-only), reused across frames/firings while the geometry key
        # matches. Re-keying never touches a plan already built.
        self._rasters: list[Raster | None] = [None] * 5
        self._raster_key: tuple[int, int, int, int | None] | None = None

    # --- motion (bound by subclasses) ---------------------------------------

    # Each takes ALL of a plan's decks and returns one position list per
    # deck: the decks share one anchor trajectory, so they move in lockstep.

    def _out(self, decks: list[Deck], W: int, k: float) -> list[list[float]]:  # noqa: N803
        raise NotImplementedError

    def _in(self, decks: list[Deck], W: int, k: float) -> list[list[float]]:  # noqa: N803
        raise NotImplementedError

    # --- snapshot -------------------------------------------------------------

    def _scratch(self, slot: int, w: int, h: int) -> Raster:
        raster = self._rasters[slot]
        if raster is None:
            raster = Raster(w, h)
            self._rasters[slot] = raster
        return raster

    def _border_only(self, canvas: Any, widget: Any, w: int, h: int) -> Raster | None:
        """Paint the widget's border ALONE, exactly as the widget's own draw
        does (``border.paint(canvas, widget.frame_for("border"))``, through
        the same wrapper), so ``build_decks`` can tell ring pixels from
        content in the ring zone. ``None`` when that isn't possible; the
        depth-based ring is then the fallback. Never raises."""
        border = getattr(widget, "border", None)
        if border is None or is_image_widget(widget):
            return None
        paint = getattr(border, "paint", None)
        frame_for = getattr(widget, "frame_for", None)
        if not callable(paint) or not callable(frame_for):
            return None
        try:
            frame = frame_for("border")
            if not isinstance(frame, int) or isinstance(frame, bool):
                return None
            raster = self._scratch(2, w, h)
            raster.Clear()
            target: Any = raster
            if is_scaled(canvas):
                target = ScaledCanvas(
                    raster, scale=canvas.scale, content_height=canvas.content_height
                )
            paint(target, frame)
        except Exception:  # a probe must never break a transition
            return None
        return raster

    def _solo_rows(
        self, canvas: Any, widget: Any, cursor_pos: int, w: int, h: int
    ) -> tuple[Raster, Raster] | None:
        """Snapshot two COPIES of a two-row widget, one with only the top row
        and one with only the bottom row (the other row's text set to
        ``" "``), so ``build_decks`` knows which row paints each pixel. The
        copies drop the border and band fills (only text is measured) and
        carry the live widget's frame state; the live widget is never
        touched. ``None`` (-> the nominal split) when the widget isn't an
        attrs instance with ``top_text`` / ``bottom_text`` fields, or
        anything raises."""
        live = _attrs_widget(widget)
        if live is None:
            return None
        try:
            fields = attrs.fields_dict(type(live))
            if not all(n in fields and fields[n].init for n in _ROW_FIELDS):
                return None
            drop = {n: None for n in _DROP_FIELDS if n in fields and fields[n].init}
            out: list[Raster] = []
            for slot, blank, keep in (
                (3, "bottom_text", "top"),
                (4, "top_text", "bottom"),
            ):
                with warnings.catch_warnings():  # e.g. a deprecated alias
                    warnings.simplefilter("ignore")
                    copy = attrs.evolve(live, **drop, **{blank: " "})
                _copy_frame_state(live, copy, keep)
                raster = self._scratch(slot, w, h)
                snapshot_into(raster, canvas, copy, cursor_pos)
                out.append(raster)
        except Exception:  # a probe must never break a transition
            return None
        return out[0], out[1]

    def _plan(self, canvas: Any, widget: Any, cursor_pos: int, slot: int) -> Plan:
        scaled = is_scaled(canvas)
        real = unwrap_to_real(canvas) if scaled else canvas
        key = (
            real.width,
            real.height,
            canvas.scale if scaled else 1,
            canvas.content_height if scaled else None,
        )
        if self._raster_key != key:
            self._rasters = [None] * 5
            self._raster_key = key
        raster = self._scratch(slot, real.width, real.height)
        snapshot_into(raster, canvas, widget, cursor_pos)
        border_only = self._border_only(canvas, widget, real.width, real.height)
        return build_decks(
            raster,
            widget,
            canvas,
            mirror=self._mirror,
            border_only=border_only,
            solo_rows=lambda: self._solo_rows(
                canvas, widget, cursor_pos, real.width, real.height
            ),
        )

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
