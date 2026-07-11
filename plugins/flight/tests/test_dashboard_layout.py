from led_ticker.plugin import unwrap_to_real

from led_ticker_flight.dashboard_layout import DWELL_MS, render_dashboard
from led_ticker_flight.data import SAMPLE_AIRCRAFT
from led_ticker_flight.palette import AIRLINES, ALT, DIST, IDENT, LABEL, SPEED, TRACK


def lit(canvas_or_real):
    return dict(unwrap_to_real(canvas_or_real)._pixels)


def test_fin_and_hero(longboi):
    render_dashboard(longboi, SAMPLE_AIRCRAFT, clock_ms=0)
    pixels = lit(longboi)
    ua = AIRLINES["UA"]
    assert pixels[(6, 37)] == ua.c1  # fin bottom-left: y = 6 + 31
    white = [
        (x, y) for (x, y), c in pixels.items() if c == IDENT and y <= 35 and x < 190
    ]
    assert len(white) > 50


def test_all_four_column_value_colors_present(longboi):
    render_dashboard(longboi, SAMPLE_AIRCRAFT, clock_ms=0)
    cols = set(lit(longboi).values())
    for semantic in (ALT, SPEED, TRACK, DIST, LABEL):
        assert semantic in cols, f"missing column color {semantic}"


def test_columns_start_at_or_after_190(longboi):
    render_dashboard(longboi, SAMPLE_AIRCRAFT, clock_ms=0)
    label_px = [(x, y) for (x, y), c in lit(longboi).items() if c == LABEL]
    # labels at y8..18; paging dots are lower
    col_labels = [p for p in label_px if p[1] < 20]
    assert col_labels and min(x for x, _ in col_labels) >= 190


def test_rotation_dwell_4800(longboi):
    from led_ticker.plugin import HeadlessCanvas, ScaledCanvas

    a = ScaledCanvas(HeadlessCanvas(512, 64), scale=4, content_height=16)
    b = ScaledCanvas(HeadlessCanvas(512, 64), scale=4, content_height=16)
    render_dashboard(a, SAMPLE_AIRCRAFT, clock_ms=DWELL_MS - 1)
    render_dashboard(b, SAMPLE_AIRCRAFT, clock_ms=DWELL_MS + 1)
    assert lit(a) != lit(b)


def test_empty_state_wide_label(longboi):
    render_dashboard(longboi, [], clock_ms=500)
    assert lit(longboi)


def test_alt_and_speed_columns_do_not_collide(longboi):
    """Regression for task-10-adversarial finding #1: hires() used to return
    the absolute end-x instead of the advance width, so `iw`/`vx` chains
    double-counted x — the ALT value column overlapped the DIST column for
    climbing/descending flights. Assert ALT stays strictly left of SPEED and
    that DIST is actually painted."""
    render_dashboard(longboi, SAMPLE_AIRCRAFT, clock_ms=0)  # idx 0 = UA2341
    pixels = lit(longboi)
    alt_xs = [x for (x, _), c in pixels.items() if c == ALT]
    speed_xs = [x for (x, _), c in pixels.items() if c == SPEED]
    dist_xs = [x for (x, _), c in pixels.items() if c == DIST]
    assert alt_xs, "ALT value never painted"
    assert speed_xs, "SPEED value never painted"
    assert dist_xs, "DIST value never painted"
    assert max(alt_xs) < min(speed_xs), "ALT column overlaps/crowds SPEED column"
