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

from typing import Any

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
    raster: _Raster, origin: str, forward_first: bool = True
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
