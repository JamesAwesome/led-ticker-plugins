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


def cards_from_pixels(
    raster: Raster,
    pixels: set[tuple[int, int]],
    cols: range,
    *,
    mirror: bool,
) -> list[Card]:
    """``segment_cards`` over an explicit pixel set (raster ``(x, y)``, all
    lit content) instead of a row range: a card is a maximal run of columns
    holding >=1 of ``pixels``. Same card shape and pixel order."""
    w = raster.width
    by_col: dict[int, list[int]] = {}
    for x, y in pixels:
        by_col.setdefault(x, []).append(y)
    cards: list[Card] = []
    start: int | None = None
    run: list[tuple[int, int, tuple[int, int, int]]] = []
    last = -1
    get = raster.get
    for c in cols:
        src = w - 1 - c if mirror else c
        ys = by_col.get(src)
        if ys:
            if start is None:
                start = c
            run.extend((c, y, px) for y in sorted(ys) if (px := get(src, y)))
            last = c
        elif start is not None:
            cards.append(_card(start, last, run))
            start, run = None, []
    if start is not None:
        cards.append(_card(start, last, run))
    return cards


def _card(
    start: int, last: int, run: list[tuple[int, int, tuple[int, int, int]]]
) -> Card:
    return Card(
        slot=start,
        width=last - start + 1,
        pixels=tuple((c - start, y, rgb) for c, y, rgb in run),
    )


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


def _components(
    raster: Raster,
    rows: range,
    cols: range,
    exclude: Container[tuple[int, int]] | None,
) -> list[list[tuple[int, int]]]:
    """8-connected components of the lit content pixels in ``rows`` x
    ``cols`` (raster coords), skipping ``exclude`` (the exact border ring)."""
    get = raster.get
    lit: set[tuple[int, int]] = set()
    for y in rows:
        for x in cols:
            if is_lit(get(x, y)) and (exclude is None or (x, y) not in exclude):
                lit.add((x, y))
    comps: list[list[tuple[int, int]]] = []
    while lit:
        seed = lit.pop()
        comp = [seed]
        stack = [seed]
        while stack:
            x, y = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    n = (x + dx, y + dy)
                    if n in lit:
                        lit.remove(n)
                        comp.append(n)
                        stack.append(n)
        comps.append(comp)
    return comps


class _Piece:
    """A connected run of content pixels: rows spanned, and each column's
    top/bottom row."""

    __slots__ = ("col_span", "pixels", "y0", "y1")

    def __init__(self, pixels: list[tuple[int, int]]) -> None:
        self.pixels = pixels
        span: dict[int, tuple[int, int]] = {}
        for x, y in pixels:
            lo_hi = span.get(x)
            span[x] = (y, y) if lo_hi is None else (min(lo_hi[0], y), max(lo_hi[1], y))
        self.col_span = span
        self.y0 = min(a for a, _b in span.values())
        self.y1 = max(b for _a, b in span.values())

    def height(self) -> int:
        return self.y1 - self.y0 + 1

    def gap_to(self, other: _Piece) -> int | None:
        """Fewest blank rows between the two pieces within a column they
        share (0 when they touch or interleave), else ``None``."""
        best: int | None = None
        a, b = self.col_span, other.col_span
        if len(b) < len(a):
            a, b = b, a
        for x, (lo, hi) in a.items():
            o = b.get(x)
            if o is None:
                continue
            d = max(o[0] - hi, lo - o[1], 1) - 1
            if best is None or d < best:
                best = d
        return best


def assign_bands(
    raster: Raster,
    rows: range,
    cols: range,
    boundary: int,
    small: int,
    exclude: Container[tuple[int, int]] | None = None,
    pull: tuple[int, int] = (0, 0),
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    """Split a two-row snapshot's content pixels into (top, bottom) sets so
    no glyph is cut across decks. ``exclude`` (the exact ring) is never
    content. "Small" = at most ``small`` rows tall (``_small_height``);
    "near" = at most ``max(1, small // 2)`` blank rows apart within a shared
    column (an i dot sits 1 logical row over its stem).

    A glyph is an 8-connected component of lit pixels. It goes WHOLE to the
    band holding the majority of its pixels relative to the nominal
    ``boundary`` (the upper band wins a tie), so a descender or a
    ``text_y_offset`` nudge that crosses the boundary stays with its glyph.
    Components are labelled per nominal half first, then joined where they
    touch across the boundary, except:

    - two LARGE pieces that touch are two rows' glyphs (a descender grazing
      a capital): each keeps its own half, as the nominal split did, and so
      does every piece of a chain of small pieces bridging two such glyphs;
    - a small piece near another piece of its own half (a dot over its
      stem, a colon's other dot, a "!" bar) is a mark of its own row even
      where it touches a glyph across the boundary, unless the other row's
      text is nudged further toward the boundary (``pull``, logical rows
      toward it, top then bottom): then it is that row's descender tip.

    A small DETACHED component (an i/j dot, an accent, a colon dot) has a
    majority that says nothing about its glyph. When it is not near a piece
    of its own half, it inherits the band of the nearest LARGE component
    sharing a column with it, searching up and down within "near". No such
    neighbour, or a tie between neighbours in different bands, leaves it to
    its own majority."""
    lo, hi = rows.start, rows.stop
    near = max(1, small // 2)
    halves = (range(lo, min(boundary, hi)), range(max(boundary, lo), hi))
    pieces: list[_Piece] = []
    side: list[int] = []
    owner: dict[tuple[int, int], int] = {}
    for half, half_rows in enumerate(halves):
        for comp in _components(raster, half_rows, cols, exclude):
            for p in comp:
                owner[p] = len(pieces)
            pieces.append(_Piece(comp))
            side.append(half)
    n = len(pieces)
    large = [p.height() > small for p in pieces]

    def has_own_neighbour(i: int) -> bool:
        """Small piece ``i`` is near another piece of its own half."""
        pi = pieces[i]
        for j in range(n):
            if j == i or side[j] != side[i]:
                continue
            d = pi.gap_to(pieces[j])
            if d is not None and d <= near:
                return True
        return False

    homed = [not large[i] and has_own_neighbour(i) for i in range(n)]
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def may_join(i: int) -> bool:
        # A homed piece crosses only when the OTHER row pulls harder.
        return not homed[i] or pull[1 - side[i]] > pull[side[i]]

    for x in cols:
        a = owner.get((x, boundary - 1))
        if a is None:
            continue
        for dx in (-1, 0, 1):
            b = owner.get((x + dx, boundary))
            if (
                b is not None
                and not (large[a] and large[b])
                and may_join(a)
                and may_join(b)
            ):
                parent[find(a)] = find(b)
    members: dict[int, list[int]] = {}
    for i in range(n):
        members.setdefault(find(i), []).append(i)

    groups: list[tuple[_Piece, int, bool]] = []  # (piece, band, homed)
    for ids in members.values():
        if {side[i] for i in ids if large[i]} == {0, 1}:
            # Small pieces chained between both rows' large glyphs: keep
            # every piece in its own half (the nominal split) for this group.
            groups.extend((pieces[i], side[i], homed[i]) for i in ids)
            continue
        g = (
            pieces[ids[0]]
            if len(ids) == 1
            else _Piece([p for i in ids for p in pieces[i].pixels])
        )
        n_top = sum(1 for _x, y in g.pixels if y < boundary)
        band = 0 if 2 * n_top >= len(g.pixels) else 1
        groups.append((g, band, any(homed[i] for i in ids)))

    top: set[tuple[int, int]] = set()
    bottom: set[tuple[int, int]] = set()
    big = [(o, o_band) for o, o_band, _h in groups if o.height() > small]
    for g, band, is_homed in groups:
        if g.height() <= small and not is_homed:
            best: int | None = None
            bands: set[int] = set()
            for o, o_band in big:
                d = g.gap_to(o)
                if d is None or d > near:
                    continue
                if best is None or d < best:
                    best, bands = d, set()
                if d == best:
                    bands.add(o_band)
            if len(bands) == 1:
                band = bands.pop()
        (top if band == 0 else bottom).update(g.pixels)
    return top, bottom


def band_rows(widget: Any, canvas: Any, real_h: int, depth: int) -> list[range]:
    """The NOMINAL band rows: one band, or a two-row widget's two bands split
    at the top band's height. ``build_decks`` refines the two-row split per
    component (``assign_bands``)."""
    if not getattr(widget, "bottom_text", ""):
        return [range(depth, real_h - depth)]
    scaled = is_scaled(canvas)
    content_h = canvas.content_height if scaled else real_h
    scale = canvas.scale if scaled else 1
    y_off = canvas.y_offset_real if scaled else 0
    top_h, _ = resolve_band_heights(content_h, getattr(widget, "top_row_height", None))
    boundary = y_off + top_h * scale
    return [range(depth, boundary), range(boundary, real_h - depth)]


def _row_pull(widget: Any) -> tuple[int, int]:
    """How far each row's text is nudged TOWARD the band boundary (logical
    rows): ``top_text_y_offset`` down, ``bottom_text_y_offset`` up. Non-int
    or missing -> 0."""

    def off(name: str) -> int:
        v = getattr(widget, name, 0)
        return v if isinstance(v, int) and not isinstance(v, bool) else 0

    return off("top_text_y_offset"), -off("bottom_text_y_offset")


def _small_height(widget: Any, canvas: Any, real_h: int) -> int:
    """Tallest component (real rows) that counts as a detached mark: a
    quarter of the shorter band, at least 1. That is 2 rows on the smallsign
    (an i dot or accent is 1) and 8 real rows on the bigsign (a scaled dot
    is 4); a letter stem or a crossing descender's glyph is far taller."""
    scaled = is_scaled(canvas)
    content_h = canvas.content_height if scaled else real_h
    scale = canvas.scale if scaled else 1
    heights = resolve_band_heights(content_h, getattr(widget, "top_row_height", None))
    return max(1, min(heights) * scale // 4)


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
        bands = band_rows(widget, canvas, h, depth)
    if len(bands) == 2:
        # Two rows split per glyph, not per pixel row: each band's cards are
        # segmented from the pixels ``assign_bands`` gave it.
        owned = assign_bands(
            raster,
            range(depth, h - depth),
            cols,
            bands[1].start,
            _small_height(widget, canvas, h),
            exclude,
            pull=_row_pull(widget),
        )
        band_cards = [cards_from_pixels(raster, o, cols, mirror=mirror) for o in owned]
    else:
        band_cards = [
            segment_cards(raster, rows, cols, mirror=mirror, exclude=exclude)
            for rows in bands
        ]
    decks: list[Deck] = []
    for cards in band_cards:
        if has_background:
            cards = merge_cards(cards)
        decks.append(Deck(cards=tuple(cards), peek=effective_peek(cards, 2 * scale)))
    return Plan(decks, ring, under)
