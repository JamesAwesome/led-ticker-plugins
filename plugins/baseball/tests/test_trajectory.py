"""tests/test_trajectory.py"""

from led_ticker.plugin import HeadlessBackend

from led_ticker_baseball.trajectory import ArcPlan, draw_trajectory, plan_arc

W, H = 106, 24


def _canvas():
    return HeadlessBackend(512, 64).create_canvas()


def _lit(real):
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}


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
    """Two home runs identical in LA/EV/distance, differing ONLY in bb_type
    (line_drive vs fly_ball), must NOT draw the same silhouette — bb_type
    itself is the sole differentiator (the core mandate of this phase). The
    line_drive is a flatter rope (lower apex) than the fly_ball moonshot."""
    liner = plan_arc(28, 105, 430, "line_drive", "HOME RUN", W, H)
    moon = plan_arc(28, 105, 430, "fly_ball", "HOME RUN", W, H)
    assert _apex(liner)[1] < _apex(moon)[1]  # liner peaks lower (rope)
    assert liner.points != moon.points  # bb_type alone changed the shape


def test_hr_arc_peak_scales_with_distance():
    """Distance must give the HR arc teeth: holding LA/EV/bb_type fixed, a
    462ft HR towers measurably higher than a 385ft wall-scraper."""
    short = plan_arc(28, 105, 385, "fly_ball", "HOME RUN", W, H)
    deep = plan_arc(28, 105, 462, "fly_ball", "HOME RUN", W, H)
    assert short.act == deep.act == "clears"
    assert _apex(deep)[1] > _apex(short)[1]  # farther HR apexes higher


def test_bb_type_alone_changes_silhouette():
    """Holding LA/EV/distance/result fixed and varying ONLY bb_type across
    three fair-ball shapes must produce three pairwise-different point lists,
    and the line_drive rope must peak lower than the steep popup."""
    la, ev, dist, res = 25, 100, 350, "DOUBLE"
    rope = plan_arc(la, ev, dist, "line_drive", res, W, H)
    fly = plan_arc(la, ev, dist, "fly_ball", res, W, H)
    pop = plan_arc(la, ev, dist, "popup", res, W, H)
    # same act — only the silhouette varies with bb_type
    assert rope.act == fly.act == pop.act == "fair"
    assert rope.points != fly.points
    assert rope.points != pop.points
    assert fly.points != pop.points
    assert _apex(rope)[1] < _apex(pop)[1]  # rope flatter than popup


def test_low_liner_runs_off_the_edge():
    p = plan_arc(8, 106, 0, "line_drive", "LINE OUT", W, H)
    assert p.landing[0] >= W - 1  # never comes down inside the box


def test_never_raises_on_missing_values():
    assert isinstance(plan_arc(None, None, None, "", "", W, H), ArcPlan)


def test_progress_zero_shows_less_than_full():
    real0 = _canvas()
    real1 = _canvas()
    p = plan_arc(28, 114, 451, "fly_ball", "HOME RUN", 106, 24)
    draw_trajectory(real0, (396, 20, 106, 24), p, 0.15)
    draw_trajectory(real1, (396, 20, 106, 24), p, 1.0)
    assert len(_lit(real0)) < len(_lit(real1))  # ball hasn't flown the whole path


def test_clears_paints_wall_tick_at_rest():
    real = _canvas()
    p = plan_arc(28, 114, 451, "fly_ball", "HOME RUN", 106, 24)
    draw_trajectory(real, (396, 20, 106, 24), p, 1.0)
    # a bright vertical run near the wall column
    wall_col = 396 + p.wall_x
    col_hits = sum(1 for (x, y) in _lit(real) if x == wall_col)
    assert col_hits >= 6


def test_never_raises_off_box_progress():
    real = _canvas()
    p = plan_arc(8, 106, 0, "line_drive", "LINE OUT", 106, 24)
    draw_trajectory(real, (396, 20, 106, 24), p, 2.0)  # clamps


def test_track_marker_stays_within_box():
    real = _canvas()
    # a deep flyout that carries to the warning track (out + distance >= 370)
    p = plan_arc(30, 101, 395, "fly_ball", "FLY OUT", 106, 24)
    assert p.act == "track"  # sanity: this fixture really is a track act
    draw_trajectory(real, (396, 20, 106, 24), p, 1.0)
    lit = _lit(real)
    # nothing may paint above the box top (y0=20) or below its bottom (y0+h-1=43)
    assert not any(y < 20 or y > 43 for (x, y) in lit)
