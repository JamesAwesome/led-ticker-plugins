"""flair.accordion — pure data layer: card segmentation, bands, ring, peek."""

from types import SimpleNamespace

from led_ticker.plugin import ScaledCanvas

from led_ticker_flair.flair._raster import Raster
from led_ticker_flair.flair.accordion_cards import (
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
