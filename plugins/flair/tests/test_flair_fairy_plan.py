import random

from led_ticker_flair.flair.fairy import _mix, plan_path

BIG = (256, 64, 4)
SMALL = (160, 16, 1)


class TestPlanPath:
    def test_deterministic_per_seed(self):
        a = plan_path(*BIG, random.Random(4))
        b = plan_path(*BIG, random.Random(4))
        assert a == b

    def test_covers_every_column(self):
        for w, h, s in (BIG, SMALL):
            assert len(plan_path(w, h, s, random.Random(1))) == w

    def test_stays_on_panel_and_nearly_straight(self):
        # Near-straight (James's pick): total vertical spread bounded by
        # half the panel; every y safely on-panel.
        for w, h, s in (BIG, SMALL):
            for seed in range(10):
                ys = plan_path(w, h, s, random.Random(seed))
                assert all(0 < y < h - 1 for y in ys), (w, h, seed)
                assert max(ys) - min(ys) <= h / 2, (w, h, seed)

    def test_baseline_in_center_band(self):
        # The MEAN of the path sits in the center third (drift/wobble are
        # small excursions around it).
        for w, h, s in (BIG, SMALL):
            for seed in range(10):
                ys = plan_path(w, h, s, random.Random(seed))
                mean = sum(ys) / len(ys)
                assert h / 2 - h / 6 - 1 <= mean <= h / 2 + h / 6 + 1


class TestMix:
    def test_deterministic_and_spread(self):
        assert _mix(1, 2, 3) == _mix(1, 2, 3)
        vals = {_mix(7, x, 0) & 0xFF for x in range(200)}
        assert len(vals) > 40  # mixes, not constant/degenerate

    def test_order_sensitive(self):
        assert _mix(1, 2) != _mix(2, 1)
