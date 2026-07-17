"""flair.poker — the ``Poker`` suit-ripple transition class (Task 3) +
registration.

Stub canvas / widget fixtures copied from test_flair_stickers_transition.py
(the per-file duplication is this repo's convention).
"""

from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import SNAP_THRESHOLD, ScaledCanvas

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.poker import Poker


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
    """Widget stub. ``draw_pixel`` lights one pixel at (0, 0); ``fill`` (an
    (r, g, b) tuple) fills the whole canvas — used to make 'revealed but
    empty' pixels observable as the incoming colour rather than black."""
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
    def test_unknown_suit_raises_naming_options(self):
        with pytest.raises(ValueError, match="hearts.*diamonds.*clubs.*spades|suits"):
            Poker(suits=["wands"])

    def test_empty_or_nonlist_rejected(self):
        for bad in ([], "hearts", [1], [""]):
            with pytest.raises(ValueError):
                Poker(suits=bad)

    def test_valid_suits_and_default(self):
        assert Poker().suits == ["hearts", "diamonds", "clubs", "spades"]
        assert Poker(suits=["diamonds"]).suits == ["diamonds"]
        assert Poker(suits=["hearts", "spades"]).suits == ["hearts", "spades"]


class TestEndpoints:
    def test_t_zero_draws_outgoing_only(self) -> None:
        p = Poker(suits=["hearts"], seed=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        result = p.frame_at(0.0, canvas, outgoing, incoming)

        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        # No glyph/ring layer painted anything at t=0 (outgoing is a no-op
        # stub here, so any pixel at all would be a leak).
        assert canvas._pixels == {}
        assert result is canvas

    def test_snap_draws_incoming_on_bg(self) -> None:
        p = Poker(suits=["hearts"], seed=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=True)

        result = p.frame_at(
            0.96, canvas, outgoing, incoming, incoming_bg_color=(9, 9, 9)
        )

        outgoing.draw.assert_not_called()
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)
        # incoming drew its own pixel at (0, 0) AFTER the bg fill -> wins there.
        assert canvas._pixels[(0, 0)] == (255, 0, 0)
        # Elsewhere the snap_reset bg fill is observable.
        assert canvas._pixels[(5, 5)] == (9, 9, 9)
        assert result is canvas

    def _assert_full_reveal(self, real: _StubCanvas, canvas: Any) -> None:
        """Sweep t across the wash phase (accumulating the reveal mask), then
        at t just below SNAP assert NO panel pixel is the black complement:
        the incoming widget fills a non-black colour, so a black pixel can only
        be one we blacked out for being still-unrevealed. Rainbow rings are
        never pure black, so black == unrevealed exactly."""
        p = Poker(seed=7)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False, fill=(7, 7, 7))

        t = 0.4
        while t < SNAP_THRESHOLD:
            p.frame_at(t, canvas, outgoing, incoming)
            t += 0.02
        p.frame_at(SNAP_THRESHOLD - 1e-4, canvas, outgoing, incoming)

        black = [
            (x, y)
            for y in range(real.height)
            for x in range(real.width)
            if real._pixels.get((x, y)) == (0, 0, 0)
        ]
        assert black == [], f"{len(black)} panel pixels left as black complement"

    def test_full_reveal_before_snap_smallsign(self) -> None:
        real = _StubCanvas(width=160, height=16)
        self._assert_full_reveal(real, real)

    def test_full_reveal_before_snap_bigsign(self) -> None:
        real = _StubCanvas(width=256, height=64)
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        self._assert_full_reveal(real, wrapped)

    def test_no_outgoing_paint_after_cutover(self) -> None:
        p = Poker(suits=["clubs"], seed=2)
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        p.frame_at(0.6, canvas, outgoing, incoming)

        outgoing.draw.assert_not_called()
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)


class TestDeterminismAndRefire:
    def test_same_seed_same_frames(self) -> None:
        canvas_a = _StubCanvas(width=160, height=16)
        canvas_b = _StubCanvas(width=160, height=16)

        Poker(seed=5).frame_at(0.3, canvas_a, _make_widget(False), _make_widget(False))
        Poker(seed=5).frame_at(0.3, canvas_b, _make_widget(False), _make_widget(False))

        assert canvas_a._pixels == canvas_b._pixels
        assert canvas_a._pixels  # sanity: something actually painted

    def test_refire_replans(self) -> None:
        p = Poker()  # seed=None -> entropy reseed on every re-fire
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        for t in (0.0, 0.3, 0.6, 1.0):
            p.frame_at(t, canvas, outgoing, incoming)
        first_plan = p._plan
        assert first_plan is not None

        for t in (0.0, 0.1):
            p.frame_at(t, canvas, outgoing, incoming)
        second_plan = p._plan
        assert second_plan is not None
        assert second_plan is not first_plan


class TestPerf:
    def test_no_ring_rasterization_after_first_frame(self, monkeypatch) -> None:
        import led_ticker_flair.flair.poker as m

        calls: list[Any] = []
        real_ring = m.ring_pixels

        def _spy(*a: Any, **k: Any) -> Any:
            calls.append(a)
            return real_ring(*a, **k)

        monkeypatch.setattr(m, "ring_pixels", _spy)

        p = Poker(seed=2)
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        p.frame_at(0.5, canvas, outgoing, incoming)
        assert calls  # cache warm on the first frame
        first_call_count = len(calls)

        p.frame_at(0.6, canvas, outgoing, incoming)
        # No NEW rasterization on the second frame -- every ring shell (every
        # glyph x every integer radius, not just the ones live at t=0.5) was
        # pre-warmed when the plan was built.
        assert len(calls) == first_call_count


# ---------------------------------------------------------------------------
# Registration -- _RecordingAPI idiom copied per this repo's
# per-file-duplication convention (see test_flair_stickers_transition.py).
# ---------------------------------------------------------------------------


class _RecordingAPI:
    """Minimal PluginAPI stand-in recording animation + transition registrations."""

    def __init__(self) -> None:
        self.animations: dict[str, type] = {}
        self.transitions: dict[str, type] = {}
        self.widgets: dict[str, type] = {}

    def animation(self, style: str):
        def deco(cls):
            self.animations[style] = cls
            return cls

        return deco

    def transition(self, name: str):
        def deco(cls):
            self.transitions[name] = cls
            return cls

        return deco

    def widget(self, name: str):
        def deco(cls):
            self.widgets[name] = cls
            return cls

        return deco


class TestRegistration:
    def test_poker_registered(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "poker" in api.transitions
        assert api.transitions["poker"] is Poker

    def test_other_transitions_still_registered(self) -> None:
        """Poker registration must not displace existing transitions."""
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "spinout" in api.transitions
        assert "fireworks" in api.transitions
        assert "stickers" in api.transitions

    def test_other_namespaces_unaffected(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "propeller" in api.animations
        assert "fisheye" in api.animations
        assert "lottery" in api.widgets
