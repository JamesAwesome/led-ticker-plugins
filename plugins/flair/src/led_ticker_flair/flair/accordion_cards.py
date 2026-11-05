"""flair.accordion — pure data layer: split a widget snapshot into cards
(maximal runs of lit columns), per-band decks, and the border ring that
stays put. No canvas drawing here."""

import inspect
from collections.abc import Container, Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple

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


class Plan(NamedTuple):
    """Everything one widget's phase paints, in real coordinates."""

    decks: list[Deck]
    ring: list[Pixel]  # static border ring, painted AFTER the cards
    under: list[Pixel]  # border pixels the content covered: painted BEFORE


def segment_cards(
    raster: Raster,
    rows: range,
    cols: range,
    *,
    mirror: bool,
    exclude: Container[tuple[int, int]] | None = None,
) -> list[Card]:
    """A card is a maximal run of columns with >=1 lit pixel in ``rows``.
    ``exclude`` holds raster ``(x, y)`` positions that are not content (the
    exact border ring)."""
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
                if exclude is not None and (src, y) in exclude:
                    continue
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


def merge_cards(cards: Sequence[Card]) -> list[Card]:
    """Fuse a band's cards into ONE card spanning the band's lit extent
    (gaps stay blank inside it). Empty in, empty out."""
    if len(cards) < 2:
        return list(cards)
    first = cards[0]
    end = max(c.slot + c.width for c in cards)
    pixels = tuple(
        (dx + c.slot - first.slot, y, rgb) for c in cards for dx, y, rgb in c.pixels
    )
    return [Card(slot=first.slot, width=end - first.slot, pixels=pixels)]


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


def _unlit_row_split(
    raster: Raster,
    lo: int,
    hi: int,
    nominal: int,
    window: int,
    cols: range,
    exclude: Container[tuple[int, int]] | None,
) -> int:
    """The row in ``[lo, hi)`` within ``window`` of ``nominal`` that has no
    lit content pixel, nearest first (the upper row wins a tie), else
    ``nominal``. Splitting there keeps a glyph that straddles the nominal
    boundary whole in one deck."""

    def blank(y: int) -> bool:
        for x in cols:
            px = raster.get(x, y)
            if is_lit(px) and (exclude is None or (x, y) not in exclude):
                return False
        return True

    for d in range(window + 1):
        for y in (nominal - d, nominal + d):
            if lo < y < hi and blank(y):
                return y
    return nominal


def band_rows(
    widget: Any,
    canvas: Any,
    real_h: int,
    depth: int,
    *,
    raster: Raster | None = None,
    cols: range | None = None,
    exclude: Container[tuple[int, int]] | None = None,
) -> list[range]:
    if not getattr(widget, "bottom_text", ""):
        return [range(depth, real_h - depth)]
    scaled = is_scaled(canvas)
    content_h = canvas.content_height if scaled else real_h
    scale = canvas.scale if scaled else 1
    y_off = canvas.y_offset_real if scaled else 0
    top_h, _ = resolve_band_heights(content_h, getattr(widget, "top_row_height", None))
    boundary = y_off + top_h * scale
    if raster is not None and cols is not None:
        # A glyph can cross the nominal boundary (a text_y_offset nudge, a
        # descender): split at the nearest fully-unlit row instead.
        boundary = _unlit_row_split(
            raster,
            depth,
            real_h - depth,
            boundary,
            max(1, top_h * scale // 4),
            cols,
            exclude,
        )
    return [range(depth, boundary), range(boundary, real_h - depth)]


def is_image_widget(widget: Any) -> bool:
    """Core ``gif`` / ``image`` widgets (duck-typed: an async ``play`` plus a
    ``_paint_full`` hook, the ``_BaseImageWidget`` shape; nothing on the
    plugin surface names the class). Their ``draw()`` — the transition
    compositing path — paints ONLY the picture: no border, no text overlay.
    So neither a ring nor a row split exists in their snapshot."""
    play = getattr(widget, "play", None)
    return inspect.iscoroutinefunction(play) and callable(
        getattr(widget, "_paint_full", None)
    )


# A border-only render is trusted only when at least this share of its lit
# pixels shows up, colour-exact, in the snapshot. Content can cover part of
# the ring; a render that mostly misses means the widget didn't paint this
# border this way (a different frame, a different host), so fall back.
_RING_MATCH_MIN = 0.5


def exact_ring(
    raster: Raster, border_only: Raster
) -> tuple[list[Pixel], list[Pixel]] | None:
    """Split the snapshot's border pixels using a render of the border ALONE.

    A snapshot pixel is ring only where it equals the border-only render;
    any other lit pixel (text overlapping the ring, a background showing
    through bulb gaps) is content and goes to the cards. Where content
    covered the border, the border-only colour is returned as ``under`` so
    the ring has no hole once the card moves away. ``None`` -> the render
    can't be trusted (nothing lit, or too little of it matches)."""
    ring: list[Pixel] = []
    under: list[Pixel] = []
    n_lit = 0
    for y in range(raster.height):
        for x in range(raster.width):
            b = border_only.get(x, y)
            if not is_lit(b) or b is None:
                continue
            n_lit += 1
            px = raster.get(x, y)
            if px == b:
                ring.append((x, y, b))
            elif is_lit(px):
                under.append((x, y, b))
    if n_lit == 0 or len(ring) < _RING_MATCH_MIN * n_lit:
        return None
    return ring, under


def build_decks(
    raster: Raster,
    widget: Any,
    canvas: Any,
    *,
    mirror: bool,
    border_only: Raster | None = None,
) -> Plan:
    """Split a snapshot into decks + ring. ``border_only`` is the widget's
    border painted alone (same frame, same wrapper) when the caller could
    render it: it gives the exact ring. Without it, the depth-based ring
    (``ring_depth``) is the fallback."""
    scale = canvas.scale if is_scaled(canvas) else 1
    w, h = raster.width, raster.height
    if is_image_widget(widget):
        # The picture slides as one deck; nothing in it is a ring or a row.
        cards = segment_cards(raster, range(h), range(w), mirror=mirror)
        return Plan([Deck(tuple(cards), effective_peek(cards, 2 * scale))], [], [])
    exact = None
    if border_only is not None and getattr(widget, "border", None) is not None:
        exact = exact_ring(raster, border_only)
    exclude: set[tuple[int, int]] | None = None
    if exact is not None:
        ring, under = exact
        exclude = {(x, y) for x, y, _ in ring}
        depth = 0  # content anywhere, including the ring zone, is a card
    else:
        depth = ring_depth(widget, raster)
        ring, under = ring_pixels(raster, depth), []
    cols = range(depth, w - depth)
    # A background effect (sparse streaks/spokes bridging the glyphs) has no
    # gaps worth fanning, and a per-row split would shear the rows apart
    # under sweep: one band over the whole content area, merged to ONE card.
    has_background = getattr(widget, "background", None) is not None
    if has_background:
        bands = [range(depth, h - depth)]
    else:
        bands = band_rows(
            widget, canvas, h, depth, raster=raster, cols=cols, exclude=exclude
        )
    decks: list[Deck] = []
    for rows in bands:
        cards = segment_cards(raster, rows, cols, mirror=mirror, exclude=exclude)
        if has_background:
            cards = merge_cards(cards)
        decks.append(Deck(cards=tuple(cards), peek=effective_peek(cards, 2 * scale)))
    return Plan(decks, ring, under)
