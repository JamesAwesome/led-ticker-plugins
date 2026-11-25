"""flair.slots — transition classes, reel timeline, registration.

Stub canvas / widget fixtures follow test_flair_splitflap_transition.py (the
per-file duplication is this repo's convention).
"""

import random
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import SNAP_THRESHOLD, ScaledCanvas, unwrap_to_real
from PIL import Image

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair._board_transition import LAND
from led_ticker_flair.flair.slots import (
    Slots,
    SlotsAlternating,
    SlotsRandom,
    SlotsReverse,
)

RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)


class _StubCanvas:
    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height
        self._pixels: dict[tuple[int, int], tuple[int, int, int]] = {}

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        self._pixels[(x, y)] = (r, g, b)

    def SubFill(  # noqa: N802
        self, x: int, y: int, w: int, h: int, r: int, g: int, b: int
    ) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self._pixels[(xx, yy)] = (r, g, b)

    def Clear(self) -> None:  # noqa: N802
        self._pixels.clear()

    def Fill(self, r: int, g: int, b: int) -> None:  # noqa: N802
        for y in range(self.height):
            for x in range(self.width):
                self._pixels[(x, y)] = (r, g, b)

    def SetImage(self, image: Any, offset_x: int = 0, offset_y: int = 0) -> None:  # noqa: N802
        pixels = image.load()
        w, h = image.size
        for y in range(h):
            for x in range(w):
                px = pixels[x, y]
                self.SetPixel(offset_x + x, offset_y + y, px[0], px[1], px[2])


def _widget(
    pixels: list[tuple[int, int, tuple[int, int, int]]], border: Any = None
) -> Any:
    widget = mock.Mock()
    widget.hold_time = 0.0
    widget.border = border
    widget.background = None
    widget.bottom_text = ""
    widget.top_row_height = None

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        for x, y, (r, g, b) in pixels:
            canvas.SetPixel(x, y, r, g, b)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


def _block(x0: int, x1: int, h: int, colour: tuple[int, int, int]) -> list:
    return [(x, y, colour) for x in range(x0, x1) for y in range(h)]


def _two_cells(colour: tuple[int, int, int]) -> Any:
    return _widget(_block(0, 3, 8, colour) + _block(10, 13, 8, colour))


def _frame(p: Any, t: float, c: Any, o: Any, i: Any, **kw: Any) -> dict:
    c.Clear()
    p.frame_at(t, c, o, i, **kw)
    return dict(c._pixels)


def _t(s: float) -> float:
    """Transition t for timeline position s (s = p / LAND)."""
    return s * LAND * SNAP_THRESHOLD


class TestKnobs:
    @pytest.mark.parametrize(
        "kw",
        [
            {"spins": -1},
            {"spins": True},
            {"spins": 1.5},
            {"spins": "3"},
            {"spins": 7},
            {"stagger": 0.95},
            {"stagger": -0.1},
            {"stagger": True},
        ],
    )
    def test_knob_validation(self, kw):
        with pytest.raises(ValueError):
            Slots(**kw)

    def test_defaults(self):
        p = Slots()
        assert (p.spins, p.stagger) == (3, 0.5)
        assert p.min_frames == 60 and p.scale_switch_at == 1.0
        assert Slots(spins=6).spins == 6

    def test_min_frames_follows_the_pace_floor(self):
        assert Slots().min_frames == 60
        assert Slots(spins=3, stagger=0.8).min_frames == 150
        assert SlotsAlternating(spins=3, stagger=0.8).min_frames == 150


class TestFrames:
    def test_t0_paints_outgoing_exactly(self):
        c = _StubCanvas(16, 8)
        o = _two_cells(RED)
        px = _frame(Slots(), 0.0, c, o, _two_cells(GREEN))
        ref = _StubCanvas(16, 8)
        o.draw(ref)
        assert px == ref._pixels

    def test_snap_draws_incoming(self, monkeypatch):
        calls: list[Any] = []
        monkeypatch.setattr(
            "led_ticker_flair.flair._board_transition.snap_reset",
            lambda cv, bg: calls.append(bg),
        )
        c = _StubCanvas(16, 8)
        i = _two_cells(GREEN)
        Slots().frame_at(
            SNAP_THRESHOLD, c, _two_cells(RED), i, incoming_bg_color=(9, 9, 9)
        )
        assert calls == [(9, 9, 9)]
        assert i.draw.call_args.kwargs["cursor_pos"] == 0
        assert set(c._pixels.values()) == {GREEN}

    def test_all_landed_before_snap(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = Slots()
        p.frame_at(0.0, c, o, i)
        px = _frame(p, 0.92 * SNAP_THRESHOLD, c, o, i)
        ref = _StubCanvas(16, 8)
        i.draw(ref)
        assert px == ref._pixels

    def test_all_reels_start_together(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = Slots(spins=0, stagger=0.5)
        at0 = _frame(p, 0.0, c, o, i)
        early = _frame(p, _t(0.1), c, o, i)
        left = lambda px: {k: v for k, v in px.items() if k[0] < 5}  # noqa: E731
        right = lambda px: {k: v for k, v in px.items() if k[0] >= 10}  # noqa: E731
        assert left(early) != left(at0) and right(early) != right(at0)

    def test_forward_left_reel_stops_first(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = Slots(spins=0, stagger=0.5)
        p.frame_at(0.0, c, o, i)
        px = _frame(p, _t(0.5), c, o, i)
        assert all(px[(x, y)] == GREEN for x in range(3) for y in range(8))
        right = {k: v for k, v in px.items() if k[0] >= 10}
        assert right != {(x, y): RED for x in range(10, 13) for y in range(8)}
        assert right != {(x, y): GREEN for x in range(10, 13) for y in range(8)}

    def test_reverse_right_reel_stops_first(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = SlotsReverse(spins=0, stagger=0.5)
        p.frame_at(0.0, c, o, i)
        px = _frame(p, _t(0.5), c, o, i)
        assert all(px[(x, y)] == GREEN for x in range(10, 13) for y in range(8))
        left = {k: v for k, v in px.items() if k[0] < 5}
        assert left != {(x, y): RED for x in range(3) for y in range(8)}
        assert left != {(x, y): GREEN for x in range(3) for y in range(8)}

    def test_high_stagger_first_reel_lands_exactly(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = Slots(spins=0, stagger=0.9)
        p.frame_at(0.0, c, o, i)
        px = _frame(p, _t(0.1), c, o, i)
        assert all(px[(x, y)] == GREEN for x in range(3) for y in range(8))

    def test_overshoot_dips_incoming_by_one_row(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = Slots(spins=0, stagger=0.0)
        p.frame_at(0.0, c, o, i)
        px = _frame(p, _t(0.95), c, o, i)
        assert (1, 0) not in px and all(px[(1, y)] == GREEN for y in range(1, 8))

    def test_mid_spin_is_dimmed(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = Slots(spins=0, stagger=0.0)
        p.frame_at(0.0, c, o, i)
        px = _frame(p, _t(0.3), c, o, i)
        reds = {v for v in px.values() if v[1] == 0 and v[2] == 0}
        assert reds and all(0 < r < 255 for r, _, _ in reds)

    def test_long_reel_cycles_in_betweens(self):
        p = Slots(spins=3, stagger=0.9)
        c = _StubCanvas(40, 8)
        o = _widget(
            _block(0, 3, 8, RED) + _block(10, 13, 8, GREEN) + _block(20, 23, 8, BLUE)
        )
        i = _widget(
            _block(0, 3, 8, GREEN) + _block(10, 13, 8, BLUE) + _block(20, 23, 8, RED)
        )
        p.frame_at(0.0, c, o, i)
        last = max(p._reels, key=lambda r: r.stop)
        assert last.k == 40 and len(last.strip) == 41
        mids = last.strip[1:-1]
        assert len({id(m) for m in mids}) < len(mids)

    def test_both_empty_paints_nothing_until_snap(self):
        c = _StubCanvas(16, 8)
        o, i = _widget([]), _widget([])
        p = Slots()
        for t in (0.0, 0.3, 0.6, 0.9):
            assert _frame(p, t, c, o, i) == {}

    def test_empty_outgoing_spins_from_blank(self):
        c = _StubCanvas(16, 8)
        o, i = _widget([]), _two_cells(GREEN)
        p = Slots()
        assert _frame(p, 0.0, c, o, i) == {}
        assert set(_frame(p, 0.92 * SNAP_THRESHOLD, c, o, i).values()) == {GREEN}

    def test_border_ring_static(self):
        ring = [(x, 0, BLUE) for x in range(16)] + [(x, 7, BLUE) for x in range(16)]
        ring += [(0, y, BLUE) for y in range(8)] + [(15, y, BLUE) for y in range(8)]
        border = SimpleNamespace(thickness=1)
        inner = range(2, 6)
        o = _widget(ring + [(x, y, RED) for x in range(3, 6) for y in inner], border)
        i = _widget(ring + [(x, y, GREEN) for x in range(9, 12) for y in inner], border)
        c = _StubCanvas(16, 8)
        p = Slots()
        p.frame_at(0.0, c, o, i)
        for t in (0.1, 0.4, 0.7):
            px = _frame(p, t, c, o, i)
            assert all(px.get((x, y)) == BLUE for x, y, _ in ring)

    def test_image_widget_spins_as_strips(self):
        img = Image.new("RGB", (32, 8), (200, 40, 40))
        widget = mock.Mock()
        widget.hold_time = 0.0
        widget.border = None
        widget.background = None
        widget.bottom_text = ""

        def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
            unwrap_to_real(canvas).SetImage(img, 0, 0)
            return (canvas, cursor_pos)

        widget.draw.side_effect = _draw
        c = _StubCanvas(32, 8)
        p = Slots(spins=0)
        p.frame_at(0.0, c, widget, _two_cells(GREEN))
        assert p._board is not None and len(p._board.flaps) > 2

    def test_unchanged_cell_stays_put_and_undimmed(self):
        c = _StubCanvas(16, 8)
        same = _block(0, 3, 8, RED)
        o = _widget(same + _block(10, 13, 8, GREEN))
        i = _widget(same + _block(10, 13, 8, BLUE))
        p = Slots()
        start = _frame(p, 0.0, c, o, i)
        left = lambda px: {k: v for k, v in px.items() if k[0] < 5}  # noqa: E731
        changed = False
        for k in range(1, p.min_frames):
            t = k / p.min_frames * SNAP_THRESHOLD
            px = _frame(p, t, c, o, i)
            assert left(px) == left(start)
            changed |= {k: v for k, v in px.items() if k[0] >= 5} != {
                k: v for k, v in start.items() if k[0] >= 5
            }
        assert changed

    def test_shade_ramps_without_a_pop(self, monkeypatch):
        from led_ticker.plugin import TickerMessage

        from led_ticker_flair.flair import slots as slots_module

        calls: list[tuple[int, float]] = []
        real_paint = slots_module.paint_reel

        def spy(set_px, strip, band, d, shade, w, h, window):
            calls.append((id(strip), shade))
            real_paint(set_px, strip, band, d, shade, w, h, window)

        monkeypatch.setattr(slots_module, "paint_reel", spy)
        c = _StubCanvas(160, 16)
        o, i = TickerMessage(text="ABCDEFG"), TickerMessage(text="HIJKLMN")
        p = Slots()
        n = p.min_frames
        frames: list[dict[int, float]] = []
        for k in range(n):
            t = k / (n - 1)
            if t >= SNAP_THRESHOLD:
                break
            calls.clear()
            c.Clear()
            p.frame_at(t, c, o, i)
            frames.append(dict(calls))
        assert len(frames) > 2 and frames[0]
        assert all(v == 1.0 for v in frames[0].values())
        assert all(v == 1.0 for v in frames[-1].values())
        for a, b in zip(frames, frames[1:], strict=False):
            for key in a:
                assert abs(b[key] - a[key]) <= 0.15


class TestReelWindows:
    @staticmethod
    def _walk(monkeypatch, out_text="WIN", in_text="PULL LEVER"):
        """Per pre-snap frame: [(window, written xs, strip)] per reel painted."""
        from led_ticker.plugin import TickerMessage

        from led_ticker_flair.flair import slots as slots_module

        frames: list[list[tuple[tuple[int, int, float], list[int], tuple]]] = []
        real_paint = slots_module.paint_reel

        def spy(set_px, strip, band, d, shade, w, h, window):
            xs: list[int] = []

            def rec(x, y, r, g, b):
                xs.append(x)
                set_px(x, y, r, g, b)

            frames[-1].append((window, xs, strip))
            real_paint(rec, strip, band, d, shade, w, h, window)

        monkeypatch.setattr(slots_module, "paint_reel", spy)
        c = _StubCanvas(160, 16)
        o, i = TickerMessage(text=out_text), TickerMessage(text=in_text)
        p = Slots()
        n = p.min_frames
        for k in range(n):
            t = k / (n - 1)
            if t >= SNAP_THRESHOLD:
                break
            frames.append([])
            c.Clear()
            p.frame_at(t, c, o, i)
        return frames

    def test_reel_pixels_stay_inside_reel_windows(self, monkeypatch):
        frames = self._walk(monkeypatch)
        assert len(frames) > 2
        painted = 0
        for calls in frames:
            for (wl, ww, _cx), xs, _ in calls:
                painted += len(xs)
                assert all(wl <= x < wl + ww for x in xs)
        assert painted

    @pytest.mark.parametrize(
        ("out_text", "in_text"), [("WIN", "PULL LEVER"), ("PULL LEVER", "WIN")]
    )
    def test_reel_windows_disjoint_at_start_and_landing(
        self, monkeypatch, out_text, in_text
    ):
        frames = self._walk(monkeypatch, out_text, in_text)

        def disjoint(calls):
            spans = sorted((wl, wl + ww) for (wl, ww, _cx), _, _ in calls)
            return all(a[1] <= b[0] for a, b in zip(spans, spans[1:], strict=False))

        assert frames[0] and disjoint(frames[0])
        assert disjoint(frames[-1])
        assert all(disjoint(f) for f in frames)

    def test_blank_ends_are_zero_width_windows(self, monkeypatch):
        starts = ends = 0
        for out_text, in_text in [("WIN", "PULL LEVER"), ("PULL LEVER", "WIN")]:
            frames = self._walk(monkeypatch, out_text, in_text)
            for (wl, ww, _cx), _, strip in frames[0]:
                if strip[0] is None:
                    starts += 1
                    last = strip[-1]
                    assert (wl, ww) == (last.slot + last.width // 2, 0)
            for (wl, ww, _cx), _, strip in frames[-1]:
                if strip[-1] is None:
                    ends += 1
                    first = strip[0]
                    assert (wl, ww) == (first.slot + first.width // 2, 0)
        assert starts and ends


class TestVariantsRegistration:
    def test_alternating_cycles_forward_reverse(self):
        c = _StubCanvas(16, 8)
        p = SlotsAlternating()
        kinds = []
        for _ in range(3):
            p.frame_at(0.0, c, _two_cells(RED), _two_cells(GREEN))
            kinds.append(type(p._transitions[p._index]))
        assert kinds == [Slots, SlotsReverse, Slots]
        assert p.min_frames == 60 and p.scale_switch_at == 1.0

    def test_random_order_seeded_reproducible(self):
        def run(seed: int) -> dict:
            c = _StubCanvas(16, 8)
            p = SlotsRandom(spins=0)
            p._rng = random.Random(seed)
            p.frame_at(0.0, c, _two_cells(RED), _two_cells(GREEN))
            return _frame(p, _t(0.4), c, _two_cells(RED), _two_cells(GREEN))

        assert run(5) == run(5)

    def test_random_stop_order_differs_between_seeds(self):
        def landed_left(seed: int) -> bool:
            c = _StubCanvas(16, 8)
            p = SlotsRandom(spins=0, stagger=0.9)
            p._rng = random.Random(seed)
            p.frame_at(0.0, c, _two_cells(RED), _two_cells(GREEN))
            px = _frame(p, _t(0.5), c, _two_cells(RED), _two_cells(GREEN))
            return all(px.get((x, y)) == GREEN for x in range(3) for y in range(8))

        assert len({landed_left(seed) for seed in range(8)}) == 2

    def test_registration_four_types(self):
        api = mock.Mock()
        reg: dict[str, Any] = {}
        api.transition.side_effect = lambda name: (
            lambda cls: reg.__setitem__(name, cls) or cls
        )
        api.animation.side_effect = lambda name: lambda cls: cls
        api.background.side_effect = lambda name: lambda cls: cls
        api.widget.side_effect = lambda name: lambda cls: cls
        flair_pkg.register(api)
        assert reg["slots.forward"] is Slots
        assert reg["slots.reverse"] is SlotsReverse
        assert reg["slots.alternating"] is SlotsAlternating
        assert reg["slots.random"] is SlotsRandom


class TestRealCoreWidgets:
    @staticmethod
    def _run(p: Any, canvas: Any, real: Any, outgoing: Any, incoming: Any) -> None:
        for k in range(21):
            real.Clear()
            p.frame_at(k / 20, canvas, outgoing, incoming)
        real.Clear()
        p.frame_at(0.0, canvas, outgoing, incoming)
        real.Clear()
        p.frame_at(0.92 * SNAP_THRESHOLD, canvas, outgoing, incoming)
        landed = {k: v for k, v in real._pixels.items() if v != (0, 0, 0)}
        real.Clear()
        p.frame_at(0.96, canvas, outgoing, incoming)
        snap = {k: v for k, v in real._pixels.items() if v != (0, 0, 0)}
        assert snap and landed == snap

    def test_ticker_message_scale_1(self):
        from led_ticker.plugin import TickerMessage

        c = _StubCanvas(160, 16)
        self._run(
            Slots(),
            c,
            c,
            TickerMessage(text="NOW BOARDING"),
            TickerMessage(text="GATE 12"),
        )

    def test_ticker_message_scaled(self):
        from led_ticker.plugin import TickerMessage

        real = _StubCanvas(256, 64)
        sc = ScaledCanvas(real, scale=4, content_height=16)
        self._run(
            SlotsReverse(),
            sc,
            real,
            TickerMessage(text="ON TIME"),
            TickerMessage(text="DELAYED 10"),
        )

    def test_two_row_to_message_scaled(self):
        from led_ticker.plugin import TickerMessage, TwoRowMessage

        real = _StubCanvas(256, 64)
        sc = ScaledCanvas(real, scale=2, content_height=32)
        self._run(
            SlotsRandom(),
            sc,
            real,
            TwoRowMessage(top_text="FRESH", bottom_text="COFFEE"),
            TickerMessage(text="OPEN"),
        )

    def test_message_to_gif_scaled(self, tmp_path):
        from led_ticker.plugin import TickerMessage
        from led_ticker.widgets.gif import GifPlayer

        frame = Image.new("RGB", (32, 16), (0, 0, 0))
        for x in range(4, 28):
            for y in range(4, 12):
                frame.putpixel((x, y), (200, 40, 40))
        path = tmp_path / "bar.gif"
        frame.save(path, save_all=True, append_images=[frame], duration=100)
        real = _StubCanvas(256, 64)
        sc = ScaledCanvas(real, scale=4, content_height=16)
        self._run(
            Slots(),
            sc,
            real,
            TickerMessage(text="GIF"),
            GifPlayer(path=str(path), fit="stretch"),
        )


class TestPerf:
    """One full firing at bigsign / longboi size. Mac timings: board build
    (first frame) ~22 ms at 256x64 and ~52 ms at 512x64 for a full-panel
    noise picture, 3-6 ms per frame after at 256 / 512 wide. Bounds are ~10x headroom so
    CI noise doesn't flake, while a quadratic regression (seconds) trips."""

    @staticmethod
    def _noise_widget(w: int, h: int, seed: int) -> Any:
        rng = random.Random(seed)
        img = Image.new("RGB", (w, h))
        img.putdata(
            [(rng.randrange(1, 256), rng.randrange(256), 0) for _ in range(w * h)]
        )
        widget = mock.Mock()
        widget.hold_time = 0.0
        widget.border = None
        widget.background = None
        widget.bottom_text = ""

        def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
            unwrap_to_real(canvas).SetImage(img, 0, 0)
            return (canvas, cursor_pos)

        widget.draw.side_effect = _draw
        return widget

    @pytest.mark.parametrize("kw", [{}, {"spins": 6, "stagger": 0.9}])
    @pytest.mark.parametrize("w", [256, 512])
    def test_perf_full_panel_picture_firing(self, w, kw):
        import time

        real = _StubCanvas(w, 64)
        sc = ScaledCanvas(real, scale=4, content_height=16)
        o, i = self._noise_widget(w, 64, 1), self._noise_widget(w, 64, 2)
        p = Slots(**kw)
        t0 = time.perf_counter()
        p.frame_at(0.0, sc, o, i)
        first = time.perf_counter() - t0
        worst = 0.0
        for k in range(1, 60):
            t0 = time.perf_counter()
            p.frame_at(k / 60 * SNAP_THRESHOLD, sc, o, i)
            worst = max(worst, time.perf_counter() - t0)
        assert first < 0.6
        assert worst < 0.05

    def test_perf_text_firing(self):
        import time

        from led_ticker.plugin import TickerMessage

        real = _StubCanvas(256, 64)
        sc = ScaledCanvas(real, scale=4, content_height=16)
        o = TickerMessage(text="NOW BOARDING")
        i = TickerMessage(text="GATE 12 ON TIME")
        p = Slots(spins=6, stagger=0.9)
        t0 = time.perf_counter()
        for k in range(36):
            p.frame_at(k / 36 * SNAP_THRESHOLD, sc, o, i)
        assert time.perf_counter() - t0 < 0.5
