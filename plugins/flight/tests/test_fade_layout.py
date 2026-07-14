"""Fade-through-black between rotating flights on hero/dashboard.

With 2+ tracked flights, render_hero/render_dashboard fade the whole card
through black for paint.FADE_MS at each end of its DWELL_MS window (a hard
cut between rotating flights read as a glitch on the physical panel per
hardware review). A single held flight never fades. See paint.FADE_MS and
the `bright` computation in hero_layout.render_hero / dashboard_layout.
render_dashboard.
"""

from led_ticker.plugin import HeadlessCanvas, ScaledCanvas, unwrap_to_real

from led_ticker_flight import dashboard_layout, hero_layout
from led_ticker_flight.data import SAMPLE_AIRCRAFT, Aircraft
from led_ticker_flight.paint import FADE_MS
from led_ticker_flight.palette import AIRLINES

UA = AIRLINES["UA"]


def lit(canvas_or_real):
    return dict(unwrap_to_real(canvas_or_real)._pixels)


def _scaled(rgb, bright):
    r, g, b = rgb
    return (int(r * bright), int(g * bright), int(b * bright))


def _bigsign():
    return ScaledCanvas(HeadlessCanvas(256, 64), scale=4, content_height=16)


def _longboi():
    return ScaledCanvas(HeadlessCanvas(512, 64), scale=4, content_height=16)


def test_hero_fin_dims_exactly_near_dwell_end():
    # Both clock values fall within idx-0's dwell window (UA2341), so the
    # only difference between the two renders is the fade brightness.
    mid = hero_layout.DWELL_MS // 2  # far from either edge -> b == 1.0
    near_end = hero_layout.DWELL_MS - 50  # 50ms from the end -> b == 0.25

    mid_canvas = _bigsign()
    hero_layout.render_hero(mid_canvas, SAMPLE_AIRCRAFT, clock_ms=mid)
    mid_pixels = lit(mid_canvas)
    assert mid_pixels[(4, 30)] == UA.c1  # full bright: exact fin color

    end_canvas = _bigsign()
    hero_layout.render_hero(end_canvas, SAMPLE_AIRCRAFT, clock_ms=near_end)
    end_pixels = lit(end_canvas)
    assert end_pixels[(4, 30)] == _scaled(UA.c1, 0.25)


def test_hero_fully_black_at_exact_dwell_boundary():
    # clock_ms == DWELL_MS lands exactly on the boundary between idx 0 and
    # idx 1's windows: pos = clock_ms % DWELL_MS == 0 -> b == 0.0. A fully
    # black frame is acceptable here (every painted pixel is (0, 0, 0)).
    canvas = _bigsign()
    hero_layout.render_hero(canvas, SAMPLE_AIRCRAFT, clock_ms=hero_layout.DWELL_MS)
    pixels = lit(canvas)
    assert pixels, "expected the layout to paint something (even if black)"
    assert all(c == (0, 0, 0) for c in pixels.values())


def test_hero_single_flight_never_fades():
    # A single held flight has len(flights) == 1 -> the fade guard never
    # fires, even at a clock_ms that would be a dwell boundary for 2+
    # flights (b would otherwise be 0.0 there).
    canvas = _bigsign()
    solo = [SAMPLE_AIRCRAFT[0]]
    hero_layout.render_hero(canvas, solo, clock_ms=hero_layout.DWELL_MS)
    pixels = lit(canvas)
    assert pixels[(4, 30)] == UA.c1  # exact, undimmed fin color


def test_dashboard_fin_dims_exactly_near_dwell_end():
    mid = dashboard_layout.DWELL_MS // 2
    near_end = dashboard_layout.DWELL_MS - 50

    mid_canvas = _longboi()
    dashboard_layout.render_dashboard(mid_canvas, SAMPLE_AIRCRAFT, clock_ms=mid)
    mid_pixels = lit(mid_canvas)
    assert mid_pixels[(6, 37)] == UA.c1

    end_canvas = _longboi()
    dashboard_layout.render_dashboard(end_canvas, SAMPLE_AIRCRAFT, clock_ms=near_end)
    end_pixels = lit(end_canvas)
    assert end_pixels[(6, 37)] == _scaled(UA.c1, 0.25)


def test_dashboard_fully_black_at_exact_dwell_boundary():
    canvas = _longboi()
    dashboard_layout.render_dashboard(
        canvas, SAMPLE_AIRCRAFT, clock_ms=dashboard_layout.DWELL_MS
    )
    pixels = lit(canvas)
    assert pixels, "expected the layout to paint something (even if black)"
    assert all(c == (0, 0, 0) for c in pixels.values())


def test_dashboard_single_flight_never_fades():
    canvas = _longboi()
    unknown = Aircraft("N12345", "", 3500, 0, 120, 180, "5KM N", 5.0, "N12345")
    dashboard_layout.render_dashboard(
        canvas, [unknown], clock_ms=dashboard_layout.DWELL_MS
    )
    # Not comparing exact colors here (unknown airline uses DEFAULT_AIRLINE,
    # a different c1) — assert the frame isn't the all-black result the
    # 2+-flight fade guard would otherwise produce at this exact clock_ms.
    pixels = lit(canvas)
    assert any(c != (0, 0, 0) for c in pixels.values())


def test_fade_ms_constant_is_200():
    assert FADE_MS == 200.0
