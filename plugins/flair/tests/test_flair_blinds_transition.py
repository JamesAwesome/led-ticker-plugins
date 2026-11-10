"""flair.blinds — Blinds transition classes.

Stub canvas / widget fixtures copied from test_flair_laser_transition.py
(the per-file duplication is this repo's convention); this copy's SubFill
records ONE call so the perf bound counts a band fill once.
"""

from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import ScaledCanvas, unwrap_to_real
from PIL import Image

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.blinds import (
    Blinds,
    BlindsAlternating,
    BlindsLeft,
    BlindsRandom,
    BlindsRight,
    BlindsUp,
)


class _StubCanvas:
    """Minimal scale=1 real-canvas stub."""

    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height
        self._pixels: dict[tuple[int, int], tuple[int, int, int]] = {}
        self.calls: list[tuple[int, int, int, int, int]] = []
        self.subfills: list[tuple[int, int, int, int, tuple[int, int, int]]] = []

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        self._pixels[(x, y)] = (r, g, b)
        self.calls.append((x, y, r, g, b))

    def SubFill(  # noqa: N802
        self, x: int, y: int, w: int, h: int, r: int, g: int, b: int
    ) -> None:
        self.subfills.append((x, y, w, h, (r, g, b)))
        self.calls.append((x, y, r, g, b))  # one call, not w*h (perf counting)
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self._pixels[(xx, yy)] = (r, g, b)

    def Clear(self) -> None:  # noqa: N802
        self._pixels.clear()
        self.subfills.clear()

    def Fill(self, r: int, g: int, b: int) -> None:  # noqa: N802
        for y in range(self.height):
            for x in range(self.width):
                self.SetPixel(x, y, r, g, b)

    def SetImage(self, image: Any, offset_x: int = 0, offset_y: int = 0) -> None:  # noqa: N802
        pixels = image.load()
        w, h = image.size
        for y in range(h):
            for x in range(w):
                px = pixels[x, y]
                if len(px) == 4 and px[3] == 0:
                    r, g, b = 0, 0, 0
                else:
                    r, g, b = px[0], px[1], px[2]
                self.SetPixel(offset_x + x, offset_y + y, r, g, b)


def _make_widget(draw_pixel: bool = True, fill: Any = None) -> Any:
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        if fill is not None:
            canvas.Fill(*fill)
        if draw_pixel:
            canvas.SetPixel(0, 0, 255, 0, 0)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


def _text_widget(pixels: list[tuple[int, int, tuple[int, int, int]]]) -> Any:
    """A widget that SetPixels a fixed list onto whatever canvas it gets."""
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        for x, y, (r, g, b) in pixels:
            canvas.SetPixel(x, y, r, g, b)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


def _image_widget(img: Any) -> Any:
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        unwrap_to_real(canvas).SetImage(img, 0, 0)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


RED = (255, 0, 0)
GREEN = (0, 255, 0)


def _solid(w: int, h: int, colour: tuple[int, int, int]) -> Any:
    return _text_widget([(x, y, colour) for x in range(w) for y in range(h)])


def _frame(p: Any, t: float, c: Any, o: Any, i: Any, **kw: Any) -> dict:
    c.Clear()
    p.frame_at(t, c, o, i, **kw)
    return dict(c._pixels)


def _rows(px: dict, h: int, x: int = 0) -> list[Any]:
    return [px.get((x, y)) for y in range(h)]


def _cols(px: dict, w: int, y: int = 0) -> list[Any]:
    return [px.get((x, y)) for x in range(w)]


class TestBlindsFrames:
    def test_t0_outgoing_only_no_reveal(self):
        c = _StubCanvas(4, 16)
        px = _frame(Blinds(), 0.0, c, _solid(4, 16, RED), _solid(4, 16, GREEN))
        assert set(px.values()) == {RED}
        assert c.subfills == []

    def test_mid_frame_down_reveals_top_of_each_slat(self):
        c = _StubCanvas(4, 16)
        o, i = _solid(4, 16, RED), _solid(4, 16, GREEN)
        p = Blinds(slats=4)  # 4 slats of 4 rows
        p.frame_at(0.0, c, o, i)
        px = _frame(p, 0.475, c, o, i)  # p = 0.5 -> 2 rows per slat
        assert _rows(px, 16) == [GREEN, GREEN, RED, RED] * 4

    def test_up_reveals_bottom_of_each_slat(self):
        c = _StubCanvas(4, 16)
        o, i = _solid(4, 16, RED), _solid(4, 16, GREEN)
        p = BlindsUp(slats=4)
        p.frame_at(0.0, c, o, i)
        px = _frame(p, 0.475, c, o, i)
        assert _rows(px, 16) == [RED, RED, GREEN, GREEN] * 4

    def test_right_and_left_use_columns(self):
        c = _StubCanvas(16, 2)
        o, i = _solid(16, 2, RED), _solid(16, 2, GREEN)
        p = BlindsRight(slats=4)
        p.frame_at(0.0, c, o, i)
        assert _cols(_frame(p, 0.475, c, o, i), 16) == [GREEN, GREEN, RED, RED] * 4
        p = BlindsLeft(slats=4)
        p.frame_at(0.0, c, o, i)
        assert _cols(_frame(p, 0.475, c, o, i), 16) == [RED, RED, GREEN, GREEN] * 4

    def test_revealed_band_gets_incoming_bg(self):
        c = _StubCanvas(4, 16)
        blank = _make_widget(draw_pixel=False)
        p = Blinds(slats=4)
        p.frame_at(0.0, c, blank, blank)
        px = _frame(p, 0.475, c, blank, blank, incoming_bg_color=(10, 20, 30))
        assert (0, 0, 4, 2, (10, 20, 30)) in c.subfills
        assert (
            _rows(px, 16)
            == [(10, 20, 30)] * 2 + [None] * 2 + ([(10, 20, 30)] * 2 + [None] * 2) * 3
        )

    def test_revealed_band_black_when_incoming_bg_none(self):
        c = _StubCanvas(4, 16)
        blank = _make_widget(draw_pixel=False)
        p = Blinds()
        p.frame_at(0.0, c, blank, blank)
        _frame(p, 0.475, c, blank, blank)
        assert c.subfills and all(f[4] == (0, 0, 0) for f in c.subfills)

    def test_snap_draws_incoming_over_bg(self, monkeypatch):
        calls: list[Any] = []
        monkeypatch.setattr(
            "led_ticker_flair.flair.blinds.snap_reset",
            lambda cv, bg: calls.append(bg),
        )
        c = _StubCanvas(4, 16)
        i = _solid(4, 16, GREEN)
        Blinds().frame_at(0.96, c, _solid(4, 16, RED), i, incoming_bg_color=(9, 9, 9))
        assert calls[-1] == (9, 9, 9)
        assert set(c._pixels.values()) == {GREEN}

    def test_outgoing_not_drawn_live_after_snapshot(self):
        c = _StubCanvas(4, 16)
        o, i = _solid(4, 16, RED), _solid(4, 16, GREEN)
        p = Blinds()
        for t in (0.0, 0.2, 0.4, 0.6, 0.9):
            p.frame_at(t, c, o, i)
        assert o.draw.call_count == 1
        assert i.draw.call_count == 1

    def test_t0_always_starts_a_new_firing(self):
        c = _StubCanvas(4, 16)
        p = Blinds()
        p.frame_at(0.0, c, _solid(4, 16, RED), _solid(4, 16, GREEN))
        px = _frame(p, 0.0, c, _solid(4, 16, GREEN), _solid(4, 16, RED))
        assert set(px.values()) == {GREEN}

    def test_equal_t_is_not_a_refire(self):
        c = _StubCanvas(4, 16)
        p = Blinds()
        p.frame_at(0.3, c, _solid(4, 16, RED), _solid(4, 16, GREEN))
        ref = p._plan
        p.frame_at(0.3, c, _solid(4, 16, RED), _solid(4, 16, GREEN))
        assert p._plan is ref

    def test_image_widget_snapshots_through_setimage(self):
        img = Image.new("RGB", (4, 16), (0, 0, 0))
        img.putpixel((1, 0), (10, 20, 30))
        c = _StubCanvas(4, 16)
        blank = _make_widget(draw_pixel=False)
        p = Blinds()
        p.frame_at(0.0, c, blank, _image_widget(img))
        px = _frame(p, 0.475, c, blank, _image_widget(img))
        assert px[(1, 0)] == (10, 20, 30)

    def test_scaled_slats_snap_to_logical_rows(self):
        real = _StubCanvas(8, 64)
        sc = ScaledCanvas(real, scale=4, content_height=16)

        def _real_solid(colour: tuple[int, int, int]) -> Any:
            w = mock.Mock()

            def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> Any:
                r = unwrap_to_real(canvas)
                for y in range(64):
                    for x in range(8):
                        r.SetPixel(x, y, *colour)
                return canvas, cursor_pos

            w.draw.side_effect = _draw
            return w

        o, i = _real_solid(RED), _real_solid(GREEN)
        p = Blinds(slats=4)  # 4 slats of 16 real rows
        p.frame_at(0.0, sc, o, i)
        real.Clear()
        p.frame_at(0.475, sc, o, i)  # 8 real rows revealed per slat
        col = [real._pixels.get((0, y)) for y in range(64)]
        assert col == ([GREEN] * 8 + [RED] * 8) * 4


class TestKnobsVariantsRegistration:
    def test_default_slats_by_orientation(self):
        assert Blinds().slats == 8
        assert BlindsUp().slats == 8
        assert BlindsRight().slats == 8
        assert [s.slats for s in BlindsAlternating()._transitions] == [8, 8, 8, 8]
        assert [s.slats for s in BlindsAlternating(slats=6)._transitions] == [6] * 4
        assert [s.slats for s in BlindsRandom(slats=6)._transitions] == [6] * 4

    @pytest.mark.parametrize("bad", [0, -1, True, 1.5, "4"])
    def test_slats_validation(self, bad):
        with pytest.raises(ValueError, match="slats"):
            Blinds(slats=bad)

    def test_registration_six_types_distinct_instances(self):
        api = mock.Mock()
        reg: dict[str, Any] = {}
        api.transition.side_effect = lambda name: (
            lambda cls: reg.__setitem__(name, cls) or cls
        )
        api.animation.side_effect = lambda name: lambda cls: cls
        api.background.side_effect = lambda name: lambda cls: cls
        api.widget.side_effect = lambda name: lambda cls: cls
        flair_pkg.register(api)
        assert reg["blinds.down"] is Blinds
        assert reg["blinds.up"] is BlindsUp
        assert reg["blinds.right"] is BlindsRight
        assert reg["blinds.left"] is BlindsLeft
        assert reg["blinds.alternating"] is BlindsAlternating
        assert reg["blinds.random"] is BlindsRandom
        assert reg["blinds.down"]() is not reg["blinds.down"]()

    def test_alternating_cycles_down_right_up_left(self):
        c = _StubCanvas(4, 16)
        p = BlindsAlternating()
        seen = []
        for _ in range(5):
            p.frame_at(0.0, c, _solid(4, 16, RED), _solid(4, 16, GREEN))
            seen.append(p._transitions[p._index]._direction)
            p.frame_at(0.96, c, _solid(4, 16, RED), _solid(4, 16, GREEN))
        assert seen == ["down", "right", "up", "left", "down"]

    def test_random_never_repeats_back_to_back(self):
        c = _StubCanvas(4, 16)
        p = BlindsRandom()
        p._rng.seed(1)
        seen = []
        for _ in range(30):
            p.frame_at(0.0, c, _solid(4, 16, RED), _solid(4, 16, GREEN))
            seen.append(p._transitions[p._index]._direction)
            p.frame_at(0.96, c, _solid(4, 16, RED), _solid(4, 16, GREEN))
        assert all(a != b for a, b in zip(seen, seen[1:], strict=False))
        assert len(set(seen)) >= 3

    def test_min_frames_16_on_every_type(self):
        for cls in (Blinds, BlindsUp, BlindsRight, BlindsLeft):
            assert cls.min_frames == 16
        assert BlindsAlternating().min_frames == 16
        assert BlindsRandom().min_frames == 16

    def test_scale_switch_at_is_1(self):
        assert Blinds.scale_switch_at == 1.0


class TestPerfUniformity:
    """Count WORK per frame (SubFill counted once), lightning convention."""

    @staticmethod
    def _sweep(p: Any, canvas: Any, real: Any, o: Any, i: Any, panel: int) -> None:
        t = 0.0
        while t < 1.0:
            before = len(real.calls)
            p.frame_at(round(t, 3), canvas, o, i)
            n = len(real.calls) - before
            assert n <= int(1.5 * panel), f"t={t:.2f} painted {n} px"
            t += 0.02

    def test_per_frame_paint_volume_bounded(self):
        c = _StubCanvas(160, 16)
        self._sweep(
            Blinds(), c, c, _solid(160, 16, RED), _solid(160, 16, GREEN), 160 * 16
        )

    def test_alternating_refire_frames_equally_bounded(self):
        c = _StubCanvas(160, 16)
        p = BlindsAlternating()
        o, i = _solid(160, 16, RED), _solid(160, 16, GREEN)
        for t in (0.0, 0.6, 0.96):
            p.frame_at(t, c, o, i)
        self._sweep(p, c, c, o, i, 160 * 16)

    def test_full_panel_fill_within_paint_bound(self):
        real = _StubCanvas(256, 64)
        sc = ScaledCanvas(real, scale=4, content_height=16)
        full = _make_widget(draw_pixel=False, fill=(7, 7, 7))
        self._sweep(Blinds(), sc, real, full, full, 256 * 64)


class TestRealCoreWidgets:
    @staticmethod
    def _revealed_vs_snap(p: Any, canvas: Any, real: Any, incoming: Any) -> None:
        blank = _make_widget(draw_pixel=False)
        p.frame_at(0.0, canvas, blank, incoming)
        real.Clear()
        p.frame_at(0.9499, canvas, blank, incoming)  # p rounds to fully open
        opened = {k: v for k, v in real._pixels.items() if v != (0, 0, 0)}
        real.Clear()
        p.frame_at(0.96, canvas, blank, incoming)
        snap = {k: v for k, v in real._pixels.items() if v != (0, 0, 0)}
        assert snap
        assert opened == snap

    def test_ticker_message_scale_1(self):
        from led_ticker.plugin import TickerMessage

        c = _StubCanvas(160, 16)
        self._revealed_vs_snap(Blinds(), c, c, TickerMessage(text="BLINDS"))

    def test_ticker_message_scaled(self):
        from led_ticker.plugin import TickerMessage

        real = _StubCanvas(256, 64)
        sc = ScaledCanvas(real, scale=4, content_height=16)
        self._revealed_vs_snap(Blinds(), sc, real, TickerMessage(text="BLINDS"))
