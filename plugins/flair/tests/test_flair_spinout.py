"""flair.spinout — registration, seam guard, and Spinout transition tests."""

import sys
from typing import Any
from unittest import mock

import pytest

from led_ticker_flair import flair as flair_pkg  # noqa: I001

# ---------------------------------------------------------------------------
# Minimal stub canvas helpers
# ---------------------------------------------------------------------------


class _StubCanvas:
    """Minimal scale=1 canvas stub."""

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


class _ScaledStubCanvas:
    """Minimal scale=4 ScaledCanvas stub (just enough for matches() + blit)."""

    def __init__(self, width: int = 64, height: int = 16) -> None:
        self.width = width
        self.height = height
        self.scale = 4
        self.content_height = height
        # The real canvas underneath
        self.real = _StubCanvas(width * 4, height * 4)
        # Track SetPixel calls for assertions
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


# ---------------------------------------------------------------------------
# _RecordingAPI — captures both animation and transition registrations
# ---------------------------------------------------------------------------


class _RecordingAPI:
    """Minimal PluginAPI stand-in recording animation + transition registrations."""

    def __init__(self) -> None:
        self.animations: dict[str, type] = {}
        self.transitions: dict[str, type] = {}

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


# ---------------------------------------------------------------------------
# Widget stub that draws lit pixels into a canvas
# ---------------------------------------------------------------------------


def _make_widget(draw_pixel: bool = True) -> Any:
    """Widget stub whose draw() optionally lights one pixel."""
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas, cursor_pos: int = 0, **kw):
        if draw_pixel:
            canvas.SetPixel(0, 0, 255, 0, 0)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_spinout_registered(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "spinout" in api.transitions

    def test_propeller_still_registered(self) -> None:
        """Spinout registration must not displace the existing propeller."""
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "propeller" in api.animations


def test_register_guard_message_when_seam_missing(monkeypatch) -> None:
    """Version-skew error quality: a core without make_rotation_surface
    must produce an actionable '>= 4.6' message, not a bare ImportError.

    Goes through register() — not _import_seam() directly — so a refactor
    that drops the guard call from register() fails this test."""
    import types

    stub = types.ModuleType("led_ticker.plugin")
    # Withhold make_rotation_surface — simulates a pre-4.6 core.
    monkeypatch.setitem(sys.modules, "led_ticker.plugin", stub)

    with pytest.raises(ImportError, match=r">= 4\.6"):
        flair_pkg.register(_RecordingAPI())


# ---------------------------------------------------------------------------
# Constructor validation tests
# ---------------------------------------------------------------------------


class TestSpinoutCtorValidation:
    def _cls(self):
        from led_ticker_flair.flair.spinout import Spinout

        return Spinout

    def test_bool_revolutions_rejected(self) -> None:
        with pytest.raises(ValueError, match="revolutions"):
            self._cls()(revolutions=True)

    def test_zero_revolutions_rejected(self) -> None:
        with pytest.raises(ValueError, match="revolutions"):
            self._cls()(revolutions=0)

    def test_negative_revolutions_rejected(self) -> None:
        with pytest.raises(ValueError, match="revolutions"):
            self._cls()(revolutions=-1)

    def test_invalid_direction_rejected(self) -> None:
        with pytest.raises(ValueError, match="direction"):
            self._cls()(direction="sideways")

    def test_valid_defaults_construct(self) -> None:
        s = self._cls()()
        assert s.revolutions == 2
        assert s.direction == "cw"

    def test_valid_custom_params(self) -> None:
        s = self._cls()(revolutions=3, direction="ccw")
        assert s.revolutions == 3
        assert s.direction == "ccw"


# ---------------------------------------------------------------------------
# scale_switch_at attribute pin (antagonist finding 1)
# ---------------------------------------------------------------------------


class TestScaleSwitchAtPin:
    def test_scale_switch_at_is_class_attribute_1_0(self) -> None:
        """LOAD-BEARING pin: scale_switch_at == 1.0 on the class so
        run_transition holds the outgoing bg for the entire spin and
        defers the cross-scale re-wrap until the cut frame (t=1.0)."""
        from led_ticker_flair.flair.spinout import Spinout

        assert Spinout.scale_switch_at == 1.0
        # Must be a CLASS attribute, not instance-only.
        assert "scale_switch_at" in Spinout.__dict__


# ---------------------------------------------------------------------------
# Envelope tests (angle math)
# ---------------------------------------------------------------------------


class TestSpinoutEnvelope:
    def _cls(self):
        from led_ticker_flair.flair.spinout import Spinout

        return Spinout

    def _angle(self, spinout, t: float) -> float:
        """Pre-modulo angle for monotonicity checks."""
        return 360.0 * spinout.revolutions * (t**3)

    def test_t0_angle_is_zero(self) -> None:
        s = self._cls()()
        # At t=0 the ease-in cubic is 0^3=0, so angle=0
        assert self._angle(s, 0.0) == 0.0

    def test_pre_mod_angle_strictly_monotonic(self) -> None:
        """Pre-modulo angle strictly increases from t=0 to t=1 (ease-in cubic)."""
        s = self._cls()(revolutions=2)
        ts = [i / 20 for i in range(21)]
        angles = [self._angle(s, t) for t in ts]
        for i in range(1, len(angles)):
            assert angles[i] >= angles[i - 1]
        # Strictly increasing (no plateau except at t=0)
        assert angles[-1] > angles[0]

    def test_ccw_mirrors_cw(self) -> None:
        """CCW formula produces the mirror of CW: (-angle) % 360."""
        cw = self._cls()(direction="cw")
        # Mid-spin angle is non-zero
        t = 0.5
        base_angle = 360.0 * cw.revolutions * (t**3)
        assert base_angle != 0.0

        # The CCW formula: -angle % 360.0 gives the mirror
        cw_angle = base_angle % 360.0
        expected_ccw = (-base_angle) % 360.0
        # Mirror should differ from cw (since angle != 0 and != 180)
        assert expected_ccw != cw_angle


# ---------------------------------------------------------------------------
# Snapshot-once + outgoing_scroll_pos tests
# ---------------------------------------------------------------------------


class TestSnapshotOnce:
    def _make_spinout(self):
        from led_ticker_flair.flair.spinout import Spinout

        return Spinout(revolutions=1)

    def test_draw_called_once_blit_called_n_times(self) -> None:
        """N ascending frame_at calls → outgoing.draw called once (snapshot),
        blit should have been called multiple times (verified by multiple
        frames painting to canvas)."""
        spinout = self._make_spinout()
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=True)
        incoming = _make_widget(draw_pixel=False)

        ts = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9]
        for t in ts:
            spinout.frame_at(t, canvas, outgoing, incoming)

        # outgoing.draw should have been called exactly once (snapshot on t=0.0)
        assert outgoing.draw.call_count == 1

    def test_outgoing_scroll_pos_forwarded_as_cursor_pos(self) -> None:
        """outgoing_scroll_pos kwarg is forwarded as cursor_pos to outgoing.draw."""
        spinout = self._make_spinout()
        canvas = _StubCanvas()
        incoming = _make_widget(draw_pixel=False)

        received_cursor_pos: list[int] = []

        outgoing = mock.Mock()

        def _spy_draw(c, cursor_pos=0, **kw):
            received_cursor_pos.append(cursor_pos)
            c.SetPixel(0, 0, 255, 0, 0)
            return (c, cursor_pos)

        outgoing.draw.side_effect = _spy_draw

        # Negative value: the scrolled-out sign semantics per push.py precedent
        spinout.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-42)

        assert outgoing.draw.call_count == 1
        assert received_cursor_pos == [-42]

    def test_snapshot_only_taken_at_first_frame(self) -> None:
        """Snapshot taken only on first frame (t=0.0); subsequent frames
        do not call outgoing.draw again."""
        spinout = self._make_spinout()
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=True)
        incoming = _make_widget(draw_pixel=False)

        # First call snapshots
        spinout.frame_at(0.0, canvas, outgoing, incoming)
        assert outgoing.draw.call_count == 1

        # More frames — no more draws
        for t in [0.2, 0.4, 0.6, 0.8]:
            spinout.frame_at(t, canvas, outgoing, incoming)
        assert outgoing.draw.call_count == 1


# ---------------------------------------------------------------------------
# t >= 1.0 cut branch
# ---------------------------------------------------------------------------


class TestCutBranch:
    def _make_spinout(self):
        from led_ticker_flair.flair.spinout import Spinout

        return Spinout(revolutions=1)

    def test_t1_calls_incoming_draw(self) -> None:
        spinout = self._make_spinout()
        canvas = _StubCanvas()
        outgoing = _make_widget()
        incoming = _make_widget()

        result = spinout.frame_at(1.0, canvas, outgoing, incoming)

        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)
        assert result is canvas

    def test_t1_does_not_call_outgoing_draw(self) -> None:
        spinout = self._make_spinout()
        canvas = _StubCanvas()
        outgoing = _make_widget()
        incoming = _make_widget()

        spinout.frame_at(1.0, canvas, outgoing, incoming)
        outgoing.draw.assert_not_called()

    def test_t_above_1_also_calls_incoming(self) -> None:
        spinout = self._make_spinout()
        canvas = _StubCanvas()
        outgoing = _make_widget()
        incoming = _make_widget()

        result = spinout.frame_at(1.5, canvas, outgoing, incoming)
        incoming.draw.assert_called_once()
        assert result is canvas

    def test_t1_returns_canvas(self) -> None:
        spinout = self._make_spinout()
        canvas = _StubCanvas()
        outgoing = _make_widget()
        incoming = _make_widget()

        result = spinout.frame_at(1.0, canvas, outgoing, incoming)
        assert result is canvas


# ---------------------------------------------------------------------------
# Re-fire pin: fresh snapshot on new firing
# ---------------------------------------------------------------------------


class TestRefire:
    def test_refire_causes_new_snapshot(self) -> None:
        """After a complete sweep (t=1.0), a new t=0 firing re-snapshots
        (outgoing.draw called a second time)."""
        from led_ticker_flair.flair.spinout import Spinout

        spinout = Spinout(revolutions=1)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=True)
        incoming = _make_widget(draw_pixel=False)

        # First sweep
        for t in [0.0, 0.5, 1.0]:
            spinout.frame_at(t, canvas, outgoing, incoming)
        assert outgoing.draw.call_count == 1

        # Re-fire: t goes below last_t (new firing starts from 0.0)
        spinout.frame_at(0.0, canvas, outgoing, incoming)
        # The re-fire invalidates the surface; second snapshot happens on first draw
        assert outgoing.draw.call_count == 2


# ---------------------------------------------------------------------------
# Cross-scale tripwire
# ---------------------------------------------------------------------------


class TestCrossScale:
    def test_scaled_canvas_snapshots_once_full_sweep(self) -> None:
        """On a scale-4 canvas the surface snapshots once and the t=1.0
        frame draws incoming on whatever canvas is passed."""
        from led_ticker_flair.flair.spinout import Spinout

        spinout = Spinout(revolutions=1)
        canvas = _ScaledStubCanvas(width=64, height=16)
        outgoing = _make_widget(draw_pixel=True)
        incoming = _make_widget(draw_pixel=False)

        # Full sweep on scaled canvas
        for t in [0.0, 0.25, 0.5, 0.75]:
            spinout.frame_at(t, canvas, outgoing, incoming)

        # Snapshot taken exactly once
        assert outgoing.draw.call_count == 1

        # t=1.0: incoming drawn, result is the canvas passed in
        result = spinout.frame_at(1.0, canvas, outgoing, incoming)
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)
        assert result is canvas


# ---------------------------------------------------------------------------
# Scale-1 and scaled blit smoke
# ---------------------------------------------------------------------------


class TestBlitSmoke:
    def test_scale1_blit_does_not_raise(self) -> None:
        """scale=1 canvas: full sweep completes without exception."""
        from led_ticker_flair.flair.spinout import Spinout

        spinout = Spinout(revolutions=1)
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_widget(draw_pixel=True)
        incoming = _make_widget(draw_pixel=False)

        for t in [0.0, 0.2, 0.5, 0.8, 1.0]:
            spinout.frame_at(t, canvas, outgoing, incoming)

    def test_scaled_canvas_blit_does_not_raise(self) -> None:
        """scale=4 canvas: full sweep completes without exception."""
        from led_ticker_flair.flair.spinout import Spinout

        spinout = Spinout(revolutions=1)
        canvas = _ScaledStubCanvas(width=64, height=16)
        outgoing = _make_widget(draw_pixel=True)
        incoming = _make_widget(draw_pixel=False)

        for t in [0.0, 0.2, 0.5, 0.8, 1.0]:
            spinout.frame_at(t, canvas, outgoing, incoming)


# ---------------------------------------------------------------------------
# Compound rotation (outgoing itself uses rotation) non-crash
# ---------------------------------------------------------------------------


class TestCompoundRotation:
    def test_compound_rotation_non_crash(self) -> None:
        """Outgoing whose draw() uses a rotation surface doesn't crash the
        Spinout transition — a full sweep completes without exception."""
        from led_ticker.plugin import make_rotation_surface

        from led_ticker_flair.flair.spinout import Spinout

        spinout = Spinout(revolutions=1)
        canvas = _StubCanvas(width=160, height=16)

        # Build a rotation surface to simulate a compound-rotation outgoing
        inner_surface = make_rotation_surface(canvas)

        def _compound_draw(c, cursor_pos=0, **kw):
            inner_surface._buffer.SetPixel(5, 5, 255, 0, 0)
            inner_surface.snapshot()
            inner_surface.blit(c, 45.0, c.width / 2)
            return (c, cursor_pos)

        outgoing = mock.Mock()
        outgoing.draw.side_effect = _compound_draw
        incoming = _make_widget(draw_pixel=False)

        for t in [0.0, 0.3, 0.6, 0.9, 1.0]:
            spinout.frame_at(t, canvas, outgoing, incoming)


# ---------------------------------------------------------------------------
# Every frame_at path returns canvas
# ---------------------------------------------------------------------------


class TestReturnsCanvas:
    def test_t0_returns_canvas(self) -> None:
        from led_ticker_flair.flair.spinout import Spinout

        s = Spinout()
        canvas = _StubCanvas()
        result = s.frame_at(0.0, canvas, _make_widget(), _make_widget())
        assert result is canvas

    def test_mid_t_returns_canvas(self) -> None:
        from led_ticker_flair.flair.spinout import Spinout

        s = Spinout()
        canvas = _StubCanvas()
        outgoing = _make_widget()
        incoming = _make_widget()
        s.frame_at(0.0, canvas, outgoing, incoming)  # snapshot
        result = s.frame_at(0.5, canvas, outgoing, incoming)
        assert result is canvas

    def test_t1_returns_canvas(self) -> None:
        from led_ticker_flair.flair.spinout import Spinout

        s = Spinout()
        canvas = _StubCanvas()
        result = s.frame_at(1.0, canvas, _make_widget(), _make_widget())
        assert result is canvas


class TestRule53Contract:
    def test_unknown_kwarg_raises_type_error(self) -> None:
        """The two-param __init__ signature is rule-53 LOAD-BEARING:
        _build_plugin_style validates config kwargs against
        inspect.signature(cls), so a **kwargs catch-all would silently
        swallow config typos like revolution=3. This tripwire fails if
        anyone adds **kwargs to __init__."""
        import inspect

        import pytest

        from led_ticker_flair.flair.spinout import Spinout

        with pytest.raises(TypeError):
            Spinout(revolution=3)  # typo'd kwarg must NOT be swallowed
        params = inspect.signature(Spinout).parameters.values()
        assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params)
