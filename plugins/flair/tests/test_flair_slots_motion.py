import pytest
from led_ticker.plugin import SNAP_THRESHOLD

from led_ticker_flair.flair import slots as S
from led_ticker_flair.flair._board_transition import LAND


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


_PACE_COMBOS = [
    (3, 0.5, 60),
    (0, 0.5, 60),
    (0, 0.9, 75),
    (6, 0.5, 105),
    (3, 0.8, 150),
    (3, 0.9, 300),
    (6, 0.9, 525),
]


@pytest.mark.parametrize(("spins", "stagger", "want"), _PACE_COMBOS)
def test_pace_floor_values(spins, stagger, want):
    assert S.pace_floor(spins, stagger) == want


@pytest.mark.parametrize(("spins", "stagger", "_want"), _PACE_COMBOS)
def test_pace_floor_bounds_symbols_per_frame(spins, stagger, _want):
    n = S.pace_floor(spins, stagger)
    stop = 1.0 - stagger  # the first reel
    k = S.reel_advances(spins, stop, stagger)
    pitch, gap = 35, 9
    travel = k * pitch
    overshoot = S.overshoot_rows(pitch, gap)
    d = []
    for i in range(n + 1):
        t = i / n
        s = min(t / SNAP_THRESHOLD / LAND, 1.0)
        u = min(1.0, s / stop)
        d.append(S.displacement(u, travel, overshoot))
    worst = max(abs(b - a) for a, b in zip(d, d[1:], strict=False)) / pitch
    assert worst <= 0.3


def test_glide_endpoints():
    assert S.glide(0.0) == 0.0
    assert S.glide(S.SETTLE_START) == pytest.approx(1.0)
    assert S.glide(1.0) == 1.0
    g = [S.glide(i / 100) for i in range(101)]
    assert all(b >= a for a, b in zip(g, g[1:], strict=False))


@pytest.mark.parametrize(
    "geo",
    [
        (10, 7, 30, 24),
        (30, 24, 10, 7),
        (5, 8, 5, 8),
        (0, 3, 100, 4),
        (40, 0, 30, 24),
        (30, 24, 40, 0),
    ],
)
def test_reel_window_endpoints(geo):
    x0, w0, x1, w1 = geo
    assert S.reel_window(*geo, 0.0) == (x0, w0)
    assert S.reel_window(*geo, 1.0) == (x1, w1)
    wl, ww = S.reel_window(*geo, 0.5)
    assert abs(ww - (w0 + w1) / 2) <= 1
    assert min(x0, x1) <= wl <= max(x0, x1)
