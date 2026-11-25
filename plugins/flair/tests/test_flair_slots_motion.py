import pytest
from led_ticker.plugin import SNAP_THRESHOLD

from led_ticker_flair.flair import slots as S
from led_ticker_flair.flair._board_transition import LAND


def test_schedule_is_stop_times_over_the_board_ripple():
    import random

    from led_ticker.plugin import TickerMessage

    from led_ticker_flair.flair._board_transition import BoardTransition

    class _C:
        width, height = 160, 16

        def Clear(self):
            pass

        def SetPixel(self, *a):
            pass

    from led_ticker_flair.flair.splitflap_board import build_board

    p = S.SlotsRandom(3, 0.5)
    c = _C()
    out_plan = p._plan(c, TickerMessage(text="WIN"), 0, 1)
    in_plan = p._plan(c, TickerMessage(text="PULL LEVER"), 0, 1)
    board = build_board(out_plan, in_plan, p.steps, random.Random(1))
    p._rng = random.Random(11)
    got = p._schedule(board)
    p._rng = random.Random(11)
    want = [1 - p.stagger + st for st in BoardTransition._schedule(p, board)]
    assert got == want and got


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
    (0, 0.9, 90),
    (6, 0.5, 101),
    (3, 0.8, 150),
    (3, 0.9, 300),
    (6, 0.9, 504),
]


@pytest.mark.parametrize(("spins", "stagger", "want"), _PACE_COMBOS)
def test_pace_floor_values(spins, stagger, want):
    assert S.pace_floor(spins, stagger) == want


@pytest.mark.parametrize(("spins", "stagger", "_want"), _PACE_COMBOS)
def test_pace_floor_bounds_symbols_per_frame(spins, stagger, _want):
    n = S.pace_floor(spins, stagger)
    pitch, gap = 35, 9
    overshoot = S.overshoot_rows(pitch, gap)
    worst = 0.0
    # every raw stop position, including the first reel (stop = 1 - stagger)
    for i in range(41):
        stop = 1.0 - stagger + stagger * i / 40
        k = S.reel_advances(spins, stop, stagger)
        travel = k * pitch
        d = []
        for f in range(n + 1):
            s = min(f / n / SNAP_THRESHOLD / LAND, 1.0)
            u = min(1.0, s / stop)
            d.append(S.displacement(u, travel, overshoot))
        step = max(abs(b - a) for a, b in zip(d, d[1:], strict=False)) / pitch
        worst = max(worst, step)
    assert worst <= 0.3


def test_rounding_headroom():
    assert S.rounding_headroom(3) == pytest.approx(5 / 4.5)
    assert S.rounding_headroom(0) == pytest.approx(2 / 1.5)


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
    assert S.reel_window(*geo, 0.0) == (x0, w0, x0 + w0 / 2)
    assert S.reel_window(*geo, 1.0) == (x1, w1, x1 + w1 / 2)
    wl, ww, cx = S.reel_window(*geo, 0.5)
    assert cx == pytest.approx(((x0 + w0 / 2) + (x1 + w1 / 2)) / 2)
    assert abs(ww - (w0 + w1) / 2) <= 1
    assert min(x0, x1) <= wl <= max(x0, x1)


@pytest.mark.parametrize(
    ("geo", "up"),
    [((144, 12, 128, 20), False), ((128, 20, 144, 12), True)],
)
def test_glide_never_steps_backwards(geo, up):
    width = 3
    oxs = []
    for i in range(201):
        _wl, _ww, cx = S.reel_window(*geo, i / 200)
        oxs.append(round(cx - width / 2))
    pairs = list(zip(oxs, oxs[1:], strict=False))
    if up:
        assert all(b >= a for a, b in pairs)
    else:
        assert all(b <= a for a, b in pairs)


@pytest.mark.parametrize(
    "geo", [(144, 12, 128, 20), (10, 7, 30, 24), (3, 5, 40, 9), (30, 24, 10, 7)]
)
def test_window_edges_monotone(geo):
    """Each window edge moves one way across the glide: the clip never steps
    backwards even where the width rounds."""
    lefts, rights = [], []
    for i in range(401):
        wl, ww, _cx = S.reel_window(*geo, i / 400)
        lefts.append(wl)
        rights.append(wl + ww)
    sl = 1 if geo[2] >= geo[0] else -1
    sr = 1 if geo[2] + geo[3] >= geo[0] + geo[1] else -1
    assert all(sl * (b - a) >= 0 for a, b in zip(lefts, lefts[1:], strict=False))
    assert all(sr * (b - a) >= 0 for a, b in zip(rights, rights[1:], strict=False))


def test_spins_zero_later_reels_cycle_in_betweens():
    """spins = 0 still builds a board with >= 2 in-between flaps, so reels with
    k >= 3 keep spinning through borrowed characters until their stop."""
    from led_ticker.plugin import TickerMessage

    class _C:
        width, height = 160, 16

        def Clear(self):
            pass

        def Fill(self, *a):
            pass

        def SubFill(self, *a):
            pass

        def SetPixel(self, *a):
            pass

        def SetImage(self, *a):
            pass

    p = S.Slots(spins=0, stagger=0.8)
    p.frame_at(
        0.0, _C(), TickerMessage(text="NOW BOARDING"), TickerMessage(text="GATE 12")
    )
    board = p._board
    assert board is not None
    checked = 0
    for flap, reel in zip(board.flaps, p._reels, strict=True):
        if flap.static or reel.k < 3 or len(flap.seq) <= 2:
            continue
        first, last = reel.strip[0], reel.strip[-1]

        def key(c):
            return None if c is None else c.rows_key()

        ends = {key(first), key(last)}
        assert any(s is not None and key(s) not in ends for s in reel.strip[1:-1]), (
            reel.k
        )
        checked += 1
    assert checked >= 1
