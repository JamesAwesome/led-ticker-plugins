"""flair.lightning — the ``Lightning`` strike-and-peel transition class.

Stub canvas / widget fixtures copied from test_flair_poker_transition.py
(the per-file duplication is this repo's convention).
"""

from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import ScaledCanvas

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.lightning import Lightning


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
                Lightning(seed=bad)

    def test_bad_color_rejected(self):
        for bad in ([255, 0], [255, 0, "x"], [300, 0, 0], "red", [True, 0, 0]):
            with pytest.raises(ValueError, match="color"):
                Lightning(color=bad)

    def test_valid_knobs(self):
        assert Lightning().trail_color == (150, 190, 255)
        assert Lightning(color=[255, 92, 38]).trail_color == (255, 92, 38)
        Lightning(seed=7)  # no raise


class TestEndpoints:
    def test_t_zero_draws_outgoing_only(self) -> None:
        p = Lightning(seed=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        result = p.frame_at(0.0, canvas, outgoing, incoming)

        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        assert canvas._pixels == {}  # no bolt paint at t=0
        assert result is canvas

    def test_snap_draws_incoming_on_bg(self) -> None:
        p = Lightning(seed=1)
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
        p = Lightning(seed=2)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        p.frame_at(0.6, canvas, outgoing, incoming)

        outgoing.draw.assert_not_called()
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)

    def test_strike_paints_bolt_over_outgoing(self) -> None:
        p = Lightning(seed=3)
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p.frame_at(0.3, canvas, o, i)
        o.draw.assert_called_once()
        i.draw.assert_not_called()
        assert canvas._pixels  # bolt pixels present
        # head is white-hot somewhere
        assert (255, 255, 255) in canvas._pixels.values()


class TestFullReveal:
    """At t just below SNAP the gap must cover the whole panel: the incoming
    fills (7, 7, 7), so any black pixel is a reveal gap. Deterministic — the
    gap bound is a pure function of t (no frame sweep needed)."""

    @pytest.mark.parametrize("seed", range(8))
    @pytest.mark.parametrize(
        ("width", "height", "scale"), [(160, 16, 1), (256, 64, 4)]
    )
    def test_full_reveal_before_snap(self, width, height, scale, seed) -> None:
        real = _StubCanvas(width=width, height=height)
        canvas = (
            ScaledCanvas(real, scale=scale, content_height=16)
            if scale > 1
            else real
        )
        p = Lightning(seed=seed)
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
        p = Lightning()  # seed=None
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        for t in (0.3, 0.6, 0.96):
            p.frame_at(t, canvas, o, i)
        first = p._crack
        assert first
        p.frame_at(0.05, canvas, o, i)  # t regressed -> new firing
        assert p._crack is not first

    def test_seeded_refire_keeps_plan(self) -> None:
        p = Lightning(seed=9)
        canvas = _StubCanvas()
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p.frame_at(0.3, canvas, o, i)
        first = p._crack
        p.frame_at(0.96, canvas, o, i)
        p.frame_at(0.05, canvas, o, i)
        assert p._crack is first


class TestPhysicalResolution:
    def test_bolt_paints_real_canvas_thin(self) -> None:
        """Through a ScaledCanvas the bolt must land on the REAL canvas at
        ~2px thickness (max(1, scale//2)) — a wrapper-drawn bolt would
        block-expand to >= scale (4) rows per column."""
        real = _StubCanvas(width=256, height=64)
        canvas = ScaledCanvas(real, scale=4, content_height=16)
        p = Lightning(seed=5)
        o = _make_widget(draw_pixel=False)
        i = _make_widget(draw_pixel=False)
        p.frame_at(0.4, canvas, o, i)
        assert real._pixels
        # column 5 is deep in the trail at t=0.4 (head ~89% across): trail
        # thickness is 2 real px there, never a 4px block.
        rows = [y for (x, y) in real._pixels if x == 5]
        assert rows
        assert len(rows) <= 3
