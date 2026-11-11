"""Snapshot a widget into accordion-style decks (``build_decks``), with the
exact border ring (a border-only render) and a two-row per-pixel row split
(single-row renders of attrs copies). Shared by flair.accordion and
flair.splitflap; extracted verbatim from ``_Accordion``.
"""

import warnings
from typing import Any

import attrs
from led_ticker.plugin import (
    FrameAwareBase,
    ScaledCanvas,
    is_scaled,
    unwrap_to_real,
)

from led_ticker_flair.flair._raster import Raster, snapshot_into
from led_ticker_flair.flair.accordion_cards import (
    Plan,
    build_decks,
    is_image_widget,
)

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


class DeckSnapshotMixin:
    """Owns the scratch rasters and ``_plan``. Hosts call
    ``_init_deck_snapshot(mirror)`` from ``__init__``."""

    _mirror: bool

    def _init_deck_snapshot(self, mirror: bool) -> None:
        self._mirror = mirror
        # Scratch rasters (outgoing, incoming, border-only, top-only,
        # bottom-only), reused across frames/firings while the geometry key
        # matches. Re-keying never touches a plan already built.
        self._rasters: list[Raster | None] = [None] * 5
        self._raster_key: tuple[int, int, int, int | None] | None = None

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
