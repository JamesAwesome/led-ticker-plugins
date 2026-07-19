import random

from led_ticker_flair.flair.lightning import plan_bolt

BIG = (256, 64, 4)
SMALL = (160, 16, 1)


class TestPlanBolt:
    def test_deterministic_per_seed(self):
        a = plan_bolt(*BIG, random.Random(4))
        b = plan_bolt(*BIG, random.Random(4))
        assert a == b

    def test_covers_every_column(self):
        for w, h, s in (BIG, SMALL):
            crack = plan_bolt(w, h, s, random.Random(1))
            assert len(crack) == w

    def test_y_confined_to_center_third(self):
        for w, h, s in (BIG, SMALL):
            for seed in range(10):
                crack = plan_bolt(w, h, s, random.Random(seed))
                lo, hi = h / 2 - h / 6 - 1, h / 2 + h / 6 + 1  # ±1 rounding slack
                assert all(lo <= y <= hi for y in crack), (w, h, seed)

    def test_zigzags_direction_alternates(self):
        # A true zigzag crosses the panel midline repeatedly: count sign
        # changes of (y - h/2) at the planned vertices via the column walk —
        # at least 3 crossings on a bigsign-width bolt.
        w, h, s = BIG
        crack = plan_bolt(w, h, s, random.Random(2))
        mid = h / 2
        signs = [1 if y > mid else -1 for y in crack if y != mid]
        crossings = sum(1 for a, b in zip(signs, signs[1:], strict=False) if a != b)
        assert crossings >= 3
