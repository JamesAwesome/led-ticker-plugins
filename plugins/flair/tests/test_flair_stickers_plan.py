"""Pure-math tests for the stickers plan module (no canvas)."""

import math
import random

from led_ticker_flair.flair.stickers import (
    departed_count,
    dilate,
    plan_stickers,
    rotate_pixels,
    visible_count,
)

BIGSIGN = (256, 64, 36)  # panel_w, panel_h, footprint (32px sprite + 2*OUTLINE_PAD)
SMALLSIGN = (160, 16, 12)  # 8px sprite + 2*OUTLINE_PAD


class TestPlan:
    def test_orders_are_independent_permutations(self):
        rng = random.Random(7)
        plan = plan_stickers(*BIGSIGN, slugs=["taco"], rng=rng)
        n = len(plan)
        assert sorted(s.arrive for s in plan) == list(range(n))
        assert sorted(s.depart for s in plan) == list(range(n))
        # not the same permutation, not reversed (peel must not be a rewind)
        assert [s.arrive for s in plan] != [s.depart for s in plan]
        assert [s.arrive for s in plan] != [n - 1 - s.depart for s in plan]

    def test_deterministic_per_seed(self):
        p1 = plan_stickers(*BIGSIGN, slugs=["taco", "sun"], rng=random.Random(3))
        p2 = plan_stickers(*BIGSIGN, slugs=["taco", "sun"], rng=random.Random(3))
        assert p1 == p2

    def test_slug_choice_restricted_to_pool(self):
        plan = plan_stickers(*BIGSIGN, slugs=["moon"], rng=random.Random(1))
        assert {s.slug for s in plan} == {"moon"}


class TestCoverage:
    def _covers(self, panel_w, panel_h, footprint, seed):
        """Union of every sticker's ROTATED inscribed backing must cover the
        panel. Model the backing as the footprint square rotated about the
        sticker center (the conservative inscribed axis-aligned square)."""
        rng = random.Random(seed)
        plan = plan_stickers(panel_w, panel_h, footprint, ["taco"], rng)
        covered = [[False] * panel_w for _ in range(panel_h)]
        for s in plan:
            a = math.radians(abs(s.angle_deg))
            half = (footprint / (math.cos(a) + math.sin(a))) / 2
            y_min = max(0, int(s.cy - half))
            y_max = min(panel_h, int(s.cy + half) + 1)
            x_min = max(0, int(s.cx - half))
            x_max = min(panel_w, int(s.cx + half) + 1)
            for y in range(y_min, y_max):
                for x in range(x_min, x_max):
                    covered[y][x] = True
        return all(all(row) for row in covered)

    def test_bigsign_covered_across_seeds(self):
        assert all(self._covers(*BIGSIGN, seed=s) for s in range(25))

    def test_smallsign_covered_across_seeds(self):
        assert all(self._covers(*SMALLSIGN, seed=s) for s in range(25))


class TestPacing:
    def test_build_reaches_all_at_half(self):
        assert visible_count(0.0, 30) == 0
        assert visible_count(0.5, 30) == 30
        assert visible_count(0.25, 30) not in (0, 30)  # actually progressive

    def test_peel_reaches_all_at_one(self):
        assert departed_count(0.5, 30) == 0
        assert departed_count(1.0, 30) == 30

    def test_monotonic(self):
        vals = [visible_count(t / 100, 30) for t in range(0, 51)]
        assert vals == sorted(vals)


class TestPixelMath:
    def test_dilate_grows_mask(self):
        m = {(5, 5)}
        assert dilate(m, 1) == {(x, y) for x in (4, 5, 6) for y in (4, 5, 6)}

    def test_rotate_zero_is_identity(self):
        px = {(0, 0): (1, 2, 3), (3, 0): (4, 5, 6)}
        assert rotate_pixels(px, 0.0) == px

    def test_rotate_preserves_colors_and_is_hole_free(self):
        # solid 10x10 block rotated 10 deg must stay a connected solid region:
        # pixel count can't shrink (inverse mapping guarantees no holes).
        # NOTE: the count inequality is a proxy that holds at THIS small size;
        # at realistic 36px footprints a rotated square legitimately loses a
        # few CORNER pixels to discretization (still zero interior holes) —
        # don't "strengthen" this test to a bigger block and chase a phantom.
        px = {(x, y): (9, 9, 9) for x in range(10) for y in range(10)}
        out = rotate_pixels(px, 10.0)
        assert len(out) >= len(px)
        assert set(out.values()) == {(9, 9, 9)}
