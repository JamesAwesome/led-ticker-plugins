"""flair.interlock — pure math: strand assignment, content-sized travel,
phase offsets, plan building."""

from led_ticker_flair.flair._raster import Raster
from led_ticker_flair.flair._snapshot import Geometry
from led_ticker_flair.flair.interlock import (
    build_plan,
    clear_distance,
    mesh_offset,
    split_offset,
    strand_index,
)

SMALL = Geometry(10, 4, 1, 0, 4)


def test_strand_index_scale1_one_row_strands():
    assert [strand_index(y, 0, 1, 16) for y in range(16)] == list(range(16))


def test_strand_index_bigsign_four_real_rows():
    assert [strand_index(y, 0, 4, 16) for y in (0, 1, 2, 3, 4)] == [0, 0, 0, 0, 1]


def test_strands_anchor_at_y_offset_real_and_clamp_letterbox():
    # 128x64 panel, scale 2, content 16 -> y_offset_real 16, strand_px 2, 16 strands
    assert strand_index(16, 16, 2, 16) == 0
    assert strand_index(18, 16, 2, 16) == 1
    assert strand_index(0, 16, 2, 16) == 0  # letterbox above -> first strand
    assert strand_index(63, 16, 2, 16) == 15  # letterbox below -> last strand


def test_clear_distance_centred():
    assert clear_distance(60, 99, 160, toward_positive=True) == 100
    assert clear_distance(60, 99, 160, toward_positive=False) == 100


def test_clear_distance_edge_hugging():
    assert clear_distance(0, 39, 160, toward_positive=True) == 160
    assert clear_distance(0, 39, 160, toward_positive=False) == 40
    assert clear_distance(120, 159, 160, toward_positive=True) == 40
    assert clear_distance(120, 159, 160, toward_positive=False) == 160


def test_split_offset_endpoints():
    assert split_offset(0.0, 100) == 0
    assert split_offset(0.25, 100) == 50
    assert split_offset(0.5, 100) == 100
    assert split_offset(0.7, 100) == 100  # clamped


def test_mesh_offset_endpoints():
    assert mesh_offset(0.5, 100) == 100
    assert mesh_offset(0.725, 100) == 50
    assert mesh_offset(0.95, 100) == 0
    assert mesh_offset(0.99, 100) == 0  # clamped


def _raster(w: int, h: int, lit: list[tuple[int, int]]) -> Raster:
    r = Raster(w, h)
    for x, y in lit:
        r.SetPixel(x, y, 200, 100, 50)
    r.SetPixel(9, 3, 0, 0, 0)  # pure black is never lit
    return r


def test_build_plan_splits_parity_and_per_parity_extent():
    r = _raster(10, 4, [(2, 0), (3, 1), (7, 2), (5, 3)])
    p = build_plan(r, "horizontal", SMALL, 1)
    assert p.axis == "horizontal"
    assert p.size == 10
    assert sorted((x, y) for x, y, _c in p.even) == [(2, 0), (7, 2)]
    assert sorted((x, y) for x, y, _c in p.odd) == [(3, 1), (5, 3)]
    assert (p.even_lo, p.even_hi) == (2, 7)  # x-extent of even strands
    assert (p.odd_lo, p.odd_hi) == (3, 5)


def test_build_plan_vertical_uses_columns_and_y_extent():
    r = _raster(10, 4, [(2, 0), (3, 1), (2, 3), (5, 2)])
    p = build_plan(r, "vertical", SMALL, 1)
    assert p.size == 4
    assert sorted((x, y) for x, y, _c in p.even) == [(2, 0), (2, 3)]
    assert sorted((x, y) for x, y, _c in p.odd) == [(3, 1), (5, 2)]
    assert (p.even_lo, p.even_hi) == (0, 3)  # y-extent
    assert (p.odd_lo, p.odd_hi) == (1, 2)


def test_build_plan_strand_two_scale_four():
    geo = Geometry(8, 16, 4, 0, 16)  # strand 2 -> 8 real rows per strand
    r = _raster(8, 16, [(0, 7), (0, 8)])
    p = build_plan(r, "horizontal", geo, 2)
    assert [(x, y) for x, y, _c in p.even] == [(0, 7)]
    assert [(x, y) for x, y, _c in p.odd] == [(0, 8)]


def test_build_plan_empty():
    p = build_plan(Raster(10, 4), "horizontal", SMALL, 1)
    assert p.even == [] and p.odd == []
    assert (p.even_lo, p.even_hi, p.odd_lo, p.odd_hi) == (-1, -1, -1, -1)
