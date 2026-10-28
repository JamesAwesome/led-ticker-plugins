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
