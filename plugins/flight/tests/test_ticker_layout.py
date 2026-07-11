from led_ticker.plugin import unwrap_to_real

from led_ticker_flight.data import SAMPLE_AIRCRAFT
from led_ticker_flight.palette import DIST, IDENT, TYPE
from led_ticker_flight.ticker_layout import render_ticker


def lit(canvas_or_real):
    return dict(unwrap_to_real(canvas_or_real)._pixels)


def _colors(canvas):
    return set(lit(canvas).values())


def test_stream_enters_from_right(smallsign):
    render_ticker(smallsign, SAMPLE_AIRCRAFT, clock_ms=0)
    pixels = lit(smallsign)
    assert pixels, "nothing drawn at t=0"
    # at t=0 offset=0: stream starts at x=width -> only wraparound copy visible


def test_stream_advances_between_ticks():
    from led_ticker.plugin import HeadlessCanvas

    a = HeadlessCanvas(160, 16)
    b = HeadlessCanvas(160, 16)
    render_ticker(a, SAMPLE_AIRCRAFT, clock_ms=1000)
    render_ticker(b, SAMPLE_AIRCRAFT, clock_ms=2000)
    assert lit(a) != lit(b), "26 px/s crawl did not move in 1s"


def test_semantic_colors_present_mid_crawl(smallsign):
    # 20s in, several tokens on screen: expect ident white + a field color
    render_ticker(smallsign, SAMPLE_AIRCRAFT, clock_ms=20000)
    cols = _colors(smallsign)
    semantic = {IDENT, TYPE, DIST, (255, 180, 0), (60, 220, 60), (0, 220, 255)}
    assert len(cols & semantic) >= 2, f"expected multiple semantic colors, got {cols}"


def test_row_vertically_centered(smallsign):
    render_ticker(smallsign, SAMPLE_AIRCRAFT, clock_ms=20000)
    ys = {y for (_, y) in lit(smallsign) if (_, y) != (159, 1)}  # exclude live dot
    assert min(ys) >= 1 and max(ys) <= 14


def test_empty_state_radar(smallsign):
    render_ticker(smallsign, [], clock_ms=800)
    assert lit(smallsign), "empty state drew nothing"


def test_seamless_loop_period(smallsign):
    # clock_ms=0 and clock_ms = period/26*1000 must render identically
    from led_ticker.plugin import HeadlessCanvas

    from led_ticker_flight.ticker_layout import stream_period

    period = stream_period(smallsign, SAMPLE_AIRCRAFT)
    a = HeadlessCanvas(160, 16)
    b = HeadlessCanvas(160, 16)
    render_ticker(a, SAMPLE_AIRCRAFT, clock_ms=0)
    render_ticker(b, SAMPLE_AIRCRAFT, clock_ms=period / 26 * 1000)
    la = {k: v for k, v in lit(a).items() if k != (158, 1)}  # live dot differs by phase
    lb = {k: v for k, v in lit(b).items() if k != (158, 1)}
    assert la == lb
