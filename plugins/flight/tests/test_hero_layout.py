from led_ticker.plugin import HeadlessCanvas, ScaledCanvas, unwrap_to_real

from led_ticker_flight.data import SAMPLE_AIRCRAFT, Aircraft
from led_ticker_flight.hero_layout import DWELL_MS, render_hero
from led_ticker_flight.palette import (
    AIRLINES,
    DEFAULT_AIRLINE,
    DIST,
    IDENT,
    LABEL,
    TRACK,
    TYPE,
)

# Mid-dwell offset: with 2+ flights the fade-through-black zeroes brightness
# at both dwell-window edges (see test_fade_layout.py), so tests that just
# want a stable, fully-bright frame for a given flight index anchor here
# instead of at the dwell boundary (clock_ms=0 / DWELL_MS, etc).
MID = DWELL_MS // 2


def lit(canvas_or_real):
    return dict(unwrap_to_real(canvas_or_real)._pixels)


def test_fin_at_pinned_position(bigsign):
    render_hero(bigsign, SAMPLE_AIRCRAFT, clock_ms=MID)  # idx 0 = UA2341
    pixels = lit(bigsign)
    ua = AIRLINES["UA"]
    # fin bottom-left: r=27 -> leftX=0 -> pixel at (4, 3+27) in c1
    assert pixels[(4, 30)] == ua.c1
    # accent band r=14,15,16,17 -> c2 at the fin's right edge (x = 4+22)
    assert pixels[(26, 17)] == ua.c2


def test_hero_ident_is_white_hires_band(bigsign):
    render_hero(bigsign, SAMPLE_AIRCRAFT, clock_ms=MID)
    white = [(x, y) for (x, y), c in lit(bigsign).items() if c == IDENT]
    in_band = [p for p in white if 35 <= p[0] <= 200 and 1 <= p[1] <= 30]
    assert len(in_band) > 50, "hero callsign not present as hires white pixels"


def test_rotation_advances_at_dwell(bigsign):
    a = ScaledCanvas(HeadlessCanvas(256, 64), scale=4, content_height=16)
    b = ScaledCanvas(HeadlessCanvas(256, 64), scale=4, content_height=16)
    render_hero(a, SAMPLE_AIRCRAFT, clock_ms=MID)  # UA2341
    render_hero(b, SAMPLE_AIRCRAFT, clock_ms=DWELL_MS + MID)  # DL815
    assert lit(a) != lit(b)


def test_paging_dots_current_index(bigsign):
    render_hero(bigsign, SAMPLE_AIRCRAFT, clock_ms=MID)
    pixels = lit(bigsign)
    n = 4
    x0 = 256 - n * 8 - 4
    y0 = 64 - 8 - 2
    assert pixels[(x0, y0)] == IDENT  # current = idx 0
    assert pixels[(x0 + 8, y0)] == LABEL


def test_vr_level_bar_for_level_flight(bigsign):
    # WN88 (idx 2) has vr=0 -> level bar, amber
    render_hero(bigsign, SAMPLE_AIRCRAFT, clock_ms=2 * DWELL_MS + MID)
    pixels = lit(bigsign)
    amber_low = [
        (x, y)
        for (x, y), c in pixels.items()
        if c == (255, 180, 0) and 44 <= y <= 60 and x < 15
    ]
    assert amber_low, "level bar missing"


def test_empty_state(bigsign):
    render_hero(bigsign, [], clock_ms=100)
    assert lit(bigsign)


def test_unknown_airline_renders_default_grey_no_type_row(bigsign):
    """N-number callsigns (general aviation registrations, not airline
    flight numbers) are the majority real-world case — airline_of() falls
    back to DEFAULT_AIRLINE (name == ""). Must not raise, must fin in the
    default grey, and must not draw a name/type row (al.name == "" and
    actype == "" both gate their `hires(...)` calls off)."""
    unknown = Aircraft("N12345", "", 3500, 0, 120, 180, "5KM N", 5.0, "N12345")
    render_hero(bigsign, [unknown], clock_ms=0)
    pixels = lit(bigsign)
    assert DEFAULT_AIRLINE.name == ""
    assert DEFAULT_AIRLINE.c1 in pixels.values(), "default grey fin not painted"
    assert TYPE not in pixels.values(), "TYPE color painted with no actype"


def test_metrics_line_dist_and_track_land_on_canvas(bigsign):
    """Regression for task-10-adversarial finding #1: hires() used to return
    the absolute end-x instead of the advance width, so the metrics-line
    `x += hires(...) + gap` chain double-counted x — DIST was never painted
    (walked off the 256-px canvas) and TRACK was clipped at the right edge."""
    render_hero(bigsign, SAMPLE_AIRCRAFT, clock_ms=MID)  # idx 0 = UA2341
    pixels = lit(bigsign)
    dist_xs = [x for (x, _), c in pixels.items() if c == DIST]
    assert dist_xs, "DIST field never painted"
    track_xs = [x for (x, _), c in pixels.items() if c == TRACK]
    assert track_xs, "TRACK field never painted"
    assert max(track_xs) < 256 - 8, "TRACK field clipped into/past the paging-dot zone"
