"""flair.lottery — pure geometry + roll-timeline math (Task 1, no widget),
the ball-face painter (Task 2), and widget config validation +
registration (Task 4)."""

import logging
import math

import pytest
from led_ticker.plugin import (
    ENGINE_TICK_MS,
    HeadlessCanvas,
    ScaledCanvas,
    ValidationContext,
    make_rotation_surface,
    unwrap_to_real,
)

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.lottery import (
    _INSET_NO_BORDER,
    _INSET_WITH_BORDER,
    PALETTE,
    Lottery,
    auto_font_size,
    ball_phase,
    layout,
    paint_face,
    ticks_per_ball,
)


class TestPalette:
    def test_eight_spec_colors_in_order(self) -> None:
        assert PALETTE == (
            (255, 60, 60),
            (60, 220, 60),
            (255, 180, 0),
            (80, 140, 255),
            (255, 80, 255),
            (0, 220, 220),
            (255, 120, 40),
            (170, 90, 255),
        )


class TestLayout:
    def test_three_words_diameter(self) -> None:
        diameter, slots = layout(3, 256, 64, 1)
        # min(64 - 2*1, 256 // 3 - 4) == min(62, 81) == 62
        assert diameter == 62
        assert len(slots) == 3

    def test_eight_words_diameter(self) -> None:
        diameter, slots = layout(8, 256, 64, 1)
        # min(62, 256 // 8 - 4) == min(62, 28) == 28
        assert diameter == 28
        assert len(slots) == 8

    def test_slots_evenly_spaced(self) -> None:
        diameter, slots = layout(3, 256, 64, 1)
        stride = diameter + 4  # GAP
        diffs = [b - a for a, b in zip(slots, slots[1:], strict=False)]
        assert diffs == [stride] * (len(slots) - 1)

    def test_slots_centered_as_a_group(self) -> None:
        panel_w = 256
        for n in (3, 8):
            _diameter, slots = layout(n, panel_w, 64, 1)
            mean = (slots[0] + slots[-1]) / 2
            assert mean == pytest.approx(panel_w / 2)

    def test_three_words_exact_slot_centers(self) -> None:
        diameter, slots = layout(3, 256, 64, 1)
        assert (diameter, slots) == (62, [62, 128, 194])

    def test_eight_words_exact_slot_centers(self) -> None:
        diameter, slots = layout(8, 256, 64, 1)
        assert (diameter, slots) == (28, [16, 48, 80, 112, 144, 176, 208, 240])

    def test_slot_centers_are_ints(self) -> None:
        _diameter, slots = layout(3, 256, 64, 1)
        assert all(isinstance(cx, int) for cx in slots)


class TestTicksPerBall:
    def test_800ms_is_16_ticks(self) -> None:
        assert ticks_per_ball(800) == 16

    def test_uses_engine_tick_ms(self) -> None:
        assert ENGINE_TICK_MS == 50
        assert ticks_per_ball(500) == 500 // ENGINE_TICK_MS

    def test_floor_is_one_tick(self) -> None:
        assert ticks_per_ball(1) == 1
        assert ticks_per_ball(0) == 1


class TestBallPhase:
    TPB = 16
    DIAMETER = 28
    SLOT_CX = 80  # ball index 2's slot from the 8-word layout above

    def test_before_window_is_off_canvas(self) -> None:
        cx, angle, settled = ball_phase(0, 2, self.TPB, self.DIAMETER, self.SLOT_CX)
        assert cx == -float(self.DIAMETER)
        assert settled is False

    def test_before_window_covers_every_earlier_frame(self) -> None:
        start = 2 * self.TPB
        for frame in range(0, start):
            cx, _angle, settled = ball_phase(
                frame, 2, self.TPB, self.DIAMETER, self.SLOT_CX
            )
            assert cx == -float(self.DIAMETER)
            assert settled is False

    def test_window_starts_exactly_at_index_times_tpb(self) -> None:
        start = 2 * self.TPB
        before_cx, _, before_settled = ball_phase(
            start - 1, 2, self.TPB, self.DIAMETER, self.SLOT_CX
        )
        at_cx, _, at_settled = ball_phase(
            start, 2, self.TPB, self.DIAMETER, self.SLOT_CX
        )
        assert before_cx == -float(self.DIAMETER)
        assert before_settled is False
        # At t=0 the ball is already launched (on-canvas at -diameter/2),
        # distinct from the off-canvas parked position.
        assert at_cx == pytest.approx(-self.DIAMETER / 2)
        assert at_settled is False

    def test_next_balls_window_starts_at_i_plus_1_times_tpb(self) -> None:
        for i in (0, 1, 2, 3):
            start = (i + 1) * self.TPB
            cx, _, settled = ball_phase(
                start, i + 1, self.TPB, self.DIAMETER, self.SLOT_CX
            )
            assert cx == pytest.approx(-self.DIAMETER / 2)
            assert settled is False

    def test_cx_monotonically_increases_during_window(self) -> None:
        start = 2 * self.TPB
        prev = -math.inf
        for frame in range(start, start + self.TPB):
            cx, _angle, _settled = ball_phase(
                frame, 2, self.TPB, self.DIAMETER, self.SLOT_CX
            )
            assert cx > prev
            prev = cx

    def test_settled_flag_flips_exactly_at_window_end(self) -> None:
        start = 2 * self.TPB
        end = start + self.TPB
        _cx, _angle, settled_last_tick = ball_phase(
            end - 1, 2, self.TPB, self.DIAMETER, self.SLOT_CX
        )
        _cx, _angle, settled_at_end = ball_phase(
            end, 2, self.TPB, self.DIAMETER, self.SLOT_CX
        )
        assert settled_last_tick is False
        assert settled_at_end is True

    def test_angle_is_exactly_zero_at_settle(self) -> None:
        start = 2 * self.TPB
        end = start + self.TPB
        for frame in (end, end + 1, end + 500):
            cx, angle, settled = ball_phase(
                frame, 2, self.TPB, self.DIAMETER, self.SLOT_CX
            )
            assert cx == float(self.SLOT_CX)
            assert angle == 0.0
            assert settled is True

    def test_angle_approaches_zero_continuously(self) -> None:
        start = 2 * self.TPB
        end = start + self.TPB
        prev_abs = math.inf
        for frame in range(start, end):
            _cx, angle, _settled = ball_phase(
                frame, 2, self.TPB, self.DIAMETER, self.SLOT_CX
            )
            assert angle <= 0.0  # negated: leftward-entry roll
            assert abs(angle) <= prev_abs + 1e-9
            prev_abs = abs(angle)

    def test_angle_matches_remaining_distance_formula(self) -> None:
        # Pin the exact formula at a specific mid-window frame so an
        # accidental sign flip / wrong radius can't sneak through the
        # monotonic/negative-only checks above.
        frame = 2 * self.TPB + 8  # t = 0.5 exactly (TPB=16)
        cx, angle, _settled = ball_phase(
            frame, 2, self.TPB, self.DIAMETER, self.SLOT_CX
        )
        t_eased = 1.0 - (1.0 - 0.5) ** 3
        launch_cx = -self.DIAMETER / 2
        expected_cx = launch_cx + t_eased * (self.SLOT_CX - launch_cx)
        radius = self.DIAMETER / 2
        expected_angle = -math.degrees((self.SLOT_CX - expected_cx) / radius)
        assert cx == pytest.approx(expected_cx)
        assert angle == pytest.approx(expected_angle)
        assert angle != 0.0  # genuinely mid-roll, not a degenerate 0 match


class TestAutoFontSize:
    def test_kebab_fits_at_diameter_56_scale_4(self) -> None:
        size = auto_font_size("kebab", 56, "Inter-Bold", 4)
        assert size >= 8

    def test_kebab_size_is_largest_that_fits(self) -> None:
        """Regression tripwire for the chord-factor / range-bound math, pinned
        as an INVARIANT rather than an exact integer: freetype glyph advances
        differ by ~1px across platforms (13 on macOS vs 14 on Linux CI for this
        exact input), so we assert the returned size fits the 0.72 chord and
        the next size up does not."""
        from led_ticker.plugin import get_text_width, resolve_font

        diameter = 56
        chord = diameter * 0.72
        size = auto_font_size("kebab", diameter, "Inter-Bold", 4)
        assert 12 <= size <= 15  # sane band; catches gross chord/range drift
        from led_ticker_flair.flair.lottery import _REAL_SCALE1_STUB

        assert (
            get_text_width(
                resolve_font("Inter-Bold", size),
                "kebab",
                padding=0,
                canvas=_REAL_SCALE1_STUB,
            )
            <= chord
        )
        assert (
            get_text_width(
                resolve_font("Inter-Bold", size + 1),
                "kebab",
                padding=0,
                canvas=_REAL_SCALE1_STUB,
            )
            > chord
        )

    def test_long_word_does_not_fit_small_ball(self) -> None:
        word = "abcdefghijklmnopqrst"  # 20 chars
        assert auto_font_size(word, 28, "Inter-Bold", 4) == 0

    def test_larger_diameter_allows_larger_or_equal_size(self) -> None:
        small = auto_font_size("hi", 28, "Inter-Bold", 4)
        large = auto_font_size("hi", 62, "Inter-Bold", 4)
        assert large >= small

    def test_rejects_bad_scale(self) -> None:
        with pytest.raises(ValueError):
            auto_font_size("hi", 56, "Inter-Bold", 0)
        with pytest.raises(ValueError):
            auto_font_size("hi", 56, "Inter-Bold", True)
        with pytest.raises(ValueError):
            auto_font_size("hi", 56, "Inter-Bold", 1.5)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# paint_face (Task 2)
# ---------------------------------------------------------------------------

# Panel geometry mirrors the bigsign: 256x64 real, scale=4, content_height=16
# (full-height content band -> y_offset_real == 0, no letterboxing).
_PANEL_W, _PANEL_H = 256, 64
_SCALE = 4
_CONTENT_HEIGHT = 16
_CX_LOGICAL = 32.0  # panel-center in logical coords (real cx == 128)
_CY_LOGICAL = 8.0  # panel-center in logical coords (real cy == 32)
_CX_P, _CY_P = 128, 32  # the same center, in real pixels
_R_P = 31  # ball radius, real px (diameter 62 -- matches layout()'s 3-word case)


def _make_wrapper() -> ScaledCanvas:
    real = HeadlessCanvas(width=_PANEL_W, height=_PANEL_H)
    return ScaledCanvas(real, scale=_SCALE, content_height=_CONTENT_HEIGHT)


def _paint_and_blit(**paint_kwargs) -> HeadlessCanvas:
    """Paint a face onto a fresh rotation surface, snapshot it, and blit it
    (angle=0, no rotation) onto a second fresh real canvas -- the brief's
    prescribed round-trip so assertions run on ordinary real-canvas pixels
    rather than reaching into the surface's internal buffer."""
    surface = make_rotation_surface(_make_wrapper())
    paint_face(surface.target, **paint_kwargs)
    surface.snapshot()

    live_real = HeadlessCanvas(width=_PANEL_W, height=_PANEL_H)
    live = ScaledCanvas(live_real, scale=_SCALE, content_height=_CONTENT_HEIGHT)
    surface.blit(live, angle_deg=0.0, cx_logical=paint_kwargs["cx_logical"])
    return live_real


class TestPaintFaceClassic:
    def test_face_is_white(self) -> None:
        real = _paint_and_blit(
            cx_logical=_CX_LOGICAL,
            cy_logical=_CY_LOGICAL,
            r_px=_R_P,
            style="classic",
            color=(255, 60, 60),
            word="kebab",
            font_name="Inter-Bold",
            scale=_SCALE,
        )
        ring_w = max(1, _R_P // 8)
        # Sample well inside the face, clear of the ring band and (for a
        # 62px ball) clear of the vertically-centered text.
        assert real.get_pixel(_CX_P, _CY_P - _R_P + ring_w + 4) == (255, 255, 255)

    def test_ring_is_the_configured_color(self) -> None:
        ring_color = (255, 60, 60)
        real = _paint_and_blit(
            cx_logical=_CX_LOGICAL,
            cy_logical=_CY_LOGICAL,
            r_px=_R_P,
            style="classic",
            color=ring_color,
            word="kebab",
            font_name="Inter-Bold",
            scale=_SCALE,
        )
        # Rim samples, left and right of center.
        assert real.get_pixel(_CX_P + _R_P - 1, _CY_P) == ring_color
        assert real.get_pixel(_CX_P - _R_P + 1, _CY_P) == ring_color

    def test_dark_text_pixels_present(self) -> None:
        real = _paint_and_blit(
            cx_logical=_CX_LOGICAL,
            cy_logical=_CY_LOGICAL,
            r_px=_R_P,
            style="classic",
            color=(255, 60, 60),
            word="kebab",
            font_name="Inter-Bold",
            scale=_SCALE,
        )
        dark_pixels = [xy for xy, rgb in real._pixels.items() if rgb == (10, 10, 10)]
        assert dark_pixels, "expected dark (10,10,10) text pixels inside the face"

    def test_nothing_painted_outside_circle_bounding_box(self) -> None:
        real = _paint_and_blit(
            cx_logical=_CX_LOGICAL,
            cy_logical=_CY_LOGICAL,
            r_px=_R_P,
            style="classic",
            color=(255, 60, 60),
            word="kebab",
            font_name="Inter-Bold",
            scale=_SCALE,
        )
        tol = 1  # blit is a rotate + half-res round-trip, not pixel-exact
        for (x, y), rgb in real._pixels.items():
            if rgb == (0, 0, 0):
                continue
            assert _CX_P - _R_P - tol <= x <= _CX_P + _R_P + tol, (x, y, rgb)
            assert _CY_P - _R_P - tol <= y <= _CY_P + _R_P + tol, (x, y, rgb)


class TestPaintFaceSolid:
    def test_fill_and_white_text(self) -> None:
        fill_color = (80, 140, 255)
        real = _paint_and_blit(
            cx_logical=_CX_LOGICAL,
            cy_logical=_CY_LOGICAL,
            r_px=_R_P,
            style="solid",
            color=fill_color,
            word="kebab",
            font_name="Inter-Bold",
            scale=_SCALE,
        )
        # Sample well inside the face, clear of the text.
        assert real.get_pixel(_CX_P, _CY_P - _R_P + 4) == fill_color

        white_pixels = [
            xy for xy, rgb in real._pixels.items() if rgb == (255, 255, 255)
        ]
        assert white_pixels, "expected white text pixels on the solid face"

        # No dark classic-style text color should appear.
        dark_pixels = [xy for xy, rgb in real._pixels.items() if rgb == (10, 10, 10)]
        assert not dark_pixels


class TestPaintFaceUnfittableWord:
    def test_circle_paints_without_text_and_logs_once(self, caplog) -> None:
        long_word = "abcdefghijklmnopqrst"  # pinned in TestAutoFontSize as a 0-fit
        small_r_px = 14  # diameter 28, matches the pinned auto_font_size case
        with caplog.at_level(logging.WARNING, logger="led_ticker_flair"):
            real = _paint_and_blit(
                cx_logical=_CX_LOGICAL,
                cy_logical=_CY_LOGICAL,
                r_px=small_r_px,
                style="classic",
                color=(60, 220, 60),
                word=long_word,
                font_name="Inter-Bold",
                scale=_SCALE,
            )

        assert real.count_nonzero() > 0, "the circle itself must still be painted"
        dark_pixels = [xy for xy, rgb in real._pixels.items() if rgb == (10, 10, 10)]
        assert not dark_pixels, "no text should have been drawn"

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1


class TestPaintFaceRejectsBadStyle:
    def test_unknown_style_raises(self) -> None:
        surface = make_rotation_surface(_make_wrapper())
        with pytest.raises(ValueError):
            paint_face(
                surface.target,
                cx_logical=_CX_LOGICAL,
                cy_logical=_CY_LOGICAL,
                r_px=_R_P,
                style="not-a-style",
                color=(255, 60, 60),
                word="kebab",
                font_name="Inter-Bold",
                scale=_SCALE,
            )


# ---------------------------------------------------------------------------
# Lottery widget (Task 3)
# ---------------------------------------------------------------------------


class _RecordingBorder:
    """Test double for the ``border`` field: records the underlying real
    canvas's lit-pixel count at the moment ``paint`` is called, so a test
    can assert the border ran BEFORE any ball pixel landed (order via a
    side-channel observation, not a mock call-order API)."""

    def __init__(self) -> None:
        self.calls: list[int] = []

    def paint(self, canvas, frame) -> None:
        self.calls.append(unwrap_to_real(canvas).count_nonzero())


class TestLotteryWidget:
    WORDS = ["cat", "dog", "fox"]

    def _widget(self, **kwargs) -> Lottery:
        return Lottery(words=list(self.WORDS), **kwargs)

    def test_scale_one_paints_nothing_and_logs_once(self, caplog) -> None:
        real = HeadlessCanvas(width=_PANEL_W, height=_PANEL_H)  # unscaled
        widget = self._widget()
        with caplog.at_level(logging.WARNING, logger="led_ticker_flair"):
            widget.draw(real)
            widget.draw(real)  # second call must NOT re-log (latch)

        assert real.count_nonzero() == 0
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "flair.lottery" in warnings[0].getMessage()
        assert "scaled display" in warnings[0].getMessage()

    def test_frame_zero_lights_pixels(self) -> None:
        canvas = _make_wrapper()
        widget = self._widget()
        canvas.real.Clear()
        widget.draw(canvas)
        assert canvas.real.count_nonzero() > 0

    def test_mid_roll_frame_differs_from_frame_zero(self) -> None:
        canvas = _make_wrapper()
        widget = self._widget()

        canvas.real.Clear()
        widget.draw(canvas)
        frame0_pixels = dict(canvas.real._pixels)

        for _ in range(8):
            widget.advance_frame()
        canvas.real.Clear()
        widget.draw(canvas)
        mid_pixels = dict(canvas.real._pixels)

        assert mid_pixels != frame0_pixels

    def test_all_settled_output_stable_across_draws(self) -> None:
        canvas = _make_wrapper()
        widget = self._widget()
        total_ticks = ticks_per_ball(widget.roll_ms) * len(self.WORDS)

        # Drive frame-by-frame with a draw every tick (the real engine's
        # cadence, constraint #12) well past the last ball's settle point.
        canvas.real.Clear()
        widget.draw(canvas)
        for _ in range(total_ticks + 5):
            widget.advance_frame()
            canvas.real.Clear()
            widget.draw(canvas)

        snap1 = dict(canvas.real._pixels)
        canvas.real.Clear()
        widget.draw(canvas)
        snap2 = dict(canvas.real._pixels)

        assert snap1, "expected all three settled balls to paint something"
        assert snap1 == snap2

    def test_reset_frame_rerolls(self) -> None:
        canvas = _make_wrapper()
        widget = self._widget()

        canvas.real.Clear()
        widget.draw(canvas)
        frame0_pixels = dict(canvas.real._pixels)

        for _ in range(20):
            widget.advance_frame()
        canvas.real.Clear()
        widget.draw(canvas)  # mid-roll draw, proves state advanced

        widget.reset_frame()
        canvas.real.Clear()
        widget.draw(canvas)
        post_reset_pixels = dict(canvas.real._pixels)

        assert post_reset_pixels == frame0_pixels

    def test_border_paints_before_ball_pixels(self) -> None:
        canvas = _make_wrapper()
        border = _RecordingBorder()
        widget = self._widget(border=border)

        canvas.real.Clear()
        widget.draw(canvas)

        assert border.calls == [0], "border must see the canvas before ball pixels"
        assert canvas.real.count_nonzero() > 0

    def test_returns_canvas_and_zero_cursor(self) -> None:
        canvas = _make_wrapper()
        widget = self._widget()
        assert widget.draw(canvas) == (canvas, 0)
        assert widget.draw(canvas, y_offset=3) == (canvas, 0)

    def test_y_offset_all_settled_shows_settled_row_shifted(self) -> None:
        """Once every ball has settled, a y_offset draw still shows that
        settled row — just shifted — via the SAME two-surface blit path
        (dy_logical) rather than a special-cased direct paint. This is the
        old `test_y_offset_direct_paints_settled_shifted` assertion,
        preserved because it's still a true statement about the settled
        state; it's no longer the ONLY thing y_offset can render (see
        `test_y_offset_renders_current_frame_shifted` below for the
        mid-roll case the old code got wrong)."""
        total_ticks = ticks_per_ball(800) * len(self.WORDS)

        canvas_a = _make_wrapper()
        widget_a = self._widget()
        for _ in range(total_ticks + 5):
            widget_a.advance_frame()
        canvas_a.real.Clear()
        widget_a.draw(canvas_a, y_offset=2)
        ys_a = [y for _x, y in canvas_a.real._pixels]

        canvas_b = _make_wrapper()
        widget_b = self._widget()
        for _ in range(total_ticks + 5):
            widget_b.advance_frame()
        canvas_b.real.Clear()
        widget_b.draw(canvas_b, y_offset=5)
        ys_b = [y for _x, y in canvas_b.real._pixels]

        assert ys_a and ys_b
        # Same content (all 3 words fully settled), shifted by exactly
        # (5 - 2) logical rows * scale real px. Compare the TOP edge only:
        # these balls are near full-panel-height (3-word layout), so a
        # downward shift clips the BOTTOM edge against the panel
        # differently for each offset — the top edge is unclipped for both
        # and shifts by exactly the expected real-pixel delta.
        assert min(ys_b) - min(ys_a) == (5 - 2) * _SCALE

    def test_y_offset_renders_current_frame_shifted(self) -> None:
        """MAJOR-finding regression: a y_offset draw must render the SAME
        roll-state content as a y_offset=0 draw at the same frame, just
        translated — not substitute an all-settled composite. Uses an
        8-word layout (small ball diameter) so the vertical shift used
        here doesn't clip against the panel edge, keeping the pixel-set
        comparison clean."""
        words = ["ax", "by", "cz", "do", "eh", "fi", "gu", "hy"]
        dy = 4  # logical rows

        canvas_a = _make_wrapper()
        widget_a = Lottery(words=list(words))
        for _ in range(3):
            widget_a.advance_frame()
        canvas_a.real.Clear()
        widget_a.draw(canvas_a)
        pixels_a = set(canvas_a.real._pixels)

        canvas_b = _make_wrapper()
        widget_b = Lottery(words=list(words))
        for _ in range(3):
            widget_b.advance_frame()
        canvas_b.real.Clear()
        widget_b.draw(canvas_b, y_offset=dy)
        pixels_b = set(canvas_b.real._pixels)

        assert pixels_a and pixels_b
        shifted_a = {(x, y + dy * _SCALE) for x, y in pixels_a}

        # tolerance of 1 real row/col for blit rounding (rotate + half-res
        # round-trip is not pixel-exact) — a lit pixel in one set must have
        # a lit neighbor within Chebyshev distance 1 in the other.
        def _unmatched(pixels, other) -> int:
            count = 0
            for x, y in pixels:
                if any(
                    (x + ddx, y + ddy) in other
                    for ddx in (-1, 0, 1)
                    for ddy in (-1, 0, 1)
                ):
                    continue
                count += 1
            return count

        unmatched_b = _unmatched(pixels_b, shifted_a)
        unmatched_a = _unmatched(shifted_a, pixels_b)
        assert unmatched_b / len(pixels_b) < 0.05
        assert unmatched_a / len(shifted_a) < 0.05

    def test_y_offset_incoming_push_does_not_reveal_finished_row(self) -> None:
        """Direct probe for the review's finding: an incoming push
        transition resets the widget (fresh `reset_frame`, frame 0) and
        then draws it across a range of y_offset values as it slides in.
        The OLD `_draw_settled_direct` path painted every ball fully
        settled regardless of frame — spoiling the reveal by sliding in
        the FINISHED row. The fix must show, at most, the very start of
        the roll (mostly/entirely off-canvas) — nowhere near the fully
        settled pixel count."""
        canvas = _make_wrapper()
        widget = self._widget()
        widget.reset_frame()
        canvas.real.Clear()
        widget.draw(canvas, y_offset=8)
        frame0_lit = canvas.real.count_nonzero()

        total_ticks = ticks_per_ball(800) * len(self.WORDS)
        settled_canvas = _make_wrapper()
        settled_widget = self._widget()
        for _ in range(total_ticks + 5):
            settled_widget.advance_frame()
        settled_canvas.real.Clear()
        settled_widget.draw(settled_canvas)
        settled_lit = settled_canvas.real.count_nonzero()

        assert settled_lit > 0
        assert frame0_lit < 0.2 * settled_lit


# ---------------------------------------------------------------------------
# Rack-fill choreography (roll-order j carries word/slot index n-1-j)
# ---------------------------------------------------------------------------


class TestRackFillChoreography:
    """New choreography: the FIRST ball entering rolls to the RIGHTMOST slot,
    the next stops one slot short, etc. — a rack fills, no ball ever rolls
    through an already-settled one. Reveal order is right-to-left (last
    config word lands first); the FINAL display still reads config order
    left-to-right (word i always ends up at slot i — unchanged)."""

    WORDS = ["cat", "dog", "fox"]  # colors: red, green, amber (PALETTE[0:3])

    def _widget(self, **kwargs) -> Lottery:
        return Lottery(words=list(self.WORDS), **kwargs)

    def test_first_entrant_settles_into_rightmost_slot_only(self) -> None:
        canvas = _make_wrapper()
        widget = self._widget()
        tpb = ticks_per_ball(widget.roll_ms)

        canvas.real.Clear()
        widget.draw(canvas)
        for _ in range(tpb):
            widget.advance_frame()
        canvas.real.Clear()
        widget.draw(canvas)

        # Only the rightmost slot (index 2, "fox") has settled — the first
        # ball to roll targets the rightmost slot, not slot 0.
        assert widget._settled == [False, False, True]

        diameter, slots = layout(3, _PANEL_W, _PANEL_H, _INSET_NO_BORDER)
        r = diameter // 2
        rightmost_cx = slots[2]
        fox_color = PALETTE[2]

        # Rim sample at the settled (rightmost) ball matches fox's color —
        # color travels with its word/slot, unaffected by roll order.
        assert canvas.real.get_pixel(rightmost_cx + r - 1, _CY_P) == fox_color

        # No lit pixels anywhere near the other two slot regions — the
        # newly-launched next ball is still off-canvas, nothing was ever
        # drawn there this tick.
        for slot_cx in (slots[0], slots[1]):
            region = [
                (x, y)
                for (x, y), rgb in canvas.real._pixels.items()
                if rgb != (0, 0, 0) and (x - slot_cx) ** 2 + (y - _CY_P) ** 2 <= r * r
            ]
            assert region == []

    def test_final_settled_order_matches_config_left_to_right(self) -> None:
        canvas = _make_wrapper()
        widget = self._widget()
        total_ticks = ticks_per_ball(widget.roll_ms) * len(self.WORDS)

        canvas.real.Clear()
        widget.draw(canvas)
        for _ in range(total_ticks + 5):
            widget.advance_frame()
        canvas.real.Clear()
        widget.draw(canvas)

        assert widget._settled == [True, True, True]

        diameter, slots = layout(3, _PANEL_W, _PANEL_H, _INSET_NO_BORDER)
        r = diameter // 2
        # Each slot's rim color pairs with its config-order word/color —
        # slot i == colors[i] == PALETTE[i], read left-to-right.
        for i, slot_cx in enumerate(slots):
            assert canvas.real.get_pixel(slot_cx + r - 1, _CY_P) == PALETTE[i]

    def test_no_ball_ever_crosses_a_settled_one(self) -> None:
        """The regression this task fixes: under the OLD (left-to-right
        entry) choreography, a later ball rolling toward a slot further
        right than an already-settled one would sweep straight through the
        settled ball's painted face, temporarily overwriting its pixels.
        Rack-fill makes every later-rolling ball's entire path (and its
        target slot) strictly LEFT of every already-settled ball, so a
        settled ball's face region must be byte-identical on every frame
        after it settles, no matter what any other ball is doing."""
        canvas = _make_wrapper()
        widget = self._widget()
        diameter, slots = layout(3, _PANEL_W, _PANEL_H, _INSET_NO_BORDER)
        r = diameter // 2
        tpb = ticks_per_ball(widget.roll_ms)
        total = tpb * 3

        def region_snapshot(pixels: dict, cx: int) -> dict:
            return {
                (x, y): rgb
                for (x, y), rgb in pixels.items()
                if (x - cx) ** 2 + (y - _CY_P) ** 2 <= r * r
            }

        settled_snapshots: dict[int, dict] = {}

        canvas.real.Clear()
        widget.draw(canvas)
        for frame in range(1, total + 5):
            widget.advance_frame()
            canvas.real.Clear()
            widget.draw(canvas)
            pixels = canvas.real._pixels

            for i in range(3):
                if not widget._settled[i]:
                    continue
                snap = region_snapshot(pixels, slots[i])
                if i in settled_snapshots:
                    assert snap == settled_snapshots[i], (
                        f"slot {i} ('{self.WORDS[i]}') changed at frame "
                        f"{frame} while another ball was still rolling — "
                        "a ball crossed a settled one"
                    )
                settled_snapshots[i] = snap

        # Sanity: all three actually settled and were checked at least once.
        assert set(settled_snapshots) == {0, 1, 2}


class TestChoreographyKnob:
    """`choreography` selects the entry order: "rack_fill" (default, v0.5.0
    behavior — first entrant lands rightmost, no crossings) or "roll_through"
    (the original look — balls fill left-to-right in word order, later balls
    visibly rolling in front of settled ones)."""

    WORDS = ["cat", "dog", "fox"]

    def test_default_is_rack_fill(self) -> None:
        assert Lottery(words=list(self.WORDS)).choreography == "rack_fill"

    def test_roll_through_first_entrant_settles_leftmost(self) -> None:
        canvas = _make_wrapper()
        widget = Lottery(words=list(self.WORDS), choreography="roll_through")
        tpb = ticks_per_ball(widget.roll_ms)

        canvas.real.Clear()
        widget.draw(canvas)
        for _ in range(tpb):
            widget.advance_frame()
        canvas.real.Clear()
        widget.draw(canvas)

        # Slot 0 ("cat", leftmost) settles FIRST under roll_through.
        assert widget._settled == [True, False, False]

    def test_roll_through_later_ball_crosses_a_settled_one(self) -> None:
        """The signature roll-through look: ball 1's path to slot 1 sweeps
        THROUGH settled slot 0's face — its region must change on at least
        one frame while ball 1 rolls (the exact opposite of rack_fill's
        byte-stability invariant)."""
        canvas = _make_wrapper()
        widget = Lottery(words=list(self.WORDS), choreography="roll_through")
        diameter, slots = layout(3, _PANEL_W, _PANEL_H, _INSET_NO_BORDER)
        r = diameter // 2
        tpb = ticks_per_ball(widget.roll_ms)

        def region_snapshot(pixels: dict, cx: int) -> dict:
            return {
                (x, y): rgb
                for (x, y), rgb in pixels.items()
                if (x - cx) ** 2 + (y - _CY_P) ** 2 <= r * r
            }

        canvas.real.Clear()
        widget.draw(canvas)
        # Roll ball 0 (slot 0) to rest.
        for _ in range(tpb):
            widget.advance_frame()
        canvas.real.Clear()
        widget.draw(canvas)
        assert widget._settled[0] is True
        baseline = region_snapshot(canvas.real._pixels, slots[0])

        # During ball 1's window, slot 0's region must change at least once.
        changed = False
        for _ in range(tpb):
            widget.advance_frame()
            canvas.real.Clear()
            widget.draw(canvas)
            if region_snapshot(canvas.real._pixels, slots[0]) != baseline:
                changed = True
                break
        assert changed, "roll_through ball never crossed the settled slot-0 face"

    def test_roll_through_final_display_reads_config_order(self) -> None:
        canvas = _make_wrapper()
        widget = Lottery(words=list(self.WORDS), choreography="roll_through")
        tpb = ticks_per_ball(widget.roll_ms)
        canvas.real.Clear()
        widget.draw(canvas)
        for _ in range(tpb * 3 + 2):
            widget.advance_frame()
        canvas.real.Clear()
        widget.draw(canvas)
        assert widget._settled == [True, True, True]
        # ring colors pair with words: slot i rim sample == PALETTE[i]
        diameter, slots = layout(3, _PANEL_W, _PANEL_H, _INSET_NO_BORDER)
        r = diameter // 2
        for i in range(3):
            assert canvas.real.get_pixel(slots[i], _CY_P - r + 1) == PALETTE[i]

    def test_validate_config_rejects_unknown_choreography(self) -> None:
        errs = Lottery.validate_config({"words": ["a"], "choreography": "spiral"})
        assert any("choreography" in e for e in errs)

    def test_validate_config_accepts_both_modes(self) -> None:
        for mode in ("rack_fill", "roll_through"):
            assert Lottery.validate_config({"words": ["a"], "choreography": mode}) == []


# ---------------------------------------------------------------------------
# Config validation (Task 4)
# ---------------------------------------------------------------------------


def _ctx(tmp_path, *, scale=4, content_height=16, panel_width=256, panel_height=64):
    return ValidationContext(
        scale=scale,
        content_height=content_height,
        panel_width=panel_width,
        panel_height=panel_height,
        config_dir=tmp_path,
    )


class TestValidateConfigHappyPath:
    def test_minimal_config_is_valid(self) -> None:
        assert Lottery.validate_config({"words": ["cat", "dog", "fox"]}) == []

    def test_full_config_is_valid(self) -> None:
        cfg = {
            "words": ["cat", "dog", "fox"],
            "colors": [[255, 0, 0], [0, 255, 0], [0, 0, 255]],
            "ball_style": "solid",
            "roll_ms": 500,
        }
        assert Lottery.validate_config(cfg) == []


class TestValidateConfigWords:
    def test_missing_words_is_an_error(self) -> None:
        errors = Lottery.validate_config({})
        assert any("words" in e and "non-empty" in e for e in errors)

    def test_empty_words_list_is_an_error(self) -> None:
        errors = Lottery.validate_config({"words": []})
        assert any("words" in e and "non-empty" in e for e in errors)

    def test_words_not_a_list_is_an_error(self) -> None:
        errors = Lottery.validate_config({"words": "cat"})
        assert any("words" in e and "non-empty" in e for e in errors)

    def test_more_than_eight_words_is_an_error(self) -> None:
        errors = Lottery.validate_config({"words": [f"w{i}" for i in range(9)]})
        assert any("at most 8" in e and "9" in e for e in errors)

    def test_exactly_eight_words_is_valid(self) -> None:
        errors = Lottery.validate_config({"words": [f"w{i}" for i in range(8)]})
        assert errors == []

    def test_non_string_word_is_an_error(self) -> None:
        errors = Lottery.validate_config({"words": ["cat", 5, "fox"]})
        assert any("non-empty strings" in e for e in errors)

    def test_empty_string_word_is_an_error(self) -> None:
        errors = Lottery.validate_config({"words": ["cat", "", "fox"]})
        assert any("non-empty strings" in e for e in errors)


class TestValidateConfigColors:
    def test_colors_not_a_list_is_an_error(self) -> None:
        errors = Lottery.validate_config({"words": ["cat", "dog"], "colors": "red"})
        assert any("colors" in e and "must be a list" in e for e in errors)

    def test_colors_length_mismatch_names_both_lengths(self) -> None:
        errors = Lottery.validate_config(
            {"words": ["cat", "dog", "fox"], "colors": [[255, 0, 0], [0, 255, 0]]}
        )
        assert any("2" in e and "3" in e and "colors" in e for e in errors)

    def test_colors_entry_wrong_arity_is_an_error(self) -> None:
        errors = Lottery.validate_config(
            {"words": ["cat", "dog"], "colors": [[255, 0], [0, 255, 0]]}
        )
        assert any("[r, g, b]" in e for e in errors)

    def test_colors_entry_out_of_range_is_an_error(self) -> None:
        errors = Lottery.validate_config(
            {"words": ["cat", "dog"], "colors": [[300, 0, 0], [0, 255, 0]]}
        )
        assert any("[r, g, b]" in e for e in errors)

    def test_colors_entry_non_int_is_an_error(self) -> None:
        errors = Lottery.validate_config(
            {"words": ["cat", "dog"], "colors": [[1.5, 0, 0], [0, 255, 0]]}
        )
        assert any("[r, g, b]" in e for e in errors)

    def test_colors_matching_length_is_valid(self) -> None:
        errors = Lottery.validate_config(
            {"words": ["cat", "dog"], "colors": [[255, 0, 0], [0, 255, 0]]}
        )
        assert errors == []

    def test_colors_none_is_valid(self) -> None:
        assert Lottery.validate_config({"words": ["cat", "dog"], "colors": None}) == []


class TestValidateConfigBallStyle:
    def test_invalid_ball_style_is_an_error(self) -> None:
        errors = Lottery.validate_config({"words": ["cat"], "ball_style": "sparkly"})
        assert any("ball_style" in e and "sparkly" in e for e in errors)

    def test_classic_and_solid_are_valid(self) -> None:
        for style in ("classic", "solid"):
            assert (
                Lottery.validate_config({"words": ["cat"], "ball_style": style}) == []
            )


class TestValidateConfigRollMs:
    def test_roll_ms_below_floor_is_an_error(self) -> None:
        errors = Lottery.validate_config({"words": ["cat"], "roll_ms": 99})
        assert any("roll_ms" in e and ">= 100" in e for e in errors)

    def test_roll_ms_non_int_is_an_error(self) -> None:
        errors = Lottery.validate_config({"words": ["cat"], "roll_ms": "fast"})
        assert any("roll_ms" in e for e in errors)

    def test_roll_ms_bool_is_an_error(self) -> None:
        errors = Lottery.validate_config({"words": ["cat"], "roll_ms": True})
        assert any("roll_ms" in e for e in errors)

    def test_roll_ms_at_floor_is_valid(self) -> None:
        errors = Lottery.validate_config({"words": ["cat"], "roll_ms": 100})
        assert errors == []


class TestValidateConfigWarnings:
    def test_scale_one_warns_bigsign_required(self, tmp_path) -> None:
        ctx = _ctx(tmp_path, scale=1)
        warnings = Lottery.validate_config_warnings({"words": ["cat"]}, ctx)
        assert len(warnings) == 1
        assert "flair.lottery" in warnings[0]
        assert "scaled display" in warnings[0]

    def test_unfittable_word_names_the_word_and_diameter(self, tmp_path) -> None:
        ctx = _ctx(tmp_path, scale=4, panel_width=256, panel_height=64)
        long_word = "abcdefghijklmnopqrst"  # pinned 0-fit case from TestAutoFontSize
        cfg = {"words": [long_word], "font": "Inter-Bold"}
        warnings = Lottery.validate_config_warnings(cfg, ctx)
        assert len(warnings) == 1
        assert long_word in warnings[0]
        diameter, _slots = layout(1, 256, 64, _INSET_NO_BORDER)
        assert str(diameter) in warnings[0]

    def test_fittable_config_has_no_warnings(self, tmp_path) -> None:
        ctx = _ctx(tmp_path, scale=4, panel_width=256, panel_height=64)
        cfg = {"words": ["cat", "dog", "fox"], "font": "Inter-Bold"}
        assert Lottery.validate_config_warnings(cfg, ctx) == []

    def test_missing_words_returns_no_warnings(self, tmp_path) -> None:
        # required-field error is validate_config's job; this hook is a no-op.
        ctx = _ctx(tmp_path, scale=4)
        assert Lottery.validate_config_warnings({}, ctx) == []

    def test_border_widens_inset_used_for_the_fit_check(self, tmp_path) -> None:
        # A single word at a small panel: with the wider border inset the
        # diameter shrinks, which can flip a borderline word from fitting to
        # not fitting — assert the reported diameter reflects the border
        # inset, not the no-border one.
        ctx = _ctx(tmp_path, scale=4, panel_width=256, panel_height=64)
        cfg = {"words": ["cat", "dog", "fox"], "font": "Inter-Bold", "border": {}}
        warnings = Lottery.validate_config_warnings(cfg, ctx)
        no_border_diameter, _ = layout(3, 256, 64, _INSET_NO_BORDER)
        with_border_diameter, _ = layout(3, 256, 64, _INSET_WITH_BORDER)
        assert no_border_diameter != with_border_diameter
        for w in warnings:
            assert str(no_border_diameter) not in w


# ---------------------------------------------------------------------------
# Registration (Task 4 fold-in)
# ---------------------------------------------------------------------------


class _RecordingAPI:
    """Minimal PluginAPI stand-in recording widget registrations."""

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
    def test_lottery_registered_by_name(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "lottery" in api.widgets

    def test_lottery_class_is_Lottery(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert api.widgets["lottery"] is Lottery


class TestFaceLegibility:
    """Ball-face text legibility (hardware, halal-cart sign 2026-07-16):
    small Inter at the default threshold 128 dropped thin strokes — GYRO
    read as BYRD. The lottery now resolves at the thin-stroke threshold."""

    def test_fit_and_paint_resolve_at_thin_stroke_threshold(self, monkeypatch):
        import led_ticker_flair.flair.lottery as lot

        seen = []
        real_resolve = lot.resolve_font

        def spy(name, size=None, threshold=None):
            seen.append(threshold)
            return real_resolve(name, size, threshold)

        monkeypatch.setattr(lot, "resolve_font", spy)
        size = lot.auto_font_size("HALAL", 56, "Inter-Bold", 4)
        assert size > 0
        assert set(seen) == {lot._FACE_THRESHOLD}, (
            "fit measurement must resolve at the thin-stroke threshold"
        )

    def test_config_set_font_raises_helpfully_on_non_string(self):
        """RESOLVES_OWN_FONT keeps `font` a raw NAME string — core no
        longer coerces it to a Font object. A non-string here would mean
        that contract broke (or a caller bypassed it); reject it with a
        clear message instead of crashing deep in the paint path."""
        import pytest

        from led_ticker_flair.flair.lottery import Lottery

        class _FakeCoercedFont:  # what core used to hand over, pre-RESOLVES_OWN_FONT
            pass

        with pytest.raises(ValueError, match="must be a font name string"):
            Lottery(words=["A"], font=_FakeCoercedFont())


class TestConfigSelectedFont:
    """RESOLVES_OWN_FONT (core >=4.27): a config-set `font` stays a raw
    NAME string instead of being coerced to a Font object, so the lottery
    can pick a font (e.g. a pixel font) and auto-size it at render time."""

    def test_resolves_own_font_marker_is_set(self):
        from led_ticker_flair.flair.lottery import Lottery

        assert Lottery.RESOLVES_OWN_FONT is True

    def test_default_font_omitted_still_works(self):
        from led_ticker_flair.flair.lottery import Lottery

        lot = Lottery(words=["HALAL"])
        assert lot.font == "Inter-Bold"

    def test_config_set_pixel_font_is_accepted_and_used(self):
        """Previously any config-set `font` (even a valid name) was
        rejected outright by `_font_is_a_name`. Now a valid name — a
        pixel font in particular, the point of the grid-snap — builds
        cleanly and is used as-is (not silently ignored)."""
        from led_ticker_flair.flair.lottery import Lottery

        lot = Lottery(words=["HALAL"], font="spleen-6x12")
        assert lot.font == "spleen-6x12"

    def test_unknown_font_name_still_raises_clearly(self):
        import pytest

        from led_ticker_flair.flair.lottery import Lottery

        with pytest.raises(ValueError, match="no-such-font"):
            Lottery(words=["A"], font="no-such-font")


class TestConfigSelectedFontEndToEnd:
    """`test_config_set_pixel_font_is_accepted_and_used` above calls
    `Lottery(...)` directly — it never proves core's real config-load path
    (validate_widget_cfg -> _resolve_fonts) actually leaves `font` alone for
    this widget. Before the RESOLVES_OWN_FONT rework, a hires name like
    `spleen-6x12` with no `font_size` would raise ("requires font_size,
    e.g. font_size = 24...") right here in _resolve_fonts, before Lottery's
    own validate_config/constructor ever saw it — the exact bug this class
    guards against regressing."""

    async def test_config_pixel_font_survives_the_real_factory_path(self):
        from led_ticker import _plugin_loader as L

        L.reset_plugins()
        try:
            L.load_plugins(None, entry_points_enabled=True)

            from led_ticker.app.factories import validate_widget_cfg

            cfg = {
                "type": "flair.lottery",
                "words": ["HALAL"],
                "font": "spleen-6x12",
            }
            # No font_size — a normal (non-RESOLVES_OWN_FONT) widget with a
            # hires font name here would raise in _resolve_fonts.
            await validate_widget_cfg(cfg, None)

            # The load-bearing assertion: RESOLVES_OWN_FONT left `font` as
            # the raw NAME string. A widget without the opt-out would have
            # it replaced by a resolved Font/HiresFont object by now.
            assert cfg["font"] == "spleen-6x12"
        finally:
            L.reset_plugins()

    async def test_hires_font_without_font_size_still_raises_for_a_normal_widget(
        self,
    ):
        """Sanity check that the failure mode this test guards against is
        real: a widget WITHOUT RESOLVES_OWN_FONT still hits the
        font_size-required error for the same hires name, on the same
        real path."""
        from led_ticker import _plugin_loader as L

        L.reset_plugins()
        try:
            L.load_plugins(None, entry_points_enabled=True)

            from led_ticker.app.factories import validate_widget_cfg

            cfg = {
                "type": "message",
                "text": "hi",
                "font": "spleen-6x12",
            }
            with pytest.raises(ValueError, match="requires font_size"):
                await validate_widget_cfg(cfg, None)
        finally:
            L.reset_plugins()


class TestAutoFontSizePixelGrid:
    def test_pixel_font_returns_only_native_multiples(self):
        from led_ticker_flair.flair.lottery import auto_font_size

        # Across a range of ball diameters, a pixel font must resolve to a
        # native multiple (or 0 = doesn't fit) — never an off-grid size.
        for diam in (40, 48, 56, 64, 80):
            for word in ("HALAL", "GYRO", "RICE"):
                size = auto_font_size(word, diam, "spleen-6x12", 4)
                assert size == 0 or size % 12 == 0, (diam, word, size)

    def test_pixel_font_snaps_down_not_up(self):
        # A diameter whose continuous fit lands between 12 and 24 must snap
        # DOWN to 12 (fits), never up to 24 (would overflow).
        from led_ticker_flair.flair.lottery import auto_font_size

        size = auto_font_size("RICE", 48, "spleen-6x12", 4)
        assert size in (0, 12, 24, 36)  # on-grid only
        # 48px ball: continuous fit ~15 -> snaps to 12
        assert size == 12

    def test_tiny_ball_returns_zero_when_native_overflows(self):
        from led_ticker_flair.flair.lottery import auto_font_size

        # A ball too small for even native 12px pixel text -> 0 (doesn't fit).
        assert auto_font_size("HALAL", 16, "spleen-6x12", 4) == 0

    def test_outline_font_unchanged(self):
        # Inter keeps the continuous search (may return any int).
        from led_ticker_flair.flair.lottery import auto_font_size

        size = auto_font_size("RICE", 48, "Inter-Bold", 4)
        assert size > 0  # unchanged continuous behavior
