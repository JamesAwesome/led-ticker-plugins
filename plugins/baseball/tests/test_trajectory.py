"""tests/test_trajectory.py"""

from led_ticker_baseball.trajectory import ArcPlan, plan_arc

W, H = 106, 24


def _apex(plan):
    # column and height of the highest (min-y) point
    x, y = min(plan.points, key=lambda p: p[1])
    return x, (H - 1 - y)


def test_home_run_clears():
    p = plan_arc(28, 114.2, 451, "fly_ball", "HOME RUN", W, H)
    assert p.act == "clears"
    assert p.wall_x is not None and p.wall_x >= W - 10


def test_caught_flyout_lands_short_with_no_wall():
    p = plan_arc(35, 99.0, 360, "fly_ball", "FLY OUT", W, H)
    assert p.act == "caught"
    assert p.wall_x is None
    assert p.landing[0] < W - 12  # lands short of the wall


def test_warning_track_out_is_track_act():
    p = plan_arc(30, 101.0, 395, "fly_ball", "FLY OUT", W, H)
    assert p.act == "track"


def test_grounder_stays_low():
    p = plan_arc(-4, 98.0, 0, "ground_ball", "GROUND OUT", W, H)
    assert p.act == "grounder"
    _cx, peak = _apex(p)
    assert peak <= 4  # barely leaves the ground


def test_equal_distance_hrs_differ_by_bb_type():
    """Two 430ft home runs, one line_drive one fly_ball, must NOT draw the
    same silhouette — the core mandate of this phase."""
    liner = plan_arc(18, 108, 430, "line_drive", "HOME RUN", W, H)
    moon = plan_arc(34, 104, 430, "fly_ball", "HOME RUN", W, H)
    assert _apex(liner)[1] < _apex(moon)[1]  # liner peaks lower
    assert _apex(liner)[0] > _apex(moon)[0]  # liner apexes later
    assert liner.points != moon.points


def test_low_liner_runs_off_the_edge():
    p = plan_arc(8, 106, 0, "line_drive", "LINE OUT", W, H)
    assert p.landing[0] >= W - 1  # never comes down inside the box


def test_never_raises_on_missing_values():
    assert isinstance(plan_arc(None, None, None, "", "", W, H), ArcPlan)
