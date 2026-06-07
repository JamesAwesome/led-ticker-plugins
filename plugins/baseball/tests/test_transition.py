"""Tests for the ported Baseball transition + hi-res rolling-ball path.

Combined from three core test files:
  - tests/test_baseball.py (whole file)
  - tests/test_hires_loader.py (baseball rotation tests)
  - tests/test_transitions.py (baseball snap + frame-drawing tests)

Imports the transition family / hi-res helpers from
``led_ticker_baseball.transition`` (the plugin port). Registry-based
``test_registered`` tests are dropped — registration is wired in
``register(api)`` in a later task.
"""

import unittest.mock as mock

from rgbmatrix import _StubCanvas

from led_ticker.scaled_canvas import ScaledCanvas
from led_ticker_baseball.transition import (
    BASEBALL_FRAMES,
    SNAP_THRESHOLD,
    SPRITE_SIZE,
    Baseball,
    BaseballAlternating,
    BaseballReverse,
    draw_baseball_frame,
    draw_baseball_frame_rtl,
)


class TestBaseballSprite:
    def test_has_four_frames(self):
        assert len(BASEBALL_FRAMES) == 4

    def test_each_frame_has_pixels(self):
        for frame in BASEBALL_FRAMES:
            assert len(frame) > 0

    def test_sprite_pixels_in_bounds(self):
        for frame in BASEBALL_FRAMES:
            for dx, dy, r, g, b in frame:
                assert 0 <= dx < SPRITE_SIZE
                assert 0 <= dy < SPRITE_SIZE
                assert 0 <= r <= 255
                assert 0 <= g <= 255
                assert 0 <= b <= 255

    def test_frames_have_similar_pixel_count(self):
        """All rotation frames should have the same number of pixels (same circle)."""
        counts = [len(f) for f in BASEBALL_FRAMES]
        assert max(counts) - min(counts) == 0


class TestDrawBaseballFrame:
    def test_at_zero_ball_offscreen_left(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_baseball_frame(canvas, 0.0, width=40, height=16)
        # At t=0 the ball is fully offscreen to the left → nothing lit.
        assert canvas.count_nonzero() == 0

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_baseball_frame(canvas, 0.5, width=40, height=16)
        assert canvas.count_nonzero() > 0

    def test_blackout_left_of_ball(self):
        canvas = _StubCanvas(width=160, height=16)
        for y in range(16):
            for x in range(160):
                canvas.SetPixel(x, y, 100, 100, 100)
        draw_baseball_frame(canvas, 0.5, width=160, height=16)
        assert canvas.get_pixel(0, 8) == (0, 0, 0)

    def test_no_out_of_bounds(self):
        canvas = _StubCanvas(width=40, height=16)
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            draw_baseball_frame(canvas, p, width=40, height=16)
            for x, y in canvas._pixels:
                assert 0 <= x < 40
                assert 0 <= y < 16

    def test_progressive_blackout(self):
        """More left-side pixels blacked out as progress increases."""
        prev_black = 0
        for step in range(1, 11):
            p = step / 10.0
            canvas = _StubCanvas(width=80, height=16)
            for y in range(16):
                for x in range(80):
                    canvas.SetPixel(x, y, 100, 100, 100)
            draw_baseball_frame(canvas, p, width=80, height=16)
            black = sum(1 for v in canvas._pixels.values() if v == (0, 0, 0))
            assert black >= prev_black
            prev_black = black


class TestDrawBaseballFrameRTL:
    def test_at_zero_ball_offscreen_right(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_baseball_frame_rtl(canvas, 0.0, width=40, height=16)
        # At t=0 the ball is fully offscreen to the right → nothing lit.
        assert canvas.count_nonzero() == 0

    def test_at_midpoint_draws_pixels(self):
        canvas = _StubCanvas(width=40, height=16)
        draw_baseball_frame_rtl(canvas, 0.5, width=40, height=16)
        assert canvas.count_nonzero() > 0

    def test_blackout_right_of_ball(self):
        canvas = _StubCanvas(width=160, height=16)
        for y in range(16):
            for x in range(160):
                canvas.SetPixel(x, y, 100, 100, 100)
        draw_baseball_frame_rtl(canvas, 0.5, width=160, height=16)
        assert canvas.get_pixel(159, 8) == (0, 0, 0)

    def test_no_out_of_bounds(self):
        canvas = _StubCanvas(width=40, height=16)
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            draw_baseball_frame_rtl(canvas, p, width=40, height=16)
            for x, y in canvas._pixels:
                assert 0 <= x < 40
                assert 0 <= y < 16

    def test_sprite_is_flipped(self):
        canvas_ltr = _StubCanvas(width=160, height=16)
        canvas_rtl = _StubCanvas(width=160, height=16)
        draw_baseball_frame(canvas_ltr, 0.3, width=160, height=16)
        draw_baseball_frame_rtl(canvas_rtl, 0.3, width=160, height=16)
        ltr_pixels = set(canvas_ltr._pixels.keys())
        rtl_pixels = set(canvas_rtl._pixels.keys())
        assert ltr_pixels != rtl_pixels


class TestBaseballTransition:
    def test_frame_at_draws_to_canvas(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        bb = Baseball()
        result = bb.frame_at(0.5, pixel_canvas, outgoing, incoming)
        assert result is pixel_canvas

    def test_midpoint_draws_outgoing(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        bb = Baseball()
        bb.frame_at(0.3, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called

    def test_complete_shows_incoming_only(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        bb = Baseball()
        bb.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called

    def test_returns_canvas(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        bb = Baseball()
        result = bb.frame_at(0.5, pixel_canvas, make_widget(40), make_widget(40))
        assert result is pixel_canvas


class TestBaseballReverseTransition:
    def test_complete_shows_incoming(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        bb = BaseballReverse()
        bb.frame_at(1.0, pixel_canvas, outgoing, incoming)
        assert not outgoing.draw.called
        assert incoming.draw.called

    def test_midpoint_draws_outgoing(self, make_widget):
        pixel_canvas = _StubCanvas(width=40, height=16)
        outgoing = make_widget(40)
        incoming = make_widget(40)
        bb = BaseballReverse()
        bb.frame_at(0.3, pixel_canvas, outgoing, incoming)
        assert outgoing.draw.called


class TestBaseballAlternatingTransition:
    def test_alternates_direction(self, make_widget):
        bb = BaseballAlternating()
        canvas = _StubCanvas(width=40, height=16)
        bb.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert bb._index == 0
        bb.frame_at(1.0, canvas, make_widget(40), make_widget(40))
        bb.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert bb._index == 1
        bb.frame_at(1.0, canvas, make_widget(40), make_widget(40))
        bb.frame_at(0.0, canvas, make_widget(40), make_widget(40))
        assert bb._index == 0


class TestBaseballHiresDispatch:
    def test_lowres_path_for_mock_canvas(self):
        """Mock isn't a ScaledCanvas → lowres path. Existing behavior preserved."""
        canvas = mock.MagicMock()
        canvas.width = 160
        canvas.height = 16
        outgoing = mock.MagicMock()
        incoming = mock.MagicMock()

        bb = Baseball()
        with (
            mock.patch.object(
                bb, "_frame_at_lowres", wraps=bb._frame_at_lowres
            ) as lowres,
            mock.patch.object(
                bb, "_frame_at_hires", wraps=bb._frame_at_hires
            ) as hires,
        ):
            bb.frame_at(0.5, canvas, outgoing, incoming)
            lowres.assert_called_once()
            hires.assert_not_called()

    def test_hires_paints_visible_baseball_pixels(self):
        """ScaledCanvas → hires path produces white + red stitch pixels."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)

        outgoing = mock.MagicMock()
        incoming = mock.MagicMock()
        Baseball().frame_at(0.4, wrapped, outgoing, incoming, duration_ms=1500)

        white_pixels = sum(
            1
            for y in range(real.height)
            for x in range(real.width)
            if real.get_pixel(x, y) == (250, 250, 245)
        )
        red_stitches = sum(
            1
            for y in range(real.height)
            for x in range(real.width)
            if real.get_pixel(x, y) == (200, 30, 40)
        )
        assert white_pixels > 100, "expected hi-res baseball white body pixels"
        assert red_stitches > 0, "expected hi-res baseball red stitch pixels"

    def test_baseball_reverse_hires(self):
        """BaseballReverse on ScaledCanvas paints visible baseball."""
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)

        outgoing = mock.MagicMock()
        incoming = mock.MagicMock()
        BaseballReverse().frame_at(0.4, wrapped, outgoing, incoming, duration_ms=1500)

        white_pixels = sum(
            1
            for y in range(real.height)
            for x in range(real.width)
            if real.get_pixel(x, y) == (250, 250, 245)
        )
        assert white_pixels > 100


# --- scale_switch_at ---


class TestScaleSwitchAt:
    """Tripwire: baseball variants must set scale_switch_at=SNAP_THRESHOLD so
    the outgoing widget is drawn at its native scale during the trail phase.
    """

    def test_baseball_switches_at_snap_threshold(self):
        assert Baseball.scale_switch_at == SNAP_THRESHOLD

    def test_baseball_reverse_switches_at_snap_threshold(self):
        assert BaseballReverse.scale_switch_at == SNAP_THRESHOLD

    def test_baseball_alternating_switches_at_snap_threshold(self):
        assert BaseballAlternating.scale_switch_at == SNAP_THRESHOLD


# --- Hi-res rolling rotation (ported from test_hires_loader.py) ---


class TestBaseballRotation:
    """Baseball rotation index advances with travel, producing visually
    distinct frames as the ball rolls. Locks in the 'rolling' behavior."""

    def _setup(self):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        opts = RGBMatrixOptions()
        opts.cols = 256
        opts.rows = 64
        opts.chain_length = 1
        opts.parallel = 1
        real = RGBMatrix(options=opts).CreateFrameCanvas()
        wrapped = ScaledCanvas(real, scale=4, content_height=16)
        return real, wrapped

    def _render_at(self, t, real, wrapped, *, flip_horizontal=False):
        from led_ticker_baseball.transition import render_hires_baseball_frame

        # Reset canvas before each render
        for y in range(real.height):
            for x in range(real.width):
                real.SetPixel(x, y, 0, 0, 0)

        outgoing = mock.MagicMock()
        incoming = mock.MagicMock()
        render_hires_baseball_frame(
            t,
            wrapped,
            outgoing,
            incoming,
            flip_horizontal=flip_horizontal,
            duration_ms=1500,
        )

    def _white_pixels_set(self, real):
        # Snapshot of where the ball's white body lit up (modulo trail).
        # Ball-white in this codebase is (250, 250, 245).
        return {
            (x, y)
            for y in range(real.height)
            for x in range(real.width)
            if real.get_pixel(x, y) == (250, 250, 245)
        }

    def test_rotation_produces_distinct_frames_across_travel(self):
        """At several t values mid-traversal the WHITE-pixel pattern of
        the ball should differ between samples — proves rotation_idx is
        cycling. We sample 4 t values spread evenly across the visible
        traversal."""
        real, wrapped = self._setup()
        snapshots = []
        for t in [0.15, 0.35, 0.55, 0.75]:
            self._render_at(t, real, wrapped)
            snapshots.append(self._white_pixels_set(real))

        # At least 2 distinct rotation positions observed across the 4
        # samples. Some samples may coincidentally land on the same
        # rotation_idx % 8, but with 8 frames over the full panel width
        # at least 2 must differ for "rolling" to be true.
        unique = {frozenset(s) for s in snapshots}
        assert len(unique) >= 2, (
            f"baseball did not rotate as it traveled: only "
            f"{len(unique)} distinct frame snapshot(s) over 4 samples"
        )

    def test_rtl_rotation_produces_distinct_frames(self):
        """Same property holds for the reverse direction."""
        real, wrapped = self._setup()
        snapshots = []
        for t in [0.15, 0.35, 0.55, 0.75]:
            self._render_at(t, real, wrapped, flip_horizontal=True)
            snapshots.append(self._white_pixels_set(real))

        unique = {frozenset(s) for s in snapshots}
        assert len(unique) >= 2

    def test_rotation_constants_align(self):
        """_BASEBALL_ROTATION_FRAMES is the divisor used by the renderer's
        pixels_per_rotation_frame formula. If a future change drops the
        constant out of sync, this test catches it."""
        from led_ticker_baseball.transition import _BASEBALL_ROTATION_FRAMES

        assert _BASEBALL_ROTATION_FRAMES >= 4, (
            "fewer than 4 rotation frames means the ball will read as "
            "alternating between 2 patterns instead of rolling"
        )
        assert _BASEBALL_ROTATION_FRAMES <= 32, (
            "more than 32 frames over a single panel-width traversal "
            "would cycle so fast it looks chaotic on a 256-wide panel"
        )


# --- Hi-res snap (ported from test_transitions.py) ---


class TestHiresSnapRespectsIncomingBg:
    """The hires snap inside `render_hires_baseball_frame`
    (`_snap_reset`) does its own bg-aware reset before drawing incoming
    at t>=SNAP_THRESHOLD. Without it, the snap calls `canvas.Clear()`
    and the last transition frame paints incoming on black — clobbering
    the Fill(incoming_bg) that `run_transition` did one line earlier.
    """

    def test_snap_clear_when_incoming_bg_is_none(self):
        """Default → snap calls Clear(). Legacy behavior preserved
        for transitions between two no-bg sections."""
        from led_ticker_baseball.transition import _snap_reset

        canvas = mock.MagicMock()
        _snap_reset(canvas, None)
        canvas.Clear.assert_called_once_with()
        canvas.Fill.assert_not_called()

    def test_snap_fill_when_incoming_bg_set(self):
        """Tuple `(r, g, b)` → snap calls Fill(r, g, b) instead of
        Clear, so the snap-drawn incoming sits on the right bg."""
        from led_ticker_baseball.transition import _snap_reset

        canvas = mock.MagicMock()
        _snap_reset(canvas, (255, 230, 80))
        canvas.Fill.assert_called_once_with(255, 230, 80)
        canvas.Clear.assert_not_called()

    def test_snap_normalizes_graphics_color(self):
        """`_snap_reset` accepts an un-normalized `graphics.Color` —
        future direct callers that pass a widget's `bg_color` (which is
        a Color post-coercion) work without re-normalizing at every site."""
        from rgbmatrix.graphics import Color

        from led_ticker_baseball.transition import _snap_reset

        canvas = mock.MagicMock()
        _snap_reset(canvas, Color(42, 0, 16))
        canvas.Fill.assert_called_once_with(42, 0, 16)
        canvas.Clear.assert_not_called()

    def test_baseball_hires_snap_uses_fill_when_incoming_bg_set(self):
        """End-to-end integration tripwire on the snap path. Drives
        `Baseball.frame_at(t=0.95)` through the hires dispatch (real
        ScaledCanvas → real `render_hires_baseball_frame` →
        `_snap_reset`) with `incoming_bg_color` set, asserts the
        underlying real canvas saw `Fill(...)` and NOT `Clear()`.

        Baseball is fully procedural (no Pillow decode), so this test
        runs without mocking any cache.
        """
        # Mock real canvas. ScaledCanvas.Fill / .Clear delegate to
        # `self.real.Fill` / `self.real.Clear`, so spying on the mock
        # captures both wrapper-level and direct calls.
        real = mock.MagicMock()
        real.width = 256
        real.height = 64
        wrapper = ScaledCanvas(real, scale=4)

        outgoing = mock.Mock()
        incoming = mock.Mock()
        bb = Baseball()

        # t=0.95 is the SNAP_THRESHOLD; t=1.0 short-circuits to the
        # `t >= 1.0` early return BEFORE the hires dispatch, which
        # is a different (also correct) path. 0.95 forces the snap
        # branch inside render_hires_baseball_frame.
        bb.frame_at(
            0.95,
            wrapper,
            outgoing,
            incoming,
            incoming_bg_color=(255, 230, 80),
        )

        # The snap must Fill, not Clear. Outgoing.draw and the trail
        # paint via SetPixel — those don't touch Fill/Clear. So any
        # Fill call here came from _snap_reset.
        assert real.Fill.called, (
            "Baseball hires snap did not call Fill — "
            "`_snap_reset` regressed to `canvas.Clear()`"
        )
        real.Fill.assert_any_call(255, 230, 80)
        real.Clear.assert_not_called()


# --- SubFill blackout (ported from test_transitions.py) ---


class TestBaseballFrameDrawing:
    def test_ltr_blackout_uses_subfill(self, canvas):
        draw_baseball_frame(canvas, progress=0.5, width=160, height=16)
        assert canvas.SubFill.call_count >= 1
        first_call = canvas.SubFill.call_args_list[0]
        assert first_call.args[0] == 0
        assert first_call.args[1] == 0
        assert first_call.args[4:] == (0, 0, 0)

    def test_rtl_blackout_uses_subfill(self, canvas):
        draw_baseball_frame_rtl(canvas, progress=0.5, width=160, height=16)
        assert canvas.SubFill.call_count >= 1
        first_call = canvas.SubFill.call_args_list[0]
        assert first_call.args[1] == 0
        assert first_call.args[4:] == (0, 0, 0)
