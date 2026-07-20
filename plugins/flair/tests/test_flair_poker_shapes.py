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


class TestHeartNotPinched:
    """James (2026-07-19): the heart bottom looked pinched on the sign — the
    old linear wedge left a multi-row 1–4 px spike dangling below the body.
    The emoji-curve mask (spec 2026-07-20) tapers to the tip within a couple
    of rows. Guard the taper rate, not the exact silhouette."""

    @staticmethod
    def _row_widths(r):
        pts = interior_pixels("hearts", r)
        rows = {}
        for x, y in pts:
            lo, hi = rows.get(y, (x, x))
            rows[y] = (min(lo, x), max(hi, x))
        return {y: hi - lo + 1 for y, (lo, hi) in rows.items()}

    def test_bottom_taper_is_short(self):
        # At each display-relevant radius, rows narrower than a quarter of
        # the shape's width must be confined to the tip's short cusp taper.
        # Allowance scales with r (a cusp taper is O(r) rows but few): the
        # emoji curve sits at 3-4 such rows; the old linear wedge had 5+ at
        # r=12 (the visible spike on the sign).
        for r in (7, 12, 20):
            widths = self._row_widths(r)
            max_w = max(widths.values())
            narrow = [y for y, w in widths.items() if w <= max(2, max_w // 4)]
            assert len(narrow) <= max(3, r // 5), (
                f"r={r}: {len(narrow)} narrow rows {sorted(narrow)} — "
                "pinched tip is back"
            )

    def test_heart_still_heart_shaped(self):
        # Sanity net alongside the taper guard: symmetric, top notch between
        # lobes, single bottom tip, fits the ±r box.
        r = 16
        pts = interior_pixels("hearts", r)
        assert pts == {(-x, y) for x, y in pts}  # x-mirror symmetric
        ys = [y for _, y in pts]
        top, bot = min(ys), max(ys)
        assert bot > 0 > top
        assert all(abs(x) <= r and -r <= y <= r for x, y in pts)
        # top notch: on the topmost lobe row, x=0 is OUTSIDE (cleft)
        top_row_xs = {x for x, y in pts if y == top}
        assert 0 not in top_row_xs
