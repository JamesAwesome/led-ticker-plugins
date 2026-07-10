"""flair.fireworks — pure burst plan + geometry (Task 1) and the
``Fireworks`` transition class (Task 2)."""

import math
import random
from typing import Any
from unittest import mock

import pytest
from led_ticker.plugin import ScaledCanvas

from led_ticker_flair import flair as flair_pkg
from led_ticker_flair.flair.fireworks import (
    _LAUNCH_OPEN_BOUNDARY,
    PALETTE,
    Burst,
    Fireworks,
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


# ---------------------------------------------------------------------------
# Fireworks transition (Task 2)
# ---------------------------------------------------------------------------
#
# Stub canvas / widget fixture shapes copied from test_flair_spinout.py (the
# per-file duplication is this repo's convention -- see that module's own
# comment). Extended here with an ordered SetPixel call log (`.calls`) for
# the determinism test, and a `Fill` method (spinout's fixture never needed
# one; `snap_reset` calls `canvas.Fill(*bg)` when an `incoming_bg_color` is
# given).


class _StubCanvas:
    """Minimal scale=1 real-canvas stub."""

    def __init__(self, width: int = 160, height: int = 16) -> None:
        self.width = width
        self.height = height
        self._pixels: dict[tuple[int, int], tuple[int, int, int]] = {}
        # Ordered log of every SetPixel call (x, y, r, g, b) -- the
        # determinism test compares this between two independent instances.
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


def _make_fill_widget(color: tuple[int, int, int]) -> Any:
    """Widget stub whose draw() paints its ENTIRE canvas `color` -- used by
    the pixel-semantics tests so "shows outgoing/incoming's pixel" and
    "still black" are unambiguous at any coordinate not touched by the
    transition's own effect painting.
    """
    widget = mock.Mock()
    widget.hold_time = 0.0

    def _draw(canvas: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
        canvas.Fill(*color)
        return (canvas, cursor_pos)

    widget.draw.side_effect = _draw
    return widget


class TestFireworksCtorValidation:
    def test_bursts_below_minimum_rejected(self) -> None:
        with pytest.raises(ValueError, match="bursts"):
            Fireworks(bursts=1)

    def test_bursts_above_maximum_rejected(self) -> None:
        with pytest.raises(ValueError, match="bursts"):
            Fireworks(bursts=9)

    def test_bool_bursts_rejected(self) -> None:
        with pytest.raises(ValueError, match="bursts"):
            Fireworks(bursts=True)  # type: ignore[arg-type]

    def test_colors_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="colors"):
            Fireworks(colors=[[300, 0, 0]])

    def test_colors_wrong_shape_rejected(self) -> None:
        with pytest.raises(ValueError, match="colors"):
            Fireworks(colors=[[1, 2]])

    def test_valid_bounds_construct(self) -> None:
        Fireworks(bursts=2)
        Fireworks(bursts=8)

    def test_defaults_construct(self) -> None:
        fw = Fireworks()
        assert fw.bursts is None
        assert fw.colors is None
        assert fw.seed is None

    def test_valid_colors_construct(self) -> None:
        fw = Fireworks(colors=[[1, 2, 3], [4, 5, 6]])
        assert fw.colors == [(1, 2, 3), (4, 5, 6)]


class TestT0PureOutgoing:
    def test_t0_draws_only_outgoing(self) -> None:
        fw = Fireworks(seed=3)
        canvas = _StubCanvas()
        outgoing = _make_widget(draw_pixel=True)
        incoming = _make_widget(draw_pixel=False)

        result = fw.frame_at(0.0, canvas, outgoing, incoming)

        outgoing.draw.assert_called_once()
        incoming.draw.assert_not_called()
        assert result is canvas

    def test_negative_t_also_draws_only_outgoing(self) -> None:
        fw = Fireworks(seed=3)
        canvas = _StubCanvas()
        outgoing = _make_widget()
        incoming = _make_widget()

        fw.frame_at(-0.1, canvas, outgoing, incoming)
        incoming.draw.assert_not_called()

    def test_outgoing_scroll_pos_forwarded(self) -> None:
        fw = Fireworks(seed=3)
        canvas = _StubCanvas()
        incoming = _make_widget(draw_pixel=False)
        received: list[int] = []

        outgoing = mock.Mock()

        def _spy(c: Any, cursor_pos: int = 0, **kw: Any) -> tuple[Any, int]:
            received.append(cursor_pos)
            return (c, cursor_pos)

        outgoing.draw.side_effect = _spy

        fw.frame_at(0.0, canvas, outgoing, incoming, outgoing_scroll_pos=-7)
        assert received == [-7]


class TestSnap:
    def test_threshold_snaps_and_draws_incoming(self) -> None:
        fw = Fireworks(seed=3)
        canvas = _StubCanvas()
        outgoing = _make_widget()
        incoming = _make_widget(draw_pixel=True)

        result = fw.frame_at(
            0.95, canvas, outgoing, incoming, incoming_bg_color=(9, 9, 9)
        )

        outgoing.draw.assert_not_called()
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)
        # incoming drew its own pixel at (0, 0) AFTER the bg fill -> wins there.
        assert canvas._pixels[(0, 0)] == (255, 0, 0)
        # Elsewhere the snap_reset bg fill is observable.
        assert canvas._pixels[(5, 5)] == (9, 9, 9)
        assert result is canvas

    def test_no_bg_color_clears_instead_of_fills(self) -> None:
        fw = Fireworks(seed=3)
        canvas = _StubCanvas()
        canvas._pixels[(5, 5)] = (1, 2, 3)  # pre-existing content
        outgoing = _make_widget()
        incoming = _make_widget(draw_pixel=False)

        fw.frame_at(0.95, canvas, outgoing, incoming)

        # snap_reset with no bg color Clears() -- prior content is gone.
        assert (5, 5) not in canvas._pixels

    def test_t_above_1_also_snaps(self) -> None:
        fw = Fireworks(seed=3)
        canvas = _StubCanvas()
        outgoing = _make_widget()
        incoming = _make_widget(draw_pixel=True)

        result = fw.frame_at(1.5, canvas, outgoing, incoming)
        incoming.draw.assert_called_once_with(canvas, cursor_pos=0)
        assert result is canvas


class TestPhaseOnePixelSemantics:
    def test_burst_center_black_once_open_far_corner_shows_outgoing(self) -> None:
        fw = Fireworks(seed=1)
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_fill_widget((10, 20, 30))
        incoming = _make_widget(draw_pixel=False)

        # Force a known, deterministic plan (bypass the seeded rng) so the
        # burst geometry is exact rather than depending on plan_bursts'
        # random placement.
        burst = Burst(
            cx=140.0,
            cy=8.0,
            radius_max=10.0,
            t_start=0.0,
            t_burst_dur=0.5,
            color=(200, 50, 50),
            spark_angles=(),
        )
        fw._plan = [burst]
        fw._plan_dims = (160, 16)
        fw._last_t = 0.0  # prevent the refire guard from clobbering the plan

        # p = (0.4 - 0.0) / 0.5 = 0.8 -> well into "open".
        fw.frame_at(0.4, canvas, outgoing, incoming)

        assert canvas._pixels[(140, 8)] == (0, 0, 0)
        # Far corner is nowhere near the burst's bounding box.
        assert canvas._pixels[(0, 0)] == (10, 20, 30)
        assert canvas._pixels[(159, 15)] == (10, 20, 30)


class TestPhaseTwoPixelSemantics:
    def test_far_pixel_black_burst_center_shows_incoming(self) -> None:
        fw = Fireworks(seed=1)
        canvas = _StubCanvas(width=256, height=64)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_fill_widget((0, 255, 0))

        burst = Burst(
            cx=30.0,
            cy=30.0,
            radius_max=20.0,
            t_start=0.2,
            t_burst_dur=0.3,
            color=(200, 50, 50),
            spark_angles=(),
        )
        fw._plan = [burst]
        fw._plan_dims = (256, 64)
        fw._last_t = 0.5

        # Just past the bloom boundary -- radius has barely grown past
        # radius_max (20), nowhere near covering the panel.
        fw.frame_at(0.51, canvas, outgoing, incoming)

        assert canvas._pixels[(30, 30)] == (0, 255, 0)  # burst center: revealed
        assert canvas._pixels[(250, 60)] == (0, 0, 0)  # far corner: blacked out


class TestRadiusMonotonicity:
    def test_planned_burst_radius_grows_across_full_sweep(self) -> None:
        fw = Fireworks(seed=1)
        canvas = _StubCanvas(width=160, height=16)
        outgoing = _make_widget(draw_pixel=True)
        incoming = _make_widget(draw_pixel=False)

        # Warm up: force a plan build via one early frame.
        fw.frame_at(0.01, canvas, outgoing, incoming)
        assert fw._plan
        b = fw._plan[0]

        ts = [i / 100 for i in range(1, 100)]
        radii = [burst_state(b, t, 160, 16)[0] for t in ts]
        for a, c in zip(radii, radii[1:], strict=False):
            assert c >= a - 1e-9
        assert radii[-1] > radii[0]


class TestRefire:
    def test_refire_rebuilds_plan(self) -> None:
        fw = Fireworks()  # seed=None -> entropy reseed on every re-fire
        canvas = _StubCanvas()
        outgoing = _make_widget()
        incoming = _make_widget()

        for t in (0.0, 0.3, 0.6, 1.0):
            fw.frame_at(t, canvas, outgoing, incoming)
        first_plan = fw._plan
        assert first_plan is not None

        for t in (0.0, 0.1):
            fw.frame_at(t, canvas, outgoing, incoming)
        second_plan = fw._plan
        assert second_plan is not None
        assert second_plan is not first_plan

    def test_refire_with_explicit_seed_still_rebuilds_a_plan(self) -> None:
        """Even with an explicit seed (no reseed on re-fire), a new firing
        still gets a freshly-BUILT plan object (the stale one is dropped) --
        only the underlying rng continuation is exempted from reseeding."""
        fw = Fireworks(seed=7)
        canvas = _StubCanvas()
        outgoing = _make_widget()
        incoming = _make_widget()

        for t in (0.0, 0.3, 0.6, 1.0):
            fw.frame_at(t, canvas, outgoing, incoming)
        first_plan = fw._plan

        for t in (0.0, 0.1):
            fw.frame_at(t, canvas, outgoing, incoming)
        second_plan = fw._plan
        assert second_plan is not first_plan


class TestDeterminism:
    def test_same_seed_two_full_sweeps_identical_pixel_logs(self) -> None:
        ts = [i / 20 for i in range(21)]  # 0.0, 0.05, ..., 1.0

        def _sweep() -> list[tuple[int, int, int, int, int]]:
            fw = Fireworks(seed=7)
            canvas = _StubCanvas(width=160, height=16)
            outgoing = _make_widget(draw_pixel=True)
            incoming = _make_widget(draw_pixel=True)
            for t in ts:
                fw.frame_at(t, canvas, outgoing, incoming)
            return canvas.calls

        log_a = _sweep()
        log_b = _sweep()
        assert log_a == log_b
        assert log_a  # sanity: the sweep actually painted something

    def test_different_seed_diverges(self) -> None:
        ts = [i / 20 for i in range(21)]

        def _sweep(seed: int) -> list[tuple[int, int, int, int, int]]:
            fw = Fireworks(seed=seed)
            canvas = _StubCanvas(width=160, height=16)
            outgoing = _make_widget(draw_pixel=True)
            incoming = _make_widget(draw_pixel=True)
            for t in ts:
                fw.frame_at(t, canvas, outgoing, incoming)
            return canvas.calls

        assert _sweep(7) != _sweep(8)


class TestScaledCanvasEffectPixels:
    def test_effect_pixels_land_on_real(self) -> None:
        real = _StubCanvas(width=256, height=64)
        wrapped = ScaledCanvas(real, scale=4, content_height=16)

        fw = Fireworks(seed=1)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_widget(draw_pixel=False)

        burst = Burst(
            cx=50.0,
            cy=20.0,
            radius_max=3.0,
            t_start=0.0,
            t_burst_dur=0.5,
            color=(200, 50, 50),
            spark_angles=(),
        )
        fw._plan = [burst]
        fw._plan_dims = (256, 64)
        fw._last_t = 0.0

        # p = (0.45 - 0.0) / 0.5 = 0.9 -> "open"; radius close to
        # radius_max (3.0), definitely open (past the 0.3 launch boundary).
        fw.frame_at(0.45, wrapped, outgoing, incoming)

        # The burst center lands on `real` at its OWN real-pixel
        # coordinates -- not scaled by 4x, not block-expanded.
        assert real._pixels[(50, 20)] == (0, 0, 0)
        # A neighbor 8 real px away (well outside radius_max=3, but well
        # INSIDE where a 4x logical block-expansion would have painted had
        # the code mistakenly used `wrapped.SetPixel` instead of
        # `real.SetPixel`) must be untouched.
        assert (58, 20) not in real._pixels


# ---------------------------------------------------------------------------
# Visual-punch fix (rim ring / sparks / launch-streak head) -- root cause
# was rim brightness scaling by `1 - p` (dim by the time a hole reads as
# large) plus sparse 1px spark points reading as specks at 256x64+
# physical resolution. These tests pin the NEW curve/geometry; there was
# no prior test pinning the old `1 - p` formula to update.
# ---------------------------------------------------------------------------


class TestEaseBrightness:
    def test_full_brightness_below_start(self) -> None:
        assert Fireworks._ease_brightness(0.0) == 1.0
        assert Fireworks._ease_brightness(0.7) == 1.0

    def test_eases_down_after_start(self) -> None:
        mid = Fireworks._ease_brightness(0.85)
        assert 0.3 < mid < 1.0

    def test_floors_at_one(self) -> None:
        assert Fireworks._ease_brightness(1.0) == pytest.approx(0.3)

    def test_never_below_floor_past_one(self) -> None:
        # Defensive: a caller passing a slightly-over-1.0 value (rounding)
        # must not fall below the documented floor.
        assert Fireworks._ease_brightness(1.5) == pytest.approx(0.3)


class TestDrawRing:
    def test_ring_is_gap_free_circle_at_radius(self) -> None:
        real = _StubCanvas(width=200, height=200)
        b = Burst(
            cx=100.0,
            cy=100.0,
            radius_max=40.0,
            t_start=0.0,
            t_burst_dur=0.5,
            color=(200, 50, 50),
            spark_angles=(),
        )
        Fireworks._draw_ring(real, b, radius=40.0, brightness=1.0, w=200, h=200)

        # Full brightness -> exact burst color, no dimming.
        painted = {xy: rgb for xy, rgb in real._pixels.items() if rgb != (0, 0, 0)}
        assert painted
        assert all(rgb == (200, 50, 50) for rgb in painted.values())

        # Every pixel actually sits (within 1px rounding) on the circle.
        for x, y in painted:
            dist = math.hypot(x - 100.0, y - 100.0)
            assert abs(dist - 40.0) <= 1.5

        # Gap-free: no missing angular sector wider than a couple of
        # degrees (proxy -- every 5-degree wedge around the circle has at
        # least one painted pixel).
        buckets: set[int] = set()
        for x, y in painted:
            angle = math.degrees(math.atan2(y - 100.0, x - 100.0)) % 360
            buckets.add(int(angle // 5))
        assert len(buckets) >= 360 // 5 - 2  # allow a couple of rounding gaps

    def test_brightness_scales_color(self) -> None:
        real = _StubCanvas(width=60, height=60)
        b = Burst(
            cx=30.0,
            cy=30.0,
            radius_max=10.0,
            t_start=0.0,
            t_burst_dur=0.5,
            color=(200, 100, 50),
            spark_angles=(),
        )
        Fireworks._draw_ring(real, b, radius=10.0, brightness=0.25, w=60, h=60)
        painted = [rgb for rgb in real._pixels.values() if rgb != (0, 0, 0)]
        assert painted
        assert all(rgb == (50, 25, 12) for rgb in painted)

    def test_zero_brightness_paints_nothing(self) -> None:
        real = _StubCanvas(width=60, height=60)
        b = Burst(
            cx=30.0,
            cy=30.0,
            radius_max=10.0,
            t_start=0.0,
            t_burst_dur=0.5,
            color=(200, 100, 50),
            spark_angles=(),
        )
        Fireworks._draw_ring(real, b, radius=10.0, brightness=0.0, w=60, h=60)
        assert real._pixels == {}


class TestDrawSparks:
    def test_sparks_land_outside_ring_radius(self) -> None:
        real = _StubCanvas(width=200, height=200)
        spark_angles = tuple((i * 30.0, 0.0) for i in range(12))
        b = Burst(
            cx=100.0,
            cy=100.0,
            radius_max=40.0,
            t_start=0.0,
            t_burst_dur=0.5,
            color=(10, 20, 30),
            spark_angles=spark_angles,
        )
        Fireworks._draw_sparks(real, b, radius=40.0, brightness=1.0, w=200, h=200)

        painted = [xy for xy, rgb in real._pixels.items() if rgb != (0, 0, 0)]
        assert painted
        for x, y in painted:
            dist = math.hypot(x - 100.0, y - 100.0)
            # radius (40) + jitter band (1..3) -- always strictly outside
            # the ring, never on or inside it.
            assert dist > 40.0

    def test_every_fourth_spark_is_white_hot(self) -> None:
        real = _StubCanvas(width=200, height=200)
        # Zero jitter_deg for every spark -> deterministic non-overlapping
        # placement, and predictable idx-based white-hot selection.
        spark_angles = tuple((i * 30.0, 0.0) for i in range(12))
        b = Burst(
            cx=100.0,
            cy=100.0,
            radius_max=40.0,
            t_start=0.0,
            t_burst_dur=0.5,
            color=(10, 20, 30),
            spark_angles=spark_angles,
        )
        Fireworks._draw_sparks(real, b, radius=40.0, brightness=1.0, w=200, h=200)

        colors = {rgb for rgb in real._pixels.values() if rgb != (0, 0, 0)}
        assert (255, 255, 255) in colors  # at least one white-hot spark
        assert (10, 20, 30) in colors  # and at least one burst-color spark

    def test_zero_brightness_paints_nothing(self) -> None:
        real = _StubCanvas(width=60, height=60)
        b = Burst(
            cx=30.0,
            cy=30.0,
            radius_max=10.0,
            t_start=0.0,
            t_burst_dur=0.5,
            color=(200, 100, 50),
            spark_angles=((0.0, 0.0), (90.0, 0.0)),
        )
        Fireworks._draw_sparks(real, b, radius=10.0, brightness=0.0, w=60, h=60)
        assert real._pixels == {}

    def test_no_sparks_is_a_noop(self) -> None:
        real = _StubCanvas(width=60, height=60)
        b = Burst(
            cx=30.0,
            cy=30.0,
            radius_max=10.0,
            t_start=0.0,
            t_burst_dur=0.5,
            color=(200, 100, 50),
            spark_angles=(),
        )
        Fireworks._draw_sparks(real, b, radius=10.0, brightness=1.0, w=60, h=60)
        assert real._pixels == {}


class TestLaunchStreakWhiteHotHead:
    def test_head_rows_are_white_hot(self) -> None:
        real = _StubCanvas(width=60, height=60)
        b = Burst(
            cx=10.0,
            cy=5.0,
            radius_max=10.0,
            t_start=0.0,
            t_burst_dur=0.5,
            color=(200, 50, 50),
            spark_angles=(),
        )
        # p slightly above 0 -> head is a couple of rows off the very
        # bottom edge, so both head rows land in-bounds (at p=0 exactly
        # the head sits flush on the last row and its second row clips).
        Fireworks._draw_launch_streak(real, b, p=0.05, w=60, h=60)

        frac = 0.05 / _LAUNCH_OPEN_BOUNDARY
        head_y = round((60 - 1) - frac * ((60 - 1) - b.cy))
        assert real._pixels[(10, head_y)] == (255, 255, 255)
        assert real._pixels[(10, head_y + 1)] == (255, 255, 255)
        # Tail rows below the head fade in the burst's own color, not white.
        tail_color = real._pixels[(10, head_y + 2)]
        assert tail_color != (255, 255, 255)
        assert tail_color[0] > tail_color[1] == tail_color[2]  # red-family fade


# ---------------------------------------------------------------------------
# Registration (Task 3) -- _RecordingAPI idiom copied per this repo's
# per-file-duplication convention (see test_flair_spinout.py / test_flair_fisheye.py).
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
    def test_fireworks_registered(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "fireworks" in api.transitions
        assert api.transitions["fireworks"] is Fireworks

    def test_spinout_still_registered(self) -> None:
        """Fireworks registration must not displace the existing spinout."""
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "spinout" in api.transitions

    def test_other_namespaces_unaffected(self) -> None:
        api = _RecordingAPI()
        flair_pkg.register(api)
        assert "propeller" in api.animations
        assert "fisheye" in api.animations
        assert "lottery" in api.widgets


# ---------------------------------------------------------------------------
# Mandatory fold-in 2 (Task-2 review) -- explicit-seed refire semantics
# ---------------------------------------------------------------------------


class TestSeedRefireSemantics:
    """Pins the docstring contract on `seed`: an explicit seed reproduces
    the FIRST firing identically across fresh instances, but a re-fire of
    the SAME instance continues the rng (so the second firing's plan
    varies) -- reproducibility is per-instance-per-firing, not a promise
    that the same seed always plans the same sequence forever.
    """

    @staticmethod
    def _fire_full_sweep(fw: Fireworks, w: int = 160, h: int = 16) -> list[Burst]:
        canvas = _StubCanvas(width=w, height=h)
        outgoing = _make_widget(draw_pixel=True)
        incoming = _make_widget(draw_pixel=True)
        for t in (i / 20 for i in range(21)):  # 0.0, 0.05, ..., 1.0
            fw.frame_at(t, canvas, outgoing, incoming)
        assert fw._plan is not None
        return fw._plan

    def test_same_instance_two_firings_differ(self) -> None:
        fw = Fireworks(seed=7)
        first_plan = self._fire_full_sweep(fw)
        second_plan = self._fire_full_sweep(fw)
        assert second_plan != first_plan

    def test_fresh_instances_same_seed_first_firing_identical(self) -> None:
        first_plan = self._fire_full_sweep(Fireworks(seed=7))
        second_plan = self._fire_full_sweep(Fireworks(seed=7))
        assert second_plan == first_plan


# ---------------------------------------------------------------------------
# Mandatory fold-in 1 (Task-2 review) -- late-bloom perf short-circuit
# ---------------------------------------------------------------------------


class TestLateBloomPerfShortCircuit:
    """A burst whose radius alone already covers the panel's farthest
    corner proves the union of ALL bursts is total -- `_blackout_complement`
    must paint zero complement-black pixels that frame. Under the
    per-row interval-union algorithm this isn't a special-cased branch
    (there is no mask to skip building): a row whose merged interval
    already spans the whole panel yields zero gap pixels out of the same
    per-row loop every other row goes through, at the same O(n log n)
    cost -- full coverage falls out of the general case for free rather
    than needing its own short-circuit.
    """

    def test_full_cover_burst_paints_zero_black_complement_pixels(self) -> None:
        fw = Fireworks(seed=1)
        w, h = 512, 64
        canvas = _StubCanvas(width=w, height=h)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_fill_widget((0, 255, 0))

        # Centered burst; radius_max is irrelevant here since bloom-phase
        # radius (see burst_state) grows toward hypot(w, h) regardless --
        # by t=0.9 it comfortably exceeds the farthest-corner distance from
        # panel center for ANY spec-valid radius_max.
        burst = Burst(
            cx=w / 2.0,
            cy=h / 2.0,
            radius_max=40.0,
            t_start=0.0,
            t_burst_dur=0.5,
            color=(200, 50, 50),
            spark_angles=(),
        )
        fw._plan = [burst]
        fw._plan_dims = (w, h)
        fw._last_t = 0.5

        canvas.calls.clear()
        fw.frame_at(0.9, canvas, outgoing, incoming)

        black_calls = [c for c in canvas.calls if c[2:] == (0, 0, 0)]
        assert black_calls == []

    def test_non_covering_burst_still_blacks_the_far_corner(self) -> None:
        """Sanity control: a burst that has NOT yet grown to cover the
        panel still produces the ordinary complement-blackout behavior
        (the short-circuit must not fire early)."""
        fw = Fireworks(seed=1)
        w, h = 256, 64
        canvas = _StubCanvas(width=w, height=h)
        outgoing = _make_widget(draw_pixel=False)
        incoming = _make_fill_widget((0, 255, 0))

        burst = Burst(
            cx=30.0,
            cy=30.0,
            radius_max=20.0,
            t_start=0.2,
            t_burst_dur=0.3,
            color=(200, 50, 50),
            spark_angles=(),
        )
        fw._plan = [burst]
        fw._plan_dims = (w, h)
        fw._last_t = 0.5

        fw.frame_at(0.51, canvas, outgoing, incoming)

        assert canvas._pixels[(250, 60)] == (0, 0, 0)

    def test_mid_bloom_paints_far_fewer_than_half_the_panel(self) -> None:
        """Mid-bloom cost sanity check (the specific regime that used to
        be the mask version's worst frame -- several bursts jointly, but
        not individually, covering the panel: cheap in black-pixel count
        but the OLD bytearray-mask algorithm still paid a full
        stamp-then-scan on every burst's bounding box here). The
        per-row interval-union algorithm's cost tracks the actual black
        area, so the number of complement paints at this seeded 6-burst
        512x64 plan/frame stays far below a half-panel's worth of
        pixels.
        """
        w, h = 512, 64
        fw = Fireworks(seed=3)
        canvas = _StubCanvas(width=w, height=h)
        fw._plan = plan_bursts(w, h, random.Random(3), count=6)
        fw._plan_dims = (w, h)
        fw._last_t = 0.5

        canvas.calls.clear()
        fw._blackout_complement(canvas, w, h, 0.74)

        black_calls = [c for c in canvas.calls if c[2:] == (0, 0, 0)]
        assert len(black_calls) < (w * h) // 2
