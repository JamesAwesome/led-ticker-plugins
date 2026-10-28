"""flair.laser — pure half: the readable `_Raster` snapshot surface and the
`raster_order` lit-pixel plan. No canvas/widget stubs needed here."""

from PIL import Image

from led_ticker_flair.flair.laser import _Raster


def test_raster_setpixel_get_and_oob_ignored():
    r = _Raster(4, 2)
    r.SetPixel(1, 1, 10, 20, 30)
    r.SetPixel(9, 9, 1, 1, 1)
    assert r.get(1, 1) == (10, 20, 30)
    assert r.get(0, 0) is None
    assert r.get(9, 9) is None


def test_raster_subfill_clips_and_clear_resets():
    r = _Raster(4, 2)
    r.SubFill(2, 0, 10, 10, 5, 5, 5)
    assert r.get(3, 1) == (5, 5, 5)
    assert r.get(1, 1) is None
    r.Clear()
    assert all(r.get(x, y) is None for x in range(4) for y in range(2))


def test_raster_fill_sets_every_slot():
    r = _Raster(3, 3)
    r.Fill(7, 8, 9)
    assert all(r.get(x, y) == (7, 8, 9) for x in range(3) for y in range(3))


def test_setimage_alpha_zero_is_unlit_and_clips():
    img = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
    img.putpixel((0, 0), (200, 100, 50, 255))
    img.putpixel((1, 0), (9, 9, 9, 0))  # transparent -> black
    r = _Raster(3, 1)
    r.SetImage(img, 1, 0)  # img x=0 lands at x=1; img x=2 is clipped
    assert r.get(1, 0) == (200, 100, 50)
    assert r.get(2, 0) == (0, 0, 0)
    assert r.get(0, 0) is None


# --- raster_order -----------------------------------------------------------

import pytest  # noqa: E402

from led_ticker_flair.flair.laser import raster_order  # noqa: E402


def _grid(rows):
    """'#' lit red, '.' unset, 'k' explicit black."""
    r = _Raster(len(rows[0]), len(rows))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "#":
                r.SetPixel(x, y, 255, 0, 0)
            if ch == "k":
                r.SetPixel(x, y, 0, 0, 0)
    return r


def _xy(px):
    return [(x, y) for x, y, _ in px]


def test_top_origin_rasters_rows_boustrophedon_skipping_empty():
    px, parity = raster_order(_grid(["#.#", "...", ".##"]), "top")
    assert _xy(px) == [(0, 0), (2, 0), (2, 2), (1, 2)]
    assert parity is True  # row 0 forward, row 2 backward -> next is forward


def test_bottom_origin_starts_at_last_row():
    px, _ = raster_order(_grid(["#..", "..#"]), "bottom")
    assert _xy(px) == [(2, 1), (0, 0)]


def test_left_origin_rasters_columns():
    px, _ = raster_order(_grid(["#.", "##"]), "left")
    assert _xy(px) == [(0, 0), (0, 1), (1, 1)]


def test_right_origin_starts_at_last_column():
    px, _ = raster_order(_grid(["#.", "##"]), "right")
    assert _xy(px) == [(1, 1), (0, 1), (0, 0)]


def test_black_and_unset_are_unlit():
    px, _ = raster_order(_grid(["k#."]), "top")
    assert _xy(px) == [(1, 0)]


def test_lit_pixels_carry_their_colour():
    px, _ = raster_order(_grid(["#"]), "top")
    assert px == [(0, 0, (255, 0, 0))]


def test_forward_first_false_reverses_first_line():
    px, parity = raster_order(_grid(["##"]), "top", forward_first=False)
    assert _xy(px) == [(1, 0), (0, 0)]
    assert parity is True


def test_empty_raster_returns_no_pixels_and_keeps_parity():
    assert raster_order(_Raster(2, 2), "left", forward_first=False) == ([], False)


def test_unknown_origin_raises():
    with pytest.raises(ValueError, match="origin"):
        raster_order(_Raster(1, 1), "diagonal")
