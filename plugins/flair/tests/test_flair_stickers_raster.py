"""Rasterization tests — capture via a recording stub, die-cut, cache."""

from led_ticker_flair.flair.stickers import (
    BACKING_PAD,
    OUTLINE_PAD,
    StickerRaster,
    capture_sprite,
    compose_sticker,
    dilate,
)


class TestCapture:
    def test_lowres_taco_captures_pixels_at_origin(self):
        px = capture_sprite("taco", scale=1, content_height=None)
        assert px, "sprite must capture lit pixels"
        xs = [p[0] for p in px]
        ys = [p[1] for p in px]
        assert min(xs) == 0 and min(ys) == 0, "bbox-normalized to origin"
        # Emoji may vary in size; just check it's reasonable
        assert max(xs) >= 4 and max(ys) >= 4

    def test_hires_taco_is_bigger_than_lowres(self):
        low = capture_sprite("taco", scale=1, content_height=None)
        hi = capture_sprite("taco", scale=4, content_height=16)
        assert len(hi) > len(low) * 4


class TestDieCut:
    def test_compose_layers(self):
        sprite = {(2, 2): (200, 100, 0)}
        out = compose_sticker(sprite)
        assert out[(2, 2)] == (200, 100, 0)  # sprite on top
        assert out[(1, 1)] == (0, 0, 0)  # black fill ring
        assert out[(2 - OUTLINE_PAD, 2)] == (255, 255, 255)  # white rim
        fill = dilate({(2, 2)}, BACKING_PAD)
        rim = dilate({(2, 2)}, OUTLINE_PAD) - fill
        assert set(out) == fill | rim | {(2, 2)}


class TestRasterCache:
    def test_angle_quantization_shares_entries(self, monkeypatch):
        calls = []
        import led_ticker_flair.flair.stickers as m

        real = m.capture_sprite
        monkeypatch.setattr(
            m, "capture_sprite", lambda *a, **k: calls.append(a) or real(*a, **k)
        )
        cache = StickerRaster()
        cache.get("taco", 4.4, 1, None)
        cache.get("taco", 3.6, 1, None)  # both quantize to 4 degrees
        assert len(calls) == 1
