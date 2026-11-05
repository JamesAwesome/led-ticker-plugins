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
    exact_ring,
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
    assert isinstance(effective_peek(cards[:1], 8), float)


def test_ring_depth_from_thickness():
    r = Raster(20, 16)
    assert ring_depth(SimpleNamespace(border=SimpleNamespace(thickness=2)), r) == 2
    assert ring_depth(SimpleNamespace(border=None), r) == 0


def test_ring_depth_measured_without_thickness():
    # An unknown, attribute-less border shape: a solid 3-px ring is measured.
    r = Raster(20, 16)
    for y in range(16):
        for x in range(20):
            if y < 3 or y >= 13 or x < 3 or x >= 17:
                r.SetPixel(x, y, *W)
    assert ring_depth(SimpleNamespace(border=object()), r) == 3


def test_ring_depth_ignores_content_touching_top_edge():
    # The measured fallback runs only when a border is set, so a bordered
    # widget of unknown shape whose CONTENT touches the top edge (full-width
    # top rows, the old "≥ 50% of the row" false positive) must read 0.
    r = Raster(20, 16)
    for y in range(3):
        _cols(r, range(20), rows=[y])
    assert ring_depth(SimpleNamespace(border=object()), r) == 0
    assert ring_depth(SimpleNamespace(border=None), r) == 0


def test_ring_depth_ignores_full_height_text():
    # Tall glyphs touching BOTH the top and bottom rows (but not the side
    # columns) are content, not a ring.
    r = Raster(40, 16)
    _cols(r, [x for x in range(2, 38) if x % 3])
    assert ring_depth(SimpleNamespace(border=object()), r) == 0


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
    decks, ring, _under = build_decks(r, widget, canvas, mirror=False)
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
    decks, ring, _under = build_decks(r, widget, r, mirror=False)
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


def _dense_deck():
    cards = tuple(Card(slot=s, width=5, pixels=()) for s in (0, 2, 4, 6))
    return Deck(cards=cards, peek=effective_peek(cards, 8))


_DECKS = [
    _deck([0, 40, 90], [20, 30, 25], 4.0),
    _dense_deck(),  # dense: P=8 capped to 2
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


def _anchor_travel(fn, d):
    """Exact per-step (1/100) anchor travel and extra spread allowance."""
    s = _slots(d)
    p = d.peek
    n = len(s)
    right = max(i * p + c.width for i, c in enumerate(d.cards))
    if fn is am.sweep_out:
        g0 = max(_PW - (n - 1) * p, max(s[i] - i * p for i in range(n)))
        return abs(g0 - (-right - 1)) / 100, 0.0
    if fn is am.sweep_in:
        return abs(_PW - min(s[i] - i * p for i in range(n))) / 100, 0.0
    spread = max(abs((s[i] - s[0]) - i * p) for i in range(n))
    if fn is am.stretch_out:
        return abs(s[0] - (-right - 1)) / 100, spread / 100
    return abs(_PW - s[0]) / 100, spread / 100


def test_continuity():
    # sweep is 1-Lipschitz in the anchor; stretch adds the spread collapse.
    # No +P slack: a card snapping a peek at pickup must fail.
    for fn in _OUT + _IN:
        for d in _DECKS:
            anchor_dx, extra = _anchor_travel(fn, d)
            prev = fn(d, _PW, 0.0)
            for step in range(1, 101):
                cur = fn(d, _PW, step / 100)
                for c, q in zip(cur, prev, strict=True):
                    assert abs(c - q) <= anchor_dx + extra + 1e-9
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
    cards = tuple(Card(slot=s, width=5, pixels=()) for s in (0, 2, 4, 6))
    d = Deck(cards=cards, peek=effective_peek(cards, 8))
    assert d.peek == 2  # P=8 capped to the average spacing
    fanned = cards[-1].slot + cards[-1].width - cards[0].slot
    for fn in _OUT:
        pos = fn(d, _PW, 1.0)  # fully stacked
        stacked = pos[-1] + cards[-1].width - pos[0]
        assert stacked == pytest.approx((len(cards) - 1) * d.peek + 5)
        assert stacked <= fanned


# --- Task 4: occluding compositor ---------------------------------------

from led_ticker_flair.flair.accordion_compose import compose  # noqa: E402

RED = (255, 0, 0)
BLUE = (0, 0, 255)


def _full_card(slot, width, rgb, rows=(0,)):
    return Card(
        slot=slot,
        width=width,
        pixels=tuple((dx, y, rgb) for dx in range(width) for y in rows),
    )


def _run(deck, positions, W, mirror=False):
    calls = []
    compose(
        deck,
        positions,
        W,
        lambda x, y, r, g, b: calls.append((x, y, (r, g, b))),
        mirror=mirror,
    )
    return calls


def test_top_card_occludes():
    deck = Deck(cards=(_full_card(0, 4, RED), _full_card(2, 4, BLUE)), peek=2.0)
    calls = _run(deck, [0, 2], 10)
    got = {x: rgb for x, _, rgb in calls}
    assert got == {0: RED, 1: RED, 2: BLUE, 3: BLUE, 4: BLUE, 5: BLUE}
    assert len(calls) == 6


def test_unlit_top_cells_paint_nothing():
    top = Card(slot=0, width=2, pixels=((0, 0, BLUE),))  # no pixel at (1, 0)
    under = Card(slot=0, width=2, pixels=((0, 0, RED), (1, 0, RED)))
    deck = Deck(cards=(under, top), peek=1.0)
    calls = _run(deck, [0, 0], 4)
    assert calls == [(0, 0, BLUE)]


def test_offscreen_clipped():
    deck = Deck(cards=(_full_card(0, 4, RED),), peek=1.0)
    calls = _run(deck, [-2], 10)
    assert {x for x, _, _ in calls} == {0, 1}
    calls = _run(deck, [8], 10)
    assert {x for x, _, _ in calls} == {8, 9}


def test_mirror_maps_columns():
    deck = Deck(cards=(_full_card(0, 1, RED),), peek=1.0)
    assert _run(deck, [0], 10, mirror=True) == [(9, 0, RED)]


def test_t0_matches_snapshot_clipped_content():
    r = Raster(20, 6)
    _cols(r, [0, 1, 2, 8, 9, 17, 18, 19])  # clipped at both edges
    cards = _seg(r)
    deck = Deck(cards=tuple(cards), peek=2.0)
    pos = am.sweep_out(deck, 20, 0.0)
    calls = _run(deck, pos, 20)
    painted = {(x, y) for x, y, _ in calls}
    lit = {
        (x, y)
        for x in range(20)
        for y in range(6)
        if r.get(x, y) is not None and r.get(x, y) != (0, 0, 0)
    }
    assert painted == lit
    assert len(calls) == len(painted)


# --- real core borders (tests may import core internals; plugin SOURCE may
# not — see test_import_purity.py, which scans src/ only) -------------------

from led_ticker.borders import (  # noqa: E402
    ColorBandsBorder,
    LightbulbBorder,
    RainbowChaseBorder,
)

GEOMETRIES = [(160, 16), (128, 64), (256, 64)]


def _bulb(**kw):
    return lambda: LightbulbBorder(**kw)


BORDERS = {
    "bulb-chase": (_bulb(mode="chase"), None),
    "bulb-alternate": (_bulb(mode="alternate"), None),
    "bulb-unison": (_bulb(mode="unison"), None),
    "bulb-rainbow": (_bulb(mode="chase", lit_color="rainbow"), None),
    "bulb-black-unlit": (_bulb(mode="chase", unlit_color=(0, 0, 0)), None),
    "bulb-size2-gap5": (_bulb(bulb_size=2, gap=5), 2),
    "rainbow-t2": (lambda: RainbowChaseBorder(thickness=2), 2),
    "bands-t2": (
        lambda: ColorBandsBorder(colors=[(255, 0, 0), (0, 0, 255)], thickness=2),
        2,
    ),
}


def _expected_depth(name, h):
    fixed = BORDERS[name][1]
    if fixed is not None:
        return fixed
    return 3 if h >= 32 else 1  # LightbulbBorder's auto bulb size


def _bordered_raster(border, w, h, frame):
    r = Raster(w, h)
    border.paint(r, frame)
    return r


def _inset_content(r, d):
    # Glyph-ish blocks pressed right up against the ring's inner edge.
    w, h = r.width, r.height
    for x in (d, d + 1, w // 2, w - d - 2, w - d - 1):
        for y in range(d, h - d):
            r.SetPixel(x, y, 0, 255, 0)


@pytest.mark.parametrize("w,h", GEOMETRIES)
@pytest.mark.parametrize("name", sorted(BORDERS))
@pytest.mark.parametrize("frame", [0, 2, 8, 17])
def test_core_border_ring_depth(name, w, h, frame):
    border = BORDERS[name][0]()
    r = _bordered_raster(border, w, h, frame)
    assert ring_depth(SimpleNamespace(border=border), r) == _expected_depth(name, h)


@pytest.mark.parametrize("w,h", GEOMETRIES)
@pytest.mark.parametrize("name", sorted(BORDERS))
def test_core_border_no_inset_card_touches_ring(name, w, h):
    border = BORDERS[name][0]()
    d = _expected_depth(name, h)
    r = _bordered_raster(border, w, h, 0)
    _inset_content(r, d)
    widget = SimpleNamespace(border=border, bottom_text="")
    decks, ring, _under = build_decks(r, widget, Raster(w, h), mirror=False)
    cards = decks[0].cards
    assert len(cards) >= 3  # the inset content splits; the ring is no card
    for card in cards:
        for dx, y, _ in card.pixels:
            x = card.slot + dx
            assert d <= x < w - d and d <= y < h - d, (name, x, y)
    in_band = {
        (x, y)
        for y in range(h)
        for x in range(w)
        if (y < d or y >= h - d or x < d or x >= w - d)
        and r.get(x, y) not in (None, (0, 0, 0))
    }
    assert {(x, y) for x, y, _ in ring} == in_band
    assert ring  # every geometry keeps a visible ring


@pytest.mark.parametrize("w,h", GEOMETRIES)
@pytest.mark.parametrize("mode", ["chase", "alternate", "unison"])
def test_lightbulb_measured_fallback_without_duck_type(mode, w, h):
    # Same pixels, but a border object exposing none of LightbulbBorder's
    # attributes: the measured four-edge fallback must still find the bulbs.
    r = _bordered_raster(LightbulbBorder(mode=mode), w, h, 0)
    expected = 3 if h >= 32 else 1
    assert ring_depth(SimpleNamespace(border=object()), r) == expected


def test_exact_ring_splits_content_from_border():
    border_only = Raster(10, 4)
    snap = Raster(10, 4)
    for x in range(10):
        border_only.SetPixel(x, 0, 0, 0, 255)
        snap.SetPixel(x, 0, 0, 0, 255)
    snap.SetPixel(0, 0, *W)  # content over the ring
    snap.SetPixel(0, 1, *W)
    ring, under = exact_ring(snap, border_only)
    assert {(x, y) for x, y, _ in ring} == {(x, 0) for x in range(1, 10)}
    assert under == [(0, 0, (0, 0, 255))]


def test_exact_ring_untrusted_render_falls_back():
    snap = Raster(10, 4)
    _cols(snap, [0, 9])
    assert exact_ring(snap, Raster(10, 4)) is None  # nothing lit alone
    other = Raster(10, 4)
    for x in range(10):
        other.SetPixel(x, 0, 0, 0, 255)  # a ring the snapshot never had
    assert exact_ring(snap, other) is None
    # build_decks then uses the depth-based ring.
    widget = SimpleNamespace(border=SimpleNamespace(thickness=1), bottom_text="")
    decks, ring, under = build_decks(
        snap, widget, snap, mirror=False, border_only=other
    )
    assert under == [] and {x for x, _, _ in ring} == {0, 9}


def test_sweep_out_hand_starts_at_right_edge():
    # Spec: g starts at max(W-(n-1)P, ...): the hand begins at the panel's
    # right edge, so left-aligned content stays in its slots while the hand
    # crosses the empty right part. Without the term the hand starts at the
    # content and the first card moves at once.
    d = _deck([2, 10, 20], [4, 4, 4], 3.0)
    for k in (0.02, 0.05, 0.1):
        assert am.sweep_out(d, _PW, k) == pytest.approx(_slots(d)), k
    # ... and it does start moving eventually.
    assert am.sweep_out(d, _PW, 0.9) != pytest.approx(_slots(d))

