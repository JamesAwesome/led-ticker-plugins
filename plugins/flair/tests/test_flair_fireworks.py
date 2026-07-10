"""flair.fireworks — pure burst plan + geometry (Task 1, no widget/transition
class yet). Later tasks extend this file with the transition-class TDD."""

import math
import random

import pytest

from led_ticker_flair.flair.fireworks import (
    PALETTE,
    Burst,
    burst_count,
    burst_state,
    plan_bursts,
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


class TestBurstCount:
    def test_smallsign_pinned_five(self) -> None:
        assert burst_count(160, 16) == 5

    def test_bigsign_pinned_four(self) -> None:
        assert burst_count(256, 64) == 4

    def test_longboi_pinned_six(self) -> None:
        assert burst_count(512, 64) == 6

    def test_clamped_to_minimum_three(self) -> None:
        # w / max(h, 32) rounds to 0/1 for a very tall/narrow panel.
        assert burst_count(16, 256) == 3

    def test_clamped_to_maximum_six(self) -> None:
        # A very wide panel would otherwise round well past 6.
        assert burst_count(2000, 16) == 6


class TestPlanBurstsDeterminism:
    def test_same_seed_yields_identical_plan(self) -> None:
        plan_a = plan_bursts(256, 64, random.Random(7))
        plan_b = plan_bursts(256, 64, random.Random(7))
        assert plan_a == plan_b

    def test_different_seed_yields_different_plan(self) -> None:
        plan_a = plan_bursts(256, 64, random.Random(7))
        plan_b = plan_bursts(256, 64, random.Random(8))
        assert plan_a != plan_b

    def test_default_count_matches_burst_count(self) -> None:
        plan = plan_bursts(256, 64, random.Random(1))
        assert len(plan) == burst_count(256, 64) == 4

    def test_explicit_count_overrides_default(self) -> None:
        plan = plan_bursts(256, 64, random.Random(1), count=6)
        assert len(plan) == 6


class TestPlanBurstsBounds:
    @pytest.mark.parametrize(("w", "h"), [(160, 16), (256, 64), (512, 64)])
    def test_centers_in_bounds(self, w: int, h: int) -> None:
        plan = plan_bursts(w, h, random.Random(42))
        for b in plan:
            assert 0.0 <= b.cx <= w
            assert 0.0 <= b.cy <= h * (2.0 / 3.0) + 1e-9

    @pytest.mark.parametrize(("w", "h"), [(160, 16), (256, 64), (512, 64)])
    def test_radius_max_in_band(self, w: int, h: int) -> None:
        plan = plan_bursts(w, h, random.Random(42))
        for b in plan:
            assert 0.55 * h <= b.radius_max <= 0.85 * h

    @pytest.mark.parametrize(("w", "h"), [(160, 16), (256, 64), (512, 64)])
    def test_stagger_in_bounds(self, w: int, h: int) -> None:
        plan = plan_bursts(w, h, random.Random(42))
        for b in plan:
            assert 0.05 <= b.t_start <= 0.45

    def test_spark_angle_count_in_bounds(self) -> None:
        plan = plan_bursts(256, 64, random.Random(42))
        for b in plan:
            assert 16 <= len(b.spark_angles) <= 32

    def test_centers_spread_across_horizontal_bands(self) -> None:
        # With 4 bursts across w=256, each burst should land in its own
        # quarter-width band, not all cluster together.
        plan = plan_bursts(256, 64, random.Random(3), count=4)
        band_w = 256 / 4
        for i, b in enumerate(plan):
            assert i * band_w <= b.cx <= (i + 1) * band_w


class TestPlanBurstsColors:
    def test_colors_cycle_when_provided(self) -> None:
        colors = [(1, 2, 3), (4, 5, 6)]
        plan = plan_bursts(256, 64, random.Random(9), count=5, colors=colors)
        expected = [colors[i % len(colors)] for i in range(5)]
        assert [b.color for b in plan] == expected

    def test_defaults_to_palette_cycle(self) -> None:
        plan = plan_bursts(256, 64, random.Random(9), count=len(PALETTE) + 2)
        expected = [PALETTE[i % len(PALETTE)] for i in range(len(PALETTE) + 2)]
        assert [b.color for b in plan] == expected


class TestBurstState:
    def _burst(
        self,
        *,
        cx: float = 10.0,
        cy: float = 5.0,
        radius_max: float = 20.0,
        t_start: float = 0.2,
        t_burst_dur: float = 0.3,
        color: tuple[int, int, int] = (255, 0, 0),
        spark_angles: tuple[tuple[float, float], ...] = (),
    ) -> Burst:
        return Burst(
            cx=cx,
            cy=cy,
            radius_max=radius_max,
            t_start=t_start,
            t_burst_dur=t_burst_dur,
            color=color,
            spark_angles=spark_angles,
        )

    def test_waiting_before_t_start(self) -> None:
        b = self._burst(t_start=0.2)
        radius, phase = burst_state(b, 0.1, 100, 100)
        assert phase == "waiting"
        assert radius == 0.0

    def test_launch_phase_zero_radius(self) -> None:
        b = self._burst(t_start=0.2, t_burst_dur=0.3)
        # p = (0.25 - 0.2) / 0.3 = 0.1667 < 0.3 -> launch
        radius, phase = burst_state(b, 0.25, 100, 100)
        assert phase == "launch"
        assert radius == 0.0

    def test_open_phase_eases_toward_radius_max(self) -> None:
        b = self._burst(t_start=0.2, t_burst_dur=0.3, radius_max=20.0)
        # p = (0.49999 - 0.2) / 0.3 -> just under 1.0, near end of open.
        radius, phase = burst_state(b, 0.49, 100, 100)
        assert phase == "open"
        assert 0.0 < radius <= 20.0

    def test_open_phase_reaches_radius_max_at_bloom_boundary(self) -> None:
        # t_burst_dur constructed as (0.5 - t_start) means open completes
        # exactly at the bloom handoff.
        b = self._burst(t_start=0.2, t_burst_dur=0.3, radius_max=20.0)
        radius, phase = burst_state(b, 0.499999, 100, 100)
        assert phase == "open"
        assert radius == pytest.approx(20.0, abs=1e-2)

    def test_bloom_phase_after_global_half(self) -> None:
        b = self._burst(t_start=0.2, t_burst_dur=0.3, radius_max=20.0)
        radius, phase = burst_state(b, 0.5, 100, 100)
        assert phase == "bloom"
        assert radius == pytest.approx(20.0)

    def test_bloom_radius_covers_panel_near_t_one(self) -> None:
        w, h = 256, 64
        b = self._burst(t_start=0.2, t_burst_dur=0.3, radius_max=20.0)
        radius, phase = burst_state(b, 0.98, w, h)
        assert phase == "bloom"
        assert radius >= 0.9 * math.hypot(w, h)

    def test_bloom_radius_exactly_hypot_at_t_one(self) -> None:
        w, h = 256, 64
        b = self._burst(t_start=0.2, t_burst_dur=0.3, radius_max=20.0)
        radius, phase = burst_state(b, 1.0, w, h)
        assert phase == "bloom"
        assert radius == pytest.approx(math.hypot(w, h))

    def test_bloom_overrides_waiting_burst(self) -> None:
        # A late-staggered burst (t_start near 0.45) is still "waiting" in
        # its own local timeline once t >= 0.5, but bloom is global and
        # overrides it for every burst at once.
        b = self._burst(t_start=0.45, t_burst_dur=0.05, radius_max=20.0)
        radius, phase = burst_state(b, 0.5, 100, 100)
        assert phase == "bloom"
        assert radius == pytest.approx(20.0)

    def test_radius_monotonically_increases_through_phases(self) -> None:
        b = self._burst(t_start=0.1, t_burst_dur=0.4, radius_max=20.0)
        ts = [0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0]
        radii = [burst_state(b, t, 100, 100)[0] for t in ts]
        for a, c in zip(radii, radii[1:], strict=False):
            assert c >= a - 1e-9
