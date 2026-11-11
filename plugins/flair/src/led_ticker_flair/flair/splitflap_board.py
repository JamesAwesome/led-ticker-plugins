"""flair.splitflap — pure data layer: pair two widgets' accordion decks
into a board of flaps (band pairs, per-flap flip sequences, hinges). No
canvas drawing here.

Spec: docs/superpowers/specs/2026-11-10-flair-splitflap-transition-design.md
"""

import math
import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field

from led_ticker_flair.flair._raster import Pixel
from led_ticker_flair.flair.accordion_cards import Card, Deck, Plan

RGB = tuple[int, int, int]
Row = tuple[tuple[int, RGB], ...]  # ((dx, rgb), ...) for one real row


GlyphKey = tuple[int, tuple[tuple[int, Row], ...]]


def _glyph_key(width: int, rows: dict[int, Row]) -> GlyphKey:
    return (width, tuple(sorted(rows.items())))


@dataclass(frozen=True)
class FlapCell:
    """One character (or strip) at its home column ``slot``: its lit pixels
    grouped by real row, ``y -> ((dx, rgb), ...)``. ``key`` is the glyph
    identity (position-free), computed ONCE: the pool scan compares it for
    every candidate, and rebuilding it there made the board build
    quadratic in deep-tuple work (seconds on a full-panel gif)."""

    slot: int
    width: int
    rows: dict[int, Row]
    key: GlyphKey = field(compare=False, repr=False)

    @classmethod
    def make(cls, slot: int, width: int, rows: dict[int, Row]) -> FlapCell:
        return cls(slot, width, rows, _glyph_key(width, rows))

    @classmethod
    def from_card(cls, card: Card) -> FlapCell:
        by_row: dict[int, list[tuple[int, RGB]]] = {}
        for dx, y, rgb in card.pixels:
            by_row.setdefault(y, []).append((dx, rgb))
        return cls.make(card.slot, card.width, {y: tuple(v) for y, v in by_row.items()})

    def rows_key(self) -> GlyphKey:
        return self.key

    def centred_on(self, centre_x: int) -> FlapCell:
        return FlapCell(centre_x - self.width // 2, self.width, self.rows, self.key)


@dataclass(frozen=True)
class BandGeom:
    """Inclusive lit-row extent of a band pair and its hinge row (top half
    = rows ``< hinge``)."""

    lo: int
    hinge: int
    hi: int


@dataclass(frozen=True)
class Flap:
    band: int
    seq: tuple[FlapCell | None, ...]  # outgoing, in-betweens..., incoming
    static: bool
    centre_x: int


@dataclass(frozen=True)
class Board:
    bands: tuple[BandGeom, ...]
    flaps: tuple[Flap, ...]
    ring_out: tuple[Pixel, ...]
    under_out: tuple[Pixel, ...]
    ring_in: tuple[Pixel, ...]
    under_in: tuple[Pixel, ...]


def typical_width(cards: Sequence[Card], band_h: int) -> int:
    """Median width of the character-like cards (no wider than the band is
    tall); with none, half the band height. Floored at a quarter of the
    band height, so a picture with a few 1-px specks doesn't shred into
    hairline strips."""
    widths = [c.width for c in cards if c.width <= band_h]
    base = statistics.median_low(widths) if widths else band_h // 2
    return max(1, base, band_h // 4)


def split_wide(cards: Sequence[Card], cell_w: int) -> list[Card]:
    """Cut any card wider than ``2 * cell_w`` into near-equal strips of about
    ``cell_w`` columns (pixels partitioned by column)."""
    out: list[Card] = []
    for card in cards:
        if card.width <= 2 * cell_w:
            out.append(card)
            continue
        n = math.ceil(card.width / cell_w)
        bounds = [card.width * i // n for i in range(n + 1)]
        for a, b in zip(bounds, bounds[1:], strict=False):
            px = tuple((dx - a, y, rgb) for dx, y, rgb in card.pixels if a <= dx < b)
            out.append(Card(slot=card.slot + a, width=b - a, pixels=px))
    return out


def pair_bands(
    out_decks: Sequence[Deck], in_decks: Sequence[Deck]
) -> list[tuple[tuple[Card, ...], tuple[Card, ...]]]:
    """Pair bands by index; the side with fewer bands is padded with empty
    bands at the END, so a single band pairs with the top one."""
    n = max(len(out_decks), len(in_decks))
    o = [d.cards for d in out_decks] + [()] * (n - len(out_decks))
    i = [d.cards for d in in_decks] + [()] * (n - len(in_decks))
    return list(zip(o, i, strict=True))


def _lit_rows(cards: Sequence[Card]) -> list[int]:
    return [y for c in cards for _, y, _ in c.pixels]


def _band_geom(cards: Sequence[Card]) -> BandGeom | None:
    ys = _lit_rows(cards)
    if not ys:
        return None
    lo, hi = min(ys), max(ys)
    return BandGeom(lo, (lo + hi + 1) // 2, hi)


def _sequence(
    a: FlapCell | None,
    b: FlapCell | None,
    pool: list[FlapCell],
    flips: int,
    centre_x: int,
    rng: random.Random,
) -> tuple[FlapCell | None, ...]:
    own = {c.rows_key() for c in (a, b) if c is not None}
    candidates = [c for c in pool if c.rows_key() not in own]
    # In-betweens must fit the slot: a wide borrowed glyph (a "W" through an
    # "I") would spill onto the neighbours mid-clatter. Allow ~1.5x the
    # slot's own width; when nothing fits, the narrowest available.
    slot_w = max(c.width for c in (a, b) if c is not None)
    fit = [c for c in candidates if c.width <= slot_w + max(1, slot_w // 2)]
    if not fit and candidates:
        narrowest = min(c.width for c in candidates)
        fit = [c for c in candidates if c.width == narrowest]
    candidates = fit
    mid: list[FlapCell] = []
    prev = a.rows_key() if a is not None else None
    for _ in range(flips):
        choices = [c for c in candidates if c.rows_key() != prev]
        if not choices:
            break
        pick = rng.choice(choices)
        mid.append(pick.centred_on(centre_x))
        prev = pick.rows_key()
    return (a, *mid, b)


def _overlap(a: FlapCell, b: FlapCell) -> int:
    return min(a.slot + a.width, b.slot + b.width) - max(a.slot, b.slot)


def _centre(c: FlapCell) -> int:
    return c.slot + c.width // 2


def match_cells(
    outs: Sequence[FlapCell], ins: Sequence[FlapCell]
) -> list[tuple[FlapCell | None, FlapCell | None]]:
    """Pair cells by POSITION: greedily match the most-overlapping
    (outgoing, incoming) columns first (ties: nearest centres), each cell
    used once. Unmatched cells pair with blank, in place. Returned in
    left-to-right order of the pair's home (incoming, else outgoing).

    Index pairing (cell i <-> cell i) garbles centred messages of different
    lengths: their layouts start at different x, so each new glyph would
    flip over an old neighbour (visual gate, 2026-11-10)."""
    cands = sorted(
        (
            (-_overlap(a, b), abs(_centre(a) - _centre(b)), i, j)
            for i, a in enumerate(outs)
            for j, b in enumerate(ins)
            if _overlap(a, b) > 0
        )
    )
    used_o: set[int] = set()
    used_i: set[int] = set()
    pairs: list[tuple[FlapCell | None, FlapCell | None]] = []
    for _, _, i, j in cands:
        if i in used_o or j in used_i:
            continue
        used_o.add(i)
        used_i.add(j)
        pairs.append((outs[i], ins[j]))
    pairs += [(a, None) for i, a in enumerate(outs) if i not in used_o]
    pairs += [(None, b) for j, b in enumerate(ins) if j not in used_i]

    def key(p: tuple[FlapCell | None, FlapCell | None]) -> int:
        home = p[1] if p[1] is not None else p[0]
        assert home is not None
        return _centre(home)

    pairs.sort(key=key)
    return pairs


def build_board(out_plan: Plan, in_plan: Plan, flips: int, rng: random.Random) -> Board:
    bands: list[BandGeom] = []
    flaps: list[Flap] = []
    for out_cards, in_cards in pair_bands(out_plan.decks, in_plan.decks):
        geom = _band_geom([*out_cards, *in_cards])
        if geom is None:
            continue
        band = len(bands)
        bands.append(geom)
        cell_w = typical_width([*out_cards, *in_cards], geom.hi - geom.lo + 1)
        outs = [FlapCell.from_card(c) for c in split_wide(out_cards, cell_w)]
        ins = [FlapCell.from_card(c) for c in split_wide(in_cards, cell_w)]
        pool: list[FlapCell] = []
        seen: set[object] = set()
        for c in (*outs, *ins):
            k = c.rows_key()
            if k not in seen:
                seen.add(k)
                pool.append(c)
        for a, b in match_cells(outs, ins):
            home = b if b is not None else a
            assert home is not None
            centre = home.slot + home.width // 2
            static = (
                a is not None
                and b is not None
                and a.slot == b.slot
                and a.rows_key() == b.rows_key()
            )
            seq = (a, b) if static else _sequence(a, b, pool, flips, centre, rng)
            flaps.append(Flap(band, seq, static, centre))
    return Board(
        tuple(bands),
        tuple(flaps),
        tuple(out_plan.ring),
        tuple(out_plan.under),
        tuple(in_plan.ring),
        tuple(in_plan.under),
    )
