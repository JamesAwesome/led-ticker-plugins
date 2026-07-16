from led_ticker.plugin import unwrap_to_real

from led_ticker_flight.dashboard_layout import DWELL_MS, render_dashboard
from led_ticker_flight.data import SAMPLE_AIRCRAFT, Aircraft
from led_ticker_flight.palette import (
    AIRLINES,
    ALT,
    DEFAULT_AIRLINE,
    DIST,
    IDENT,
    LABEL,
    SPEED,
    TRACK,
    TYPE,
)

MID = DWELL_MS // 2  # see test_hero_layout.py's MID for why: avoids the
# fade-through-black at dwell-window edges.


def lit(canvas_or_real):
    return dict(unwrap_to_real(canvas_or_real)._pixels)


def test_fin_and_hero(longboi):
    render_dashboard(longboi, SAMPLE_AIRCRAFT, clock_ms=MID)
    pixels = lit(longboi)
    ua = AIRLINES["UA"]
    assert pixels[(6, 37)] == ua.c1  # fin bottom-left: y = 6 + 31
    white = [
        (x, y) for (x, y), c in pixels.items() if c == IDENT and y <= 35 and x < 190
    ]
    assert len(white) > 50


def test_all_four_column_value_colors_present(longboi):
    render_dashboard(longboi, SAMPLE_AIRCRAFT, clock_ms=MID)
    cols = set(lit(longboi).values())
    for semantic in (ALT, SPEED, TRACK, DIST, LABEL):
        assert semantic in cols, f"missing column color {semantic}"


def test_columns_start_at_or_after_190(longboi):
    render_dashboard(longboi, SAMPLE_AIRCRAFT, clock_ms=MID)
    label_px = [(x, y) for (x, y), c in lit(longboi).items() if c == LABEL]
    # labels at y8..18; paging dots are lower
    col_labels = [p for p in label_px if p[1] < 20]
    assert col_labels and min(x for x, _ in col_labels) >= 190


def test_rotation_dwell_4800(longboi):
    from led_ticker.plugin import HeadlessCanvas, ScaledCanvas

    a = ScaledCanvas(HeadlessCanvas(512, 64), scale=4, content_height=16)
    b = ScaledCanvas(HeadlessCanvas(512, 64), scale=4, content_height=16)
    render_dashboard(a, SAMPLE_AIRCRAFT, clock_ms=MID)
    render_dashboard(b, SAMPLE_AIRCRAFT, clock_ms=DWELL_MS + MID)
    assert lit(a) != lit(b)


def test_empty_state_wide_label(longboi):
    render_dashboard(longboi, [], clock_ms=500)
    assert lit(longboi)


def test_unknown_airline_renders_default_grey_no_type_row(longboi):
    """N-number callsigns (general aviation registrations, not airline
    flight numbers) are the majority real-world case — airline_of() falls
    back to DEFAULT_AIRLINE (name == ""). Must not raise, must fin in the
    default grey, and must not draw a name/type row (al.name == "" and
    actype == "" both gate their `hires(...)` calls off)."""
    unknown = Aircraft("N12345", "", 3500, 0, 120, 180, "5KM N", 5.0, "N12345")
    render_dashboard(longboi, [unknown], clock_ms=0)
    pixels = lit(longboi)
    assert DEFAULT_AIRLINE.name == ""
    assert DEFAULT_AIRLINE.c1 in pixels.values(), "default grey fin not painted"
    assert TYPE not in pixels.values(), "TYPE color painted with no actype"


def test_alt_and_speed_columns_do_not_collide(longboi):
    """Regression for task-10-adversarial finding #1: hires() used to return
    the absolute end-x instead of the advance width, so `iw`/`vx` chains
    double-counted x — the ALT value column overlapped the DIST column for
    climbing/descending flights. Assert ALT stays strictly left of SPEED and
    that DIST is actually painted."""
    render_dashboard(longboi, SAMPLE_AIRCRAFT, clock_ms=MID)  # idx 0 = UA2341
    pixels = lit(longboi)
    alt_xs = [x for (x, _), c in pixels.items() if c == ALT]
    speed_xs = [x for (x, _), c in pixels.items() if c == SPEED]
    dist_xs = [x for (x, _), c in pixels.items() if c == DIST]
    assert alt_xs, "ALT value never painted"
    assert speed_xs, "SPEED value never painted"
    assert dist_xs, "DIST value never painted"
    assert max(alt_xs) < min(speed_xs), "ALT column overlaps/crowds SPEED column"


# Layout collision-guard sweep (2026-07-16, plan
# docs/superpowers/plans/2026-07-16-layout-guards-sweep.md, Task 2). The
# survey harness (tests/survey_layout_gaps.py) found two genuine collision
# surfaces on this worst-case fixture: col-0's ALT value ends only ~3px
# before col-1 starts, and the DIST value overflows its own column budget
# by ~9px into the right margin. The 6px rule (stocks #54): a near-miss on
# macOS metrics is an overlap on the Pi's freetype.
WORST_CASE_AIRCRAFT = Aircraft(
    "WN1234A", "B77W", 41000, -1200, 510, 305, "222KM NE", 222.0, "N7088A"
)


def _spy_value_extents(monkeypatch, canvas, flights, clock_ms=0.0):
    """Render, recording each `hires()` call's (text, end_x) via its ADVANCE
    width — the same measure `hires_text_width`/`fit_text_size` use and the
    one every call site's running-x math is built on (constraint #6: font
    advance width != visible glyph width, so lit-pixel scanning under-counts
    the true collision surface — advance is the correct, cross-platform-safe
    basis, matching the stocks #54 precedent)."""
    import led_ticker_flight.dashboard_layout as dash

    calls = []
    orig_hires = dash.hires

    def spy(shim, text, x, y_top, color, size, **kw):
        adv = orig_hires(shim, text, x, y_top, color, size, **kw)
        calls.append((text, x, x + adv))
        return adv

    monkeypatch.setattr(dash, "hires", spy)
    dash.render_dashboard(canvas, flights, clock_ms=clock_ms)
    return calls


def test_column_values_keep_min_clearance_worst_case(longboi, monkeypatch):
    """Every column value clears the next column by >= _COL_GAP (2px — the
    documented exception to the 6px default: strongly color-differentiated
    neighbors + the design's own pre-guard clearance; CONTRIBUTING.md), and
    the DIST value stays inside the panel's right margin."""
    from led_ticker_flight.dashboard_layout import _COL_GAP

    calls = _spy_value_extents(monkeypatch, longboi, [WORST_CASE_AIRCRAFT])
    real = unwrap_to_real(longboi)
    ends = {text: end for text, _start, end in calls}
    starts = {text: start for text, start, _end in calls}
    alt_end = ends["41,000"]
    spd_start = starts["510"]
    spd_end = ends["510"]
    trk_start = starts["305°"]
    trk_end = ends["305°"]
    dist_start = starts["222KM NE"]
    dist_end = ends["222KM NE"]
    assert spd_start - alt_end >= _COL_GAP, "ALT value crowds the SPD column"
    assert trk_start - spd_end >= _COL_GAP, "SPD value crowds the TRK column"
    assert dist_start - trk_end >= _COL_GAP, "TRK value crowds the DIST column"
    assert real.width - dist_end >= _COL_GAP, (
        "DIST value overflows into the right margin"
    )


def test_row_stays_at_design_size_and_uniform_worst_case(longboi, monkeypatch):
    """At the 2px floor even the survey's worst case fits at the FULL design
    size — the guard must be invisible for all realistic data (James render
    review, 2026-07-16). And the row is UNIFORM: mixed value sizes on one
    row read as broken typography."""
    import led_ticker_flight.dashboard_layout as dash

    sizes: dict[str, int] = {}
    orig_hires = dash.hires

    def spy(shim, text, x, y_top, color, size, **kw):
        sizes[text] = size
        return orig_hires(shim, text, x, y_top, color, size, **kw)

    monkeypatch.setattr(dash, "hires", spy)
    dash.render_dashboard(longboi, [WORST_CASE_AIRCRAFT], clock_ms=0.0)
    vals = {
        t: s for t, s in sizes.items() if t in ("41,000", "510", "305°", "222KM NE")
    }
    assert set(vals.values()) == {16}, f"expected uniform design size, got {vals}"


def test_row_shrinks_uniformly_when_a_value_cannot_fit(longboi, monkeypatch):
    """A genuinely-too-wide value shrinks the WHOLE row together (row-uniform
    fit), never just its own column."""
    import led_ticker_flight.dashboard_layout as dash

    wide = Aircraft(
        "WN1234A", "B77W", 41000, -1200, 510, 305, "1,222KM NNW", 1222.0, "N7088A"
    )
    sizes: dict[str, int] = {}
    orig_hires = dash.hires

    def spy(shim, text, x, y_top, color, size, **kw):
        sizes[text] = size
        return orig_hires(shim, text, x, y_top, color, size, **kw)

    monkeypatch.setattr(dash, "hires", spy)
    dash.render_dashboard(longboi, [wide], clock_ms=0.0)
    vals = {
        t: s for t, s in sizes.items() if t in ("41,000", "510", "305°", "1,222KM NNW")
    }
    assert len(set(vals.values())) == 1, f"row must shrink uniformly, got {vals}"
    assert next(iter(set(vals.values()))) < 16, "an over-wide value must shrink the row"


def test_short_column_values_keep_design_size_16(longboi, monkeypatch):
    """Short-data invariant: with generous per-column headroom, the guard
    must not shrink a column value that already has plenty of clearance —
    the fit ladder's job is to fix real collisions, not shrink everything.
    Asserted via the fit helper's own size selection (spied through
    dashboard_layout.hires), not by pixel-pinning a width."""
    import led_ticker_flight.dashboard_layout as dash

    short = Aircraft("UA123", "B738", 800, 0, 90, 5, "1KM N", 1.0, "N123AB")
    sizes: dict[str, int] = {}
    orig_hires = dash.hires

    def spy(shim, text, x, y_top, color, size, **kw):
        sizes[text] = size
        return orig_hires(shim, text, x, y_top, color, size, **kw)

    monkeypatch.setattr(dash, "hires", spy)
    dash.render_dashboard(longboi, [short], clock_ms=0.0)

    assert sizes["800"] == 16
    assert sizes["90"] == 16
    assert sizes["5°"] == 16
    assert sizes["1KM N"] == 16
