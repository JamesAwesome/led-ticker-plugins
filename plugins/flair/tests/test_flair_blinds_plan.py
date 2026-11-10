"""flair.blinds — pure math: slat bounds, reveal counts, per-pixel depth."""

from led_ticker_flair.flair._raster import Raster
from led_ticker_flair.flair._snapshot import Geometry
from led_ticker_flair.flair.blinds import (
    DEFAULT_SLATS,
    Blinds,
    build_plan,
    orientation,
    revealed,
    slat_bounds,
)


def test_default_slats():
    assert DEFAULT_SLATS == {"horizontal": 8, "vertical": 8}


def test_orientation_mapping():
    assert [orientation(d) for d in ("down", "up", "right", "left")] == [
        "horizontal",
        "horizontal",
        "vertical",
        "vertical",
    ]


def test_slat_bounds_smallsign_defaults():
    assert slat_bounds(16, 4, 1) == [(0, 4), (4, 8), (8, 12), (12, 16)]
    assert slat_bounds(160, 8, 1) == [(k * 20, k * 20 + 20) for k in range(8)]


def test_slat_bounds_bigsign_snap_to_scale():
    assert slat_bounds(64, 4, 4) == [(0, 16), (16, 32), (32, 48), (48, 64)]
    assert slat_bounds(256, 8, 4) == [(k * 32, k * 32 + 32) for k in range(8)]


def test_slat_bounds_remainder_and_clamp():
    assert slat_bounds(16, 3, 1) == [(0, 5), (5, 10), (10, 16)]
    assert slat_bounds(64, 3, 4) == [(0, 20), (20, 40), (40, 64)]
    assert slat_bounds(64, 100, 4) == [(k * 4, k * 4 + 4) for k in range(16)]


def test_revealed_endpoints():
    assert revealed(0.0, 0, 16) == 0
    assert revealed(0.5, 0, 16) == 8
    assert revealed(1.0, 0, 16) == 16


def _raster(w: int, h: int, lit: list[tuple[int, int]]) -> Raster:
    r = Raster(w, h)
    for x, y in lit:
        r.SetPixel(x, y, 1, 2, 3)
    return r


def _depths(plan_px: list[tuple]) -> dict[tuple[int, int], tuple[int, int]]:
    return {(e[0], e[1]): (e[5], e[6]) for e in plan_px}


def test_depth_per_direction_rows():
    geo = Geometry(4, 8, 1, 0, 8)
    r = _raster(4, 8, [(0, 5)])
    empty = Raster(4, 8)
    down = build_plan(r, empty, "down", 2, geo)  # slats (0,4),(4,8)
    up = build_plan(r, empty, "up", 2, geo)
    assert _depths(down.out_px) == {(0, 5): (1, 1)}
    assert _depths(up.out_px) == {(0, 5): (1, 2)}


def test_depth_per_direction_columns():
    geo = Geometry(8, 4, 1, 0, 4)
    r = _raster(8, 4, [(5, 0)])
    empty = Raster(8, 4)
    right = build_plan(empty, r, "right", 2, geo)
    left = build_plan(empty, r, "left", 2, geo)
    assert _depths(right.in_px) == {(5, 0): (1, 1)}
    assert _depths(left.in_px) == {(5, 0): (1, 2)}
    assert right.bounds == [(0, 4), (4, 8)]


def test_build_plan_only_lit_pixels():
    geo = Geometry(4, 4, 1, 0, 4)
    r = _raster(4, 4, [(1, 1)])
    r.SetPixel(2, 2, 0, 0, 0)  # pure black: unlit
    p = build_plan(r, r, "down", 2, geo)
    assert [(e[0], e[1]) for e in p.out_px] == [(1, 1)]
    assert [(e[0], e[1]) for e in p.in_px] == [(1, 1)]
    assert p.out_px[0][2:5] == (1, 2, 3)


def test_build_plan_letterboxed_slats_anchor_at_content():
    # 128x64 panel at scale 2, content 16 -> content rows 16..47. Slats split
    # the CONTENT band only; the letterbox is carried as the plan's extent.
    geo = Geometry(4, 64, 2, 16, 32)
    p = build_plan(Raster(4, 64), Raster(4, 64), "down", 4, geo)
    assert p.bounds == [(16, 24), (24, 32), (32, 40), (40, 48)]
    assert p.extent == (0, 64)


class _Real:
    def __init__(self, w: int, h: int) -> None:
        self.width, self.height = w, h
        self.px: dict[tuple[int, int], tuple[int, int, int]] = {}

    def SetPixel(self, x, y, r, g, b):  # noqa: N802
        self.px[(x, y)] = (r, g, b)

    def SubFill(self, x, y, w, h, r, g, b):  # noqa: N802
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.px[(xx, yy)] = (r, g, b)


RED, GREEN, BG = (200, 0, 0), (0, 200, 0), (0, 0, 9)


def _letterboxed_rows(direction: str, p: float) -> list[tuple[int, int, int] | None]:
    geo = Geometry(1, 64, 2, 16, 32)
    out_r, in_r = Raster(1, 64), Raster(1, 64)
    for y in range(64):  # lit everywhere, letterbox included (e.g. a border)
        out_r.SetPixel(0, y, *RED)
        in_r.SetPixel(0, y, *GREEN)
    plan = build_plan(out_r, in_r, direction, 4, geo)
    real = _Real(1, 64)
    Blinds._paint(real, plan, p, BG)
    return [real.px.get((0, y)) for y in range(64)]


def test_letterboxed_down_every_slat_opens_at_the_same_rate():
    rows = _letterboxed_rows("down", 0.5)
    # Leading letterbox opens with slat 0's first row; trailing waits for the
    # last slat to finish. Every content slat shows 4 of its 8 rows.
    assert rows[:16] == [GREEN] * 16
    assert rows[16:48] == ([GREEN] * 4 + [RED] * 4) * 4
    assert rows[48:] == [RED] * 16


def test_letterboxed_up_mirrors_down():
    rows = _letterboxed_rows("up", 0.5)
    assert rows[:16] == [RED] * 16
    assert rows[16:48] == ([RED] * 4 + [GREEN] * 4) * 4
    assert rows[48:] == [GREEN] * 16


def test_letterboxed_fully_open_reveals_everything():
    assert _letterboxed_rows("down", 1.0) == [GREEN] * 64
    assert _letterboxed_rows("up", 1.0) == [GREEN] * 64


def test_letterboxed_t0_shows_only_outgoing():
    assert _letterboxed_rows("down", 0.0) == [RED] * 64


def test_build_plan_vertical_slats_ignore_y_offset():
    geo = Geometry(16, 64, 2, 16, 32)
    p = build_plan(Raster(16, 64), Raster(16, 64), "right", 4, geo)
    assert p.bounds == [(0, 4), (4, 8), (8, 12), (12, 16)]
