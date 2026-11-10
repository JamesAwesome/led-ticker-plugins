"""flair.splitflap — the flap painter (pure, recording set_px)."""

import pytest

from led_ticker_flair.flair.splitflap_board import BandGeom, FlapCell
from led_ticker_flair.flair.splitflap_paint import (
    FLAP_SHADE,
    flap_shade,
    paint_cell,
    paint_flap,
)

RED = (200, 0, 0)
GREEN = (0, 200, 0)
BAND = BandGeom(lo=0, hinge=8, hi=15)
W, H = 32, 16


def _cell(colour, rows=None, slot=2, width=3) -> FlapCell:
    rows = range(16) if rows is None else rows
    row = tuple((dx, colour) for dx in range(width))
    return FlapCell(slot, width, dict.fromkeys(rows, row))


def _record():
    got: dict[tuple[int, int], tuple[int, int, int]] = {}

    def set_px(x, y, r, g, b):
        got[(x, y)] = (r, g, b)

    return got, set_px


def _rows(got) -> dict[int, tuple[int, int, int]]:
    out = {}
    for (_x, y), rgb in got.items():
        out.setdefault(y, rgb)
        assert out[y] == rgb  # one colour per row in these fixtures
    return out


def _shaded(rgb, q):
    f = flap_shade(q)
    return tuple(round(c * f) for c in rgb)


def test_shade_peaks_mid_flip_and_vanishes_at_ends():
    assert flap_shade(0.0) == 1.0 and flap_shade(1.0) == 1.0
    assert flap_shade(0.5) == pytest.approx(FLAP_SHADE)


def test_paint_cell_paints_every_pixel_at_home():
    got, set_px = _record()
    paint_cell(set_px, _cell(RED), W, H)
    assert set(got) == {(x, y) for x in range(2, 5) for y in range(16)}
    paint_cell(set_px, None, W, H)  # blank is a no-op


def test_flap_q0_shows_outgoing():
    a, b = _cell(RED), _cell(GREEN)
    got, set_px = _record()
    paint_flap(set_px, a, b, BAND, 0.0, W, H)
    ref, ref_px = _record()
    paint_cell(ref_px, a, W, H)
    assert got == ref


def test_flap_q1_shows_incoming():
    a, b = _cell(RED), _cell(GREEN)
    got, set_px = _record()
    paint_flap(set_px, a, b, BAND, 1.0, W, H)
    ref, ref_px = _record()
    paint_cell(ref_px, b, W, H)
    assert got == ref


def test_flap_first_half_squashes_a_top_toward_hinge():
    got, set_px = _record()
    paint_flap(set_px, _cell(RED), _cell(GREEN), BAND, 0.25, W, H)
    rows = _rows(got)
    assert all(rows[y] == GREEN for y in range(0, 4))
    assert all(rows[y] == _shaded(RED, 0.25) for y in range(4, 8))
    assert all(rows[y] == RED for y in range(8, 16))


def test_flap_second_half_unfolds_b_bottom():
    got, set_px = _record()
    paint_flap(set_px, _cell(RED), _cell(GREEN), BAND, 0.75, W, H)
    rows = _rows(got)
    assert all(rows[y] == GREEN for y in range(0, 8))
    assert all(rows[y] == _shaded(GREEN, 0.75) for y in range(8, 12))
    assert all(rows[y] == RED for y in range(12, 16))


def test_flap_samples_source_rows_not_repeats_one_row():
    # a's top half has a distinct colour per row; squashed to half height,
    # the flap shows every other source row.
    a = FlapCell(0, 1, {y: ((0, (y * 10, 0, 0)),) for y in range(16)})
    got, set_px = _record()
    paint_flap(set_px, a, None, BAND, 0.25, W, H)
    f = flap_shade(0.25)
    want = [round(v * f) for v in (0, 20, 40, 60)]
    assert [got[(0, y)][0] for y in range(4, 8)] == want


def test_flap_from_blank_and_to_blank():
    got, set_px = _record()
    paint_flap(set_px, None, _cell(GREEN), BAND, 0.25, W, H)
    assert set(_rows(got)) == set(range(0, 4))
    got, set_px = _record()
    paint_flap(set_px, _cell(RED), None, BAND, 0.75, W, H)
    assert set(_rows(got)) == set(range(12, 16))


def test_flap_tiny_half_heights_stay_in_band():
    band = BandGeom(lo=6, hinge=8, hi=9)
    a, b = _cell(RED, range(6, 10)), _cell(GREEN, range(6, 10))
    for i in range(21):
        got, set_px = _record()
        paint_flap(set_px, a, b, band, i / 20, W, H)
        assert all(6 <= y <= 9 for _, y in got)


def test_writes_clipped_to_panel():
    got, set_px = _record()
    edge = FlapCell(30, 4, {y: tuple((dx, RED) for dx in range(4)) for y in range(16)})
    for q in (0.0, 0.3, 0.7, 1.0):
        paint_flap(set_px, edge, edge, BAND, q, W, H)
    assert all(0 <= x < W and 0 <= y < H for x, y in got)
