"""flair.laser — a content-coloured beam reaches in from one panel edge,
erases the outgoing content pixel by pixel in a back-and-forth raster, then
writes the incoming content the same way. The "laser" display-entry effect
of commercial LED message signs.

Spec: docs/superpowers/specs/2026-10-28-flair-laser-transition-design.md

Design in one breath: each widget is snapshotted ONCE per firing into a
plugin-local readable raster (`_Raster`) at physical resolution; the lit
pixels are ordered by `raster_order` (origin edge first, boustrophedon,
empty lines skipped); `frame_at` maps `t` to a visited-pixel count and
paints unvisited outgoing pixels (erase) or visited incoming pixels
(write), plus a one-real-pixel beam from the origin edge to the head.
"""

import random
from typing import Any

from led_ticker.plugin import (
    SNAP_THRESHOLD,
    Canvas,
    ScaledCanvas,
    is_scaled,
    snap_reset,
    unwrap_to_real,
)

Pixel = tuple[int, int, tuple[int, int, int]]  # (x, y, (r, g, b))

_ORIGINS = ("top", "bottom", "left", "right")
_BLACK = (0, 0, 0)


class _Raster:
    """Minimal readable canvas with real-canvas write semantics.

    Out-of-bounds writes are silently ignored (same as the hardware
    canvas). Slots start as ``None`` (unset); ``Clear()`` resets them.
    ``SetImage`` exists because `gif` / `image` / `still` widgets paint via
    ``unwrap_to_real(canvas).SetImage(pil_image, x, y)`` — a snapshot
    target without it raises inside the breaker-guarded draw and TRIPS
    the widget. Alpha-0 pixels flatten to black, mirroring the production
    ``SetImage`` path.
    """

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._pixels: list[tuple[int, int, int] | None] = [None] * (width * height)

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802 - canvas API
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[y * self.width + x] = (r, g, b)

    def SubFill(  # noqa: N802 - canvas API
        self, x: int, y: int, w: int, h: int, r: int, g: int, b: int
    ) -> None:
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        pixel = (r, g, b)
        for yy in range(y0, y1):
            row = yy * self.width
            for xx in range(x0, x1):
                self._pixels[row + xx] = pixel

    def Clear(self) -> None:  # noqa: N802 - canvas API
        self._pixels = [None] * (self.width * self.height)

    def Fill(self, r: int, g: int, b: int) -> None:  # noqa: N802 - canvas API
        self._pixels = [(r, g, b)] * (self.width * self.height)

    def SetImage(  # noqa: N802 - canvas API
        self, image: Any, offset_x: int = 0, offset_y: int = 0
    ) -> None:
        pixels = image.load()
        w, h = image.size
        for y in range(h):
            for x in range(w):
                px = pixels[x, y]
                if len(px) == 4 and px[3] == 0:
                    r, g, b = 0, 0, 0
                else:
                    r, g, b = px[0], px[1], px[2]
                self.SetPixel(offset_x + x, offset_y + y, r, g, b)

    def get(self, x: int, y: int) -> tuple[int, int, int] | None:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._pixels[y * self.width + x]
        return None


def _is_lit(px: tuple[int, int, int] | None) -> bool:
    """Set and not pure black. The section ``bg_color`` is painted by the
    ENGINE, never by the widget, so it never reaches a snapshot; black is
    excluded so gif pillars / image letterbox fills aren't lasered."""
    return px is not None and px != _BLACK


def raster_order(
    raster: _Raster,
    origin: str,
    forward_first: bool = True,
    across: range | None = None,
) -> tuple[list[Pixel], bool]:
    """Lit pixels of ``raster`` in beam-visit order, plus the parity the
    NEXT phase should start with.

    Lines are physical rows (``top``/``bottom``) or columns
    (``left``/``right``); the first line is the one nearest the origin
    edge. Within a line the head runs forward (ascending) or backward,
    flipping after every line that contributed at least one pixel —
    empty lines are skipped without flipping (no frames spent on them).
    """
    if origin not in _ORIGINS:
        raise ValueError(f"origin must be one of {_ORIGINS}; got {origin!r}")
    w, h = raster.width, raster.height
    by_rows = origin in ("top", "bottom")
    if origin == "top":
        lines: range = range(h)
    elif origin == "bottom":
        lines = range(h - 1, -1, -1)
    elif origin == "left":
        lines = range(w)
    else:
        lines = range(w - 1, -1, -1)
    if across is None:
        across = range(w) if by_rows else range(h)

    out: list[Pixel] = []
    forward = forward_first
    get = raster.get
    for line in lines:
        hits: list[Pixel] = []
        for k in across:
            x, y = (k, line) if by_rows else (line, k)
            px = get(x, y)
            if _is_lit(px):
                hits.append((x, y, px))  # type: ignore[arg-type]
        if not hits:
            continue
        if not forward:
            hits.reverse()
        out.extend(hits)
        forward = not forward
    return out, forward


_DEFAULT_BEAMS = 3


def _coerce_beams(beams: Any) -> int:
    if isinstance(beams, bool) or not isinstance(beams, int) or beams < 1:
        raise ValueError(f"beams must be a positive int; got {beams!r}")
    return beams


def _lit_extent(raster: _Raster, vertical: bool) -> tuple[int, int] | None:
    """[lo, hi) of lit pixels along the across axis (x for vertical beams,
    y for horizontal), or None when nothing is lit."""
    lo, hi = None, None
    get = raster.get
    for y in range(raster.height):
        for x in range(raster.width):
            if _is_lit(get(x, y)):
                k = x if vertical else y
                lo = k if lo is None or k < lo else lo
                hi = k if hi is None or k > hi else hi
    return None if lo is None or hi is None else (lo, hi + 1)


def _spans(out_r: _Raster, in_r: _Raster, origin: str, n: int) -> list[range]:
    """Split the lit CONTENT extent along the across axis (width for
    top/bottom, height for left/right) into ``n`` near-equal contiguous
    spans, one per beam — so a centred headline gets all ``n`` beams, not
    just the one whose panel-width slice it happens to sit in."""
    vertical = origin in ("top", "bottom")
    ext = [e for e in (_lit_extent(out_r, vertical), _lit_extent(in_r, vertical)) if e]
    if not ext:
        return [range(0)]
    lo = min(e[0] for e in ext)
    hi = max(e[1] for e in ext)
    n = max(1, min(n, hi - lo))
    edges = [lo + round(k * (hi - lo) / n) for k in range(n + 1)]
    return [range(edges[k], edges[k + 1]) for k in range(n)]


class Laser:
    """Beam from the ``_origin`` edge erases the outgoing content pixel by
    pixel, then writes the incoming content the same way.

    Erase (first ``n_out`` visits): paint every NOT-yet-visited outgoing
    snapshot pixel in its own colour; erased pixels simply stop being
    painted, so the runner's ``Fill(outgoing_bg)`` shows through. Write
    (remaining ``n_in`` visits): ``snap_reset`` to the incoming bg, paint
    every visited incoming pixel in its snapshot colour. Both phases draw
    a one-real-pixel beam from the origin edge to the head pixel, in the
    head's colour. ``beams`` (default 3) splits the lit content extent into
    that many equal slices, each with its own independent beam; the bg
    cuts over to the incoming section the moment the first beam starts
    writing. Snapshots are taken ONCE per firing (refire detected
    by ``t < _last_t``); the outgoing is never drawn live after that —
    a live draw can drift from the snapshot over a ≥2.4 s transition.
    """

    min_frames = 48
    scale_switch_at = 1.0  # hard-edged family convention
    _origin = "top"

    def __init__(self, beams: Any = _DEFAULT_BEAMS) -> None:
        self.beams: int = _coerce_beams(beams)
        # tracks: parallel (out_pixels, in_pixels) pairs, one per beam
        self._tracks: list[tuple[list[Pixel], list[Pixel]]] | None = None
        self._last_t = 1.0
        self._rasters: list[_Raster | None] = [None, None]
        self._raster_key: tuple[int, int, int, int | None] | None = None

    # --- snapshot -------------------------------------------------------------

    def _snapshot(
        self, canvas: Any, widget: Any, cursor_pos: int, slot: int
    ) -> _Raster:
        """Draw ``widget`` once into a cleared physical-resolution raster,
        through a ScaledCanvas wrapper when the live canvas is scaled so
        the widget paints exactly as it would on the panel."""
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
            raster = _Raster(real.width, real.height)
            self._rasters[slot] = raster
        raster.Clear()
        target: Any = raster
        if scaled:
            target = ScaledCanvas(
                raster, scale=canvas.scale, content_height=canvas.content_height
            )
        widget.draw(target, cursor_pos=cursor_pos)
        return raster

    def _ensure_plan(self, canvas: Any, outgoing: Any, incoming: Any, pos: int) -> None:
        if self._tracks is not None:
            return
        out_r = self._snapshot(canvas, outgoing, pos, 0)
        in_r = self._snapshot(canvas, incoming, 0, 1)
        spans = _spans(out_r, in_r, self._origin, self.beams)
        tracks: list[tuple[list[Pixel], list[Pixel]]] = []
        for sp in spans:
            o, par = raster_order(out_r, self._origin, across=sp)
            i, _ = raster_order(in_r, self._origin, forward_first=par, across=sp)
            tracks.append((o, i))
        self._tracks = tracks

    # --- schedule -------------------------------------------------------------

    @property
    def _out(self) -> list[Pixel] | None:  # single-beam view (tests / debugging)
        return None if self._tracks is None else self._tracks[0][0]

    @property
    def _in(self) -> list[Pixel] | None:
        return None if self._tracks is None else self._tracks[0][1]

    @staticmethod
    def _visited_of(n: int, t: float) -> int:
        """Pixels of an ``n``-pixel track visited at progress ``t``:
        constant speed in lit pixels, all visited at ``SNAP_THRESHOLD``."""
        if t >= SNAP_THRESHOLD:
            return n
        return int(n * t / SNAP_THRESHOLD)

    def _visited(self, t: float) -> int:
        assert self._tracks is not None
        o, i = self._tracks[0]
        return self._visited_of(len(o) + len(i), t)

    # --- paint ----------------------------------------------------------------

    def _draw_beam(self, real: Any, rw: int, rh: int, head: Pixel) -> None:
        hx, hy, (r, g, b) = head
        set_px = real.SetPixel
        if self._origin == "top":
            for y in range(0, hy + 1):
                set_px(hx, y, r, g, b)
        elif self._origin == "bottom":
            for y in range(hy, rh):
                set_px(hx, y, r, g, b)
        elif self._origin == "left":
            for x in range(0, hx + 1):
                set_px(x, hy, r, g, b)
        else:
            for x in range(hx, rw):
                set_px(x, hy, r, g, b)

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t < self._last_t:  # new firing -> fresh snapshots
            self._tracks = None
        self._last_t = t

        if t >= SNAP_THRESHOLD:
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
            incoming.draw(canvas, cursor_pos=0)
            return canvas

        pos = kwargs.get("outgoing_scroll_pos", 0)
        self._ensure_plan(canvas, outgoing, incoming, pos)
        assert self._tracks is not None
        # `real` is re-derived EVERY call, never cached (constraint #1).
        real = unwrap_to_real(canvas) if is_scaled(canvas) else canvas
        rw, rh = real.width, real.height
        set_px = real.SetPixel

        states = [(o, i, self._visited_of(len(o) + len(i), t)) for o, i in self._tracks]
        # The bg cuts over to the incoming section the moment ANY beam
        # starts writing (single beam: exactly at the erase/write boundary).
        if any(v > len(o) for o, _i, v in states):
            snap_reset(canvas, kwargs.get("incoming_bg_color"))
        heads: list[Pixel] = []
        for o, i, v in states:
            n_out = len(o)
            if v <= n_out:
                for k in range(v, n_out):
                    x, y, (r, g, b) = o[k]
                    set_px(x, y, r, g, b)
                if v > 0:
                    heads.append(o[v - 1])
            else:
                written = v - n_out
                for k in range(written):
                    x, y, (r, g, b) = i[k]
                    set_px(x, y, r, g, b)
                heads.append(i[written - 1])
        for head in heads:
            self._draw_beam(real, rw, rh, head)
        return canvas


class LaserBottom(Laser):
    """Beam reaches up from the bottom edge; rasters bottom row first."""

    _origin = "bottom"


class LaserLeft(Laser):
    """Beam reaches in from the left edge; rasters left column first."""

    _origin = "left"


class LaserRight(Laser):
    """Beam reaches in from the right edge; rasters right column first."""

    _origin = "right"


class _LaserMulti:
    """Shared shape for the alternating / random variants (FairyAlternating
    convention): a list of the four single-origin instances, ``_index``
    advanced on every new firing (``t < _last_t``), ``min_frames`` peeking
    the NEXT variant, ``frame_at`` delegated."""

    def __init__(self, beams: Any = _DEFAULT_BEAMS) -> None:
        self._transitions: list[Laser] = [
            Laser(beams=beams),
            LaserRight(beams=beams),
            LaserBottom(beams=beams),
            LaserLeft(beams=beams),
        ]
        self._index: int = -1
        self._last_t: float = 1.0

    def _next_index(self) -> int:
        raise NotImplementedError

    @property
    def min_frames(self) -> int:
        return self._transitions[0].min_frames

    def frame_at(
        self, t: float, canvas: Canvas, outgoing: Any, incoming: Any, **kwargs: Any
    ) -> Canvas:
        if t < self._last_t:
            self._index = self._next_index()
        self._last_t = t
        return self._transitions[self._index].frame_at(
            t, canvas, outgoing, incoming, **kwargs
        )


class LaserAlternating(_LaserMulti):
    """Cycles top -> right -> bottom -> left, one origin per firing."""

    def _next_index(self) -> int:
        return (self._index + 1) % len(self._transitions)


class LaserRandom(_LaserMulti):
    """Picks an origin per firing; never the same one back-to-back
    (WipeRandom policy). ``_rng`` is an instance attribute so tests can
    seed it."""

    def __init__(self, beams: Any = _DEFAULT_BEAMS) -> None:
        super().__init__(beams=beams)
        self._rng = random.Random()

    def _next_index(self) -> int:
        choices = [i for i in range(len(self._transitions)) if i != self._index]
        return self._rng.choice(choices)
