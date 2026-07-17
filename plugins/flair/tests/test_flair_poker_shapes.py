"""Pure suit-shape math for flair.poker (no canvas)."""

from led_ticker_flair.flair.poker import (
    RING_W,
    SUITS,
    inside,
    interior_pixels,
    ring_pixels,
)


class TestInside:
    def test_center_inside_all_suits(self):
        for s in SUITS:
            assert inside(s, 0, 0, 10), s

    def test_far_corner_outside_all_suits(self):
        for s in SUITS:
            assert not inside(s, 100, 100, 10), s

    def test_zero_radius_empty(self):
        for s in SUITS:
            assert not inside(s, 0, 0, 0), s

    def test_diamond_is_l1_ball(self):
        assert inside("diamonds", 6, 3, 10)  # 9 <= 10
        assert not inside("diamonds", 7, 5, 10)  # 12 > 10

    def test_club_and_spade_have_a_stem_below_center(self):
        # stem is a thin vertical column just below center (y down)
        for s in ("clubs", "spades"):
            assert inside(s, 0, 8, 20), s
            assert not inside(s, 22, 8, 20), s  # too far sideways for the stem


class TestRings:
    def test_ring_is_interior_shell(self):
        interior = interior_pixels("hearts", 16)
        shell = ring_pixels("hearts", 16)
        assert shell <= interior
        inner = interior_pixels("hearts", 16 - RING_W)
        assert shell.isdisjoint(inner)
        assert shell == interior - inner

    def test_ring_nonempty_for_reasonable_radius(self):
        for s in SUITS:
            assert ring_pixels(s, 14), s


class TestRingUnionCoverage:
    """The property the reveal mask actually relies on (NOT interior
    monotonicity — clubs violate that): the union of integer-radius rings
    up to R covers interior(R). Clubs are the adversarial case."""

    def test_union_of_rings_covers_interior(self):
        for s in SUITS:
            R = 22
            union = set()
            for r in range(1, R + 1):
                union |= ring_pixels(s, r)
            missing = interior_pixels(s, R) - union
            assert not missing, f"{s}: {len(missing)} interior px uncovered by rings"
