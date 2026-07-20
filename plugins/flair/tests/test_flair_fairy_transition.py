"""flair.fairy — Fairy/FairyReverse/FairyAlternating transition classes.

Stub canvas / widget fixtures copied from test_flair_lightning_transition.py
(the per-file duplication is this repo's convention).
"""

from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import ScaledCanvas

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.fairy import Fairy, FairyAlternating, FairyReverse


class _StubCanvas:
    """Minimal scale=1 real-canvas stub."""

    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height
        self._pixels: dict[tuple[int, int], tuple[int, int, int]] = {}
        self.calls: list[tuple[int, int, int, int, int]] = []

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:  # noqa: N802
        self._pixels[(x, y)] = (r, g, b)
        self.calls.append((x, y, r, g, b))

    def SubFill(  # noqa: N802
        self, x: int, y: int, w: int, h: int, r: int, g: int, b: int
    ) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.SetPixel(xx, yy, r, g, b)

    def Clear(self) -> None:  # noqa: N802
        self._pixels.clear()

    def Fill(self, r: int, g: int, b: int) -> None:  # noqa: N802
        for y in range(self.height):
            for x in range(self.width):
                self.SetPixel(x, y, r, g, b)


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


class TestKnobValidation:
    def test_bad_seed_rejected(self):
        for bad in ("7", 1.5, True):
            with pytest.raises(ValueError, match="seed"):
                Fairy(seed=bad)

    def test_bad_color_rejected(self):
        for bad in ([255, 0], [255, 0, "x"], [300, 0, 0], "gold", [True, 0, 0]):
            with pytest.raises(ValueError, match="color"):
                Fairy(color=bad)

    def test_valid_knobs_all_variants(self):
        assert Fairy().dust_color == (255, 215, 120)
        assert Fairy(color=[255, 92, 38]).dust_color == (255, 92, 38)
        FairyReverse(seed=7)
        FairyAlternating(color=[1, 2, 3], seed=9)


class TestEndpoints:
    def test_t_zero_draws_outgoing_only(self) -> None:
        p = Fairy(seed=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)
        result = p.frame_at(0.0, canvas, outgoing, incoming)
        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        assert canvas._pixels == {}
        assert result is canvas

    def test_snap_draws_incoming_on_bg(self) -> None:
        p = Fairy(seed=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=True)
        result = p.frame_at(
            0.96, canvas, outgoing, incoming, incoming_bg_color=(9, 9, 9)
        )
        outgoing.draw.assert_not_called()
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)
        assert canvas._pixels[(0, 0)] == (255, 0, 0)
        assert canvas._pixels[(5, 5)] == (9, 9, 9)
        assert result is canvas

    def test_no_outgoing_paint_after_cutover(self) -> None:
        p = Fairy(seed=2)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)
        p.frame_at(0.6, canvas, outgoing, incoming)
        outgoing.draw.assert_not_called()
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)

    def test_flight_paints_head_and_dust_over_outgoing(self) -> None:
        p = Fairy(seed=3)
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p.frame_at(0.3, canvas, o, i)
        o.draw.assert_called_once()
        i.draw.assert_not_called()
        assert canvas._pixels
        assert (255, 255, 255) in canvas._pixels.values()  # white-hot head


class TestDirections:
    @staticmethod
    def _painted_xs(cls) -> list[int]:
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p = cls(seed=5)
        p.frame_at(0.15, canvas, o, i)  # early flight: head near start edge
        return [x for (x, _y) in canvas._pixels]

    def test_forward_starts_left(self) -> None:
        xs = self._painted_xs(Fairy)
        assert max(xs) < 160 * 0.6  # everything in the left-ish half early on

    def test_reverse_starts_right(self) -> None:
        xs = self._painted_xs(FairyReverse)
        assert min(xs) > 160 * 0.4

    def test_alternating_flips_each_firing(self) -> None:
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p = FairyAlternating(seed=6)
        sides = []
        for _ in range(3):
            canvas.Clear()
            canvas.calls.clear()
            p.frame_at(0.15, canvas, o, i)  # firing N begins (t regressed)
            xs = [x for (x, _y) in canvas._pixels]
            sides.append(sum(xs) / len(xs) < 80)  # True = left-side energy
            p.frame_at(0.96, canvas, o, i)  # finish the firing
        assert sides[0] != sides[1]
        assert sides[1] != sides[2]


class TestFullReveal:
    """Just below SNAP the gap must cover the whole panel: incoming fills
    (7, 7, 7); any black pixel is a reveal gap. Deterministic (pure gap
    function of t)."""

    @pytest.mark.parametrize("seed", range(8))
    @pytest.mark.parametrize(("width", "height", "scale"), [(160, 16, 1), (256, 64, 4)])
    def test_full_reveal_before_snap(self, width, height, scale, seed) -> None:
        real = _StubCanvas(width=width, height=height)
        canvas = (
            ScaledCanvas(real, scale=scale, content_height=16) if scale > 1 else real
        )
        p = Fairy(seed=seed)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False, fill=(7, 7, 7))
        p.frame_at(0.94, canvas, o, i)
        black = [
            (x, y)
            for y in range(height)
            for x in range(width)
            if real._pixels.get((x, y), (0, 0, 0)) == (0, 0, 0)
        ]
        assert not black, f"{len(black)} unrevealed px, first: {black[:5]}"


class TestRefire:
    def test_seedless_refire_replans(self) -> None:
        p = Fairy()
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        for t in (0.3, 0.6, 0.96):
            p.frame_at(t, canvas, o, i)
        first = p._path
        assert first
        p.frame_at(0.05, canvas, o, i)
        assert p._path is not first

    def test_seeded_refire_keeps_plan(self) -> None:
        p = Fairy(seed=9)
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p.frame_at(0.3, canvas, o, i)
        first = p._path
        p.frame_at(0.96, canvas, o, i)
        p.frame_at(0.05, canvas, o, i)
        assert p._path is first


class TestPhysicalResolution:
    def test_settled_line_is_thin_on_real_canvas(self) -> None:
        """Through a ScaledCanvas the settled line lands on the REAL canvas
        at max(1, scale//2) = 2 px — a wrapper-drawn line would block-expand
        to >= 4 rows per column."""
        real = _StubCanvas(width=256, height=64)
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        p = Fairy(seed=5)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p.frame_at(0.45, canvas, o, i)  # head near far edge, long settled line
        assert real._pixels
        # Column 3 is far behind the head: settled line only (sparks have
        # faded there — trail is 30% of width). <= 3 rows (thickness 2 +
        # rounding), never a 4-px block.
        rows = [y for (x, y) in real._pixels if x == 3]
        assert rows
        assert len(rows) <= 3


class _RecordingAPI:
    """Minimal PluginAPI stand-in recording registrations."""

    def __init__(self) -> None:
        self.animations: dict[str, type] = {}
        self.transitions: dict[str, type] = {}
        self.widgets: dict[str, type] = {}

    def animation(self, name):
        def _dec(cls):
            self.animations[name] = cls
            return cls

        return _dec

    def transition(self, name):
        def _dec(cls):
            self.transitions[name] = cls
            return cls

        return _dec

    def widget(self, name):
        def _dec(cls):
            self.widgets[name] = cls
            return cls

        return _dec


class TestRegistration:
    def test_all_three_fairy_variants_registered(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert api.transitions["fairy.forward"] is Fairy
        assert api.transitions["fairy.reverse"] is FairyReverse
        assert api.transitions["fairy.alternating"] is FairyAlternating


class TestPerfUniformity:
    """Committed CI-safe perf gate (lightning convention): count WORK per
    frame, not time — a deferred-backlog bug fails the bound
    deterministically."""

    def test_per_frame_paint_volume_bounded(self) -> None:
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p = Fairy(seed=4)
        counts = []
        t = 0.02
        while t < 1.0:
            before = len(canvas.calls)
            p.frame_at(round(t, 3), canvas, o, i)
            counts.append((round(t, 2), len(canvas.calls) - before))
            t += 0.02
        panel = 160 * 16
        worst_t, worst = max(counts, key=lambda c: c[1])
        assert worst <= int(1.5 * panel), (
            f"frame at t={worst_t} painted {worst} px (> 1.5x panel {panel})"
        )

    def test_alternating_refire_frames_equally_bounded(self) -> None:
        canvas = _StubCanvas(width=160, height=16)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p = FairyAlternating()  # seedless, flips per firing
        for t in (0.3, 0.6, 0.96):
            p.frame_at(t, canvas, o, i)
        panel = 160 * 16
        t = 0.02
        while t < 1.0:
            before = len(canvas.calls)
            p.frame_at(round(t, 3), canvas, o, i)
            assert len(canvas.calls) - before <= int(1.5 * panel)
            t += 0.02
