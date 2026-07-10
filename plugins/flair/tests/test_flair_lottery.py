"""flair.lottery — pure geometry + roll-timeline math (Task 1, no widget)."""

import math

import pytest
from led_ticker.plugin import ENGINE_TICK_MS

from led_ticker_flair.flair.lottery import (
    PALETTE,
    auto_font_size,
    ball_phase,
    layout,
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

    def test_kebab_exact_size_pin(self) -> None:
        """Regression tripwire: pins the actual largest fitting size so a
        chord-factor / range-bound regression doesn't silently drift."""
        assert auto_font_size("kebab", 56, "Inter-Bold", 4) == 13

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
