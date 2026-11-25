import pytest

from led_ticker_flair.flair import slots as S


def test_reel_stop_first_and_last():
    assert S.reel_stop("forward", 0, 0, 100, 0.5, 0.0) == pytest.approx(0.5)
    assert S.reel_stop("forward", 100, 0, 100, 0.5, 0.0) == pytest.approx(1.0)
    assert S.reel_stop("reverse", 0, 0, 100, 0.5, 0.0) == pytest.approx(1.0)
    assert S.reel_stop("random", 0, 0, 100, 0.5, 0.3) == pytest.approx(0.65)
    assert S.reel_stop("forward", 0, 0, 100, 0.0, 0.0) == pytest.approx(1.0)


def test_reel_advances_scales_with_stop():
    assert S.reel_advances(3, 0.5, 0.5) == 4  # first reel: spins + 1
    assert S.reel_advances(3, 1.0, 0.5) == 8  # last reel spins twice as long
    assert S.reel_advances(0, 1.0, 0.0) == 1


def test_reel_advances_floor_is_one():
    assert S.reel_advances(0, 0.1, 0.9) == 1


def test_speed_norm_trapezoid():
    assert S.speed_norm(0.0) == 0.0
    assert S.speed_norm(0.075) == pytest.approx(0.5)
    assert S.speed_norm(0.3) == 1.0
    assert S.speed_norm(0.675) == pytest.approx(0.5)
    assert S.speed_norm(0.9) == 0.0 and S.speed_norm(1.0) == 0.0
    assert S.speed_norm(-1) == 0.0 and S.speed_norm(2) == 0.0


def test_speed_norm_segment_boundaries():
    assert S.speed_norm(S.U_IN) == 1.0
    assert S.speed_norm(S.CRUISE_END) == pytest.approx(1.0)
    assert S.speed_norm(S.SETTLE_START) == 0.0


def test_displacement_endpoints_and_monotone_travel():
    assert S.displacement(0.0, 100.0, 3) == 0.0
    assert S.displacement(0.9, 100.0, 3) == pytest.approx(100.0)
    assert S.displacement(1.0, 100.0, 3) == pytest.approx(100.0, abs=1e-9)
    xs = [S.displacement(i / 90, 100.0, 3) for i in range(82)]
    assert all(b >= a for a, b in zip(xs, xs[1:], strict=False))


def test_displacement_overshoots_by_b_at_settle_midpoint():
    assert S.displacement(0.95, 100.0, 3) == pytest.approx(103.0)
    assert S.displacement(0.95, 100.0, 1) == pytest.approx(101.0)


def test_displacement_cruise_speed_matches_area():
    d1, d2 = S.displacement(0.3, 60.0, 1), S.displacement(0.4, 60.0, 1)
    assert (d2 - d1) / 0.1 == pytest.approx(100.0)


def test_displacement_continuous_at_segment_joins():
    eps = 1e-9
    for u in (S.U_IN, S.CRUISE_END, S.SETTLE_START):
        assert S.displacement(u - eps, 80.0, 2) == pytest.approx(
            S.displacement(u + eps, 80.0, 2), abs=1e-6
        )


def test_shade_is_plain_at_ends_and_dim_in_cruise():
    assert all(S.shade_for(u) == 1.0 for u in (0.0, 0.9, 1.0))
    assert S.shade_for(0.3) == pytest.approx(0.6)
