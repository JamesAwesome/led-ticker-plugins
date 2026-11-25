"""flair.slots — the reel painter (pure, recording set_px)."""

from led_ticker_flair.flair.slots_paint import (
    overshoot_rows,
    paint_reel,
    reel_pitch,
    strip_symbols,
)
from led_ticker_flair.flair.splitflap_board import BandGeom, FlapCell
from led_ticker_flair.flair.splitflap_paint import paint_cell

RED = (200, 0, 0)
GREEN = (0, 200, 0)
BAND = BandGeom(lo=4, hinge=8, hi=11)
W, H = 32, 16
WIN = (2, 3)  # the shared (slot, width) of the default _cell


def _cell(colour, rows=None, slot=2, width=3) -> FlapCell:
    rows = range(16) if rows is None else rows
    row = tuple((dx, colour) for dx in range(width))
    return FlapCell.make(slot, width, dict.fromkeys(rows, row))


def _record():
    got: dict[tuple[int, int], tuple[int, int, int]] = {}

    def set_px(x, y, r, g, b):
        got[(x, y)] = (r, g, b)

    return got, set_px


def _rows(got) -> dict[int, tuple[int, int, int]]:
    out = {}
    for (_x, y), rgb in got.items():
        out.setdefault(y, rgb)
        assert out[y] == rgb
    return out


def test_reel_pitch_and_gap():
    assert reel_pitch(BAND) == (10, 2)
    assert reel_pitch(BandGeom(0, 3, 6)) == (9, 2)
    assert reel_pitch(BandGeom(0, 1, 2)) == (4, 1)


def test_overshoot_rows_capped_by_gap():
    assert overshoot_rows(10, 2) == 1
    assert overshoot_rows(40, 8) == 5
    assert overshoot_rows(4, 1) == 1


def test_strip_symbols_cycles_in_betweens():
    a, m1, m2, b = _cell(RED), _cell(GREEN), _cell((0, 0, 200)), _cell((9, 9, 9))
    assert strip_symbols((a, m1, m2, b), 1) == (a, b)
    assert strip_symbols((a, m1, m2, b), 3) == (a, m1, m2, b)
    assert strip_symbols((a, m1, m2, b), 6) == (a, m1, m2, m1, m2, m1, b)


def test_strip_symbols_without_in_betweens_alternates_blank():
    a, b = _cell(RED), _cell(GREEN)
    assert strip_symbols((a, b), 4) == (a, None, a, None, b)
    assert strip_symbols((None, b), 3) == (None, None, None, b)


def _two():
    return strip_symbols((_cell(RED, range(4, 12)), _cell(GREEN, range(4, 12))), 1)


def test_paint_reel_d0_is_outgoing_in_place_exact():
    got, set_px = _record()
    paint_reel(set_px, _two(), BAND, 0.0, 1.0, W, H, WIN)
    assert set(got) == {(x, y) for x in range(2, 5) for y in range(4, 12)}
    assert set(got.values()) == {RED}


def test_paint_reel_landed_is_incoming_in_place_exact():
    got, set_px = _record()
    paint_reel(set_px, _two(), BAND, 10.0, 1.0, W, H, WIN)
    assert set(got) == {(x, y) for x in range(2, 5) for y in range(4, 12)}
    assert set(got.values()) == {GREEN}


def test_paint_reel_mid_travel_shows_two_symbols_and_a_gap():
    got, set_px = _record()
    paint_reel(set_px, _two(), BAND, 5.0, 1.0, W, H, WIN)
    rows = _rows(got)
    assert rows[9] == RED and rows[11] == RED
    assert rows[4] == GREEN and rows[6] == GREEN
    assert 7 not in rows and 8 not in rows


def test_paint_reel_overshoot_dips_and_leaves_bg_above():
    got, set_px = _record()
    paint_reel(set_px, _two(), BAND, 11.0, 1.0, W, H, WIN)
    rows = _rows(got)
    assert 4 not in rows and all(rows[y] == GREEN for y in range(5, 12))


def test_paint_reel_shade_scales_rgb():
    got, set_px = _record()
    paint_reel(set_px, (_cell(RED, range(4, 12)),), BAND, 0.0, 0.6, W, H, WIN)
    assert set(got.values()) == {(120, 0, 0)}


def test_paint_reel_clips_to_window_and_panel():
    got, set_px = _record()
    tall = _cell(RED, range(0, 16))
    paint_reel(set_px, strip_symbols((tall, tall), 1), BAND, 3.0, 1.0, W, H, WIN)
    assert {y for _, y in got} <= set(range(4, 12))
    got2, set_px2 = _record()
    edge = strip_symbols(
        (_cell(RED, range(0, 4), slot=30), _cell(GREEN, range(0, 4), slot=30)), 1
    )
    paint_reel(set_px2, edge, BandGeom(0, 2, 3), 2.0, 1.0, W, H, (30, 3))
    assert got2
    # The [0, h) clip is defensive: a band built from lit pixels always lies
    # inside the panel.
    assert all(0 <= x < W and 0 <= y < H for x, y in got2)


def test_paint_reel_only_visits_visible_symbols():
    calls = []

    class _Cell:
        slot, width = 2, 3

        @property
        def rows(self):
            calls.append(1)
            return {}

    strip = tuple(_Cell() for _ in range(71))
    paint_reel(lambda *a: None, strip, BAND, 350.0, 1.0, W, H, WIN)  # type: ignore[arg-type]
    assert len(calls) <= 3


def test_paint_reel_clips_to_window_columns():
    got, set_px = _record()
    wide = _cell(RED, range(4, 12), slot=2, width=12)
    strip = strip_symbols((wide, _cell(GREEN, range(4, 12), slot=2, width=12)), 1)
    paint_reel(set_px, strip, BAND, 3.0, 1.0, W, H, (5, 4))
    assert got
    assert all(5 <= x < 9 for x, _ in got)


def test_paint_reel_centres_symbols_in_window():
    got, set_px = _record()
    cell = _cell(RED, range(4, 12), slot=2, width=3)
    paint_reel(set_px, (cell,), BAND, 0.0, 1.0, W, H, (20, 9))
    assert {x for x, _ in got} == {23, 24, 25}


def test_paint_reel_window_at_own_slot_is_exact():
    cell = _cell(RED, range(4, 12), slot=6, width=5)
    got, set_px = _record()
    paint_reel(set_px, (cell,), BAND, 0.0, 1.0, W, H, (cell.slot, cell.width))
    want, set_px2 = _record()
    paint_cell(set_px2, cell, W, H)
    assert got and set(got) == set(want)
