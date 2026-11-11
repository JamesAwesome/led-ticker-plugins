"""flair.sand grain math: snapshot -> grains, crumble + pour trajectories."""

import math
import random

import pytest

from led_ticker_flair.flair._raster import Raster
from led_ticker_flair.flair._sand import (
    crumble_grains,
    crumble_pos,
    pour_grains,
    pour_pos,
)


def _lit(w: int, h: int) -> Raster:
    r = Raster(w, h)
    for y in range(h):
        for x in range(w):
            r.SetPixel(x, y, 200, 100 + (x % 50), 50)
    return r


def test_grains_only_from_lit_pixels():
    r = Raster(4, 3)
    r.SetPixel(0, 0, 255, 0, 0)
    r.SetPixel(2, 1, 0, 255, 0)
    r.SetPixel(3, 2, 0, 0, 0)
    cg = crumble_grains(r, random.Random(1))
    pg = pour_grains(r, random.Random(1))
    assert len(cg) == 2
    assert len(pg) == 2
    assert {g[2:5] for g in cg} == {(255, 0, 0), (0, 255, 0)}
    assert {g[2:5] for g in pg} == {(255, 0, 0), (0, 255, 0)}
    assert {g[:2] for g in pg} == {(0, 0), (2, 1)}


def test_crumble_before_release_is_in_place():
    g = (10, 20, 1, 2, 3, 0.3, 5.0)
    assert crumble_pos(g, 0.2, 256, 64) == (10, 20)


def test_crumble_all_off_panel_by_end():
    # the runner never samples p = 1: with 30 frames the last crumble frame
    # is t = 14/30 (p = 0.933), and ~0.87 under ease_in_out
    grains = crumble_grains(_lit(256, 64), random.Random(1))
    assert all(crumble_pos(g, 0.85, 256, 64) is None for g in grains)


def test_crumble_only_moves_down_and_drift_bounded():
    grains = crumble_grains(_lit(256, 64), random.Random(2))
    bound = math.ceil(0.02 * 256) + 1
    for g in grains:
        for p in (0.1, 0.5, 0.9):
            pos = crumble_pos(g, p, 256, 64)
            if pos is None:
                continue
            assert pos[1] >= g[1]
            assert abs(pos[0] - g[0]) <= bound


def test_pour_straight_drop():
    grains = pour_grains(_lit(256, 64), random.Random(3))
    for g in grains:
        for i in range(10):
            y = pour_pos(g, i / 10, 64)
            if y is not None:
                assert 0 <= y <= g[1]


def test_pour_all_landed_before_end():
    grains = pour_grains(_lit(256, 64), random.Random(4))
    assert all(pour_pos(g, 0.9999, 64) == g[1] for g in grains)


def test_pour_bottom_rows_lead():
    grains = pour_grains(_lit(256, 64), random.Random(5))

    def landed(rows: range) -> float:
        sel = [g for g in grains if g[1] in rows]
        return sum(pour_pos(g, 0.7, 64) == g[1] for g in sel) / len(sel)

    assert landed(range(56, 64)) > landed(range(0, 8))


def test_physics_holds_on_small_panel():
    r = _lit(160, 16)
    cg = crumble_grains(r, random.Random(6))
    pg = pour_grains(r, random.Random(6))
    assert all(crumble_pos(g, 0.85, 160, 16) is None for g in cg)
    assert all(pour_pos(g, 0.9999, 16) == g[1] for g in pg)


def test_same_seed_same_grains():
    r = _lit(32, 16)
    assert crumble_grains(r, random.Random(7)) == crumble_grains(r, random.Random(7))
    assert pour_grains(r, random.Random(7)) == pour_grains(r, random.Random(7))


def test_crumble_release_uneven_within_a_row():
    # "whole-wordish, a little random": not all at once, not row by row
    grains = crumble_grains(_lit(256, 64), random.Random(10))
    for row in (0, 31, 63):
        rel = [g[5] for g in grains if g[1] == row]
        assert max(rel) - min(rel) > 0.25
    top = [g[5] for g in grains if g[1] < 8]
    bottom = [g[5] for g in grains if g[1] >= 56]
    assert abs(sum(top) / len(top) - sum(bottom) / len(bottom)) < 0.03


def test_crumble_grains_drift_sideways():
    grains = crumble_grains(_lit(256, 64), random.Random(11))
    moved = 0
    for g in grains:
        pos = crumble_pos(g, 0.45, 256, 64)
        if pos is not None and pos[0] != g[0]:
            moved += 1
    assert moved > len(grains) // 10


def test_pour_starts_from_the_contents_own_bottom_row():
    # letterboxed content (rows 24..39 of 64) must not wait for empty panel
    # rows below it before its first grains land
    r = Raster(256, 64)
    for y in range(24, 40):
        for x in range(256):
            r.SetPixel(x, y, 200, 150, 50)
    grains = pour_grains(r, random.Random(12))
    assert any(pour_pos(g, 0.45, 64) == g[1] for g in grains)
    assert all(pour_pos(g, 0.9999, 64) == g[1] for g in grains)


def _band(w: int, h: int, y0: int, y1: int) -> Raster:
    r = Raster(w, h)
    for y in range(y0, y1):
        for x in range(w):
            r.SetPixel(x, y, 200, 150, 50)
    return r


# The runner never samples q = 1: the last pour frame is q ~ 0.963 (30
# frames, linear) and can be ~0.944 at other frame counts / easings.
LAST_SAMPLED_Q = 0.93


@pytest.mark.parametrize(
    ("w", "h", "y0", "y1"),
    [(256, 64, 16, 48), (256, 64, 56, 64), (160, 16, 8, 16), (256, 64, 0, 64)],
)
def test_pour_landed_by_last_sampled_frame(w, h, y0, y1):
    grains = pour_grains(_band(w, h, y0, y1), random.Random(14))
    assert all(pour_pos(g, LAST_SAMPLED_Q, h) == g[1] for g in grains)
