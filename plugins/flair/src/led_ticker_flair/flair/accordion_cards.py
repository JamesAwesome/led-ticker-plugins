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
        return peek
    avg = (cards[-1].slot - cards[0].slot) / (len(cards) - 1)
    return min(float(peek), avg)


def ring_depth(widget: Any, raster: Raster) -> int:
    border = getattr(widget, "border", None)
    if border is None:
        return 0
    thickness = getattr(border, "thickness", None)
    if isinstance(thickness, int) and not isinstance(thickness, bool):
        return thickness
    depth = 0
    for y in range(raster.height // 4):
        lit = sum(1 for x in range(raster.width) if is_lit(raster.get(x, y)))
        if lit * 2 >= raster.width:
            depth += 1
        else:
            break
    return depth


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
