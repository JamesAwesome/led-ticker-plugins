"""flair.accordion — pure data layer: split a widget snapshot into cards
(maximal runs of lit columns), per-band decks, and the border ring that
stays put. No canvas drawing here."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from led_ticker.plugin import is_scaled, resolve_band_heights

from led_ticker_flair.flair._raster import Pixel, Raster, is_lit


@dataclass(frozen=True)
class Card:
    slot: int  # natural left column, real px (mirrored space if mirror)
    width: int
    pixels: tuple[tuple[int, int, tuple[int, int, int]], ...]  # (dx, y_real, rgb)


@dataclass(frozen=True)
class Deck:
    cards: tuple[Card, ...]  # natural left-to-right order
    peek: float  # P_eff


def segment_cards(
    raster: Raster, rows: range, cols: range, *, mirror: bool
) -> list[Card]:
    """A card is a maximal run of columns with >=1 lit pixel in ``rows``."""
    w = raster.width
    cards: list[Card] = []
    start: int | None = None
    run: list[tuple[int, int, tuple[int, int, int]]] = []  # (col_idx, y, rgb)
    last = -1

    def flush() -> None:
        nonlocal start, run
        if start is not None:
            cards.append(
                Card(
                    slot=start,
                    width=last - start + 1,
                    pixels=tuple((c - start, y, rgb) for c, y, rgb in run),
                )
            )
        start = None
        run = []

    for c in cols:
        src = w - 1 - c if mirror else c
        col_px = []
        for y in rows:
            px = raster.get(src, y)
            if is_lit(px) and px is not None:
                col_px.append((c, y, px))
        if col_px:
            if start is None:
                start = c
            run.extend(col_px)
            last = c
        else:
            flush()
    flush()
    return cards


def effective_peek(cards: Sequence[Card], peek: int) -> float:
    """Cap the peek to the average slot spacing so a dense deck never
    overlaps more than it spaces."""
    if len(cards) < 2:
        return float(peek)
    avg = (cards[-1].slot - cards[0].slot) / (len(cards) - 1)
    return min(float(peek), avg)


# Measured-ring fallback: a depth layer counts as ring only when EACH of its
# four edge lines is at least this lit. Sparse enough for LightbulbBorder's
# 1x1 bulbs at gap 3 (~25% of an edge), and the all-four-edges requirement is
# what keeps text / images touching one or two edges from reading as a ring.
_RING_EDGE_COVERAGE = 0.2


def _int_attr(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _lightbulb_depth(border: Any, real_h: int) -> int | None:
    """Exact depth for core ``LightbulbBorder`` (duck-typed: ``gap`` plus a
    ``_resolve_bulb_size(real_height)`` resolver): every bulb is an N x N
    square flush with the panel edge, so the ring is N deep. Delegating to
    the border's own resolver keeps the auto rule (1 on short panels, 3 on
    tall) in ONE place. Exact even when ``unlit_color`` is black, where a
    chase ring is too sparse to measure. ``None`` -> not a lightbulb."""
    resolve = getattr(border, "_resolve_bulb_size", None)
    if _int_attr(getattr(border, "gap", None)) is None or not callable(resolve):
        return None
    try:
        return _int_attr(resolve(real_h))
    except Exception:  # never let a duck-type probe break a transition
        return None


def _measured_depth(raster: Raster) -> int:
    """Count ring layers inward from the panel edge. Layer ``d`` is ring iff
    its top row, bottom row, left column and right column (each spanning
    the layer's own extent) are ALL >= ``_RING_EDGE_COVERAGE`` lit."""
    w, h = raster.width, raster.height
    get = raster.get

    def covered(n_lit: int, n: int) -> bool:
        return n > 0 and n_lit >= _RING_EDGE_COVERAGE * n

    depth = 0
    for d in range(h // 4):
        xs = range(d, w - d)
        ys = range(d, h - d)
        if not (
            covered(sum(1 for x in xs if is_lit(get(x, d))), len(xs))
            and covered(sum(1 for x in xs if is_lit(get(x, h - 1 - d))), len(xs))
            and covered(sum(1 for y in ys if is_lit(get(d, y))), len(ys))
            and covered(sum(1 for y in ys if is_lit(get(w - 1 - d, y))), len(ys))
        ):
            break
        depth += 1
    return depth


def ring_depth(widget: Any, raster: Raster) -> int:
    """Depth (real px) of the border ring that stays put. Order: an int
    ``thickness`` (core ring borders), then the lightbulb shape, then the
    measured four-edge fallback for unknown shapes."""
    border = getattr(widget, "border", None)
    if border is None:
        return 0
    thickness = _int_attr(getattr(border, "thickness", None))
    if thickness is not None:
        return thickness
    bulb = _lightbulb_depth(border, raster.height)
    if bulb is not None:
        return bulb
    return _measured_depth(raster)


def ring_pixels(raster: Raster, depth: int) -> list[Pixel]:
    if depth <= 0:
        return []
    out: list[Pixel] = []
    w, h = raster.width, raster.height
    for y in range(h):
        edge_y = y < depth or y >= h - depth
        for x in range(w):
            if edge_y or x < depth or x >= w - depth:
                px = raster.get(x, y)
                if is_lit(px) and px is not None:
                    out.append((x, y, px))
    return out


def band_rows(widget: Any, canvas: Any, real_h: int, depth: int) -> list[range]:
    if not getattr(widget, "bottom_text", ""):
        return [range(depth, real_h - depth)]
    scaled = is_scaled(canvas)
    content_h = canvas.content_height if scaled else real_h
    scale = canvas.scale if scaled else 1
    y_off = canvas.y_offset_real if scaled else 0
    top_h, _ = resolve_band_heights(content_h, getattr(widget, "top_row_height", None))
    boundary = y_off + top_h * scale
    return [range(depth, boundary), range(boundary, real_h - depth)]


def build_decks(
    raster: Raster, widget: Any, canvas: Any, *, mirror: bool
) -> tuple[list[Deck], list[Pixel]]:
    depth = ring_depth(widget, raster)
    ring = ring_pixels(raster, depth)
    scale = canvas.scale if is_scaled(canvas) else 1
    cols = range(depth, raster.width - depth)
    decks: list[Deck] = []
    for rows in band_rows(widget, canvas, raster.height, depth):
        cards = segment_cards(raster, rows, cols, mirror=mirror)
        decks.append(Deck(cards=tuple(cards), peek=effective_peek(cards, 2 * scale)))
    return decks, ring
