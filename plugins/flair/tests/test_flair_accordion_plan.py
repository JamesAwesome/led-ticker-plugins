"""flair.accordion — pure data layer: card segmentation, bands, ring, peek."""

from types import SimpleNamespace

import pytest
from led_ticker.plugin import ScaledCanvas

from led_ticker_flair.flair import accordion_motion as am
from led_ticker_flair.flair._raster import Raster
from led_ticker_flair.flair.accordion_cards import (
    Card,
    Deck,
    band_rows,
    build_decks,
    effective_peek,
    ring_depth,
    ring_pixels,
    segment_cards,
)

W = (255, 255, 255)


def _cols(raster, cols, rows=None):
    for c in cols:
        for r in rows or range(raster.height):
            raster.SetPixel(c, r, *W)


def _seg(raster, mirror=False):
    return segment_cards(
        raster, range(raster.height), range(raster.width), mirror=mirror
    )


def test_blank_columns_split_cards():
    r = Raster(14, 8)
    _cols(r, [2, 3, 6, 9, 10, 11])
    cards = _seg(r)
    assert [c.slot for c in cards] == [2, 6, 9]
    assert [c.width for c in cards] == [2, 1, 3]


def test_touching_glyphs_merge():
    r = Raster(12, 8)
    _cols(r, range(2, 8))
    cards = _seg(r)
    assert len(cards) == 1
    assert (cards[0].slot, cards[0].width) == (2, 6)


def test_full_width_image_is_one_card():
    r = Raster(10, 4)
    _cols(r, range(10))
    cards = _seg(r)
    assert len(cards) == 1
    assert (cards[0].slot, cards[0].width) == (0, 10)


def test_black_and_unset_unlit():
    r = Raster(8, 4)
    _cols(r, [1])
    r.SetPixel(3, 2, 0, 0, 0)
    _cols(r, [5])
    cards = _seg(r)
    assert [c.slot for c in cards] == [1, 5]


def test_empty_raster_no_cards():
    assert _seg(Raster(8, 4)) == []


def test_mirror_reverses_slots():
    r = Raster(10, 4)
    _cols(r, [0, 1])
    cards = _seg(r, mirror=True)
    assert len(cards) == 1
    assert (cards[0].slot, cards[0].width) == (8, 2)


def test_effective_peek_caps_to_avg_spacing():
    r = Raster(10, 4)
    _cols(r, [0, 3, 6])
    cards = _seg(r)
    assert effective_peek(cards, 8) == 3.0
    assert effective_peek(cards[:1], 8) == 8


def test_ring_depth_from_thickness():
    r = Raster(20, 16)
    assert ring_depth(SimpleNamespace(border=SimpleNamespace(thickness=2)), r) == 2
    assert ring_depth(SimpleNamespace(border=None), r) == 0


def test_ring_depth_measured_without_thickness():
    r = Raster(20, 16)
    for y in range(3):
        _cols(r, range(20), rows=[y])
    assert ring_depth(SimpleNamespace(border=object()), r) == 3


def test_bordered_inset_splits():
    r = Raster(20, 8)
    for x in range(20):
        r.SetPixel(x, 0, *W)
        r.SetPixel(x, 7, *W)
    for y in range(8):
        r.SetPixel(0, y, *W)
        r.SetPixel(19, y, *W)
    _cols(r, [5, 9], rows=range(2, 6))
    widget = SimpleNamespace(border=SimpleNamespace(thickness=1), bottom_text="")
    canvas = Raster(20, 8)
    decks, ring = build_decks(r, widget, canvas, mirror=False)
    assert len(decks) == 1
    assert len(decks[0].cards) == 2
    assert len(ring) == 2 * 20 + 2 * 6


def test_ring_pixels_in_real_coords():
    r = Raster(6, 6)
    r.SetPixel(0, 3, *W)
    r.SetPixel(3, 3, *W)
    assert ring_pixels(r, 1) == [(0, 3, W)]


def test_two_row_bands_split_at_boundary():
    r = Raster(10, 16)
    r.SetPixel(4, 2, *W)
    r.SetPixel(4, 12, *W)
    widget = SimpleNamespace(border=None, bottom_text="x", top_row_height=None)
    assert band_rows(widget, r, 16, 0) == [range(0, 8), range(8, 16)]
    decks, ring = build_decks(r, widget, r, mirror=False)
    assert [len(d.cards) for d in decks] == [1, 1]
    assert ring == []


def test_two_row_bands_scaled():
    real = Raster(256, 64)
    canvas = ScaledCanvas(real, scale=4, content_height=16)
    widget = SimpleNamespace(border=None, bottom_text="x", top_row_height=None)
    bands = band_rows(widget, canvas, 64, 0)
    assert bands == [range(0, 32), range(32, 64)]


# ---- motion functions (Task 3) ----

_PW = 160


def _deck(slots, widths, peek):
    return Deck(
        cards=tuple(
            Card(slot=s, width=w, pixels=()) for s, w in zip(slots, widths, strict=True)
        ),
        peek=peek,
    )


_DECKS = [
    _deck([0, 40, 90], [20, 30, 25], 4.0),
    _deck([0, 2, 4, 6], [5, 5, 5, 5], 2.0),  # dense: P=8 capped to 2
    _deck([10, 70], [12, 40], 5.0),
]
_OUT = [am.sweep_out, am.stretch_out]
_IN = [am.sweep_in, am.stretch_in]


def _slots(d):
    return [float(c.slot) for c in d.cards]


def test_empty_deck():
    d = Deck(cards=(), peek=0.0)
    for fn in _OUT + _IN:
        assert fn(d, _PW, 0.5) == []


def test_out_k0_is_slots():
    for fn in _OUT:
        for d in _DECKS:
            assert fn(d, _PW, 0.0) == pytest.approx(_slots(d))


def test_out_k1_offscreen():
    for fn in _OUT:
        for d in _DECKS:
            pos = fn(d, _PW, 1.0)
            assert all(p + c.width <= 0 for p, c in zip(pos, d.cards, strict=True))


def test_in_k0_offscreen():
    for fn in _IN:
        for d in _DECKS:
            assert all(p >= _PW for p in fn(d, _PW, 0.0))


def test_in_k1_is_slots():
    for fn in _IN:
        for d in _DECKS:
            assert fn(d, _PW, 1.0) == pytest.approx(_slots(d))


def test_continuity():
    # Per-step move of any card is bounded by the anchor's travel plus one
    # peek (plus, for stretch, the spread collapsing at 1/100 per step).
    # A discontinuity would blow through that bound.
    for fn in _OUT + _IN:
        for d in _DECKS:
            s = _slots(d)
            spread = max(abs((s[i] - s[0]) - i * d.peek) for i in range(len(s)))
            extra = spread / 100 if fn in (am.stretch_out, am.stretch_in) else 0.0
            prev = fn(d, _PW, 0.0)
            for step in range(1, 101):
                cur = fn(d, _PW, step / 100)
                # card 0 sits at the anchor for stretch; for sweep it is
                # min/max(slot, anchor), so its travel is <= anchor travel.
                anchor_dx = abs(cur[0] - prev[0])
                for c, q in zip(cur, prev, strict=True):
                    assert abs(c - q) <= anchor_dx + d.peek + extra + 1e-9
                prev = cur


def test_sweep_in_lands_right_to_left():
    d = _deck([0, 10, 20], [5, 5, 5], 2.0)
    landed = []
    for i in range(3):
        for step in range(0, 1001):
            if am.sweep_in(d, _PW, step / 1000)[i] == pytest.approx(d.cards[i].slot):
                landed.append(step)
                break
    assert landed[0] > landed[1] > landed[2]


def test_t0_positions_equal_slots_clipped_content():
    d = _deck([-3, 150], [6, 8], 4.0)
    for fn in _OUT:
        assert fn(d, _PW, 0.0) == pytest.approx([-3.0, 150.0])


def test_stacked_never_wider_than_fanned():
    d = _DECKS[1]
    n = len(d.cards)
    stacked = (n - 1) * d.peek + d.cards[-1].width
    fanned = d.cards[-1].slot + d.cards[-1].width - d.cards[0].slot
    assert stacked <= fanned
