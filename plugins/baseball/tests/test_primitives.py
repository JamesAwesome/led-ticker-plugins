"""tests/test_primitives.py — procedural primitives ARE pinned pixel-exact
(they are deterministic; no freetype involved).

`draw_record` is the one exception (it composites freetype hi-res text via
`_paint.hires`) — asserted by advance-sum and by-column color class only,
same convention as tests/test_paint.py and the layout test suites."""

from led_ticker.plugin import HeadlessBackend, make_color

from led_ticker_baseball import _paint
from led_ticker_baseball import _palette as pal
from led_ticker_baseball import _primitives as prim


def _real(w=64, h=64):
    # HeadlessBackend takes (width, height) positionally — see
    # led_ticker/backends/headless.py. There is no rows/cols/chain_length
    # kwarg surface on this backend (that's an RgbMatrixBackend shape).
    return HeadlessBackend(w, h).create_canvas()


def _lit(real):
    # HeadlessCanvas has no iter_coords()/iter_pixels(); its supported read
    # surface is get_pixel(x, y) plus the `_pixels` dict it serializes from
    # (see led_ticker/backends/headless.py — get_pixel is "the supported
    # backend serialization read"). Sibling plugins (stocks/test_paint.py,
    # this plugin's own test_paint.py) already reach into `_pixels` directly
    # for this exact "any lit pixel" check, so we follow that precedent here.
    return {xy for xy, v in real._pixels.items() if v != (0, 0, 0)}


def test_diamond_filled_manhattan_exact():
    real = _real()
    prim.diamond(real, 10, 10, 2, True, pal.IDENT, 1.0)
    expect = {
        (10 + dx, 10 + dy)
        for dx in range(-2, 3)
        for dy in range(-2, 3)
        if abs(dx) + abs(dy) <= 2
    }
    assert _lit(real) == expect


def test_diamond_outline_is_ring():
    real = _real()
    prim.diamond(real, 10, 10, 3, False, pal.LABEL, 0.7)
    lit = _lit(real)
    assert (10, 10) not in lit  # hollow center
    assert (13, 10) in lit and (10, 13) in lit  # ring extremes
    r, g, b = real.get_pixel(13, 10)  # dimmed LABEL
    assert (r, g, b) == (int(70 * 0.7), int(90 * 0.7), int(130 * 0.7))


def test_pip_disc_vs_ring():
    real = _real()
    prim.pip(real, 8, 8, 3, True, pal.LOSS, 1.0)
    assert (8, 8) in _lit(real)
    real2 = _real()
    prim.pip(real2, 8, 8, 3, False, pal.LABEL, 0.7)
    assert (8, 8) not in _lit(real2)


def test_series_dashes_won_orange_unwon_dim():
    real = _real()
    prim.series_dashes(real, 4, 10, 1, pal.IDENT)
    assert real.get_pixel(4, 10) == (255, 128, 0)  # slot 0 won: ORANGE
    r, g, b = real.get_pixel(4, 15)  # slot 1 (y+5) unwon
    assert (r, g, b) == (35, 45, 65)  # LABEL dim 0.5


def test_challenge_dashes_one_remaining_orange_then_grey():
    real = _real()
    prim.challenge_dashes(real, 4, 10, 1)
    assert real.get_pixel(4, 10) == (255, 140, 0)  # slot 0 remaining: CHALLENGE
    assert real.get_pixel(4, 15) == (140, 140, 140)  # slot 1 (y+5) used: CHALLENGE_USED


def test_challenge_dashes_two_remaining_all_orange():
    real = _real()
    prim.challenge_dashes(real, 4, 10, 2)
    assert real.get_pixel(4, 10) == (255, 140, 0)
    assert real.get_pixel(4, 15) == (255, 140, 0)


def test_challenge_dashes_zero_remaining_all_grey():
    real = _real()
    prim.challenge_dashes(real, 4, 10, 0)
    assert real.get_pixel(4, 10) == (140, 140, 140)
    assert real.get_pixel(4, 15) == (140, 140, 140)


def test_challenge_dashes_caps_two_slots():
    # A remaining count above the 2-slot display caps at two orange slots
    # (no third dash painted below slot 1).
    real = _real()
    prim.challenge_dashes(real, 4, 10, 5)
    assert real.get_pixel(4, 10) == (255, 140, 0)
    assert real.get_pixel(4, 15) == (255, 140, 0)
    assert real.get_pixel(4, 20) == (0, 0, 0)  # no third slot


def test_challenge_uses_distinct_orange_from_series():
    # CHALLENGE (255,140,0) must stay visually distinct from the series-win
    # ORANGE (255,128,0) so the two dash pairs don't read as the same field.
    assert (pal.CHALLENGE.red, pal.CHALLENGE.green, pal.CHALLENGE.blue) == (255, 140, 0)
    assert (pal.CHALLENGE.green,) != (pal.ORANGE.green,)


def test_chip_unknown_team_grey_two_tone_with_knocked_corners():
    real = _real()
    prim.chip(real, 0, 0, 12, "???")
    lit = _lit(real)
    assert (0, 0) not in lit and (11, 11) not in lit  # corners knocked (r=2)
    assert (2, 9) in lit and (9, 2) in lit  # both triangles painted
    assert real.get_pixel(2, 9) != real.get_pixel(9, 2)  # two tones


def test_dotted_divider_every_third_pixel():
    real = _real()
    prim.dotted_divider(real, 4, 16, 31)
    assert real.get_pixel(4, 31) != (0, 0, 0)
    assert real.get_pixel(5, 31) == (0, 0, 0)
    assert real.get_pixel(7, 31) != (0, 0, 0)


def test_draw_record_advance_equals_sum_of_parts():
    real = _real(200, 32)
    shim, _ = _paint.phys_wrap(real)
    advance = prim.draw_record(shim, 10, 10, 12, 34, 10)
    expected = (
        _paint.text_width(10, "12")
        + _paint.text_width(10, "-")
        + _paint.text_width(10, "34")
    )
    assert advance == expected
    assert advance > 0


def test_draw_record_colors_win_dash_loss_left_to_right():
    real = _real(200, 32)
    shim, _ = _paint.phys_wrap(real)
    x = 10
    w1 = _paint.text_width(10, "12")
    w2 = _paint.text_width(10, "-")
    prim.draw_record(shim, x, 10, 12, 34, 10)
    lit = _lit(real)

    def _colors_in(x0, x1):
        return {real.get_pixel(px_, y) for px_, y in lit if x0 <= px_ < x1}

    win_region = _colors_in(x, x + w1)
    dash_region = _colors_in(x + w1, x + w1 + w2)
    loss_region = _colors_in(x + w1 + w2, x + w1 + w2 + 20)

    assert (pal.WIN.red, pal.WIN.green, pal.WIN.blue) in win_region
    assert (pal.LABEL.red, pal.LABEL.green, pal.LABEL.blue) in dash_region
    assert (pal.LOSS.red, pal.LOSS.green, pal.LOSS.blue) in loss_region


def test_bar_fill_width_matches_fraction():
    real = _real(256, 64)
    prim.draw_bar(real, 4, 40, 200, 8, 0.5, make_color(0, 200, 255))
    # track fills the whole 200px dimly; the bright fill covers ~100px.
    # Isolate the fill color band by checking the leftmost 100 vs rightmost 100.
    track_color = pal.dim(pal.LABEL, 0.32)
    track_tuple = (track_color.red, track_color.green, track_color.blue)
    fill_cols = {x for (x, y) in _lit(real) if real.get_pixel(x, y) != track_tuple}
    assert fill_cols and max(fill_cols) - 4 <= 100  # fill stops near the half mark


def test_bar_tick_in_bounds_and_at_fraction():
    real = _real(256, 64)
    prim.draw_bar(real, 4, 40, 200, 8, 0.9, make_color(0, 200, 255), tick_frac=0.7)
    # tick column ~ 4 + round(200*0.7) = 144; must be within [4, 204)
    ident_tuple = (pal.IDENT.red, pal.IDENT.green, pal.IDENT.blue)
    tick_cols = {x for (x, y) in _lit(real) if real.get_pixel(x, y) == ident_tuple}
    assert tick_cols
    assert all(4 <= x < 204 for x in tick_cols)
    assert 140 <= min(tick_cols) <= 148


def test_bar_tick_frac_one_stays_in_bounds():
    real = _real(256, 64)
    prim.draw_bar(real, 4, 40, 200, 8, 1.0, make_color(0, 200, 255), tick_frac=1.0)
    ident_tuple = (pal.IDENT.red, pal.IDENT.green, pal.IDENT.blue)
    tick_cols = {x for (x, y) in _lit(real) if real.get_pixel(x, y) == ident_tuple}
    assert tick_cols and max(tick_cols) < 204  # never paints at/after x+w


def test_bar_frac_clamps():
    real = _real(256, 64)
    # clamps to full, no raise
    prim.draw_bar(real, 4, 40, 200, 8, 2.0, make_color(0, 200, 255))
