"""flair.splitflap — paint one character cell, or one flap between two
cells, about a band's hinge row. Pure: writes go through ``set_px`` and are
clipped to the panel.

Spec: docs/superpowers/specs/2026-11-10-flair-splitflap-transition-design.md
("One flap").
"""

from collections.abc import Callable

from led_ticker_flair.flair.splitflap_board import BandGeom, FlapCell

SetPx = Callable[[int, int, int, int, int], None]

FLAP_SHADE = 0.7  # flap brightness at its steepest (edge-on) moment


def flap_shade(q: float) -> float:
    """Brightness factor of the moving flap: 1.0 at both ends of the flip,
    ``FLAP_SHADE`` mid-flip, so the first and last frame of a flip show the
    plain glyph."""
    return 1.0 - (1.0 - FLAP_SHADE) * 4.0 * q * (1.0 - q)


def _paint_rows(
    set_px: SetPx, cell: FlapCell | None, y0: int, y1: int, w: int, h: int
) -> None:
    """Paint ``cell``'s own rows ``y0 <= y < y1`` in place."""
    if cell is None:
        return
    for y, row in cell.rows.items():
        if y0 <= y < y1 and 0 <= y < h:
            for dx, (r, g, b) in row:
                x = cell.slot + dx
                if 0 <= x < w:
                    set_px(x, y, r, g, b)


def _paint_mapped(
    set_px: SetPx,
    cell: FlapCell | None,
    dst0: int,
    fh: int,
    src0: int,
    src_h: int,
    factor: float,
    w: int,
    h: int,
) -> None:
    """Paint the flap: destination rows ``[dst0, dst0 + fh)`` sample the
    cell's source rows ``[src0, src0 + src_h)`` (nearest row), shaded."""
    if cell is None or fh <= 0:
        return
    for i in range(fh):
        y = dst0 + i
        if not 0 <= y < h:
            continue
        row = cell.rows.get(src0 + i * src_h // fh)
        if not row:
            continue
        for dx, (r, g, b) in row:
            x = cell.slot + dx
            if 0 <= x < w:
                set_px(x, y, round(r * factor), round(g * factor), round(b * factor))


def paint_cell(set_px: SetPx, cell: FlapCell | None, w: int, h: int) -> None:
    if cell is not None:
        _paint_rows(set_px, cell, -(1 << 30), 1 << 30, w, h)


def paint_flap(
    set_px: SetPx,
    a: FlapCell | None,
    b: FlapCell | None,
    band: BandGeom,
    q: float,
    w: int,
    h: int,
) -> None:
    """One flap from ``a`` to ``b`` at local progress ``q`` in [0, 1].

    q < 0.5: b's top shows above the falling flap (a's top half squashed
    toward the hinge); a's bottom below the hinge. q >= 0.5: b's top above
    the hinge; the flap (b's bottom half) unfolds down over a's bottom."""
    lo, hinge, hi = band.lo, band.hinge, band.hi
    top_h, bot_h = hinge - lo, hi + 1 - hinge
    factor = flap_shade(q)
    if q < 0.5:
        fh = round(top_h * (1.0 - 2.0 * q))
        _paint_rows(set_px, b, lo, hinge - fh, w, h)
        _paint_rows(set_px, a, hinge, hi + 1, w, h)
        _paint_mapped(set_px, a, hinge - fh, fh, lo, top_h, factor, w, h)
    else:
        fh = round(bot_h * (2.0 * q - 1.0))
        _paint_rows(set_px, b, lo, hinge, w, h)
        _paint_rows(set_px, a, hinge + fh, hi + 1, w, h)
        _paint_mapped(set_px, b, hinge, fh, hinge, bot_h, factor, w, h)
