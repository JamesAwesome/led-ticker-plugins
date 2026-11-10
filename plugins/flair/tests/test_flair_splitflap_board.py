"""flair.splitflap — board data layer (pure, no canvas)."""

import random

from led_ticker_flair.flair.accordion_cards import Card, Deck, Plan
from led_ticker_flair.flair.splitflap_board import (
    BandGeom,
    FlapCell,
    build_board,
    pair_bands,
    split_wide,
    typical_width,
)

RED = (255, 0, 0)
GREEN = (0, 255, 0)


def _card(slot: int, width: int, rows: range, colour=RED) -> Card:
    return Card(
        slot=slot,
        width=width,
        pixels=tuple((dx, y, colour) for dx in range(width) for y in rows),
    )


def _plan(*bands: list[Card]) -> Plan:
    return Plan([Deck(tuple(b), 0.0) for b in bands], [], [])


def test_typical_width_median_of_glyph_like_cards():
    cards = [_card(0, w, range(1)) for w in (5, 6, 7, 40)]
    assert typical_width(cards, 10) == 6
    assert typical_width([_card(0, 40, range(1))], 10) == 5
    assert typical_width([], 1) == 1


def test_wide_card_split_into_strips():
    wide = _card(10, 64, range(4))
    strips = split_wide([wide, _card(80, 6, range(4))], 8)
    assert len(strips) == 9
    assert [s.slot for s in strips[:8]] == [10 + 8 * i for i in range(8)]
    seen = {(s.slot + dx, y) for s in strips[:8] for dx, y, _ in s.pixels}
    assert seen == {(10 + dx, y) for dx in range(64) for y in range(4)}
    assert sum(len(s.pixels) for s in strips[:8]) == 64 * 4
    assert strips[8].slot == 80 and strips[8].width == 6


def test_narrow_cards_unchanged_by_split():
    cards = [_card(0, 16, range(2))]
    assert split_wide(cards, 8) == cards


def test_pair_bands_pads_the_end():
    a = (_card(0, 4, range(2)),)
    b1 = (_card(0, 4, range(2)),)
    b2 = (_card(0, 4, range(5, 7)),)
    out = pair_bands([Deck(a, 0)], [Deck(b1, 0), Deck(b2, 0)])
    assert out == [(a, b1), ((), b2)]


def test_band_count_mismatch_pairs_top_and_blanks_extra():
    out = _plan([_card(x, 5, range(10, 20)) for x in (0, 8, 16)])
    inc = _plan(
        [_card(0, 5, range(2, 8)), _card(8, 5, range(2, 8))],
        [_card(0, 5, range(20, 26)), _card(8, 5, range(20, 26))],
    )
    board = build_board(out, inc, 3, random.Random(1))
    band0 = [f for f in board.flaps if f.band == 0]
    band1 = [f for f in board.flaps if f.band == 1]
    assert len(band0) == 3 and band0[2].seq[-1] is None
    assert len(band1) == 2 and all(f.seq[0] is None for f in band1)


def test_hinge_is_middle_of_union_of_lit_rows():
    out = _plan([_card(0, 5, range(10, 20))])
    inc = _plan([_card(0, 5, range(14, 26))])
    board = build_board(out, inc, 0, random.Random(0))
    assert board.bands[0] == BandGeom(lo=10, hinge=18, hi=25)


def test_identical_cells_are_static():
    c = _card(4, 5, range(0, 8))
    board = build_board(_plan([c]), _plan([c]), 3, random.Random(0))
    (flap,) = board.flaps
    assert flap.static is True
    assert len(flap.seq) == 2


def test_empty_outgoing_flips_from_blank():
    inc = _plan([_card(0, 5, range(0, 8)), _card(8, 5, range(0, 8))])
    board = build_board(_plan(), inc, 3, random.Random(0))
    assert len(board.flaps) == 2
    assert all(f.seq[0] is None and f.seq[-1] is not None for f in board.flaps)
    board = build_board(_plan(), _plan(), 3, random.Random(0))
    assert board.flaps == ()


def test_intermediates_from_band_pool_no_repeat_and_centred():
    # Distinct glyphs: widths 2..6, red outgoing, green incoming.
    out = _plan([_card(i * 8, 2 + i, range(0, 8), RED) for i in range(5)])
    inc = _plan([_card(i * 8, 2 + i, range(0, 6), GREEN) for i in range(5)])
    board = build_board(out, inc, 3, random.Random(7))
    pool = {
        FlapCell.from_card(c).rows_key()
        for d in (out.decks[0], inc.decks[0])
        for c in d.cards
    }
    for flap in board.flaps:
        a, *mid, b = flap.seq
        assert a is not None and b is not None
        assert len(mid) == 3
        centre = b.slot + b.width // 2
        own = (a.rows_key(), b.rows_key())
        for prev, cur in zip([a, *mid[:-1]], mid, strict=True):
            assert cur is not None
            assert cur.rows_key() in pool
            assert cur.rows_key() not in own
            assert cur.rows_key() != prev.rows_key()
            assert cur.slot + cur.width // 2 == centre


def test_small_pool_reduces_flips():
    out = _plan([_card(0, 5, range(0, 8), RED)])
    inc = _plan([_card(0, 5, range(0, 8), GREEN)])
    (flap,) = build_board(out, inc, 3, random.Random(0)).flaps
    assert len(flap.seq) == 2


def test_flap_centre_prefers_incoming():
    out = _plan([_card(0, 5, range(0, 8), RED)])
    inc = _plan([_card(20, 5, range(0, 8), GREEN)])
    (flap,) = build_board(out, inc, 0, random.Random(0)).flaps
    assert flap.centre_x == 22
    (flap,) = build_board(out, _plan(), 0, random.Random(0)).flaps
    assert flap.centre_x == 2


def test_ring_and_under_carried_from_plans():
    ring_o = [(0, 0, RED)]
    ring_i = [(1, 1, GREEN)]
    out = Plan([Deck((), 0)], ring_o, [(2, 2, RED)])
    inc = Plan([Deck((), 0)], ring_i, [])
    board = build_board(out, inc, 0, random.Random(0))
    assert board.ring_out == tuple(ring_o) and board.ring_in == tuple(ring_i)
    assert board.under_out == ((2, 2, RED),) and board.under_in == ()
