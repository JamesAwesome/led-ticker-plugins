"""flair.splitflap — transition classes, timeline, registration.

Stub canvas / widget fixtures follow test_flair_blinds_transition.py (the
per-file duplication is this repo's convention); widget stubs pin the
duck-typed border / background / two-row probes like the accordion tests.
"""

import random
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import SNAP_THRESHOLD, ScaledCanvas, unwrap_to_real
from PIL import Image

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.splitflap import (
    LAND,
    SplitFlap,
    SplitFlapAlternating,
    SplitFlapRandom,
    SplitFlapReverse,
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
            {"flips": -1},
            {"flips": True},
            {"flips": 1.5},
            {"flips": "3"},
            {"stagger": 0.95},
            {"stagger": -0.1},
            {"stagger": True},
            {"stagger": "x"},
        ],
    )
    def test_knob_validation(self, kw):
        with pytest.raises(ValueError):
            SplitFlap(**kw)

    def test_knob_edges_ok(self):
        p = SplitFlap(flips=0, stagger=0.0)
        assert p.flips == 0 and p.stagger == 0.0
        assert SplitFlap(stagger=0.9).stagger == 0.9

    def test_int_stagger_accepted_as_float(self):
        assert SplitFlap(stagger=0).stagger == 0.0

    def test_defaults(self):
        p = SplitFlap()
        assert (p.flips, p.stagger) == (3, 0.5)
        assert p.min_frames == 36 and p.scale_switch_at == 1.0


class TestFrames:
    def test_t0_paints_outgoing_exactly(self):
        c = _StubCanvas(16, 8)
        o = _two_cells(RED)
        px = _frame(SplitFlap(), 0.0, c, o, _two_cells(GREEN))
        ref = _StubCanvas(16, 8)
        o.draw(ref)
        assert px == ref._pixels

    def test_snap_draws_incoming(self, monkeypatch):
        calls: list[Any] = []
        monkeypatch.setattr(
            "led_ticker_flair.flair.splitflap.snap_reset",
            lambda cv, bg: calls.append(bg),
        )
        c = _StubCanvas(16, 8)
        i = _two_cells(GREEN)
        SplitFlap().frame_at(
            SNAP_THRESHOLD, c, _two_cells(RED), i, incoming_bg_color=(9, 9, 9)
        )
        assert calls == [(9, 9, 9)]
        assert i.draw.call_args.kwargs["cursor_pos"] == 0
        assert set(c._pixels.values()) == {GREEN}

    def test_forward_ripple_left_settles_first(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = SplitFlap(flips=0, stagger=0.5)
        p.frame_at(0.0, c, o, i)
        px = _frame(p, _t(0.5), c, o, i)
        assert px[(1, 1)] == GREEN and px[(1, 6)] == GREEN
        assert px[(11, 1)] == RED and px[(11, 6)] == RED

    def test_reverse_ripple_right_settles_first(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = SplitFlapReverse(flips=0, stagger=0.5)
        p.frame_at(0.0, c, o, i)
        px = _frame(p, _t(0.5), c, o, i)
        assert px[(11, 1)] == GREEN and px[(1, 1)] == RED

    def test_all_landed_before_snap(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = SplitFlap()
        p.frame_at(0.0, c, o, i)
        px = _frame(p, 0.92 * SNAP_THRESHOLD, c, o, i)
        ref = _StubCanvas(16, 8)
        i.draw(ref)
        assert px == ref._pixels

    def test_mid_flap_mixes_halves(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = SplitFlap(flips=0, stagger=0.0)  # one flap over the whole timeline
        p.frame_at(0.0, c, o, i)
        px = _frame(p, _t(0.25), c, o, i)  # q = 0.25: top half falling
        assert px[(1, 0)] == GREEN  # revealed top of incoming
        assert px[(1, 7)] == RED  # outgoing bottom
        r, g, b = px[(1, 3)]  # squashed flap: shaded outgoing
        assert g == 0 and b == 0 and 0 < r < 255

    def test_both_empty_paints_nothing_until_snap(self):
        c = _StubCanvas(16, 8)
        o, i = _widget([]), _widget([])
        p = SplitFlap()
        for t in (0.0, 0.3, 0.6, 0.9):
            assert _frame(p, t, c, o, i) == {}

    def test_empty_outgoing_flips_from_blank(self):
        c = _StubCanvas(16, 8)
        o, i = _widget([]), _two_cells(GREEN)
        p = SplitFlap()
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
        p = SplitFlap()
        p.frame_at(0.0, c, o, i)
        for t in (0.1, 0.4, 0.7):
            px = _frame(p, t, c, o, i)
            assert all(px.get((x, y)) == BLUE for x, y, _ in ring)

    def test_snapshots_once_per_firing(self):
        c = _StubCanvas(16, 8)
        o, i = _two_cells(RED), _two_cells(GREEN)
        p = SplitFlap()
        for t in (0.0, 0.2, 0.5, 0.8):
            p.frame_at(t, c, o, i)
        assert (o.draw.call_count, i.draw.call_count) == (1, 1)
        p.frame_at(0.0, c, o, i)  # refire
        assert (o.draw.call_count, i.draw.call_count) == (2, 2)

    def test_equal_t_is_not_a_refire(self):
        c = _StubCanvas(16, 8)
        p = SplitFlap()
        p.frame_at(0.3, c, _two_cells(RED), _two_cells(GREEN))
        ref = p._board
        p.frame_at(0.3, c, _two_cells(RED), _two_cells(GREEN))
        assert p._board is ref

    def test_outgoing_scroll_pos_forwarded(self):
        c = _StubCanvas(16, 8)
        o = _two_cells(RED)
        SplitFlap().frame_at(0.0, c, o, _two_cells(GREEN), outgoing_scroll_pos=-37)
        assert o.draw.call_args.kwargs["cursor_pos"] == -37

    def test_image_widget_flips_as_strips(self):
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
        p = SplitFlap(flips=0)
        p.frame_at(0.0, c, widget, _two_cells(GREEN))
        assert p._board is not None and len(p._board.flaps) > 2


class TestVariantsRegistration:
    def test_alternating_cycles_forward_reverse(self):
        c = _StubCanvas(16, 8)
        p = SplitFlapAlternating()
        kinds = []
        for _ in range(3):
            p.frame_at(0.0, c, _two_cells(RED), _two_cells(GREEN))
            kinds.append(type(p._transitions[p._index]))
        assert kinds == [SplitFlap, SplitFlapReverse, SplitFlap]
        assert p.min_frames == 36 and p.scale_switch_at == 1.0

    def test_random_order_seeded_reproducible(self):
        def run(seed: int) -> dict:
            c = _StubCanvas(16, 8)
            p = SplitFlapRandom(flips=0)
            p._rng = random.Random(seed)
            p.frame_at(0.0, c, _two_cells(RED), _two_cells(GREEN))
            return _frame(p, _t(0.4), c, _two_cells(RED), _two_cells(GREEN))

        assert run(5) == run(5)

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
        assert reg["splitflap.forward"] is SplitFlap
        assert reg["splitflap.reverse"] is SplitFlapReverse
        assert reg["splitflap.alternating"] is SplitFlapAlternating
        assert reg["splitflap.random"] is SplitFlapRandom


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
            SplitFlap(),
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
            SplitFlapReverse(),
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
            SplitFlapRandom(),
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
            SplitFlap(),
            sc,
            real,
            TickerMessage(text="GIF"),
            GifPlayer(path=str(path), fit="stretch"),
        )
