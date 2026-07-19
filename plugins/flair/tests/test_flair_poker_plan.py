import random

from led_ticker_flair.flair.poker import (
    RingCache,
    plan_glyphs,
    pulse_radius,
)

BIG = (256, 64)
SMALL = (160, 16)


class TestPlan:
    def test_deterministic_per_seed(self):
        a = plan_glyphs(*BIG, ["hearts", "diamonds"], random.Random(4))
        b = plan_glyphs(*BIG, ["hearts", "diamonds"], random.Random(4))
        assert a == b

    def test_suits_cycle_through_pool_only(self):
        g = plan_glyphs(*BIG, ["diamonds"], random.Random(1))
        assert {x.suit for x in g} == {"diamonds"}
        g2 = plan_glyphs(*BIG, ["hearts", "spades"], random.Random(1))
        assert {x.suit for x in g2} <= {"hearts", "spades"}

    def test_stagger_in_bounds(self):
        for g in plan_glyphs(*BIG, ["clubs"], random.Random(2)):
            assert 0.0 <= g.stagger <= 0.25

    def test_grid_counts_reasonable(self):
        assert 12 <= len(plan_glyphs(*BIG, ["hearts"], random.Random(0))) <= 24
        assert 3 <= len(plan_glyphs(*SMALL, ["hearts"], random.Random(0))) <= 12


class TestPulseTimeline:
    def test_none_before_stagger_start(self):
        assert pulse_radius(0.0, 0.2) is None

    def test_expands_then_repeats(self):
        # within a wave the radius grows; wave index increments across waves
        r1, w1 = pulse_radius(0.35, 0.0)
        r2, w2 = pulse_radius(0.45, 0.0)
        assert r2 > r1 or w2 > w1

    def test_final_wave_reached_late(self):
        _, w = pulse_radius(0.99, 0.0)
        assert w >= 1  # multiple waves have passed by the end


class TestRingCache:
    def test_quantizes_and_caches(self):
        # Hue quantizes to whole degrees at the COLORIZE layer: two gets at
        # 40.0 / 40.4 share one cache entry (same object). Geometry itself is
        # process-cached in _ring_geom, so no rasterization spy is meaningful
        # here anymore.
        cache = RingCache()
        a = cache.get("hearts", 12, 40.0)
        b = cache.get("hearts", 12, 40.4)  # same int r, same whole-deg hue
        assert a is b
        assert a  # non-empty pixel list
        c = cache.get("hearts", 12, 41.0)  # different whole degree -> new entry
        assert c is not a
