"""flair.stickers — the ``Stickers`` transition class (Task 3) + registration.

Stub canvas / widget fixture shapes copied from test_flair_fireworks.py (the
per-file duplication is this repo's convention). Extended with a `.calls`
ordered SetPixel log (determinism test) and `Fill` (snap_reset's bg fill).
"""

from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import ScaledCanvas

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.stickers import Stickers


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


def _make_widget(draw_pixel: bool = True) -> Any:
    """Widget stub whose draw() optionally lights one pixel at (0, 0)."""
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        if draw_pixel:
            canvas.SetPixel(0, 0, 255, 0, 0)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


class TestKnobValidation:
    def test_unknown_slug_raises_at_construction_naming_it(self):
        # `dragon` is a deliberately non-existent slug — do NOT use `fire`
        # here: core added `:fire:` in led-ticker-core (PR #424), so it is a
        # VALID slug now and would not be rejected. `dragon` is not in the
        # emoji set (and unlikely to be), so this stays a real rejection case.
        with pytest.raises(ValueError, match="dragon"):
            Stickers(emoji=["taco", "dragon"])

    def test_empty_or_nonlist_rejected(self):
        for bad in ([], "taco", [1], [""]):
            with pytest.raises(ValueError):
                Stickers(emoji=bad)

    def test_known_slugs_accepted(self):
        Stickers(emoji=["taco"])
        Stickers(emoji=["sun", "moon", "heart_red"])


class TestEndpoints:
    def test_t_zero_draws_outgoing_only(self) -> None:
        s = Stickers(emoji=["taco"], seed=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        result = s.frame_at(0.0, canvas, outgoing, incoming)

        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        # No sticker layer painted anything at t=0 (outgoing's own draw is
        # a no-op stub here, so any pixel at all would be a sticker leak).
        assert canvas._pixels == {}
        assert result is canvas

    def test_snap_draws_incoming_on_bg(self) -> None:
        s = Stickers(emoji=["taco"], seed=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=True)

        result = s.frame_at(
            0.96, canvas, outgoing, incoming, incoming_bg_color=(9, 9, 9)
        )

        outgoing.draw.assert_not_called()
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)
        # incoming drew its own pixel at (0, 0) AFTER the bg fill -> wins there.
        assert canvas._pixels[(0, 0)] == (255, 0, 0)
        # Elsewhere the snap_reset bg fill is observable.
        assert canvas._pixels[(5, 5)] == (9, 9, 9)
        assert result is canvas

    def test_full_cover_at_half_smallsign(self) -> None:
        """Load-bearing coverage proof: at t=0.5 every real-panel pixel has
        been painted by sticker layers (both widgets are no-ops here, so
        any covered pixel can only have come from a sticker), smallsign
        geometry (scale=1, no ScaledCanvas wrapper)."""
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)
        s = Stickers(seed=11)  # random assortment across the full slug set

        s.frame_at(0.5, canvas, outgoing, incoming)

        missing = [
            (x, y)
            for y in range(16)
            for x in range(160)
            if (x, y) not in canvas._pixels
        ]
        assert missing == []

    def test_full_cover_at_half_bigsign(self) -> None:
        """Same coverage proof, bigsign geometry (scale=4 ScaledCanvas
        wrapping a 256x64 real stub) -- stickers paint through
        unwrap_to_real, so coverage is asserted against the REAL canvas."""
        real = _StubCanvas(width=256, height=64)
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)
        s = Stickers(seed=11)

        s.frame_at(0.5, wrapped, outgoing, incoming)

        missing = [
            (x, y) for y in range(64) for x in range(256) if (x, y) not in real._pixels
        ]
        assert missing == []

    def test_peel_reveals_incoming(self) -> None:
        s = Stickers(emoji=["taco"], seed=1)
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        # Warm the plan at t=0.5 first so we know the full-cover pixel count
        # to compare the partial-peel count against.
        s.frame_at(0.5, canvas, outgoing, incoming)
        full_cover_count = len(canvas._pixels)
        assert full_cover_count == 160 * 16

        canvas2 = _StubCanvas(width=160, height=16)
        incoming2 = _make_widget(draw_pixel=False)
        result = s.frame_at(0.75, canvas2, outgoing, incoming2)

        incoming2.draw.assert_called_once_with(canvas2, cursor_pos=0)
        # Some sticker pixels are still present (not yet fully peeled)...
        assert len(canvas2._pixels) > 0
        # ...but strictly fewer than the fully-covered t=0.5 frame (some
        # stickers have already popped off, revealing incoming's Clear()).
        assert len(canvas2._pixels) < full_cover_count
        assert result is canvas2


class TestDeterminismAndRefire:
    def test_same_seed_same_frames(self) -> None:
        canvas_a = _StubCanvas(width=160, height=16)
        canvas_b = _StubCanvas(width=160, height=16)
        outgoing_a = _make_widget(draw_pixel=False)
        outgoing_b = _make_widget(draw_pixel=False)
        incoming_a = _make_widget(draw_pixel=False)
        incoming_b = _make_widget(draw_pixel=False)

        Stickers(seed=5).frame_at(0.3, canvas_a, outgoing_a, incoming_a)
        Stickers(seed=5).frame_at(0.3, canvas_b, outgoing_b, incoming_b)

        assert canvas_a._pixels == canvas_b._pixels
        assert canvas_a._pixels  # sanity: something actually painted

    def test_refire_replans(self) -> None:
        s = Stickers()  # seed=None -> entropy reseed on every re-fire
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        for t in (0.0, 0.3, 0.6, 1.0):
            s.frame_at(t, canvas, outgoing, incoming)
        first_plan = s._plan
        assert first_plan is not None

        for t in (0.0, 0.1):
            s.frame_at(t, canvas, outgoing, incoming)
        second_plan = s._plan
        assert second_plan is not None
        assert second_plan is not first_plan


class TestPerf:
    def test_no_rasterization_after_first_frame(self, monkeypatch) -> None:
        import led_ticker_flair.flair.stickers as m

        calls: list[Any] = []
        real_capture = m.capture_sprite

        def _spy(*a: Any, **k: Any) -> Any:
            calls.append(a)
            return real_capture(*a, **k)

        monkeypatch.setattr(m, "capture_sprite", _spy)

        s = Stickers(emoji=["taco", "sun", "moon"], seed=2)
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        s.frame_at(0.3, canvas, outgoing, incoming)
        assert calls  # cache warm on the first frame
        first_call_count = len(calls)

        s.frame_at(0.4, canvas, outgoing, incoming)
        # No NEW rasterization on the second frame -- the plan (and every
        # sticker in it, not just the ones visible at 0.3) was fully
        # pre-warmed into the raster cache when the plan was built.
        assert len(calls) == first_call_count


# ---------------------------------------------------------------------------
# Registration -- _RecordingAPI idiom copied per this repo's
# per-file-duplication convention (see test_flair_fireworks.py).
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
    def test_stickers_registered(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "stickers" in api.transitions
        assert api.transitions["stickers"] is Stickers

    def test_other_transitions_still_registered(self) -> None:
        """Stickers registration must not displace existing transitions."""
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "spinout" in api.transitions
        assert "fireworks" in api.transitions

    def test_other_namespaces_unaffected(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "propeller" in api.animations
        assert "fisheye" in api.animations
        assert "lottery" in api.widgets


class TestBackingKnob:
    def test_bad_backing_raises_naming_options(self) -> None:
        with pytest.raises(ValueError, match="backing"):
            Stickers(emoji=["taco"], backing="halo")

    def test_valid_backings_accepted(self) -> None:
        for b in ("card", "shadow", "none"):
            Stickers(emoji=["taco"], backing=b)

    def test_none_backing_leaves_gaps_at_half(self) -> None:
        """The documented tradeoff: without cards the panel is NOT fully
        covered at t=0.5 — sprite gaps stay unpainted (swarm, not wall).
        Inverse of test_full_cover_at_half_smallsign."""
        canvas = _StubCanvas(width=160, height=16)
        s = Stickers(emoji=["taco"], seed=3, backing="none")

        s.frame_at(0.5, canvas, _make_widget(False), _make_widget(False))

        missing = [
            (x, y)
            for y in range(16)
            for x in range(160)
            if (x, y) not in canvas._pixels
        ]
        assert missing, "bare sprites must leave gaps between their ink"

    def test_shadow_backing_leaves_gaps_but_fewer(self) -> None:
        """Shadow halos cover more than bare sprites, still less than cards."""

        def _missing(backing: str) -> int:
            canvas = _StubCanvas(width=160, height=16)
            s = Stickers(emoji=["taco"], seed=3, backing=backing)
            s.frame_at(0.5, canvas, _make_widget(False), _make_widget(False))
            return sum(
                1 for y in range(16) for x in range(160) if (x, y) not in canvas._pixels
            )

        m_none, m_shadow, m_card = (
            _missing("none"),
            _missing("shadow"),
            _missing("card"),
        )
        assert m_card == 0
        assert 0 < m_shadow < m_none
